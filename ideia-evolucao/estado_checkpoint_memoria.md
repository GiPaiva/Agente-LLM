# 1. Estado do Agente

| Campo | Descrição | Escopo |
|---|---|---|
| `objetivo`, `rota`, `produto` | Identifica o que está sendo processado | Execução atual |
| `estoque_atual`, `estoque_minimo`, `giro_medio` | Dados coletados do estoque | Execução atual |
| `quantidade_recomendada`, `fornecedor_selecionado` | Resultado da etapa de Decisão | Execução atual |
| `custo_estimado`, `impostos_estimados`, `margem_estimada`, `orcamento_disponivel` | Dados usados na Validação | Execução atual |
| `tarefas_criadas`, `falhas`, `acoes_executadas` | Histórico da execução em andamento | Execução atual |

# 2. Checkpoint

| Quando salvar | O que é salvo | Motivo |
|---|---|---|
| Antes de aguardar aprovação do gerente | Estado completo + `solicitacao_id` | Compra acima do limite automático (R$ 500) |
| Antes do envio ao fornecedor | Estado + ação pendente | Ação externa, exige confirmação humana |
| Ao atingir o limite de passos/sub-tarefas do agente (8/5) | Estado parcial + motivo da interrupção | Evita loop e permite revisão |
| A cada rodada do Avaliador (máx. 3) | Estado + histórico de rodadas | Rastreabilidade da validação |

# 3. Memória

| Tipo | O que armazena | Exemplo no projeto | Ferramentas relacionadas |
|---|---|---|---|
| **Semântica** | Fatos estáveis do domínio | Cadastro de produtos, fornecedores, preços, impostos, estoque mín/máx | `consultar_estoque`, `consultar_fornecedores` |
| **Episódica** | Eventos e interações passadas | Histórico de vendas, pedidos já feitos e aprovados | `consultar_vendas` |
| **Procedural** | Regras de como agir | Limite de R$ 500, exigência de aprovação humana, fluxo Router→Agente→Avaliador | Definidas no *system prompt* |
| **De trabalho** | Estado da tarefa atual | O `state` estruturado (Tabela 1) | Passa entre todas as etapas do fluxo |
