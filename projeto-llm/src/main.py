"""Texto livre, conversa persistente e aprovação em perfil simulado."""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from config import Config
from grafo import Aplicacao


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('texto', nargs='?')
    parser.add_argument('--thread')
    parser.add_argument('--usuario', default='operador-demo')
    parser.add_argument('--perfil', choices=['operador', 'gerente'], default='operador')
    parser.add_argument('--retomar', choices=['aprovar', 'rejeitar'])
    parser.add_argument('--quantidade', type=int)
    parser.add_argument('--pendentes', action='store_true')
    parser.add_argument('--remover-conversa')
    parser.add_argument('--um-agente', action='store_true')
    parser.add_argument('--sem-mcp', action='store_true')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--demo', action='store_true', help='seis cenários; requer modelo real')
    parser.add_argument('--controlado', action='store_true', help='dublê explicitamente identificado')
    args = parser.parse_args()
    config = Config.ambiente()
    if args.runtime:
        config = replace(config, runtime=args.runtime)
    elif args.controlado:
        config = replace(config, runtime=config.runtime / "controlado")
    kwargs = {}
    if args.controlado:
        from simulador import EmbeddingControlado, ModeloControlado
        kwargs = dict(modelo=ModeloControlado(), embedding=EmbeddingControlado())
    if args.demo:
        from avaliar import demonstrar
        try:
            return demonstrar(config, args.controlado, not args.um_agente, not args.sem_mcp)
        except RuntimeError as erro:
            print(str(erro), file=sys.stderr)
            return 2
    try:
        with Aplicacao(config, multi=not args.um_agente, usar_mcp=not args.sem_mcp, **kwargs) as app:
            codigo = 0
            def imprimir(saida):
                nonlocal codigo
                if saida.status == "falha":
                    codigo = 1
                print(json.dumps({'modo': app.modelo.modo, 'saida': saida.model_dump()}, ensure_ascii=False, indent=2))
            if args.pendentes:
                print(json.dumps(app.servico.pendentes(), ensure_ascii=False, indent=2))
            elif args.remover_conversa:
                if args.perfil != 'gerente':
                    raise PermissionError('Remoção exige perfil simulado gerente.')
                print(json.dumps(app.remover_conversa(args.remover_conversa), ensure_ascii=False, indent=2))
            elif args.retomar:
                if not args.thread:
                    parser.error('--retomar exige --thread')
                imprimir(app.retomar(args.thread, {'acao': args.retomar, 'quantidade': args.quantidade}, args.perfil))
            elif args.texto:
                imprimir(app.iniciar(args.texto, args.usuario, args.thread))
            else:
                thread = args.thread
                print('Assistente simulado. Digite sair. O perfil gerente não possui autenticação real.')
                while True:
                    try:
                        texto = input('Você: ').strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break
                    if not texto or texto.lower() == 'sair':
                        break
                    saida = app.iniciar(texto, args.usuario, thread)
                    thread = saida.thread_id
                    imprimir(saida)
                    if saida.status == 'aguardando_aprovacao':
                        print('Retome em outra chamada com --perfil gerente --thread', thread, '--retomar aprovar ou rejeitar.')
                        break
        return codigo
    except (ValueError, PermissionError, RuntimeError) as erro:
        print(str(erro), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
