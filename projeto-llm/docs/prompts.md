# O plano de prompt engineering — item 2

> Os prompts são **fonte** e vivem em `src/prompts/`, um arquivo por prompt,
> carregados em tempo de execução por `Aplicacao._prompt` (`src/grafo.py`). Este
> documento é o **raciocínio** sobre eles. Os prompts `sistema-v1..v3.md` são
> da Parte 1, e ficam no diretório como histórico versionado do laço antigo:
> o grafo atual não os carrega.

## 1. A combinação em uso, registrada em cada execução

Todo log de execução (`runtime/logs/*.json`, exportados em `logs/`) grava no
início:

- `versao.commit` e `versao.working_tree_modificado`;
- `versao.arquivos`: o sha256 de **cada** arquivo de `src/` e `dados/`,
  inclusive cada prompt;
- `modelo` e `parametros` (`temperature`, `max_tokens`, `timeout_s`, tetos,
  `recursion_limit`, `k` e limiar do RAG).

Com isso, dois logs com o mesmo hash de `src/prompts/triagem.md` usaram o mesmo
prompt de triagem, e a comparação entre semanas é um `diff`.

## 2. Uma linha por etapa em que o modelo é chamado

Parâmetros comuns a todas as etapas: `google/gemma-4-e4b` local (LM Studio),
`temperature=0`, `max_tokens=4096`, `tool_choice="required"`,
`parallel_tool_calls=false`. A saída é **sempre uma chamada de função**, e o
texto livre do modelo nunca é lido.

| Etapa | Prompt | Técnica | Por que ela | Contrato de saída | Como é testada |
|---|---|---|---|---|---|
| **triagem** (`interpretar`) | `triagem.md` | **zero-shot com regras** + saída estruturada por função forçada (`extrair_intencao`) | a separação consulta × reposição é uma convenção do domínio que cabe em uma frase cada ("pergunta informativa é consulta, mesmo com estoque baixo"). Não usamos exemplos porque a lição medida da Parte 1 (`docs/decisoes.md`, decisão 5) foi outra: o que falhava era regra escrita como **permissão**, que o modelo lia como restrição. A triagem usa regras afirmativas curtas, e a eficácia de cada uma é medida (§3) | `Interpretacao`: `intencao` ∈ `{consulta, reposicao, politica, fora_escopo}` (obrigatória), `produto: str`, `relato_falta: bool`, `pergunta: str`. **Proibido:** campo extra (`extra="forbid"`), intenção fora do `Literal`, produto ou embalagem inventados. `null` nos opcionais vale como ausente | rota correta nas 8 demonstrações reais (`io.md`); ablação da frase em 11 casos rotulados × 2 (§3); `test_triagem_null_e_ausente_mas_intencao_continua_estrita` |
| **decisão / resposta do RAG** (`agente`) | `reposicao.md` + `procedimento.md` | **zero-shot com ferramentas** (ReAct: o modelo escolhe entre ler mais ou responder) + **papel** declarado + **procedimento** em passos como memória procedural | a decisão é *"preciso buscar mais?"* e *"tenho base?"*: julgamento sobre o pedido e o que já foi recuperado, sem rótulo fixo para exemplificar. O procedimento em passos é a decomposição do processo que o case ensinou (`case.md` §12.4) | `RespostaModelo`: `resultado: str` (1–3000), `fontes: list[str]`, `suficiente: bool`. **Proibido:** com `suficiente=true`, fonte vazia ou fora das evidências desta execução; resposta de `politica` sem documento vigente; afirmar que a compra já foi feita; número que não veio de ferramenta | 8 demonstrações reais; `test_fonte_inventada_recusa_apos_uma_correcao`; `test_documento_hostil_nao_concede_escrita`; suíte controlada (60/60, integração) |
| **revisão** (`revisar`) | `revisao.md` | **papel** de revisor independente + **lista de verificação** (decomposição: produto, necessidade, quantidade mínima, orçamento, fontes) + uso **obrigatório** de ao menos uma ferramenta | o valor do revisor é conferir por conta própria, não reler o que o agente disse; a lista impede que ele aprove por estilo | `Parecer`: `aprovado: bool`, `motivos: list[str]`, `fontes: list[str]` ⊆ chaves de `evidencias`. **Proibido:** aprovar sem consulta; citar fonte com prefixo ou inventada; reprovar só por custo > R$ 500 (isso é do humano) | demonstrações `simples` e `aprovacao`; `test_revisor_falha_fechada`; `test_revisor_corrige_id_de_fonte_uma_vez`; `test_revisor_que_insiste_no_id_errado_reprova` |
| **correção de formato** (as três etapas) | `correcao-triagem.md`, `correcao-resposta.md`, `correcao-revisao.md` | **realimentação com o erro do validador**, uma única vez (refinamento de formato, não de conteúdo) | modelo pequeno erra formato de vez em quando (medido: `produto: null`, fonte `evidencias:<id>`); uma segunda chance com o erro exato resolve, e duas não resolvem mais que uma | o mesmo contrato da etapa. Na segunda falha: triagem → `falha`; agente → recusa sem base; revisor → reprova | os testes de correção acima; o caso real do revisor está em `logs/diagnostico/` |

**Etapas que não chamam o modelo**, de propósito:
- **extração de fato para a memória**: é código, por regra (`memoria.md` §4). O
  preço é perder o que a regra não previu;
- **texto da divergência e das recusas fixas** ("Produto não encontrado…",
  "Atendo consultas de estoque…"): são saídas de código. O caso que mais pesa no
  case (`case.md` §12.3) não fica à mercê da redação do modelo;
- **o prompt da pausa humana** (`aprovar`): é um **objeto** com ação,
  argumentos, consequência e prazo, montado em código, porque cada campo vem
  do estado. Não há frase livre para versionar (ver `humano.md` §2).

## 3. A regra da frase — o exercício

**Prompt:** `src/prompts/triagem.md`. **Frase removida:**
*"Pergunta apenas informativa é consulta, mesmo com estoque baixo."*

**Por que essa.** É a frase que carrega a regra implícita nº 1 do case (pergunta
não é pedido, `case.md` §12.2). Se ela não faz nada, a regra está sendo
garantida por outra coisa, o serviço ou o resto do prompt, e a frase só custa
tokens.

**Como medimos.** `python src/experimento_prompt.py 2`: só a etapa de triagem,
com o modelo real, em 11 perguntas rotuladas (4 pedidos de reposição da família
1, 4 consultas da família 4, e 3 consultas sobre produto abaixo do mínimo,
que são o alvo da frase), 2 rodadas por variante. Critério: a `intencao`
extraída é igual ao rótulo.

**O que aconteceu** (`logs/prompts/20261018-214539.json`, commit `6c48749`,
árvore limpa, `google/gemma-4-e4b`):

| Variante | Acertos | Detalhe |
|---|---|---|
| prompt original | **22/22** | 8/8 reposição, 14/14 consulta |
| sem a frase | **22/22** | idem, as mesmas intenções caso a caso, nas duas rodadas |

**Por que ela não fazia nada.** A frase fala de *"estoque baixo"*, mas a
triagem **nunca recebe o estoque**: ela roda antes de `consultar_estoque`, e
o modelo vê só o texto. A frase era uma regra sobre uma informação que a etapa
não tem. Quem de fato impede a consulta de virar compra é (1) a frase
seguinte do mesmo prompt, *"Só use reposicao se houver pedido para avaliar ou
registrar reposição"*, e (2) o serviço, que recusa preparar compra sem
`intencao = reposicao` (`src/servico.py`, `preparar`).

**Decisão: a frase saiu e não voltou.** `src/prompts/triagem.md` ficou uma
frase mais curto a partir do commit seguinte a `6c48749`. O efeito é pequeno
em tokens, mas é o resultado que a regra pede: um prompt que encolheu sem perder
comportamento. Para reproduzir a medição, `git checkout 6c48749 --
src/prompts/triagem.md` e `python src/experimento_prompt.py 2`. Sem a frase,
o script avisa e não roda, para não comparar o prompt com ele mesmo.

**Limite da medição:** 11 perguntas × 2 rodadas, um modelo. Uma frase sem
efeito aqui pode ter efeito com outro modelo. Por isso a medição fica
versionada e o script continua no repositório.
