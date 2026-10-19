# O que há em `logs/`

## Parte 2 — as evidências citadas nos documentos

Todo log de execução grava `versao.commit`, `versao.working_tree_modificado`, o
sha256 de cada arquivo de `src/` e `dados/` (inclusive cada prompt), o modelo,
os parâmetros em uso e a trajetória (`eventos`). Salvo indicação, as
evidências abaixo foram geradas no **commit `6c48749` com a árvore limpa**,
com `google/gemma-4-e4b` no LM Studio local.

| Pasta | O que é | Citado em | Como reproduzir |
|---|---|---|---|
| `demonstracoes/real/20261018-212136-726175/` | **os 8 cenários** (os 6 casos do §9 + incompleta + ambígua), via MCP, 8/8; `demonstracoes.json` resume os checks | `docs/io.md`, `README.md` | `python src/main.py --demo` |
| `demonstracoes/real/20261018-205831-280653/` | o **ensaio** anterior ao congelamento (6/8): as duas falhas, revisor citando `evidencias:<id>` e triagem com `produto: null`, que viraram as decisões 12 e 13. Gerado antes do commit `6c48749` | `docs/decisoes.md` | — (histórico) |
| `exemplos-cli/` | fora do escopo e o fluxo de aprovação **pela CLI**: pausa, operador barrado, gerente edita, 2ª aprovação. `saida-cli-*.json` é a saída de tela | `README.md`, `docs/io.md`, `docs/humano.md` | os comandos do README |
| `rag/20261018-211035.json` | calibração de k/limiar, os dois cortes, a avaliação 10/10 e o revogado sem filtro. Gerado com o código de `6c48749`, minutos antes do commit | `docs/rag.md` | `python src/avaliar_rag.py` |
| `prompts/20261018-214539.json` | a regra da frase: triagem com e sem a frase, 22/22 nas duas | `docs/prompts.md` | ver `docs/prompts.md` §3 |
| `memoria/remocao-real-20261018-214747.json` | remoção com varredura de todas as estruturas | `docs/memoria.md` §5 | `python src/demonstrar_remocao.py` |
| `reducers/demonstracao.json` | o que acontece sem reducer: paralelo (erro) × grafo real (perda silenciosa) | `docs/arquitetura.md` §5.2 | `python src/demonstrar_reducers.py` |
| `autonomia/` | três pedidos em que a leitura necessária não sai da intenção (o modelo escolhe `consultar_fornecedor`, ou deixa de buscar a exceção). Gerados depois do congelamento (`working_tree_modificado: true`; o `sha256_fontes` identifica o código) | `docs/arquitetura.md` §3, `docs/rag.md` §5 | `python src/main.py "<pedido>"` |
| `diagnostico/` | a falha do `tool_choice` nomeado antes da correção, a sondagem qwen × gemma, e o padrão de `recursion_limit` da lib (10007) | `docs/auditoria-parte2.md`, `docs/modelos.md` | — (histórico) |

Logs novos ficam locais por padrão (`logs/.gitignore`). Para publicar uma
evidência, libere o caminho exato no `.gitignore` e cite-a num documento.

---

## Parte 1 — a evidência da primeira entrega

As pastas abaixo são da Parte 1, do laço à mão anterior ao LangGraph. Elas
sustentam `docs/modelos.md` §3 e `docs/decisoes.md`, decisões 1–9. O formato
de log descrito daqui em diante é o da Parte 1.

Toda execução do agente grava a **trajetória completa** (item 4.1 da entrega):
ferramenta, argumentos, resultado, erro de cada passo, o motivo do término e o
carimbo `prompt × modelo × parâmetros`.

| Pasta | O que é | Como reproduzir |
|---|---|---|
| `demo/` | **as 4 execuções demonstradas** do item 4.5, uma por família obrigatória, mais a saída de tela em `demo.txt` | `python src/main.py --demo` |
| `avaliacao/` | as **60 medições** (20 casos × 3 execuções) por trás do placar de 57/60, mais o `relatorio-*.json` que as resume e a saída em `suite-n3-gemma.txt` | `python src/avaliar.py --n 3` |
| `benchmark/` | as **30 medições** (3 modelos × 5 casos × 2 execuções) do item 3.3, mais `comparacao-*.json` e a saída em `comparacao.txt` | `python src/benchmark.py --n 2` |

Logs de rodadas superadas foram removidos de propósito: um log gravado com o
verificador ainda com bug, ou com outro conjunto de parâmetros, não é evidência
do número publicado — é ruído que o contradiz.

## Como ler um log

```jsonc
{
  "rotulo": "caso-1a",
  "carimbo": {                    // a unidade versionada (aula 03)
    "prompt": "sistema-v3",
    "modelo": "google/gemma-4-e4b",
    "parametros": {"temperature": 0, "max_tokens": 800}
  },
  "termino": "respondeu",         // respondeu · orcamento_esgotado ·
  "motivo": null,                 // laco_detectado · truncado · erro_fatal
  "gating": {                     // a garantia de arquitetura (item 2.7)
    "escrita_foi_oferecida": true,        // a ferramenta de escrita chegou
    "escrita_liberada_no_passo": 0        // a ser DECLARADA ao modelo?
  },
  "passos": [ /* ferramenta, argumentos, resultado, erro */ ]
}
```

O campo que mais importa para a avaliação é **`gating.escrita_foi_oferecida`**.
Nos casos das famílias 2, 3, 4 e 5 ele é `false`: `criar_solicitacao_compra`
nunca chegou a ser declarada ao modelo. A diferença entre *"o modelo não
chamou"* e *"o modelo não podia chamar"* é a diferença entre sorte e desenho —
e é ela que sustenta o critério assimétrico do item 2.7.

Conferência rápida nos 4 logs da demonstração:

| caso | família | escrita oferecida? |
|---|---|---|
| `1a` | simples | **sim** — o estoque estava abaixo do mínimo |
| `2a` | divergência | não |
| `3a` | inexistente | não |
| `4a` | não comprar | não |
