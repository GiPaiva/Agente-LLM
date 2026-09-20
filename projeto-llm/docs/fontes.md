# Fontes consultadas

Tudo o que foi lido ou usado para produzir esta entrega, com link. O que foi
**conferido ao vivo** está marcado; o que não foi, também — a diferença importa,
e o enunciado cobra a honestidade da análise.

---

## 1. Material da disciplina

| Fonte | Para que serviu |
|---|---|
| `trabalhos/00-visao-geral.md` | as regras gerais, as três entregas, os anti-padrões de tema |
| `trabalhos/01-primeira-entrega.md` | o enunciado desta parte — itens 1 a 4 e a tabela de avaliação |
| `notas-aula/aula05-agentes/agente.py` | **a referência de código mais usada**: a separação `Estado` × `mensagens[]`, o `Orcamento` de três tetos, `Termino` como enum, `ErroRecuperavel`/`ErroFatal`, `detectar_laco`, a reancoragem do objetivo e — o mais importante para o desenho final — o dicionário `FASES`, que é a origem do gating (`agente.py:298-306`) |
| `notas-aula/aula05-agentes/README.md` e scripts `00`–`07` | os quatro modos de terminar, o orçamento, o erro como dado, o laço |
| `notas-aula/aula03-prompt/05-versao-de-prompt.py` | **a metodologia do verificador**: teste por propriedade, critério k de N, limiar declarado antes de rodar, e o carimbo `prompt × modelo × parâmetros` no log |
| `notas-aula/aula03-prompt/04-tool-calling.py` e `README.md` | a descrição de ferramenta como prompt ("diga o que faz, quando usar e quando **não** usar") |
| `notas-aula/aula02-modelos-e-parametros/` | por que `temperature=0` ao escolher ferramenta, e por que isso ainda não garante saída idêntica (o que motiva o k de N) |
| `notas-aula/aula01-hello-world/` | o padrão `OpenAI(base_url=..., api_key=...)` com `.env` |
| `notas-aula/requirements.txt` | a convenção de fixar versão; a disciplina usa `openai==3.0.0`, esta entrega usa `3.16.2` |

## 2. Documentos do próprio grupo

| Fonte | Para que serviu |
|---|---|
| `ideia-evolucao/v1.md` | a primeira versão do tema, os usuários e o workflow em 5 passos |
| `ideia-evolucao/v2.md` | o desenho de arquitetura Router + Agente + Avaliador, a tabela de ferramentas com reversibilidade, e **a regra de orçamento de R$ 500** (§5) que virou `LIMITE_SEM_APROVACAO` no código |
| `ideia-evolucao/base-de-conhecimento-v1.md` | o desenho do RAG da Parte 2: o que entra no índice, o corte por cláusula, os metadados |
| `agente-estoque-parte1-esboco/` | o esboço do grupo, e **os logs de 19/09 que revelaram os três defeitos** corrigidos aqui — ver [`decisoes.md`](decisoes.md) |

## 3. Documentação técnica

| Fonte | Conferido ao vivo? |
|---|---|
| SDK `openai` para Python — <https://github.com/openai/openai-python> | sim: versão 3.16.2 instalada e usada |
| Módulo `sqlite3` da biblioteca padrão — <https://docs.python.org/3/library/sqlite3.html> | sim |
| `python-dotenv` — <https://github.com/theskumar/python-dotenv> | sim: versão 1.2.2 |

## 4. Provedores de modelo

Os três candidatos comparados em [`modelos.md`](modelos.md). Todos foram
**executados de verdade** por `src/benchmark.py`; os resultados brutos estão em
`logs/benchmark/`.

| Provedor | Uso | Link | Conferido |
|---|---|---|---|
| **Servidor local compatível com OpenAI** (LM Studio, exposto por túnel Cloudflare) | o modelo escolhido, `google/gemma-4-e4b` | <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/> | sim — `GET /v1/models` e o benchmark inteiro |
| **Groq** | os dois candidatos hospedados, `qwen/qwen3.8-27b` e `openai/gpt-oss-120b` | <https://console.groq.com/docs/openai> (compatibilidade com a API da OpenAI) | sim — `GET /v1/models` e o benchmark inteiro |
| Preços da Groq | a conta de custo do §3.2 | <https://groq.com/pricing> | **não conferido ao vivo** — preço de API muda com frequência. Conferir antes de citar em apresentação |

> **Nota sobre o preço.** A conta de custo de [`modelos.md`](modelos.md) §3.2 usa
> os **tokens medidos** por nós (esses são nossos, e estão nos logs) e os
> **preços publicados** pelo provedor (esses não foram verificados ao vivo, e
> estão marcados como tal na própria tabela). O modelo escolhido roda local e
> custa zero por token, então a decisão não depende desse número — mas a
> comparação depende, e por isso a ressalva está aqui.

## 5. O que **não** foi consultado, e por quê

- **Leaderboards de modelo.** O enunciado é explícito: *"não confiem em
  leaderboard"*. A escolha do modelo saiu da verificação própria de
  `src/benchmark.py`, com os cinco casos do nosso domínio.
- **Dados de supermercado real.** Não tivemos acesso a uma loja parceira no
  prazo. Os dados são simulados e declarados como tal (case §8), e a linha de
  base do ganho é uma **estimativa declarada**, não uma medição (case §5 e §11).
