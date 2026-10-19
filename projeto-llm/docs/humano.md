# Human-in-the-loop — item 8

> Código: `src/grafo.py` (`_preparar`, `_aprovar`, `_escrever`, `retomar`),
> `src/servico.py` (`preparar`, `decidir`, `finalizar`, `pendentes`),
> `src/contratos.py` (`DecisaoHumana`). Diagrama com o ponto de parada:
> [`arquitetura.md`](arquitetura.md) §1. Execução real com pausa, edição e
> aprovação repetida: [`io.md`](io.md), exemplo 6.

---

## 1. Onde o grafo para, e por qual critério

O grafo tem **um** ponto de parada: o nó `aprovar`, que chama `interrupt(...)`.
Quem decide se o fluxo passa por ele é uma **regra em código**, a aresta
condicional que sai de `preparar`:

```python
# src/grafo.py, _compilar
"aprovar" if proposta["custo_estimado"] > min(500, proposta["orcamento_disponivel"]) else "escrever"
```

| Critério do enunciado | Como aparece no case | Para? |
|---|---|---|
| **custo acima de um teto** | solicitação acima de **R$ 500** (`POL-V2 §1`) | **sim**, é o critério principal |
| **custo acima do saldo** | a recomendação passa do orçamento restante, mas uma quantidade menor (≥ pedido mínimo) caberia (`POL-V2 §2`) | **sim**: o gerente precisa **editar** a quantidade |
| | nem o pedido mínimo cabe no saldo | **não para**: `validar` recusa direto. Nenhuma aprovação tornaria a compra válida, então perguntar seria transferir a responsabilidade sem dar escolha |
| **ação irreversível** | o sistema **não tem** ação irreversível: não envia pedido a fornecedor. A ação mais perigosa é `registrar_compra`, que debita o orçamento local | não é o critério de parada; a escrita abaixo de R$ 500 segue automática, como a política manda |
| **confiança baixa** | a revisão independente reprovou, ou a resposta não tem fonte | **não para, recusa**: `preparar` encerra com `recusado` quando o parecer não aprova, e `agente` recusa depois de uma correção sem fonte. Pedir aprovação humana de uma proposta que o próprio sistema não sustenta seria carimbo |

**Quem é chamado:** o perfil **gerente** (`retomar(..., perfil="gerente")`,
CLI `--perfil gerente`). O operador, que abriu o pedido, recebe
`aguardando_aprovacao` e **não** consegue aprovar: `retomar` com outro perfil
levanta `PermissionError` (teste `test_pausa_reinicio_edicao_e_aprovacao_duplicada`).

**Limitação declarada:** o perfil é um argumento de linha de comando, não uma
autenticação. Numa loja real, ele viria do login do sistema.

---

## 2. O que a pessoa vê, e o que ela devolve

O valor passado ao `interrupt` é o prompt da pausa, e segue a regra do §2.3:
mostra a ação exata, os argumentos e a consequência, e nunca um "confirma?"
solto.

```json
{
  "acao": "registrar_compra",
  "caso_id": "…",
  "produto": "Arroz 5kg",
  "fornecedor": "FORN_A",
  "quantidade": 50,
  "custo_estimado": 925.0,
  "orcamento": 1200.0,
  "motivo": "Valor acima de R$ 500 ou quantidade precisa de ajuste ao saldo",
  "consequencia": "Criar uma solicitação local e debitar o orçamento; nenhum envio externo.",
  "respostas": ["aprovar", "rejeitar"],
  "editavel": ["quantidade"],
  "erro_validacao_anterior": null,
  "expira": "2026-…T…-03:00"
}
```

O que a pessoa devolve é validado por `DecisaoHumana`, com `extra="forbid"`
e `strict=True`: só `acao` e `quantidade`, sem campos livres.

| Resposta | Comando | O que acontece |
|---|---|---|
| **aprovar** | `--perfil gerente --thread T --retomar aprovar` | `escrever` registra a solicitação com a quantidade proposta |
| **aprovar editando** | `... --retomar aprovar --quantidade 55` | o serviço revalida a quantidade nova (≥ pedido mínimo, custo ≤ saldo, estoque ainda abaixo do mínimo) e registra **55** |
| **rejeitar** | `... --retomar rejeitar` | o caso fica `rejeitada`, nada é escrito, o orçamento não muda |
| edição **inválida** | `... --quantidade 10` (abaixo do pedido mínimo de 50) | o serviço recusa (`RegraNegocio`), e o grafo **volta a `aprovar`** com `erro_validacao_anterior` preenchido. A pessoa vê por que a edição não valeu e decide de novo (teste `test_edicao_invalida_volta_a_pausa`) |

A edição só pode **reduzir o risco**, nunca contorná-lo. O gerente não
ultrapassa o saldo (teste `test_gerente_nao_ultrapassa_saldo`), porque a
`POL-V2 §2` diz que nem ele pode. Também não troca produto, preço nem
fornecedor: esses campos não são editáveis, e o serviço revalida preço e
fornecedor no momento da escrita.

---

## 3. A implementação, e por que ela depende do checkpoint

```
preparar ──(custo > min(500, saldo))──> aprovar ── interrupt(payload) ──> [PAUSA]
                                                                            │ checkpoint gravado
                                                     Command(resume=decisao)│ em runtime/checkpoints.sqlite
                                           aprovar (roda DE NOVO, do início)│
                                                 └─ interrupt devolve a decisão
                                          escrever ── servico.finalizar(caso_id, capacidade)
```

- **Nenhum efeito colateral antes do `interrupt`.** `_aprovar` só **lê**
  (`servico.caso(...)["expira"]`) e monta o payload. A criação da linha em
  `casos` acontece no nó **anterior**, `preparar`, com `INSERT OR IGNORE` pela
  chave `caso_id`. Ela é idempotente, então também não duplica se `preparar`
  rodar de novo.
- **O checkpointer é o `SqliteSaver`** do `langgraph-checkpoint-sqlite`
  (versão fixada em `requirements.txt`), gravando em
  `runtime/checkpoints.sqlite` e endereçado por `thread_id`. **Não é memória:**
  a aprovação pendente sobrevive ao fim do processo. O teste
  `test_pausa_reinicio_edicao_e_aprovacao_duplicada` fecha a aplicação durante
  a pausa, abre outra instância e aprova.
- **A conversa pausada não aceita pergunta nova.** `iniciar` numa thread com
  `next` pendente levanta `ValueError`. Isso evita que uma pergunta nova
  sobrescreva o estado da aprovação.
- O tempo de espera do humano **não conta** no teto de processamento ativo
  (teste `test_espera_humana_nao_consume_processamento`).

---

## 4. O que acontece se ninguém responder

| | |
|---|---|
| **prazo** | **24 horas** (`Config.aprovacao_horas`, da `POL-V2 §4`), gravado em `casos.expira` no momento de `preparar` |
| **quando vence** | a solicitação **expira**, e expirar é **rejeitar**: status `expirada`, nada é escrito, o orçamento fica intacto |
| **quem percebe** | o prazo é verificado quando a pendência é **listada** (`--pendentes`) ou **retomada**. Uma aprovação que chega depois do prazo devolve `expirada` (teste `test_rejeicao_e_expiracao[expirar]`) |
| **o que o sistema não faz** | não aprova sozinho, não escala para outra pessoa, não notifica. O silêncio nunca autoriza a compra (`POL-V2 §4`) |

**Limitação declarada:** não há agendador. Uma pendência vencida continua com
status `pendente` no banco até alguém listar ou retomar. Ninguém consegue
aprová-la depois do prazo, mas também ninguém é avisado de que ela venceu. O
passo seguinte seria um job periódico chamando `servico.pendentes()`.

---

## 5. Aprovar duas vezes

Duas camadas, e a segunda não depende da primeira:

1. **No grafo.** Se a thread já não tem nó pendente (`estado.next` vazio),
   `retomar` **não executa nada**: devolve a `Saida` gravada no checkpoint e
   registra no log um evento `aprovacao_repetida`.
2. **No serviço.** `finalizar` procura uma solicitação existente para o
   `caso_id`, que tem índice `UNIQUE` em `solicitacoes`, e devolve
   `ja_existia: true` em vez de inserir. O protocolo da solicitação é
   `sha256(caso, produto, quantidade, fornecedor)`, uma chave **derivada do
   conteúdo**. Quatro chamadas concorrentes de `finalizar` para o mesmo caso
   criam **uma** linha e debitam o orçamento **uma** vez (teste
   `test_compra_automatica_e_replay_concorrente`).

A prova com o modelo real está em [`io.md`](io.md), exemplo 6. Ali a mesma
aprovação (`aprovar`, quantidade 55) chega duas vezes, a segunda devolve a
saída da primeira, e o banco mostra uma única solicitação. O teste
`test_pausa_reinicio_edicao_e_aprovacao_duplicada` cobre o caso mais traiçoeiro:
uma segunda aprovação com **outra** quantidade (60) também não cria nada, e o
saldo fica em R$ 182,50, debitado uma única vez.
