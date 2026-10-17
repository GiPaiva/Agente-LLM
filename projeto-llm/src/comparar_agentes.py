"""Comparação pareada de um agente e reposição+revisão nos mesmos casos."""
import argparse
import json
from avaliar import rodar_suite
from config import RAIZ, agora, versao

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--controlado',action='store_true')
    p.add_argument('--n',type=int,default=3)
    p.add_argument('--mcp',action='store_true')
    a=p.parse_args()
    report={'versao':versao(),'modo':'controlado' if a.controlado else 'real','configuracoes':[]}
    for multi in (False,True):
        r=rodar_suite(a.n,controlado=a.controlado,multi=multi,mcp=a.mcp)
        report['configuracoes'].append({'multiagente':multi,'acertos':r['acertos'],'total':r['total'],
            'violacoes':r['violacoes'],'chamadas_modelo':sum(c['metricas']['n_modelo'] for c in r['casos']),
            'processamento_s':sum(c['metricas']['processamento_s'] for c in r['casos'])})
    pasta=RAIZ/'logs'/'comparacao-agentes';pasta.mkdir(exist_ok=True)
    (pasta/(agora().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
