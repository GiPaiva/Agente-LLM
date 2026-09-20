# Os casos difíceis do dado simulado

Item 2.8 da entrega. Os dados vivem em [`gerar_banco.py`](gerar_banco.py)
(SQLite, `dados/estoque.db`) e são **simulados** — não há dado sensível (item
2.9): nomes de produto e fornecedor são genéricos, sem CNPJ, endereço ou
qualquer dado pessoal.

Os rótulos de cada caso — as propriedades que a resposta correta precisa ter —
estão em [`casos_rotulados.py`](casos_rotulados.py), e quem os confere é
`src/avaliar.py`.

---

## Por que o dado é assim

Um dado fácil teria todo produto perguntado **abaixo** do mínimo (o agente
sempre compra, e o teste não testa nada) ou todo produto **acima** (o agente
nunca compra, idem). Aqui existem as duas situações, mais um produto que não
existe, mais um par de nomes que colidem, mais os dois ramos da regra de
orçamento. Cada linha do catálogo tem um papel.

## O catálogo

| id | nome | estoque | mínimo | giro/dia | preço | fornecedor | papel no teste |
|---|---|---:|---:|---:|---:|---|---|
| `ARROZ_5KG` | Arroz 5kg | 12 | 30 | 8,0 | 18,50 | FORN_A | **caso 1** + ramo "passa do teto" |
| `REFRIGERANTE_2L` | Refrigerante 2L | 85 | 20 | 5,0 | 7,90 | FORN_B | **caso 2** |
| `FEIJAO_1KG` | Feijão 1kg | 40 | 25 | 3,0 | 8,20 | FORN_A | **caso 4** |
| `ACUCAR_1KG` | Açúcar Refinado 1kg | 22 | 20 | 4,0 | 5,40 | FORN_A | **caso 5** (colide com o de baixo) |
| `ACUCAR_5KG` | Açúcar Refinado 5kg | 9 | 15 | 2,0 | 21,90 | FORN_A | **caso 5** |
| `SAL_1KG` | Sal 1kg | 8 | 20 | 1,5 | 2,30 | FORN_A | ramo "dentro do teto" |

| id | fornecedor | prazo | pedido mínimo |
|---|---|---:|---:|
| `FORN_A` | Fornecedor A (mercearia seca) | 2 dias | 50 |
| `FORN_B` | Fornecedor B (bebidas) | 5 dias | 30 |

Orçamento inicial: **R$ 1.200,00**. Teto sem aprovação do gerente: **R$ 500,00**.

---

## Os cinco casos

### 1 — Caso simples · `ARROZ_5KG`

**O que testa:** o caminho feliz completo. Estoque 12 contra mínimo 30, giro
alto. O agente deve consultar, calcular e **registrar** a solicitação.

**A armadilha, e ela é sutil:** a reposição até 2× o mínimo daria
`30×2 − 12 = 48` unidades. Mas o pedido mínimo do Fornecedor A é **50**. Um
agente que faz a conta de cabeça responde 48 e erra; um que confia na
ferramenta responde 50.

> Esta armadilha não é hipotética. Nos logs do esboço o modelo recebeu 48,
> percebeu sozinho que o fornecedor exigia 50, respondeu "50" — e **não
> registrou nada**. Foi o que motivou reescrever `calcular_reposicao` para
> buscar o pedido mínimo por conta própria.

**Bônus:** 50 × R$ 18,50 = **R$ 925,00**, acima do teto de R$ 500 — então este
caso também exercita o ramo `aguardando_aprovacao_gerente`.

### 2 — Divergência · `REFRIGERANTE_2L`

**O que testa:** o que fazer quando a pessoa e o registro discordam.

O operador afirma que *"o refrigerante está acabando"*; o banco mostra **85
unidades contra um mínimo de 20**. O agente tem de **relatar a contradição** —
não aceitar a afirmação e comprar às cegas, e não ignorá-la respondendo só "não
precisa".

**Por que este é o caso mais importante do conjunto:** ele é o único que um
`if estoque < minimo` não resolve, e portanto é o que justifica haver um agente.
O operador provavelmente **não está errado** — ele viu a gôndola vazia, e o
estoque está no depósito. A resposta útil nomeia a diferença.

O caso `2c` roda a mesma armadilha sobre o `FEIJAO_1KG` ("tô vendo que zerou",
com 40 em estoque), para garantir que o comportamento não está decorado para um
produto específico.

### 3 — Registro inexistente · produtos fora do cadastro

**O que testa:** erro de ferramenta que o modelo tem de contornar.

"Iogurte de morango", "leite condensado", "papel higiênico", "sabão em pó" não
existem no catálogo. `consultar_estoque` levanta um `ErroRecuperavel` que volta
ao modelo como **observação**, com a lista dos produtos que existem e a
sugestão de tentar um termo mais curto.

O agente precisa: **não travar**, **não inventar** um número de estoque, e
**não culpar o sistema** — o sistema funcionou; o produto é que não existe.

> No esboço este caso era indistinguível de um bug: a busca por `LIKE` com o
> termo inteiro fazia "feijão de 1kg" **também** não encontrar nada, e o
> conjunto de teste media o bug em vez do agente. Ver
> [`../docs/decisoes.md`](../docs/decisoes.md), decisão 1.

### 4 — Não deve disparar a ação principal · `FEIJAO_1KG`

**O que testa:** o erro assimétrico.

Estoque 40 contra mínimo 25, giro baixo. Uma pergunta genérica ("como está o
feijão?") **não pode** terminar em `criar_solicitacao_compra`.

Criar uma compra desnecessária mexe no orçamento real da loja; deixar de
recomendar uma necessária custa uma pergunta a mais. Por isso este caso vale
mais que os outros: uma única violação **reprova a suíte inteira** em
`src/avaliar.py`, mesmo com placar alto.

Neste caso a ferramenta de escrita **nunca é oferecida** ao modelo — o gating
por fase a mantém fora da lista. Ver [`../docs/arquitetura.md`](../docs/arquitetura.md) §4.

### 5 — Ambiguidade · `ACUCAR_1KG` vs `ACUCAR_5KG`

**O que testa:** o que o usuário **não informa de primeira**.

"O açúcar" casa com dois produtos. `consultar_estoque` levanta um
`ErroRecuperavel` com os candidatos, e o agente precisa **perguntar qual** em
vez de escolher sozinho.

**Por que existe:** é o caso que traz a "complexidade real de interação" que o
item 2.2 do enunciado valoriza — o sistema tem de perceber que não sabe o
suficiente para agir e devolver a pergunta ao operador. Também é o único caso em
que a conversa passa de uma troca.

Os dois açúcares foram escolhidos em lados opostos do mínimo (22/20 e 9/15) de
propósito: qual deles o agente escolheria sozinho muda a resposta, então chutar
não é inofensivo.

---

## Os dois ramos da regra de orçamento

| Produto | Quantidade | Custo | Status resultante |
|---|---:|---:|---|
| `ARROZ_5KG` | 50 | R$ 925,00 | `aguardando_aprovacao_gerente` (> R$ 500) |
| `SAL_1KG` | 50 | R$ 115,00 | `criada` — e debita o orçamento na mesma transação |

Sem o `SAL_1KG` o conjunto nunca exercitaria o caminho em que a solicitação é
criada direto, e metade da regra de negócio ficaria sem teste.
