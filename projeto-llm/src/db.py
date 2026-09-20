# Parte 1 — camada de acesso ao banco.
#
# Este é o requisito 4.2 da entrega: pelo menos uma ferramenta do agente
# precisa atravessar a fronteira do processo e falar com SOFTWARE TRADICIONAL,
# não com um dicionário Python no meio do arquivo. Aqui é SQLite.
#
# As ferramentas do agente (ferramentas.py) NUNCA escrevem SQL diretamente —
# elas chamam as funções deste módulo. No dia em que este banco virar servidor
# MCP (Parte 2) ou Postgres, só este arquivo muda.

import re
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "dados" / "estoque.db"


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def banco_existe() -> bool:
    return DB_PATH.exists()


def inicializar_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fornecedores (
        id            TEXT PRIMARY KEY,
        nome          TEXT NOT NULL,
        prazo_dias    INTEGER NOT NULL,
        pedido_minimo INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS produtos (
        id                   TEXT PRIMARY KEY,
        nome                 TEXT NOT NULL,
        categoria            TEXT NOT NULL,
        estoque_atual        INTEGER NOT NULL,
        estoque_minimo       INTEGER NOT NULL,
        venda_media_diaria   REAL NOT NULL,
        preco_unitario       REAL NOT NULL,
        fornecedor_id        TEXT NOT NULL REFERENCES fornecedores(id)
    );

    CREATE TABLE IF NOT EXISTS orcamento (
        id         INTEGER PRIMARY KEY CHECK (id = 1),
        disponivel REAL NOT NULL
    );

    -- chave = chave de IDEMPOTENCIA da solicitacao (nota 02 da aula 05):
    -- identifica a operacao, nao a tentativa. Reexecutar com a mesma chave
    -- nao duplica a solicitacao.
    CREATE TABLE IF NOT EXISTS solicitacoes (
        chave           TEXT PRIMARY KEY,
        produto_id      TEXT NOT NULL,
        quantidade      INTEGER NOT NULL,
        custo_estimado  REAL NOT NULL,
        status          TEXT NOT NULL,
        criado_em       TEXT NOT NULL
    );
    """)
    con.commit()


# ------------------------------------------------------------------- a busca
#
# O operador digita "o arroz de 5kg", não "ARROZ_5KG". A primeira versão desta
# camada fazia LIKE com o TERMO INTEIRO entre curingas, e por isso
# "arroz de 5kg" NUNCA casava com o nome cadastrado "Arroz 5kg" — a preposição
# no meio matava o casamento. O efeito no agente está nos logs do esboço: o
# primeiro passo de quase toda execução era um "produto não encontrado" falso,
# e num dos casos o modelo desistiu e disse ao operador que houve erro no
# sistema.
#
# Pior: aquele bug CONTAMINAVA O VERIFICADOR. O caso difícil #3 é "registro
# inexistente"; com a busca quebrada ele ficava indistinguível de "o nome foi
# escrito de outro jeito", e o conjunto rotulado media o bug em vez do agente.
#
# A versão abaixo casa POR TOKEN: normaliza acento e caixa, joga fora as
# palavras vazias e exige que todos os tokens restantes apareçam no nome ou no
# id. "feijão de 1kg" -> {feijao, 1kg} -> casa "Feijão 1kg"; "iogurte de
# morango" -> {iogurte, morango} -> continua não casando, que é o correto.

# Palavras que o operador digita e que não identificam produto nenhum.
# "litro"/"litros" está aqui porque o cadastro escreve "2L": sem descartá-las,
# "refrigerante de 2 litros" não casa com "Refrigerante 2L".
VAZIAS = {
    "de", "do", "da", "dos", "das", "o", "a", "os", "as", "um", "uma",
    "e", "em", "no", "na", "pra", "para", "com", "por",
    "litro", "litros", "lt", "unidade", "unidades", "pacote", "pacotes",
    "produto", "estoque",
}


def normalizar(texto: str) -> str:
    """Minúscula, sem acento. 'Feijão' e 'feijao' têm de casar."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def tokenizar(termo: str) -> list[str]:
    """Quebra o termo em tokens úteis para a busca.

    Guarda-chuva importante: se TUDO for palavra vazia (o operador digitou só
    "o produto"), devolve os tokens originais em vez de uma lista vazia — uma
    lista vazia casaria com o catálogo inteiro, que é o pior resultado
    possível para uma busca.
    """
    brutos = [t for t in re.split(r"[^a-z0-9]+", normalizar(termo)) if t]
    uteis = [t for t in brutos if t not in VAZIAS]
    return uteis or brutos


def _casa(linha: sqlite3.Row, tokens: list[str]) -> bool:
    """Todos os tokens precisam aparecer no nome ou no id (AND, não OR).

    AND e não OR de propósito: com OR, "arroz 5kg" casaria com qualquer
    produto que tivesse "5kg" no nome, e a desambiguação viraria ruído.
    """
    alvo = normalizar(f"{linha['nome']} {linha['id']}")
    return all(t in alvo for t in tokens)


def buscar_produtos(termo: str) -> list[sqlite3.Row]:
    """TODOS os candidatos, não `LIMIT 1`.

    Devolver a lista inteira é o que permite a ferramenta distinguir três
    situações diferentes — nenhum, um, vários — em vez de chutar o primeiro.
    O caso "vários" é o que gera a pergunta de desambiguação ao operador.
    """
    tokens = tokenizar(termo)
    con = conectar()
    try:
        linhas = con.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    finally:
        con.close()
    return [linha for linha in linhas if _casa(linha, tokens)]


def buscar_produto_por_id(produto_id: str) -> sqlite3.Row | None:
    """Busca exata por id — para as ferramentas que já receberam o id de uma
    consulta anterior, onde não faz sentido tolerar texto aproximado."""
    con = conectar()
    try:
        return con.execute("SELECT * FROM produtos WHERE id = ?",
                           (produto_id,)).fetchone()
    finally:
        con.close()


def listar_nomes_produtos() -> list[str]:
    con = conectar()
    try:
        return [r["nome"] for r in
                con.execute("SELECT nome FROM produtos ORDER BY nome")]
    finally:
        con.close()


def buscar_fornecedores(termo: str) -> list[sqlite3.Row]:
    tokens = tokenizar(termo)
    con = conectar()
    try:
        linhas = con.execute("SELECT * FROM fornecedores ORDER BY nome").fetchall()
    finally:
        con.close()
    return [linha for linha in linhas if _casa(linha, tokens)]


def buscar_fornecedor_por_id(fornecedor_id: str) -> sqlite3.Row | None:
    con = conectar()
    try:
        return con.execute("SELECT * FROM fornecedores WHERE id = ?",
                           (fornecedor_id,)).fetchone()
    finally:
        con.close()


def listar_nomes_fornecedores() -> list[str]:
    con = conectar()
    try:
        return [r["nome"] for r in
                con.execute("SELECT nome FROM fornecedores ORDER BY nome")]
    finally:
        con.close()


def orcamento_disponivel() -> float:
    con = conectar()
    try:
        linha = con.execute(
            "SELECT disponivel FROM orcamento WHERE id = 1").fetchone()
        return linha["disponivel"]
    finally:
        con.close()


# ---------------------------------------------------------------- escrita

def obter_solicitacao(chave: str) -> sqlite3.Row | None:
    con = conectar()
    try:
        return con.execute("SELECT * FROM solicitacoes WHERE chave = ?",
                           (chave,)).fetchone()
    finally:
        con.close()


def registrar_solicitacao(chave: str, produto_id: str, quantidade: int,
                          custo_estimado: float, status: str,
                          criado_em: str) -> None:
    """ESCRITA real no banco. Se `status` == 'criada', debita o orçamento na
    MESMA transação — orçamento e solicitação não podem divergir."""
    con = conectar()
    try:
        con.execute(
            "INSERT INTO solicitacoes (chave, produto_id, quantidade, "
            "custo_estimado, status, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
            (chave, produto_id, quantidade, custo_estimado, status, criado_em),
        )
        if status == "criada":
            con.execute(
                "UPDATE orcamento SET disponivel = disponivel - ? WHERE id = 1",
                (custo_estimado,),
            )
        con.commit()
    finally:
        con.close()
