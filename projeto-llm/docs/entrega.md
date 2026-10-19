# Onde está cada item da Parte 2

> Mapa para quem avalia. Cada linha aponta o documento, o código e a evidência
> (log) do item. O diagnóstico de partida e o checklist final estão em
> [`auditoria-parte2.md`](auditoria-parte2.md).

| Item do enunciado | Documento | Código | Evidência |
|---|---|---|---|
| 0 · complemento do case | [`case.md`](case.md) §12 | — | — |
| 1 · entrada e saída | [`io.md`](io.md) | `src/contratos.py` (`Saida`, `Interpretacao`, `DecisaoHumana`) | `logs/demonstracoes/real/20261018-212136-726175/`, `logs/exemplos-cli/` |
| 2 · plano de prompts + regra da frase | [`prompts.md`](prompts.md) | `src/prompts/*.md`, `Aplicacao._prompt` | `logs/prompts/` |
| 3 · arquitetura, 6 perguntas, autonomia | [`arquitetura.md`](arquitetura.md) §1–4 | `src/grafo.py` | `conferir_grafo.py` (saída em `arquitetura.md` §1.1); `logs/autonomia/` (a decisão que só o modelo toma) |
| 4 · RAG | [`rag.md`](rag.md) | `src/conhecimento.py`, `src/avaliar_rag.py`, `dados/corpus/`, `dados/perguntas-rag.json` | `logs/rag/` |
| 5 · memória e conversa | [`memoria.md`](memoria.md) | `src/conhecimento.py`, `src/grafo.py` (`_mensagens`, `remover_conversa`), `src/prompts/procedimento.md` | `logs/memoria/` |
| 6 · o grafo | [`grafo.md`](grafo.md) + desenho em [`arquitetura.md`](arquitetura.md) §1 | `src/grafo.py` (`_compilar`), `conferir_grafo.py` | saída do `conferir_grafo.py` |
| 7 · o estado e os reducers | [`arquitetura.md`](arquitetura.md) §5 | `src/grafo.py` (`Estado`), `src/demonstrar_reducers.py` | `logs/reducers/demonstracao.json` |
| 8 · human-in-the-loop | [`humano.md`](humano.md) | `src/grafo.py` (`_aprovar`, `retomar`), `src/servico.py` | exemplo 6 de [`io.md`](io.md) |
| 9 · os seis casos | [`io.md`](io.md) §3 | `src/avaliar.py` (`demonstrar`) | `logs/demonstracoes/real/20261018-212136-726175/`, `logs/exemplos-cli/` |
| 10 · o projeto como entrega | [`../README.md`](../README.md) | `requirements.txt`, `.env.example` | — |
| modelos (atualizado) | [`modelos.md`](modelos.md), adendo da Parte 2 | `src/modelo.py` | `logs/diagnostico/sondagem-modelos.txt` |
| decisões da Parte 2 | [`decisoes.md`](decisoes.md), Parte 2 | — | — |
| fontes | [`fontes.md`](fontes.md) | — | — |
