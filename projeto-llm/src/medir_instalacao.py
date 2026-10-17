"""Mede uma venv nova, dependências e download frio dos embeddings locais."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from config import RAIZ, agora, versao

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='estoque-instalacao-') as tmp:
        pasta=Path(tmp)
        inicio=time.monotonic()
        subprocess.run([sys.executable,'-m','venv',str(pasta/'venv')],check=True)
        py=pasta/'venv'/'bin'/'python'
        instalacao=time.monotonic()
        subprocess.run([str(py),'-m','pip','install','--no-cache-dir','-r',str(RAIZ/'requirements.txt')],
                       check=True,stdout=subprocess.DEVNULL)
        deps=time.monotonic()
        codigo='''import sys
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from config import Config
from conhecimento import Conhecimento
k=Conhecimento(Config(runtime=Path(sys.argv[2]),cache_modelos=Path(sys.argv[3])))
k.indexar()
assert k.buscar_documentos('Qual valor exige aprovação do gerente?')
'''
        subprocess.run([str(py),'-c',codigo,str(RAIZ/'src'),str(pasta/'runtime'),str(pasta/'modelos')],check=True)
        fim=time.monotonic()
        report={'quando':agora().isoformat(),'versao':versao(),'python':sys.version,'venv_s':instalacao-inicio,
                'dependencias_s':deps-instalacao,'embedding_e_indice_s':fim-deps,'total_s':fim-inicio,
                'cache_pip':False,'cache_embedding':False,'endpoint_LLM':'não configurado; atendimento real não medido',
                'limite_300s_preparacao':fim-inicio<300,
                'limite_300s_entrega_completa':'pendente: falta endpoint e execução LLM real'}
        destino=RAIZ/'logs'/'instalacao';destino.mkdir(exist_ok=True)
        path=destino/'preparacao.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({k:v for k,v in report.items() if k!='versao'},ensure_ascii=False,indent=2))
