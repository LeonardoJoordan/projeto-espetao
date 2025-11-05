#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Diagnóstico: Detectar e Limpar Produtos com Estoque Anômalo
Uso: python scripts/diagnostico_estoque.py
"""

import sqlite3
import sys
from pathlib import Path

# Adiciona o diretório pai ao path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent))

NOME_BANCO_DADOS = 'espetao.db'

def conectar_banco():
    """Conecta ao banco de dados."""
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

def diagnosticar_estoque():
    """Faz diagnóstico completo do estoque."""
    conn = conectar_banco()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    print("\n" + "="*70)
    print("🔍 DIAGNÓSTICO DE INTEGRIDADE DO ESTOQUE")
    print("="*70 + "\n")
    
    # 1. Produtos com movimentações negativas
    print("1️⃣  PRODUTOS COM MOVIMENTAÇÕES NEGATIVAS:")
    print("-" * 70)
    cursor.execute("""
        SELECT p.id, p.nome, SUM(m.quantidade) as total_movimentacoes
        FROM produtos p
        LEFT JOIN estoque_movimentacoes m ON p.id = m.produto_id
        GROUP BY p.id
        HAVING total_movimentacoes < 0
        ORDER BY total_movimentacoes ASC
    """)
    
    produtos_negativos = cursor.fetchall()
    if produtos_negativos:
        print(f"⚠️  ENCONTRADOS {len(produtos_negativos)} PRODUTOS COM ESTOQUE NEGATIVO:\n")
        for row in produtos_negativos:
            print(f"  • ID {row['id']}: {row['nome']}")
            print(f"    Total de Movimentações: {row['total_movimentacoes']}")
    else:
        print("✅ Nenhum produto com estoque negativo encontrado.\n")
    
    # 2. Produtos com disponibilidade = 0 mas com movimentações positivas
    print("\n2️⃣  PRODUTOS COM SALDO ZERO (Possível Bug):")
    print("-" * 70)
    cursor.execute("""
        SELECT 
            p.id, 
            p.nome, 
            SUM(m.quantidade) as on_hand,
            COALESCE((SELECT SUM(r.quantidade_reservada) 
                      FROM reservas_carrinho r 
                      WHERE r.produto_id = p.id), 0) as reservado
        FROM produtos p
        LEFT JOIN estoque_movimentacoes m ON p.id = m.produto_id
        GROUP BY p.id
        HAVING (SUM(m.quantidade) - COALESCE((SELECT SUM(r.quantidade_reservada) 
                                             FROM reservas_carrinho r 
                                             WHERE r.produto_id = p.id), 0)) = 0
    """)
    
    produtos_zerados = cursor.fetchall()
    if produtos_zerados:
        print(f"⚠️  ENCONTRADOS {len(produtos_zerados)} PRODUTOS COM SALDO ZERO:\n")
        for row in produtos_zerados:
            print(f"  • ID {row['id']}: {row['nome']}")
            print(f"    On Hand: {row['on_hand'] or 0}, Reservado: {row['reservado']}")
    else:
        print("✅ Nenhum produto com saldo zero encontrado.\n")
    
    # 3. Resumo de movimentações por tipo de origem
    print("\n3️⃣  RESUMO DE MOVIMENTAÇÕES POR ORIGEM:")
    print("-" * 70)
    cursor.execute("""
        SELECT origem, COUNT(*) as quantidade, SUM(quantidade) as total
        FROM estoque_movimentacoes
        GROUP BY origem
        ORDER BY origem
    """)
    
    origens = cursor.fetchall()
    for row in origens:
        print(f"  • {row['origem']}: {row['quantidade']} movimentações, Total: {row['total']}")
    
    # 4. Verificar integridade de referências
    print("\n4️⃣  PRODUTOS SEM CATEGORIA:")
    print("-" * 70)
    cursor.execute("""
        SELECT id, nome FROM produtos WHERE categoria_id IS NULL
    """)
    
    sem_categoria = cursor.fetchall()
    if sem_categoria:
        print(f"⚠️  ENCONTRADOS {len(sem_categoria)} PRODUTOS SEM CATEGORIA:\n")
        for row in sem_categoria:
            print(f"  • ID {row['id']}: {row['nome']}")
    else:
        print("✅ Todos os produtos têm categoria atribuída.\n")
    
    # 5. Estatísticas gerais
    print("\n5️⃣  ESTATÍSTICAS GERAIS:")
    print("-" * 70)
    cursor.execute("SELECT COUNT(*) as total FROM produtos")
    total_produtos = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM estoque_movimentacoes")
    total_movimentacoes = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM reservas_carrinho WHERE expires_at > datetime('now')")
    reservas_ativas = cursor.fetchone()['total']
    
    print(f"  • Total de Produtos: {total_produtos}")
    print(f"  • Total de Movimentações: {total_movimentacoes}")
    print(f"  • Reservas Ativas: {reservas_ativas}")
    
    conn.close()
    
    print("\n" + "="*70)
    print("✅ Diagnóstico concluído!")
    print("="*70 + "\n")

def limpar_reservas_expiradas():
    """Remove reservas expiradas do banco."""
    conn = conectar_banco()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    print("\n🧹 LIMPANDO RESERVAS EXPIRADAS...")
    print("-" * 70)
    
    cursor.execute("DELETE FROM reservas_carrinho WHERE expires_at <= datetime('now')")
    deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"✅ {deleted} reserva(s) expirada(s) removida(s).\n")

if __name__ == '__main__':
    print("\n🚀 Script de Diagnóstico de Estoque")
    print("Desenvolvido para detectar inconsistências no banco de dados.\n")
    
    diagnosticar_estoque()
    limpar_reservas_expiradas()
