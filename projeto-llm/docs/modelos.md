# A análise de modelos — item 3 da entrega

> O objetivo é **justificar uma escolha**, não catalogar o mercado.
>
> Tudo o que está aqui foi **executado**. Os três candidatos rodaram os cinco
> casos do nosso domínio, com o mesmo prompt, pelo `src/benchmark.py`. Os
> resultados brutos estão em `logs/benchmark/`. Onde um número **não** foi
> medido por nós — preço de tabela —, está dito.

---

## 3.1 Os candidatos

Três candidatos em pontos diferentes do espaço que importa para este case: um
modelo pequeno **rodando local**, um hospedado de porte médio e um hospedado
grande — para saber o que se ganharia saindo de casa e pagando mais.

### Os eixos, e por que estes

| Eixo | Por que importa **neste** case |
|---|---|
| **Tool calling e saída estruturada** | pré-requisito. Sem isso não há agente — são 4 ferramentas e o laço inteiro depende delas |
| **Onde roda / política de dados** | o sistema vê preço de compra, orçamento e volume de venda. Não é dado pessoal (case §9), mas é informação que uma loja real não manda para fora sem pensar |
| **Custo por execução** | uma loja de pequeno porte é o comprador. Um custo por consulta que não arredonda para zero mata o case |
| **Latência** | há um operador esperando na tela, no meio do turno |
| **Consistência entre execuções** | o caso de divergência é julgamento, e julgamento instável é pior que julgamento ruim: não dá para confiar nem para corrigir |

E os que **não** priorizamos, ditos para não parecer omissão:

- **Janela de contexto** — a trajetória mais longa medida usa ~8.600 tokens. Os
  três candidatos têm folga de sobra; o eixo não separa ninguém aqui.
- **Multimídia** — o case é texto. Não pede.
- **Raciocínio profundo** — a tarefa é escolher ferramenta e julgar uma frase
  contra um número, não encadear inferência matemática.

### A comparação

| Eixo | `google/gemma-4-e4b` (local) | `qwen/qwen3.8-27b` (Groq) | `openai/gpt-oss-120b` (Groq) |
|---|---|---|---|
| Tool calling / saída estruturada | Sim — medido, 10/10 | Sim — medido, 10/10 | Sim — medido, 10/10 |
| Onde roda | **máquina do grupo**, exposta por túnel Cloudflare | nuvem (Groq) | nuvem (Groq) |
| Política de dados | **nada sai da máquina** | os dados de estoque vão para um terceiro | idem |
| Custo por token | **zero** — o custo é a máquina | por token, tabela do provedor | por token, mais caro |
| Latência média medida | 21,2 s | 30,5 s* | **7,5 s** |
| Tokens médios por execução | 4.503 | 4.377 | **3.750** |
| Consistência (conjunto de 20 × 3) | **95%** — ver §3.3 | não medido no conjunto completo | não medido no conjunto completo |
| Depende de cota externa | não | **sim** — ver a nota do §3.3 | sim |

\* a latência do `qwen` inclui uma repetição por falha de rede que o próprio
laço absorveu; o número real sem o incidente fica abaixo disso. Está aqui com o
incidente porque foi o que medimos.

---

## 3.2 A conta

### O que medimos

Estes números são **nossos**, tirados de `logs/`:

| Caso | Chamadas ao modelo | Tokens (entrada + saída) |
|---|---:|---:|
| 1 — simples (o mais caro: consulta, calcula e registra) | 4 | ~8.600 |
| 2 — divergência | 3 | ~5.600 |
| 3 — inexistente (duas buscas) | 3 | ~2.900 |
| 4 — não comprar | 2 | ~2.650 |
| 5 — ambiguidade | 2 | ~2.780 |
| **média por execução** | **~3** | **~4.500** |

> **Nota de método, e ela importa.** O esboço estimou 770 tokens de entrada por
> execução. A primeira medição real deu **9.623** — errado por ~12×. Parte da
> diferença era estimativa ruim; parte era **bug**: a busca quebrada fazia o
> agente gastar um passo inteiro num "produto não encontrado" falso. Com a
> busca consertada, a execução típica caiu para ~4.500 tokens. **Medir a conta
> encontrou um defeito que a leitura do código não tinha encontrado.**

### O custo, para o modelo escolhido

```
google/gemma-4-e4b, rodando local:

  custo por token ............................ R$ 0,00
  custo por execução ......................... R$ 0,00
  custo por 100 execuções .................... R$ 0,00
  custo do semestre (3 entregas) ............. R$ 0,00

  o custo real é a máquina do grupo, que já existe, e a eletricidade.
```

### O custo se fôssemos para a nuvem

Com ~4.500 tokens por execução (≈3.900 de entrada, ≈600 de saída), e usando os
**preços publicados pelos provedores** — este é o único número desta página que
**não** conferimos ao vivo, e preço de API muda com frequência:

```
por execução  = 3.900/1.000.000 × preço_entrada
              +   600/1.000.000 × preço_saida
```

Para um modelo da faixa de ~US$ 0,15/M entrada e ~US$ 0,60/M saída, isso dá
**~US$ 0,001 por execução** — cerca de **US$ 0,10 por 100 execuções**.

**A conclusão que a conta permite:** mesmo pagando, o custo por consulta
arredonda para zero frente ao salário do operador. **Custo não é o que decide
esta escolha** — e é honesto dizer isso em vez de fingir que R$ 0,00 é uma
vantagem decisiva. O que decide está no §3.4.

---

## 3.3 A verificação mínima — os cinco casos, rodados de verdade

O enunciado é explícito: *"não confiem em leaderboard. Rodem uma verificação
própria, mesmo pequena: cinco casos do seu domínio nos três candidatos, com o
mesmo prompt."*

```bash
python src/benchmark.py --n 2
```

Cinco casos — um de cada família do conjunto rotulado —, **duas execuções
cada**, **o mesmo prompt** (`sistema-v3`) e os mesmos parâmetros nos três.

| Caso | `gemma-4-e4b` (local) | `qwen3.8-27b` (Groq) | `gpt-oss-120b` (Groq) |
|---|---|---|---|
| **1 — simples** | 2/2 · *"Sim, precisamos pedir mais. O estoque está baixo (12 unidades, mínimo 30). Acabei de criar a solicitação…"* | 2/2 · *"Sim, precisa pedir. Estoque: 12 (mínimo 30), sobra ~1,5 dia de venda. Solicitação registrada…"* | 2/2 · *"O arroz 5 kg está abaixo do mínimo: há 12 unidades, mínimo 30. Precisa repor. Solicitei 50 unid…"* |
| **2 — divergência** | 2/2 · *"O sistema mostra o contrário do que você viu: há 85 unidades de Refrigerante 2L, acima do mínimo…"* | 2/2 · *"O sistema mostra o contrário do que você viu: há 85 unidades de Refrigerante 2L…"* | 2/2 · *"O sistema mostra o contrário do que você viu: há **85** unidades de **Refrigerante 2 L**…"* |
| **3 — inexistente** | 2/2 · *"Desculpe, mas 'iogurte de morango' não está no nosso cadastro atual. Os produtos que temos…"* | 2/2 · *"Iogurte de morango não está no cadastro. Os produtos que temos são…"* | 2/2 · *"O produto **iogurte de morango** não está cadastrado. No sistema constam apenas…"* |
| **4 — não comprar** | 2/2 · *"O estoque de Feijão 1kg está em 40 unidades, e o mínimo é 25."* | 2/2 · *"Feijão 1kg: 40 unidades em estoque (mínimo 25). Está acima do mínimo, sem necessidade…"* | 2/2 · *"O estoque de Feijão 1kg está com 40 unidades, acima do mínimo de 25. Não há necessidade…"* |
| **5 — ambiguidade** | 2/2 · *"Temos dois tipos de açúcar: Açúcar Refinado 1kg e Açúcar Refinado 5kg. Qual você gostaria…"* | 2/2 · *"Tem dois no cadastro: Açúcar Refinado 1kg e Açúcar Refinado 5kg. Qual dos dois você quer?"* | 2/2 · *"Você tem dois itens cadastrados com 'açúcar'. Qual deles você quer consultar?"* |
| **total** | **10/10** | **10/10** | **10/10** |
| latência média | 21,2 s | 30,5 s | **7,5 s** |
| tokens/execução | 4.503 | 4.377 | **3.750** |

**Os três passam.** Nos cinco casos canônicos, o modelo local de 4B faz o mesmo
que o hospedado de 120B. Esse é o resultado, e ele é o argumento central da
escolha.

### Dois achados que só apareceram porque rodamos

**1. O `qwen` primeiro marcou 2/10 — e não era o modelo.** Era a cota: a conta
gratuita da Groq recusava a requisição **antes de processá-la**, com
`429 ... output tokens per minute (OTPM): Limit 1000, Requested 1015`. O
provedor estima o tamanho da saída pelo `max_tokens` declarado, e nós não
declarávamos nenhum. Declarar `max_tokens=800` levou o `qwen` de **2/10 para
10/10**.

> Se tivéssemos aceitado o primeiro número, este documento afirmaria que um
> modelo de 27B não dá conta de uma tarefa que ele resolve perfeitamente. É o
> tipo de conclusão errada que um benchmark mal lido produz — e a razão pela
> qual o enunciado manda **olhar a saída**, não só o placar.

**2. O túnel do modelo local caiu no meio de uma suíte.** Um `530` do
Cloudflare derrubou 13 dos 20 casos de uma medição de 28 minutos. O laço
classificou certo (`erro_fatal`, com a causa no log), mas perdeu a medição.
Daí veio a repetição **só para falha de transporte** em `src/agente.py` — 4xx
continua abortando na primeira, que é a lição da aula 05.

### E o conjunto completo, no modelo escolhido

Os cinco casos acima são a verificação **mínima** que o item 3.3 pede. O
conjunto rotulado inteiro — 20 casos × 3 execuções — roda só no modelo
escolhido:

```
PLACAR: 57/60 = 95%   (limiar declarado: 85%)

  1_simples        12/12
  2_divergencia     9/12
  3_inexistente    12/12
  4_nao_comprar    12/12
  5_ambiguidade    12/12

regra assimétrica (nenhuma compra indevida): OK
VEREDITO: APROVADO
```

**A falha que sobra, dita por inteiro.** O caso `2d` — *"O refrigerante está
abaixo do mínimo, né? Pode pedir."* — falha nas 3 execuções. A resposta do
modelo é *"Não, o refrigerante está acima do mínimo. Temos 85 unidades e o
mínimo é 20."*

Essa resposta **contradiz** o operador, mas não usa a forma que o contrato de
saída exige (nomear a divergência explicitamente). Nós **poderíamos** ter
afrouxado o verificador para aceitá-la — e o placar iria a 100%. Não
afrouxamos: mexer no critério depois de ver o resultado é exatamente o que a
aula 03 chama de teste que não testa nada. O caso fica como falha declarada.

---

## 3.4 A decisão

**Modelo escolhido: `google/gemma-4-e4b`, rodando local.**

Os três acertam 10/10 nos cinco casos. Quando a capacidade empata, decide o que
sobra:

1. **Política de dados.** O sistema vê preço de compra, margem e orçamento de
   uma loja. Rodando local, **nada sai da máquina**. Foi o critério de maior
   peso, e é o único em que a diferença entre os candidatos é categórica em vez
   de gradual.
2. **Custo e dependência.** Zero por token e **sem cota externa**. O incidente
   do `qwen` mostrou o que uma cota de terceiro faz com o trabalho: 8 dos 10
   casos reprovados por um limite administrativo, não por qualidade.
3. **Latência aceitável.** 21 s é mais lento que os 7,5 s do `gpt-oss-120b`, e
   isso é uma perda real. Mas a alternativa de hoje leva 3 a 6 **minutos**
   (case §5) — 21 segundos resolve o problema do operador.

**O que estamos abrindo mão, dito:** velocidade (3× mais lento que o melhor) e
um pouco de consistência — o `2d` falha no local, e o conjunto completo não foi
medido nos hospedados para saber se eles acertariam.

### Em que condições mudaríamos de ideia

Escrito **antes** de precisar, para que a decisão seja verificável e não um
chute retroativo:

| Gatilho | O que faríamos |
|---|---|
| A família 2 (divergência) cair **abaixo de 8/12** numa medição do conjunto completo | rodar o conjunto inteiro nos três candidatos e trocar pelo melhor nessa família — é o julgamento que justifica haver um agente |
| A latência local passar de **60 s** por consulta | migrar para `gpt-oss-120b`: 7,5 s medidos, e a diferença deixa de ser aceitável |
| O case passar a tocar **dado pessoal** (cliente fidelizado) | reforça o local. A política de dados vira impeditivo, não preferência |
| A máquina do grupo deixar de estar disponível | `gpt-oss-120b`, assumindo o custo por token e a cota — e declarando que dado de negócio passou a sair da máquina |
| O custo do hospedado ficar acima de **R$ 0,05 por execução** | fica local mesmo com latência pior |

**A troca é barata de propósito:** três variáveis de ambiente
(`LLM_BASE_URL`, `LLM_MODELO`, `OPENAI_API_KEY`) e nenhuma linha de código —
e `src/benchmark.py` remede os três em minutos.

---

## Como reproduzir tudo isto

```bash
python src/benchmark.py --n 2     # a tabela do §3.3 (precisa das BENCH_* no .env)
python src/avaliar.py --n 3       # o placar do conjunto completo
```

Saídas brutas em `logs/benchmark/` e `logs/avaliacao/`. Toda execução carrega o
carimbo `prompt × modelo × parâmetros`, então dá para saber qual combinação
produziu qual número.
