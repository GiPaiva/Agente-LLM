"""§5.4 — remoção com cobertura, verificada de forma independente: grava um fato,
mostra que o comportamento mudou, remove a conversa, mostra que voltou, e varre
TODAS as estruturas em disco procurando o identificador da conversa removida."""
import argparse
import json
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
from config import RAIZ, Config, agora, versao
from grafo import Aplicacao

PISTA = 'Escolha anterior confirmada'


def varrer(runtime: Path, agulhas: list[str]) -> dict:
    """Procura cada agulha em cada tabela de cada SQLite e em cada log do runtime."""
    achados = {a: [] for a in agulhas}
    for banco in sorted(runtime.glob('*.sqlite')):
        con = sqlite3.connect(banco)
        for (tabela,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            for linha in con.execute(f'SELECT * FROM "{tabela}"'):
                texto = ' '.join(x.decode('utf-8', 'ignore') if isinstance(x, bytes) else str(x) for x in linha)
                for a in agulhas:
                    if a in texto:
                        achados[a].append(f'{banco.name}:{tabela}')
        con.close()
    for log in sorted((runtime / 'logs').glob('*.json')):
        for a in agulhas:
            if a in log.read_text():
                achados[a].append('logs/' + log.name)
    return {a: sorted(set(v)) for a, v in achados.items()}


def demonstrar(controlado=False):
    with tempfile.TemporaryDirectory(prefix='remocao-') as tmp:
        cfg = replace(Config.ambiente(), runtime=Path(tmp))
        kwargs = {}
        if controlado:
            from simulador import EmbeddingControlado, ModeloControlado
            kwargs = dict(modelo=ModeloControlado(), embedding=EmbeddingControlado())
        passos = []
        with Aplicacao(cfg, usar_mcp=False, **kwargs) as app:
            def turno(rotulo, texto, thread):
                s = app.iniciar(texto, 'ana', thread)
                passos.append({'passo': rotulo, 'thread': thread, 'entrada': texto, 'status': s.status,
                               'resultado': s.resultado, 'pista_de_memoria': PISTA in s.resultado})
                return s
            # Sufixo único: remover_conversa também varre logs/ do repositório, e um
            # id fixo apagaria o relatório de uma execução anterior desta demo.
            sufixo = uuid4().hex[:8]
            a = f'ana:remocao-A-{sufixo}'
            turno('1 pergunta ambígua', 'Como está o açúcar?', a)
            turno('2 desambigua e grava fato', 'O de 5kg.', a)
            antes = varrer(cfg.runtime, [a, PISTA])
            turno('3 outra conversa usa o fato', 'Como está o açúcar?', f'ana:remocao-B-{sufixo}')
            remocao = app.remover_conversa(a)
            turno('4 depois da remoção', 'Como está o açúcar?', f'ana:remocao-C-{sufixo}')
            depois = varrer(cfg.runtime, [a, PISTA])
        return {'versao': versao(), 'quando': agora().isoformat(), 'modo': 'controlado' if controlado else 'real',
                'modelo': app.modelo.nome, 'passos': passos, 'remocao': remocao,
                'varredura_antes_da_remocao': antes, 'varredura_depois_da_remocao': depois,
                'leitura': 'O identificador da conversa A precisa sumir de todas as estruturas. '
                           'A pista derivada do fato de A pode sobreviver na saída de OUTRA conversa (B): '
                           'é dado derivado, que a remoção por thread não alcança.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--controlado', action='store_true')
    report = demonstrar(p.parse_args().controlado)
    pasta = RAIZ / 'logs' / 'memoria'; pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / ('remocao-' + report['modo'] + '-' + agora().strftime('%Y%m%d-%H%M%S') + '.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'versao'}, ensure_ascii=False, indent=2))
    print('Relatório:', path)
