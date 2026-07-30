# Modelo de dados v5

Este documento registra as regras que mantêm o banco e os relatórios
consistentes. Alterações futuras devem preservar estas invariantes.

## Decisões de negócio

- A receita nasce na confirmação do pagamento, não na criação ou entrega do
  pedido.
- O estoque é global. O local identifica onde o pedido foi feito, mas não
  divide o saldo dos produtos.
- O cancelamento de um pedido pago representa estorno integral: receita, taxa
  de pagamento, CMV e itens vendidos são revertidos.
- O dia operacional vai das 05:00 de uma data até as 05:00 da data seguinte,
  no fuso `America/Sao_Paulo`.
- Cada entrada de estoque cria um lote e as saídas usam PEPS/FIFO.
- A migração v2 → v5 preserva os cadastros e pedidos existentes. As entradas
  anteriores são consolidadas em um lote de abertura por produto.
- A zeragem operacional encerra o saldo físico sem representar receita, perda
  ou movimentação gerencial. O registro técnico permanece disponível para
  auditoria com `impacta_relatorio = 0`.

## Fontes únicas de verdade

| Informação | Fonte |
| --- | --- |
| Saldo de estoque | Lotes de `estoque_lotes` menos suas movimentações |
| Custo da venda | `pedido_itens.custo_total_centavos` e baixas por lote |
| Valor e quantidade vendidos | Snapshot em `pedido_itens` |
| Receita e estornos | Eventos imutáveis em `pagamentos` |
| Taxa de pagamento | Snapshot no evento de pagamento/estorno |
| Estado operacional | `pedidos.status` e datas de transição |
| Visitas por ponto | `operacoes` e vínculo `pedidos.operacao_id` |
| Estoque levado e retornado | Fotografias em `operacao_estoque` |

Não devem ser recriadas colunas de saldo ou custo atual em `produtos`. Esses
valores são derivados dos lotes e suas movimentações. Também não se deve usar JSON
como fonte financeira: `itens_json` existe apenas nas respostas de
compatibilidade da aplicação.

## Fluxos transacionais

### Venda

1. O servidor relê nome e preço dos produtos.
2. Uma transação valida o saldo global descontando reservas de outros
   carrinhos.
3. Os lotes mais antigos são consumidos primeiro.
4. Cada parcela consumida fotografa lote, quantidade e custo unitário.
5. O item guarda o custo total exato, inclusive quando atravessa lotes.
6. Pedido, itens normalizados e saídas de estoque são gravados juntos.
7. A reserva do carrinho é removida na mesma transação.

Uma falha em qualquer etapa desfaz toda a operação.

### Pagamento

1. Apenas um pedido aguardando pagamento pode ser confirmado.
2. A configuração da taxa é copiada para o evento imutável.
3. O relatório passa a reconhecer a receita na data desse evento.

### Cancelamento

1. A operação é idempotente.
2. O estoque é devolvido aos mesmos lotes consumidos.
3. Se houve pagamento, é criado um evento de estorno integral com a mesma taxa
   registrada no pagamento.

## Métricas do fechamento

```text
faturamento líquido = pagamentos - estornos
CMV líquido          = CMV das vendas - CMV dos estornos
lucro bruto          = faturamento líquido - CMV líquido
resultado operacional = lucro bruto - taxas líquidas - perdas
```

Todas as visões do fechamento, comparativos, gráficos e impressão usam o mesmo
cálculo em `analytics.py`. Perdas consomem os lotes FIFO e reduzem o resultado.
Ajustes marcados com `impacta_relatorio = 0` apenas reconciliam o saldo
operacional e não entram nas métricas financeiras ou nas movimentações
gerenciais.

## Zeragem operacional

- A zeragem individual e a global consomem integralmente os saldos dos lotes
  mais antigos.
- Reservas temporárias dos produtos afetados são removidas na mesma transação.
- A zeragem global inclui produtos ativos e arquivados que ainda tenham saldo.
- A operação é idempotente: repetir uma zeragem sobre saldo zero não cria novas
  movimentações.
- Os movimentos técnicos usam `tipo = 'ajuste'` e
  `impacta_relatorio = 0`.
- Produtos, pedidos, pagamentos e custos já fotografados nas vendas não são
  alterados.

## Leituras para tomada de decisão

O painel deriva informações gerenciais sem alterar as fontes contábeis:

- margem bruta e operacional, taxa de estorno, participação de CMV e taxas;
- matriz relativa de contribuição e margem dos produtos;
- concentração da receita nos três principais produtos;
- desempenho por categoria, horário e forma de pagamento;
- ritmo de saída e cobertura estimada do estoque global;
- alertas determinísticos com o próximo ponto a investigar.
- análise individual e comparação de até três locais;
- médias por visita, itens de maior e menor saída e picos por hora;
- disponibilidade baseada no estoque fotografado em cada operação.

Ao iniciar o servidor, uma operação real é aberta para o local selecionado. O
estoque global é fotografado imediatamente antes da primeira venda, permitindo
que a carga seja preparada depois que o servidor já estiver acessível. Se não
houver venda, a fotografia inicial é feita no encerramento. Ao finalizar a
operação, o saldo de retorno também é fotografado.
Produtos que não estiveram disponíveis não participam da média nem da lista de
menor saída. Produtos disponíveis com venda zero participam normalmente.

O usuário pode analisar todo o histórico, as últimas N visitas ou um período.
O painel mostra fatos observados — médias, faixas, sobras e esgotamentos — sem
gerar recomendação automática de carga.

A visão geral aceita um dia ou um intervalo inclusivo de datas operacionais.
Para um único dia, o gráfico financeiro usa intervalos de 15 minutos; para
intervalos maiores, consolida os valores por dia operacional.

A cobertura de estoque é uma estimativa baseada no ritmo do período
selecionado. Ela orienta reposição, mas não representa previsão de demanda.
As classificações de produto comparam o mix vendido no próprio período e não
devem ser interpretadas como recomendação automática de exclusão.

## Migração e auditoria

Execute:

```bash
.venv/bin/python -B scripts/migrar_schema_v2.py espetao.db
```

Antes de alterar um banco v2, v3 ou v4, a aplicação cria um backup consistente
`espetao.db.pre-v3.bak`, `espetao.db.pre-v4.bak` ou
`espetao.db.pre-v5.bak`. A migração pode ser
auditada com:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

Os testes usam bancos temporários e cobrem integridade referencial, preço
recalculado no servidor, atomicidade de estoque, reconhecimento no pagamento,
snapshot de taxa, FIFO atravessando lotes, custo total exato, estorno por lote,
perdas FIFO, zeragem operacional neutra, liberação de reservas e limites do
dia operacional. Também cobrem visitas por local, fotografias do estoque,
médias condicionadas à disponibilidade e comparação entre pontos.
