# Projeto: Gestão de Estoque de um Supermarket

## Integrantes do grupo:
* Giovanna Paiva Alves
* Matheus Sanchez Duda
* Phelipe Pereira de Souza

---

## 1. O tema
Gestão de Estoque de um Supermarket

---

## 2. O detalhamento do tema

### Contexto:
O sistema atua como um assistente inteligente integrado à rotina operacional de um supermercado de pequeno ou médio porte, centralizando o controle físico e financeiro do inventário para otimizar o capital de giro e evitar rupturas de gôndola.

### Usuário:
Gerente de estoque ou operador logístico do supermercado.

### Interação:
* Controla a quantidade de cada produto que tem no estoque
* Controla a quantidade de produtos que sai 
* Controla a quantidade de produtos que entra 
* Controla a quantidade em real (R$) de produtos que sai
* Tem um budget máximo mensal
* Realiza uma solicitação de produtos por e-mail ao fornecedor
* Informa funcionários internos sobre a data de entrega da mercadoria solicitada

### Workflow do agente:
1. **Monitoramento Contínuo:** O agente acompanha em tempo real as entradas (recebimento de mercadorias) e saídas (vendas e perdas) de produtos, atualizando automaticamente o saldo físico no estoque.
2. **Validação Financeira:** A cada movimentação de saída, o sistema calcula o impacto financeiro em reais (R$) e verifica se os custos acumulados no período estão dentro do *budget* máximo mensal estabelecido.
3. **Alerta de Reposição:** Quando o estoque de um item atinge o ponto mínimo de segurança, o agente identifica a necessidade de compra e calcula a quantidade sugerida com base na demanda histórica.
4. **Geração de Pedido:** O usuário revisa a sugestão e o agente redige automaticamente uma solicitação de produtos estruturada por e-mail para o fornecedor correspondente.
5. **Agendamento e Notificação:** Após a confirmação do fornecedor, o agente registra a data prevista de entrega e dispara notificações automáticas para a equipe de funcionários internos, preparando-os para o recebimento e conferência da carga.

### Justificativa de negócio:
A implementação deste agente de IA traz ganho operacional e financeiro direto ao supermercado por meio da redução de perdas por excesso de estoque ou vencimento de produtos e da eliminação de rupturas (falta de mercadoria na gôndola). Ao automatizar o controle do *budget* mensal, o envio de pedidos e a comunicação interna sobre entregas, o sistema otimiza o tempo da equipe de gestão, melhora o fluxo de caixa com compras mais precisas e assertivas, e agiliza a logística de recebimento no estabelecimento.