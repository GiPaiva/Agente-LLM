# A VERIFICAÇÃO MÍNIMA DOS TRÊS CANDIDATOS — item 3.3 da entrega.
#
#   python src/benchmark.py            5 casos × 3 modelos
#   python src/benchmark.py --n 2      2 execuções por caso (mede a variação)
#
# O enunciado é explícito sobre o porquê: "não confiem em leaderboard. Rodem
# uma verificação própria, mesmo pequena: cinco casos do seu domínio nos três
# candidatos, com o mesmo prompt". Cinco casos não são medição estatística — o
# que se pede é que o grupo tenha OLHADO a saída dos três modelos no próprio
# problema antes de escolher.
#
# Os cinco casos são um de cada família do conjunto rotulado, e as asserções
# são as mesmas de src/avaliar.py. Benchmark e verificador medindo coisas
# diferentes daria dois números incomparáveis.
#
# Os três candidatos vêm do .env (ver .env.example). Um modelo sem configuração
# é PULADO com aviso, não silenciosamente ignorado.

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(RAIZ / "dados"))

import gerar_banco                              # noqa: E402
import db                                       # noqa: E402
from casos_rotulados import CASOS               # noqa: E402
from agente import rodar, Orcamento             # noqa: E402
from avaliar import checar                      # noqa: E402

load_dotenv()

# Um caso por família — os cinco do item 3.3.
CASOS_BENCH = ["1a", "2a", "3a", "4a", "5a"]


def candidatos() -> list[dict]:
    """Os três candidatos de docs/modelos.md, lidos do .env.

    O nome de cada um diz o eixo que ele representa no estudo — local/grátis,
    hospedado médio, hospedado grande — porque é isso que a tabela do item 3.1
    compara, não a marca.
    """
    local_url = os.environ.get("BENCH_LOCAL_BASE_URL")
    groq_url = os.environ.get("BENCH_GROQ_BASE_URL")
    groq_key = os.environ.get("BENCH_GROQ_API_KEY")

    lista = [
        {
            "rotulo": "local-pequeno",
            "base_url": local_url,
            "api_key": os.environ.get("BENCH_LOCAL_API_KEY") or "local",
            "modelo": os.environ.get("BENCH_LOCAL_MODELO"),
            "onde": "máquina do grupo (túnel Cloudflare)",
        },
        {
            "rotulo": "hospedado-medio",
            "base_url": groq_url,
            "api_key": groq_key,
            "modelo": os.environ.get("BENCH_GROQ_MODELO_MEDIO"),
            "onde": "Groq",
        },
        {
            "rotulo": "hospedado-grande",
            "base_url": groq_url,
            "api_key": groq_key,
            "modelo": os.environ.get("BENCH_GROQ_MODELO_GRANDE"),
            "onde": "Groq",
        },
    ]
    prontos = []
    for c in lista:
        if c["base_url"] and c["modelo"]:
            prontos.append(c)
        else:
            print(f"  [pulado] {c['rotulo']}: falta BENCH_* no .env")
    return prontos


def rodar_candidato(cand: dict, n: int) -> dict:
    client = OpenAI(base_url=cand["base_url"], api_key=cand["api_key"] or "x")
    modelo = cand["modelo"]
    print(f"\n### {cand['rotulo']} — {modelo} ({cand['onde']})")

    linhas = []
    acertos_totais = tokens_totais = 0
    tempos = []

    for caso_id in CASOS_BENCH:
        caso = next(c for c in CASOS if c["id"] == caso_id)
        acertos = 0
        ultima_resposta = ""
        falhas: list[str] = []
        tokens_caso = []

        for _ in range(n):
            gerar_banco.gerar_silencioso()
            inicio = time.monotonic()
            try:
                estado = rodar(caso["pergunta"], orcamento=Orcamento(),
                               client=client, modelo=modelo, verboso=False,
                               salvar_em=RAIZ / "logs" / "benchmark",
                               rotulo=f"{cand['rotulo']}-{caso_id}")
            except Exception as e:                      # noqa: BLE001
                # Um candidato que nem responde é um RESULTADO do benchmark,
                # não um crash do script: anota e segue para o próximo.
                falhas = [f"exceção: {type(e).__name__}: {e}"]
                break

            tempos.append(time.monotonic() - inicio)
            tokens_caso.append(estado.tokens_gastos)
            checagens = checar(estado, caso["espera"])
            if all(ok for _, ok, _ in checagens):
                acertos += 1
            else:
                falhas = [f"{nome}: {motivo}"
                          for nome, ok, motivo in checagens if not ok]
            ultima_resposta = (estado.resposta or "").strip()

        acertos_totais += acertos
        tokens_totais += sum(tokens_caso)
        marca = "ok   " if acertos == n else "FALHA"
        print(f"  {marca} {caso_id}  {acertos}/{n}  {caso['familia']}")
        if falhas:
            for f in falhas:
                print(f"           └─ {f}")

        linhas.append({
            "caso": caso_id,
            "familia": caso["familia"],
            "acertos": acertos,
            "execucoes": n,
            "tokens_medios": round(sum(tokens_caso) / len(tokens_caso)) if tokens_caso else None,
            "resposta_exemplo": ultima_resposta,
            "falhas": falhas,
        })

    total = len(CASOS_BENCH) * n
    return {
        "rotulo": cand["rotulo"],
        "modelo": modelo,
        "onde": cand["onde"],
        "acertos": acertos_totais,
        "total": total,
        "taxa": round(acertos_totais / total, 4) if total else 0.0,
        "latencia_media_s": round(sum(tempos) / len(tempos), 2) if tempos else None,
        "tokens_medios_por_execucao": round(tokens_totais / total) if total else None,
        "casos": linhas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verificação mínima dos três candidatos (item 3.3)")
    parser.add_argument("--n", type=int, default=1,
                        help="execuções por caso e por modelo")
    args = parser.parse_args()

    if not db.banco_existe():
        gerar_banco.gerar()

    print(f"VERIFICAÇÃO MÍNIMA · {len(CASOS_BENCH)} casos × {args.n} "
          f"execução(ões) · mesmo prompt para todos\n")

    resultados = [rodar_candidato(c, args.n) for c in candidatos()]

    print(f"\n{'=' * 78}")
    print(f"{'candidato':<18} {'modelo':<24} {'acerto':>8} {'latência':>10} {'tokens':>8}")
    print("-" * 78)
    for r in resultados:
        lat = f"{r['latencia_media_s']}s" if r["latencia_media_s"] else "-"
        print(f"{r['rotulo']:<18} {r['modelo'][:24]:<24} "
              f"{r['acertos']}/{r['total']:<6} {lat:>10} "
              f"{r['tokens_medios_por_execucao'] or '-':>8}")
    print("=" * 78)

    destino = RAIZ / "logs" / "benchmark"
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"comparacao-{datetime.now():%Y%m%d-%H%M%S}.json"
    caminho.write_text(json.dumps(
        {"quando": datetime.now().isoformat(timespec="seconds"),
         "execucoes_por_caso": args.n,
         "casos": CASOS_BENCH,
         "resultados": resultados},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nresultado: {caminho.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
