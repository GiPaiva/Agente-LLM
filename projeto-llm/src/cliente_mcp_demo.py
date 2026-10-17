"""Cliente independente do grafo: prova de reutilização de ferramenta MCP."""
import json
from config import Config
from transporte import ClienteMCP

if __name__=='__main__':
    cliente=ClienteMCP(Config.ambiente())
    try:
        print(json.dumps(cliente.chamar('consultar_estoque',{'produto':'arroz'}),ensure_ascii=False,indent=2))
    finally: cliente.close()
