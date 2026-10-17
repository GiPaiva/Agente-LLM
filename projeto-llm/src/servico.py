"""Fronteira de confiança: regras e transação pertencem ao serviço, não ao LLM."""
import hmac
import json
import secrets
import sqlite3
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager

import db
from config import RAIZ, agora, chave


class RegraNegocio(ValueError):
    pass


class Servico:
    def __init__(self, pasta: Path, aprovacao_horas=24):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.path = self.pasta / "operacao.sqlite"
        self.aprovacao_horas = aprovacao_horas
        with self.conectar() as con:
            db.inicializar_schema(con)
            con.executescript("""
            CREATE TABLE IF NOT EXISTS casos (
              id TEXT PRIMARY KEY, usuario TEXT NOT NULL, proposta TEXT NOT NULL,
              capacidade TEXT NOT NULL, expira TEXT NOT NULL,
              aprovado INTEGER NOT NULL DEFAULT 0, revisado INTEGER NOT NULL,
              status TEXT NOT NULL DEFAULT 'pendente', quantidade INTEGER
            );
            """)
            colunas = {r[1] for r in con.execute("PRAGMA table_info(solicitacoes)")}
            if "caso_id" not in colunas:
                con.execute("ALTER TABLE solicitacoes ADD COLUMN caso_id TEXT")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uma_compra_por_caso ON solicitacoes(caso_id)")
            if not con.execute("SELECT 1 FROM produtos LIMIT 1").fetchone():
                sys.path.insert(0, str(RAIZ / "dados"))
                from gerar_banco import FORNECEDORES, PRODUTOS, ORCAMENTO_INICIAL
                con.executemany("INSERT INTO fornecedores VALUES (?,?,?,?)", FORNECEDORES)
                con.executemany("INSERT INTO produtos VALUES (?,?,?,?,?,?,?,?)", PRODUTOS)
                con.execute("INSERT INTO orcamento VALUES (1,?)", (ORCAMENTO_INICIAL,))
        self.path.chmod(0o600)

    @contextmanager
    def conectar(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def consultar_estoque(self, produto: str) -> dict:
        if not isinstance(produto, str) or not produto.strip():
            return {"erro": "Informe o nome do produto.", "candidatos": []}
        tokens = db.tokenizar(produto)
        with self.conectar() as con:
            todos = con.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
        encontrados = [dict(r) for r in todos if db._casa(r, tokens)]
        if len(encontrados) != 1:
            return {"erro": "termo ambíguo" if encontrados else "produto não encontrado",
                    "candidatos": [r["nome"] for r in encontrados],
                    "produtos_disponiveis": [r["nome"] for r in todos]}
        p = encontrados[0]
        p["abaixo_do_minimo"] = p["estoque_atual"] < p["estoque_minimo"]
        return p

    def consultar_fornecedor(self, fornecedor: str) -> dict:
        with self.conectar() as con:
            row = con.execute("SELECT * FROM fornecedores WHERE id=?", (fornecedor,)).fetchone()
        return dict(row) if row else {"erro": "fornecedor não encontrado"}

    @staticmethod
    def custo(quantidade, preco):
        return float((Decimal(str(preco)) * quantidade).quantize(Decimal("0.01")))

    def calcular_reposicao(self, produto_id: str) -> dict:
        with self.conectar() as con:
            row = con.execute("""SELECT p.*, f.pedido_minimo, f.prazo_dias
                FROM produtos p JOIN fornecedores f ON f.id=p.fornecedor_id WHERE p.id=?""",
                              (produto_id,)).fetchone()
            orcamento = con.execute("SELECT disponivel FROM orcamento WHERE id=1").fetchone()[0]
        if not row:
            return {"erro": "produto_id não existe"}
        p = dict(row)
        q = max(2 * p["estoque_minimo"] - p["estoque_atual"], p["pedido_minimo"])
        p.update(produto_id=p["id"], precisa_repor=p["estoque_atual"] < p["estoque_minimo"],
                 quantidade_recomendada=q, quantidade=q, custo_estimado=self.custo(q, p["preco_unitario"]),
                 orcamento_disponivel=orcamento, limite_sem_aprovacao=500)
        return p

    def preparar(self, caso_id: str, usuario: str, intencao: str, consultado: dict,
                 proposta: dict, revisado=True):
        """Somente coordenador confiável. Não é uma ferramenta MCP/LLM."""
        if intencao != "reposicao" or consultado.get("id") != proposta.get("produto_id"):
            raise RegraNegocio("Compra exige intenção de reposição e consulta do mesmo produto.")
        if not proposta.get("precisa_repor"):
            raise RegraNegocio("Produto não precisa de reposição.")
        with self.conectar() as con:
            con.execute("""INSERT OR IGNORE INTO casos
                (id,usuario,proposta,capacidade,expira,revisado) VALUES (?,?,?,?,?,?)""",
                (caso_id, usuario, json.dumps(proposta), secrets.token_urlsafe(32),
                 (agora() + timedelta(hours=self.aprovacao_horas)).isoformat(), int(revisado)))

    def caso(self, caso_id: str):
        with self.conectar() as con:
            row = con.execute("SELECT * FROM casos WHERE id=?", (caso_id,)).fetchone()
        return dict(row) if row else None

    def decidir(self, caso_id: str, decisao: dict):
        with self.conectar() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM casos WHERE id=?", (caso_id,)).fetchone()
            if not row:
                raise RegraNegocio("Caso não encontrado.")
            if row["status"] != "pendente":
                return row["status"]
            if agora().isoformat() >= row["expira"]:
                status = "expirada"
            elif decisao["acao"] == "rejeitar":
                status = "rejeitada"
            else:
                status = "pendente"
            con.execute("UPDATE casos SET aprovado=?,quantidade=?,status=? WHERE id=?",
                        (int(status == "pendente"), decisao.get("quantidade"), status, caso_id))
            return status

    def finalizar(self, caso_id: str, capacidade: str) -> dict:
        """Exige capacidade privada. Validação e débito na MESMA transação."""
        with self.conectar() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM casos WHERE id=?", (caso_id,)).fetchone()
            if not row or not hmac.compare_digest(row["capacidade"], capacidade):
                raise RegraNegocio("Autorização de escrita inválida.")
            existente = con.execute("SELECT * FROM solicitacoes WHERE caso_id=?", (caso_id,)).fetchone()
            if existente:
                return {**dict(existente), "ja_existia": True}
            if row["status"] != "pendente" or agora().isoformat() >= row["expira"]:
                raise RegraNegocio("Ação encerrada ou aprovação expirada.")
            if not row["revisado"]:
                raise RegraNegocio("Revisão não aprovou a ação.")
            proposta = json.loads(row["proposta"])
            p = con.execute("""SELECT p.*,f.pedido_minimo FROM produtos p
                JOIN fornecedores f ON f.id=p.fornecedor_id WHERE p.id=?""",
                            (proposta["produto_id"],)).fetchone()
            if not p or p["estoque_atual"] >= p["estoque_minimo"]:
                raise RegraNegocio("Estoque atual não autoriza reposição.")
            if p["preco_unitario"] != proposta["preco_unitario"] or p["fornecedor_id"] != proposta["fornecedor_id"]:
                raise RegraNegocio("Preço ou fornecedor mudou; faça uma nova consulta.")
            q = row["quantidade"] if row["quantidade"] is not None else proposta["quantidade"]
            if type(q) is not int or q <= 0 or q < p["pedido_minimo"]:
                raise RegraNegocio("Quantidade inválida ou abaixo do pedido mínimo do fornecedor.")
            recomendada = max(2 * p["estoque_minimo"] - p["estoque_atual"], p["pedido_minimo"])
            if not row["aprovado"] and q != recomendada:
                raise RegraNegocio("Quantidade automática difere da recomendação atual.")
            custo = self.custo(q, p["preco_unitario"])
            if custo > 500 and not row["aprovado"]:
                raise RegraNegocio("Compra acima de R$ 500 exige aprovação do gerente.")
            saldo = con.execute("SELECT disponivel FROM orcamento WHERE id=1").fetchone()[0]
            if custo > saldo:
                raise RegraNegocio("Orçamento insuficiente; aprovação não permite ultrapassar o saldo.")
            protocolo = chave({"caso": caso_id, "produto": p["id"], "quantidade": q,
                               "fornecedor": p["fornecedor_id"]})
            con.execute("""INSERT INTO solicitacoes
                (chave,produto_id,quantidade,custo_estimado,status,criado_em,caso_id)
                VALUES (?,?,?,?,'criada',?,?)""", (protocolo, p["id"], q, custo, agora().isoformat(), caso_id))
            con.execute("UPDATE orcamento SET disponivel=ROUND(disponivel-?,2) WHERE id=1", (custo,))
            con.execute("UPDATE casos SET status='criada' WHERE id=?", (caso_id,))
            return {"chave": protocolo, "produto_id": p["id"], "quantidade": q,
                    "custo_estimado": custo, "status": "criada", "caso_id": caso_id, "ja_existia": False}

    def pendentes(self):
        with self.conectar() as con:
            con.execute("UPDATE casos SET status='expirada' WHERE status='pendente' AND expira<=?", (agora().isoformat(),))
            return [{"caso_id": r["id"], "usuario": r["usuario"], "expira": r["expira"],
                     "proposta": json.loads(r["proposta"])} for r in con.execute(
                         "SELECT * FROM casos WHERE status='pendente'")]

    def resultado(self, caso_id):
        with self.conectar() as con:
            row = con.execute("SELECT * FROM solicitacoes WHERE caso_id=?", (caso_id,)).fetchone()
        return dict(row) if row else None
