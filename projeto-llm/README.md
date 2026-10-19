# Assistente de reposição de estoque — Parte 2: o agente de verdade

## Grupo

- Giovanna Paiva Alves
- Matheus Sanchez Duda
- Phelipe Pereira de Souza

## O problema, em uma frase

> O operador de estoque de um supermercado de pequeno porte decide, várias
> vezes por dia, se e quanto pedir de cada produto, cruzando de cabeça estoque
> atual, giro de venda e pedido mínimo do fornecedor — sem nenhum sistema que
> junte essas três informações.

O sistema recebe o pedido em texto livre e devolve um objeto validado
(resultado, fonte, suficiência). Ele consulta o cadastro, as regras de compra
(RAG) e a memória do operador, e registra a solicitação de compra. Acima de
R$ 500, para antes de registrar e espera o gerente. Detalhes em
[`docs/case.md`](docs/case.md). O mapa de cada item da entrega está em
[`docs/entrega.md`](docs/entrega.md).

---

## Como rodar (do zero, em menos de 5 minutos)

Pré-requisitos: **Python 3.12** e o **LM Studio** com o modelo
`google/gemma-4-e4b` carregado e o servidor local ligado (porta 1234).
Qualquer endpoint compatível com a API da OpenAI serve; ver
[`docs/modelos.md`](docs/modelos.md).

```bash
cd projeto-llm
python3.12 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# no .env, preencha:
#   LLM_BASE_URL=http://127.0.0.1:1234/v1
#   LLM_MODELO=google/gemma-4-e4b
#   OPENAI_API_KEY=lm-studio          (o LM Studio aceita qualquer valor)
# os demais podem ficar vazios: os padrões estão em src/config.py

python src/main.py "Quanto temos de arroz?"
```

**Medido do zero** (2026-10-18, cópia limpa exatamente dos arquivos desta entrega → venv → `pip install` → `.env` → primeira pergunta respondida pelo modelo real): **45 s**, com o cache do pip já aquecido nesta máquina. A primeira pergunta, de 30 a 35 s, inclui o download do modelo de embedding. Numa máquina sem cache, a instalação baixa as dependências (onnxruntime, numpy, langgraph, …), e o tempo passa a depender da rede.

- **A primeira execução baixa o modelo de embedding** (cerca de 220 MB,
  `paraphrase-multilingual-MiniLM-L12-v2`, para `runtime/modelos/`). As
  seguintes não baixam nada.
- Bancos, checkpoints e logs operacionais ficam em `runtime/`, criado sozinho.
  O banco simulado é gerado na primeira execução, e não é preciso rodar nada
  antes.
- Sem modelo nenhum, só para conferir a integração: `python src/main.py
  --controlado "Quanto temos de arroz?"`. Esse modo usa um dublê determinístico,
  identificado como tal na saída (`"modo": "controlado"`). Não mede o LLM.

### Os outros comandos

```bash
python -m pytest tests -q                 # 52 testes, sem modelo (dublês)
python conferir_grafo.py                  # nós e arestas do grafo REAL
python src/main.py --demo                 # os 8 cenários com o modelo real -> logs/demonstracoes/real/
python src/avaliar.py --controlado --n 3  # 20 casos rotulados × 3 com dublê (o mesmo do CI)
python src/avaliar_rag.py                 # calibra k/limiar e mede as 10 perguntas do RAG
python src/demonstrar_reducers.py         # o que acontece sem reducer (§7.2)
python src/demonstrar_remocao.py          # remoção com varredura das estruturas (§5.4)
python src/main.py --pendentes            # aprovações pendentes (expira as vencidas)
python src/main.py --perfil gerente --remover-conversa <thread_id>
```

---

## Como usar

### O que a pessoa digita

Texto livre, como falaria com um colega: *"tá acabando o arroz, pede mais"*,
*"como está o feijão?"*, *"posso passar do orçamento?"*. Sem formulário. Os
metadados que não são digitados vêm da linha de comando: `--usuario` (quem
pergunta) e `--thread` (para continuar uma conversa). Sem `--thread`, cada
chamada abre uma conversa nova, e o `thread_id` volta na saída.

```bash
python src/main.py "O sal de 1kg tá no fim, registra a reposição."
python src/main.py                    # modo interativo (mantém a mesma conversa)
python src/main.py --thread <thread_id> "o de 5kg"    # responde a uma pergunta do sistema
```

### O exemplo principal — o caminho feliz, real

O operador digita:

```text
O sal de 1kg tá no fim, registra a reposição.
```

E recebe o objeto inteiro:

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

> Copiado do log [`logs/demonstracoes/real/20261018-212136-726175/52cfa5f150c34124993aa464c3fe3a62-a4192e18.json`](logs/demonstracoes/real/20261018-212136-726175/52cfa5f150c34124993aa464c3fe3a62-a4192e18.json): commit `6c48749`, 2026-10-18 21:23, `google/gemma-4-e4b`, MCP, 127 s ativos, 4 chamadas de modelo.

**Como ler:** `status: criada` é a solicitação registrada, com 50 unidades e
não as 32 da conta 2×20−8, porque o código aplicou o pedido mínimo do
fornecedor. `fontes` traz os registros que sustentam o número, com o trecho
para conferir. `suficiente: true` diz que havia base. Nada foi enviado ao
fornecedor: é uma solicitação interna. A CLI imprime esse objeto dentro de
`{"modo": "real", "saida": ...}`.

Outros exemplos reais, com a recusa e as entradas incompleta, ambígua e fora
do escopo: [`docs/io.md`](docs/io.md).

### Quando ele não sabe, ou não deve, responder

| Situação | `status` | O que vem em `resultado` |
|---|---|---|
| produto não informado (*"Preciso repor."*) | `esclarecimento` | a pergunta, também em `perguntas` |
| nome ambíguo (*"o açúcar"*) | `esclarecimento` | os candidatos (1kg ou 5kg) |
| produto que não existe | `recusado` | a lista do que existe |
| regra que não está no corpus | `recusado` | o que não encontrou; `suficiente: false`, `fontes: []` |
| fora do escopo | `recusado` | o que o sistema faz |
| operador diz que acabou, cadastro diz 85 | `respondido` | os dois lados, e onde conferir; nenhuma compra |

---

## O que acontece quando o grafo para e espera alguém

Compra acima de **R$ 500** (ou que precise de ajuste ao saldo) **não é
registrada**: o grafo pausa num `interrupt`, grava o checkpoint em
`runtime/checkpoints.sqlite` e devolve `aguardando_aprovacao`. Execução real,
pela CLI (`logs/exemplos-cli/`):

**1. O operador pede:**

```bash
python src/main.py "Preciso repor arroz 5kg."
```

```json
{
  "modo": "real",
  "saida": {
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
    "thread_id": "operador-demo:73c23820d6a44568a512188d2bcaab32",
    "caso_id": "69549390f3204c44beabba080c9cdaeb",
    "perguntas": [],
    "aprovacao": {
      "acao": "registrar_compra",
      "caso_id": "69549390f3204c44beabba080c9cdaeb",
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
      "expira": "2026-10-19T21:51:18.961322-03:00"
    },
    "solicitacao": null,
    "termino": "aguardando_aprovacao"
  }
}
```

**2. O operador tenta aprovar, e não pode:**

```bash
python src/main.py --thread <thread_id> --retomar aprovar --quantidade 55
# Somente o perfil simulado gerente pode aprovar/rejeitar.
```

**3. O gerente aprova editando a quantidade para 55:**

```bash
python src/main.py --perfil gerente --thread <thread_id> --retomar aprovar --quantidade 55
```

```json
{
  "modo": "real",
  "saida": {
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
    "thread_id": "operador-demo:73c23820d6a44568a512188d2bcaab32",
    "caso_id": "69549390f3204c44beabba080c9cdaeb",
    "perguntas": [],
    "aprovacao": null,
    "solicitacao": {
      "chave": "3c4a6667435b3b841e6441898a5e237019161b4695114f6491e487a7c15158b3",
      "produto_id": "ARROZ_5KG",
      "quantidade": 55,
      "custo_estimado": 1017.5,
      "status": "criada",
      "caso_id": "69549390f3204c44beabba080c9cdaeb",
      "ja_existia": false
    },
    "termino": "criada"
  }
}
```

**4. A mesma aprovação chega de novo e não duplica nada.** A saída é idêntica à
anterior; o log registra `aprovacao_repetida`, e o banco tem **uma**
solicitação, com o saldo de R$ 1 200 − 1 017,50 = **R$ 182,50**.

- **Respostas aceitas:** `--retomar aprovar`, `--retomar rejeitar`,
  `--retomar aprovar --quantidade N` (editar). Uma edição inválida, abaixo do
  pedido mínimo ou acima do saldo, **volta à pausa** mostrando o erro.
- **Se ninguém responder em 24 h:** a solicitação **expira**, e expirar é
  rejeitar. O silêncio nunca autoriza a compra. O vencimento é verificado ao
  listar (`--pendentes`) ou ao retomar.
- **Outra pergunta na mesma conversa** antes da decisão é recusada: primeiro
  decide-se a pendência.
- A pausa sobrevive ao fim do processo: o gerente pode aprovar em outro
  terminal, horas depois.

Detalhes em [`docs/humano.md`](docs/humano.md).

---

## Como sabemos que funciona

| O quê | Resultado | Onde |
|---|---|---|
| os 8 cenários com o modelo real (os 6 casos do §9 + incompleta + ambígua) | **8/8**, commit `6c48749`, árvore limpa, via MCP | `logs/demonstracoes/real/20261018-212136-726175/` · [`docs/io.md`](docs/io.md) |
| testes automatizados (regra de negócio, contratos, HITL, memória, RAG, reducers, compatibilidade com LM Studio) | **52 passed** | `tests/test_sistema.py` |
| 20 casos rotulados × 3, com dublê (integração, não qualidade do LLM) | **60/60**, nenhuma compra indevida | `python src/avaliar.py --controlado --n 3` |
| RAG: 10 perguntas reservadas | **10/10**; revogado nunca recuperado | `logs/rag/20261018-211035.json` · [`docs/rag.md`](docs/rag.md) |
| ablação de uma frase do prompt de triagem | 22/22 com e sem; **a frase saiu** | `logs/prompts/` · [`docs/prompts.md`](docs/prompts.md) |

---

## Estrutura do repositório

```
README.md              este arquivo
requirements.txt       todas as versões fixadas (langgraph, fastembed, mcp, openai, ...)
.env.example           os nomes das variáveis, sem nenhum valor
conferir_grafo.py      imprime nós e arestas do grafo que src/main.py executa

docs/
  entrega.md           o mapa: item do enunciado -> documento, código, evidência
  case.md              o case, COMPLEMENTADO (§12: o que o domínio ensinou)
  io.md                o contrato de entrada e saída, e os exemplos reais
  prompts.md           o plano de prompt engineering e a regra da frase
  arquitetura.md       o diagrama, as 6 perguntas, a autonomia, o estado e os reducers
  grafo.md             os padrões, quem decide cada aresta, o que o framework não deu
  rag.md               as formas de recuperar, as 10 perguntas, o revogado, o corte e o k
  memoria.md           os dois níveis, as três memórias, a escrita, o esquecimento, a conversa
  humano.md            o ponto de parada, o prazo, a idempotência
  modelos.md           a análise de modelos (Parte 1 + adendo da Parte 2)
  decisoes.md          o histórico das decisões, Partes 1 e 2
  auditoria-parte2.md  o diagnóstico de partida e o checklist final
  fontes.md            tudo que foi consultado, com link

src/
  main.py              a CLI: texto livre, conversa, aprovação, remoção
  grafo.py             o StateGraph: estado, nós, arestas, interrupt, log
  contratos.py         os schemas Pydantic (Saida, Interpretacao, ...)
  modelo.py            o cliente do modelo (tool calling, retries, tetos)
  servico.py           a regra de negócio e a escrita transacional (fronteira de confiança)
  conhecimento.py      RAG (índice, corte, busca vigente) e memória (episódios, fatos)
  servidor_mcp.py      o servidor MCP de estoque; transporte.py é o cliente
  prompts/             os prompts, versionados, carregados em tempo de execução
  avaliar.py · avaliar_rag.py · experimento_prompt.py · demonstrar_*.py   medições
  simulador.py         os dublês de teste (nunca usados como medição de LLM)

dados/                 o corpus (dados/corpus/), as perguntas do RAG, o catálogo simulado
logs/                  as evidências citadas nos docs (ver logs/README.md)
tests/                 os testes
```
