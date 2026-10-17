"""Índices separados: documentos curados, episódios e fatos aprendidos."""
import json
import re
import sqlite3
from datetime import timedelta
from pathlib import Path
from contextlib import contextmanager

import numpy as np
from config import RAIZ, Config, agora, chave


class EmbeddingLocal:
    def __init__(self, config: Config):
        from fastembed import TextEmbedding
        from tokenizers import Tokenizer
        self.modelo = TextEmbedding(model_name=config.embedding,
                                   cache_dir=str(config.cache_modelos),
                                   providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_str(self.modelo.model.tokenizer.to_str())
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()

    def contar(self, texto):
        return len(self.tokenizer.encode(texto).ids)

    def vetores(self, textos):
        return np.asarray(list(self.modelo.embed(textos)), dtype=np.float32)


class Conhecimento:
    def __init__(self, config: Config, embedding=None, corpus=None):
        self.config = config
        config.runtime.mkdir(parents=True, exist_ok=True)
        self.path = config.runtime / "conhecimento.sqlite"
        self._embedding = embedding
        self.corpus = Path(corpus or RAIZ / "dados" / "corpus")
        parametros = config.runtime / "rag-parametros.json"
        if not parametros.exists():
            parametros = RAIZ / "dados" / "rag-config.json"
        self.parametros = json.loads(parametros.read_text()) if parametros.exists() else {
            "k": config.rag_k, "limiar": config.rag_limiar, "calibrado": False}
        with self.conectar() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS trechos (id TEXT PRIMARY KEY, doc TEXT, secao TEXT,
                texto TEXT, metadados TEXT, vetor BLOB);
            CREATE TABLE IF NOT EXISTS episodios (id TEXT PRIMARY KEY, usuario TEXT,
                thread TEXT, texto TEXT, quando TEXT, vetor BLOB);
            CREATE TABLE IF NOT EXISTS fatos (id TEXT PRIMARY KEY, usuario TEXT,
                chave TEXT, valor TEXT, quando TEXT, thread TEXT);
            CREATE TABLE IF NOT EXISTS controle (chave TEXT PRIMARY KEY, valor TEXT);
            """)

    @contextmanager
    def conectar(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    @property
    def embedding(self):
        if self._embedding is None:
            self._embedding = EmbeddingLocal(self.config)
        return self._embedding

    def cortar(self, texto, cabecalho, max_tokens=120):
        palavras = texto.split()
        inicio = 0
        while inicio < len(palavras):
            fim = inicio
            while fim < len(palavras) and self.embedding.contar(
                    cabecalho + "\n" + " ".join(palavras[inicio:fim + 1])) <= max_tokens:
                fim += 1
            if fim == inicio:
                raise ValueError("Cabeçalho ou palavra excede o limite do embedding.")
            yield cabecalho + "\n" + " ".join(palavras[inicio:fim])
            if fim == len(palavras):
                break
            inicio = max(inicio + 1, fim - 10)

    def indexar(self, forcar=False):
        arquivos = sorted(self.corpus.glob("*.md"))
        assinatura = chave({"modelo": self.config.embedding, "implementacao": type(self.embedding).__name__,
                            "arquivos": {p.name: p.read_text() for p in arquivos}, "corte": self.config.corte, "tokens": 120})
        with self.conectar() as con:
            anterior = con.execute("SELECT valor FROM controle WHERE chave='corpus'").fetchone()
        if anterior and anterior[0] == assinatura and not forcar:
            return
        trechos = []
        for arquivo in arquivos:
            texto = arquivo.read_text(encoding="utf-8")
            metadados = json.loads(re.search(r"<!--(.*?)-->", texto, re.S).group(1))
            for secao in re.split(r"(?m)^## ", texto)[1:]:
                titulo, _, corpo = secao.partition("\n")
                partes = [corpo[j:j + 200] for j in range(0, len(corpo), 160)] if self.config.corte == "caracteres" else [corpo]
                cortados = [trecho for parte in partes for trecho in self.cortar(parte, f"{metadados['id']} > {titulo}")]
                for i, trecho in enumerate(cortados):
                    trechos.append((f"{metadados['id']}:{titulo.split()[0]}:{i}",
                                    metadados["id"], titulo, trecho, json.dumps(metadados)))
        vetores = self.embedding.vetores([t[3] for t in trechos])
        with self.conectar() as con:
            con.execute("DELETE FROM trechos")
            con.executemany("INSERT INTO trechos VALUES (?,?,?,?,?,?)",
                            [(*t, v.astype(np.float32).tobytes()) for t, v in zip(trechos, vetores)])
            con.execute("INSERT OR REPLACE INTO controle VALUES ('corpus',?)", (assinatura,))

    @staticmethod
    def similaridade(a, blob):
        b = np.frombuffer(blob, dtype=np.float32)
        norma = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / norma) if norma else 0.0

    def buscar_documentos(self, consulta: str, fornecedor: str = "", k=None, limiar=None):
        self.indexar()
        vetor = self.embedding.vetores([consulta])[0]
        with self.conectar() as con:
            rows = con.execute("SELECT * FROM trechos").fetchall()
        candidatos = []
        for r in rows:
            meta = json.loads(r["metadados"])
            if meta["status"] != "vigente" or meta["vigencia"] > agora().date().isoformat():
                continue
            if fornecedor and meta.get("fornecedor") not in (None, fornecedor):
                continue
            score = self.similaridade(vetor, r["vetor"])
            if score >= (self.parametros["limiar"] if limiar is None else limiar):
                candidatos.append({"id": r["id"], "tipo": "documento", "trecho": r["texto"],
                                   "score": round(score, 5), "metadados": meta})
        candidatos.sort(key=lambda x: (-x["score"], x["id"]))
        return candidatos[:k or self.parametros["k"]]

    def guardar_episodio(self, usuario, thread, conteudo):
        # Um resumo de resultado confirmado; nunca a entrada bruta ou instruções do usuário.
        texto = json.dumps(conteudo, ensure_ascii=False, sort_keys=True)
        ident = chave({"usuario": usuario, "thread": thread, "conteudo": conteudo})
        with self.conectar() as con:
            if con.execute("SELECT 1 FROM episodios WHERE id=?", (ident,)).fetchone():
                return {"id": ident, "ja_existia": True}
        # Identificadores aleatórios e protocolos servem à auditoria, não à similaridade.
        contexto = " ".join(str(conteudo[k]).replace("_", " ") for k in
                            ("produto", "nome", "status", "divergencia") if k in conteudo)
        vetor = self.embedding.vetores([contexto])[0]
        with self.conectar() as con:
            gravou = con.execute("INSERT OR IGNORE INTO episodios VALUES (?,?,?,?,?,?)",
                        (ident, usuario, thread, texto, agora().isoformat(), vetor.tobytes()))
            novo = gravou.rowcount == 1
        return {"id": ident, "ja_existia": not novo}

    def lembrar(self, usuario, consulta):
        self.decair()
        with self.conectar() as con:
            rows = con.execute("SELECT * FROM episodios WHERE usuario=?", (usuario,)).fetchall()
        if not rows:
            return []
        vetor = self.embedding.vetores([consulta])[0]
        lembrancas = [(self.similaridade(vetor, r["vetor"]), r) for r in rows]
        return [{"id": r["id"], "tipo": "memoria", "trecho": r["texto"]}
                for score, r in sorted(lembrancas, key=lambda x: -x[0])[:2] if score >= 0.4]

    def guardar_fato(self, usuario, alias, produto_id, thread, caso_id):
        # Nova confirmação é um novo evento; replay do mesmo caso é a mesma escrita.
        ident = chave({"usuario": usuario, "alias": alias, "produto_id": produto_id, "thread": thread, "caso": caso_id})
        with self.conectar() as con:
            gravou = con.execute("INSERT OR IGNORE INTO fatos VALUES (?,?,?,?,?,?)",
                        (ident, usuario, alias, produto_id, agora().isoformat(), thread))
            novo = gravou.rowcount == 1
        return {"id": ident, "ja_existia": not novo}

    def fato(self, usuario, alias):
        with self.conectar() as con:
            row = con.execute("SELECT valor FROM fatos WHERE usuario=? AND chave=? ORDER BY quando DESC,id DESC LIMIT 1",
                              (usuario, alias)).fetchone()
        return row[0] if row else None

    def decair(self):
        with self.conectar() as con:
            corte = (agora() - timedelta(days=self.config.memoria_dias)).isoformat()
            return con.execute("DELETE FROM episodios WHERE quando<?", (corte,)).rowcount

    def remover_thread(self, thread):
        with self.conectar() as con:
            con.execute("DELETE FROM episodios WHERE thread=?", (thread,))
            con.execute("DELETE FROM fatos WHERE thread=?", (thread,))
