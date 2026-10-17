"""Compatibilidade: escritas da Parte 1 foram substituídas pela autorização do serviço."""
from servico import RegraNegocio

class ErroRecuperavel(RegraNegocio):
    pass

class ErroFatal(RuntimeError):
    pass


def criar_solicitacao_compra(produto_id: str, quantidade: int, chave: str):
    raise ErroRecuperavel('Escrita legada bloqueada; use o grafo e sua capacidade privada.')
