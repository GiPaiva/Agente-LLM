# Parte 1 — o agente: estado explícito, orçamento, gating de ferramenta e o
# laço de tool calling.
#
# Mesma ideia do `agente.py` da aula 05, reduzida ao mínimo que a Parte 1 pede
# (item 4.1: pouco código, 2 a 4 ferramentas, sem router, sem avaliador — isso
# é escopo da Parte 2, ver ideia-evolucao/v2.md).
#
# A ideia que NÃO pode ser cortada mesmo no mínimo:
#
#     mensagens[] é FORMATO DE TRANSPORTE, não é o estado do agente.
#
# Por isso existe `Estado` como objeto, e `montar_mensagens()` o traduz para o
# formato que a API espera a cada volta — nunca o contrário. Sem essa
# separação, orçamento, detecção de laço e log de trajetória não são
# implementáveis: a informação de que eles precisam não existe dentro de uma
# lista de dicionários de mensagem.

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError

from ferramentas import (FERRAMENTAS, FASES, ESCRITA, declaracoes,
                         ErroRecuperavel, ErroFatal)

load_dotenv()

RAIZ = Path(__file__).parent.parent
LOGS = RAIZ / "logs"

# ------------------------------------------------------- prompt e carimbo

PROMPT_ARQUIVO = "sistema-v3"

# Os parâmetros fazem parte da unidade versionada `prompt × modelo ×
# parâmetros` — por isso ficam aqui, num lugar só, e vão carimbados em todo
# registro de logs/.
#
#   temperature=0   escolher ferramenta é decisão, e variar decisão é defeito.
#                   (Não garante saída idêntica — é por isso que o verificador
#                   mede k de N e não "passou".)
#
#   max_tokens=800  teto de parada (aula 02). Duas razões, e a segunda só
#                   apareceu quando medimos: a resposta mais longa deste
#                   sistema tem ~80 tokens e a maior trajetória gastou ~600 no
#                   total, então 800 por chamada não corta nada. E, sem ele, a
#                   conta gratuita da Groq recusa a requisição ANTES de
#                   processá-la — o limite de lá é por tokens de saída
#                   esperados por minuto, e uma requisição sem teto declarado
#                   é estimada acima do limite. Ver docs/modelos.md §3.3.
PARAMETROS = {"temperature": 0, "max_tokens": 800}


def carregar_prompt(nome: str) -> str:
    """Lê só o bloco entre os marcadores do .md.

    O resto do arquivo é a documentação da técnica e do contrato (exigida pelo
    item 4.3) e não deve consumir contexto. Os marcadores são explícitos de
    propósito: a versão anterior fatiava o arquivo no primeiro bloco de crase,
    e qualquer exemplo de código acrescentado à documentação teria mudado, em
    silêncio, o prompt que vai para o modelo.
    """
    texto = (RAIZ / "prompts" / f"{nome}.md").read_text(encoding="utf-8")
    achado = re.search(r"<!-- PROMPT:INICIO -->(.*?)<!-- PROMPT:FIM -->",
                       texto, re.DOTALL)
    if achado is None:
        raise ErroFatal(
            f"prompts/{nome}.md não tem os marcadores <!-- PROMPT:INICIO --> e "
            f"<!-- PROMPT:FIM -->. Sem eles não dá para saber o que é prompt e "
            f"o que é documentação.")
    return achado.group(1).strip()


SYSTEM = carregar_prompt(PROMPT_ARQUIVO)


def cliente_e_modelo() -> tuple[OpenAI, str]:
    """A troca de provedor é troca de variável de ambiente, não de código
    (item 4.1 da entrega). São três: base_url, modelo e chave."""
    return (
        OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.mistral.ai/v1"),
            api_key=os.environ.get("OPENAI_API_KEY") or "nao-usada-localmente",
        ),
        os.environ.get("LLM_MODELO", "mistral-small-latest"),
    )


# ============================================================ ESTADO

class Termino(str, Enum):
    RESPONDEU = "respondeu"           # o modelo concluiu
    ORCAMENTO = "orcamento_esgotado"  # bateu um dos três tetos
    LACO = "laco_detectado"           # girando sem progresso
    TRUNCADO = "truncado"             # bateu max_tokens no meio da resposta
    ERRO_FATAL = "erro_fatal"         # falha de transporte, não de conteúdo


@dataclass
class Passo:
    indice: int
    ferramenta: str
    argumentos: dict
    resultado: dict | None = None
    erro: str | None = None
    tokens_entrada: int = 0
    tokens_saida: int = 0


@dataclass
class Estado:
    objetivo: str                                     # imutável: a âncora
    execucao_id: str = field(default_factory=lambda: uuid4().hex[:8])
    passos: list[Passo] = field(default_factory=list)
    tokens_gastos: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    duracao_s: float = 0.0
    termino: Termino | None = None
    motivo: str | None = None
    resposta: str | None = None
    # Quais ferramentas o modelo pode ver AGORA. Começa na fase de análise e só
    # cresce por decisão do código — ver `talvez_liberar_escrita`.
    ferramentas_ativas: list[str] = field(
        default_factory=lambda: list(FASES["analise"]))
    fase: str = "analise"
    # Trilha de quando a escrita foi liberada, para o log e para o verificador.
    escrita_liberada_no_passo: int | None = None
    historico: list = field(default_factory=list)  # visão do modelo, DERIVADA

    @property
    def n_passos(self) -> int:
        return len(self.passos)

    def registrar(self, passo: Passo) -> None:
        self.passos.append(passo)


@dataclass
class Orcamento:
    """Três tetos. `max_passos` sozinho não é orçamento: um passo consome de
    algumas centenas a dezenas de milhares de tokens."""
    max_passos: int = 8
    max_tokens: int = 60_000
    max_segundos: float = 300.0
    inicio: float = field(default_factory=time.monotonic)

    def excedido(self, estado: Estado) -> str | None:
        """Devolve QUAL teto estourou — um bool seria mais simples e inútil."""
        if estado.n_passos >= self.max_passos:
            return f"passos {estado.n_passos}/{self.max_passos}"
        if estado.tokens_gastos >= self.max_tokens:
            return f"tokens {estado.tokens_gastos}/{self.max_tokens}"
        decorrido = time.monotonic() - self.inicio
        if decorrido >= self.max_segundos:
            return f"tempo {decorrido:.0f}s/{self.max_segundos:.0f}s"
        return None


# ============================================ O GATING (restrição por arquitetura)
#
# Aula 05, nota 02 §6: "restrição por arquitetura vence restrição por prompt —
# instrução ele pode ignorar, ferramenta não declarada ele não tem como
# chamar."
#
# O agente começa sem a ferramenta de escrita. Quem a habilita é esta função,
# depois que um `consultar_estoque` DESTA execução devolveu
# `abaixo_do_minimo: True`. Nos casos 2, 3, 4 e 5 do conjunto rotulado isso
# nunca acontece, e portanto `criar_solicitacao_compra` nunca chega a ser
# oferecida ao modelo.
#
# É o que transforma o critério assimétrico do item 2.7 ("nunca criar compra
# indevida") de uma esperança de prompt numa garantia verificável — e o
# verificador confere no log que a ferramenta não foi sequer declarada, não
# apenas que não foi chamada.

def talvez_liberar_escrita(estado: Estado, passo: Passo, verboso: bool) -> None:
    if estado.fase == "reposicao":
        return
    if passo.ferramenta != "consultar_estoque" or passo.erro:
        return
    if not (passo.resultado or {}).get("abaixo_do_minimo"):
        return

    estado.fase = "reposicao"
    estado.ferramentas_ativas = list(FASES["reposicao"])
    estado.escrita_liberada_no_passo = passo.indice
    if verboso:
        print(f"      [gating] {passo.resultado['nome']} está abaixo do mínimo "
              f"— escrita liberada")


# ============================================================ O LAÇO

PISTAS = {
    401: "chave inválida ou ausente — confira OPENAI_API_KEY no .env",
    403: "a chave não tem permissão para este modelo",
    404: "modelo não encontrado — confira LLM_MODELO no .env",
    422: "a API recusou o corpo da requisição — olhe `tools`",
}

REANCORAR_A_CADA = 4


# Tentativas extras, e SÓ para falha de transporte. Ver a docstring de
# `chamar()` — o número é baixo de propósito: 2 novas tentativas cobrem o
# soluço de rede e continuam parando rápido quando o problema é real.
TENTATIVAS_TRANSPORTE = 2
ESPERA_ENTRE_TENTATIVAS = 3.0


def chamar(client: OpenAI, **kwargs):
    """Uma chamada, com retry **apenas para falha de transporte**.

    A distinção é a da aula 05, e ela decide o que se pode repetir:

      TRANSPORTE  a rede caiu, o servidor devolveu 5xx, o túnel piscou.
                  Repetir a MESMA requisição pode funcionar — nada mudou do
                  lado do conteúdo. É o único caso tratado aqui.

      CONTEÚDO    o modelo mandou um argumento inválido. Repetir a mesma
                  requisição devolve o mesmo erro. Quem tenta de novo, com
                  informação nova, é o modelo — e isso é assunto de
                  `executar()`, não daqui.

      CONFIGURAÇÃO  401, 403, 404, 422. Repetir só esconde o erro, que é o
                  que a aula 05 alerta ("retry silencioso esconde erro de
                  configuração, a causa mais comum num laboratório"). Por
                  isso 4xx aborta na primeira, e a mensagem diz o que fazer.

    O retry é **visível**: ele imprime cada nova tentativa. Retry que ninguém
    vê é o que transforma "está lento" num mistério.

    Motivo concreto de existir: o modelo local desta entrega é servido por um
    túnel Cloudflare, e um 530 de alguns segundos derrubava uma suíte de 60
    execuções pela metade — perdendo 20 minutos de medição por um soluço que
    não tem nada a ver com o agente.
    """
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS_TRANSPORTE + 2):
        try:
            return client.chat.completions.create(**kwargs)

        # --- CONFIGURAÇÃO e limite: aborta na primeira, sem repetir.
        except RateLimitError as e:
            raise ErroFatal(
                f"429 — excesso de requisições. Espere e rode de novo. ({e})") from e
        except APIStatusError as e:
            if e.status_code < 500:
                pista = PISTAS.get(e.status_code, "consulte a documentação da API")
                raise ErroFatal(f"{e.status_code} — {pista}. ({e})") from e
            ultimo_erro = e
            descricao = f"{e.status_code} do servidor"

        # --- TRANSPORTE: vale repetir.
        except APIConnectionError as e:
            ultimo_erro = e
            descricao = "sem conexão"

        if tentativa <= TENTATIVAS_TRANSPORTE:
            print(f"      [rede] {descricao} — tentativa "
                  f"{tentativa}/{TENTATIVAS_TRANSPORTE + 1}, repetindo em "
                  f"{ESPERA_ENTRE_TENTATIVAS:.0f}s")
            time.sleep(ESPERA_ENTRE_TENTATIVAS)

    raise ErroFatal(
        f"falha de transporte após {TENTATIVAS_TRANSPORTE + 1} tentativas — "
        f"confira LLM_BASE_URL e se o servidor do modelo está de pé. "
        f"({ultimo_erro})") from ultimo_erro


def montar_mensagens(estado: Estado) -> list[dict]:
    """A lista de mensagens é uma VISÃO do estado, montada a cada volta."""
    mensagens = [{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": estado.objetivo}]
    mensagens.extend(estado.historico)

    # Reancoragem: em trajetória longa o objetivo fica no MEIO do contexto, que
    # é onde o modelo lê pior. Custa dezenas de tokens.
    if estado.n_passos and estado.n_passos % REANCORAR_A_CADA == 0:
        mensagens.append({
            "role": "user",
            "content": f"Lembrete do objetivo: {estado.objetivo}"})
    return mensagens


def mensagem_de_tool(passo: Passo, tool_call_id: str) -> dict:
    conteudo = passo.resultado if passo.resultado is not None else {"erro": passo.erro}
    return {"role": "tool", "tool_call_id": tool_call_id,
            "name": passo.ferramenta,
            "content": json.dumps(conteudo, ensure_ascii=False)}


def executar(chamada, estado: Estado) -> Passo:
    """A ACTION do ReAct, e a classificação do erro — quem decide se um erro é
    recuperável é o CÓDIGO, nunca o modelo."""
    nome = chamada.function.name
    passo = Passo(indice=estado.n_passos, ferramenta=nome, argumentos={})

    try:
        passo.argumentos = json.loads(chamada.function.arguments or "{}")
    except json.JSONDecodeError:
        passo.erro = "argumentos não são JSON válido"
        passo.resultado = {"erro": passo.erro}
        return passo

    # Chamou uma ferramenta que não está ativa nesta fase. Não é exceção: é
    # observação, e o texto ensina o modelo o que fazer antes.
    if nome not in estado.ferramentas_ativas:
        passo.erro = f"ferramenta indisponível nesta etapa: {nome}"
        passo.resultado = {
            "erro": passo.erro,
            "disponiveis": estado.ferramentas_ativas,
            "sugestao": ("registrar compra só fica disponível depois que "
                         "consultar_estoque mostrar o produto abaixo do mínimo"
                         if nome in ESCRITA else
                         "use uma das ferramentas disponíveis"),
        }
        return passo

    funcao = FERRAMENTAS.get(nome)
    if funcao is None:                     # o modelo inventou o nome
        passo.erro = f"ferramenta desconhecida: {nome}"
        passo.resultado = {"erro": passo.erro,
                           "disponiveis": estado.ferramentas_ativas}
        return passo

    try:
        passo.resultado = funcao(**passo.argumentos)
    except ErroRecuperavel as e:
        # Volta para o modelo como OBSERVAÇÃO, não como exceção que derruba o
        # programa. O texto do erro é prompt (nota 03 da aula 05).
        passo.erro = e.payload["erro"]
        passo.resultado = e.payload
    except TypeError as e:                 # alucinou ou esqueceu um parâmetro
        passo.erro = f"argumentos inválidos: {e}"
        passo.resultado = {"erro": passo.erro}
    return passo


def assinatura(passo: Passo) -> tuple:
    """sort_keys=True não é detalhe: sem ele {'a':1,'b':2} e {'b':2,'a':1} são
    assinaturas diferentes e o detector não detecta nada."""
    return (passo.ferramenta, json.dumps(passo.argumentos, sort_keys=True))


def detectar_laco(estado: Estado, limite: int = 3) -> bool:
    if estado.n_passos < limite:
        return False
    return len({assinatura(p) for p in estado.passos[-limite:]}) == 1


def rodar(pergunta: str,
          orcamento: Orcamento | None = None,
          client: OpenAI | None = None,
          modelo: str | None = None,
          verboso: bool = True,
          salvar_em: Path | None = None,
          rotulo: str | None = None) -> Estado:
    """O laço ReAct sobre o Estado.

    Devolve o Estado inteiro — não só o texto — porque quem chamou precisa da
    trajetória e do motivo de término para logar (item 4.1: "terminação
    registrada", "log da trajetória").
    """
    if client is None or modelo is None:
        client, modelo = cliente_e_modelo()
    orcamento = orcamento or Orcamento()
    estado = Estado(objetivo=pergunta)
    inicio = time.monotonic()

    try:
        while True:
            if (motivo := orcamento.excedido(estado)):
                estado.termino, estado.motivo = Termino.ORCAMENTO, motivo
                break

            if detectar_laco(estado):
                # Intervir ANTES de abortar: injeta a observação e dá mais uma
                # chance. Só aborta se voltar a repetir.
                if estado.motivo == "laco: observacao injetada":
                    estado.termino = Termino.LACO
                    estado.motivo = "repetiu a mesma chamada mesmo após a intervenção"
                    break
                ultimo = estado.passos[-1]
                if verboso:
                    print(f"      [laço] {ultimo.ferramenta} repetida — "
                          f"injetando observação")
                estado.historico.append({
                    "role": "user",
                    "content": (f"Você já chamou {ultimo.ferramenta} com esses "
                                f"argumentos e recebeu esse resultado. Use a "
                                f"informação que já tem ou diga ao usuário o "
                                f"que falta.")})
                estado.motivo = "laco: observacao injetada"

            try:
                resposta = chamar(
                    client,
                    model=modelo,
                    messages=montar_mensagens(estado),
                    tools=declaracoes(estado.ferramentas_ativas),
                    **PARAMETROS,
                )
            except ErroFatal as e:
                estado.termino, estado.motivo = Termino.ERRO_FATAL, str(e)
                break

            uso = resposta.usage
            estado.tokens_gastos += uso.total_tokens
            estado.tokens_entrada += uso.prompt_tokens
            estado.tokens_saida += uso.completion_tokens
            msg = resposta.choices[0].message

            if verboso:
                print(f"   passo {estado.n_passos} · contexto enviado: "
                      f"{uso.prompt_tokens} tokens · fase {estado.fase}")

            if not msg.tool_calls:            # respondeu: terminou
                # Resposta cortada por max_tokens é um término DIFERENTE de
                # "respondeu", e precisa aparecer como tal: um texto truncado
                # parece uma resposta e não é. Sem esta distinção, o
                # verificador contaria meia resposta como acerto, e quem
                # lesse o log veria "respondeu" para uma frase pela metade.
                if resposta.choices[0].finish_reason == "length":
                    estado.termino = Termino.TRUNCADO
                    estado.motivo = f"max_tokens={PARAMETROS.get('max_tokens')}"
                else:
                    estado.termino = Termino.RESPONDEU
                estado.resposta = msg.content
                break

            estado.historico.append(msg)
            for chamada in msg.tool_calls:
                passo = executar(chamada, estado)
                passo.tokens_entrada = uso.prompt_tokens
                passo.tokens_saida = uso.completion_tokens
                estado.registrar(passo)
                estado.historico.append(mensagem_de_tool(passo, chamada.id))
                if verboso:
                    marca = "ERRO " if passo.erro else "     "
                    print(f"      {marca}{passo.ferramenta}({passo.argumentos}) -> "
                          f"{json.dumps(passo.resultado, ensure_ascii=False)[:90]}")
                # O gating roda DEPOIS de executar, sobre o resultado real.
                talvez_liberar_escrita(estado, passo, verboso)
    finally:
        # O trace é gravado em TODOS os caminhos. O `except` que registra só o
        # sucesso é o que garante que você nunca vai achar a causa.
        estado.duracao_s = round(time.monotonic() - inicio, 2)
        salvar_log(estado, modelo, salvar_em or (LOGS / "demo"), rotulo)

    return estado


def resumo(estado: Estado) -> str:
    return (f"término: {estado.termino.value}"
            f"{' (' + estado.motivo + ')' if estado.motivo else ''} · "
            f"{estado.n_passos} passos · {estado.tokens_gastos} tokens")


def salvar_log(estado: Estado, modelo: str, pasta: Path,
               rotulo: str | None = None) -> Path:
    """Log da trajetória completa (item 4.1): ferramenta, argumentos, resultado
    e erro de cada passo, mais o motivo de término.

    Carrega também o CARIMBO `prompt × modelo × parâmetros` cobrado desde a
    aula 03 — sem ele, "a resposta de terça estava errada" não tem resposta: o
    git log diz como o arquivo mudou, não qual combinação estava rodando.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    registro = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "rotulo": rotulo,
        "carimbo": {
            "prompt": PROMPT_ARQUIVO,
            "modelo": modelo,
            "parametros": PARAMETROS,
        },
        "pergunta": estado.objetivo,
        "termino": estado.termino.value if estado.termino else None,
        "motivo": estado.motivo,
        "resposta": estado.resposta,
        "duracao_s": estado.duracao_s,
        "tokens": {
            "entrada": estado.tokens_entrada,
            "saida": estado.tokens_saida,
            "total": estado.tokens_gastos,
        },
        # A trilha do gating. É isto que permite ao verificador conferir que a
        # ferramenta de escrita não foi sequer OFERECIDA ao modelo, e não só
        # que ela não foi chamada.
        "gating": {
            "fase_final": estado.fase,
            "ferramentas_ativas_no_fim": estado.ferramentas_ativas,
            "escrita_liberada_no_passo": estado.escrita_liberada_no_passo,
            "escrita_foi_oferecida": estado.escrita_liberada_no_passo is not None,
        },
        "passos": [asdict(p) for p in estado.passos],
    }
    prefixo = f"{rotulo}-" if rotulo else ""
    caminho = pasta / f"{prefixo}{datetime.now():%Y%m%d-%H%M%S}-{estado.execucao_id}.json"
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return caminho
