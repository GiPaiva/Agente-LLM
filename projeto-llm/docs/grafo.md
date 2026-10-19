# O grafo — item 6

> **O desenho canônico do grafo está em [`arquitetura.md`](arquitetura.md) §1**,
> ao lado da saída de `conferir_grafo.py`. Este documento não repete o desenho
> (dois desenhos divergem), e trata do resto do item 6: os padrões, quem decide
> cada bifurcação, o que o framework não deu e a decisão que virou parâmetro. A
> tabela de campos do estado e os reducers (item 7) estão em `arquitetura.md` §5.

---

## 1. A implementação

- `StateGraph(Estado)` em `src/grafo.py`, `Aplicacao._compilar`: 10 nós, 1
  aresta fixa de entrada, 1 de saída, 1 incondicional no meio
  (`aprovar -> escrever`) e 8 nós com aresta condicional, todas com **mapa de
  destinos explícito** (`{"finalizar": "finalizar", ...}`).
- **Compilado uma vez**: `self.grafo = self._compilar()` no construtor de
  `Aplicacao`. A CLI cria uma aplicação por processo e reutiliza o mesmo grafo
  em todas as perguntas e retomadas.
- **Sem paralelismo.** Não há arestas saindo do mesmo ponto para dois nós nem
  `Send`. O único candidato natural seria rodar o revisor em paralelo com o
  agente, mas o revisor **depende** da proposta do agente. E, com o LM Studio
  local atendendo uma requisição por vez, paralelizar chamadas de modelo daria
  a soma dos tempos, não o maior (o aviso medido na Aula 09).
- **Conferência:** `python conferir_grafo.py` importa `Aplicacao` de `src/grafo.py`
  (o mesmo objeto que `src/main.py` executa) e imprime `get_graph()`. A saída
  está colada em `arquitetura.md` §1.

---

## 2. Os padrões, nomeados

| Padrão | Onde, no grafo | Por que ele, e não o de baixo | Condição de não uso |
|---|---|---|---|
| **sequencial com portão** | `interpretar → coletar → … → validar → revisar → preparar → escrever`; cada aresta passa pelo portão `caminho()`: se já há `saida` ou `erro`, vai a `finalizar` | é a espinha do pedido. O portão é o que transforma "erro no meio" em término classificado, em vez de exceção solta | — (é o degrau mais baixo) |
| ***router*** | `interpretar` classifica a intenção num `Literal["consulta","reposicao","politica","fora_escopo"]`; `coletar` despacha: `fora_escopo` e produto vazio vão a `finalizar`; `politica` vai ao agente **sem** consultar o cadastro; `consulta`/`reposicao` consultam o cadastro antes | texto livre não tem campo "intenção": uma regra por palavra-chave erra *"tá acabando o arroz, pede mais"* × *"como está o arroz?"*. É julgamento sobre linguagem, que o código não faz | se a entrada viesse de um formulário com a intenção marcada, o router viraria um `if` |
| **agente (laço curto)** | `agente ⇄ ferramentas`, com `agente → agente` na correção de saída | o modelo decide **se** precisa de mais alguma leitura (documento, fornecedor) antes de responder, e **se** a resposta tem base (`suficiente`). A quantidade de voltas depende do pedido: 0 para "quanto temos de arroz?" (o cadastro já veio), 1+ para política | se toda pergunta precisasse sempre da mesma leitura, seria uma etapa fixa (ver `rag.md` §5) |
| **avaliador-otimizador** (avaliador) | `revisar`: um segundo papel de modelo, com prompt próprio e **subconjunto** do estado (proposta + evidências, sem a trajetória), que consulta de forma independente e emite `Parecer` | uma compra mexe no orçamento. O validador em código (`validar`) cobre o verificável (saldo, fonte citada existe); o revisor cobre a coerência entre proposta, cadastro e regra do corpus | no modo `--um-agente` o revisor é desligado e só o portão em código decide (o comparativo está em `src/comparar_agentes.py`) |
| **human-in-the-loop** | `preparar → aprovar (interrupt) → escrever` | ver [`humano.md`](humano.md) | compra ≤ R$ 500 com saldo: segue direto para `escrever` |

**Não usamos:** paralelização (sem ganho real num servidor local, como acima) e
orquestrador-trabalhador (não há subtarefas independentes a distribuir; um
pedido é sobre um produto).

**O degrau mais caro está justificado?** O laço do agente existe, mas é
**curto e cercado**: o cadastro e o cálculo vêm do código **antes** do laço
(`coletar`), a escrita fica **fora** do alcance do modelo (o agente só tem
ferramentas de leitura), e o que ele decide é só *se busca mais* e *se
responde ou recusa*. A defesa completa, com a decisão apontada no diagrama,
está em `arquitetura.md` §3.

---

## 3. Quem decide cada bifurcação

| Aresta condicional | Destinos | Quem decide | Como |
|---|---|---|---|
| `interpretar →` | `coletar` · `finalizar` | **código** | `saida` ou `erro` presentes (entrada longa demais, contrato da triagem inválido após uma correção) |
| `coletar →` | `agente` · `finalizar` | **código**, sobre a saída do **modelo** | o `Literal` da triagem (`fora_escopo` → recusa) e campos verificáveis (produto vazio → pergunta; produto não encontrado ou ambíguo → recusa ou pergunta) |
| `agente →` | `ferramentas` · `validar` · `agente` · `finalizar` | **modelo**, com saída estruturada | o modelo emite **uma** chamada de ferramenta (`tool_choice="required"`): uma leitura → `ferramentas`; `emitir_resposta` com `RespostaModelo` validado → `validar`; resposta inválida na 1ª vez → `agente` (correção); erro ou teto → `finalizar` |
| `ferramentas →` | `agente` · `finalizar` | **código** | detector de laço e tetos |
| `validar →` | `revisar` · `finalizar` | **código** | `suficiente=false` → recusa; proposta acima do saldo e pedido mínimo também acima → recusa; sem proposta (consulta) → resposta; com proposta → revisão |
| `revisar →` | `preparar` · `finalizar` | **código**, sobre a saída do **modelo** revisor | o portão `caminho()`. Se o parecer reprovar, quem encerra é `preparar` |
| `preparar →` | `aprovar` · `escrever` · `finalizar` | **código** | `custo_estimado > min(500, orcamento_disponivel)` → `aprovar` |
| `escrever →` | `aprovar` · `finalizar` | **código** | edição humana inválida (`RegraNegocio` depois de uma decisão) → volta à pausa |

**Nenhuma bifurcação usa embedding como roteador.** As rotas de intenção
dependem de pedido × informação ("pede mais" × "como está"), e não de assunto:
as duas frases são sobre o mesmo produto. A similaridade de embedding não as
separa.

**O schema garante a rota, não a rota certa.** Na triagem, o `Literal` impede
uma intenção inventada, mas não impede `consulta` onde era `reposicao`. Quem
cobre o erro de rota é o serviço: `preparar` recusa escrever sem
`intencao == "reposicao"` **e** sem `abaixo_do_minimo`. Um erro de triagem pode
deixar de comprar, mas não pode comprar o que não devia.

---

## 4. O que o framework não deu

| Frente | O framework cobre? | O que escrevemos | Onde | Linhas |
|---|---|---|---|---|
| **motivo de término** | não: `END` diz que acabou, não por quê | `Saida.termino` + classificação em `_finalizar` (`laco_detectado`, `orcamento_esgotado`, `truncado`, `erro_fatal`) + `_executar` convertendo exceção em `falha` | `src/contratos.py:59`, `src/grafo.py:439-459`, `src/grafo.py:514-528` | ~25 |
| **detector de laço** | não: `recursion_limit` só limita | a mesma ferramenta com os mesmos argumentos 2× injeta uma observação ("você já fez esta consulta"); 4× encerra com `laco_detectado` | `src/grafo.py:311-330` | 6 |
| **tetos** | só passos (`recursion_limit`) | chamadas de modelo (8), ferramentas (8), tokens (60 000), tempo **ativo** (600 s, sem contar a espera humana), e o saldo de tempo repassado ao timeout de cada chamada | `src/grafo.py:100-128`, `src/modelo.py:38-42` | ~32 |
| **erro recuperável × fatal** | não | 4xx = fatal sem retry (configuração/cota); 5xx e conexão = retry explícito (`max_retries=0` no SDK, para não haver retry escondido); `RegraNegocio` depois de uma decisão humana = recuperável (volta à pausa); resto = fatal | `src/modelo.py:39-52`, `src/grafo.py:150-156`, `src/grafo.py:433-437` | ~23 |

Total: **cerca de 86 linhas** de código que o framework não deu.

**O que o framework cobriu inteiro, e não escrevemos:**
- persistência e retomada: `compile(checkpointer=SqliteSaver(...))`
  (`src/grafo.py`, fim de `_compilar`) + `interrupt`/`Command(resume=...)`
  (`_aprovar`, `retomar`). Nenhuma linha nossa serializa estado;
- reducers: `Annotated[list[dict], operator.add]` em `mensagens` e `eventos`
  (`src/grafo.py:33-34`);
- proteção contra escrita concorrente sem reducer: ramos paralelos escrevendo a
  mesma chave levantam `InvalidUpdateError` (demonstrado em
  `src/demonstrar_reducers.py`, `paralelo_isolado`).

---

## 5. A decisão que virou parâmetro

**`recursion_limit`.** Na Parte 1, o laço à mão tinha um teto de passos
**explícito**, justificado pelo orçamento. No LangGraph, essa decisão virou um
parâmetro de configuração com valor padrão, que ninguém precisa escrever. O
número que o grupo tinha em mente era **25 supersteps**, o padrão que o
`langchain_core` ainda declara (`DEFAULT_RECURSION_LIMIT = 25` em
`langchain_core/runnables/config.py`, no pacote instalado).

**O padrão já mudou, e nós medimos.** Na versão fixada neste repositório
(`langgraph==1.2.15`), o LangGraph tem o próprio padrão:
`DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT",
"10007"))` (`langgraph/_internal/_config.py:32`). Um grafo em laço infinito,
invocado sem configuração, só para em **10 007** supersteps. Com
`recursion_limit=64`, para em 64. A execução das duas variantes está em
`logs/diagnostico/recursion-limit-padrao.txt`, e o caminho de 64 fica fixado em
`test_recursion_limit_declarado_vence_o_padrao_da_lib`. É o cenário que o §6.6
descreve: a biblioteca mudou um padrão, e quem dependia dele perdeu o teto de
passos sem nenhum aviso. Num modelo local de 30 s por chamada, 10 007 passos
são dias.

**Por que declaramos 64.** Um pedido com aprovação percorre cerca de 9 nós fixos
(`interpretar`, `coletar`, `agente`, `validar`, `revisar`, `preparar`,
`aprovar`, `escrever`, `finalizar`), e o laço `agente ⇄ ferramentas` pode dar
até 8 voltas (o teto de ferramentas), ou seja, 16 supersteps. Somando a
reentrada da edição inválida, o pior caso legítimo passa de 25. Com o padrão
antigo, uma execução legítima longa terminaria em `GraphRecursionError` no
lugar do nosso `orcamento_esgotado`, que é mais informativo. Com o padrão novo,
o teto do framework deixa de existir na prática. Por isso 64: acima de qualquer
caminho legítimo, para que **os nossos tetos disparem antes do teto do
framework**, e com um teto do framework que continua existindo.

**Se o padrão mudar de novo:** nada muda para nós. O valor está declarado em
`src/config.py` (`recursion_limit: int = 64`, com o comentário da decisão), é
passado em toda chamada (`Aplicacao._config`) e é gravado em cada log
(`parametros.recursion_limit`). O teste canário falha se o padrão da biblioteca
voltar a ficar abaixo de 64, ou se o nosso valor deixar de ser aplicado.

**Outras decisões que viraram parâmetro, também declaradas:**
- o reducer de `mensagens`: o `add_messages` do LangGraph deduplica por id,
  e nós usamos `operator.add` (concatenação pura), porque as mensagens são
  dicionários sem id;
- `max_retries=0` no cliente `openai`, cujo padrão é **2 retries escondidos**.
  Os retries são nossos e contam no orçamento (`src/modelo.py`, teste
  `test_sdk_openai_http_local_sem_retries_ocultos`);
- `parallel_tool_calls=False` e `tool_choice="required"`, enviados em toda
  chamada (`src/modelo.py`).
