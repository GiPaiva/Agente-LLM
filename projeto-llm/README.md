# Assistente de reposição de estoque — Parte 1

## Grupo

- Giovanna Paiva Alves
- Matheus Sanchez Duda
- Phelipe Pereira de Souza

## O problema, em uma frase

> O operador de estoque de um supermercado de pequeno porte decide, várias
> vezes por dia, se e quanto pedir de cada produto, cruzando de cabeça estoque
> atual, giro de venda e pedido mínimo do fornecedor — sem nenhum sistema que
> junte essas três informações.

Detalhamento completo em [`docs/case.md`](docs/case.md).

---

## Como rodar

Pré-requisito: **Python 3.11+**. Testado do zero — venv nova, instalação,
`.env` e os 4 casos rodando — em **2 minutos** (29 s de instalação + 94 s
de execução), contra o teto de 5 minutos do enunciado.

```bash
git clone <url-do-repositorio>
cd Agente-LLM

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edite o .env: LLM_BASE_URL, LLM_MODELO e OPENAI_API_KEY.
# O .env.example traz os três candidatos de docs/modelos.md, prontos para copiar.

python src/main.py --demo          # os 4 casos do item 4.5, com log
python src/main.py                 # modo interativo
```

Na primeira execução, se `dados/estoque.db` não existir, ele é **gerado
automaticamente** com os dados simulados — não é preciso rodar nada antes.

### Qual modelo configurar

O sistema fala com qualquer endpoint compatível com a API da OpenAI. Trocar de
provedor é trocar **três variáveis de ambiente**, nunca código. O modelo
escolhido e a justificativa estão em [`docs/modelos.md`](docs/modelos.md).

### Os outros comandos

```bash
python src/avaliar.py              # o verificador: roda o conjunto rotulado
python src/avaliar.py --n 3        # 3 execuções por caso (o critério k de N)
python src/avaliar.py --familia 2  # só a família de divergência
python src/benchmark.py            # compara os 3 candidatos (item 3.3)
python dados/gerar_banco.py        # regenera o banco simulado
```

---

## Como usar

### O que a pessoa digita

Uma pergunta em português sobre um produto do estoque. **Texto livre, sem
formato fixo** — é para ser digitado no meio do turno:

```
O arroz de 5kg está acabando, veja se precisamos pedir mais.
tá acabando o arroz, pede mais pro fornecedor
Como está o feijão?
quanto temos de açúcar?
```

### O que o sistema faz com aquilo

Consulta o estoque real num banco SQLite. Julga — e este é o ponto em que o
modelo decide — se a pergunta pede **ação** ou só **informação**, e se o que
você afirmou bate com o registro. Calcula a quantidade de reposição já
respeitando o pedido mínimo do fornecedor. E, **só quando o produto está de
fato abaixo do mínimo**, registra uma solicitação de compra.

### Que saída ela recebe, e como interpretá-la

Um texto curto com os números consultados, mais uma linha técnica entre
colchetes:

```
[término: respondeu · 2 passos · 5561 tokens]
```

| Campo | O que significa |
|---|---|
| `término` | por que o programa parou: `respondeu`, `orcamento_esgotado`, `laco_detectado`, `truncado` ou `erro_fatal` |
| `passos` | quantas chamadas de ferramenta foram feitas |
| `tokens` | o custo da execução |

Quando uma solicitação é registrada, a resposta traz **protocolo** e **status**:

| Status | O que fazer |
|---|---|
| `criada` | pronto — o orçamento já foi debitado |
| `aguardando_aprovacao_gerente` | passou de R$ 500: **avise o gerente**, o pedido ainda não vale |

Toda execução grava a trajetória completa em `logs/` — ferramenta, argumentos,
resultado, erro, motivo do término e o carimbo `prompt × modelo × parâmetros`.

### Um exemplo completo, real

Entrada e saída **reais**, copiadas de uma execução de `python src/main.py
--demo`. O log completo desta execução está em `logs/demo/`.

```
$ python src/main.py --demo

=== caso 1a · 1_simples ===
Operador: O arroz de 5kg está acabando, veja se precisamos pedir mais.
   passo 0 · contexto enviado: 1210 tokens · fase analise
           consultar_estoque({'produto': 'arroz de 5kg'})
             -> {"id": "ARROZ_5KG", "nome": "Arroz 5kg", "estoque_atual": 12,
                 "estoque_minimo": 30, "abaixo_do_minimo": true, ...}
      [gating] Arroz 5kg está abaixo do mínimo — escrita liberada
   passo 1 · contexto enviado: 1627 tokens · fase reposicao
           calcular_reposicao({'produto_id': 'ARROZ_5KG'})
             -> {"precisa_repor": true, "quantidade_recomendada": 50,
                 "quantidade_antes_do_pedido_minimo": 48,
                 "pedido_minimo_do_fornecedor": 50, "custo_estimado": 925.0, ...}
   passo 2 · contexto enviado: 2143 tokens · fase reposicao
           criar_solicitacao_compra({'produto_id': 'ARROZ_5KG',
                                     'quantidade': 50,
                                     'chave': 'ARROZ_5KG:50'})
             -> {"protocolo": "ARROZ_5KG:50",
                 "status": "aguardando_aprovacao_gerente", ...}
   passo 3 · contexto enviado: 2556 tokens · fase reposicao

Assistente: Sim, precisamos pedir mais. O estoque está baixo (12 unidades,
mínimo 30).

Acabei de criar a solicitação de compra para **50 unidades** do Arroz 5kg.

*   **Protocolo:** ARROZ_5KG:50
*   **Status:** Aguardando aprovação do gerente.
*   **Prazo de entrega:** 2 dias.

[término: respondeu · 3 passos · 8607 tokens]
```

**Como ler este exemplo.** A linha `[gating]` é o momento em que o **código** —
não o modelo — libera a ferramenta de escrita, porque a consulta devolveu
`abaixo_do_minimo: true`. Antes dela, `criar_solicitacao_compra` não existia
para o modelo.

E repare em `quantidade_antes_do_pedido_minimo: 48` contra
`quantidade_recomendada: 50`: repor até 2× o mínimo daria 48, mas o pedido
mínimo do Fornecedor A é 50. Quem aplicou a regra foi a ferramenta, em código —
o modelo apenas repassou o número.

### O que o sistema **não** faz

- **Não envia nada a fornecedor nenhum.** A solicitação fica registrada no
  banco e é cancelável. O envio real é Parte 2/3, e aí exigirá confirmação
  humana.
- **Não aprova sozinho compra acima de R$ 500.** Marca como pendente e passa
  para o gerente.
- **Não inventa número.** Se o produto não está no cadastro, ele diz isso e
  lista os que existem.
- **Não escolhe por você quando o termo é ambíguo.** "Açúcar" casa com dois
  produtos; ele pergunta qual.
- **Não lembra da conversa anterior.** Cada pergunta é uma execução
  independente. Memória entre execuções é Parte 2.
- **Não sabe o que você viu na loja.** Se você sabe de uma promoção que vai
  esvaziar a gôndola amanhã, ele não tem como saber — ele responde pelo
  histórico.

### Quando ele não sabe responder

Ele **diz o que não achou e o que existe**, em vez de chutar ou de culpar o
sistema:

```
Você: Quanto temos de iogurte de morango no estoque?

Assistente: Desculpe, mas "iogurte de morango" não está no nosso cadastro atual. Os produtos que temos cadastrados são: Arroz 5kg, Açúcar Refinado 1kg, Açúcar Refinado 5kg, Feijão 1kg, Refrigerante 2L e Sal 1kg.
```

E quando o que você diz **não bate** com o registro, ele diz os dois lados em
vez de escolher um:

```
Você: O refrigerante de 2 litros está acabando, já pode pedir mais pro fornecedor?

Assistente: O sistema mostra o contrário do que você viu: há 85 unidades de Refrigerante 2L, acima do mínimo de 20. Não precisa pedir agora.
```

---

## Como sabemos que a saída está certa

O verificador é código, não opinião: **20 casos rotulados à mão**
(`dados/casos_rotulados.py`), conferidos por `src/avaliar.py` com asserções de
propriedade, `k de N` execuções e **limiar declarado antes de rodar**.

```bash
python src/avaliar.py --n 3
```

Ele imprime o placar com denominador, o resultado por família, se a **regra
assimétrica** foi violada (nenhuma compra indevida) e um veredito — e devolve
código de saída ≠ 0 quando reprova.

Os números medidos estão em [`docs/decisoes.md`](docs/decisoes.md) e
[`docs/modelos.md`](docs/modelos.md); os relatórios brutos em `logs/avaliacao/`.

---

## Estrutura do repositório

```
README.md              este arquivo
requirements.txt       dependências com versão fixada
.env.example           os nomes das variáveis, sem nenhum valor

docs/                  TODA a pesquisa e documentação do case
  case.md              itens 1 e 2 — tema, usuários, workflow, justificativa
  modelos.md           item 3 — os 3 candidatos, comparados de verdade
  arquitetura.md       item 4.4 — diagrama, quem decide, orçamento, gating
  decisoes.md          o histórico: o que mudou do esboço, e por quê
  fontes.md            tudo que foi consultado, com link

prompts/               os prompts, versionados
  sistema-v1.md        a versão do esboço
  sistema-v2.md        a reescrita
  sistema-v3.md        a versão ativa

src/                   o agente
  db.py                camada de acesso ao SQLite (item 4.2 — a fronteira)
  ferramentas.py       as 4 ferramentas, as declarações e as FASES
  agente.py            Estado, Orçamento, gating e o laço (item 4.1)
  main.py              ponto de entrada (interativo e --demo)
  avaliar.py           o verificador (itens 2.6 e 2.7)
  benchmark.py         a verificação mínima dos 3 candidatos (item 3.3)

dados/                 os dados simulados
  gerar_banco.py       gera dados/estoque.db
  casos_rotulados.py   o conjunto rotulado, com as asserções
  casos-dificeis.md    os casos difíceis nomeados (item 2.8)

logs/
  demo/                as 4 execuções demonstradas (item 4.5)
  avaliacao/           os relatórios do verificador
  benchmark/           a comparação dos 3 modelos
```

E, fora da entrega, o material que a explica:

```
trabalhos/             o enunciado do professor
notas-aula/            o código das aulas
ideia-evolucao/        as anotações do grupo, da v1 à v2 da ideia
agente-estoque-parte1-esboco/
                       o esboço do grupo, preservado — é o "antes" de
                       docs/decisoes.md
```

---

## Onde está cada item da entrega

| Item | Onde |
|---|---|
| 0 · o grupo | este arquivo, acima |
| 1 e 2 · tema, usuários, workflow, negócio | [`docs/case.md`](docs/case.md) |
| 2.6 · o verificador | [`docs/case.md`](docs/case.md) §6 · `src/avaliar.py` |
| 2.8 · os dados e os casos difíceis | [`dados/casos-dificeis.md`](dados/casos-dificeis.md) |
| 3 · a análise de modelos | [`docs/modelos.md`](docs/modelos.md) |
| 4.1 · o agente | `src/agente.py` |
| 4.2 · a integração com software tradicional | `src/db.py` → SQLite |
| 4.3 · o prompt engineering | `prompts/sistema-v3.md` |
| 4.4 · a arquitetura básica | [`docs/arquitetura.md`](docs/arquitetura.md) |
| 4.5 · a demonstração, com log | `logs/demo/` |
| 4.6 · as instruções de uso | este arquivo, "Como rodar" e "Como usar" |
