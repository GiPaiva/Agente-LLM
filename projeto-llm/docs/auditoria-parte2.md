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

- **Modelo: começamos pelo `qwen/qwen3-4b-thinking-2507` e voltamos ao `google/gemma-4-e4b`** da Parte 1. O critério de troca foi escrito antes de rodar: se o qwen falhasse por formato ou tempo, a demonstração iria para o gemma. Ele falhou na etapa de decisão: truncou com 4 095 tokens de raciocínio, e com amostragem levou 58–71 s repetindo uma leitura já feita. Detalhes no adendo de `modelos.md`.
- **`temperature=0`**, apesar de o cartão do modelo sugerir amostragem. Na sondagem do qwen, `0.6` levou o raciocínio da triagem de 782 para 3.234 tokens e de 18 s para 78 s, sem mudar a resposta. O gemma usa `0` desde a Parte 1.
- **Caso 3 (registro inexistente) continua resolvido pelo código**, não pelo modelo. A defesa está em `arquitetura.md` §3.
- **Commits feitos pelo grupo**, não pelo assistente: os logs registram `commit` e `working_tree_modificado`.

## 4. Checklist do enunciado — estado final

| Item | Antes | Depois | Onde | Evidência |
|---|---|---|---|---|
| 0 case complementado | ❌ | ✅ | `docs/case.md` §12 | — |
| 1 entrada = texto; saída validada (resultado, fonte, suficiência); ≥3 exemplos reais com commit, data e log; incompleta, ambígua e fora do escopo | ❌ | ✅ | `docs/io.md`, `src/contratos.py` | 9 execuções reais citadas, commit `6c48749` |
| 2 plano de prompts; prompts em arquivo; regra da frase | ❌ | ✅ | `docs/prompts.md`, `src/prompts/` | `logs/prompts/20261018-214539.json`: 22/22 com e sem; a frase saiu |
| 3 diagrama, 6 perguntas, defesa da autonomia | ⚠️ | ✅ | `docs/arquitetura.md` §1–3 | `n_recuperacoes` por execução (`io.md` §4) |
| 4 RAG: formas, 10 perguntas, corpus, revogado, corte e k, integração no laço | ❌ | ✅ | `docs/rag.md` | `logs/rag/20261018-211035.json`: 10/10; revogado a 0,011 do limiar sem curadoria |
| 5 memória: níveis, fronteira, 3 memórias, escrita idempotente, esquecimento, conversa | ❌ | ✅ | `docs/memoria.md` | `logs/memoria/remocao-real-20261018-214747.json` |
| 6 grafo: desenho × `conferir_grafo.py`, padrões, quem decide, o que o framework não deu, parâmetro | ⚠️ | ✅ | `docs/grafo.md`, `docs/arquitetura.md` §1.1, `conferir_grafo.py` | o padrão de `recursion_limit` é **10007** na versão fixada (não 25), coberto pelo teste canário |
| 7 estado: tabela, reducers, o que acontece sem eles, o que não está no estado | ⚠️ | ✅ | `docs/arquitetura.md` §5 | `logs/reducers/demonstracao.json`: grafo real perde 3 de 4 eventos sem erro |
| 8 HITL: interrupt + checkpointer + resume, aprovar/rejeitar/editar, prazo, idempotência | ❌ | ✅ | `docs/humano.md` | `io.md` exemplo 6; `logs/exemplos-cli/` |
| 9 seis casos com log | ❌ | ✅ | `docs/io.md` §3–4 | `logs/demonstracoes/real/20261018-212136-726175/`: 8/8 |
| 10 README (rodar em <5 min, usar, exemplo, pausa), requirements fixado, `.env.example` sem valores | ⚠️ | ✅ | `README.md` | do clone limpo à 1ª resposta real em 43 s, com o cache do pip aquecido |

Validação final: `pytest` **52 passed**; `avaliar.py --controlado --n 3`
**60/60**, sem compra indevida; `conferir_grafo.py` igual ao desenho.

## 5. Riscos residuais

| Risco | Por que fica | Mitigação declarada |
|---|---|---|
| **o modelo é pequeno e local** (4B) | escolha de política de dados (`modelos.md` §3.4) | contratos estritos com uma correção, falha fechada, e o serviço revalida tudo; o pior erro do modelo é deixar de comprar, nunca comprar errado |
| **N=1 por cenário com o modelo real** | cada cenário leva de 11 a 149 s; a suíte de 20 casos × 3 com o modelo real não foi refeita na Parte 2 | a Parte 1 mediu 57/60 com o mesmo modelo, e a integração está coberta por 60/60 com dublê. Próximo passo: `python src/avaliar.py --n 3` |
| **fluxos com compra levam 2–2,5 min** | 4 chamadas de modelo, a revisão incluída | `--um-agente` desliga o revisor (o portão em código continua); a troca para modelo hospedado custa três variáveis de ambiente |
| **sem autenticação real do gerente** | o perfil é um argumento de CLI | declarado em `humano.md` §1 |
| **prazo verificado só na leitura** | não há agendador | expirada nunca vira aprovada (`humano.md` §4) |
| **checkpointer SQLite local** | um arquivo, uma máquina | sobrevive ao processo; não serve para vários servidores |
| **remoção por conversa, não por titular**; dado derivado em outra conversa sobrevive | medido em `demonstrar_remocao.py` | declarado em `memoria.md` §5 |
| **LM Studio local precisa estar ligado** | é o modelo escolhido | o modo `--controlado` roda a integração sem modelo, marcado como tal |
