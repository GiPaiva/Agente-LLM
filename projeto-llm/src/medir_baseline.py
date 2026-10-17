"""Cronometra DEZ tarefas realizadas por uma pessoa; não fabrica medidas humanas."""
import argparse
import json
import time
from config import RAIZ, agora, versao

TAREFAS=[
 'Consultar estoque de arroz 5kg.', 'Calcular quantidade e custo de reposição de arroz.',
 'Verificar se arroz exige aprovação.', 'Consultar estoque de refrigerante 2L.',
 'Decidir sobre compra quando há gôndola vazia e 85 refrigerantes no banco.',
 'Consultar estoque de feijão 1kg.', 'Desambiguar uma consulta sobre açúcar.',
 'Calcular reposição e custo de sal 1kg.', 'Identificar pedido mínimo e prazo do Fornecedor A.',
 'Consultar se aprovação humana permite ultrapassar o orçamento.'
]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--participante',required=True,help='identificador simulado, sem nome pessoal')
    p.add_argument('--fase',choices=['manual','assistente'],required=True)
    a=p.parse_args()
    print('Use dados/referencia-manual.md como referência dos números e dados/corpus/ para as regras.')
    print('Mesmas tarefas nas duas fases. Na fase assistente, registre a resposta e a espera humana separadamente.')
    rows=[]
    for i,tarefa in enumerate(TAREFAS,1):
        input(f'{i}/10 {tarefa}\nEnter inicia o cronômetro. ')
        inicio=time.monotonic()
        resposta=input('Resolva a tarefa e digite a resposta: ')
        tempo=time.monotonic()-inicio
        rows.append({'tarefa':tarefa,'tempo_s':round(tempo,3),'resposta':resposta,
                     'correta':input('Conferida com o gabarito? [s/n] ').strip().lower()=='s'})
    pasta=RAIZ/'logs'/'baseline';pasta.mkdir(exist_ok=True)
    path=pasta/(a.fase+'-'+agora().strftime('%Y%m%d-%H%M%S')+'.json')
    path.write_text(json.dumps({'versao':versao(),'quando':agora().isoformat(),'ambiente':'simulado',
        'participante':a.participante,'fase':a.fase,'tarefas':rows},ensure_ascii=False,indent=2))
    print(path)


if __name__=='__main__': main()
