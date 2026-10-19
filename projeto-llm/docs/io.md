# Entrada e saída — item 1

> O contrato do sistema com quem o usa. O schema vive no código, em
> `src/contratos.py` (Pydantic, `extra="forbid"`, `strict=True`). Todos os
> exemplos abaixo foram **copiados dos logs** de execuções reais: os blocos
> JSON foram extraídos do campo `saida` de cada arquivo citado, sem edição.
> Commit, data e arquivo de log aparecem em cada exemplo.
>
> Ambiente das execuções: LM Studio local, `google/gemma-4-e4b`,
> `temperature=0`, `max_tokens=4096`, ferramentas servidas por MCP, commit
> `6c48749` com a árvore limpa.

---

## 1. A entrada

**O sistema recebe texto livre**, digitado pelo operador: `python src/main.py
"<texto>"`, ou o modo interativo `python src/main.py`. Não há formulário nem
campo obrigatório.

O que acompanha o texto **sem ser digitado**:

| Metadado | De onde vem | Para que serve |
|---|---|---|
| `usuario` | `--usuario` (padrão `operador-demo`). Numa loja, viria do login | isola memória e conversa por pessoa |
| `thread_id` | `--thread`, ou gerado como `usuario:uuid4` | o endereço do checkpoint (ver `memoria.md` §6) |
| `caso_id` | `uuid4` novo por pedido | a chave de idempotência da compra (ver `humano.md` §5) |
| perfil | `--perfil operador\|gerente` | só o gerente retoma uma aprovação |

A aprovação do gerente **não** é texto livre: é uma resposta estruturada a uma
pausa (`--retomar aprovar|rejeitar [--quantidade N]`), validada por
`DecisaoHumana`. Ela não é a entrada do sistema, é a resposta a um ponto de
parada. Ver [`humano.md`](humano.md).

---

## 2. O contrato de saída

`Saida` (`src/contratos.py`), devolvida em **toda** execução, inclusive na
recusa e na falha:

| Campo | Tipo | Papel no contrato |
|---|---|---|
| `resultado` | `str` | **o resultado**: a resposta, a pergunta de volta, a recusa com o motivo, ou a solicitação criada |
| `fontes` | `list[Fonte]` (`id`, `tipo ∈ {registro, documento, memoria}`, `trecho`) | **a fonte**: só evidência recuperada **nesta** execução; o trecho vai junto, para conferir |
| `suficiente` | `bool` | **a suficiência**: se havia base para responder ou agir. `false` é recusa, pergunta ou falha |
| `status` | `Literal[respondido, recusado, esclarecimento, aguardando_aprovacao, criada, rejeitada, expirada, falha]` | o que aconteceu |
| `termino` | `str` | o motivo do término (taxonomia em `arquitetura.md` §2) |
| `perguntas` | `list[str]` | o que o sistema precisa saber, quando `status = esclarecimento` |
| `aprovacao` | `dict \| None` | o payload da pausa, quando `status = aguardando_aprovacao` |
| `solicitacao` | `dict \| None` | a solicitação registrada, quando `status = criada` |
| `thread_id`, `caso_id` | `str` | para retomar e auditar |

**A recusa é parte do contrato:** `suficiente=false` com `status=recusado` e um
`resultado` que diz o que falta ou o que o sistema faz.

Os contratos **internos**, entre etapas, também são validados:
`Interpretacao` (triagem), `RespostaModelo` (agente), `Parecer` (revisor) e
`DecisaoHumana` (gerente). Estão descritos em [`prompts.md`](prompts.md) §2.

---

## 3. Os exemplos

### Exemplo 1 — o caminho feliz (caso 1 do §9: o caso simples)

**Entrada exata:**

```text
O sal de 1kg tá no fim, registra a reposição.
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Solicitação criada: 50 unidades; custo R$ 115.00. Nenhum pedido foi enviado ao fornecedor.",
  "fontes": [
    {
      "id": "estoque:SAL_1KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"SAL_1KG\", \"nome\": \"Sal 1kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 8, \"estoque_minimo\": 20, \"venda_media_diaria\": 1.5, \"preco_unitario\": 2.3, \"fornecedor_id\": \"FORN_A\", \"abaixo_do_minimo\": true}"
    },
    {
      "id": "calculo:SAL_1KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"SAL_1KG\", \"nome\": \"Sal 1kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 8, \"estoque_minimo\": 20, \"venda_media_diaria\": 1.5, \"preco_unitario\": 2.3, \"fornecedor_id\": \"FORN_A\", \"pedido_minimo\": 50, \"prazo_dias\": 2, \"produto_id\": \"SAL_1KG\", \"precisa_repor\": true, \"quantidade_recomendada\": 50, \"quantidade\": 50, \"custo_estimado\": 115.0, \"orcamento_disponivel\": 1200.0, \"limite_sem_aprovacao\": 500}"
    }
  ],
  "suficiente": true,
  "status": "criada",
  "thread_id": "operador-demo:0bd05d303df74108afd97b961e5bb6cc",
  "caso_id": "52cfa5f150c34124993aa464c3fe3a62",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": {
    "chave": "baf04d947b00352e40e3e304ba5c9874319d2bca854154d5a46c44e24d66bad0",
    "produto_id": "SAL_1KG",
    "quantidade": 50,
    "custo_estimado": 115.0,
    "status": "criada",
    "caso_id": "52cfa5f150c34124993aa464c3fe3a62",
    "ja_existia": false
  },
  "termino": "criada"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:23:43 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/52cfa5f150c34124993aa464c3fe3a62-a4192e18.json`](../logs/demonstracoes/real/20261018-212136-726175/52cfa5f150c34124993aa464c3fe3a62-a4192e18.json)
>
> chamadas de modelo **4** · ferramentas **4** · recuperações **0** · tokens 4395+2969 · 127 s ativos


**O que ler aqui:** `status: criada` com a solicitação de **50** unidades, não
48. O pedido mínimo do fornecedor foi aplicado pelo código (`calculo:SAL_1KG`
nas fontes). O custo de R$ 115 está abaixo do teto de R$ 500, então não houve
pausa. As duas fontes são registros conferíveis, e o texto diz que **nenhum
pedido foi enviado ao fornecedor** (é solicitação, não pedido; ver `case.md` §12.1).

### Exemplo 2 — a recusa (caso 5 do §9: fora do corpus)

**Entrada exata:**

```text
Qual a política de garantia de televisores?
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Não encontrei trecho vigente sobre a política de garantia de televisores. Por favor, forneça mais detalhes ou verifique os documentos do contrato/produto.",
  "fontes": [],
  "suficiente": false,
  "status": "recusado",
  "thread_id": "operador-demo:f782488c19704a5ea7c0373104c70c49",
  "caso_id": "2abff029b55147559a8c18846706d803",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "recusado"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:25:47 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/2abff029b55147559a8c18846706d803-62b4b8e0.json`](../logs/demonstracoes/real/20261018-212136-726175/2abff029b55147559a8c18846706d803-62b4b8e0.json)
>
> chamadas de modelo **3** · ferramentas **1** · recuperações **1** · tokens 1685+670 · 30 s ativos


**O que ler aqui:** `suficiente: false` e `fontes: []`. A triagem classificou
como `politica`, o modelo **decidiu buscar** (`recuperações 1`), a busca
devolveu zero trechos acima do limiar, e o modelo recusou em vez de responder
pela própria memória. O `resultado` diz **o que não encontrou** e sugere onde
procurar. Isto é o §1.2, não o §1.4: a pergunta está no escopo (política de
compra), mas a resposta não está no corpus.

### Exemplo 3 — entrada incompleta (§1.4)

**Entrada exata:**

```text
Preciso repor.
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Qual produto você quer consultar ou repor?",
  "fontes": [],
  "suficiente": false,
  "status": "esclarecimento",
  "thread_id": "operador-demo:ed03761c2e6f428a9d8469e3c4277629",
  "caso_id": "00c292cfe9574dc9a15c29c06a0cfb1a",
  "perguntas": [
    "Qual produto você quer consultar ou repor?"
  ],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "esclarecimento"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:28:43 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/00c292cfe9574dc9a15c29c06a0cfb1a-d2604021.json`](../logs/demonstracoes/real/20261018-212136-726175/00c292cfe9574dc9a15c29c06a0cfb1a-d2604021.json)
>
> chamadas de modelo **1** · ferramentas **0** · recuperações **0** · tokens 325+613 · 27 s ativos


**O que ler aqui:** o sistema **pergunta o que falta** (`perguntas` preenchido,
`status: esclarecimento`) e gastou **uma** chamada de modelo: a triagem
extraiu `reposicao` sem produto, e o código parou antes de consultar qualquer
coisa. Responder como se a entrada estivesse completa exigiria inventar um
produto.

### Exemplo 4 — entrada ambígua (§1.4)

**Entrada exata:**

```text
Como está o açúcar?
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Qual destes produtos: Açúcar Refinado 1kg, Açúcar Refinado 5kg?",
  "fontes": [],
  "suficiente": false,
  "status": "esclarecimento",
  "thread_id": "operador-demo:300f085d1490454aa486fba7d024af52",
  "caso_id": "023c8c6e85d24ddca711714478e93886",
  "perguntas": [
    "Qual destes produtos: Açúcar Refinado 1kg, Açúcar Refinado 5kg?"
  ],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "esclarecimento"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:28:55 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/023c8c6e85d24ddca711714478e93886-0b20a436.json`](../logs/demonstracoes/real/20261018-212136-726175/023c8c6e85d24ddca711714478e93886-0b20a436.json)
>
> chamadas de modelo **1** · ferramentas **1** · recuperações **0** · tokens 325+257 · 12 s ativos


**O que ler aqui:** "açúcar" casa com dois produtos de situação **oposta**
(1kg acima do mínimo, 5kg abaixo). O sistema não escolhe: lista os candidatos
e espera. O próximo turno, na mesma `thread_id`, resolve com *"o de 5kg"*
(demonstrado em `logs/memoria/remocao-real-20261018-214747.json`, passos 1–2).

### Exemplo 5 — entrada fora do escopo (§1.4)

**Entrada exata:**

```text
Qual a capital do Canadá?
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Atendo consultas de estoque, reposição e políticas de compra deste mercado simulado.",
  "fontes": [],
  "suficiente": false,
  "status": "recusado",
  "thread_id": "operador-demo:3a0d95ad5d3841e7ab55b54b7f35593f",
  "caso_id": "197dd8c5e821426cb7b04b845497904f",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "recusado"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:48:52 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/exemplos-cli/197dd8c5e821426cb7b04b845497904f-35771195.json`](../logs/exemplos-cli/197dd8c5e821426cb7b04b845497904f-35771195.json)
>
> chamadas de modelo **1** · ferramentas **0** · recuperações **0** · tokens 326+345 · 13 s ativos


**O que ler aqui:** recusa sem consultar nada (`ferramentas 0`), dizendo **o
que o sistema faz**. A triagem devolveu `fora_escopo`, e o router em `coletar`
encerrou. Este exemplo foi rodado pela CLI (`python src/main.py "Qual a capital
do Canadá?"`); a saída de tela está em `logs/exemplos-cli/saida-cli-fora.json`.

### Exemplo 6 — a ação que para e espera (caso 6 do §9)

**1ª invocação — a pausa:**

**Entrada exata:**

```text
Preciso repor arroz 5kg.
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "O gerente precisa revisar esta solicitação antes da compra.",
  "fontes": [
    {
      "id": "estoque:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"abaixo_do_minimo\": true}"
    },
    {
      "id": "calculo:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"pedido_minimo\": 50, \"prazo_dias\": 2, \"produto_id\": \"ARROZ_5KG\", \"precisa_repor\": true, \"quantidade_recomendada\": 50, \"quantidade\": 50, \"custo_estimado\": 925.0, \"orcamento_disponivel\": 1200.0, \"limite_sem_aprovacao\": 500}"
    }
  ],
  "suficiente": true,
  "status": "aguardando_aprovacao",
  "thread_id": "operador-demo:7569cf17854f42669cacb61fa14bcaa6",
  "caso_id": "0c688bcd18674de48271aa5a5f6af04c",
  "perguntas": [],
  "aprovacao": {
    "acao": "registrar_compra",
    "caso_id": "0c688bcd18674de48271aa5a5f6af04c",
    "produto": "Arroz 5kg",
    "fornecedor": "FORN_A",
    "quantidade": 50,
    "custo_estimado": 925.0,
    "orcamento": 1200.0,
    "motivo": "Valor acima de R$ 500 ou quantidade precisa de ajuste ao saldo",
    "consequencia": "Criar uma solicitação local e debitar o orçamento; nenhum envio externo.",
    "respostas": [
      "aprovar",
      "rejeitar"
    ],
    "editavel": [
      "quantidade"
    ],
    "erro_validacao_anterior": null,
    "expira": "2026-10-19T21:28:16.020991-03:00"
  },
  "solicitacao": null,
  "termino": "aguardando_aprovacao"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:28:16 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/0c688bcd18674de48271aa5a5f6af04c-6b8b3de6.json`](../logs/demonstracoes/real/20261018-212136-726175/0c688bcd18674de48271aa5a5f6af04c-6b8b3de6.json)
>
> chamadas de modelo **4** · ferramentas **3** · recuperações **0** · tokens 4539+3214 · 148 s ativos


**2ª invocação — o gerente aprova editando a quantidade para 55:**

**Entrada exata:**

```text
Preciso repor arroz 5kg.
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Solicitação criada: 55 unidades; custo R$ 1017.50. Nenhum pedido foi enviado ao fornecedor.",
  "fontes": [
    {
      "id": "estoque:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"abaixo_do_minimo\": true}"
    },
    {
      "id": "calculo:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"pedido_minimo\": 50, \"prazo_dias\": 2, \"produto_id\": \"ARROZ_5KG\", \"precisa_repor\": true, \"quantidade_recomendada\": 50, \"quantidade\": 50, \"custo_estimado\": 925.0, \"orcamento_disponivel\": 1200.0, \"limite_sem_aprovacao\": 500}"
    }
  ],
  "suficiente": true,
  "status": "criada",
  "thread_id": "operador-demo:7569cf17854f42669cacb61fa14bcaa6",
  "caso_id": "0c688bcd18674de48271aa5a5f6af04c",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": {
    "chave": "34eae016a1fd0d10e8ec1eb9004d101996f306be4f142cbbf72a382aea8625d5",
    "produto_id": "ARROZ_5KG",
    "quantidade": 55,
    "custo_estimado": 1017.5,
    "status": "criada",
    "caso_id": "0c688bcd18674de48271aa5a5f6af04c",
    "ja_existia": false
  },
  "termino": "criada"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:28:16 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/0c688bcd18674de48271aa5a5f6af04c-3534f3b8.json`](../logs/demonstracoes/real/20261018-212136-726175/0c688bcd18674de48271aa5a5f6af04c-3534f3b8.json)
>
> chamadas de modelo **4** · ferramentas **4** · recuperações **0** · tokens 4539+3214 · 149 s ativos


**3ª invocação — a mesma aprovação chega de novo:**

**Entrada exata:**

```text
Preciso repor arroz 5kg.
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Solicitação criada: 55 unidades; custo R$ 1017.50. Nenhum pedido foi enviado ao fornecedor.",
  "fontes": [
    {
      "id": "estoque:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"abaixo_do_minimo\": true}"
    },
    {
      "id": "calculo:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"pedido_minimo\": 50, \"prazo_dias\": 2, \"produto_id\": \"ARROZ_5KG\", \"precisa_repor\": true, \"quantidade_recomendada\": 50, \"quantidade\": 50, \"custo_estimado\": 925.0, \"orcamento_disponivel\": 1200.0, \"limite_sem_aprovacao\": 500}"
    }
  ],
  "suficiente": true,
  "status": "criada",
  "thread_id": "operador-demo:7569cf17854f42669cacb61fa14bcaa6",
  "caso_id": "0c688bcd18674de48271aa5a5f6af04c",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": {
    "chave": "34eae016a1fd0d10e8ec1eb9004d101996f306be4f142cbbf72a382aea8625d5",
    "produto_id": "ARROZ_5KG",
    "quantidade": 55,
    "custo_estimado": 1017.5,
    "status": "criada",
    "caso_id": "0c688bcd18674de48271aa5a5f6af04c",
    "ja_existia": false
  },
  "termino": "criada"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:28:16 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/0c688bcd18674de48271aa5a5f6af04c-25ee25dd.json`](../logs/demonstracoes/real/20261018-212136-726175/0c688bcd18674de48271aa5a5f6af04c-25ee25dd.json)
>
> chamadas de modelo **4** · ferramentas **4** · recuperações **0** · tokens 4539+3214 · 149 s ativos


**O que ler aqui:**
- a pausa mostra a **ação exata** (`registrar_compra`), os argumentos (produto,
  fornecedor, quantidade 50, custo R$ 925, saldo R$ 1 200), a **consequência** e
  o **prazo** (`expira`, 24 h). `suficiente: true`, porque havia base: o que
  falta é alçada, não informação;
- a aprovação editada registra **55**, não os 50 propostos: R$ 1 017,50, ainda
  dentro do saldo;
- a terceira invocação devolve **a mesma** `Saida` da segunda (a mesma `chave`),
  e o log é do tipo `aprovacao_repetida`. Nenhuma execução nova aconteceu, e o
  banco tem **1** solicitação. O relatório da demonstração registra
  `compras_no_banco: 1` (`demonstracoes.json`, caso `aprovacao`);
- o mesmo fluxo pela CLI, com o operador tentando aprovar e sendo barrado
  (`Somente o perfil simulado gerente pode aprovar/rejeitar.`), está em
  `logs/exemplos-cli/` e no `README.md`. Lá, depois da segunda aprovação, a
  tabela `solicitacoes` tem uma linha e o saldo é R$ 182,50.

---

## 4. O que cada execução custou

| Caso | Entrada | `status` | chamadas de modelo | recuperações (`buscar_documentos`) | ferramentas | tempo ativo |
|---|---|---|---:|---:|---:|---:|
| simples | O sal de 1kg tá no fim, registra a reposição. | `criada` | 4 | 0 | 4 | 127 s |
| divergencia | Acabou refrigerante, pede mais. | `respondido` | 2 | 0 | 1 | 55 s |
| inexistente | Quanto temos de iogurte? | `recusado` | 1 | 0 | 1 | 11 s |
| nao_agir | Quanto temos de arroz? | `respondido` | 2 | 0 | 1 | 26 s |
| fora_corpus | Qual a política de garantia de televisores? | `recusado` | 3 | 1 | 1 | 30 s |
| aprovada | Preciso repor arroz 5kg. | `criada` | 4 | 0 | 4 | 149 s |
| incompleta | Preciso repor. | `esclarecimento` | 1 | 0 | 0 | 27 s |
| ambigua | Como está o açúcar? | `esclarecimento` | 1 | 0 | 1 | 12 s |
| fora_escopo | Qual a capital do Canadá? | `recusado` | 1 | 0 | 0 | 13 s |

Fonte: campo `metricas` de cada log citado acima. `aprovada` mostra os contadores acumulados da pausa e da retomada do
exemplo 6, que são gravados no checkpoint. O tempo de espera do gerente não conta.

**Leituras que a intenção não prevê.** Três execuções a mais, feitas para
separar a decisão do modelo da decisão do router, estão em
`logs/autonomia/` e são discutidas em [`arquitetura.md`](arquitetura.md) §3.
Em duas consultas, o modelo decidiu chamar `consultar_fornecedor` e respondeu
o prazo e o pedido mínimo.

**Recuperações por execução (§4.4):** a busca no corpus aconteceu em **1 de 9**
execuções, a única pergunta de política. Em todas as consultas de estoque o
modelo respondeu com o registro e **não buscou**, e em nenhuma delas a falta da
busca fez a resposta errar. Com etapa fixa, as 8 outras buscas seriam inúteis.
O revisor também não buscou documentos. A consulta independente dele foi
`consultar_fornecedor` no caso simples (conferir o pedido mínimo) e
`consultar_estoque` no caso de aprovação.

### Os casos restantes do §9

**Caso 2 — a divergência:**

**Entrada exata:**

```text
Acabou refrigerante, pede mais.
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "O sistema mostra o contrário do que você viu: há 85 unidades de Refrigerante 2L, acima do mínimo de 20. Confira a gôndola e o depósito; não foi criada compra.",
  "fontes": [
    {
      "id": "estoque:REFRIGERANTE_2L",
      "tipo": "registro",
      "trecho": "{\"id\": \"REFRIGERANTE_2L\", \"nome\": \"Refrigerante 2L\", \"categoria\": \"bebidas\", \"estoque_atual\": 85, \"estoque_minimo\": 20, \"venda_media_diaria\": 5.0, \"preco_unitario\": 7.9, \"fornecedor_id\": \"FORN_B\", \"abaixo_do_minimo\": false}"
    }
  ],
  "suficiente": true,
  "status": "respondido",
  "thread_id": "operador-demo:17c73813fb5b42a0a0bcc72fc77cbd21",
  "caso_id": "4496e53de16a412cb64684851150b2bb",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "respondido"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:24:39 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/4496e53de16a412cb64684851150b2bb-9b0fbc9d.json`](../logs/demonstracoes/real/20261018-212136-726175/4496e53de16a412cb64684851150b2bb-9b0fbc9d.json)
>
> chamadas de modelo **2** · ferramentas **1** · recuperações **0** · tokens 1349+1268 · 55 s ativos


**O que ler aqui:** o operador diz que acabou; o cadastro mostra 85 contra
mínimo 20. A resposta nomeia os dois lados (*"mostra o contrário do que você
viu"*), aponta onde está a diferença provável (gôndola × depósito) e diz que
**não** criou compra. O texto é de código (`validar`), disparado por
`relato_falta=true` da triagem com estoque acima do mínimo.

**Caso 3 — o registro inexistente:**

**Entrada exata:**

```text
Quanto temos de iogurte?
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Produto não encontrado no cadastro. Disponíveis: Arroz 5kg, Açúcar Refinado 1kg, Açúcar Refinado 5kg, Feijão 1kg, Refrigerante 2L, Sal 1kg",
  "fontes": [],
  "suficiente": false,
  "status": "recusado",
  "thread_id": "operador-demo:adefe598db384c7ab414e18dd76dd95f",
  "caso_id": "ffa64a2d8d324b8a90820e6b35cb036a",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "recusado"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:24:50 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/ffa64a2d8d324b8a90820e6b35cb036a-8408825b.json`](../logs/demonstracoes/real/20261018-212136-726175/ffa64a2d8d324b8a90820e6b35cb036a-8408825b.json)
>
> chamadas de modelo **1** · ferramentas **1** · recuperações **0** · tokens 327+250 · 11 s ativos


**O que ler aqui:** recusa útil: diz que o produto não existe e lista o que
existe. **Uma** chamada de modelo (a triagem). O erro de ferramenta
(`produto não encontrado`) é tratado pelo código em `coletar`, de propósito,
para que o modelo não tenha a chance de inventar um estoque. A defesa está em
`arquitetura.md` §3.

**Caso 4 — não dispara a ação principal:**

**Entrada exata:**

```text
Quanto temos de arroz?
```

**Saída completa** (`Saida`, objeto validado):

```json
{
  "resultado": "Temos 12 unidades de Arroz 5kg.",
  "fontes": [
    {
      "id": "estoque:ARROZ_5KG",
      "tipo": "registro",
      "trecho": "{\"id\": \"ARROZ_5KG\", \"nome\": \"Arroz 5kg\", \"categoria\": \"mercearia\", \"estoque_atual\": 12, \"estoque_minimo\": 30, \"venda_media_diaria\": 8.0, \"preco_unitario\": 18.5, \"fornecedor_id\": \"FORN_A\", \"abaixo_do_minimo\": true}"
    }
  ],
  "suficiente": true,
  "status": "respondido",
  "thread_id": "operador-demo:dda049ac4ac64a92b4da6dc8bbf2a479",
  "caso_id": "5f8a81ec2eec4a7489aec9b43d283f83",
  "perguntas": [],
  "aprovacao": null,
  "solicitacao": null,
  "termino": "respondido"
}
```

> commit `6c48749` · `working_tree_modificado: false` · 2026-10-18 21:25:16 · modelo `google/gemma-4-e4b` · MCP `true` · log [`logs/demonstracoes/real/20261018-212136-726175/5f8a81ec2eec4a7489aec9b43d283f83-9d5dbdb0.json`](../logs/demonstracoes/real/20261018-212136-726175/5f8a81ec2eec4a7489aec9b43d283f83-9d5dbdb0.json)
>
> chamadas de modelo **2** · ferramentas **1** · recuperações **0** · tokens 1321+579 · 26 s ativos


**O que ler aqui:** o arroz está **abaixo** do mínimo (12 < 30), e mesmo assim
nenhuma compra foi criada, porque a pergunta é informativa (triagem:
`consulta`). O serviço só aceita preparar compra com `intencao = reposicao`.
A resposta cita o número do registro (`estoque:ARROZ_5KG`), não da memória.
