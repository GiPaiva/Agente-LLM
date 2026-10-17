"""Fachada da versão integrada. A implementação da Parte 1 permanece no Git."""
from grafo import Aplicacao, Estado


def rodar(pergunta: str, **opcoes):
    with Aplicacao(**opcoes) as app:
        return app.iniciar(pergunta)
