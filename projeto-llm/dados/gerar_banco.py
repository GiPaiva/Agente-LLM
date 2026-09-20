# Gera dados/estoque.db com dados SIMULADOS (item 2.8 da entrega).
#
# Os dados são desenhados para PRESERVAR A DIFICULDADE do problema. Um dado
# fácil teria todo produto perguntado abaixo do mínimo (o agente sempre compra)
# ou sempre acima (o agente nunca compra). Aqui existem as duas situações, mais
# um produto que não existe, mais um par de nomes parecidos que força
# desambiguação. Cada caso difícil está nomeado em dados/casos-dificeis.md.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import db  # noqa: E402

FORNECEDORES = [
    # id, nome, prazo_dias, pedido_minimo
    ("FORN_A", "Fornecedor A (mercearia seca)", 2, 50),
    ("FORN_B", "Fornecedor B (bebidas)", 5, 30),
]

PRODUTOS = [
    # id, nome, categoria, estoque_atual, estoque_minimo,
    # venda_media_diaria, preco_unitario, fornecedor_id

    # CASO 1 — SIMPLES: estoque bem abaixo do mínimo, giro alto.
    # Deve recomendar reposição e criar a solicitação. O custo passa de R$ 500,
    # então ela nasce como `aguardando_aprovacao_gerente` — o caminho que
    # exercita a regra de orçamento.
    ("ARROZ_5KG", "Arroz 5kg", "mercearia", 12, 30, 8.0, 18.50, "FORN_A"),

    # CASO 2 — DIVERGÊNCIA: o sistema mostra estoque folgado (85, contra um
    # mínimo de 20), mas o operador AFIRMA que "o refrigerante está acabando".
    # O agente tem de confiar no dado consultado e RELATAR a divergência, em
    # vez de comprar às cegas ou simplesmente dizer "está tranquilo".
    ("REFRIGERANTE_2L", "Refrigerante 2L", "bebidas", 85, 20, 5.0, 7.90, "FORN_B"),

    # CASO 4 — NÃO deve disparar a ação principal: estoque acima do mínimo e
    # giro baixo. Uma pergunta genérica sobre este produto não pode terminar em
    # solicitação de compra.
    ("FEIJAO_1KG", "Feijão 1kg", "mercearia", 40, 25, 3.0, 8.20, "FORN_A"),

    # CASO 5 — AMBIGUIDADE: dois açúcares. "o açúcar" casa com os dois, e o
    # agente precisa PERGUNTAR qual, em vez de escolher um sozinho. É o caso
    # que exercita o que o item 2.2 do enunciado chama de complexidade real de
    # interação: o que o usuário não informa de primeira.
    ("ACUCAR_1KG", "Açúcar Refinado 1kg", "mercearia", 22, 20, 4.0, 5.40, "FORN_A"),
    ("ACUCAR_5KG", "Açúcar Refinado 5kg", "mercearia", 9, 15, 2.0, 21.90, "FORN_A"),

    # Produto de apoio: abaixo do mínimo e BARATO, para exercitar o outro ramo
    # da regra de orçamento — solicitação criada direto, com status `criada`,
    # sem passar pelo gerente.
    ("SAL_1KG", "Sal 1kg", "mercearia", 8, 20, 1.5, 2.30, "FORN_A"),
]

# Orçamento mensal disponível. Usado para decidir se uma solicitação pode ser
# criada direto ou fica pendente de aprovação do gerente — teto de R$ 500 sem
# aprovação, regra herdada de ideia-evolucao/v2.md, seção 5.
ORCAMENTO_INICIAL = 1200.00


def gerar() -> None:
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = db.conectar()
    try:
        db.inicializar_schema(con)
        con.executemany("INSERT INTO fornecedores VALUES (?, ?, ?, ?)", FORNECEDORES)
        con.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?, ?)", PRODUTOS)
        con.execute("INSERT INTO orcamento VALUES (1, ?)", (ORCAMENTO_INICIAL,))
        con.commit()
    finally:
        con.close()

    print(f"Banco gerado em {db.DB_PATH} "
          f"({len(PRODUTOS)} produtos, {len(FORNECEDORES)} fornecedores, "
          f"orçamento R$ {ORCAMENTO_INICIAL:.2f})")


def gerar_silencioso() -> None:
    """Mesma coisa, sem imprimir — usada por src/avaliar.py, que regenera o
    banco antes de CADA execução. Sem isso, uma solicitação criada na volta
    anterior tornaria a seguinte idempotente e o caso passaria sem o agente ter
    feito nada."""
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        gerar()


if __name__ == "__main__":
    gerar()
