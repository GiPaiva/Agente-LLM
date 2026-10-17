"""Ablação real: remove uma frase e compara o mesmo conjunto, sem mudar o critério."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from config import RAIZ, Config, agora, versao
from avaliar import executar_caso, CASOS
from grafo import Aplicacao

FRASE='Pergunta apenas informativa é consulta, mesmo com estoque baixo.'


def main():
    if not os.environ.get('LLM_BASE_URL') or not os.environ.get('LLM_MODELO'):
        print('PENDENTE: ablação exige modelo real configurado; nenhum efeito de prompt foi medido.')
        return 2
    original=Aplicacao._prompt
    rows=[]
    for variante in ('original','sem_frase'):
        def ler(self,nome):
            texto=original(self,nome)
            return texto.replace(FRASE,'') if variante=='sem_frase' and nome=='triagem' else texto
        with patch.object(Aplicacao,'_prompt',ler):
            for caso in CASOS:
                for _ in range(3):
                    rows.append({'variante':variante,**executar_caso(caso,Config.ambiente(),multi=False)})
    pasta=RAIZ/'logs'/'prompts';pasta.mkdir(exist_ok=True)
    (pasta/(agora().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(
        {'versao':versao(),'frase_removida':FRASE,'decisao':'frase mantida até revisão dos resultados',
         'casos':rows},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())
