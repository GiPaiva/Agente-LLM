"""§2.3 — a regra da frase: remove UMA frase do prompt de triagem e mede só a
etapa que a lê (a triagem), com o modelo real, no mesmo conjunto e critério.

Rodar o grafo inteiro 120 vezes num modelo local levaria horas; a frase só
afeta a interpretação, então a etapa isolada é a medição honesta e barata."""
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from config import RAIZ, Config, agora, versao
from grafo import Aplicacao

sys.path.insert(0, str(RAIZ / 'dados'))
from casos_rotulados import CASOS

FRASE = 'Pergunta apenas informativa é consulta, mesmo com estoque baixo.'
# Rótulo da intenção que a triagem deve extrair. Família 1 pede compra; família 4
# e as duas perguntas sobre produto abaixo do mínimo são só informativas.
ESPERADO = {**{c['id']: 'reposicao' for c in CASOS if c['familia'] == '1_simples'},
            **{c['id']: 'consulta' for c in CASOS if c['familia'] == '4_nao_comprar'}}
EXTRAS = [{'id': 'x1', 'pergunta': 'Quanto temos de arroz?', 'intencao': 'consulta'},
          {'id': 'x2', 'pergunta': 'O sal de 1kg tá abaixo do mínimo?', 'intencao': 'consulta'},
          {'id': 'x3', 'pergunta': 'Quanto tem de açúcar 5kg? Tá baixo?', 'intencao': 'consulta'}]
CONJUNTO = [{'id': c['id'], 'pergunta': c['pergunta'], 'intencao': ESPERADO[c['id']]}
            for c in CASOS if c['id'] in ESPERADO] + EXTRAS


def triar(app, texto):
    estado = {'texto': texto, 'usuario': 'ablacao', 'thread_id': 'ablacao', 'caso_id': 'ablacao',
              'mensagens': [], **{k: 0 for k in ('n_modelo', 'n_ferramentas', 'n_recuperacoes',
                                                 'tokens_entrada', 'tokens_saida', 'processamento_s')}}
    r = app._interpretar(estado)
    return (r.get('interpretacao') or {}).get('intencao') or 'erro:' + str(r.get('erro'))[:80]


def main(n=2):
    if not os.environ.get('LLM_BASE_URL') or not os.environ.get('LLM_MODELO'):
        print('PENDENTE: ablação exige modelo real configurado; nenhum efeito de prompt foi medido.')
        return 2
    if FRASE not in (RAIZ / 'src' / 'prompts' / 'triagem.md').read_text():
        print('A frase já foi removida (decisão em docs/prompts.md §3). Para reproduzir a medição, '
              'rode no commit 6c48749: git checkout 6c48749 -- src/prompts/triagem.md')
        return 2
    original = Aplicacao._prompt
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        config = replace(Config.ambiente(), runtime=Path(tmp))
        for variante in ('original', 'sem_frase'):
            def ler(self, nome, _variante=variante, **campos):
                texto = original(self, nome, **campos)
                return texto.replace(FRASE, '') if _variante == 'sem_frase' and nome == 'triagem' else texto
            Aplicacao._prompt = ler
            try:
                with Aplicacao(config, usar_mcp=False) as app:
                    for caso in CONJUNTO:
                        for rodada in range(n):
                            obtido = triar(app, caso['pergunta'])
                            rows.append({'variante': variante, 'rodada': rodada, **caso, 'obtido': obtido,
                                         'ok': obtido == caso['intencao']})
                            print(variante, caso['id'], caso['intencao'], '->', obtido, flush=True)
            finally:
                Aplicacao._prompt = original
    placar = {v: f"{sum(r['ok'] for r in rows if r['variante'] == v)}/{sum(r['variante'] == v for r in rows)}"
              for v in ('original', 'sem_frase')}
    report = {'versao': versao(), 'quando': agora().isoformat(), 'modelo': os.environ['LLM_MODELO'],
              'etapa': 'triagem', 'frase_removida': FRASE, 'n': n, 'placar': placar, 'casos': rows}
    pasta = RAIZ / 'logs' / 'prompts'; pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / (agora().strftime('%Y%m%d-%H%M%S') + '.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'placar': placar, 'relatorio': str(path)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2))
