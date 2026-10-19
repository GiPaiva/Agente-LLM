"""§7.2 — o que acontece sem reducer: (1) grafo isolado com ramos paralelos;
(2) o grafo REAL do sistema com `eventos` sem `operator.add`, rodado com dublê."""
import json
import operator
import sys
import tempfile
from pathlib import Path
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.errors import InvalidUpdateError
from config import RAIZ, Config, agora, versao
from grafo import Aplicacao, Estado
from simulador import EmbeddingControlado, ModeloControlado


class Sem(TypedDict): valores: list[str]
class Com(TypedDict): valores: Annotated[list[str], operator.add]


def construir(tipo):
    g = StateGraph(tipo)
    g.add_node('a', lambda s: {'valores': ['a']})
    g.add_node('b', lambda s: {'valores': ['b']})
    for n in ('a', 'b'):
        g.add_edge(START, n); g.add_edge(n, END)
    return g.compile()


# Mesmo Estado do sistema, exceto `eventos` sem reducer: cada nó SOBRESCREVE a trajetória.
EstadoSemReducer = TypedDict('EstadoSemReducer', {**Estado.__annotations__, 'eventos': list[dict]}, total=False)


class AplicacaoSemReducer(Aplicacao):
    estado_tipo = EstadoSemReducer


def trajetoria(classe, pasta, texto):
    with classe(Config(runtime=pasta), ModeloControlado(), EmbeddingControlado(), usar_mcp=False) as app:
        saida = app.iniciar(texto)
        estado = app.grafo.get_state(app._config(saida.thread_id)).values
        return {'status': saida.status, 'n_eventos': len(estado.get('eventos', [])),
                'tipos': [e['tipo'] + ':' + (e.get('ferramenta') or e.get('etapa') or '') for e in estado.get('eventos', [])]}


def demonstrar(texto='Quanto temos de arroz?'):
    try:
        sem = construir(Sem).invoke({'valores': []})
    except InvalidUpdateError as e:
        sem = {'erro': type(e).__name__, 'mensagem': str(e).splitlines()[0]}
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        real = {'entrada': texto, 'com_reducer': trajetoria(Aplicacao, Path(a), texto),
                'sem_reducer': trajetoria(AplicacaoSemReducer, Path(b), texto)}
    return {'versao': versao(), 'quando': agora().isoformat(),
            'paralelo_isolado': {'sem_reducer': sem, 'com_reducer': construir(Com).invoke({'valores': []})},
            'grafo_real_sequencial': real,
            'leitura': 'Paralelo sem reducer: o LangGraph levanta InvalidUpdateError (o framework protege). '
                       'Sequencial sem reducer: nenhum erro, a mesma saída, e a trajetória perde os eventos '
                       'dos nós anteriores — inclusive os que o detector de laço lê.'}


if __name__ == '__main__':
    report = demonstrar()
    pasta = RAIZ / 'logs' / 'reducers'; pasta.mkdir(parents=True, exist_ok=True)
    (pasta / 'demonstracao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'versao'}, ensure_ascii=False, indent=2))
