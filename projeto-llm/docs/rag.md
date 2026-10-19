# RAG como memória consultável — item 4

> Código: `src/conhecimento.py` (índice, corte, busca, filtro de vigência),
> `src/avaliar_rag.py` (calibração e avaliação), `src/grafo.py` (`_ferramentas`:
> a busca como ferramenta). Conjunto de perguntas: `dados/perguntas-rag.json`.
> Corpus: `dados/corpus/`. Medição: `logs/rag/20261018-211035.json`
> (embedding real, sem LLM). O log foi gerado com o código que, minutos depois,
> virou o commit `6c48749`. Por isso ele registra `commit: 28228b6` e
> `working_tree_modificado: true`: o próprio script reescreve
> `dados/rag-config.json`, arquivo versionado. Os parâmetros que ele escolheu
> (k=5, limiar 0,45) são os que estão commitados nesse arquivo.

---

## 1. As formas de recuperar, e as que o case usa

### 1.1 A classificação das dez perguntas

As dez perguntas de avaliação (`perguntas-rag.json`, bloco `avaliacao`). Outras
dez, escritas à parte, servem só para calibrar (§4) e nunca para medir.

| # | Pergunta | A resposta é um… | Forma | Trecho / registro que responde |
|---|---|---|---|---|
| 1 | Quantas unidades de arroz 5kg estão cadastradas? | registro | consulta estruturada | `produtos.estoque_atual` = 12 (`consultar_estoque`) |
| 2 | Qual o prazo cadastrado do Fornecedor A? | registro | consulta estruturada | `fornecedores.prazo_dias` = 2 (`consultar_fornecedor`) |
| 3 | Quanto saldo resta para comprar arroz? | registro | consulta estruturada | `orcamento.disponivel` = 1200 (`calcular_reposicao`) |
| 4 | Qual a quantidade recomendada para repor sal? | registro **calculado** | consulta estruturada | `calcular_reposicao` → 50 |
| 5 | Qual valor exige aprovação do gerente? | assunto | busca vetorial | `POL-V2 §1`: *"Acima de R$ 500, o gerente precisa aprovar…"* |
| 6 | Excepcionalmente, como o gerente pode ajustar uma compra que passa do saldo? **(exceção)** | assunto | busca vetorial | `POL-V2 §2`: *"Exceção: ele pode reduzir a quantidade, respeitando o pedido mínimo…"* |
| 7 | Se só parte da carga estiver avariada, posso receber o restante? **(exceção)** | assunto | busca vetorial | `FORN-A-V1 §2`: *"Exceção: as unidades boas podem ser recebidas normalmente…"* |
| 8 | Banco mostra estoque mas o operador não acha produto na gôndola. Como agir? | assunto | busca vetorial | `CONF-V1 §1`: *"Confira a gôndola e o depósito antes de comprar."* |
| 9 | A ausência de resposta do gerente autoriza o pedido após um dia? | assunto | busca vetorial | `POL-V2 §4`: *"O silêncio nunca autoriza a compra."* |
| 10 | Qual a política de garantia de televisores? **(fora do corpus)** | — | busca vetorial → **recusa** | nenhum trecho; a resposta correta é a lista vazia |

Composição exigida: **2 exceções** (6, 7) e **1 sem resposta no corpus** (10).

**A classificação não concentrou tudo em "assunto":** 4 de 10 são registros.
As perguntas de número (*quanto temos*, *qual o prazo*) são as que o operador
mais faz (ver `case.md` §2), e a resposta delas **não está em documento
nenhum**: está no cadastro, e muda a cada venda.

### 1.2 As formas que o sistema implementa

| Forma usada | Com o quê | O que ela responde no case |
|---|---|---|
| **consulta estruturada** | SQLite (`runtime/operacao.sqlite`), ferramentas `consultar_estoque`, `consultar_fornecedor`, `calcular_reposicao` (`src/servico.py`), também expostas por MCP | as perguntas 1–4: estoque, prazo, saldo, quantidade, e todo número que aparece numa resposta |
| **busca vetorial** | embedding local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões, via `fastembed`, CPU), vetores em SQLite, similaridade de cosseno em `numpy` | as perguntas 5–10: as regras da política e dos contratos |

**"O seu RAG é vetorial ou é banco de dados?"** Os dois: o número vem do banco,
a regra vem do índice.

**As formas que não usamos, e por quê:**
- **busca textual:** nenhuma pergunta do conjunto é *"onde aparece o termo X"*.
  O corpus tem 9 seções, e quem procura um termo abre o arquivo.
- **grafo:** a única relação do corpus é *"POL-V2 revoga POL-V1"*, e ela está
  num **metadado** (`status: revogado`) usado como filtro (§3). Um banco de
  grafo para uma aresta não se paga.
- **agregação** (*"quais produtos estão abaixo do mínimo?"*): seria um
  `SELECT ... WHERE`, e não está no escopo das ferramentas desta entrega. O
  operador pergunta por um produto de cada vez.

---

## 2. O corpus

| Documento | Arquivo | Origem | Quem mantém | Muda com que frequência |
|---|---|---|---|---|
| `POL-V2` política de compras (vigente) | `politica-v2.md` | escrita pelo grupo, a partir de `ideia-evolucao/v2.md` §5 e da Parte 1 | gerente (simulado) | rara: revisão anual ou quando a loja muda a alçada |
| `POL-V1` política antiga (**revogada**) | `politica-v1-revogada.md` | idem, de propósito obsoleta | — | nunca mais |
| `FORN-A-V1` contrato de mercearia | `fornecedor-a.md` | escrito pelo grupo; pedido mínimo e prazo iguais ao cadastro | comprador (simulado) | na renovação do contrato |
| `FORN-B-V1` contrato de bebidas | `fornecedor-b.md` | idem | comprador (simulado) | na renovação do contrato |
| `CONF-V1` procedimento de divergência | `conferencia.md` | escrito pelo grupo a partir da família 2 da Parte 1 | operador (simulado) | rara |

Cada arquivo começa com um cabeçalho JSON (`id`, `status`, `vigencia`, `dono`,
`versao` e, nos contratos, `fornecedor`) que vira metadado de cada trecho.

**O índice é reconstruído quando o corpus muda.** `indexar()` calcula uma
assinatura (sha256 do conteúdo dos arquivos + modelo de embedding + estratégia
de corte) e só reindexa quando ela muda. Como o corpus muda raramente, o custo
é zero na maioria das execuções, e a reconstrução é automática quando alguém
edita um documento. O corpus real descrito no `case.md` §10 teria cerca de 57
páginas e 150–300 trechos; o simulado tem 9.

---

## 3. O documento revogado

**O que pusemos:** `POL-V1`, que diz *"Compras até R$ 1000 dispensam aprovação
do gerente"*. Ela responde, **errado**, à pergunta 5. Se fosse usada, uma
compra de R$ 925 (o arroz) seria criada sem aprovação.

**O que acontece, medido** (`logs/rag/20261018-211035.json`, campo
`revogado_sem_filtro`):

| Pergunta | Com o filtro de vigência | **Sem** o filtro, mesmo limiar (0,45) | Sem o filtro, limiar 0 |
|---|---|---|---|
| Qual valor exige aprovação do gerente? | `POL-V2:1` 0,457 | `POL-V2:1` 0,457 | `POL-V2:1` 0,457 · **`POL-V1:1` 0,446** · `POL-V2:2` 0,416 … |
| Compra de 800 reais precisa de aprovação? | `POL-V2:1` 0,599 | `POL-V2:1` 0,599 | `POL-V2:1` 0,599 · **`POL-V1:1` 0,432** · … |
| Até quanto posso comprar sem aprovação? | `POL-V2:1` 0,530 … | idem | idem (POL-V1 fora do top-5) |

**O achado:** sem curadoria, a política revogada é o **2º trecho mais próximo**
da pergunta sobre o teto, a **0,011** do limiar. Ela ficaria fora do contexto
por **sorte do limiar**, não por desenho. Um ajuste de 0,45 para 0,44 a
colocaria no contexto do modelo, ao lado da vigente, com o mesmo tom
autoritativo. O sistema não tem como saber, pelo texto, qual das duas vale.

**A solução é curadoria, não técnica de recuperação.** `buscar_documentos`
descarta trechos com `status != "vigente"` ou `vigencia` futura **antes** de
pontuar. O parâmetro `incluir_revogados` existe só para esta medição: ele não
está no schema da ferramenta, então o modelo não consegue pedir o documento
revogado (teste `test_revogado_so_aparece_sem_curadoria_e_modelo_nao_pede`).
O documento continua **indexado**: revogar é mudar o metadado, não apagar o
arquivo, e o histórico fica auditável.

---

## 4. O corte e o `k`

### 4.1 A estratégia de corte: **por estrutura**

O corpus é composto de regulamentos curtos com seções numeradas (`## 1 Limite e
aprovação`). Cada seção é **uma regra com a sua exceção**. O corte é por seção
(`## `), com o cabeçalho `ID > título` prefixado a cada trecho. Uma seção que
passe de 120 tokens do tokenizador do embedding seria subdividida com
sobreposição de 10 palavras, mas nenhuma do corpus atual passa: 9 seções viram
9 trechos.

**O que a medição disse, e por que mantivemos a estrutura mesmo assim.** Na
calibração (top-3, sem limiar), o corte por **caracteres** (200 com
sobreposição de 40) acertou 9/10 e o por estrutura 8/10 (`cortes` no log). O
erro da estrutura foi *"Como determinar a quantidade para repor?"*: a seção
certa (`POL-V2 §3`) veio em 4º. Mantivemos a estrutura porque:

- o corte por caracteres parte a seção no meio, e separa *"Exceção:"* da regra
  que ela excepciona. Em `POL-V2 §2`, o trecho com *"Mesmo o gerente não pode
  autorizar uma compra que exceda o saldo"* e o trecho com *"Exceção: ele pode
  reduzir a quantidade"* podem ser recuperados separados, e o modelo receberia
  meia regra;
- a diferença (1 pergunta em 10) desaparece com `k=5` (10/10 na calibração);
- a citação fica conferível: o id `POL-V2:2:0` aponta uma seção inteira, que um
  humano lê em 10 segundos.

### 4.2 O `k` e o limiar: **k = 5, limiar = 0,45**

Escolhidos por `src/avaliar_rag.py` sobre as **dez perguntas de calibração**
(nunca as de avaliação), varrendo k ∈ {1, 3, 5} × limiar ∈ {0,20 … 0,60}, com
esta prioridade: (1) zero falso positivo na pergunta sem resposta (sorvete);
(2) mais acertos de fonte; (3) menor k; (4) maior limiar.

| k | limiar 0,20 | 0,25–0,45 | 0,50 | 0,55–0,60 |
|---|---|---|---|---|
| 1 | 8/10, 1 falso positivo | 9/10 | 8/10 | 7/10 |
| 3 | 8/10, 1 falso positivo | 9/10 | 8/10 | 7/10 |
| 5 | 9/10, 1 falso positivo | **10/10** | 8/10 | 7/10 |

- **Por que k = 5 com só 9 trechos.** Em perguntas de procedimento, o trecho
  certo pode vir em 4º (*"como determinar a quantidade"*). Com um corpus de 9
  trechos, k = 5 parece "quase tudo", mas **o limiar é que corta**: na prática
  a busca devolve de 0 a 3 trechos (avaliação: 1, 3, 2, 2, 3, 0). O `k` alto
  aqui não enche a janela, porque o limiar não deixa.
- **Por que 0,45.** É o maior limiar com 10/10. Acima de 0,50 a pergunta 5 se
  perde (0,457). Abaixo de 0,25 a pergunta do sorvete passa a recuperar lixo
  (0,22).
- **O ponto frágil, declarado.** A margem entre o acerto mais fraco (pergunta
  5, 0,457) e o revogado (0,446) é de 0,011. O limiar não separa vigente de
  revogado, e não precisa: quem separa é o filtro do §3.

### 4.3 O resultado na avaliação

**10/10** (`acertos` no log): as 4 estruturadas devolvem o valor esperado; as
5 vetoriais com resposta trazem o trecho certo em 1º; a pergunta 10
(televisores) devolve **lista vazia**, e é essa lista vazia que leva o agente à
recusa (§5).

---

## 5. Onde a recuperação entra no laço: **ferramenta do agente**

`buscar_documentos` é uma das ferramentas de leitura oferecidas ao modelo no
nó `agente`, ao lado de `consultar_estoque`, `consultar_fornecedor` e
`calcular_reposicao` (`src/transporte.py`, `ferramentas_leitura`). O modelo
decide se busca.

**Por que ferramenta, e não etapa fixa.** A maioria dos pedidos do operador é
de **número** (*"quanto temos de arroz?"*). Para esses, a evidência já chega
pronta do cadastro, consultado pelo código em `coletar`, e uma busca no corpus
seria inútil em toda execução. Uma etapa fixa pagaria um embedding e
encheria o contexto com regras que a resposta não usa. Já os pedidos de
**política** (*"posso passar do saldo?"*) não têm evidência nenhuma sem a
busca. A decisão "preciso de regra para responder isto?" é de conteúdo, e é do
modelo.

**O que impede o modelo de pular a busca quando precisa dela:**
- o prompt (`reposicao.md`): *"nunca responda políticas pela memória do modelo"*;
- o **código**: uma resposta `suficiente=true` a um pedido de intenção
  `politica` sem nenhuma fonte do tipo `documento` recuperada **nesta
  execução** é rejeitada em `_agente`. O modelo ganha uma chance de corrigir e,
  se insistir, a execução vira recusa;
- citar uma fonte que não foi recuperada também é rejeitado.

**Chamadas de recuperação por execução, medidas** (`n_recuperacoes` nos logs da
demonstração real, tabela completa em [`io.md`](io.md) §4): **1 busca em 9
execuções**, exatamente na única pergunta de política (*garantia de
televisores*), que voltou vazia e virou recusa. As 8 execuções sem busca são
consultas de estoque, pedidos de reposição, entradas incompletas ou ambíguas e
uma fora do escopo: nenhuma precisava do corpus, e todas acertaram. Com etapa
fixa, seriam 9 buscas, 8 delas inúteis.

**O custo da escolha, também medido.** No pedido *"Preciso repor arroz 5kg, mas
e se o orçamento não der para tudo?"* (`logs/autonomia/`), a resposta está no
corpus (`POL-V2 §2`, a exceção da redução), e o modelo **não buscou**. Uma
etapa fixa teria trazido o trecho. A ferramenta economiza 8 buscas em 9 e, neste
caso, perdeu 1. O dano é contido porque a exceção é exercida no ponto de
aprovação humana (o gerente edita a quantidade) e o serviço reaplica a regra do
saldo de qualquer forma.
