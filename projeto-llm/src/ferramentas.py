# Parte 1 — as ferramentas do agente. Quatro, que é o teto do item 4.1
# ("2 a 4 ferramentas; mais que isso é escopo da Parte 2").
#
#   consultar_estoque .......... LEITURA   (banco)
#   consultar_fornecedor ....... LEITURA   (banco)
#   calcular_reposicao ......... CÁLCULO   (banco + aritmética em código)
#   criar_solicitacao_compra ... ESCRITA   (banco, idempotente)
#
# A única ESCRITA é `criar_solicitacao_compra`: reversível (dá para cancelar
# antes do envio ao fornecedor, que é a próxima etapa e está fora do escopo
# desta entrega), idempotente por chave e sujeita à regra de orçamento.

from datetime import date

import db

# Acima deste valor de comprometimento, a solicitação nasce PENDENTE de
# aprovação do gerente — não é recusada nem executada em silêncio.
# Regra herdada de ideia-evolucao/v2.md, seção 5.
LIMITE_SEM_APROVACAO = 500.0

# Repor até este múltiplo do estoque mínimo. Dois é uma escolha, não uma
# verdade: é o limite conhecido do cálculo, declarado em docs/case.md §10.
FATOR_REPOSICAO = 2


class ErroRecuperavel(Exception):
    """O modelo pode contornar mudando a chamada. Volta como OBSERVAÇÃO para o
    modelo, não como exceção que derruba o programa.

    O texto e o contexto deste erro são PROMPT (nota 03 da aula 05): eles
    precisam ensinar o modelo a se corrigir, e é por isso que carregam a lista
    de alternativas em vez de só dizer "não encontrado".
    """

    def __init__(self, mensagem: str, **contexto):
        super().__init__(mensagem)
        self.payload = {"erro": mensagem, **contexto}


class ErroFatal(Exception):
    """Nenhuma decisão do modelo resolve isto. Aborta o laço."""


# ------------------------------------------------------------- ferramentas

def consultar_estoque(produto: str) -> dict:
    """LEITURA. Vai ao banco (db.py) — não a um dicionário no código.

    Distingue três situações, e é essa distinção que faz o agente se comportar
    bem nos casos difíceis:

      0 candidatos  -> erro recuperável com a lista de produtos existentes.
                       É o caso difícil #3 (registro inexistente).
      2+ candidatos -> erro recuperável pedindo DESAMBIGUAÇÃO. É o caso #5,
                       e é o que obriga o agente a perguntar em vez de chutar.
      1 candidato   -> o produto.
    """
    candidatos = db.buscar_produtos(produto)

    if not candidatos:
        raise ErroRecuperavel(
            "produto não encontrado",
            recebido=produto,
            produtos_disponiveis=db.listar_nomes_produtos(),
            sugestao=("tente um termo mais curto (só o nome, sem a embalagem); "
                      "se ainda assim não houver, o produto não existe no "
                      "cadastro e você deve dizer isso ao usuário"),
        )

    if len(candidatos) > 1:
        raise ErroRecuperavel(
            "termo ambíguo: mais de um produto casa",
            recebido=produto,
            candidatos=[c["nome"] for c in candidatos],
            sugestao=("pergunte ao usuário qual deles ele quer; não escolha "
                      "sozinho"),
        )

    linha = candidatos[0]
    return {
        "id": linha["id"],
        "nome": linha["nome"],
        "estoque_atual": linha["estoque_atual"],
        "estoque_minimo": linha["estoque_minimo"],
        "venda_media_diaria": linha["venda_media_diaria"],
        "preco_unitario": linha["preco_unitario"],
        "fornecedor_id": linha["fornecedor_id"],
        # Pré-calculado no CÓDIGO de propósito: comparar dois inteiros é a
        # decisão mais fácil de errar quando se deixa para o modelo, e ela é a
        # que separa o caso 1 do caso 4.
        "abaixo_do_minimo": linha["estoque_atual"] < linha["estoque_minimo"],
    }


def consultar_fornecedor(fornecedor: str) -> dict:
    """LEITURA. Aceita o id (FORN_A) ou o nome ("Fornecedor A")."""
    linha = db.buscar_fornecedor_por_id(fornecedor)
    if linha is None:
        candidatos = db.buscar_fornecedores(fornecedor)
        if not candidatos:
            raise ErroRecuperavel(
                "fornecedor não encontrado",
                recebido=fornecedor,
                fornecedores_disponiveis=db.listar_nomes_fornecedores(),
                sugestao=("use o fornecedor_id devolvido por consultar_estoque"),
            )
        if len(candidatos) > 1:
            raise ErroRecuperavel(
                "termo ambíguo: mais de um fornecedor casa",
                recebido=fornecedor,
                candidatos=[c["nome"] for c in candidatos],
            )
        linha = candidatos[0]

    return {
        "id": linha["id"],
        "nome": linha["nome"],
        "prazo_dias": linha["prazo_dias"],
        "pedido_minimo": linha["pedido_minimo"],
    }


def calcular_reposicao(produto_id: str) -> dict:
    """CÁLCULO. Aritmética é trabalho de código, não do modelo.

    Recebe UM argumento — o id do produto — e busca o resto sozinho no banco.
    A versão anterior desta ferramenta recebia estoque, mínimo, giro e pedido
    mínimo como quatro argumentos, sendo o último OPCIONAL; nos logs do esboço
    o modelo omitiu justamente o pedido mínimo, recebeu 48 de volta, percebeu
    que o fornecedor exigia 50 e refez a conta de cabeça respondendo "50".
    Uma ferramenta de cálculo cujo resultado o modelo corrige no braço não
    está impedindo nada.

    Buscar os números aqui dentro elimina a classe de erro inteira: não há
    argumento para o modelo esquecer, nem número para ele transcrever errado.
    """
    produto = db.buscar_produto_por_id(produto_id)
    if produto is None:
        raise ErroRecuperavel(
            "produto_id não existe",
            recebido=produto_id,
            sugestao="use o campo `id` devolvido por consultar_estoque",
        )

    fornecedor = db.buscar_fornecedor_por_id(produto["fornecedor_id"])
    pedido_minimo = fornecedor["pedido_minimo"] if fornecedor else 0
    prazo_dias = fornecedor["prazo_dias"] if fornecedor else None

    estoque = produto["estoque_atual"]
    minimo = produto["estoque_minimo"]
    giro = produto["venda_media_diaria"]
    dias_restantes = round(estoque / giro, 1) if giro > 0 else None

    if estoque >= minimo:
        return {
            "produto_id": produto["id"],
            "precisa_repor": False,
            "quantidade_recomendada": 0,
            "motivo": (f"estoque {estoque} >= mínimo {minimo}: não há "
                       f"necessidade de reposição"),
            "dias_de_estoque_restante": dias_restantes,
            "custo_estimado": 0.0,
            "prazo_dias": prazo_dias,
        }

    bruta = minimo * FATOR_REPOSICAO - estoque
    quantidade = max(bruta, pedido_minimo)
    custo = round(quantidade * produto["preco_unitario"], 2)

    return {
        "produto_id": produto["id"],
        "precisa_repor": True,
        "quantidade_recomendada": quantidade,
        # Os dois campos abaixo existem para o modelo poder EXPLICAR a conta ao
        # operador sem recalculá-la. Sem eles, ele inventa a explicação.
        "quantidade_antes_do_pedido_minimo": bruta,
        "pedido_minimo_do_fornecedor": pedido_minimo,
        "motivo": (f"estoque {estoque} < mínimo {minimo}; repor até "
                   f"{FATOR_REPOSICAO}x o mínimo daria {bruta}, e o pedido "
                   f"mínimo do fornecedor é {pedido_minimo}"),
        "dias_de_estoque_restante": dias_restantes,
        "preco_unitario": produto["preco_unitario"],
        "custo_estimado": custo,
        "prazo_dias": prazo_dias,
    }


def criar_solicitacao_compra(produto_id: str, quantidade: int, chave: str) -> dict:
    """ESCRITA. Reversível: registra no banco, não envia nada a fornecedor
    nenhum (esse envio é Parte 2/3, e aí sim exige confirmação humana).

    Idempotente por `chave` (nota 02, aula 05): a chave identifica a OPERAÇÃO
    ("ARROZ_5KG:48"), não a tentativa. Repetir a chamada com a mesma chave não
    duplica a solicitação — devolve a que já existe, com `ja_existia: True`,
    que é informação PARA O MODELO: ele descobre que já agiu.

    O preço NÃO é argumento. Quem multiplica é o banco, a partir do cadastro:
    deixar o modelo informar o preço unitário é deixá-lo escolher quanto a
    loja vai gastar.
    """
    existente = db.obter_solicitacao(chave)
    if existente is not None:
        return {
            "protocolo": existente["chave"],
            "status": existente["status"],
            "quantidade": existente["quantidade"],
            "custo_estimado": existente["custo_estimado"],
            "ja_existia": True,
        }

    produto = db.buscar_produto_por_id(produto_id)
    if produto is None:
        raise ErroRecuperavel(
            "produto_id não existe",
            recebido=produto_id,
            sugestao="use o campo `id` devolvido por consultar_estoque",
        )

    if quantidade <= 0:
        raise ErroRecuperavel(
            "quantidade precisa ser maior que zero",
            recebido=quantidade,
        )

    custo_estimado = round(quantidade * produto["preco_unitario"], 2)
    orcamento = db.orcamento_disponivel()

    # A regra de negócio mora no CÓDIGO, não no prompt. Se morasse no prompt,
    # seria uma sugestão.
    if custo_estimado > LIMITE_SEM_APROVACAO or custo_estimado > orcamento:
        status = "aguardando_aprovacao_gerente"
    else:
        status = "criada"

    db.registrar_solicitacao(chave, produto_id, quantidade, custo_estimado,
                             status, date.today().isoformat())

    return {
        "protocolo": chave,
        "status": status,
        "produto": produto["nome"],
        "quantidade": quantidade,
        "preco_unitario": produto["preco_unitario"],
        "custo_estimado": custo_estimado,
        "limite_sem_aprovacao": LIMITE_SEM_APROVACAO,
        "orcamento_disponivel_antes": orcamento,
        "ja_existia": False,
    }


FERRAMENTAS = {
    "consultar_estoque": consultar_estoque,
    "consultar_fornecedor": consultar_fornecedor,
    "calcular_reposicao": calcular_reposicao,
    "criar_solicitacao_compra": criar_solicitacao_compra,
}

ESCRITA = {"criar_solicitacao_compra"}


# A descrição de ferramenta É PROMPT: diz o que faz, quando usar e QUANDO NÃO
# USAR (aula 03, nota 04 §4).
DECLARACOES = {
    "consultar_estoque": {
        "type": "function",
        "function": {
            "name": "consultar_estoque",
            "description": (
                "Consulta estoque atual, estoque mínimo, venda média diária e "
                "preço de um produto pelo nome. Use SEMPRE antes de afirmar "
                "qualquer número de estoque ou decidir sobre reposição — nunca "
                "invente esses números. Se o resultado disser que o termo é "
                "ambíguo, pergunte ao usuário qual produto ele quer."),
            "parameters": {
                "type": "object",
                "properties": {
                    "produto": {
                        "type": "string",
                        "description": ("nome do produto como o usuário falou, "
                                        "ex: 'arroz' ou 'arroz 5kg'"),
                    },
                },
                "required": ["produto"],
                "additionalProperties": False,
            },
        },
    },
    "consultar_fornecedor": {
        "type": "function",
        "function": {
            "name": "consultar_fornecedor",
            "description": (
                "Consulta nome, prazo de entrega e pedido mínimo de um "
                "fornecedor, a partir do fornecedor_id devolvido por "
                "consultar_estoque. Use quando for informar ao usuário em "
                "quantos dias a mercadoria chega."),
            "parameters": {
                "type": "object",
                "properties": {
                    "fornecedor": {
                        "type": "string",
                        "description": "o fornecedor_id, ex: 'FORN_A'",
                    },
                },
                "required": ["fornecedor"],
                "additionalProperties": False,
            },
        },
    },
    "calcular_reposicao": {
        "type": "function",
        "function": {
            "name": "calcular_reposicao",
            "description": (
                "Calcula a quantidade de reposição e o custo estimado de um "
                "produto. Já considera o pedido mínimo do fornecedor. Use em "
                "vez de calcular de cabeça, e NÃO corrija o número que ela "
                "devolver: ele já está certo. Só chame depois de "
                "consultar_estoque, para ter o id."),
            "parameters": {
                "type": "object",
                "properties": {
                    "produto_id": {
                        "type": "string",
                        "description": ("o campo `id` devolvido por "
                                        "consultar_estoque, ex: 'ARROZ_5KG'"),
                    },
                },
                "required": ["produto_id"],
                "additionalProperties": False,
            },
        },
    },
    "criar_solicitacao_compra": {
        "type": "function",
        "function": {
            "name": "criar_solicitacao_compra",
            "description": (
                "ESCRITA: registra uma solicitação de compra. Use a quantidade "
                "que calcular_reposicao devolveu. Não use para perguntas "
                "apenas informativas, e não use para produto cujo estoque "
                "esteja acima do mínimo."),
            "parameters": {
                "type": "object",
                "properties": {
                    "produto_id": {"type": "string"},
                    "quantidade": {
                        "type": "integer",
                        "description": ("exatamente a quantidade_recomendada "
                                        "de calcular_reposicao"),
                    },
                    "chave": {
                        "type": "string",
                        "description": ("chave de idempotência derivada do "
                                        "conteúdo: produto_id:quantidade, "
                                        "ex: 'ARROZ_5KG:48'"),
                    },
                },
                "required": ["produto_id", "quantidade", "chave"],
                "additionalProperties": False,
            },
        },
    },
}


# ---------------------------------------------------------------- as FASES
#
# Aula 05, nota 02 §6: "restrição por arquitetura vence restrição por prompt —
# instrução ele pode ignorar, ferramenta não declarada ele não tem como
# chamar."
#
# Na fase de ANÁLISE, `criar_solicitacao_compra` simplesmente NÃO EXISTE para o
# modelo. Quem a habilita é o código de agente.py, e só depois que um
# `consultar_estoque` desta execução devolveu `abaixo_do_minimo: True`.
#
# É isso que transforma o critério assimétrico do item 2.7 da entrega ("nunca
# criar compra no caso 4") de uma esperança de prompt numa GARANTIA: nos casos
# 2, 3 e 4 a ferramenta de escrita nunca chega a ser oferecida ao modelo.
FASES = {
    "analise": ["consultar_estoque", "consultar_fornecedor", "calcular_reposicao"],
    "reposicao": ["consultar_estoque", "consultar_fornecedor",
                  "calcular_reposicao", "criar_solicitacao_compra"],
}


def declaracoes(ativas: list[str]) -> list[dict]:
    return [DECLARACOES[nome] for nome in ativas]
