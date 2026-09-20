# Parte 1 — ponto de entrada.
#
#   python src/main.py            conversa, interativo
#   python src/main.py --demo     roda os 4 casos do item 4.5 e grava logs/demo/
#
# Os 4 casos da demonstração são os primeiros de cada família obrigatória do
# conjunto rotulado (dados/casos_rotulados.py) — o mesmo conjunto que
# src/avaliar.py usa. Demo e verificador medindo coisas diferentes é como não
# ter verificador.

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))     # permite `import db`, `import agente`
sys.path.insert(0, str(RAIZ / "dados"))            # permite `import gerar_banco`

import db                                                    # noqa: E402
import gerar_banco                                           # noqa: E402
from casos_rotulados import CASOS_DEMO, por_id                # noqa: E402
from agente import rodar, resumo, cliente_e_modelo, Orcamento  # noqa: E402


def garantir_banco() -> None:
    if not db.banco_existe():
        print("Banco não encontrado — gerando dados/estoque.db com dados simulados...")
        gerar_banco.gerar()


def rodar_demo(limpar_entre_casos: bool) -> None:
    """Os 4 casos do item 4.5, com o log de cada um no repositório."""
    garantir_banco()
    client, modelo = cliente_e_modelo()
    print(f"DEMONSTRAÇÃO — 4 casos do item 4.5 · modelo={modelo}\n")

    for caso_id in CASOS_DEMO:
        caso = por_id(caso_id)
        if limpar_entre_casos:
            # Cada caso parte do mesmo estado. Sem isso, o caso 1 debita o
            # orçamento e o seguinte roda contra um banco diferente do
            # documentado — e o log deixa de ser reproduzível.
            gerar_banco.gerar_silencioso()

        print(f"=== caso {caso['id']} · {caso['familia']} ===")
        print(f"Operador: {caso['pergunta']}")
        estado = rodar(caso["pergunta"], orcamento=Orcamento(),
                       client=client, modelo=modelo,
                       salvar_em=RAIZ / "logs" / "demo",
                       rotulo=f"caso-{caso['id']}")
        print(f"\nAssistente: {estado.resposta}")
        print(f"[{resumo(estado)}]\n")


def rodar_interativo() -> None:
    garantir_banco()
    client, modelo = cliente_e_modelo()
    print(f"Assistente de estoque ({modelo}) — pergunte sobre um produto, "
          f"ou 'sair'.")
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if pergunta.lower() in {"sair", "exit", "quit", ""}:
            break
        estado = rodar(pergunta, orcamento=Orcamento(),
                       client=client, modelo=modelo,
                       salvar_em=RAIZ / "logs" / "interativo")
        print(f"\nAssistente: {estado.resposta}")
        print(f"[{resumo(estado)}]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assistente de reposição de estoque — Parte 1")
    parser.add_argument("--demo", action="store_true",
                        help="roda os 4 casos do item 4.5 e grava logs/demo/")
    parser.add_argument("--manter-banco", action="store_true",
                        help="no --demo, não regenera o banco entre os casos")
    args = parser.parse_args()

    if args.demo:
        rodar_demo(limpar_entre_casos=not args.manter_banco)
    else:
        rodar_interativo()


if __name__ == "__main__":
    main()
