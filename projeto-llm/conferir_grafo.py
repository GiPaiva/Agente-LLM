"""Inspeciona exatamente o grafo utilizado por src/main.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from grafo import Aplicacao

if __name__ == "__main__":
    with Aplicacao(usar_mcp=False) as app:
        grafo = app.grafo.get_graph()
        print("NÓS")
        for nome in sorted(grafo.nodes):
            print(nome)
        print("ARESTAS")
        for e in sorted(grafo.edges, key=lambda e: (e.source, e.target)):
            print(f"{e.source} -> {e.target}" + (" [condicional]" if e.conditional else ""))
