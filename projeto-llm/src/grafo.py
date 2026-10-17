"""Sistema entregue: um StateGraph persistente, compartilhado pela CLI e inspeção."""
import json
import operator
import sqlite3
import time
import re
import db
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Annotated, TypedDict
from uuid import uuid4

from jsonschema import validate
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from config import RAIZ, Config, agora, chave, versao
from contratos import DecisaoHumana, Fonte, Interpretacao, Parecer, RespostaModelo, Saida
from conhecimento import Conhecimento
from modelo import Modelo
from servico import RegraNegocio, Servico
from transporte import ClienteMCP, ferramentas_leitura, schema


class Estado(TypedDict, total=False):
    texto: str
    usuario: str
    thread_id: str
    caso_id: str
    mensagens: Annotated[list[dict], operator.add]
    eventos: Annotated[list[dict], operator.add]
    interpretacao: dict
    produto: dict
    proposta: dict | None
    evidencias: dict
    lembrancas: list[dict]
    chamada: dict | None
    candidata: dict | None
    parecer: dict | None
    decisao: dict | None
    saida: dict | None
    erro: str | None
    n_modelo: int
    n_ferramentas: int
    n_recuperacoes: int
    tokens_entrada: int
    tokens_saida: int
    processamento_s: float
    correcoes: int
    alias_pendente: str
    candidatos_pendentes: list[str]
    correcao_humana: str | None
    uso_incompleto: bool


def ferramenta_saida(nome, contrato):
    return {"type": "function", "function": {"name": nome,
        "description": "Emite o objeto validado desta etapa.", "parameters": contrato.model_json_schema()}}


class Aplicacao:
    def __init__(self, config=None, modelo=None, embedding=None, multi=True, usar_mcp=True):
        self.config = config or Config.ambiente()
        self.servico = Servico(self.config.runtime, self.config.aprovacao_horas)
        self.conhecimento = Conhecimento(self.config, embedding)
        self.modelo = modelo or Modelo(self.config)
        self.multi = multi
        self.mcp = ClienteMCP(self.config) if usar_mcp else None
        self.conexao = sqlite3.connect(self.config.runtime / "checkpoints.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(self.conexao)
        self._relogio = ContextVar("relogio_ativo", default=None)
        self.grafo = self._compilar()  # uma vez por processo/aplicação, nunca por pergunta

    def close(self):
        if self.mcp:
            self.mcp.close()
        self.conexao.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _config(self, thread):
        return {"configurable": {"thread_id": thread}, "recursion_limit": self.config.recursion_limit}

    def _contadores(self, s):
        return {**{k: s.get(k, 0) for k in ("n_modelo", "n_ferramentas", "n_recuperacoes",
                "tokens_entrada", "tokens_saida", "uso_incompleto")},
                "processamento_s": self._tempo_ativo(s)}

    def _tempo_ativo(self, s):
        relogio = self._relogio.get()
        return (relogio[0] + time.monotonic() - relogio[1]
                if relogio else s.get("processamento_s", 0))

    def _medir_no(self, func):
        @wraps(func)
        def executar(s):
            # Um intervalo por nó inclui memória, validação e preparação, sem
            # contar novamente as chamadas internas nem a espera entre resumes.
            token = self._relogio.set((s.get("processamento_s", 0), time.monotonic()))
            try:
                atualizacao = func(s)
                return {**atualizacao, "processamento_s": self._tempo_ativo(s)}
            finally:
                self._relogio.reset(token)
        return executar

    def _limite(self, s, ferramenta=False):
        c = self.config
        if s.get("n_modelo", 0) >= c.max_modelo and not ferramenta:
            return "teto de chamadas ao modelo"
        if s.get("n_ferramentas", 0) >= c.max_ferramentas and ferramenta:
            return "teto de ferramentas"
        if s.get("tokens_entrada", 0) + s.get("tokens_saida", 0) >= c.max_tokens:
            return "teto de tokens"
        if self._tempo_ativo(s) >= c.max_segundos:
            return "teto de processamento ativo"
        return None

    def _prompt(self, nome):
        return (RAIZ / "src" / "prompts" / f"{nome}.md").read_text()

    def _chamar(self, s, mensagens, tools, obrigatoria=None, agente="reposicao"):
        if limite := self._limite(s):
            raise RuntimeError(limite)
        try:
            r = self.modelo.chamar(mensagens, tools, obrigatoria=obrigatoria, agente=agente,
                                  restante=self.config.max_segundos - self._tempo_ativo(s),
                                  max_tentativas=self.config.max_modelo - s["n_modelo"])
            s["n_modelo"] += r.get("tentativas", 1)
            s["tokens_entrada"] += r.get("entrada", 0)
            s["tokens_saida"] += r.get("saida", 0)
            if r.get("uso_disponivel") is False:
                s["uso_incompleto"] = True
            return r
        except Exception as erro:
            tentativas = getattr(erro, "tentativas", 1)
            s["n_modelo"] += tentativas
            if tentativas:
                s["uso_incompleto"] = True
            return {"nome": "", "argumentos": {}, "erro": str(erro), "fatal": True,
                    "tentativas": tentativas, "uso_disponivel": False}

    def _ler(self, s, nome, argumentos, agente="reposicao"):
        if limite := self._limite(s, ferramenta=True):
            raise RuntimeError(limite)
        if nome == "registrar_compra" or nome not in {t["function"]["name"] for t in ferramentas_leitura()}:
            raise ValueError("Agentes não possuem permissão de escrita.")
        validate(argumentos, schema(nome))
        s["n_ferramentas"] += 1
        if self.mcp:
            resultado = self.mcp.chamar(nome, argumentos)
        elif nome == "buscar_documentos":
            resultado = self.conhecimento.buscar_documentos(**argumentos)
        else:
            resultado = getattr(self.servico, nome)(**argumentos)
        if nome == "buscar_documentos":
            s["n_recuperacoes"] += 1
        return resultado

    def _evento(self, s, tipo, agente="codigo", **dados):
        return {"caso_id": s["caso_id"], "quando": agora().isoformat(), "tipo": tipo,
                "agente": agente, **dados}

    def _saida(self, s, status, resultado, suficiente=False, termino=None, **extra):
        return Saida(resultado=resultado, fontes=[Fonte.model_validate(x) for x in s.get("evidencias", {}).values()],
                     suficiente=suficiente, status=status, thread_id=s["thread_id"], caso_id=s["caso_id"],
                     termino=termino or status, **extra).model_dump()

    def _interpretar(self, s):
        if not s["texto"].strip():
            return {"interpretacao": Interpretacao(intencao="consulta").model_dump()}
        if len(s["texto"]) > self.config.max_contexto_caracteres:
            return {"saida": self._saida(s, "recusado", "Entrada longa demais; descreva um pedido mais curto.")}
        msgs = [{"role": "system", "content": self._prompt("triagem")},
                {"role": "user", "content": json.dumps({"texto": s["texto"],
                  "esclarecimento_anterior": s.get("alias_pendente", ""),
                  "candidatos": s.get("candidatos_pendentes", []),
                  "contexto_recente": s.get("mensagens", [])[-4:]}, ensure_ascii=False)}]
        eventos = []
        try:
            for tentativa in range(2):
                r = self._chamar(s, msgs, [ferramenta_saida("extrair_intencao", Interpretacao)], "extrair_intencao")
                eventos.append(self._evento(s, "modelo", "reposicao", etapa="triagem", resposta=r))
                if r.get("fatal"):
                    raise RuntimeError(r["erro"])
                try:
                    if r.get("erro") or r["nome"] != "extrair_intencao":
                        raise ValueError("Use extrair_intencao.")
                    interpretacao = Interpretacao.model_validate(r["argumentos"]).model_dump()
                    return {**self._contadores(s), "interpretacao": interpretacao, "eventos": eventos}
                except (ValueError, ValidationError) as erro:
                    msgs.append({"role": "user", "content": "Corrija o formato estruturado: " + str(erro)[:200]})
            raise ValueError("Contrato da triagem inválido após uma correção.")
        except Exception as erro:
            return {**self._contadores(s), "erro": str(erro), "eventos": eventos}

    def _coletar(self, s):
        i = s["interpretacao"]
        if i["intencao"] == "fora_escopo":
            return {"saida": self._saida(s, "recusado", "Atendo consultas de estoque, reposição e políticas de compra deste mercado simulado.")}
        if i["intencao"] != "politica" and not i["produto"].strip():
            pergunta = "Qual produto você quer consultar ou repor?"
            return {"saida": self._saida(s, "esclarecimento", pergunta, perguntas=[pergunta])}
        eventos, evidencias = [], {}
        try:
            if i["intencao"] == "politica":
                return {"mensagens": [{"role": "user", "content": s["texto"]}], "evidencias": {}}
            produto = self._ler(s, "consultar_estoque", {"produto": i["produto"]})
            eventos.append(self._evento(s, "ferramenta", "reposicao", ferramenta="consultar_estoque",
                                         argumentos={"produto": i["produto"]}, resultado=produto))
            if produto.get("erro"):
                candidatos = produto["candidatos"]
                texto = ("Qual destes produtos: " + ", ".join(candidatos) + "?" if candidatos else
                         "Produto não encontrado no cadastro. Disponíveis: " + ", ".join(produto["produtos_disponiveis"]))
                confirmado = self.conhecimento.fato(s["usuario"], i["produto"])
                if candidatos and confirmado:
                    texto += " Escolha anterior confirmada: " + confirmado + ". Confirme a embalagem novamente."
                return {**self._contadores(s), "eventos": eventos,
                        "alias_pendente": i["produto"] if candidatos else "",
                        "candidatos_pendentes": candidatos,
                        "saida": self._saida(s, "esclarecimento" if candidatos else "recusado", texto,
                                              perguntas=[texto] if candidatos else [])}
            embalagens = set(re.findall(r"\d+(?:kg|l)\b", db.normalizar(s["texto"]).replace(" ", "")))
            embalagem_confirmada = len(embalagens) == 1 and next(iter(embalagens)) in db.normalizar(produto["nome"]).replace(" ", "")
            if embalagem_confirmada and s.get("alias_pendente") and produto["nome"] in s.get("candidatos_pendentes", []):
                self.conhecimento.guardar_fato(s["usuario"], s["alias_pendente"], produto["id"], s["thread_id"], s["caso_id"])
            evidencias["estoque:" + produto["id"]] = {"id": "estoque:" + produto["id"], "tipo": "registro",
                    "trecho": json.dumps(produto, ensure_ascii=False)}
            proposta = None
            if i["intencao"] == "reposicao" and produto["abaixo_do_minimo"]:
                proposta = self._ler(s, "calcular_reposicao", {"produto_id": produto["id"]})
                eventos.append(self._evento(s, "ferramenta", "reposicao", ferramenta="calcular_reposicao",
                                             argumentos={"produto_id": produto["id"]}, resultado=proposta))
                if proposta.get("erro"):
                    raise RegraNegocio(proposta["erro"])
                evidencias["calculo:" + produto["id"]] = {"id": "calculo:" + produto["id"], "tipo": "registro",
                        "trecho": json.dumps(proposta, ensure_ascii=False)}
            lembrancas = self.conhecimento.lembrar(s["usuario"], s["texto"])
            conteudo = {"pergunta": s["texto"], "interpretacao": i, "evidencias": evidencias,
                        "proposta": proposta, "episodios_anteriores_nao_sao_estoque_atual": lembrancas}
            return {**self._contadores(s), "produto": produto, "proposta": proposta,
                    "evidencias": evidencias, "lembrancas": lembrancas, "eventos": eventos,
                    "alias_pendente": "", "candidatos_pendentes": [],
                    "mensagens": [{"role": "user", "content": json.dumps(conteudo, ensure_ascii=False)}]}
        except Exception as erro:
            return {**self._contadores(s), "erro": str(erro), "eventos": eventos}

    def _mensagens(self, s):
        sistema = self._prompt("reposicao") + "\n" + self._prompt("procedimento")
        # Checkpoint íntegro; a visão para o modelo corta blocos antigos, nunca
        # uma metade do par assistant/tool nem o pedido atual e a proposta.
        atual = [{"role": "system", "content": sistema},
                 {"role": "user", "content": json.dumps({"objetivo": s["texto"],
                  "evidencias": s.get("evidencias", {}), "proposta": s.get("proposta")}, ensure_ascii=False)}]
        blocos = []
        for m in s.get("mensagens", []):
            if m["role"] != "tool":
                blocos.append([m])
            elif blocos:
                blocos[-1].append(m)
        extras = []
        for bloco in reversed(blocos):
            if len(json.dumps(atual + bloco + extras)) > self.config.max_contexto_caracteres:
                break
            extras = bloco + extras
        return atual + extras

    def _agente(self, s):
        try:
            r = self._chamar(s, self._mensagens(s), ferramentas_leitura() +
                             [ferramenta_saida("emitir_resposta", RespostaModelo)])
            evento = self._evento(s, "modelo", "reposicao", etapa="decisao", resposta=r)
            if r.get("erro"):
                raise ValueError(r["erro"])
            if r["nome"] == "emitir_resposta":
                try:
                    candidata = RespostaModelo.model_validate(r["argumentos"]).model_dump()
                    if candidata["suficiente"] and (not candidata["fontes"] or
                            not set(candidata["fontes"]) <= set(s.get("evidencias", {}))):
                        raise ValueError("Fonte ausente ou não recuperada nesta execução.")
                    if s["interpretacao"]["intencao"] == "politica" and candidata["suficiente"] and not any(
                            s["evidencias"][f]["tipo"] == "documento" for f in candidata["fontes"]):
                        raise ValueError("Política exige documento vigente recuperado.")
                    return {**self._contadores(s), "candidata": candidata, "eventos": [evento]}
                except (ValueError, ValidationError) as erro:
                    if s.get("correcoes", 0) >= 1:
                        return {**self._contadores(s), "eventos": [evento], "saida": self._saida(
                            s, "recusado", "Não tenho base verificável para responder. Consulte o cadastro ou a política vigente.")}
                    return {**self._contadores(s), "eventos": [evento], "correcoes": 1,
                            "mensagens": [{"role": "user", "content": "Corrija a saída: " + str(erro)[:200]}]}
            return {**self._contadores(s), "chamada": r, "eventos": [evento]}
        except Exception as erro:
            return {**self._contadores(s), "erro": str(erro),
                    "eventos": [evento] if "evento" in locals() else []}

    def _ferramentas(self, s):
        chamada = s["chamada"]
        nome, args = chamada["nome"], chamada["argumentos"]
        anteriores = [e for e in s.get("eventos", []) if e["caso_id"] == s["caso_id"] and e["tipo"] == "ferramenta"]
        iguais = sum(e.get("ferramenta") == nome and e.get("argumentos") == args for e in anteriores[-4:])
        if iguais >= 4:
            return {"erro": "laco_detectado: repetiu a mesma chamada após observação", "chamada": None}
        evidencias = dict(s.get("evidencias", {}))
        try:
            resultado = self._ler(s, nome, args)
            if nome == "buscar_documentos":
                for fonte in resultado:
                    evidencias[fonte["id"]] = {k: fonte[k] for k in ("id", "tipo", "trecho")}
            elif not resultado.get("erro"):
                ident = nome + ":" + str(resultado.get("id") or resultado.get("produto_id") or "registro")
                evidencias[ident] = {"id": ident, "tipo": "registro", "trecho": json.dumps(resultado, ensure_ascii=False)}
        except Exception as erro:
            resultado = {"erro": str(erro)}
        if iguais >= 2:
            resultado = {"observacao": "Você já fez esta consulta. Use o resultado ou recuse; não repita.", "resultado": resultado}
        call_id = uuid4().hex
        return {**self._contadores(s), "chamada": None, "evidencias": evidencias,
                "eventos": [self._evento(s, "ferramenta", "reposicao", ferramenta=nome, argumentos=args, resultado=resultado)],
                "mensagens": [{"role": "assistant", "content": None, "tool_calls": [{"id": call_id,
                    "type": "function", "function": {"name": nome, "arguments": json.dumps(args)}}]},
                    {"role": "tool", "tool_call_id": call_id, "content": json.dumps(resultado, ensure_ascii=False)}]}

    def _validar(self, s):
        if limite := self._limite(s, ferramenta=True):
            return {"erro": limite}
        if not s["candidata"]["suficiente"]:
            return {"saida": self._saida(s, "recusado", s["candidata"]["resultado"])}
        p = s.get("proposta")
        if p and p["custo_estimado"] > p["orcamento_disponivel"] and self.servico.custo(
                p["pedido_minimo"], p["preco_unitario"]) > p["orcamento_disponivel"]:
            return {"saida": self._saida(s, "recusado", "Orçamento insuficiente. Reduza a necessidade em uma nova solicitação; o gerente não pode ultrapassar o saldo.")}
        if p:
            return {}
        resposta = s["candidata"]["resultado"]
        if s["interpretacao"]["relato_falta"] and s.get("produto") and not s["produto"]["abaixo_do_minimo"]:
            p = s["produto"]
            resposta = (f"O sistema mostra o contrário do que você viu: há {p['estoque_atual']} unidades de {p['nome']}, "
                        f"acima do mínimo de {p['estoque_minimo']}. Confira a gôndola e o depósito; não foi criada compra.")
        return {"saida": self._saida(s, "respondido", resposta, True)}

    def _revisar(self, s):
        if not self.multi:
            return {"parecer": {"aprovado": True, "motivos": ["Validação determinística; modo de um agente."], "fontes": []}}
        # Subconjunto de contrato; o revisor não recebe a trajetória nem segredos.
        msgs = [{"role": "system", "content": self._prompt("revisao")}, {"role": "user", "content": json.dumps(
            {"proposta": s["proposta"], "evidencias": s["evidencias"]}, ensure_ascii=False)}]
        eventos, consultou = [], False
        fontes = dict(s["evidencias"])
        try:
            while True:
                r = self._chamar(s, msgs, ferramentas_leitura() + [ferramenta_saida("emitir_parecer", Parecer)], agente="revisao")
                eventos.append(self._evento(s, "modelo", "revisao", etapa="revisao", resposta=r))
                if r.get("erro"):
                    raise ValueError(r["erro"])
                if r["nome"] == "emitir_parecer":
                    parecer = Parecer.model_validate(r["argumentos"]).model_dump()
                    if not consultou or (parecer["aprovado"] and (not parecer["fontes"] or not set(parecer["fontes"]) <= set(fontes))):
                        raise ValueError("Revisor precisa consultar e citar evidências verificadas.")
                    return {**self._contadores(s), "parecer": parecer, "eventos": eventos}
                resultado = self._ler(s, r["nome"], r["argumentos"], "revisao")
                consultou = True
                if r["nome"] == "buscar_documentos":
                    for f in resultado:
                        fontes[f["id"]] = {k: f[k] for k in ("id", "tipo", "trecho")}
                call_id = uuid4().hex
                msgs.extend([{"role": "assistant", "content": None, "tool_calls": [{"id": call_id,
                    "type": "function", "function": {"name": r["nome"], "arguments": json.dumps(r["argumentos"])}}]},
                    {"role": "tool", "tool_call_id": call_id, "content": json.dumps(resultado, ensure_ascii=False)}])
                eventos.append(self._evento(s, "ferramenta", "revisao", ferramenta=r["nome"], argumentos=r["argumentos"], resultado=resultado))
        except Exception as erro:
            return {**self._contadores(s), "eventos": eventos,
                    "parecer": {"aprovado": False, "motivos": ["Revisão indisponível ou inválida: " + str(erro)], "fontes": []}}

    def _preparar(self, s):
        if not s["parecer"]["aprovado"]:
            return {"saida": self._saida(s, "recusado", "Revisão não autorizou a proposta: " + "; ".join(s["parecer"]["motivos"]))}
        try:
            self.servico.preparar(s["caso_id"], s["usuario"], s["interpretacao"]["intencao"], s["produto"], s["proposta"])
            return {}
        except Exception as erro:
            return {"erro": str(erro)}

    def _aprovar(self, s):
        # Nenhum efeito colateral antes do interrupt: este nó recomeça ao retomar.
        p = s["proposta"]
        decisao = interrupt({"acao": "registrar_compra", "caso_id": s["caso_id"], "produto": p["nome"],
            "fornecedor": p["fornecedor_id"], "quantidade": p["quantidade"], "custo_estimado": p["custo_estimado"],
            "orcamento": p["orcamento_disponivel"], "motivo": "Valor acima de R$ 500 ou quantidade precisa de ajuste ao saldo",
            "consequencia": "Criar uma solicitação local e debitar o orçamento; nenhum envio externo.",
            "respostas": ["aprovar", "rejeitar"], "editavel": ["quantidade"],
            "erro_validacao_anterior": s.get("correcao_humana"),
            "expira": self.servico.caso(s["caso_id"])["expira"]})
        return {"decisao": DecisaoHumana.model_validate(decisao).model_dump(), "correcao_humana": None}

    def _escrever(self, s):
        try:
            if self._limite(s, ferramenta=True):
                raise RegraNegocio(self._limite(s, ferramenta=True))
            if s.get("decisao"):
                status = self.servico.decidir(s["caso_id"], s["decisao"])
                if status != "pendente":
                    return {"saida": self._saida(s, status, "Solicitação " + status + "; nenhuma compra executada.")}
            caso = self.servico.caso(s["caso_id"])
            s["n_ferramentas"] += 1
            if self.mcp:
                resultado = self.mcp.chamar("registrar_compra", {"caso_id": s["caso_id"], "capacidade": caso["capacidade"]})
            else:
                resultado = self.servico.finalizar(s["caso_id"], caso["capacidade"])
            texto = f"Solicitação criada: {resultado['quantidade']} unidades; custo R$ {resultado['custo_estimado']:.2f}. Nenhum pedido foi enviado ao fornecedor."
            return {**self._contadores(s), "saida": self._saida(s, "criada", texto, True, solicitacao=resultado),
                    "eventos": [self._evento(s, "escrita", ferramenta="registrar_compra", resultado=resultado)]}
        except Exception as erro:
            evento = self._evento(s, "escrita_recusada", ferramenta="registrar_compra", erro=str(erro))
            if isinstance(erro, RegraNegocio) and s.get("decisao") and not self._limite(s, ferramenta=True):
                return {**self._contadores(s), "correcao_humana": str(erro), "eventos": [evento]}
            return {**self._contadores(s), "erro": str(erro), "eventos": [evento]}

    def _finalizar(self, s):
        erro = s.get("erro") or "Execução sem saída válida."
        termino = "laco_detectado" if "laco_detectado" in erro.lower() else "orcamento_esgotado" if "teto" in erro.lower() else "truncado" if "truncada" in erro.lower() else "erro_fatal"
        saida = s.get("saida") or self._saida(s, "falha", erro, termino=termino)
        if saida["status"] == "falha":
            caso = self.servico.caso(s["caso_id"])
            if caso and caso["status"] == "pendente":
                self.servico.decidir(s["caso_id"], {"acao": "rejeitar"})
        eventos = []
        if saida["status"] in {"criada", "respondido", "rejeitada", "expirada", "recusado"} and s.get("produto"):
            try:
                memoria = self.conhecimento.guardar_episodio(s["usuario"], s["thread_id"], {
                    "caso": s["caso_id"], "produto": s["produto"]["id"], "nome": s["produto"]["nome"], "status": saida["status"],
                    "solicitacao": {k: v for k, v in (saida.get("solicitacao") or {}).items()
                        if k in {"chave", "produto_id", "quantidade", "custo_estimado", "status", "caso_id"}},
                    "divergencia": s["interpretacao"]["relato_falta"]
                        and not s["produto"]["abaixo_do_minimo"]})
                eventos.append(self._evento(s, "memoria", resultado=memoria))
            except Exception as erro:
                eventos.append(self._evento(s, "memoria_indisponivel", erro=type(erro).__name__))
        return {"saida": saida, "eventos": eventos}

    def _compilar(self):
        g = StateGraph(Estado)
        for nome, func in [("interpretar", self._interpretar), ("coletar", self._coletar),
                ("agente", self._agente), ("ferramentas", self._ferramentas), ("validar", self._validar),
                ("revisar", self._revisar), ("preparar", self._preparar), ("aprovar", self._aprovar),
                ("escrever", self._escrever), ("finalizar", self._finalizar)]:
            g.add_node(nome, self._medir_no(func))
        def caminho(s, proximo):
            return "finalizar" if s.get("erro") or s.get("saida") else proximo
        g.add_edge(START, "interpretar")
        for a, b in [("interpretar", "coletar"), ("coletar", "agente"), ("ferramentas", "agente"),
                     ("validar", "revisar"), ("revisar", "preparar")]:
            g.add_conditional_edges(a, lambda s, p=b: caminho(s, p), {b: b, "finalizar": "finalizar"})
        g.add_conditional_edges("agente", lambda s: "finalizar" if s.get("erro") or s.get("saida") else
            "validar" if s.get("candidata") else "ferramentas" if s.get("chamada") else "agente",
            {n: n for n in ("finalizar", "validar", "ferramentas", "agente")})
        g.add_conditional_edges("preparar", lambda s: caminho(s, "aprovar" if s["proposta"]["custo_estimado"] > min(500,s["proposta"]["orcamento_disponivel"]) else "escrever"),
                                {n: n for n in ("aprovar", "escrever", "finalizar")})
        g.add_edge("aprovar", "escrever")
        g.add_conditional_edges("escrever", lambda s: "aprovar" if s.get("correcao_humana") else "finalizar",
                                {"aprovar": "aprovar", "finalizar": "finalizar"})
        g.add_edge("finalizar", END)
        return g.compile(checkpointer=self.checkpointer)

    def iniciar(self, texto, usuario="operador-demo", thread_id=None):
        thread = thread_id or usuario + ":" + uuid4().hex
        config = self._config(thread)
        anterior = self.grafo.get_state(config)
        if anterior.values and anterior.values.get("usuario") != usuario:
            raise PermissionError("Conversa pertence a outro usuário simulado.")
        if anterior.next:
            raise ValueError("Esta conversa aguarda aprovação. Retome ou rejeite antes de enviar outra pergunta.")
        entrada = {"texto": texto, "usuario": usuario, "thread_id": thread, "caso_id": uuid4().hex,
                   "interpretacao": {}, "produto": {}, "proposta": None, "evidencias": {},
                   "lembrancas": [], "chamada": None, "candidata": None, "parecer": None,
                   "decisao": None, "saida": None, "erro": None, "correcoes": 0, "correcao_humana": None, "uso_incompleto": False,
                   **{k: 0 for k in ("n_modelo", "n_ferramentas", "n_recuperacoes", "tokens_entrada", "tokens_saida", "processamento_s")}}
        return self._executar(entrada, config)

    def retomar(self, thread_id, decisao, perfil="operador"):
        if perfil != "gerente":
            raise PermissionError("Somente o perfil simulado gerente pode aprovar/rejeitar.")
        decisao = DecisaoHumana.model_validate(decisao).model_dump()
        config = self._config(thread_id)
        estado = self.grafo.get_state(config)
        if not estado.values:
            raise ValueError("Conversa não encontrada.")
        if not estado.next:
            saida = Saida.model_validate(estado.values["saida"])
            self._log(estado.values, "aprovacao_repetida")
            return saida
        return self._executar(Command(resume=decisao), config)

    def _executar(self, entrada, config):
        try:
            estado = self.grafo.invoke(entrada, config)
        except Exception as erro:
            estado = dict(self.grafo.get_state(config).values)
            estado["saida"] = self._saida(estado, "falha", "Execução interrompida: " + type(erro).__name__)
            self._log(estado, "erro_fatal")
            return Saida.model_validate(estado["saida"])
        if estado.get("__interrupt__"):
            payload = estado["__interrupt__"][0].value
            saida = self._saida(estado, "aguardando_aprovacao", "O gerente precisa revisar esta solicitação antes da compra.", True, aprovacao=payload)
        else:
            saida = estado["saida"]
        self._log({**estado, "saida": saida}, saida["status"])
        return Saida.model_validate(saida)

    def _log(self, estado, evento):
        pasta = self.config.runtime / "logs"
        pasta.mkdir(exist_ok=True)
        registro = {"quando": agora().isoformat(), "evento": evento, "modo": self.modelo.modo,
            "modelo": self.modelo.nome, "multiagente": self.multi, "mcp": bool(self.mcp),
            "versao": versao(), "parametros": {"temperature": 0, "max_tokens": 800,
                "recursion_limit": self.config.recursion_limit, "rag": self.conhecimento.parametros},
            "thread_id": estado["thread_id"], "caso_id": estado["caso_id"], "entrada": estado["texto"],
            "metricas": self._contadores(estado), "saida": estado.get("saida"),
            "eventos": [e for e in estado.get("eventos", []) if e["caso_id"] == estado["caso_id"]],
            "uso_incompleto": estado.get("uso_incompleto", False),
            "custo_api": None if estado.get("uso_incompleto") else (
                estado.get("tokens_entrada", 0) * self.config.preco_entrada +
                estado.get("tokens_saida", 0) * self.config.preco_saida) / 1_000_000,
            "tarifa_usd_milhao": {"entrada": self.config.preco_entrada, "saida": self.config.preco_saida},
            "energia_kwh": None}
        path = pasta / f"{estado['caso_id']}-{uuid4().hex[:8]}.json"
        path.write_text(json.dumps(registro, ensure_ascii=False, indent=2))

    def remover_conversa(self, thread_id):
        estado = self.grafo.get_state(self._config(thread_id))
        if estado.values:
            caso = self.servico.caso(estado.values["caso_id"])
            if caso and caso["status"] == "pendente":
                self.servico.decidir(caso["id"], {"acao": "rejeitar"})
        self.checkpointer.delete_thread(thread_id)
        self.conhecimento.remover_thread(thread_id)
        for p in (self.config.runtime / "logs").glob("*.json"):
            if json.loads(p.read_text()).get("thread_id") == thread_id:
                p.unlink()
        def contem(obj):
            if isinstance(obj, dict):
                return obj.get("thread_id") == thread_id or any(contem(v) for v in obj.values())
            return isinstance(obj, list) and any(contem(v) for v in obj)
        exportados = []
        for p in (RAIZ / "logs").rglob("*.json"):
            if contem(json.loads(p.read_text())):
                exportados.append(str(p.relative_to(RAIZ)))
                p.unlink()
        for p in (RAIZ / "README.md", RAIZ / "docs" / "io.md"):
            if not p.exists():
                continue
            def limpar(match):
                try:
                    return "Exemplo removido por solicitação; gere novamente as evidências." if contem(json.loads(match.group(1))) else match.group(0)
                except ValueError:
                    return match.group(0)
            anterior = p.read_text()
            novo = re.sub(r"```json\n(.*?)\n```", limpar, anterior, flags=re.S)
            if novo != anterior:
                p.write_text(novo)
        # Procedural versionada e registros contábeis não contêm entrada bruta.
        return {"thread_id": thread_id, "estruturas": ["checkpoint", "episodios/vetores", "fatos", "logs", "exportacoes e exemplos"],
                "exportacoes_removidas": exportados,
                "operacao": "solicitações auditáveis preservadas; pendência cancelada"}
