<!-- {"id":"POL-V2","status":"vigente","vigencia":"2026-01-01","dono":"gerente simulado","versao":2} -->
# Política simulada de compras
## 1 Limite e aprovação
Solicitações de compra até R$ 500 podem ser criadas automaticamente, se houver necessidade de reposição e saldo. Acima de R$ 500, o gerente precisa aprovar antes de registrar a compra. O sistema não envia pedidos a fornecedores.
## 2 Orçamento insuficiente
O orçamento disponível é um limite obrigatório. Mesmo o gerente não pode autorizar uma compra que exceda o saldo. Exceção: ele pode reduzir a quantidade, respeitando o pedido mínimo do fornecedor e o saldo, ou rejeitar a solicitação.
## 3 Quantidade recomendada
Só repor quando o estoque atual estiver abaixo do mínimo. A recomendação é duas vezes o estoque mínimo menos o estoque atual, elevada ao pedido mínimo do fornecedor se necessário. Uma consulta informativa não cria uma compra.
## 4 Prazo da aprovação
A aprovação pendente expira após 24 horas. O silêncio nunca autoriza a compra. O prazo é verificado quando a pendência é listada ou retomada.
