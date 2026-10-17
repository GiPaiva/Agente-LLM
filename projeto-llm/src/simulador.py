"""Dublês de integração. Nunca representam medição de qualidade de um LLM."""
import json
import re
import hashlib
import numpy as np
import db


class EmbeddingControlado:
    def contar(self, texto):
        return len(texto.split()) + 2

    def vetores(self, textos):
        vetores = []
        for texto in textos:
            v = np.zeros(384, dtype=np.float32)
            for token in re.findall(r"\w+", db.normalizar(texto)):
                v[int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % 384] += 1
            vetores.append(v)
        return np.asarray(vetores)


class ModeloControlado:
    modo = "controlado"
    nome = "duble-deterministico-nao-LLM"

    def chamar(self, mensagens, ferramentas, obrigatoria=None, agente="reposicao", **_):
        nomes = {t["function"]["name"] for t in ferramentas}
        dados = [json.loads(m["content"]) for m in mensagens if m["role"] == "user"
                 and m.get("content", "").startswith("{")]
        atual = dados[-1] if dados else {}
        if obrigatoria == "extrair_intencao":
            texto = db.normalizar(atual["texto"])
            politica = any(t in texto for t in ("politica", "aprovacao", "avaria", "contrato", "orcamento", "limite", "recebimento"))
            produto = next((t for t in ("arroz", "refrigerante", "feijao", "acucar", "sal") if re.search(r"\b" + t + r"\b", texto)), "")
            embalagem = next((t for t in ("1kg", "5kg", "2l") if t in texto.replace(" ", "")), "")
            if not produto and atual.get("esclarecimento_anterior") and embalagem:
                produto = atual["esclarecimento_anterior"]
            desconhecido = next((t for t in ("iogurte", "leite condensado", "papel higienico", "sabao em po", "manteiga") if t in texto), "")
            produto = (produto + " " + embalagem).strip() if produto else desconhecido
            falta = any(t in texto for t in ("acab", "zer", "fim", "falt", "abaixo", "sumiu"))
            repor = any(t in texto for t in ("ped", "compr", "repor", "reposi", "registra", "deixa o pedido")) or falta
            escopo = bool(produto or politica or any(t in texto for t in ("estoque", "produto", "repor", "pedir", "quanto temos")))
            args = {"intencao": "politica" if politica else ("reposicao" if repor else "consulta") if escopo else "fora_escopo",
                    "produto": produto, "relato_falta": falta, "pergunta": ""}
            nome = "extrair_intencao"
        elif agente == "revisao":
            tools = [m for m in mensagens if m["role"] == "tool"]
            if not tools:
                nome, args = "consultar_estoque", {"produto": atual["proposta"]["nome"]}
            else:
                nome, args = "emitir_parecer", {"aprovado": True, "motivos": ["Dados conferidos pelo dublê."],
                                               "fontes": list(atual["evidencias"])[:1]}
        else:
            base = dados[0] if dados else {}
            evidencias = base.get("evidencias", {})
            tools = [m for m in mensagens if m["role"] == "tool"]
            if not evidencias and not tools:
                nome, args = "buscar_documentos", {"consulta": base.get("objetivo", ""), "fornecedor": ""}
            else:
                nome, args = "emitir_resposta", {"resultado": "Dados consultados: " + " ".join(
                    f["trecho"] for f in evidencias.values()), "fontes": list(evidencias), "suficiente": bool(evidencias)}
                if not evidencias:
                    args["resultado"] = "Não encontrei base suficiente no corpus para responder."
        assert nome in nomes
        return {"nome": nome, "argumentos": args, "entrada": 0, "saida": 0, "tentativas": 1}
