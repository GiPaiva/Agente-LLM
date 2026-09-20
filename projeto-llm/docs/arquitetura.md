# A arquitetura básica — item 4.4 da entrega

> O que este documento responde: quais são as ferramentas, qual é o laço, onde
> está o estado, qual é o orçamento, quais são as condições de término, onde o
> **modelo** decide e onde o **código** decide — e, no fim, a pergunta que vale
> ponto: *onde está a decisão que justifica um agente em vez de um workflow?*

---

## 1. O desenho

```
   ENTRADA
   operador digita em texto livre                              [—]
   "o arroz de 5kg está acabando, veja se precisamos pedir mais"
        |
        v
   +--------------------------------------------------------------+
   |  ESTADO (src/agente.py)                                       |
   |    objetivo        a pergunta, imutável — a âncora            |
   |    passos[]        ferramenta, argumentos, resultado, erro    |
   |    tokens_gastos   entrada + saída acumuladas                 |
   |    fase            "analise" -> "reposicao"                   |
   |    ferramentas_ativas   o que o modelo PODE ver agora         |
   |    historico       visão do modelo — DERIVADA, não a verdade  |
   +--------------------------------------------------------------+
        |
        |   montar_mensagens(estado)   <- traduz o estado para a API
        v
   +==============================================================+
   ||  O LAÇO ReAct                    while True                ||
   ||                                                            ||
   ||   [1] orçamento estourou? ------------------> ORCAMENTO     ||  CÓDIGO
   ||   [2] laço detectado? --- injeta observação                 ||  CÓDIGO
   ||        repetiu de novo? --------------------> LACO          ||  CÓDIGO
   ||   [3] chamar o modelo, com as ferramentas ATIVAS            ||
   ||        falha de transporte? ----------------> ERRO_FATAL    ||  CÓDIGO
   ||   [4] veio tool_call?                                       ||  MODELO
   ||        não  ------------------------------->  RESPONDEU     ||
   ||        sim  -> executar() -> registra o passo               ||
   ||   [5] GATING: liberar a escrita?                            ||  CÓDIGO
   ||                                                            ||
   ||   volta para [1]                                            ||
   +==============================================================+
        |                        |
        |                        +---> executar()  a ACTION do ReAct
        |                                 |
        v                                 v
   RETORNO                        +-----------------------------+
   texto curto ao operador        |  FERRAMENTAS                |
   + [término · passos · tokens]  |                             |
                                  |  consultar_estoque      L   |
                                  |  consultar_fornecedor   L   |
                                  |  calcular_reposicao     C   |
                                  |  criar_solicitacao_     E   |
                                  |    compra        (gated)    |
                                  +-----------------------------+
                                            |
                                            v  (src/db.py — a fronteira)
                                  +-----------------------------+
                                  |  SQLite  dados/estoque.db   |
                                  |  produtos · fornecedores    |
                                  |  orcamento · solicitacoes   |
                                  +-----------------------------+

   L = leitura   C = cálculo   E = escrita (reversível, idempotente)
```

## 2. Quem decide em cada ponto

A marcação que o item 4.4 pede, e que costuma surpreender: **a maioria dos
passos é código.**

| # | Passo | Quem decide | Por quê |
|---|---|---|---|
| 1 | teto de passos / tokens / tempo | **CÓDIGO** | orçamento não se negocia com o modelo |
| 2 | detecção de laço | **CÓDIGO** | o modelo não percebe que está girando |
| 3 | quais ferramentas o modelo pode ver | **CÓDIGO** | é o gating, §4 |
| 4 | **qual ferramenta chamar, e com que argumento** | **MODELO** | é a decisão em tempo de execução |
| 5 | **a pergunta pede ação ou só informação?** | **MODELO** | não é classificável por regra |
| 6 | **o que o operador diz bate com o dado?** | **MODELO** | é julgamento, não comparação |
| 7 | o produto está abaixo do mínimo | **CÓDIGO** | `abaixo_do_minimo`, comparação de dois inteiros |
| 8 | a quantidade a repor | **CÓDIGO** | `calcular_reposicao`, aritmética |
| 9 | a compra passa do teto de R$ 500 | **CÓDIGO** | regra de negócio, não opinião |
| 10 | erro recuperável ou fatal | **CÓDIGO** | quem classifica erro nunca é o modelo |
| 11 | como escrever a resposta | **MODELO** | com os fatos que o código garantiu |

## 3. O orçamento e as condições de término

Três tetos, porque `max_passos` sozinho não é orçamento: um passo consome de
algumas centenas a dezenas de milhares de tokens.

| Teto | Valor | Por quê este valor |
|---|---|---|
| `max_passos` | 8 | a trajetória mais longa medida usa **3** passos (caso 1: consulta, calcula, registra); 8 dá folga para duas buscas erradas e ainda para |
| `max_tokens` | 60.000 | a execução mais cara medida gastou **8.607**; o teto existe para o caso patológico, não para o caso típico |
| `max_segundos` | 300 | a execução mais cara medida levou ~30 s no modelo local; acima de 300 s o operador já desistiu |

E um quarto teto, que é por chamada e não por execução:

| Parâmetro | Valor | Por quê |
|---|---|---|
| `max_tokens` (por chamada) | 800 | a resposta mais longa do sistema tem ~80 tokens. Além de evitar resposta interminável, é o que faz a cota gratuita da Groq aceitar a requisição — ver [`modelos.md`](modelos.md) §3.3 |

E **cinco** formas de terminar — todas nomeadas, todas gravadas no log:

```
RESPONDEU          o modelo concluiu e devolveu texto
ORCAMENTO          bateu um dos três tetos — o log diz QUAL
LACO               repetiu a mesma chamada mesmo após a intervenção
TRUNCADO           a resposta foi cortada por max_tokens
ERRO_FATAL         falha de transporte, depois das tentativas de repetição
```

`TRUNCADO` é separado de `RESPONDEU` de propósito: um texto cortado **parece**
uma resposta e não é. Sem a distinção, o verificador contaria meia resposta
como acerto e o log diria "respondeu" para uma frase pela metade.

E `ERRO_FATAL` só acontece depois de o laço tentar de novo — mas **apenas em
falha de transporte** (5xx, conexão caída). Erro de configuração (401, 403,
404, 422) aborta na primeira tentativa, porque repetir esconderia a causa. A
distinção é da aula 05, e ganhou uso real: um `530` do túnel Cloudflare
derrubou uma suíte de 28 minutos pela metade.

O programa **sempre diz por que parou** (item 4.1, "terminação registrada"), e
a trajetória inteira vai para `logs/` em todos os caminhos — inclusive nos que
falham, que são os que interessam quando algo dá errado.

## 4. O gating — restrição por arquitetura

Esta é a peça que mais mudou em relação ao esboço, e a que sustenta o critério
de sucesso.

O agente **começa sem a ferramenta de escrita**. Quem a habilita é o código, e
só depois que um `consultar_estoque` desta execução devolveu
`abaixo_do_minimo: true`:

```
fase "analise"     consultar_estoque · consultar_fornecedor · calcular_reposicao
                            |
                            |  consultar_estoque devolveu abaixo_do_minimo: true
                            v
fase "reposicao"   ... as três acima + criar_solicitacao_compra
```

A razão está na aula 05, nota 02 §6: *"restrição por arquitetura vence
restrição por prompt — instrução ele pode ignorar, ferramenta não declarada ele
não tem como chamar."*

O critério de sucesso do case tem um lado assimétrico: criar uma compra
indevida mexe no orçamento real da loja, enquanto deixar de recomendar uma
necessária custa uma pergunta a mais. No esboço, "nunca compre no caso 4" era
uma frase no prompt — ou seja, uma esperança. Aqui é uma propriedade do
sistema: nas famílias 2, 3, 4 e 5 do conjunto rotulado a ferramenta de escrita
**nunca chega a ser oferecida** ao modelo.

E isso é **verificável**: cada log grava o bloco `gating`, e `src/avaliar.py`
confere `escrita_foi_oferecida` contra o rótulo. A diferença entre "o modelo
não chamou" e "o modelo não podia chamar" é a diferença entre sorte e desenho.

## 5. As ferramentas

| Ferramenta | O que faz | L/E | Reversível? | Contra o que conversa |
|---|---|---|---|---|
| `consultar_estoque` | estoque, mínimo, giro, preço, e `abaixo_do_minimo` | Leitura | — | SQLite via `src/db.py` |
| `consultar_fornecedor` | prazo e pedido mínimo | Leitura | — | SQLite via `src/db.py` |
| `calcular_reposicao` | quantidade e custo, já com o pedido mínimo aplicado | Cálculo | — | SQLite + aritmética em código |
| `criar_solicitacao_compra` | registra a solicitação | **Escrita** | **Sim** — cancelável, não envia nada a ninguém | SQLite via `src/db.py` |

Três propriedades das ferramentas, e nenhuma é decoração:

**A descrição é prompt.** Cada declaração diz o que a ferramenta faz, quando
usar e **quando não usar** (aula 03, nota 04 §4).

**O erro é dado, não exceção.** `ErroRecuperavel` volta para o modelo como
observação, com a lista de alternativas junto — é o que ensina o modelo a se
corrigir. `ErroFatal` aborta o laço. Quem classifica é o código.

**A escrita é idempotente.** A chave (`ARROZ_5KG:50`) identifica a **operação**,
não a tentativa: repetir a chamada devolve a solicitação existente com
`ja_existia: true`, informação que o modelo usa para saber que já agiu.

## 6. A fronteira com software tradicional (item 4.2)

`src/db.py` é a camada de acesso, e as ferramentas **nunca** escrevem SQL. O
agente atravessa a fronteira do próprio processo e lida com o que isso traz:
registro ausente, termo ambíguo, formato inesperado.

É também a fronteira escolhida para virar **servidor MCP na Parte 2** — foi
isolada com isso em vista: trocar SQLite por MCP muda um arquivo.

## 7. A pergunta do item 4.4

> **Onde, neste desenho, está a decisão que justifica um agente em vez de um
> workflow?**

Nos passos **4, 5 e 6** da tabela da §2 — e o caso que prova isso é a família
2 do conjunto rotulado.

Um workflow fixo seria `if estoque < minimo: criar_solicitacao`. Ele acerta as
famílias 1 e 4 sem modelo nenhum. Mas erra a 2: o operador chega dizendo *"o
refrigerante está acabando, já pode pedir?"* e o banco mostra 85 unidades
contra um mínimo de 20. O workflow responde "não" e pronto. O que o caso exige
é reconhecer que **há uma contradição entre o que a pessoa viu e o que o
registro diz**, e relatar as duas coisas — porque quem está na loja pode ter
visto a gôndola vazia com o estoque no depósito.

Isso não é classificação, é julgamento sobre uma frase em texto livre, e não
cabe numa regra: a pergunta chega em formulações que ninguém enumera de
antemão ("acabou na gôndola", "tô vendo que zerou", "está abaixo do mínimo,
né?"). As quatro formulações da família 2 do conjunto rotulado são exatamente
essas, e o sistema acerta **9 de 12** — a medição está em
[`modelos.md`](modelos.md) §3.3.

**Por que não o nível abaixo.** Um **Router** resolveria *"que tipo de pergunta
é essa"* — consulta, reposição, dúvida. Não resolve *"o operador está certo ou
o sistema está certo"*, que é o que decide a resposta. Por isso o nível é
agente, e não roteador.

**E a honestidade da conta:** a maior parte deste sistema **é** workflow. Sete
dos onze pontos de decisão são código, e é assim que deve ser — a regra da
disciplina é *use a menor autonomia que resolve*. O agente existe por causa de
três pontos, e eles estão medidos: são as famílias 2 e 5 do conjunto rotulado,
as duas que um `if` não cobre.

## 8. O que muda na Parte 2

| Peça de hoje | Vira |
|---|---|
| `src/db.py` | **servidor MCP** — a fronteira já está isolada |
| o laço à mão em `src/agente.py` | **LangGraph**, com a comparação "o que o framework deu e o que tirou" |
| as regras que hoje moram no prompt | **RAG** sobre política de compras e contratos de fornecedor (`ideia-evolucao/base-de-conhecimento-v1.md`) |
| nada — cada execução começa do zero | **memória entre execuções**: o que já foi pedido esta semana |
| o gating por fase | o **Avaliador** desenhado em `ideia-evolucao/v2.md` §5 |
