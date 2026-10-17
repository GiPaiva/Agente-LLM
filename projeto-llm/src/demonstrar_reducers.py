"""Experimento isolado do framework; não é o grafo de produto inspecionado."""
import json
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.errors import InvalidUpdateError
from config import RAIZ, agora, versao

class Sem(TypedDict): valores:list[str]
class Com(TypedDict): valores:Annotated[list[str],operator.add]


def construir(tipo):
    g=StateGraph(tipo)
    g.add_node('a',lambda s:{'valores':['a']})
    g.add_node('b',lambda s:{'valores':['b']})
    for n in ('a','b'):
        g.add_edge(START,n);g.add_edge(n,END)
    return g.compile()


if __name__=='__main__':
    try:
        sem=construir(Sem).invoke({'valores':[]})
    except InvalidUpdateError as e:
        sem={'erro':type(e).__name__,'mensagem':str(e)}
    report={'versao':versao(),'quando':agora().isoformat(),'sem_reducer':sem,
            'com_reducer':construir(Com).invoke({'valores':[]})}
    pasta=RAIZ/'logs'/'reducers';pasta.mkdir(exist_ok=True)
    (pasta/'demonstracao.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
