# O que há em `logs/`

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
