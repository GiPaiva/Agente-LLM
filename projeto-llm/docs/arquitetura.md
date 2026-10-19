# A arquitetura do agente — itens 3, 6.1 e 7

> O que este documento responde: o desenho do sistema como ele roda hoje (o
> grafo LangGraph de `src/grafo.py`), as seis perguntas, a defesa do nível de
> autonomia, a fronteira de confiança, e a tabela de campos do estado com os
> reducers. Os padrões do grafo, quem decide cada aresta e o que o framework
> não deu estão em [`grafo.md`](grafo.md). O ponto de parada humana está
> detalhado em [`humano.md`](humano.md). A arquitetura da Parte 1 (o laço
> ReAct à mão) está na §7, como histórico.

---

## 1. O desenho

Legenda: **[M]** o nó chama o modelo · **[C]** só código · **L** ferramenta
de leitura · **E** escrita · `══>` aresta condicional · `──>` incondicional ·
**⏸** o sistema para e espera uma pessoa · **■** término.

```
 ENTRADA: texto livre do operador                    + metadados não digitados:
 "O sal de 1kg tá no fim, registra a reposição."       usuario (--usuario), thread_id = usuario:uuid
        │                                              caso_id = uuid novo por pedido
        v
 ┌─────────────────┐  [M] triagem: extrair_intencao → Interpretacao
 │  interpretar    │      intencao ∈ Literal{consulta, reposicao, politica, fora_escopo}
 └────────┬────────┘      produto · relato_falta · pergunta        prompt: triagem.md
          ║ [C] entrada longa / contrato inválido 2× ───────────────────────────────> ■ recusado / falha
          v
 ┌─────────────────┐  [C] ROUTER sobre o Literal + leituras fixas      ┌──────────────────────────┐
 │  coletar        │  fora_escopo ─────────────────────────> ■ recusado│ SQLite operacao.sqlite   │
 │                 │  produto vazio ───────────────────────> ■ esclarecimento (pergunta)
 │                 │  consultar_estoque (L) ───────────────────────────>│ produtos·fornecedores    │
 │                 │     não encontrado ───────────────────> ■ recusado + lista do cadastro
 │                 │     ambíguo ──────────────────────────> ■ esclarecimento + candidatos
 │                 │  reposicao e abaixo do mínimo:                     │ orcamento·casos          │
 │                 │     calcular_reposicao (L) ────────────────────────>│ solicitacoes             │
 │                 │  lembrar(usuario) ── memória episódica ──┐         └──────────────────────────┘
 └────────┬────────┘  fato(usuario, alias) ── semântica (KV) ─┤ conhecimento.sqlite
          ║ [C]                                               │ (episodios · fatos · trechos)
          v                                                   │
 ┌─────────────────┐  [M] DECISÃO QUE SÓ O MODELO TOMA (§3):   │
 │  agente         │◄═╗  ferramentas L: buscar_documentos ─────┴─> índice vetorial do corpus
 │  reposicao.md + │  ║                 consultar_fornecedor     (só documentos vigentes)
 │  procedimento.md│  ║                 consultar_estoque / calcular_reposicao
 └──┬──────┬───────┘  ║  ou emitir_resposta → RespostaModelo {resultado, fontes, suficiente}
    ║      ║  ║        ║
    ║      ║  ╚═ resposta inválida (1ª vez) ══╝ (agente → agente, correção)
    ║      v
    ║  ┌──────────────┐ [C] detector de laço (2× injeta observação, 4× ■ laco_detectado)
    ║  │ ferramentas  │ [C] tetos: modelo 8 · ferramentas 8 · tokens 60k · 600 s ativos ──> ■ orcamento_esgotado
    ║  └──────┬───────┘ ══> volta ao agente
    v
 ┌─────────────────┐  [C] PORTÃO: suficiente=false ───────────> ■ recusado (o que falta)
 │  validar        │      pedido mínimo > saldo ─────────────> ■ recusado
 │                 │      sem proposta (consulta) ───────────> ■ respondido
 │                 │        relato_falta e estoque ≥ mínimo → texto de DIVERGÊNCIA (código)
 └────────┬────────┘
          ║ com proposta
          v
 ┌─────────────────┐  [M] AVALIADOR independente (revisao.md), recebe só proposta + evidências,
 │  revisar        │      consulta ≥1 ferramenta L, emite Parecer {aprovado, motivos, fontes}
 └────────┬────────┘      erro/fonte inválida 2× → reprova (falha fechada)
          ║
          v
 ┌─────────────────┐  [C] parecer reprovou ─────────────────> ■ recusado
 │  preparar       │  [C] servico.preparar: grava o CASO + capacidade privada (não é compra)
 └──┬──────────┬───┘
    ║          ║ [C] custo > min(R$ 500, saldo)
    ║          v
    ║   ┌─────────────────┐  ⏸ interrupt(payload: ação, argumentos, consequência, prazo)
    ║   │  aprovar        │     perfil GERENTE responde: aprovar · rejeitar · aprovar editando
    ║   └────────┬────────┘     checkpoint em runtime/checkpoints.sqlite (SqliteSaver)
    ║            │              silêncio > 24 h ──> expirada (= rejeitada)
    ║            v
    ║   ┌─────────────────┐
    ╚══>│  escrever       │  E  registrar_compra (via MCP) com a capacidade privada:
        │                 │     o serviço revalida tudo na MESMA transação; idempotente por caso_id
        └──┬──────────────┘     edição inválida ══> volta a aprovar (⏸ de novo, com o erro)
           v
 ┌─────────────────┐  [C] classifica o término · grava episódio (memória) · log
 │  finalizar      │
 └────────┬────────┘
          v
 SAÍDA: Saida {resultado, fontes[], suficiente, status, termino, perguntas, aprovacao, solicitacao}
 ■ status: respondido · criada · aguardando_aprovacao · rejeitada · expirada · recusado · esclarecimento · falha
```

**O que o modelo nunca vê:** a ferramenta de escrita. `registrar_compra` não
está na lista de ferramentas do agente nem do revisor (`ferramentas_leitura`
em `src/transporte.py`), e `_ler` recusa qualquer escrita
(`test_llm_nao_consegue_chamar_escrita`). Quem escreve é o nó `escrever`, com
uma capacidade que só existe no serviço.

### 1.1 A conferência contra o código

Comando, na raiz de `projeto-llm/`:

```
.venv/bin/python conferir_grafo.py
```

Saída (commit `6c48749`), colada sem edição:

```
NÓS
__end__
__start__
agente
aprovar
coletar
escrever
ferramentas
finalizar
interpretar
preparar
revisar
validar
ARESTAS
__start__ -> interpretar
agente -> agente [condicional]
agente -> ferramentas [condicional]
agente -> finalizar [condicional]
agente -> validar [condicional]
aprovar -> escrever
coletar -> agente [condicional]
coletar -> finalizar [condicional]
escrever -> aprovar [condicional]
escrever -> finalizar [condicional]
ferramentas -> agente [condicional]
ferramentas -> finalizar [condicional]
finalizar -> __end__
interpretar -> coletar [condicional]
interpretar -> finalizar [condicional]
preparar -> aprovar [condicional]
preparar -> escrever [condicional]
preparar -> finalizar [condicional]
revisar -> finalizar [condicional]
revisar -> preparar [condicional]
validar -> finalizar [condicional]
validar -> revisar [condicional]
```

**Desenho × código.** São os mesmos 10 nós e as mesmas 21 arestas. Dois pontos
que o desenho mostra e a lista não mostra:

- os vários **■** que saem de `coletar`, `validar` e `preparar` são, no código,
  **uma** aresta para `finalizar`. O nó grava `saida` e o portão `caminho()` a
  encaminha. O término é o mesmo nó, com o motivo no campo `termino`;
- o **router** não aparece como aresta própria: a classificação é do modelo
  (`interpretar`), e o despacho para recusa, pergunta, política ou cadastro
  acontece **dentro** de `coletar`. Mantivemos assim porque os quatro ramos
  terminam em dois destinos (`agente` ou `finalizar`), e uma aresta por
  intenção multiplicaria nós sem mudar o comportamento.

---

## 2. As seis perguntas

### As ferramentas

| Ferramenta | O que faz | Leitura/escrita | Reversível | Quem pode chamar |
|---|---|---|---|---|
| `consultar_estoque` | produto por nome (match por token), com `abaixo_do_minimo`; devolve candidatos se ambíguo | leitura | — | código (`coletar`), agente, revisor |
| `consultar_fornecedor` | prazo e pedido mínimo por id | leitura | — | agente, revisor |
| `calcular_reposicao` | `max(2×mínimo − atual, pedido mínimo)`, custo, saldo | leitura (cálculo) | — | código (`coletar`), agente, revisor |
| `buscar_documentos` | busca vetorial no corpus **vigente**, k=5, limiar 0,45 | leitura | — | agente, revisor |
| `registrar_compra` | cria a solicitação e debita o orçamento, numa transação | **escrita** | localmente sim (nada sai da loja), mas mexe no orçamento | **só o código** (`escrever`), com capacidade privada |

Todas são servidas por um **servidor MCP** (`src/servidor_mcp.py`, stdio) por
padrão. O cliente confere o catálogo contra um manifesto local (nomes,
descrições, argumentos) e recusa um servidor alterado
(`test_catalogo_malicioso_recusado`). `--sem-mcp` chama o serviço direto, com o
mesmo contrato.

### O laço

Há um laço só, `agente ⇄ ferramentas`. A cada volta: o código monta a visão do
modelo a partir do estado (`_mensagens`: objetivo + evidências + proposta +
trajetória recente); o modelo emite **uma** chamada; se for leitura,
`ferramentas` executa, acrescenta o resultado às `evidencias` e às
`mensagens`, e volta. **O que faz a volta seguinte existir** é o modelo pedir
mais uma leitura em vez de `emitir_resposta`. Na maioria dos pedidos de
estoque, o laço dá **zero voltas**: o cadastro já chegou por `coletar`, e o
modelo responde na primeira chamada (ver `io.md` §4).

### O estado

Um `TypedDict` explícito (`Estado`, `src/grafo.py:28`), com 28 campos (§5). A
lista de mensagens é **um** campo, `mensagens`, e não o estado. Decisões
(`interpretacao`, `parecer`, `decisao`), contadores e identificadores são
campos próprios.

### O orçamento

| Teto | Valor | Quem cobre |
|---|---|---|
| passos (supersteps) | 64 | LangGraph (`recursion_limit`), declarado em `src/config.py` |
| chamadas de modelo | 8 por execução (inclui retries) | nosso (`_limite`) |
| chamadas de ferramenta | 8 | nosso |
| tokens (entrada + saída) | 60 000 | nosso |
| tempo **ativo** | 600 s; a espera humana não conta | nosso (`_medir_no`, `_tempo_ativo`) |
| tempo por chamada | 120 s, e nunca mais que o saldo do teto | nosso (`src/modelo.py`) |
| tokens por resposta | 4 096 (`LLM_MAX_TOKENS`) | parâmetro da API |
| tamanho da entrada / janela | 24 000 caracteres | nosso (`max_contexto_caracteres`) |

### O término

Toda execução acaba com uma `Saida` validada, e o motivo fica em `termino`:

| `termino` | Quando |
|---|---|
| `respondido` | consulta respondida com fonte |
| `criada` | solicitação registrada (automática ou aprovada) |
| `aguardando_aprovacao` | pausa no `interrupt`; a execução continua em outra invocação |
| `rejeitada` · `expirada` | o gerente rejeitou, ou o prazo de 24 h venceu |
| `recusado` | fora do escopo, produto inexistente, sem base no corpus, revisão reprovou, saldo insuficiente |
| `esclarecimento` | falta o produto, ou o nome é ambíguo |
| `laco_detectado` | a mesma leitura repetida 4× |
| `orcamento_esgotado` | um teto do §2 estourou |
| `truncado` | resposta do modelo cortada pelo `max_tokens` |
| `erro_fatal` | falha de transporte depois dos retries, 4xx da API, exceção não prevista |

### O humano

Um ponto de parada, o `interrupt` em `aprovar`. Entra quando a compra passa de
R$ 500 ou precisa de ajuste ao saldo. O perfil chamado é o **gerente**: não o
operador que pediu, porque a política dá a alçada a ele. Se ninguém responder
em 24 h, a solicitação expira e expirar é rejeitar. Detalhe em
[`humano.md`](humano.md).

---

## 3. A defesa do nível de autonomia: **router + um laço de agente curto**

O sistema é, na maior parte, **workflow**: dos 10 nós, 7 são só código. O
nível de baixo, um **router** com etapas fixas, resolveria tudo isto:
consulta de estoque, produto inexistente, ambiguidade, divergência (o texto é
de código) e a compra.

**O que o router não resolve, e onde está no diagrama:** o nó **`agente`**
(marcado *"DECISÃO QUE SÓ O MODELO TOMA"*). Ali o modelo decide, sobre texto
livre, duas coisas:

1. **qual leitura a mais o pedido exige**, além do que o código já trouxe;
2. **se a evidência sustenta uma resposta** (`suficiente`).

**A prova precisa separar o modelo do router**, e os 9 runs de `io.md` não
separam. Neles, a busca no corpus só aconteceu quando a triagem disse
`politica`, e o próprio `_agente` exige documento nas respostas de política.
Um `if intencao == "politica": buscar()` reproduziria aqueles 9 runs. Por isso
rodamos pedidos em que a leitura necessária **não** sai da intenção
(`logs/autonomia/`, modelo real, MCP, 2026-10-18. Os logs registram commit
`6c48749` com `working_tree_modificado: true`, porque foram gerados depois do
congelamento: depois dele mudaram documentos, testes, um comentário de
`config.py`, o guarda do script de ablação e uma frase a menos em `triagem.md`. O `sha256_fontes`,
`4d765d7e…`, amarra os runs ao código final):

| Pedido | Intenção (triagem) | O que o código trouxe | O que o **modelo** decidiu ler | Resultado |
|---|---|---|---|---|
| *Quanto temos de arroz?* (`io.md`, caso 4) | `consulta` | `estoque:ARROZ_5KG` | **nada** | "Temos 12 unidades" |
| *Em quantos dias chega o refrigerante se eu pedir hoje?* | `consulta` | `estoque:REFRIGERANTE_2L` (com `fornecedor_id`, sem prazo) | **`consultar_fornecedor("FORN_B")`**, id tirado do registro | "chega em 5 dias" ✓ |
| *Quanto temos de feijão e qual o pedido mínimo do fornecedor dele?* | `consulta` | `estoque:FEIJAO_1KG` | **`consultar_fornecedor("FORN_A")`** | "40 unidades… pedido mínimo 50" ✓ |
| *Qual a política de garantia de televisores?* (`io.md`, ex. 2) | `politica` | nada | `buscar_documentos` → vazio | recusa, `suficiente: false` ✓ |

As três primeiras linhas têm **a mesma intenção** e terminam em leituras
diferentes. Um router por intenção mandaria as três pelo mesmo caminho: ou
leria o fornecedor sempre (uma leitura inútil no arroz) ou nunca (sem resposta
para o prazo). A decisão vem do conteúdo da pergunta diante do registro já
consultado, e é essa a decisão que só o modelo toma em tempo de execução.

**O resultado que não favorece o agente, declarado.** No pedido *"Preciso
repor arroz 5kg, mas e se o orçamento não der para tudo?"*, o modelo **não**
buscou no corpus a exceção de `POL-V2 §2` (o gerente pode reduzir a
quantidade). Respondeu com o cálculo e precisou de uma correção, porque citou
`proposta` como fonte. O fluxo seguiu para a aprovação humana, e é ali que a
exceção é exercida: o gerente pode editar a quantidade. O sistema não errou,
mas o modelo deixou de trazer uma regra que a pergunta pedia. Por isso o
human-in-the-loop, e não o modelo, é o dono dessa exceção.

**O revisor também escolhe a leitura.** Nos fluxos de compra, ele consultou
`consultar_fornecedor` no sal e no arroz com orçamento, e `consultar_estoque` no
arroz da demonstração (`io.md` §4). A escolha não é fixa.

**O que o modelo NÃO decide** (e um agente livre decidiria): qual produto
consultar primeiro (o código consulta), quanto comprar (o código calcula),
**se** compra (o serviço exige intenção + estoque abaixo do mínimo + revisão +
aprovação), e a escrita (o modelo não tem a ferramenta).

**O caso 3 (registro inexistente) é tratado pelo código, de propósito.** O
enunciado sugere um erro de ferramenta que o modelo contorna. No nosso
sistema, `consultar_estoque` é chamado pelo código em `coletar`. Quando o
produto não existe, o código recusa **sem chamar o modelo**, com a lista do
cadastro (log do caso `inexistente`: 1 chamada de modelo, só a triagem). A
razão: a resposta certa para "iogurte" não depende de julgamento, e deixar o
modelo contornar o erro abriria espaço para o pior desfecho do case, que é
**inventar um estoque**. Na Parte 1, essa família era resolvida pelo modelo, que
acertava 12/12 (`docs/modelos.md`). Na Parte 2, ela não gasta modelo nenhum, e
não pode errar assim. O modelo ainda contorna erros de ferramenta **dentro** do
laço: uma leitura que falha volta como observação em `ferramentas`
(`{"erro": ...}`), e o modelo segue com o que tem ou recusa.

---

## 4. A fronteira de confiança

| Camada | Confia em | Não confia em |
|---|---|---|
| modelo (triagem, agente, revisor) | — | é tratado como conteúdo não confiável: pode errar a rota, citar fonte inexistente ou ser induzido por texto do usuário ou do corpus |
| grafo (código) | contratos Pydantic, regras verificáveis | nos argumentos que o modelo propõe: fontes têm de estar nas evidências recuperadas **nesta** execução |
| serviço (`src/servico.py`) | só no próprio banco | no grafo: na escrita, revalida estoque, preço, fornecedor, pedido mínimo, saldo, aprovação, revisão e prazo, na **mesma transação** do débito |

Testes que sustentam a tabela: `test_proposta_adulterada_recusada` (preço,
quantidade ou produto adulterados), `test_backend_revalida_estoque`,
`test_documento_hostil_nao_concede_escrita`, `test_fonte_inventada_recusa_apos_uma_correcao`.

---

## 5. O estado que atravessa o grafo — item 7

### 5.1 Os campos

| Campo | Tipo | Quem **escreve** | Quem **lê** | De onde veio |
|---|---|---|---|---|
| `texto` | `str` | entrada (`iniciar`) | `interpretar`, `coletar`, `_mensagens`, log | o operador digitou |
| `usuario` | `str` | entrada | `coletar` (memória), `preparar`, `finalizar`, `iniciar` (isolamento) | `--usuario` da CLI |
| `thread_id` | `str` | entrada | `_saida`, `finalizar` (episódio), log | `usuario:uuid4` |
| `caso_id` | `str` | entrada | eventos, `preparar`, `aprovar`, `escrever`, `finalizar` | `uuid4` por pedido |
| `mensagens` | `list[dict]`, **reducer `operator.add`** | `coletar`, `agente` (correção), `ferramentas` | `interpretar` (últimas 4), `_mensagens` | conversa e trajetória |
| `eventos` | `list[dict]`, **reducer `operator.add`** | todos os nós que chamam modelo ou ferramenta, e `finalizar` | `ferramentas` (detector de laço), log | trajetória auditável |
| `interpretacao` | `dict` (`Interpretacao`) | `interpretar` | `coletar`, `agente`, `validar`, `preparar`, `finalizar` | modelo (triagem) |
| `produto` | `dict` | `coletar` | `validar`, `preparar`, `finalizar` | `consultar_estoque` |
| `proposta` | `dict \| None` | `coletar` | `_mensagens`, `validar`, `revisar`, `preparar`, aresta de `preparar`, `aprovar` | `calcular_reposicao` |
| `evidencias` | `dict[id → Fonte]` | `coletar`, `ferramentas` (substituição pelo dicionário completo) | `agente` (confere fontes), `revisar`, `_saida` | ferramentas e corpus |
| `lembrancas` | `list[dict]` | `coletar` | entra em `mensagens` | memória episódica |
| `chamada` | `dict \| None` | `agente`; `ferramentas` zera | `ferramentas`, aresta de `agente` | modelo |
| `candidata` | `dict \| None` | `agente` | `validar`, aresta de `agente` | modelo (`RespostaModelo`) |
| `parecer` | `dict \| None` | `revisar` | `preparar` | modelo revisor (`Parecer`) |
| `decisao` | `dict \| None` | `aprovar` | `escrever` | humano (`DecisaoHumana`) |
| `correcao_humana` | `str \| None` | `escrever` (erro da edição); `aprovar` zera | `aprovar` (payload), aresta de `escrever` | serviço |
| `saida` | `dict \| None` | qualquer nó que encerra; `finalizar` | portão `caminho()`, `_executar` | — |
| `erro` | `str \| None` | qualquer nó, em falha | portão, `finalizar` (classifica o término) | — |
| `alias_pendente`, `candidatos_pendentes` | `str`, `list[str]` | `coletar` | `interpretar`, `coletar` (turno seguinte) | desambiguação |
| `correcoes` | `int` | `agente` | `agente` | — |
| `n_modelo`, `n_ferramentas`, `n_recuperacoes`, `tokens_entrada`, `tokens_saida` | `int` | `_chamar`/`_ler`, copiados por cada nó via `_contadores` | `_limite`, log | contagem |
| `processamento_s` | `float` | `_medir_no`, em todo nó | `_limite`, log | relógio monotônico |
| `uso_incompleto` | `bool` | `_chamar` | log (custo) | resposta da API sem `usage` |

**Campos escritos por vários nós sem reducer:** `saida`, `erro` e os
contadores. Não há corrida, porque o grafo não tem ramos paralelos: há sempre
um nó por superstep, e o último a escrever é, por construção, o mais recente.
Os contadores são gravados como **total acumulado**, não como incremento, então
sobrescrever é o correto. **Se um dia houver paralelismo**, esses campos
precisam de reducer (`max` para os contadores, ou deltas somados), e o
LangGraph avisaria com `InvalidUpdateError` (§5.2).

### 5.2 Os reducers, e o que acontece sem eles

| Campo | Reducer | Por quê |
|---|---|---|
| `mensagens` | `operator.add` | cada nó devolve **só as mensagens novas**; sem o reducer, o turno anterior da conversa e o par `assistant`/`tool` da volta anterior seriam sobrescritos |
| `eventos` | `operator.add` | a trajetória é acumulativa; ela alimenta o detector de laço e o log |

O `add_messages` do LangGraph não foi usado: ele deduplica por `id` de
mensagem, e as nossas são dicionários sem id. A concatenação pura é o
comportamento que queremos.

**A demonstração** (`python src/demonstrar_reducers.py` → `logs/reducers/demonstracao.json`):

| Experimento | Sem reducer | Com reducer |
|---|---|---|
| grafo isolado, dois ramos **paralelos** escrevendo `valores` | `InvalidUpdateError: At key 'valores': Can receive only one value per step` | `['a', 'b']` |
| o **grafo real**, sequencial, `eventos` sem `operator.add`, pergunta *"Quanto temos de arroz?"* | status `respondido`, **1 evento** (`memoria`) | status `respondido`, **4 eventos** (triagem, `consultar_estoque`, decisão, memória) |

**O defeito silencioso está na segunda linha, não na primeira.** No paralelo,
o LangGraph nos protege com uma exceção. No sequencial, que é o nosso grafo, o
campo sem reducer é sobrescrito a cada nó, a saída continua **idêntica**,
nenhum erro aparece, e a trajetória perde três de quatro eventos. O detector de
laço, que lê `eventos`, deixa de ver as chamadas anteriores. Ele quebraria sem
nenhum sinal. O teste `test_sem_reducer_o_grafo_real_perde_trajetoria_em_silencio`
fixa esse comportamento.

### 5.3 O que NÃO está no estado

**O que ficou na lista de mensagens:** o pedido do turno (como JSON com
pergunta, interpretação, evidências, proposta e episódios), as chamadas de
ferramenta do agente e os resultados delas, e as mensagens de correção. É
texto conversacional para o modelo. Decisões, contadores e identificadores não
ficam ali.

**O que é derivado e não guardado:**
- **a visão do modelo** (`_mensagens`): recalculada a cada chamada a partir do
  estado, com a janela aplicada. Guardar criaria duas fontes de verdade, a
  trajetória e a visão cortada dela;
- **"precisa de aprovação?"**: calculado na aresta de `preparar` a partir de
  `proposta`, sem flag no estado, que poderia divergir do custo;
- **o motivo de término**: derivado de `erro` em `finalizar`;
- **a expiração**: derivada de `casos.expira` no momento da leitura, e não um
  status mantido por agendador;
- **o custo em dólar**: calculado no log a partir dos tokens e da tarifa.

### 5.4 O estado entre agentes

O sistema tem dois papéis de modelo, o agente de reposição e o revisor. O
revisor recebe **um objeto de contrato próprio**, `{proposta, evidencias}`, e
não o estado inteiro nem a trajetória (`_revisar`). Assim ele não é
influenciado pelo raciocínio do agente, e um campo novo no `Estado` não o
alcança. O que ele devolve é o `Parecer` validado, o único campo que ele
escreve. A escolha é **definitiva**: a independência do revisor depende de ele
não ver a trajetória.

---

## 6. A fronteira com software tradicional

As ferramentas falam com um SQLite real, por um servidor MCP, por um processo
separado. O grafo não escreve SQL. Regra de negócio, transação e idempotência
pertencem a `src/servico.py`, que é software comum e é testado sem modelo
nenhum (os testes `test_compra_automatica_*` a `test_gerente_nao_ultrapassa_saldo`, no início de `tests/test_sistema.py`).

---

## 7. Histórico: a arquitetura da Parte 1

Até o commit `d796ef8`, o agente era um laço ReAct escrito à mão
(`src/agente.py`), com gating por fase: a ferramenta de escrita
`criar_solicitacao_compra` só era **oferecida** ao modelo quando o estoque
consultado estava abaixo do mínimo. A Parte 2 trocou isso por três coisas:

| Parte 1 | Parte 2 | Por quê |
|---|---|---|
| laço `while True` à mão | `StateGraph` com checkpointer | retomada depois da pausa humana sem reimplementar persistência |
| o modelo podia chamar a escrita, quando liberada | o modelo **nunca** tem a escrita; o nó `escrever` (código) chama | "não podia chamar" é mais forte que "não foi oferecida nesta fase" |
| compra > R$ 500 gravada como pendente | nada é gravado antes do `interrupt` | uma linha pendente é efeito colateral; a pausa não é |
| regras no prompt | regras no corpus (RAG) e no serviço | o conhecimento tem dono, versão e vigência |

O documento completo da Parte 1 está em `git show d796ef8:projeto-llm/docs/arquitetura.md`.
