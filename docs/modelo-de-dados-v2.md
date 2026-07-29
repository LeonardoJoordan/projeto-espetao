# Modelo de dados v2

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
- O histórico legado de pedidos não é importado. A migração mantém catálogo,
  configurações, locais e o saldo consolidado atual de cada produto ativo.

## Fontes únicas de verdade

| Informação | Fonte |
| --- | --- |
| Saldo de estoque | Soma de `estoque_movimentacoes.quantidade` |
| Valor e quantidade vendidos | Snapshot em `pedido_itens` |
| Receita e estornos | Eventos imutáveis em `pagamentos` |
| Taxa de pagamento | Snapshot no evento de pagamento/estorno |
| Estado operacional | `pedidos.status` e datas de transição |

Não devem ser recriadas colunas de saldo ou custo atual em `produtos`. Esses
valores são derivados do livro de movimentações. Também não se deve usar JSON
como fonte financeira: `itens_json` existe apenas nas respostas de
compatibilidade da aplicação.

## Fluxos transacionais

### Venda

1. O servidor relê nome, preço e custo dos produtos.
2. Uma transação valida o saldo global descontando reservas de outros
   carrinhos.
3. Pedido, itens normalizados e saídas de estoque são gravados juntos.
4. A reserva do carrinho é removida na mesma transação.

Uma falha em qualquer etapa desfaz toda a operação.

### Pagamento

1. Apenas um pedido aguardando pagamento pode ser confirmado.
2. A configuração da taxa é copiada para o evento imutável.
3. O relatório passa a reconhecer a receita na data desse evento.

### Cancelamento

1. A operação é idempotente.
2. O estoque é devolvido integralmente.
3. Se houve pagamento, é criado um evento de estorno integral com a mesma taxa
   registrada no pagamento.

## Métricas do fechamento

```text
faturamento líquido = pagamentos - estornos
CMV líquido          = CMV das vendas - CMV dos estornos
lucro bruto          = faturamento líquido - CMV líquido
resultado operacional = lucro bruto - taxas líquidas - perdas/ajustes
```

Todas as visões do fechamento, comparativos, gráficos e impressão usam o mesmo
cálculo em `analytics.py`. Ajustes negativos de inventário são tratados como
perda; ajustes positivos corrigem o saldo, mas não são reconhecidos como
receita.

## Leituras para tomada de decisão

O painel deriva informações gerenciais sem alterar as fontes contábeis:

- margem bruta e operacional, taxa de estorno, participação de CMV e taxas;
- matriz relativa de contribuição e margem dos produtos;
- concentração da receita nos três principais produtos;
- desempenho por categoria, horário e forma de pagamento;
- ritmo de saída e cobertura estimada do estoque global;
- alertas determinísticos com o próximo ponto a investigar.

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

Antes de substituir o banco, o script cria um backup
`espetao.db.legacy-v1.bak`. A migração pode ser auditada com:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

Os testes usam bancos temporários e cobrem integridade referencial, preço
recalculado no servidor, atomicidade de estoque, reconhecimento no pagamento,
snapshot de taxa, estorno integral, perdas e limites do dia operacional.
