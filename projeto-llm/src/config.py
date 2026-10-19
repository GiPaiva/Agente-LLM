"""Configuração explícita. Segredos nunca fazem parte do contexto ou trace."""
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def agora() -> datetime:
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


def chave(conteudo) -> str:
    return hashlib.sha256(json.dumps(conteudo, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def versao() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RAIZ,
                                         text=True).strip()
        sujo = bool(subprocess.check_output(["git", "status", "--porcelain"],
                                            cwd=RAIZ, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, sujo = "sem-git", True
    fontes = {str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest()
              for pasta in (RAIZ / "src", RAIZ / "dados")
              for p in sorted(pasta.rglob("*"))
              if p.is_file() and p.suffix in {".py", ".md", ".json"}}
    fontes["requirements.txt"] = hashlib.sha256((RAIZ / "requirements.txt").read_bytes()).hexdigest()
    return {"commit": commit, "working_tree_modificado": sujo,
            "sha256_fontes": chave(fontes), "arquivos": fontes}


@dataclass(frozen=True)
class Config:
    runtime: Path = RAIZ / "runtime"
    max_modelo: int = 8
    max_ferramentas: int = 8
    max_tokens: int = 60_000
    max_segundos: float = 600
    max_contexto_caracteres: int = 24_000  # estimativa conservadora, não tokens
    timeout: float = 120  # por chamada; modelo de raciocínio local leva 14–25 s
    max_tokens_resposta: int = 4096  # inclui o raciocínio do modelo "thinking"
    temperatura: float = 0.0
    retries: int = 2
    # Decisão que virou parâmetro da lib (§6.6). langchain_core declara 25, mas o
    # langgraph==1.2.15 fixado usa o próprio padrão, 10007 (medido em
    # logs/diagnostico/recursion-limit-padrao.txt), o que na prática remove o teto. Declaramos 64 (nós fixos + 8 voltas
    # agente⇄ferramentas, com folga) para que os nossos tetos disparem antes.
    recursion_limit: int = 64
    aprovacao_horas: float = 24
    memoria_dias: int = 30
    embedding: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    cache_modelos: Path = RAIZ / "runtime" / "modelos"
    rag_k: int = 3
    rag_limiar: float = 0.55  # provisório até calibrar com o corpus local
    corte: str = "estrutura"
    preco_entrada: float = 0.0
    preco_saida: float = 0.0

    @classmethod
    def ambiente(cls):
        def numero(nome, padrao, tipo=float):
            return tipo(os.environ.get(nome) or padrao)
        return cls(runtime=Path(os.environ.get("AGENTE_RUNTIME") or RAIZ / "runtime"),
                   timeout=numero("LLM_TIMEOUT", cls.timeout),
                   max_tokens_resposta=numero("LLM_MAX_TOKENS", cls.max_tokens_resposta, int),
                   temperatura=numero("LLM_TEMPERATURA", cls.temperatura),
                   max_segundos=numero("AGENTE_MAX_SEGUNDOS", cls.max_segundos),
                   preco_entrada=float(os.environ.get("LLM_PRECO_ENTRADA_USD_MILHAO") or 0),
                   preco_saida=float(os.environ.get("LLM_PRECO_SAIDA_USD_MILHAO") or 0))
