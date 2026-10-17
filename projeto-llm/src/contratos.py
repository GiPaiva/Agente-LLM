"""Contratos públicos: texto entra; um objeto validado sai, inclusive na recusa."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Contrato(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Fonte(Contrato):
    id: str
    tipo: Literal["registro", "documento", "memoria"]
    trecho: str


class Interpretacao(Contrato):
    intencao: Literal["consulta", "reposicao", "politica", "fora_escopo"]
    produto: str = ""
    relato_falta: bool = False
    pergunta: str = ""


class RespostaModelo(Contrato):
    resultado: str = Field(min_length=1, max_length=3000)
    fontes: list[str]
    suficiente: bool


class Parecer(Contrato):
    aprovado: bool
    motivos: list[str]
    fontes: list[str]


class DecisaoHumana(Contrato):
    acao: Literal["aprovar", "rejeitar"]
    quantidade: int | None = Field(default=None, gt=0)


class Saida(Contrato):
    resultado: str
    fontes: list[Fonte] = Field(default_factory=list)
    suficiente: bool
    status: Literal["respondido", "recusado", "esclarecimento", "aguardando_aprovacao",
                    "criada", "rejeitada", "expirada", "falha"]
    thread_id: str
    caso_id: str
    perguntas: list[str] = Field(default_factory=list)
    aprovacao: dict | None = None
    solicitacao: dict | None = None
    termino: str
