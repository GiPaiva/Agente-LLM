"""Servidor local. Somente o coordenador possui a capacidade de escrita."""
import argparse
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from config import Config
from conhecimento import Conhecimento
from servico import Servico
from transporte import DESCRICOES


def criar_servidor(config):
    estoque, conhecimento = Servico(config.runtime), Conhecimento(config)
    servidor = FastMCP("estoque-simulado", log_level="ERROR")

    @servidor.tool(description=DESCRICOES["consultar_estoque"])
    def consultar_estoque(produto: str) -> dict:
        return estoque.consultar_estoque(produto)

    @servidor.tool(description=DESCRICOES["consultar_fornecedor"])
    def consultar_fornecedor(fornecedor: str) -> dict:
        return estoque.consultar_fornecedor(fornecedor)

    @servidor.tool(description=DESCRICOES["calcular_reposicao"])
    def calcular_reposicao(produto_id: str) -> dict:
        return estoque.calcular_reposicao(produto_id)

    @servidor.tool(description=DESCRICOES["buscar_documentos"])
    def buscar_documentos(consulta: str, fornecedor: str = "") -> list[dict]:
        return conhecimento.buscar_documentos(consulta, fornecedor)

    @servidor.tool(description=DESCRICOES["registrar_compra"])
    def registrar_compra(caso_id: str, capacidade: str) -> dict:
        return estoque.finalizar(caso_id, capacidade)

    return servidor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    criar_servidor(Config(runtime=parser.parse_args().runtime)).run(transport="stdio")
