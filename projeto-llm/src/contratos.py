"""Contratos públicos: texto entra; um objeto validado sai, inclusive na recusa."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    # Modelos locais dizem "não informado" com null (medido: gemma em "Preciso
    # repor."). Para os opcionais, null e o padrão significam o mesmo; a intenção
    # continua obrigatória e estrita.
    @field_validator("produto", "relato_falta", "pergunta", mode="before")
    @classmethod
    def nulo_e_ausente(cls, valor, info):
        return cls.model_fields[info.field_name].default if valor is None else valor


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
