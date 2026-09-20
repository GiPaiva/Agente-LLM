# Case — Assistente de reposição de estoque para supermercado de pequeno porte

> Itens 1 e 2 da entrega. A arquitetura do agente está em
> [`arquitetura.md`](arquitetura.md), a análise de modelos em
> [`modelos.md`](modelos.md), e o histórico de decisões em
> [`decisoes.md`](decisoes.md).

---

## 1. O problema

**Em uma frase:** o operador de estoque de um supermercado de pequeno porte
decide, várias vezes por dia, se e quanto pedir de cada produto, cruzando de
cabeça estoque atual, giro de venda e pedido mínimo do fornecedor — sem nenhum
sistema que junte essas três informações.

**Quem sofre com isso hoje:** o **operador de estoque/reposição do turno**, que
também atende cliente e repõe gôndola ao mesmo tempo. Não é "o supermercado" —
é essa pessoa específica, no meio do turno, tentando lembrar se já pediu arroz
esta semana.

### O contexto de onde o agente vai ser usado

**Onde roda.** Dentro da rotina do próprio operador, no computador do balcão de
estoque, acionado por ele mesmo. (Um agente proativo, acordado por um evento de
estoque baixo, é o passo natural seguinte — está fora do escopo desta Parte 1
porque exige um scheduler, e porque o que se prova aqui é outra coisa.)

**O que existe antes e depois.** Antes: a pergunta do operador, em texto livre
("o arroz está acabando, peço mais?"). Depois: uma solicitação de compra
registrada, com status. Quem consome o resultado são duas pessoas — o próprio
operador, que precisa saber se está resolvido, e o gerente, que precisa aprovar
o que passou do teto.

**O que acontece hoje sem ele.** O operador confere a prateleira no olho, às
vezes abre a planilha do PDV, e decide de memória se o pedido mínimo do
fornecedor já foi atingido. **Não fica registro de por que aquela quantidade foi
pedida** — e esse é o problema que mais dói depois, quando alguém pergunta.

**As regras do domínio.** Estoque mínimo por produto. Pedido mínimo por
fornecedor (abaixo dele o fornecedor não atende). Orçamento mensal de compras,
com teto de **R$ 500** de comprometimento sem aprovação do gerente — regra
herdada do desenho em `ideia-evolucao/v2.md` §5.

**O que dá errado hoje** — o item mais valioso, porque é o que define o sistema:

1. O operador confunde *"está vendendo bem"* com *"está abaixo do mínimo"*. São
   coisas diferentes: um produto vende rápido e tem estoque alto; outro vende
   devagar e está raspando.
2. Pede quantidade errada porque esqueceu o pedido mínimo do fornecedor — e o
   pedido volta.
3. **Vê a gôndola vazia e conclui que o estoque acabou**, quando o que faltou
   foi repor do depósito. É o caso mais interessante, e virou a família 2 do
   conjunto de teste.
4. Pergunta por um produto que não existe mais no cadastro, ou por um nome
   genérico que casa com dois produtos ("o açúcar" — 1kg ou 5kg?).

---

## 2. Os usuários, e como o agente conversa com eles

| Perfil | O que ele quer | O que ele sabe | O que ele **pode** fazer |
|---|---|---|---|
| **Operador de estoque** *(principal)* | saber rápido se precisa repor, e já deixar a solicitação pronta | conhece a loja e os produtos; não conhece o sistema a fundo | pergunta · confirma o produto quando ambíguo · aceita ou ignora a recomendação |
| **Gerente** | aprovar compras acima do teto, ver quanto sobrou do orçamento | conhece o orçamento e as regras de aprovação | **aprova ou recusa** solicitação pendente — a única ação de alçada |
| Fornecedor *(indireto, fora do escopo desta parte)* | receber o pedido certo | nada do sistema | responde ao pedido (Parte 2/3) |

**Usuário principal: o operador.** É para ele que o sistema responde quando os
interesses conflitam — ele quer resposta rápida, o gerente quer rastreabilidade.
A escolha: responder rápido **e** registrar tudo, sem fazer o operador esperar a
aprovação do gerente para receber a resposta.

**Quem aprova ação irreversível.** Nesta Parte 1 **não existe ação
irreversível**: `criar_solicitacao_compra` grava no banco e não envia nada a
ninguém — é cancelável. O envio real ao fornecedor, esse sim irreversível, é
Parte 2/3, e quem confirma é o **gerente**.

### Como é a interação

- **Por onde:** texto livre, no terminal. É o canal mais rápido para quem está
  no meio do turno — sem formulário, sem campo obrigatório. E é o canal que
  força o sistema a lidar com a linguagem real ("tá acabando o arroz").
- **Quem começa:** o operador. Sempre, nesta parte.
- **Quantas trocas:** normalmente 1 — pergunta e resposta, com o agente
  resolvendo por dentro em 1 a 3 chamadas de ferramenta. **Vira 2 quando o termo
  é ambíguo**: o sistema pergunta qual produto, e aí sim espera.
- **O que o sistema devolve:** texto curto em português — o que encontrou, o que
  calculou, e se registrou uma solicitação (com protocolo e status). Mais uma
  linha técnica entre colchetes: término, passos e tokens.
- **Como termina:** com sucesso, o operador sabe se precisa fazer algo mais
  (avisar o gerente, se ficou pendente). Sem sucesso, o sistema **diz o que não
  achou e o que existe** — nunca inventa número, nunca culpa "o sistema".

### Diálogo 1 — o caso simples

```
Operador:   O arroz de 5kg está acabando, veja se precisamos pedir mais.

Assistente: O estoque de Arroz 5kg está em 12 unidades, abaixo do mínimo de 30.
            Recomendo repor 50 unidades (o pedido mínimo do Fornecedor A).
            Solicitação registrada: protocolo ARROZ_5KG:50, custo estimado
            R$ 925,00 — acima do limite de R$ 500, então está aguardando
            aprovação do gerente. Prazo de entrega: 2 dias.
```

### Diálogo 2 — a divergência (o que mostra a complexidade real)

```
Operador:   O refrigerante de 2 litros está acabando, já pode pedir mais
            pro fornecedor?

Assistente: O sistema mostra o contrário do que você viu: há 85 unidades de Refrigerante 2L, acima do mínimo de 20. Não precisa pedir agora.
```

*(saída real, de `logs/demo/`)*

O segundo diálogo é o que justifica o tema. O operador **não está mentindo** —
ele viu a gôndola vazia. O sistema também não está errado — há 85 no depósito.
A resposta útil não é "sim" nem "não": é **dizer que os dois discordam, e onde
provavelmente está a diferença**.

### A complexidade real de interação

- **O que o operador não informa de primeira:** o estoque mínimo, o giro médio,
  o pedido mínimo do fornecedor e, frequentemente, **qual produto exatamente**
  ("o açúcar" casa com dois). O sistema busca tudo isso sozinho, e **pergunta**
  quando o termo é ambíguo em vez de escolher.
- **Quando o que ele diz contradiz o sistema:** família 2 do conjunto rotulado.
  O agente relata a divergência em vez de aceitar a afirmação ou ignorá-la.
- **Como o sistema decide que já sabe o suficiente:** só depois de
  `consultar_estoque`; e, se for repor, depois de `calcular_reposicao`. Nunca
  antes — e isso é garantido por arquitetura, não por prompt (ver §3).
- **Quando o sistema para e chama um humano:** quando o custo estimado passa de
  R$ 500 ou do orçamento restante, a solicitação nasce com status
  `aguardando_aprovacao_gerente`. Quem age é o **gerente**, não o operador.

---

## 3. O workflow do agente

```
1. ENTRADA     operador digita a pergunta em texto livre        [—]

2. CONSULTA    busca o produto no SQLite                         [CÓDIGO]
               0 resultados   -> erro recuperável + lista
               2+ resultados  -> pergunta qual (volta ao passo 1)

3. JULGAMENTO  a pergunta pede ação ou só informação?            [MODELO]
               o que o operador disse bate com o dado?

4. GATING      o estoque está abaixo do mínimo?                  [CÓDIGO]
               não -> a ferramenta de escrita NÃO é oferecida
               sim -> a ferramenta de escrita é liberada

5. CÁLCULO     quantidade e custo, já com o pedido mínimo        [CÓDIGO]

6. ESCRITA     registra a solicitação                            [ESCRITA — reversível]
               custo > R$ 500 -> status aguardando_aprovacao_gerente
               custo <= R$ 500 -> status criada, debita o orçamento

7. RETORNO     responde em texto curto                           [MODELO redige,
                                                                  CÓDIGO garante os fatos]
```

Sete passos, dentro da faixa de 5 a 8.

**O passo de escrita é reversível** — nada é enviado a fornecedor nenhum nesta
parte — e por isso não exige confirmação humana antes de rodar. O que exige
aprovação humana é o **valor**: acima de R$ 500 a solicitação nasce marcada, e
cabe ao gerente agir. O passo irreversível (envio ao fornecedor) não existe
nesta entrega, de propósito.

**O passo 4 é novo em relação ao esboço**, e é o que mais mudou: a liberação da
ferramenta de escrita é uma decisão de **código** sobre o resultado real da
consulta. Ver [`arquitetura.md`](arquitetura.md) §4.

---

## 4. O sistema

**O que ele faz.** Recebe uma pergunta em texto livre sobre um produto, consulta
o estoque real num banco SQLite, julga se a pergunta pede ação ou informação e
se o que o operador afirmou bate com o registro, calcula a quantidade de
reposição respeitando o pedido mínimo do fornecedor e — só quando o produto está
de fato abaixo do mínimo — registra uma solicitação de compra reversível,
marcando-a como pendente de aprovação quando passa do teto de R$ 500.

**Nível de autonomia pretendido: agente.**

**Por que não o nível de baixo.** Um **Router** classificaria a pergunta
(consulta / reposição / dúvida) e despacharia. Ele resolve as famílias 1, 3 e 4
do conjunto de teste. Não resolve a família 2 — *"o operador está certo ou o
registro está certo?"* não é uma classe de pergunta, é um julgamento sobre o
conteúdo da frase diante de um número consultado. E não resolve a 5, em que o
sistema precisa perceber que **não sabe o suficiente** e perguntar.

A honestidade da conta está em [`arquitetura.md`](arquitetura.md) §7: sete dos
onze pontos de decisão deste sistema são código. O agente existe por causa de
três, e eles estão medidos.

### As ferramentas

| Ferramenta | O que faz | Leitura ou escrita? | Reversível? | Contra o que ela conversa |
|---|---|---|---|---|
| `consultar_estoque` | estoque, mínimo, giro, preço e `abaixo_do_minimo` | Leitura | — | **SQLite** (`dados/estoque.db`) via `src/db.py` |
| `consultar_fornecedor` | prazo de entrega e pedido mínimo | Leitura | — | **SQLite** via `src/db.py` |
| `calcular_reposicao` | quantidade e custo, já com o pedido mínimo aplicado | Cálculo | — | **SQLite** + aritmética em código |
| `criar_solicitacao_compra` | registra a solicitação e debita o orçamento | **Escrita** | **Sim** — cancelável, nada sai da loja | **SQLite** via `src/db.py` |

A última coluna é o requisito 4.2: as ferramentas atravessam a fronteira do
processo e falam com software tradicional — não com um dicionário Python.

---

## 5. A justificativa de negócio

### Por que um agente, e não software comum

A tarefa central — o passo 3 do workflow — exige **decisão em tempo de
execução**: julgar se uma frase em texto livre pede ação ou informação, e se o
que a pessoa afirma sobre a prateleira bate com o que o registro diz. Os passos
2, 4, 5 e 6 **são** código puro, e por isso estão marcados assim.

O nível abaixo não dava conta porque a divergência entre o relato e o registro
não é uma classe a rotear: é uma comparação entre duas afirmações, uma delas em
linguagem natural e imprevisível. Um formulário com campo "produto" e botão
"pedir" resolveria as famílias 1 e 4 — e é por isso que este case **não** vale
pelas famílias 1 e 4.

### O ganho esperado — **estimativa declarada, não medição**

> **Ressalva, antes do número.** A linha de base abaixo é uma **estimativa do
> grupo**, não uma medição. Não tivemos acesso a um supermercado parceiro no
> prazo da Parte 1. O enunciado pede que a linha de base seja medida, e ela não
> foi — isto é uma **lacuna declarada**, não uma medição disfarçada. É também o
> risco nº 1 do §10.

**Eixo escolhido: tempo por tarefa.** É o único que conseguiríamos cronometrar
sem acesso ao sistema de uma loja real — e a regra do enunciado é justamente
*prometa o eixo que você consegue medir*.

- **Linha de base estimada:** 3 a 6 minutos por produto — abrir a planilha do
  PDV, achar o produto, lembrar o pedido mínimo do fornecedor, decidir a
  quantidade. Baseado no relato dos três integrantes com experiência de compra
  em pequeno comércio. **Não cronometrado.**
- **Alvo:** menos de 30 segundos por pergunta.
- **A conta:** de ~4 min para ~30 s = **−87% por produto consultado**. Um
  operador que confere 10 a 15 produtos/dia pouparia **35 a 55 min/dia** — ou
  seja, de ~50 min/dia para ~7 min/dia.
- **O denominador:** 10 a 15 produtos/dia, 1 operador, 1 loja. Também estimado.

**O que vamos fazer com isso na Parte 3:** cronometrar 10 consultas reais de um
operador voluntário de um mercado de bairro, antes e depois, e conferir a
promessa contra o número. O enunciado diz que prometer 80% e entregar 30% com a
conta à vista é aceitável; prometer e não poder conferir, não. **A conferência
está agendada.**

### O ganho para o usuário, que não é o mesmo do negócio

- **Para o negócio:** menos ruptura de gôndola e menos capital parado em estoque
  excedente. E — o ganho que hoje simplesmente não existe — **rastreabilidade**:
  cada solicitação fica registrada com quantidade, custo e motivo. Hoje essa
  decisão não é registrada em lugar nenhum.
- **Para o operador:** resposta na primeira pergunta, sem precisar decorar o
  pedido mínimo de cada fornecedor, e sem abrir planilha no meio do turno.

**A tensão, dita:** o sistema é deliberadamente **conservador** — ele só
registra compra quando o dado confirma a necessidade, e por arquitetura não
consegue fazer diferente. Isso reduz compra desnecessária, mas significa que, no
caso em que o operador tem uma informação que o sistema não tem (uma promoção
que vai esvaziar a gôndola amanhã), o agente vai dizer "não precisa" e estará
errado. **Quem paga por esse erro é o operador**, que precisa usar o bom senso
além da resposta — e é por isso que o sistema relata a divergência em vez de
encerrar o assunto.

### O outro lado da conta

- **Quanto custa rodar:** **R$ 0,00 por execução** — o modelo escolhido roda
  localmente, na máquina do grupo. O custo é a máquina, não o token. Uma
  execução gasta **~4.500 tokens medidos** (~3 chamadas ao modelo) e leva
  ~21 s; se fosse na nuvem, daria ~US$ 0,001 por consulta. A conta completa
  está em [`modelos.md`](modelos.md) §3.2.
- **Quanto custa construir:** aproximadamente 3 tardes do grupo nesta Parte 1
  (desenho, código, conjunto rotulado e documentação).
- **O que se perde:** o caso do parágrafo acima — a informação que o operador
  tem e o sistema não. E a inconsistência do modelo pequeno na família de
  divergência: **9 acertos em 12** (`modelos.md` §3.3). Quem paga é o operador,
  que numa consulta em cada quatro recebe uma resposta correta nos números mas
  que não nomeia a contradição — ele lê "não precisa pedir" e não fica sabendo
  que o sistema discorda do que ele viu na gôndola.

---

## 6. O verificador

**Como sabemos que a saída está certa:** um **conjunto rotulado à mão** com
**20 casos** — 5 famílias × 4 formulações — em `dados/casos_rotulados.py`, e um
verificador que roda e diz passou ou falhou: `src/avaliar.py`.

O verificador não compara texto. Ele checa **propriedades**, que é o que o
código a seguir realmente depende:

| Família | O que se verifica |
|---|---|
| 1 — simples | consultou · calculou · **registrou** a solicitação · a quantidade respeita o pedido mínimo · a resposta diz quanto foi pedido |
| 2 — divergência | consultou · **não** registrou · a resposta cita o estoque real **e** confronta o que o operador afirmou |
| 3 — inexistente | consultou · **não** inventou nenhum número · disse que não está no cadastro · **não** culpou o sistema |
| 4 — não comprar | consultou · **não** registrou · citou o estoque real |
| 5 — ambiguidade | consultou · **não** registrou · **perguntou** qual produto em vez de escolher |
| todas | terminou respondendo · o **gating** ficou correto: a escrita foi (ou não foi) oferecida conforme o rótulo |

Três propriedades do verificador, herdadas do `05-versao-de-prompt.py` da aula 03:

1. **Teste por propriedade**, não por igualdade de texto — comparar strings
   reprova acertos.
2. **O critério é k de N**, não "passou" — `temperature=0` não garante saída
   idêntica, e o conjunto é medido com `--n 3`.
3. **O limiar é declarado antes de rodar**: 85%, escrito em `src/avaliar.py`.

E uma que é deste case: a **regra assimétrica** — uma única compra indevida
reprova a suíte inteira, mesmo com placar alto.

`src/avaliar.py` devolve código de saída ≠ 0 quando reprova, então já serve de
portão de CI na Parte 3.

---

## 7. O critério de sucesso

**Acerta ≥ 17 dos 20 casos rotulados (85%)**, medido com 3 execuções por caso —
ou seja, ≥ `51/60`.

**Medido: `57/60` = 95% — APROVADO.** Com zero violações da regra assimétrica.
O detalhamento por família e a única falha remanescente estão em
[`modelos.md`](modelos.md) §3.3.

**E**, como o custo do erro é assimétrico, uma segunda métrica que vale mais que
a primeira: **zero solicitações de compra criadas nas famílias 2, 3, 4 e 5.**

Criar uma compra desnecessária mexe no orçamento real da loja; deixar de
recomendar uma necessária custa uma pergunta a mais ao operador. Os dois erros
não têm o mesmo preço, e o critério reflete isso. Esta segunda métrica é
garantida por arquitetura (o gating), não por prompt — ver
[`arquitetura.md`](arquitetura.md) §4.

O resultado medido está em [`decisoes.md`](decisoes.md) e o relatório bruto em
`logs/avaliacao/`.

---

## 8. Dados

**Simulados**, gerados por `dados/gerar_banco.py` num SQLite. Seis produtos,
dois fornecedores, um orçamento.

**Como preservamos a dificuldade do problema.** Um dado fácil teria todo produto
perguntado abaixo do mínimo (o agente sempre compra) ou sempre acima (nunca
compra). Aqui existem as duas situações, mais três armadilhas nomeadas:

| Caso difícil | Como está no dado |
|---|---|
| **Divergência** | `REFRIGERANTE_2L`: estoque 85, mínimo 20 — e o operador afirma que está acabando |
| **Registro inexistente** | "iogurte de morango", "leite condensado", "papel higiênico" — não existem no cadastro |
| **Não deve disparar a ação** | `FEIJAO_1KG`: estoque 40, mínimo 25, giro baixo |
| **Ambiguidade** | `ACUCAR_1KG` e `ACUCAR_5KG` — "o açúcar" casa com os dois |
| *(os dois ramos do orçamento)* | `ARROZ_5KG` custa R$ 925 → pendente de aprovação; `SAL_1KG` custa R$ 115 → criada direto |

Detalhe de cada um em [`../dados/casos-dificeis.md`](../dados/casos-dificeis.md).

---

## 9. Dado sensível

**Este tema não toca dado sensível.** Nomes de produto e fornecedor são
genéricos, sem CNPJ, endereço, dado pessoal, de saúde ou financeiro de
terceiros. É uma **vantagem do tema**, não uma omissão: nada precisa ser
anonimizado, e nada impede o uso de API pública.

Há, ainda assim, informação **de negócio** — preço de compra, orçamento
disponível, volume de venda. Não é dado pessoal, mas é informação que uma loja
real não mandaria para fora sem pensar. Isso pesou na escolha do modelo: o
escolhido roda **local**, e nada sai da máquina (ver [`modelos.md`](modelos.md)).

---

## 10. Espaço para o que ainda vem

- [x] **RAG (Parte 2)** — o conhecimento de domínio a indexar é a **política de
  compras** (teto de aprovação, quem aprova, o que fazer quando o orçamento
  acaba), os **contratos de fornecedor** (pedido mínimo, prazo, frete, desconto
  por volume, devolução) e os **procedimentos de recebimento e perdas**. Hoje
  existe em Word/PDF numa pasta compartilhada: ~57 páginas, 150 a 300 chunks. O
  desenho — o que entra, o corte por cláusula, os metadados — já está feito em
  `ideia-evolucao/base-de-conhecimento-v1.md`. Hoje essas regras estão
  **escritas no prompt e no código** (o teto de R$ 500 é uma constante em
  `src/ferramentas.py`), e é exatamente isso que o RAG substitui.

- [x] **MCP (Parte 2)** — `src/db.py` vira **servidor MCP de estoque**. É a
  fronteira que esta entrega já isolou de propósito: as ferramentas nunca
  escrevem SQL, então trocar a implementação muda um arquivo. O ganho a
  demonstrar: a consulta de estoque deixa de ser código acoplado a este agente e
  vira um serviço que o agente de compras **e** o de comunicação consomem.

- [x] **LangGraph (Parte 2)** — o laço à mão de `src/agente.py` vira grafo de
  estado. A comparação é a entrega: o nosso `Estado` + `Termino` + gating por
  fase já é um grafo de estado escrito na mão, e a pergunta é o que o framework
  dá e o que tira. Candidato natural: o gating vira uma aresta condicional.

- [x] **Multiagente (Parte 3)** — dois agentes. O de **reposição** (este), que
  lida com dinheiro e precisa de gating e aprovação; e o de **comunicação
  interna**, que avisa funcionário sobre chegada de carga e tarefa de reposição
  (desenhado em `ideia-evolucao/v2.md` §8). São separados porque um mexe no
  orçamento e o outro só manda mensagem: merecem orçamentos, salvaguardas e
  níveis de autonomia diferentes. A alternativa — um agente só com sete
  ferramentas — perde essa distinção.

---

## 11. O maior risco

**O risco nº 1 é a linha de base não medida.** A venda do §5 está apoiada numa
estimativa do grupo, não em cronômetro, porque não conseguimos acesso a um
supermercado parceiro no prazo. Se o número real for 1,5 min em vez de 4, o
ganho cai de −87% para −67% e o case continua de pé; se for 40 segundos, a
justificativa de tempo **desaparece** e o argumento teria de migrar para
rastreabilidade e redução de erro de pedido — que são reais, mas que não
medimos. **Plano B:** cronometrar 10 consultas de um operador voluntário de um
mercado de bairro na Parte 3, antes de declarar qualquer número como fato.

**O risco nº 2 é a consistência na família de divergência.** O modelo escolhido
tem 4B de parâmetros e acerta **9 de 12** nessa família — as três falhas são
todas a mesma formulação (`2d`), e são consistentes, não aleatórias. É a
família que justifica haver um agente, então é a que menos pode falhar.
**Plano B:** `src/benchmark.py` já compara os três candidatos, e a condição de
troca está escrita em [`modelos.md`](modelos.md) §3.4 — com gatilho numérico
("se a família 2 cair abaixo de 8/12"), decidido antes de precisar.

**Um terceiro, menor e conhecido:** `calcular_reposicao` repõe até 2× o estoque
mínimo. É uma regra simples, determinística e declarada — não é erro do modelo —,
mas superestima a compra de produto com giro muito irregular. Está em código
(`FATOR_REPOSICAO`), visível e fácil de trocar quando houver dado real de giro.
