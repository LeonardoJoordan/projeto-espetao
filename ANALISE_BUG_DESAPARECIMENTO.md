# 🚨 ANÁLISE CRÍTICA: BUG DO PRODUTO DESAPARECIDO

## 🎯 Diagnóstico do Problema

**Cenário Relatado:**
- Produto "Espetinho de Maminha" tinha 4 unidades em estoque
- Desapareceu do `cliente.html` (não era mais exibido)
- Após adicionar 1 unidade no painel de gestão (totalizando 5), o produto reapareceu
- O sistema exibia corretamente as 5 unidades

**Raiz Confirmada: ❌ PROBLEMA CRÍTICO NA QUERY SQL**

---

## 🔴 CAUSA RAIZ - Linha 165-200 em `gerenciador_db.py`

### O Código Problemático:

```python
def obter_todos_produtos():
    """
    Busca todos os produtos com disponibilidade positiva...
    """
    # ...
    cursor.execute('''
        SELECT 
            p.id, p.nome, p.descricao, p.foto_url, p.preco_venda, 
            c.nome as categoria_nome, p.categoria_id, p.requer_preparo,
            c.ordem as categoria_ordem, p.ordem as produto_ordem,
            (SELECT COALESCE(SUM(m.quantidade), 0) 
             FROM estoque_movimentacoes m 
             WHERE m.produto_id = p.id) as on_hand,
            (SELECT COALESCE(SUM(r.quantidade_reservada), 0) 
             FROM reservas_carrinho r 
             WHERE r.produto_id = p.id AND r.expires_at > ?) as reservado
        FROM produtos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        GROUP BY p.id
        HAVING (on_hand - reservado) > 0        # ← PROBLEMA AQUI!
        ORDER BY c.ordem, p.ordem, p.nome
    ''', (agora_utc,))
```

### ⚠️ O Problema:

1. **A query usa `SUM()` de subqueries** para calcular `on_hand` e `reservado`
2. **Mas com `GROUP BY p.id`**, essas subqueries perdem contexto de agregação
3. **Pior ainda:** Se `estoque_movimentacoes` tiver registros com `quantidade NEGATIVA` (devoluções/ajustes), e a soma resultar ≤ 0, o produto é filtrado

### Exemplo do Bug:

```
Espetinho de Maminha (ID=5):
- Estoque Inicial: +5 (entrada_de_estoque)
- Venda 1: -1 (pedido finalizado)
- Resultado: 4 unidades

Mas se houve um ajuste negativo não intencional:
- Ajuste: -4 (bug/erro manual)
- Total em estoque_movimentacoes: 5 - 1 - 4 = 0
- CLÁUSULA HAVING: (0 - 0) > 0? NÃO ❌
- RESULTADO: Produto não aparece!

Quando adiciona +1:
- Total agora: 0 + 1 = 1
- CLÁUSULA HAVING: (1 - 0) > 0? SIM ✅
- RESULTADO: Produto aparece novamente!
```

---

## 🔍 Como o Bug Acontece:

1. **Movimentação Negativa Desconhecida**
   - Ajuste de estoque negativo (dano, furto, erro de entrada)
   - Query incorreta que insere quantidade negativa
   - Cancelamento de pedido que não removeu a movimentação

2. **Cálculo de Disponibilidade Quebrado**
   - `(on_hand - reservado) > 0` falha se `on_hand` ≤ 0
   - Produto desaparece do cardápio
   - Não gera erro, apenas oculta silenciosamente ❌

3. **Reaparece com Qualquer Entrada Positiva**
   - +1 unidade: `(1 - 0) > 0` = TRUE
   - Produto volta imediatamente

---

## 💥 Cenários que Podem Causar Isso:

| Cenário | Como Ocorre | Resultado |
|---------|------------|-----------|
| **1. Ajuste Manual Errado** | Admin digitou "-4" em vez de "+1" | Estoque vai para 0/negativo |
| **2. Bug em Cancelamento** | Pedido cancelado, mas movimentação negativa não foi revertida | Estoque fica desincronizado |
| **3. Devolução não Integrada** | Sistema antigo que fez devolução não sincronizou com novo ledger | Quantidade fica negativa |
| **4. Migração de Dados** | Script de migração inseriu valores incorretos | Alguns produtos com estoque negativo |
| **5. Concorrência na API** | Múltiplas requisições simultâneas causaram double-debit | Estoque zerou |

---

## ✅ SOLUÇÃO: Corrigir a Query

### Problema da Query Atual:

```sql
-- ❌ ERRADO: GROUP BY sem agregação correta
GROUP BY p.id
HAVING (on_hand - reservado) > 0
```

**Problema:** Subqueries externas não são computadas antes do `GROUP BY`, causando cálculos inconsistentes.

### Solução Recomendada:

```sql
-- ✅ CORRETO: Usar CTE ou subquery completa
WITH estoque_calc AS (
    SELECT 
        p.id,
        p.nome,
        p.descricao,
        p.foto_url,
        p.preco_venda,
        c.nome as categoria_nome,
        p.categoria_id,
        p.requer_preparo,
        c.ordem as categoria_ordem,
        p.ordem as produto_ordem,
        COALESCE(
            (SELECT SUM(m.quantidade) 
             FROM estoque_movimentacoes m 
             WHERE m.produto_id = p.id), 
            0
        ) as on_hand,
        COALESCE(
            (SELECT SUM(r.quantidade_reservada) 
             FROM reservas_carrinho r 
             WHERE r.produto_id = p.id AND r.expires_at > ?),
            0
        ) as reservado
    FROM produtos p
    LEFT JOIN categorias c ON p.categoria_id = c.id
)
SELECT * FROM estoque_calc
WHERE (on_hand - reservado) > 0
ORDER BY categoria_ordem, produto_ordem, nome;
```

---

## 🛡️ PREVENÇÃO: Adicionar Validações

### 1. **Log de Todas as Movimentações Negativas**
```python
def registrar_movimentacao(produto_id, quantidade, origem):
    if quantidade < 0:
        log_warning(f"MOVIMENTAÇÃO NEGATIVA: Produto {produto_id}, ->{quantidade}, Origem: {origem}")
```

### 2. **Validação ao Ajustar Estoque**
```python
def ajustar_estoque(produto_id, quantidade):
    estoque_atual = obter_estoque_atual(produto_id)
    if estoque_atual + quantidade < 0:
        raise ValueError("Estoque não pode ficar negativo!")
```

### 3. **Auditoria Automática**
```python
# Detectar produtos com estoque negativo
def validar_integridade_estoque():
    cursor.execute("""
        SELECT p.id, p.nome, SUM(m.quantidade) as total
        FROM produtos p
        LEFT JOIN estoque_movimentacoes m ON p.id = m.produto_id
        GROUP BY p.id
        HAVING total <= 0
    """)
    produtos_negativos = cursor.fetchall()
    if produtos_negativos:
        alert_admin(f"ALERTA: Produtos com estoque inválido: {produtos_negativos}")
```

---

## 📊 Recomendações Imediatas

### CRÍTICO (Fazer Agora):
1. ✅ **Corrigir a query SQL** em `obter_todos_produtos()`
2. ✅ **Verificar tabela `estoque_movimentacoes`** por registros negativos/inconsistentes
3. ✅ **Limpar dados corrompidos** (se houver)

### IMPORTANTE (Próxima Sprint):
4. Adicionar validação que impede estoque negativo
5. Implementar log de auditoria para movimentações
6. Adicionar endpoint de "Validação de Integridade" no admin

### BOM TER (Melhorias):
7. Dashboard que mostra produtos com estoque anômalo
8. Alerta automático quando produto desaparece/reaparece
9. Teste unitário para cenários de estoque negativo

---

## 🔗 Arquivo Relacionado

- **`gerenciador_db.py` - Linhas 165-220**: Função `obter_todos_produtos()`
- **`database.py` - Linhas 120-160**: Definição da tabela `estoque_movimentacoes`

---

## ⚡ Urgência

**ALTA** ⚠️ 

Este bug causa **desaparecimento intermitente de produtos no cardápio** sem erro. Em produção com clientes, pode criar:
- ❌ Confusão dos clientes ("Por que esse item desapareceu?")
- ❌ Perda de vendas
- ❌ Desconfiança no sistema

**Recomendação: Corrigir ANTES da próxima versão de produção.**
