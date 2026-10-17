"""Agrega traces de uma execução de eval/demo, sem misturar configurações."""
import argparse
import json
import statistics
import math
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pasta',type=Path)
    a=p.parse_args()
    rows=[json.loads(f.read_text()) for f in a.pasta.glob('*.json')]
    rows=[r for r in rows if 'metricas' in r and 'caso_id' in r]
    # Pausa, retomada e aprovação repetida carregam contadores cumulativos.
    # Uma única linha final por caso evita somar a trajetória mais de uma vez.
    finais={}
    for r in sorted(rows,key=lambda r:r['quando']): finais[r['caso_id']]=r
    rows=list(finais.values())
    if not rows: raise SystemExit('Não há traces nesta pasta.')
    tempos=sorted(r['metricas']['processamento_s'] for r in rows)
    print(json.dumps({'casos':len(rows),'modos':sorted({r['modo'] for r in rows}),
        'media_processamento_s':statistics.mean(tempos),'p95_processamento_s':tempos[max(0,math.ceil(len(tempos)*.95)-1)],
        'chamadas_modelo':sum(r['metricas']['n_modelo'] for r in rows),
        'ferramentas':sum(r['metricas']['n_ferramentas'] for r in rows),
        'recuperacoes':sum(r['metricas']['n_recuperacoes'] for r in rows),
        'tokens_entrada':sum(r['metricas']['tokens_entrada'] for r in rows),
        'tokens_saida':sum(r['metricas']['tokens_saida'] for r in rows),
        'custo_api_usd':sum(r['custo_api'] for r in rows) if all(r.get('custo_api') is not None for r in rows) else None,
        'energia_kwh_medida':None,
        'nota':'Tarifa local sem cobrança não inclui energia/hardware. Ganho humano depende do baseline.'},ensure_ascii=False,indent=2))
