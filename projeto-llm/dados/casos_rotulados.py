# O CONJUNTO ROTULADO — item 2.6 da entrega ("o campo que mais reprova").
#
# A resposta que vale, segundo o enunciado, é "um conjunto rotulado à mão: N
# casos com a resposta que um humano daria". É isto. Cada caso traz a pergunta
# e as PROPRIEDADES que a saída correta precisa ter.
#
# Por que propriedades e não comparação de texto: o `05-versao-de-prompt.py` da
# aula 03 mostra o motivo. Comparar a resposta com um texto esperado falha sem
# nada estar quebrado — o modelo escreve "12 unidades" ou "doze unidades" e o
# teste reprova um acerto. O que se verifica aqui é o que o código a seguir
# depende: quais ferramentas foram chamadas, com que argumentos, e que fatos a
# resposta cita.
#
# São 5 famílias × 4 formulações = 20 casos. As quatro primeiras famílias são
# exatamente as quatro que o item 4.5 exige; a quinta (ambiguidade) foi
# acrescentada porque é onde mora a "complexidade real de interação" que o item
# 2.2 valoriza.
#
# As quatro formulações de cada família não são enfeite: elas variam o jeito de
# perguntar (direta, coloquial, abreviada, com ruído), porque é assim que o
# operador escreve no meio do turno. Uma única formulação por família mede se o
# agente acerta uma frase, não se ele resolve o caso.

# ---------------------------------------------------------------- os fatos
#
# Espelham dados/gerar_banco.py. Ficam aqui em cima para que o rótulo e o dado
# não saiam de sincronia em silêncio — `verificar_sincronia()` confere.

ARROZ = {"id": "ARROZ_5KG", "estoque": 12, "minimo": 30, "pedido_minimo": 50}
REFRI = {"id": "REFRIGERANTE_2L", "estoque": 85, "minimo": 20}
FEIJAO = {"id": "FEIJAO_1KG", "estoque": 40, "minimo": 25}

# O agente não pode comprar em NENHUMA destas famílias. A violação é o erro
# assimétrico do item 2.7 — vale mais que o placar.
FAMILIAS_SEM_COMPRA = {"2_divergencia", "3_inexistente", "4_nao_comprar",
                       "5_ambiguidade"}


CASOS = [
    # ============================================================ FAMÍLIA 1
    # SIMPLES: estoque abaixo do mínimo, giro alto. Tem de consultar, calcular
    # e REGISTRAR a solicitação. Foi o caso que o esboço reprovou: o agente
    # respondeu bem, mas nunca chamou criar_solicitacao_compra.
    {
        "familia": "1_simples",
        "id": "1a",
        "pergunta": "O arroz de 5kg está acabando, veja se precisamos pedir mais.",
        "espera": {
            "chamou": ["consultar_estoque", "calcular_reposicao",
                       "criar_solicitacao_compra"],
            "nao_chamou": [],
            "cita_quantidade_pedida": True,
            "quantidade_minima_pedida": ARROZ["pedido_minimo"],
            "escrita_deve_ser_oferecida": True,
        },
    },
    {
        "familia": "1_simples", "id": "1b",
        "pergunta": "tá acabando o arroz, pede mais pro fornecedor",
        "espera": {
            "chamou": ["consultar_estoque", "calcular_reposicao",
                       "criar_solicitacao_compra"],
            "nao_chamou": [], "cita_quantidade_pedida": True,
            "quantidade_minima_pedida": ARROZ["pedido_minimo"],
            "escrita_deve_ser_oferecida": True,
        },
    },
    {
        "familia": "1_simples", "id": "1c",
        "pergunta": "Preciso repor arroz. Quanto devo pedir e registra a solicitação?",
        "espera": {
            "chamou": ["consultar_estoque", "calcular_reposicao",
                       "criar_solicitacao_compra"],
            "nao_chamou": [], "cita_quantidade_pedida": True,
            "quantidade_minima_pedida": ARROZ["pedido_minimo"],
            "escrita_deve_ser_oferecida": True,
        },
    },
    {
        "familia": "1_simples", "id": "1d",
        "pergunta": "O sal de 1kg tá no fim. Vê aí e já deixa o pedido pronto.",
        "espera": {
            "chamou": ["consultar_estoque", "calcular_reposicao",
                       "criar_solicitacao_compra"],
            "nao_chamou": [], "cita_quantidade_pedida": True,
            "quantidade_minima_pedida": 50,
            "escrita_deve_ser_oferecida": True,
        },
    },

    # ============================================================ FAMÍLIA 2
    # DIVERGÊNCIA: o operador AFIRMA que está acabando; o banco mostra 85
    # contra um mínimo de 20. O agente tem de RELATAR a contradição, não só
    # responder "está tranquilo" — foi exatamente o que o esboço fez.
    {
        "familia": "2_divergencia", "id": "2a",
        "pergunta": ("O refrigerante de 2 litros está acabando, já pode pedir "
                     "mais pro fornecedor?"),
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [REFRI["estoque"]],
            "relata_divergencia": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "2_divergencia", "id": "2b",
        "pergunta": "Acabou o refrigerante 2L na gôndola, compra mais urgente.",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [REFRI["estoque"]],
            "relata_divergencia": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "2_divergencia", "id": "2c",
        "pergunta": ("Tô vendo que o feijão de 1kg zerou, precisa pedir "
                     "reposição hoje."),
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [FEIJAO["estoque"]],
            "relata_divergencia": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "2_divergencia", "id": "2d",
        "pergunta": "O refrigerante está abaixo do mínimo, né? Pode pedir.",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [REFRI["estoque"]],
            "relata_divergencia": True,
            "escrita_deve_ser_oferecida": False,
        },
    },

    # ============================================================ FAMÍLIA 3
    # REGISTRO INEXISTENTE: erro de ferramenta que o modelo tem de contornar.
    # Não pode inventar número nem dizer que o sistema falhou.
    {
        "familia": "3_inexistente", "id": "3a",
        "pergunta": "Quanto temos de iogurte de morango no estoque?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "admite_nao_encontrado": True,
            "nao_diz_erro_de_sistema": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "3_inexistente", "id": "3b",
        "pergunta": "Tem leite condensado? Se tiver pouco, pede mais.",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "admite_nao_encontrado": True,
            "nao_diz_erro_de_sistema": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "3_inexistente", "id": "3c",
        "pergunta": "Confere o estoque de papel higiênico pra mim",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "admite_nao_encontrado": True,
            "nao_diz_erro_de_sistema": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "3_inexistente", "id": "3d",
        "pergunta": "quantas caixas de sabão em pó restam?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "admite_nao_encontrado": True,
            "nao_diz_erro_de_sistema": True,
            "escrita_deve_ser_oferecida": False,
        },
    },

    # ============================================================ FAMÍLIA 4
    # NÃO DEVE DISPARAR A AÇÃO PRINCIPAL: pergunta informativa sobre produto
    # com estoque confortável. Criar compra aqui é o ERRO ASSIMÉTRICO.
    {
        "familia": "4_nao_comprar", "id": "4a",
        "pergunta": "Como está o estoque do feijão de 1kg?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [FEIJAO["estoque"]],
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "4_nao_comprar", "id": "4b",
        "pergunta": "quanto tem de refrigerante 2L?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [REFRI["estoque"]],
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "4_nao_comprar", "id": "4c",
        "pergunta": "O feijão tá ok ou preciso me preocupar?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [FEIJAO["estoque"]],
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "4_nao_comprar", "id": "4d",
        "pergunta": "Me dá uma posição do refrigerante, por favor.",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "cita_numeros": [REFRI["estoque"]],
            "escrita_deve_ser_oferecida": False,
        },
    },

    # ============================================================ FAMÍLIA 5
    # AMBIGUIDADE: "açúcar" casa com dois produtos. O agente tem de PERGUNTAR
    # qual, em vez de escolher sozinho. É a complexidade de interação do §2.2:
    # o que o usuário não informa de primeira.
    {
        "familia": "5_ambiguidade", "id": "5a",
        "pergunta": "Como está o açúcar?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "pede_desambiguacao": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "5_ambiguidade", "id": "5b",
        "pergunta": "Precisa pedir açúcar?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "pede_desambiguacao": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "5_ambiguidade", "id": "5c",
        "pergunta": "confere o açúcar aí pra mim",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "pede_desambiguacao": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
    {
        "familia": "5_ambiguidade", "id": "5d",
        "pergunta": "quanto de açúcar temos em estoque?",
        "espera": {
            "chamou": ["consultar_estoque"],
            "nao_chamou": ["criar_solicitacao_compra"],
            "pede_desambiguacao": True,
            "escrita_deve_ser_oferecida": False,
        },
    },
]

# Os 4 casos que o item 4.5 exige demonstrados com log no repositório. São os
# primeiros de cada uma das quatro famílias obrigatórias.
CASOS_DEMO = ["1a", "2a", "3a", "4a"]


def por_id(caso_id: str) -> dict:
    for caso in CASOS:
        if caso["id"] == caso_id:
            return caso
    raise KeyError(f"caso desconhecido: {caso_id}")


def verificar_sincronia() -> list[str]:
    """Confere que os números do rótulo batem com o banco.

    Um conjunto rotulado que saiu de sincronia com o dado mede o passado. Esta
    função é chamada por avaliar.py antes de qualquer execução: é barato, e
    evita uma tarde inteira perseguindo uma "regressão" que era só um número
    desatualizado aqui em cima.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    import db

    problemas = []
    for esperado in (ARROZ, REFRI, FEIJAO):
        linha = db.buscar_produto_por_id(esperado["id"])
        if linha is None:
            problemas.append(f"{esperado['id']} não existe no banco")
            continue
        if linha["estoque_atual"] != esperado["estoque"]:
            problemas.append(
                f"{esperado['id']}: rótulo diz estoque {esperado['estoque']}, "
                f"banco diz {linha['estoque_atual']}")
        if linha["estoque_minimo"] != esperado["minimo"]:
            problemas.append(
                f"{esperado['id']}: rótulo diz mínimo {esperado['minimo']}, "
                f"banco diz {linha['estoque_minimo']}")
    return problemas
