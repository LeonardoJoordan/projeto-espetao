# 📋 GUIA: Como Usar o Script de Diagnóstico

## 🎯 Objetivo

O script `diagnostico_estoque.py` foi criado para **detectar e monitorar inconsistências de estoque** que poderiam causar o bug de desaparecimento de produtos.

## 📍 Localização

```
projeto_espetao/
└── scripts/
    └── diagnostico_estoque.py  ← Aqui!
```

## 🚀 Como Executar

### Pré-requisitos
- Python 3.7+
- SQLite3 (incluído no Python)
- Estar no diretório raiz do projeto

### Execução

**Via Terminal (PowerShell/CMD):**
```powershell
cd c:\Users\leotn\VSCode\projeto_espetao
python scripts/diagnostico_estoque.py
```

**Via Terminal (Linux/Mac):**
```bash
cd ~/projeto_espetao
python3 scripts/diagnostico_estoque.py
```

**Via VS Code:**
1. Abra o arquivo `scripts/diagnostico_estoque.py`
2. Clique no ▶️ (Run) no canto superior direito
3. Veja o output no terminal

## 📊 O que o Script Faz

### 1️⃣ Detecta Produtos com Estoque Negativo
```
1️⃣  PRODUTOS COM MOVIMENTAÇÕES NEGATIVAS:
⚠️  ENCONTRADOS 2 PRODUTOS COM ESTOQUE NEGATIVO:

  • ID 5: Espetinho de Maminha
    Total de Movimentações: -1
    
  • ID 12: Calabresa Premium
    Total de Movimentações: -3
```

**O que significa:** Há movimentações que deixaram o estoque negativo  
**Ação necessária:** Investigar origem (ajuste manual, bug, etc)

---

### 2️⃣ Encontra Produtos com Saldo Zero
```
2️⃣  PRODUTOS COM SALDO ZERO (Possível Bug):
⚠️  ENCONTRADOS 1 PRODUTOS COM SALDO ZERO:

  • ID 5: Espetinho de Maminha
    On Hand: 0, Reservado: 0
```

**O que significa:** Produto tem saldo exatamente zero (pode ter sido o bug)  
**Ação necessária:** Verificar se era intencional ou se houve movimentação negativa

---

### 3️⃣ Resume Movimentações por Tipo
```
3️⃣  RESUMO DE MOVIMENTAÇÕES POR ORIGEM:
  • entrada_estoque: 50 movimentações, Total: +245
  • venda_pedido: 120 movimentações, Total: -85
  • ajuste_manual: 5 movimentações, Total: -3
  • cancelamento_pedido: 2 movimentações, Total: +10
```

**O que significa:** Resumo de como o estoque foi movimentado  
**Use para:** Entender o fluxo geral de movimentações  
**Red Flag:** Se `ajuste_manual` tiver valores negativos grandes

---

### 4️⃣ Verifica Integridade de Referências
```
4️⃣  PRODUTOS SEM CATEGORIA:
✅ Todos os produtos têm categoria atribuída.
```

**O que significa:** Não há produtos órfãos ou sem categoria  
**Red Flag:** Se aparecer "ENCONTRADOS X PRODUTOS SEM CATEGORIA"

---

### 5️⃣ Estatísticas Gerais
```
5️⃣  ESTATÍSTICAS GERAIS:
  • Total de Produtos: 48
  • Total de Movimentações: 180
  • Reservas Ativas: 3
```

**O que significa:** Visão geral da saúde do banco  
**Use para:** Monitoramento rotineiro

---

## 🔍 Interpretando o Output

### ✅ Tudo OK (Esperado)
```
✅ Nenhum produto com estoque negativo encontrado.
✅ Nenhum produto com saldo zero encontrado.
✅ Todos os produtos têm categoria atribuída.
```

### ⚠️ Potencial Problema
```
⚠️  ENCONTRADOS 2 PRODUTOS COM ESTOQUE NEGATIVO:
```

→ **Ação:** Investigar cada produto listado

### 🚨 Crítico
```
⚠️  ENCONTRADOS 10+ PRODUTOS COM SALDO ZERO:
```

→ **Ação:** Possível corrupção de banco de dados, contactar desenvolvedor

---

## 📅 Quando Executar

### Rotina Recomendada:
- **Diariamente:** Se há muita movimentação de estoque
- **Semanalmente:** Para monitoramento geral
- **Quando:** Um cliente reportar produto desaparecido
- **Antes:** De fazer backup ou atualizar código

## 🔧 Como Agir Conforme os Resultados

### Se encontrar Produtos com Estoque Negativo:

1. **Identifique a origem:**
   ```bash
   # Consultar banco direto (SQLite)
   sqlite3 espetao.db
   
   # Dentro do SQLite:
   SELECT * FROM estoque_movimentacoes 
   WHERE produto_id = 5 
   ORDER BY created_at DESC;
   ```

2. **Corrija o estoque:**
   - Via painel `produtos.html`: Ajuste manualmente para o valor correto
   - Adicione uma entrada positiva de "Ajuste Corretivo"

3. **Documente:**
   - Crie um arquivo `INCIDENTES_ESTOQUE.md` com o registro
   - Anote a data, produto, causa e solução

---

### Se encontrar Muitos Produtos com Saldo Zero:

1. **Suspeita:** Possível bug ou corrupção
2. **Ação:** Executar script novamente após reiniciar o programa
3. **Se persistir:** Contactar desenvolvedor com logs

---

## 📊 Exemplo Completo de Uso

```bash
$ python scripts/diagnostico_estoque.py

🚀 Script de Diagnóstico de Estoque
Desenvolvido para detectar inconsistências no banco de dados.

======================================================================
🔍 DIAGNÓSTICO DE INTEGRIDADE DO ESTOQUE
======================================================================

1️⃣  PRODUTOS COM MOVIMENTAÇÕES NEGATIVAS:
----------------------------------------------------------------------
✅ Nenhum produto com estoque negativo encontrado.

2️⃣  PRODUTOS COM SALDO ZERO (Possível Bug):
----------------------------------------------------------------------
✅ Nenhum produto com saldo zero encontrado.

3️⃣  RESUMO DE MOVIMENTAÇÕES POR ORIGEM:
----------------------------------------------------------------------
  • entrada_estoque: 50 movimentações, Total: 245
  • venda_pedido: 120 movimentações, Total: -85
  • ajuste_manual: 2 movimentações, Total: -3
  • cancelamento_pedido: 8 movimentações, Total: 15

4️⃣  PRODUTOS SEM CATEGORIA:
----------------------------------------------------------------------
✅ Todos os produtos têm categoria atribuída.

5️⃣  ESTATÍSTICAS GERAIS:
----------------------------------------------------------------------
  • Total de Produtos: 48
  • Total de Movimentações: 180
  • Reservas Ativas: 2

======================================================================
✅ Diagnóstico concluído!
======================================================================

🧹 LIMPANDO RESERVAS EXPIRADAS...
----------------------------------------------------------------------
✅ 0 reserva(s) expirada(s) removida(s).

# Tudo OK! Nenhuma ação necessária.
```

---

## 🚨 Troubleshooting

### "Error: database is locked"
- **Causa:** Programa está rodando e usando o banco
- **Solução:** Feche o programa, execute o script, reabra o programa

### "File not found: espetao.db"
- **Causa:** Script está sendo executado de pasta errada
- **Solução:** Execute do diretório raiz (`cd c:\Users\leotn\VSCode\projeto_espetao`)

### "No module named sqlite3"
- **Causa:** SQLite3 não está instalado (raro)
- **Solução:** SQLite3 é built-in no Python, reinstale Python

---

## 💡 Tips & Tricks

### Salvar Output em Arquivo:
```bash
python scripts/diagnostico_estoque.py > diagnostico_saida.txt
```

### Executar Apenas uma Parte:
Editar o script e comentar as seções que não quer

### Adicionar Checagem Customizada:
Editar o script e adicionar nova query SQL na seção "5️⃣ ESTATÍSTICAS GERAIS"

---

## 📞 Suporte

Se o script encontrar problemas, documente:
1. O output completo do script
2. A data/hora da execução
3. O que você estava fazendo quando isso ocorreu
4. Número de clientes conectados

Compartilhe essas informações com o desenvolvedor.

---

**Última atualização:** 5 de novembro de 2025  
**Script criado para:** Monitorar bug #1 (Desaparecimento de Produtos)
