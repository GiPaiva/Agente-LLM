# Memória entre execuções, e a gestão da conversa — item 5

> Código: `src/conhecimento.py` (episódica, semântica, decaimento, remoção por
> thread), `src/grafo.py` (`_mensagens`, `_finalizar`, `remover_conversa`),
> `src/prompts/procedimento.md` (procedural). Evidências: `logs/memoria/` e o
> teste `tests/test_sistema.py::test_memoria_idempotente_contradicao_decaimento_remocao`.

---

## 1. Os dois níveis, no nosso case

| | curto prazo | longo prazo |
|---|---|---|
| **o que é** | a execução corrente de **um** pedido do operador | o que o operador já viveu com o sistema |
| **conteúdo** | system prompt (`reposicao.md` + `procedimento.md`), objetivo (o texto), evidências (registros do cadastro e trechos do corpus), proposta calculada, trajetória (`mensagens`, `eventos`), contadores de orçamento | **episódios** (o que aconteceu com que produto, e se houve divergência), **fatos** ("açúcar" → `ACUCAR_5KG` para a Ana), **procedimento** (como repor, versionado) |
| **persistido como** | checkpoint do LangGraph em `runtime/checkpoints.sqlite` (`SqliteSaver`) | tabelas `episodios` (com vetor) e `fatos` (chave-valor) em `runtime/conhecimento.sqlite`; o procedimento como arquivo em `src/prompts/` |
| **ciclo de vida** | morre quando a conversa é removida, e fica inerte quando a execução termina | acumula, até ser esquecido (§4) |

### O que precisa estar no checkpoint para retomar sem reaplicar efeito

A retomada do `interrupt` reexecuta o nó `aprovar` do começo (ver
[`humano.md`](humano.md) §3). Para ela não repetir nenhum efeito, o checkpoint
guarda:

- `caso_id`: é a chave da linha em `casos` e a chave de idempotência da
  escrita. Com ele, o serviço sabe que a compra daquele caso já existe;
- `proposta` e `produto`, tal como foram consultados, para mostrar ao gerente a
  mesma coisa que o revisor aprovou;
- `parecer` e `decisao`, para que a retomada não chame o revisor (modelo) de novo;
- os contadores (`n_modelo`, `n_ferramentas`, `tokens_*`, `processamento_s`).
  Sem eles, cada retomada zeraria o orçamento.

O que **não** vai para o checkpoint: a capacidade privada de escrita (fica só
na tabela `casos` do serviço, e o teste
`test_pausa_reinicio_edicao_e_aprovacao_duplicada` confere que ela não aparece
nos logs) e os vetores dos documentos.

### A ordem de descarte quando a janela não cabe

`_mensagens` (`src/grafo.py`) monta a visão do modelo a partir do estado, e o
estado no checkpoint continua íntegro. O orçamento é de
`max_contexto_caracteres = 24 000`, uma estimativa conservadora em caracteres,
não em tokens.

| Prioridade | Fonte | Política |
|---|---|---|
| **nunca sai** | system prompt (papel + procedimento) | fixo |
| **nunca sai** | objetivo (texto do pedido), evidências desta execução, proposta | fixo; é a âncora |
| sai por último | blocos mais recentes da trajetória | entram do mais novo para o mais antigo enquanto couberem |
| **sai primeiro** | blocos mais antigos da trajetória (inclusive turnos anteriores da mesma conversa) | descartados inteiros: nunca se corta metade de um par `assistant`/`tool`, o que quebraria o contrato da API |

A entrada maior que a janela é recusada **antes** de chamar o modelo
(`_interpretar`, teste `test_entrada_vazia_e_longa_nao_chama_modelo`), em vez de
ser truncada no fim, que é onde está o pedido.

---

## 2. A fronteira: checkpoint × memória × RAG, no nosso case

| | checkpoint | memória | RAG |
|---|---|---|---|
| **escopo** | uma conversa (`thread_id`) | todas as conversas **do mesmo operador** | nenhuma; é externo |
| **propósito** | **retomar** a aprovação pendente | **lembrar** a embalagem que a Ana confirmou, e que ela já relatou falta de refrigerante | **consultar** a política de compras e os contratos |
| **forma** | estado íntegro do grafo | fragmento selecionado: um resumo de resultado, nunca a entrada bruta | trecho de documento curado (`dados/corpus/`) |
| **leitura** | uma vez, ao retomar ou ao continuar a conversa | `lembrar` por similaridade a cada pedido (top-2, ≥ 0,4); `fato` por chave quando o produto é ambíguo | por relevância, **quando o modelo pede** (`buscar_documentos`) |
| **quem escreve** | o LangGraph, a cada superstep | o **código**, em `_finalizar` e em `_coletar` | ninguém em execução: o corpus é curado pelo grupo |

**O que a recuperação por relevância traz que a serialização integral não
traria:** quando a Ana pergunta do refrigerante, entram dois episódios
parecidos (um, a divergência de semana passada), e não as centenas de execuções
dela. **O que ela deixa para trás:** episódios de outros produtos e qualquer
detalhe da trajetória (os argumentos de cada ferramenta), que não são
guardados no episódio. Um episódio diz *o que aconteceu*, não *como*.

**Episódio não é estoque.** O episódio entra no contexto com a chave
`episodios_anteriores_nao_sao_estoque_atual`, porque um estoque lembrado de
ontem não é o estoque de hoje. O número citado vem sempre do cadastro
consultado na execução.

---

## 3. As três memórias, nas estruturas certas

| Tipo | O que guarda no case | Estrutura | Por que essa |
|---|---|---|---|
| **episódica** | `{caso, produto, nome, status, solicitacao resumida, divergencia}` do fim de cada execução com produto | tabela `episodios` + vetor do embedding local (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dim) | "já aconteceu algo parecido?" é pergunta de assunto, então a similaridade serve |
| **semântica** | `(usuario, alias) → produto_id`: "açúcar" quer dizer `ACUCAR_5KG` para a Ana | tabela `fatos`, consulta por **chave** exata | o alias é uma chave e tem uma resposta; buscar por similaridade seria caro e impreciso |
| **procedural** | como repor: interpretar → cadastro → divergência → documentos → deixar escrita ao código | **texto no system prompt** (`src/prompts/procedimento.md`), versionado no Git | é instrução, não fato. Muda por revisão do grupo, nunca por aprendizado automático (a última linha do arquivo proíbe isso) |

**O fato semântico sugere, mas não decide.** Mesmo com o alias confirmado, a
consulta ambígua seguinte continua perguntando, e acrescenta *"Escolha anterior
confirmada: ACUCAR_5KG. Confirme a embalagem novamente."* (`_coletar`). Errar a
embalagem compra o produto errado, e o custo de uma pergunta a mais é pequeno.

---

## 4. A política de escrita

**Escolha: o código extrai por regra.** O modelo não tem ferramenta de
memória. O preço declarado é perder o que a regra não previu (ex.: o operador
diz *"o fornecedor B atrasou de novo"*, e isso não vira memória).

| Escrita | Quando | Volume por execução | Chave de idempotência |
|---|---|---|---|
| episódio | `_finalizar`, se houve produto consultado e a execução terminou em `criada`, `respondido`, `rejeitada`, `expirada` ou `recusado` | **0 ou 1** registro, cerca de 200–400 bytes de JSON + 1 vetor de 384 floats (1,5 KB) | `sha256(usuario, thread, conteudo)`, com `ja_existia` no retorno |
| fato | `_coletar`, quando o operador responde à desambiguação com uma única embalagem que bate com um dos candidatos | **0 ou 1** registro, cerca de 100 bytes | `sha256(usuario, alias, produto_id, thread, caso)`, com `ja_existia` |

A chave é **derivada do conteúdo**: o mesmo resultado na mesma conversa gera a
mesma chave, e o replay de uma retomada não duplica nada (testes
`test_memoria_idempotente_...` e `test_fato_reconfirmado_e_memoria_concorrente`,
este último com 4 escritas concorrentes que geram 1 registro). Uma
**nova** confirmação, em outro caso, é um novo evento, e por isso a chave do fato
inclui o caso.

O que **nunca** é gravado: a entrada bruta do operador (pode conter instrução
injetada), os trechos de documento, a capacidade de escrita.

---

## 5. Como o agente esquece

O case precisa das **três** causas, por três razões diferentes:

| Causa | Por que o case precisa | O que faz no sistema | O dado é apagado? |
|---|---|---|---|
| **contradição** | a Ana confirmou "açúcar = 1kg" num dia e "açúcar = 5kg" noutro | `fato()` lê o **mais recente** por carimbo de tempo (`ORDER BY quando DESC`) | não: o antigo continua na tabela, como histórico |
| **decaimento** | um episódio de compra de 2 meses atrás não diz nada sobre o giro de hoje, e a tabela cresce sem parar | `decair()` roda a cada `lembrar()` e **apaga** episódios com mais de **30 dias** (`Config.memoria_dias`) | sim |
| **remoção** | a memória guarda o identificador do operador (dado de pessoa, ver `case.md` §12.5) | `remover_conversa(thread_id)` (CLI: `--remover-conversa <thread> --perfil gerente`) | sim |

**Por que 30 dias.** O ciclo de compras do case é semanal, com prazos de 2 e 5
dias (`FORN-A`, `FORN-B`). Um episódio com mais de quatro ciclos já foi
substituído por consultas mais novas do mesmo produto. É uma escolha do grupo,
não uma medição de giro real (ver `case.md` §11).

### A cobertura da remoção

A remoção é **por conversa**. Estruturas em que o identificador pode estar, e o
que acontece com cada uma:

| Estrutura | O que guarda | Na remoção |
|---|---|---|
| checkpoint (`checkpoints.sqlite`: `checkpoints`, `writes`) | o estado inteiro, inclusive o texto e os argumentos de cada passo | `delete_thread` |
| `episodios` | resumo e vetor | `DELETE ... WHERE thread=?` |
| `fatos` | alias → produto | `DELETE ... WHERE thread=?` |
| logs operacionais (`runtime/logs/`) | entrada, eventos e argumentos das ferramentas | apagados |
| logs exportados (`logs/`) e blocos JSON de `README.md` / `docs/io.md` | exemplos | apagados, ou substituídos por um aviso |
| procedural (`procedimento.md`) | não menciona operador; não é aprendida | nada a remover |
| `casos` / `solicitacoes` (`operacao.sqlite`) | `usuario` e proposta de cada compra | **retidos de propósito**: registro contábil. Pendência aberta é cancelada |

**A verificação independente** (`python src/demonstrar_remocao.py`): grava o
fato na conversa A, mostra que a conversa B passa a dizer *"Escolha anterior
confirmada"*, remove A, mostra que a conversa C volta a não dizer, e varre
**todas** as tabelas de todos os SQLite e todos os logs procurando o id de A.
Resultado registrado em `logs/memoria/`.

**O achado da varredura:** o id de A some de todas as estruturas, mas a
**pista derivada** do fato de A continua no checkpoint e no log da conversa B,
que a usou. A remoção por thread não alcança dado derivado que outra conversa
copiou. Para um pedido de titular ("apague tudo da Ana"), a resposta correta é
remover **todas** as conversas do usuário. Isso hoje exige listar as threads e
remover uma a uma, e está declarado como limitação.

Nenhuma causa de esquecimento exige reconstruir o índice: episódios e fatos são
linhas, e o índice de documentos é separado. A remoção serve, portanto, também
à **recuperação de incidente**: um episódio envenenado sai com um `DELETE`, sem
janela de manutenção.

---

## 6. A conversa, e o que sobra dela

**O que identifica uma conversa.** `thread_id = "<usuario>:<uuid4>"`, gerado em
`Aplicacao.iniciar` quando a CLI não recebe `--thread`. O usuário vem do
argumento `--usuario`, e não é digitado no texto (ver [`io.md`](io.md) §1). Duas
conversas simultâneas da mesma pessoa são dois `thread_id` diferentes, com
checkpoints independentes, e compartilham só a memória de longo prazo. Retomar
a conversa de outra pessoa dá `PermissionError` (teste
`test_isolamento_conversa_e_fato_confirmado`). Uma conversa com aprovação
pendente não aceita pergunta nova até ser decidida.

**Onde o checkpoint é gravado.** Em arquivo SQLite (`runtime/checkpoints.sqlite`,
`SqliteSaver`), e sobrevive ao fim do processo. O teste
`test_pausa_reinicio_edicao_e_aprovacao_duplicada` fecha a aplicação na pausa,
abre outra e aprova. **Limitação:** é um arquivo local de uma máquina; dois
processos aprovando ao mesmo tempo dependem do lock do SQLite, e não há
replicação.

**O que acontece quando a janela enche.** Política: **descartar os blocos mais
antigos da trajetória, inteiros** (§1). Perde-se o raciocínio dos turnos
antigos da mesma conversa, por exemplo a pergunta de desambiguação de três
turnos atrás. Isso é aceitável porque a desambiguação pendente é guardada em
campos próprios do estado (`alias_pendente`, `candidatos_pendentes`), e não
depende das mensagens. Sumarizar custaria uma chamada a mais de modelo por
turno, num modelo local de 30 s por chamada.

**O que passa da conversa para a memória de longo prazo.** Só o que o §4
declara: no máximo um episódio e um fato por execução. A trajetória, o texto
digitado e os trechos recuperados **não** sobem.
