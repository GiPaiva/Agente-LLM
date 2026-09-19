# Base de conhecimento v1: Gestão de Estoque de Supermercado

---

## 1. Informação especializada que o agente precisa

| Informação | Motivo | Por que vem de fora |
|---|---|---|
| Política de compras (limite de R$ 500 sem aprovação, orçamento mensal, quem aprova) | Privada | Regra interna da empresa. |
| Contratos com fornecedores (pedido mínimo, prazo, frete, desconto por volume, devolução) | Privada e recente | Contrato é confidencial e muda a cada renegociação. |
| Procedimentos de recebimento de carga e tratamento de perdas/vencimento | Privada | É o processo daquele mercado, não o genérico. |
| Estoque, vendas, preços e orçamento disponível | Privada e recente | Muda a cada venda e vem do sistema (ver seção 3). |
| Alíquotas de impostos por produto | Específica | O modelo erra detalhes tributários. Vem do cadastro do produto. |

**O que o modelo já sabe e não será indexado:** conceitos de gestão de estoque (ponto de reposição, estoque de segurança, curva ABC, giro) e como redigir um e-mail formal a fornecedor.

---

## 2. Onde os dados estão

| Fonte | Onde vive | Formato | Dono / mudança | Acesso |
|---|---|---|---|---|
| Estoque, vendas, movimentações | Banco do sistema de estoque | Registros SQL | Sistema, a cada venda | Sim |
| Fornecedores, preços, prazos, impostos | Cadastro no banco | Planilha / tabela | Comprador, diário, semanal ou mensal | Sim |
| Orçamento mensal | Tabela de configuração | Registro | Gerente, mensal | Sim |
| Contratos de fornecedores | Pasta compartilhada | PDF / Word | Comprador, a cada renegociação | Sim |
| Política de compras | Pasta compartilhada | Word / PDF | Gerente, raramente | Sim |
| Procedimentos (recebimento, perdas) | Pasta compartilhada | Word / PDF | Gerente e logística, raramente | Sim |

---

## 3. O que vai para o índice

**Entra (busca semântica):**

| Documento | Volume |
|---|---|
| Contratos de fornecedores | 5 arquivos, ~8 páginas cada |
| Política de compras | 1 arquivo, ~5 páginas |
| Procedimentos operacionais | 3 arquivos, ~4 páginas cada |
| Total | ~57 páginas, de 150 a 300 chunks |

**Fica de fora, resolvido por consulta estruturada:**

| Pergunta | Consulta | Ferramenta |
|---|---|---|
| Quanto temos de arroz? | Filtro por produto | consultar_estoque |
| Quanto vendemos por dia? | Agregação por data | consultar_vendas |
| Preço e prazo do Fornecedor A? | Cadastro | consultar_fornecedores |
| Quanto sobra de orçamento? | Soma contra o limite | consultar_orcamento |
| Alíquota do produto? | Campo do cadastro | calcular_custo |

Também ficam de fora a legislação tributária completa, o histórico de e-mails e o conhecimento genérico de gestão.

**Ferramenta:** com poucas centenas de chunks não é preciso banco vetorial. Os embeddings ficam em memória e a busca é por cosseno, com filtro de metadado antes. Se passar de alguns milhares de chunks, reavalia.

**Acréscimo à arquitetura v1:** uma ferramenta de leitura, buscar_documentos, que recebe a consulta e filtros de metadado, usada na etapa de decisão quando o agente precisa de uma regra escrita, por exemplo "o contrato permite pedido abaixo do mínimo?".

---

## 4. Estratégia de chunking

Os três tipos de documento têm estrutura, então o corte segue a unidade natural de cada um.

| Documento | Corte | Motivo | Metadados |
|---|---|---|---|
| Contratos | Cláusula numerada | Cada cláusula trata de um assunto (prazo, frete, devolução). | tipo, fornecedor_id, clausula, vigencia_fim |
| Política de compras | Seção ou item numerado | Cada regra é autocontida. | tipo, secao, versao, data_vigencia |
| Procedimentos | Procedimento inteiro (título e passos) | Um passo isolado não faz sentido sem os demais. | tipo, processo, setor |

Regras comuns:

1. Todo chunk herda o cabeçalho, por exemplo "Contrato Fornecedor A > Cláusula 5 - Prazo de entrega", para fazer sentido sozinho.
2. Cláusula ou seção acima de ~1.500 caracteres é dividida por parágrafo, repetindo o cabeçalho.
3. Documento sem estrutura (e-mail, ata) é cortado a cada ~800 caracteres, com ~100 de sobreposição.

O agente já conhece o fornecedor selecionado pelo estado, então a busca combina filtro e similaridade. Por exemplo, para "pedido mínimo e frete" do Fornecedor A, o filtro restringe aos contratos desse fornecedor e a similaridade escolhe a cláusula dentro deles.
