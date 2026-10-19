"""Tool calling estruturado via SDK openai, com tentativas e telemetria explícitas."""
import json
import os
import time
from openai import OpenAI, APIConnectionError, APIStatusError


class FalhaModelo(RuntimeError):
    def __init__(self, mensagem, tentativas=0):
        super().__init__(mensagem)
        self.tentativas = tentativas


class Modelo:
    modo = "real"

    def __init__(self, config, client=None, modelo=None):
        self.config, self.client = config, client
        self.nome = modelo or os.environ.get("LLM_MODELO") or "nao-configurado"

    def chamar(self, mensagens, ferramentas, obrigatoria=None, agente="reposicao", restante=300, max_tentativas=3):
        if self.client is None:
            if not os.environ.get("LLM_BASE_URL") or self.nome == "nao-configurado":
                raise FalhaModelo("Configure LLM_BASE_URL e LLM_MODELO no .env; nenhuma execução real foi feita.")
            self.client = OpenAI(base_url=os.environ["LLM_BASE_URL"],
                                 api_key=os.environ.get("OPENAI_API_KEY") or "local",
                                 max_retries=0, timeout=self.config.timeout)
        # Zero-shot com ferramentas e saída estruturada. Impede argumentos livres,
        # mas o schema não garante decisão correta: o serviço valida as compras.
        # LM Studio só aceita tool_choice none/auto/required (HTTP 400 no nomeado):
        # forçar uma ferramenta = oferecer só ela com "required". Ver docs/decisoes.md.
        if obrigatoria:
            ferramentas = [t for t in ferramentas if t["function"]["name"] == obrigatoria]
        kwargs = {"model": self.nome, "messages": mensagens, "tools": ferramentas,
                  "temperature": self.config.temperatura, "max_tokens": self.config.max_tokens_resposta,
                  "parallel_tool_calls": False, "tool_choice": "required"}
        inicio = time.monotonic()
        tentativas = min(self.config.retries + 1, max_tentativas)
        for tentativa in range(tentativas):
            saldo = restante - (time.monotonic() - inicio)
            if saldo <= 0:
                raise FalhaModelo("Teto de processamento ativo atingido.", tentativa)
            try:
                result = self.client.with_options(max_retries=0,
                    timeout=min(self.config.timeout, saldo)).chat.completions.create(**kwargs)
                break
            except (APIConnectionError, APIStatusError) as erro:
                if isinstance(erro, APIStatusError) and erro.status_code < 500:
                    raise FalhaModelo(f"API recusou a configuração/cota ({erro.status_code}).", tentativa + 1) from None
                if tentativa == tentativas - 1:
                    raise FalhaModelo("Falha de transporte após tentativas explícitas.", tentativa + 1) from None
                time.sleep(min(0.5, max(0, saldo)))
        escolha = result.choices[0]
        chamadas = escolha.message.tool_calls or []
        uso = result.usage
        retorno = {"nome": "", "argumentos": {}, "entrada": uso.prompt_tokens if uso else 0,
                   "saida": uso.completion_tokens if uso else 0, "tentativas": tentativa + 1,
                   "uso_disponivel": uso is not None}
        if escolha.finish_reason == "length" or len(chamadas) != 1:
            return {**retorno, "erro": "Resposta truncada ou sem uma única chamada estruturada."}
        try:
            return {**retorno, "nome": chamadas[0].function.name,
                    "argumentos": json.loads(chamadas[0].function.arguments)}
        except json.JSONDecodeError:
            return {**retorno, "erro": "Argumentos não são JSON válido."}
