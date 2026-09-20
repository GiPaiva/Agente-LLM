# Registro de decisões

> O enunciado pede que **toda a pesquisa e documentação do case viva em
> `docs/`**, e dá a razão: *"a pesquisa passa a ter histórico — dá para ver
> quando o grupo mudou de ideia sobre o próprio case, e por quê."*
>
> Este arquivo é esse histórico. Cada decisão traz **o que mudou, por que, e —
> quando aplicável — o número que sustenta a mudança.**

---

## De onde esta versão veio

Esta entrega é a versão refinada do esboço em
`agente-estoque-parte1-esboco/agente-estoque-parte1/build/`, que continua no
repositório, intocado, para que o `git diff` desta evolução exista.

O esboço rodou contra `google/gemma-4-e4b` em 19/09, e os logs daquela execução
(`agente-estoque-parte1-esboco/.../logs/`) são o insumo mais valioso que
tínhamos: eles mostraram que **o agente reprovava no próprio critério de
sucesso do grupo** — 1 acerto em 4 casos, contra a meta de 4/4.

O que segue são as decisões tomadas a partir daquela evidência.

---

## Decisão 1 — a busca de produto passou a casar por token

**O problema.** `db.buscar_produto` fazia `LIKE` com o **termo inteiro** entre
curingas. O operador digita "arroz de 5kg"; o cadastro diz "Arroz 5kg"; a
preposição no meio matava o casamento.

**A evidência.** Três dos quatro casos demonstrados começavam com um "produto
não encontrado" **falso**:

| Log do esboço | Termo | O que aconteceu |
|---|---|---|
| `20260919-150032` | `"arroz de 5kg"` | falhou no passo 0; o modelo se recuperou tentando `"Arroz 5kg"` |
| `20260919-150056` | `"refrigerante de 2 litros"` | falhou no passo 0 |
| `20260919-150117` | `"feijão de 1kg"` | falhou, e **o modelo desistiu**: respondeu ao operador *"houve um erro ao buscar os detalhes do estoque"* — nunca respondeu o estoque |

**Por que isso era pior do que parece.** O bug **contaminava o verificador**. O
caso difícil nº 3 é "registro inexistente"; com a busca quebrada, ele ficava
indistinguível de "o nome foi escrito de outro jeito". O conjunto de teste
estava medindo o bug, não o agente.

**A decisão.** Casamento por token: normaliza acento e caixa, descarta palavras
vazias (`de`, `do`, `litros`…) e exige que **todos** os tokens restantes
apareçam no nome ou no id. Devolve **todos** os candidatos, não `LIMIT 1`.

**Medido depois.** `"arroz de 5kg"`, `"feijão de 1kg"` e
`"refrigerante de 2 litros"` casam de primeira; `"iogurte de morango"` continua
não casando — que é o comportamento correto e o que preserva o caso nº 3.

**O efeito colateral bom.** Devolver a lista inteira criou de graça um caso
difícil novo: dois açúcares (1kg e 5kg) casam com "o açúcar", e o agente
precisa **perguntar qual**. Virou a família 5 do conjunto rotulado, e é o caso
que mais exercita a "complexidade real de interação" do item 2.2.

---

## Decisão 2 — `calcular_reposicao` passou a buscar os próprios dados

**O problema.** A ferramenta recebia quatro argumentos — estoque, mínimo, giro
e pedido mínimo — e o último era **opcional**.

**A evidência.** No log `20260919-150032`, o modelo chamou a ferramenta **sem**
o pedido mínimo, recebeu `48`, depois consultou o fornecedor, viu que o pedido
mínimo era `50`, e respondeu **"50"** ao operador. Ou seja: refez a conta de
cabeça, por cima do resultado da ferramenta.

Uma ferramenta de cálculo cujo número o modelo corrige no braço não está
impedindo nada — e aritmética no modelo é exatamente o que ela existe para
evitar.

**A decisão.** A assinatura virou `calcular_reposicao(produto_id)`. O código lê
produto e fornecedor do banco e devolve quantidade, custo, pedido mínimo
aplicado e prazo, tudo pronto. Não há argumento para o modelo esquecer nem
número para transcrever errado.

**O custo da decisão, declarado:** a ferramenta ficou menos "pura" (faz I/O
além de calcular). Aceitamos: a alternativa mede pior.

---

## Decisão 3 — a ferramenta de escrita passou a ser liberada por código

**O problema.** "Nunca crie compra quando o estoque está acima do mínimo" era
uma frase no prompt. Frase no prompt é uma esperança, e o critério de sucesso do
case tem um lado **assimétrico**: criar uma compra indevida mexe no orçamento
real da loja.

**A decisão.** Gating por fase, portado de `notas-aula/aula05-agentes/agente.py:298`
(`FASES`). O agente começa **sem** `criar_solicitacao_compra`; quem a habilita é
o código, e só depois que um `consultar_estoque` desta execução devolveu
`abaixo_do_minimo: true`.

A razão é da própria aula 05, nota 02 §6: *"restrição por arquitetura vence
restrição por prompt — instrução ele pode ignorar, ferramenta não declarada ele
não tem como chamar."*

**O que isso muda na avaliação.** Cada log grava o bloco `gating`, e o
verificador confere `escrita_foi_oferecida` contra o rótulo. A diferença entre
*"o modelo não chamou"* e *"o modelo não podia chamar"* é a diferença entre
sorte e desenho — e agora ela é verificável.

**Efeito colateral no case:** isto virou um passo novo no workflow do §3 do
`case.md`, marcado `[CÓDIGO]`. O sistema ficou **menos** autônomo do que o
esboço, de propósito. A regra da disciplina é *use a menor autonomia que
resolve*.

---

## Decisão 4 — o verificador virou código, e o conjunto foi de 4 para 20 casos

**O problema.** O esboço tinha um "verificador" que era uma tabela em Markdown.
O item 2.6 do enunciado é explícito sobre isso ser o campo que mais reprova, e
"verificador construído conta".

**A decisão.** `src/avaliar.py` + `dados/casos_rotulados.py`. O conjunto foi de
4 casos para **20** — 5 famílias × 4 formulações — para que o critério de
sucesso tenha denominador de verdade.

Três propriedades vieram de `notas-aula/aula03-prompt/05-versao-de-prompt.py`:

1. **teste por propriedade**, não por igualdade de texto;
2. **critério k de N** (o conjunto é medido com `--n 3`);
3. **limiar declarado antes de rodar** (85%, constante no topo do arquivo).

E uma que é deste case: a **regra assimétrica** — uma compra indevida reprova a
suíte inteira, mesmo com placar alto.

**Quatro formulações por família, e não uma.** Uma só mediria se o agente
acerta *uma frase*. As quatro variam o jeito de perguntar (direta, coloquial,
abreviada, com ruído), que é como o operador escreve no meio do turno.

### O verificador também teve bugs, e eles reprovavam acertos

Registrado porque é o tipo de coisa que se esquece:

| Bug | O que ele fazia | Correção |
|---|---|---|
| `chamou` exigia `not erro` | nas famílias 3 e 5 o **erro é o caminho correto** — a asserção reprovava o acerto | `chamou` passou a significar *tentou chamar* |
| números extraídos do texto inteiro | listar "Arroz 5kg, Feijão 1kg, Refrigerante 2L" contava como ter citado 5, 1 e 2, e reprovava a resposta certa para produto inexistente | os nomes do catálogo são removidos antes de extrair números |
| `"acima do mínimo"` contava como relato de divergência | aprovava *"o estoque está em 85, acima do mínimo"* — que é **exatamente** a resposta que a família 2 existe para reprovar | a marca foi removida; só contam marcas de **contraste** |

A terceira é a mais importante: **um verificador frouxo não verifica.** Ele
estava aprovando o comportamento que o case define como errado.

---

## Decisão 5 — o prompt, de v1 a v3, com medição

O enunciado cobra prompt em arquivo, versionado, com `prompt × modelo ×
parâmetros` carimbado. As três versões estão em `prompts/`, e o carimbo vai em
todo registro de `logs/`.

| Versão | O que mudou | Placar |
|---|---|---|
| **v1** | a do esboço; carimbada para `mistral-small-latest`, mas rodada contra gemma | 1/4 no conjunto de 4 casos do esboço |
| **v2** | reescrita com as três frases da v1 mais busca com termo curto e desambiguação | 5/20 (N=1) — **mas ver a ressalva abaixo** |
| **v3** | duas permissões viraram **obrigações com contrato de saída** | **57/60** (N=3) |

> **Ressalva sobre o 5/20 da v2, e ela importa.** Aquela medição foi feita
> **antes** de corrigirmos os bugs do próprio verificador (tabela da decisão 4).
> Boa parte daquelas falhas era do verificador, não da v2: as famílias 3 e 5
> estavam sendo reprovadas por asserções erradas. **O 5/20 e o 57/60 não são
> comparáveis**, e apresentá-los lado a lado como "ganho de 70 pontos" seria
> desonesto.
>
> O que **é** comparável, porque não passa pelos bugs corrigidos, é o
> comportamento por família nas duas famílias que a v3 atacou:
>
> | Família | v2 | v3 | A falha da v2 era real? |
> |---|---|---|---|
> | 1 — simples | **0/4** | **12/12** | sim: o agente nunca chamava `criar_solicitacao_compra` |
> | 2 — divergência | **1/4** | **9/12** | sim: respondia o fato sem confrontar o operador |

### O que a v2 errava, e por quê

As duas falhas restantes da v2 tinham a mesma forma: **a instrução era uma
permissão, e o modelo a leu como restrição.**

1. *"Só registre uma solicitação quando o estoque estiver abaixo do mínimo."*
   O modelo entendeu "não registre quando estiver acima" — e nunca registrou
   nada, nem quando devia. Família 1: **0/4**.

2. *"Diga as duas coisas: o que você observou e o que o dado mostra."*
   Dizia **o quê**, não **como**. O modelo respondia o fato ("não precisa
   pedir, há 85 unidades") sem confrontar o que o operador tinha afirmado.
   Família 2: **1/4**.

### O que a v3 fez

1. **Obrigação afirmativa:** *"se `calcular_reposicao` devolver `precisa_repor:
   true`, você DEVE chamar `criar_solicitacao_compra` antes de responder"*, com
   a razão junto (*"recomendar e não registrar deixa o operador achando que o
   pedido foi feito quando não foi"*).
   → família 1 foi de **0/4 para 4/4**.

2. **Contrato de saída com forma literal e exemplo negativo** para a
   divergência, incluindo a observação de que a afirmação pode vir embrulhada
   numa pergunta (*"está acabando, já pode pedir?"* tem uma afirmação **e** uma
   pergunta).
   → família 2 subiu, com a ressalva da §"O resultado".

**A lição, que é a da aula 03:** não existe análise estática de prompt. As duas
frases da v2 pareciam corretas na leitura; só a suíte mostrou que uma delas
nunca disparava e a outra disparava pela metade.

---

## Decisão 6 — repetir, mas só o que vale repetir

**O problema, e ele apareceu sozinho.** No meio de uma medição de 28 minutos, o
túnel Cloudflare que serve o modelo local devolveu `530` por alguns segundos.
O laço classificou certo — `erro_fatal`, com a causa no log —, mas 13 dos 20
casos foram perdidos por um soluço que não tem nada a ver com o agente.

**A tensão.** A aula 05 é explícita contra retry: *"retry silencioso esconde
erro de configuração, que é a causa mais comum num laboratório."* E está certa.

**A decisão.** Repetir **apenas falha de transporte**, e de forma **visível**.
A própria aula 05 dá a régua ao dizer que "repetir serve para falha de
TRANSPORTE". Então:

| Tipo de falha | O que fazemos | Por quê |
|---|---|---|
| 5xx, conexão caída | até 2 repetições, **imprimindo cada uma** | nada mudou do lado do conteúdo; repetir pode funcionar |
| 401, 403, 404, 422 | aborta na primeira, com a pista do que corrigir | é configuração — repetir esconderia a causa, que é o alerta da aula |
| 429 | aborta na primeira | é cota; repetir piora |
| argumento inválido do modelo | não é assunto de `chamar()` | quem tenta de novo, com informação nova, é o **modelo** |

Retry que ninguém vê é o que transforma "está lento" num mistério — por isso
ele imprime. As quatro linhas estão testadas em `chamar()`.

---

## Decisão 7 — `max_tokens` entrou no conjunto de parâmetros

**O problema.** O `qwen/qwen3.8-27b` marcou **2/10** no benchmark. Parecia
incapacidade do modelo. Não era: a conta gratuita da Groq recusava a requisição
**antes de processá-la**, com
`429 ... output tokens per minute (OTPM): Limit 1000, Requested 1015`.

O provedor estima o tamanho da saída a partir do `max_tokens` declarado — e nós
não declarávamos nenhum, então ele assumia o teto do modelo.

**A decisão.** `max_tokens=800` em `PARAMETROS`. A resposta mais longa do
sistema tem ~80 tokens, então o teto não corta nada. O `qwen` foi de **2/10
para 10/10**.

**O efeito colateral que exigiu código:** com um teto, passa a ser possível uma
resposta ser **cortada** — e texto cortado parece resposta e não é. Daí o
término `TRUNCADO`, separado de `RESPONDEU`, checando `finish_reason` (o mesmo
que o `05-versao-de-prompt.py` da aula 03 faz).

**E o efeito na medição:** mudar um parâmetro muda a combinação versionada
`prompt × modelo × parâmetros`. O 57/60 foi **remedido** depois desta mudança,
não herdado da medição anterior.

> A lição que ficou: *o primeiro número de um benchmark pode estar medindo a
> sua conta, não o modelo.* Se tivéssemos aceitado o 2/10, este repositório
> afirmaria que um modelo de 27B não dá conta de uma tarefa que ele resolve
> perfeitamente.

---

## Decisão 8 — os três candidatos são os que realmente rodam

**O problema.** O `modelos.md` do esboço comparava `mistral-small-latest`,
`llama3.1:8b` e `mistral-large-latest`, e a §3.3 — "os cinco casos rodados de
verdade", item avaliado — estava **em branco**. Mas o sistema rodava
`google/gemma-4-e4b` por um túnel Cloudflare.

Uma análise de modelos que não descreve o modelo que o sistema usa não
justifica escolha nenhuma.

**A decisão.** Os três candidatos passaram a ser os três que o grupo tem
funcionando, e os cinco casos foram **rodados de verdade** nos três, pelo
`src/benchmark.py`, com o mesmo prompt:

| Candidato | Modelo | Representa |
|---|---|---|
| local-pequeno | `google/gemma-4-e4b` | local, zero por token, dado não sai da máquina |
| hospedado-medio | `qwen/qwen3.8-27b` (Groq) | hospedado, porte médio |
| hospedado-grande | `openai/gpt-oss-120b` (Groq) | o que se ganha pagando mais |

Resultados em [`modelos.md`](modelos.md) §3.3 e em `logs/benchmark/`.

**A conta de custo também estava errada.** O esboço estimava 770 tokens de
entrada por execução. A medição real da primeira rodada deu **9.623** — ordem de
grandeza errada por ~12×. A conta foi refeita com tokens medidos.

> O que produziu a diferença não foi só a estimativa: foi o próprio bug da
> decisão 1. Com a busca consertada, uma execução típica caiu para ~2.400
> tokens. **Consertar a busca barateou o sistema em ~4×** — um ganho que não
> estava planejado e que só apareceu porque a conta passou a ser medida.

---

## Decisão 9 — o que **não** mudamos, e por quê

Registrado porque decisão de não mexer também é decisão.

| Mantido do esboço | Por quê |
|---|---|
| `Estado` como objeto, `mensagens[]` como transporte | é a ideia central da aula 05 e o esboço acertou nela |
| `ErroRecuperavel` vs `ErroFatal`, com o erro voltando como observação | idem — e é o que faz o caso 3 funcionar |
| idempotência por chave em `criar_solicitacao_compra` | idem |
| `src/db.py` como camada isolada | é a fronteira que vira MCP na Parte 2 |
| quatro ferramentas | o teto do item 4.1; a tentação de acrescentar uma quinta é escopo da Parte 2 |
| **a linha de base do ganho como estimativa declarada** | não houve acesso a mercado parceiro. Preferimos declarar a lacuna a inventar um número. Ver `case.md` §5 e §11 |
| `temperature=0` | escolher ferramenta é decisão; variar é defeito |
| sem retry automático em `chamar()` | decisão da aula 05: retry silencioso esconde erro de configuração |

---

## O resultado

**Antes (esboço, 4 casos rotulados à mão):** **1/4**, contra a meta declarada
de 4/4. As três falhas estão nas decisões 1, 2 e 5 acima.

**Depois (20 casos × 3 execuções = 60 medições):**

```
PLACAR: 57/60 = 95%   (limiar declarado antes de rodar: 85%)

  1_simples        12/12      <- era 0/4 na v2 do prompt
  2_divergencia     9/12
  3_inexistente    12/12
  4_nao_comprar    12/12
  5_ambiguidade    12/12

regra assimétrica (nenhuma compra indevida): OK
VEREDITO: APROVADO
```

Relatório bruto em `logs/avaliacao/relatorio-*.json`, reproduzível com
`python src/avaliar.py --n 3`.

### A falha que sobrou, e por que não a apagamos

O caso `2d` — *"O refrigerante está abaixo do mínimo, né? Pode pedir."* — falha
nas três execuções, sempre com a mesma resposta: *"Não, o refrigerante está
acima do mínimo. Temos 85 unidades e o mínimo é 20."*

Essa resposta **contradiz** o operador — começa com "Não" — mas não nomeia a
divergência, que é o que o contrato de saída exige. Bastaria acrescentar `"nao,"`
à lista de marcas de contraste do verificador para o placar ir a **60/60**.

**Não fizemos.** Mexer no critério depois de ver o resultado é exatamente o que
a aula 03 chama de teste que não testa nada, e seria a terceira vez neste
documento em que um verificador frouxo aprova o comportamento errado. O caso
fica como falha declarada, e o número fica 95%.
