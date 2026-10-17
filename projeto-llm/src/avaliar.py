"""Evals da versão integrada. Cada caso usa banco e checkpoint temporários."""
import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from config import RAIZ, Config, agora, versao
from grafo import Aplicacao
from modelo import Modelo
from simulador import ModeloControlado, EmbeddingControlado
sys.path.insert(0,str(RAIZ/'dados'))
from casos_rotulados import CASOS

LIMIAR=0.85


def checar(saida, caso, primeira, total_compras):
    familia=caso['familia']
    checks={'objeto_validado': bool(saida.resultado)}
    if familia=='1_simples':
        checks.update(compra=saida.status=='criada' and total_compras==1,
                      quantidade=bool(saida.solicitacao) and saida.solicitacao['quantidade']>=caso['espera']['quantidade_minima_pedida'],
                      pausa_ou_automatico=primeira.status in ('criada','aguardando_aprovacao'))
    elif familia=='2_divergencia':
        checks.update(sem_compra=total_compras==0, respondeu=saida.status=='respondido',
                      divergencia=any(t in saida.resultado.lower() for t in ('contrário','diverg','contradiz')),
                      estoque=all(str(n) in saida.resultado for n in caso['espera']['cita_numeros']))
    elif familia=='3_inexistente':
        checks.update(sem_compra=total_compras==0,recusa=saida.status=='recusado',sem_estoque_inventado=not saida.fontes)
    elif familia=='4_nao_comprar':
        checks.update(sem_compra=total_compras==0,respondeu=saida.status=='respondido')
    elif familia=='5_ambiguidade':
        checks.update(sem_compra=total_compras==0,perguntou=saida.status=='esclarecimento' and bool(saida.perguntas))
    return checks


def executar_caso(caso, config, controlado=False, multi=True, mcp=False, modelo_factory=None, destino=None, editar=False):
    with tempfile.TemporaryDirectory(prefix='estoque-eval-') as tmp:
        cfg=replace(config,runtime=Path(tmp))
        modelo=modelo_factory(cfg) if modelo_factory else ModeloControlado() if controlado else Modelo(cfg)
        embed=EmbeddingControlado() if controlado else None
        with Aplicacao(cfg,modelo,embed,multi=multi,usar_mcp=mcp) as app:
            primeira=app.iniciar(caso['pergunta'])
            saida=primeira
            repetida=None
            if saida.status=='aguardando_aprovacao':
                decisao={'acao':'aprovar','quantidade':55 if editar else None}
                saida=app.retomar(saida.thread_id,decisao,'gerente')
                repetida=app.retomar(saida.thread_id,decisao,'gerente')
            with app.servico.conectar() as c:
                total=c.execute('SELECT COUNT(*) FROM solicitacoes').fetchone()[0]
            checks=checar(saida,caso,primeira,total) if 'familia' in caso else {
                'status': primeira.status==caso['status'], 'sem_compra_indevida':total<=1,
                'duplicacao':repetida is None or (repetida==saida and total==1)}
            estado=app.grafo.get_state(app._config(saida.thread_id)).values
            eventos=[e for e in estado.get('eventos',[]) if e['caso_id']==saida.caso_id]
            if primeira.aprovacao and editar:
                checks['aprovou_editando']=saida.solicitacao and saida.solicitacao['quantidade']==55
            if destino:
                destino.mkdir(parents=True,exist_ok=True)
                for log in (cfg.runtime/'logs').glob('*.json'):
                    shutil.copy2(log,destino/log.name)
            return {'caso':caso['id'],'entrada':caso['pergunta'],'primeira_saida':primeira.model_dump(),
                    'saida':saida.model_dump(),'aprovacao_repetida':repetida.model_dump() if repetida else None,
                    'checks':checks,'acertou':all(checks.values()),'compras_no_banco':total,
                    'metricas':app._contadores(estado),'eventos_por_agente':{
                        n:sum(e['agente']==n for e in eventos) for n in ('reposicao','revisao','codigo')}}


def rodar_suite(n=3,familia=None,controlado=False,multi=True,mcp=False,config=None,modelo_factory=None):
    config=config or Config.ambiente()
    if not controlado and modelo_factory is None and (not os.environ.get('LLM_BASE_URL') or not os.environ.get('LLM_MODELO')):
        raise RuntimeError('Eval real pendente: configure LLM_BASE_URL e LLM_MODELO. Não será substituída por dublê.')
    if n<1: raise ValueError('--n deve ser positivo')
    casos=[c for c in CASOS if not familia or c['familia'].startswith(familia)]
    if not casos: raise ValueError('Família sem casos')
    pasta=RAIZ/'logs'/'integrado'/('controlado' if controlado else 'real')/agora().strftime('%Y%m%d-%H%M%S-%f')
    rows=[executar_caso(c,config,controlado,multi,mcp,modelo_factory,pasta) for c in casos for _ in range(n)]
    violacoes=[r['caso'] for r in rows if not r['caso'].startswith('1') and r['compras_no_banco']]
    acertos=sum(r['acertou'] for r in rows)
    report={'quando':agora().isoformat(),'modo':'controlado' if controlado else 'real','versao':versao(),
            'multiagente':multi,'mcp':mcp,'acertos':acertos,'total':len(rows),'limiar':LIMIAR,
            'violacoes':violacoes,'verificacoes_passaram':acertos/len(rows)>=LIMIAR and not violacoes,'casos':rows,
            'interpretacao':'Integração com dublê; não mede qualidade do LLM.' if controlado else 'Execuções reais do modelo configurado.'}
    pasta.mkdir(parents=True,exist_ok=True)
    (pasta/'relatorio.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('casos','versao')},ensure_ascii=False,indent=2))
    print('Relatório:',pasta/'relatorio.json')
    return report


def demonstrar(config,controlado=False,multi=True,mcp=False):
    if not controlado and (not os.environ.get('LLM_BASE_URL') or not os.environ.get('LLM_MODELO')):
        raise RuntimeError('Demonstração real pendente: configure o endpoint local no .env.')
    casos=[{'id':'simples','pergunta':'O sal de 1kg tá no fim, registra a reposição.','status':'criada'},
           {'id':'divergencia','pergunta':'Acabou refrigerante, pede mais.','status':'respondido'},
           {'id':'inexistente','pergunta':'Quanto temos de iogurte?','status':'recusado'},
           {'id':'nao_agir','pergunta':'Quanto temos de arroz?','status':'respondido'},
           {'id':'fora_corpus','pergunta':'Qual a política de garantia de televisores?','status':'recusado'},
           {'id':'aprovacao','pergunta':'Preciso repor arroz 5kg.','status':'aguardando_aprovacao'},
           {'id':'incompleta','pergunta':'Preciso repor.','status':'esclarecimento'},
           {'id':'ambigua','pergunta':'Como está o açúcar?','status':'esclarecimento'}]
    pasta=RAIZ/'logs'/'demonstracoes'/('controlado' if controlado else 'real')/agora().strftime('%Y%m%d-%H%M%S-%f')
    rows=[executar_caso(c,config,controlado,multi,mcp,destino=pasta,editar=c['id']=='aprovacao') for c in casos]
    report={'modo':'controlado' if controlado else 'real','versao':versao(),'casos':rows}
    pasta.mkdir(parents=True,exist_ok=True)
    (pasta/'demonstracoes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('Demonstrações:',pasta/'demonstracoes.json')
    return 0 if all(r['acertou'] for r in rows) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--n',type=int,default=3)
    p.add_argument('--familia')
    p.add_argument('--controlado',action='store_true')
    p.add_argument('--um-agente',action='store_true')
    p.add_argument('--mcp',action='store_true')
    a=p.parse_args()
    try:
        r=rodar_suite(a.n,a.familia,a.controlado,not a.um_agente,a.mcp)
        return 0 if r['verificacoes_passaram'] else 1
    except (ValueError,RuntimeError) as e:
        print(str(e),file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())
