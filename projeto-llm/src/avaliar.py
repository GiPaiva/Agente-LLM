# O VERIFICADOR — item 2.6 e 2.7 da entrega.
#
#   python src/avaliar.py              conjunto inteiro, N=1
#   python src/avaliar.py --n 3        3 execuções por caso
#   python src/avaliar.py --familia 2  só a família de divergência
#
# Três decisões herdadas do `05-versao-de-prompt.py` da aula 03, e as três
# importam:
#
#   1. TESTE POR PROPRIEDADE, não por igualdade de texto. Comparar a resposta
#      com um texto esperado reprova acertos: o modelo escreve "12 unidades" ou
#      "doze", e nada está quebrado. O que se verifica é o que o sistema a
#      seguir depende — que ferramenta foi chamada, com que argumento, e que
#      fatos a resposta cita.
#
#   2. O CRITÉRIO É k DE N, não "passou". temperature=0 não garante saída
#      idêntica, então um único acerto não é evidência e uma única falha não é
#      regressão.
#
#   3. O LIMIAR É DECLARADO ANTES DE RODAR. Limiar escolhido depois de ver o
#      resultado não testa nada.
#
# E uma que é deste case: a REGRA ASSIMÉTRICA. Criar uma compra indevida mexe
# no orçamento real da loja; deixar de recomendar uma necessária custa uma
# pergunta a mais. Por isso uma única violação REPROVA a suíte inteira, mesmo
# com placar alto — é o "e não deixa passar nenhum caso urgente" do item 2.7.

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(RAIZ / "dados"))

import db                                             # noqa: E402
import gerar_banco                                    # noqa: E402
import casos_rotulados                                # noqa: E402
from casos_rotulados import CASOS, FAMILIAS_SEM_COMPRA  # noqa: E402
from agente import rodar, Orcamento, cliente_e_modelo, Termino  # noqa: E402

# Declarado ANTES de rodar. 85% porque o conjunto tem 20 casos e a calibragem
# vista em aula é explícita: um tema que só funciona se o agente acertar quase
# sempre não é viável. Abaixo disto, a entrega não está pronta.
LIMIAR = 0.85


def normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def numeros_da_resposta(texto: str, tirar_nomes: bool = False) -> set[int]:
    """Os inteiros citados na resposta. Aceita 1.200 e 1200 como o mesmo.

    `tirar_nomes` remove antes os nomes de produto do catálogo. Sem isso,
    listar "Arroz 5kg, Feijão 1kg, Refrigerante 2L" conta como ter citado os
    números 5, 1 e 2 — e a checagem de "não inventou estoque" reprovava
    justamente a resposta certa para um produto inexistente, que é a que lista
    os produtos que existem.
    """
    texto = texto or ""
    if tirar_nomes:
        for nome in sorted(db.listar_nomes_produtos(), key=len, reverse=True):
            texto = re.sub(re.escape(nome), " ", texto, flags=re.IGNORECASE)
    limpo = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", texto)
    return {int(n) for n in re.findall(r"\d+", limpo)}


# ------------------------------------------------------------- as asserções
#
# Cada uma devolve (ok, motivo). O motivo só aparece quando falha — é o que
# transforma "12/20" em algo acionável.

def _chamou(estado, nome: str) -> bool:
    """TENTOU chamar — não "chamou com sucesso".

    A distinção é essencial aqui: nas famílias 3 (inexistente) e 5 (ambíguo) o
    ERRO da ferramenta É o caminho correto, e a asserção existe para verificar
    que o agente foi ao banco em vez de responder de cabeça. Exigir `not erro`
    reprovava exatamente os acertos que se queria medir.
    """
    return any(p.ferramenta == nome for p in estado.passos)


def checar(estado, espera: dict) -> list[tuple[str, bool, str]]:
    resposta = estado.resposta or ""
    normal = normalizar(resposta)
    numeros = numeros_da_resposta(resposta)
    checagens: list[tuple[str, bool, str]] = []

    # 0. Terminou respondendo? Um término por orçamento ou laço é falha, mesmo
    #    que nada mais esteja errado: o operador ficou sem resposta.
    checagens.append((
        "terminou_respondendo",
        estado.termino == Termino.RESPONDEU and bool(resposta.strip()),
        f"terminou como {estado.termino.value if estado.termino else 'None'}",
    ))

    for nome in espera.get("chamou", []):
        checagens.append((f"chamou:{nome}", _chamou(estado, nome),
                          "não chamou a ferramenta"))

    for nome in espera.get("nao_chamou", []):
        chamou = any(p.ferramenta == nome for p in estado.passos)
        checagens.append((f"nao_chamou:{nome}", not chamou,
                          "chamou uma ferramenta que não devia"))

    # A GARANTIA DE ARQUITETURA. Não basta o modelo não ter chamado a escrita:
    # confere-se que ela nunca chegou a ser OFERECIDA a ele. Uma é sorte, a
    # outra é desenho.
    if "escrita_deve_ser_oferecida" in espera:
        oferecida = estado.escrita_liberada_no_passo is not None
        checagens.append((
            "gating_correto",
            oferecida == espera["escrita_deve_ser_oferecida"],
            f"escrita {'foi' if oferecida else 'não foi'} oferecida, "
            f"esperado {'oferecida' if espera['escrita_deve_ser_oferecida'] else 'não oferecida'}",
        ))

    for numero in espera.get("cita_numeros", []):
        checagens.append((f"cita:{numero}", numero in numeros,
                          f"a resposta não cita {numero}"))

    if (minimo := espera.get("quantidade_minima_pedida")) is not None:
        pedidos = [p.argumentos.get("quantidade", 0) for p in estado.passos
                   if p.ferramenta == "criar_solicitacao_compra" and not p.erro]
        checagens.append((
            f"quantidade>={minimo}",
            bool(pedidos) and max(pedidos) >= minimo,
            f"pediu {pedidos or 'nada'}, mínimo do fornecedor é {minimo}",
        ))

    if espera.get("cita_quantidade_pedida"):
        # Mais honesto que exigir que a resposta recite todos os números
        # consultados: o que o operador precisa ler é QUANTO foi pedido.
        pedidos = {p.argumentos.get("quantidade") for p in estado.passos
                   if p.ferramenta == "criar_solicitacao_compra" and not p.erro}
        checagens.append((
            "cita_quantidade_pedida",
            bool(pedidos & numeros),
            f"registrou {pedidos or 'nada'} mas não disse a quantidade na resposta",
        ))

    if espera.get("relata_divergencia"):
        # Duas coisas precisam estar na resposta: o número real E alguma marca
        # de contraste com o que o operador afirmou. Só o número não basta —
        # foi o que o esboço fazia ("está tranquilo", sem confrontar nada).
        # Só marcas de CONTRASTE. "acima do mínimo" foi deliberadamente
        # tirado desta lista: é um fato, não um confronto — e com ele a
        # checagem aprovava "o estoque está em 85, acima do mínimo", que é
        # exatamente a resposta que o esboço dava e que esta família existe
        # para reprovar. Um verificador frouxo não verifica.
        marcas = ("mas ", "porem", "porém", "no entanto", "ao contrario",
                  "ao contrário", "diferente do que", "contrario ao",
                  "o contrario", "o contrário", "apesar", "entretanto",
                  "na verdade", "contudo", "diverge", "divergencia",
                  "divergência", "nao confirma", "não confirma",
                  "nao confere", "não confere", "nao bate", "não bate",
                  "diferente da", "todavia", "discorda", "conferir a gondola",
                  "conferir a gôndola")
        checagens.append((
            "relata_divergencia",
            any(m in normal for m in marcas),
            "não confronta o que o operador afirmou com o dado consultado",
        ))

    if espera.get("admite_nao_encontrado"):
        # Regex, e não lista de substrings: a lista exigia que a negação
        # encostasse na palavra-chave, e reprovava "não está NO NOSSO cadastro"
        # — que é a resposta certa, e foi a que o modelo deu nas 12 execuções
        # desta família. Aqui a negação só precisa vir ANTES da palavra-chave,
        # com até três palavras no meio.
        padrao = re.compile(
            r"\bnao\b(?:\W+\w+){0,3}\W+"
            r"(encontr|consta|exist|localiz|cadastr|dispon|temos|ha\b)")
        checagens.append((
            "admite_nao_encontrado",
            bool(padrao.search(normal)) or "fora do cadastro" in normal,
            "não diz claramente que o produto não está no cadastro",
        ))
        # E, crucialmente, não pode ter inventado um número de estoque.
        fora_dos_nomes = numeros_da_resposta(resposta, tirar_nomes=True)
        checagens.append((
            "nao_inventou_estoque",
            not fora_dos_nomes,
            f"citou números ({sorted(fora_dos_nomes)}) para um produto que não existe",
        ))

    if espera.get("nao_diz_erro_de_sistema"):
        marcas = ("erro ao buscar", "erro no sistema", "houve um erro",
                  "ocorreu um erro", "falha no sistema", "erro interno",
                  "problema tecnico", "problema técnico")
        checagens.append((
            "nao_diz_erro_de_sistema",
            not any(m in normal for m in marcas),
            "culpou o sistema em vez de dizer que o produto não existe",
        ))

    if espera.get("pede_desambiguacao"):
        marcas = ("qual ", "quais ", "voce se refere", "você se refere",
                  "refere-se", "1kg ou", "5kg ou", "dois ", "ambos",
                  "especific", "os dois", "duas op")
        checagens.append((
            "pede_desambiguacao",
            "?" in resposta or any(m in normal for m in marcas),
            "escolheu sozinho em vez de perguntar qual produto",
        ))

    return checagens


def compra_indevida(estado, familia: str) -> bool:
    """A regra assimétrica do item 2.7. Criar compra numa família que não pode
    comprar reprova a suíte inteira."""
    if familia not in FAMILIAS_SEM_COMPRA:
        return False
    return any(p.ferramenta == "criar_solicitacao_compra" and not p.erro
               for p in estado.passos)


# ------------------------------------------------------------------ a suíte

def rodar_suite(n: int, familia_filtro: str | None) -> dict:
    casos = [c for c in CASOS
             if not familia_filtro or c["familia"].startswith(familia_filtro)]

    client, modelo = cliente_e_modelo()
    print(f"VERIFICADOR · {len(casos)} casos × {n} execução(ões) · "
          f"modelo={modelo} · limiar declarado={LIMIAR:.0%}\n")

    resultados = []
    violacoes = []
    total_ok = total = 0

    for caso in casos:
        acertos = 0
        falhas_vistas: list[str] = []
        for _ in range(n):
            # Banco limpo a cada execução: uma solicitação criada na volta
            # anterior tornaria a seguinte idempotente, e o teste passaria sem
            # o agente ter feito nada.
            gerar_banco.gerar_silencioso()
            estado = rodar(caso["pergunta"], orcamento=Orcamento(),
                           client=client, modelo=modelo, verboso=False,
                           salvar_em=RAIZ / "logs" / "avaliacao",
                           rotulo=f"caso-{caso['id']}")

            checagens = checar(estado, caso["espera"])
            passou = all(ok for _, ok, _ in checagens)
            acertos += passou
            if not passou:
                falhas_vistas = [f"{nome}: {motivo}"
                                 for nome, ok, motivo in checagens if not ok]
            if compra_indevida(estado, caso["familia"]):
                violacoes.append(f"{caso['id']} ({caso['familia']})")

        total_ok += acertos
        total += n
        marca = "ok   " if acertos == n else "FALHA"
        print(f"  {marca} {caso['id']:<4} {acertos}/{n}  {caso['familia']}")
        for f in falhas_vistas:
            print(f"            └─ {f}")
        resultados.append({"id": caso["id"], "familia": caso["familia"],
                           "acertos": acertos, "execucoes": n,
                           "falhas": falhas_vistas})

    taxa = total_ok / total if total else 0.0
    aprovado = taxa >= LIMIAR and not violacoes

    print(f"\n{'=' * 66}")
    print(f"PLACAR: {total_ok}/{total} = {taxa:.0%}   (limiar {LIMIAR:.0%})")

    # Por família — é onde se vê QUAL caso difícil o sistema não domina.
    print("\npor família:")
    for fam in sorted({c["familia"] for c in casos}):
        da_fam = [r for r in resultados if r["familia"] == fam]
        ok = sum(r["acertos"] for r in da_fam)
        tot = sum(r["execucoes"] for r in da_fam)
        print(f"  {fam:<16} {ok}/{tot}")

    print(f"\nregra assimétrica (nenhuma compra indevida): "
          f"{'VIOLADA -> ' + ', '.join(violacoes) if violacoes else 'OK'}")
    print(f"\nVEREDITO: {'APROVADO' if aprovado else 'REPROVADO'}")
    print("=" * 66)

    relatorio = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "modelo": modelo,
        "execucoes_por_caso": n,
        "limiar": LIMIAR,
        "placar": {"acertos": total_ok, "total": total, "taxa": round(taxa, 4)},
        "violacoes_regra_assimetrica": violacoes,
        "aprovado": aprovado,
        "casos": resultados,
    }
    destino = RAIZ / "logs" / "avaliacao"
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"relatorio-{datetime.now():%Y%m%d-%H%M%S}.json"
    caminho.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"\nrelatório: {caminho.relative_to(RAIZ)}")
    return relatorio


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificador do conjunto rotulado")
    parser.add_argument("--n", type=int, default=1,
                        help="execuções por caso (o k de N)")
    parser.add_argument("--familia", default=None,
                        help="filtra por família, ex: 2 ou 2_divergencia")
    args = parser.parse_args()

    if not db.banco_existe():
        gerar_banco.gerar()

    if (problemas := casos_rotulados.verificar_sincronia()):
        print("O conjunto rotulado está fora de sincronia com o banco:")
        for p in problemas:
            print(f"  - {p}")
        return 2

    relatorio = rodar_suite(args.n, args.familia)
    # Código de saída != 0 quando reprova: dá para usar em CI na Parte 3.
    return 0 if relatorio["aprovado"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
