"""Escolhe parâmetros na calibração; só depois mede as dez perguntas reservadas."""
import argparse
import json
import tempfile
from pathlib import Path
from dataclasses import replace
from config import RAIZ, Config, agora, versao
from conhecimento import Conhecimento
from servico import Servico


def avaliar(k, perguntas, n, limiar):
    rows=[]
    for p in perguntas:
        resultados=k.buscar_documentos(p['pergunta'],k=n,limiar=limiar)
        fontes=[r['id'] for r in resultados]
        ok=any(f.startswith(prefix) for f in fontes for prefix in p['fontes']) if p['fontes'] else not fontes
        rows.append({'pergunta':p['pergunta'],'fontes':fontes,'scores':[r['score'] for r in resultados],'ok':ok})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--indexar',action='store_true')
    args=parser.parse_args()
    config=Config.ambiente()
    k=Conhecimento(config)
    k.indexar()
    data=json.loads((RAIZ/'dados'/'perguntas-rag.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        alternativo=Conhecimento(replace(config,runtime=Path(tmp),corte='caracteres'),k.embedding)
        cortes={}
        for nome,indice in [('estrutura',k),('caracteres',alternativo)]:
            comparacao=avaliar(indice,data['calibracao'],3,0)
            with indice.conectar() as con:
                volume=con.execute('SELECT COUNT(*) FROM trechos').fetchone()[0]
            cortes[nome]={'acertos_fontes_top3_sem_portao':sum(r['ok'] for r in comparacao),
                          'trechos':volume,'casos':comparacao}
    ensaios=[]
    for n in (1,3,5):
        for limiar in (0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60):
            rows=avaliar(k,data['calibracao'],n,limiar)
            falsos=sum(not r['ok'] for r,p in zip(rows,data['calibracao']) if not p['fontes'])
            ensaios.append({'k':n,'limiar':limiar,'acertos':sum(r['ok'] for r in rows),'falsos_positivos':falsos,'casos':rows})
    # Prioridade: recusar o negativo de calibração, acertar fontes, menor k, maior corte.
    escolhido=max(ensaios,key=lambda x:(-x['falsos_positivos'],x['acertos'],-x['k'],x['limiar']))
    parametros={k:escolhido[k] for k in ('k','limiar')}
    parametros.update(calibrado=True,embedding=config.embedding,quando=agora().isoformat(),
                      dataset='dados/perguntas-rag.json:calibracao')
    (config.runtime/'rag-parametros.json').write_text(json.dumps(parametros,indent=2))
    (RAIZ/'dados'/'rag-config.json').write_text(json.dumps(parametros,indent=2))
    k.parametros=parametros
    docs=[p for p in data['avaliacao'] if p['forma']=='busca vetorial']
    avaliacao=avaliar(k,docs,escolhido['k'],escolhido['limiar'])
    with tempfile.TemporaryDirectory() as tmp:
        s=Servico(Path(tmp))
        for p in data['avaliacao']:
            if p['forma']=='consulta estruturada':
                r=getattr(s,p['ferramenta'])(**p['argumentos'])
                avaliacao.append({'pergunta':p['pergunta'],'forma':p['forma'],'resultado':r,
                                  'ok':r[p['campo']]==p['esperado']})
    with k.conectar() as con:
        revogados=[dict(r) for r in con.execute("SELECT id,texto FROM trechos WHERE doc='POL-V1'")]
    report={'quando':agora().isoformat(),'versao':versao(),'modo':'embedding_local_real_sem_LLM',
            'parametros':parametros,'cortes':cortes,'calibracao':ensaios,'avaliacao':avaliacao,
            'acertos':sum(r['ok'] for r in avaliacao),'total':len(avaliacao),
            'documentos_revogados_indexados_mas_filtrados':revogados}
    destino=RAIZ/'logs'/'rag';destino.mkdir(exist_ok=True)
    path=destino/(agora().strftime('%Y%m%d-%H%M%S')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'parametros':parametros,'acertos':report['acertos'],'total':report['total'],'relatorio':str(path)},ensure_ascii=False,indent=2))
    return 0 if report['acertos']==report['total'] else 1


if __name__=='__main__': raise SystemExit(main())
