# Auditoria da Parte 2 — diagnóstico e checklist

> Documento de trabalho do grupo. Registra o estado do repositório **antes** da
> consolidação da Parte 2, o que foi corrigido e o que ficou como risco. A
> versão final do checklist está na §4.

## 1. Ponto de partida (commit `28228b6`, 2026-10-18)

O commit `1c56c89` (2026-10-16) integrou o código da Parte 2: `StateGraph` com
estado tipado e reducers, `SqliteSaver`, `interrupt` + `Command(resume=...)`,
aprovação editável, idempotência por `caso_id`, prazo de 24 h, RAG como
ferramenta (`buscar_documentos`) com documento revogado filtrado, as três
memórias, decaimento, remoção com cobertura, detector de laço, tetos e motivo
de término, revisor independente, MCP e 41 testes. A própria mensagem do commit
avisava: *"Execuções com modelo local real permanecem pendentes."*

Linha de base medida nesta auditoria:

| Verificação | Resultado |
|---|---|
| `pytest tests -q` | 41 passed |
| `python src/avaliar.py --controlado --n 3` | 60/60, sem compra indevida (dublê, não mede LLM) |
| `python src/main.py --sem-mcp "Quanto temos de arroz?"` (modelo real) | **falha** — `API recusou a configuração/cota (400)`, `termino=erro_fatal` |

O log da falha está em `logs/diagnostico/antes-correcao-tool-choice.json`.

## 2. Achados

| # | Prioridade | Achado | Evidência |
|---|---|---|---|
| A1 | P0 | O LM Studio só aceita `tool_choice` em `none`, `auto` e `required`. A forma nomeada (`{"type":"function",...}`), usada em `src/modelo.py` na triagem, devolve HTTP 400. **Toda** execução real morria na primeira chamada. | sondagem por `curl`; log acima |
| A2 | P0 | `max_tokens=800` era fixo em `src/modelo.py`. O `qwen3-4b-thinking` gasta 615–782 tokens **só raciocinando** na triagem (`temperature=0`), então a saída trunca (`finish_reason=length`). | sondagem |
| A3 | P1 | O `timeout=30 s` e o teto de 300 s por execução não cabem num modelo que leva 14–25 s por chamada e faz de 4 a 6 chamadas por caso. | sondagem |
| A4 | P1 | `_log` gravava `"max_tokens": 800` fixo, ou seja, o log mentia sobre o parâmetro em uso. | `src/grafo.py` |
| A5 | P1 | A demonstração de reducer usava só um grafo isolado e mostrava `InvalidUpdateError`. O framework **protege** o caso paralelo, mas a perda silenciosa num grafo sequencial não estava demonstrada. | `src/demonstrar_reducers.py` |
| A6 | P1 | `experimento_prompt.py` roda 20 casos × 3 × 2 grafos completos, o que dá horas no modelo local. Na prática, a ablação nunca rodaria. | `src/experimento_prompt.py` |
| A7 | P1 | `logs/.gitignore` liberava arquivos que não existem neste clone e citava um `docs/entrega.md` também inexistente. | `logs/.gitignore` |
| A8 | P1 | `README.md` e `docs/arquitetura.md` descrevem o laço à mão da Parte 1 (`agente.py`, `criar_solicitacao_compra`), que não existe mais. | — |
| A9 | P2 | O `.env` tinha só os nomes das variáveis, sem valores. | — |
| A10 | P2 | `dados/rag-config.json` (k=5, limiar 0,45) não tinha log versionado que o sustentasse. | — |

## 3. Decisões tomadas nesta rodada

- **Modelo principal: `qwen/qwen3-4b-thinking-2507`**, com o `google/gemma-4-e4b` da Parte 1 como alternativa (ver `modelos.md`, adendo da Parte 2). Critério de troca, escrito antes de rodar: se o qwen falhar em 2 ou mais dos 8 cenários por formato ou tempo, a demonstração vai para o gemma.
- **`temperature=0`**, apesar de o cartão do modelo sugerir amostragem. Na sondagem, `0.6` levou o raciocínio de 782 para 3.234 tokens e de 18 s para 78 s, sem mudar a resposta.
- **Caso 3 (registro inexistente) continua resolvido pelo código**, não pelo modelo. A defesa está em `arquitetura.md` §3.2.
- **Commits feitos pelo grupo**, não pelo assistente: os logs registram `commit` e `working_tree_modificado`.

## 4. Checklist do enunciado

Preenchido ao final da rodada — ver §4 atualizada abaixo.

| Item | Antes | Depois | Onde |
|---|---|---|---|
| 0 case complementado | ❌ | | `docs/case.md` §12 |
| 1 entrada/saída + exemplos reais | ❌ | | `docs/io.md` |
| 2 plano de prompts + frase | ❌ | | `docs/prompts.md` |
| 3 arquitetura | ⚠️ | | `docs/arquitetura.md` |
| 4 RAG | ❌ | | `docs/rag.md` |
| 5 memória | ❌ | | `docs/memoria.md` |
| 6 grafo + `conferir_grafo.py` | ⚠️ | | `docs/grafo.md` |
| 7 estado + reducers | ⚠️ | | `docs/arquitetura.md` §5 |
| 8 human-in-the-loop | ❌ | | `docs/humano.md` |
| 9 seis casos com log | ❌ | | `logs/parte2/` |
| 10 README, requirements, .env.example | ⚠️ | | raiz |
