"""Cinco casos nos candidatos configurados; nenhum resultado histórico é reutilizado."""
import argparse
import json
import os
from openai import OpenAI
from avaliar import executar_caso, CASOS
from config import RAIZ, Config, agora, versao
from modelo import Modelo


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--n',type=int,default=2)
    a=parser.parse_args()
    candidatos=[('local','BENCH_LOCAL_BASE_URL','BENCH_LOCAL_MODELO','BENCH_LOCAL_API_KEY'),
                ('medio','BENCH_GROQ_BASE_URL','BENCH_GROQ_MODELO_MEDIO','BENCH_GROQ_API_KEY'),
                ('grande','BENCH_GROQ_BASE_URL','BENCH_GROQ_MODELO_GRANDE','BENCH_GROQ_API_KEY')]
    rows=[]
    for rotulo,url,nome,key in candidatos:
        if not os.environ.get(url) or not os.environ.get(nome):
            print('PENDENTE:',rotulo,'sem configuração'); continue
        factory=lambda cfg,u=os.environ[url],m=os.environ[nome],k=os.environ.get(key) or 'local': Modelo(
            cfg,OpenAI(base_url=u,api_key=k,max_retries=0,timeout=cfg.timeout),m)
        for caso in [c for c in CASOS if c['id'] in ('1a','2a','3a','4a','5a')]:
            for _ in range(a.n):
                rows.append({'candidato':rotulo,**executar_caso(caso,Config.ambiente(),multi=False,modelo_factory=factory)})
    if not rows: return 2
    pasta=RAIZ/'logs'/'benchmark-integrado';pasta.mkdir(exist_ok=True)
    path=pasta/(agora().strftime('%Y%m%d-%H%M%S')+'.json')
    path.write_text(json.dumps({'versao':versao(),'casos':rows},ensure_ascii=False,indent=2))
    print(path)
    return 0


if __name__=='__main__': raise SystemExit(main())
