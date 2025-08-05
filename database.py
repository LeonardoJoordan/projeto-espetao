import sqlite3

NOME_BANCO_DADOS = 'espetao.db'

def inicializar_banco():
    """
    Cria e inicializa o banco de dados e suas tabelas, se não existirem.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        print(f"Banco de dados '{NOME_BANCO_DADOS}' conectado com sucesso.")

        # Tabela de Locais
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE
            )
        ''')
        print("Tabela 'locais' verificada/criada.")

        # Tabela de Categorias
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                ordem INTEGER DEFAULT 0  -- NOVO CAMPO: Ordem para arrastar e soltar
            )
        ''')
        print("Tabela 'categorias' verificada/criada.")

        # Tabela de Produtos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                descricao TEXT,
                foto_url TEXT,
                preco_venda REAL NOT NULL,
                estoque_atual INTEGER NOT NULL,
                estoque_reservado INTEGER NOT NULL DEFAULT 0,
                custo_medio REAL NOT NULL DEFAULT 0,
                categoria_id INTEGER,
                ordem INTEGER DEFAULT 0,
                requer_preparo INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (categoria_id) REFERENCES categorias (id)
            )
        ''')
        print("Tabela 'produtos' verificada/criada.")

        # Garante que a categoria 'Espetinhos' sempre exista
        cursor.execute('''
            INSERT OR IGNORE INTO categorias (id, nome, ordem) VALUES (1, 'Espetinhos', 0)
        ''')

        # Tabela de Tempos de Preparo (NOVA)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tempos_preparo (
                produto_id INTEGER NOT NULL,
                ponto TEXT NOT NULL,
                tempo_em_segundos INTEGER NOT NULL,
                PRIMARY KEY (produto_id, ponto),
                FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
            )
        ''')
        print("Tabela 'tempos_preparo' verificada/criada.")        

        # Tabela de Entradas de Estoque (Histórico de Compras)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entradas_de_estoque (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_produto INTEGER NOT NULL,
                quantidade_comprada INTEGER NOT NULL,
                custo_unitario_compra REAL NOT NULL,
                data_entrada TEXT NOT NULL,
                FOREIGN KEY (id_produto) REFERENCES produtos (id)
            )
        ''')
        print("Tabela 'entradas_de_estoque' verificada/criada.")

        # Tabela de Pedidos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_cliente TEXT,
                status TEXT NOT NULL,
                metodo_pagamento TEXT,
                valor_total REAL,
                custo_total_pedido REAL,
                timestamp_criacao TEXT NOT NULL,
                timestamp_pagamento TEXT,
                timestamp_finalizacao TEXT,
                itens_json TEXT,
                senha_diaria INTEGER NOT NULL DEFAULT 1,
                fluxo_simples INTEGER NOT NULL DEFAULT 0, -- 1 se for simples, 0 se for complexo
                local_id INTEGER,
                FOREIGN KEY (local_id) REFERENCES locais (id)
            )
        ''')
        print("Tabela 'pedidos' verificada/criada.")

        # Tabela de Acompanhamentos (NOVA)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS acompanhamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                is_visivel INTEGER NOT NULL DEFAULT 1
            )
        ''')
        print("Tabela 'acompanhamentos' verificada/criada.")

        # Tabela de Configurações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor REAL NOT NULL
            )
        ''')
        print("Tabela 'configuracoes' verificada/criada.")

        # Insere valores padrão para as taxas, caso não existam
        config_padrao = {
            'taxa_credito': 0.0,
            'taxa_debito': 0.0,
            'taxa_pix': 0.0
        }
        for chave, valor in config_padrao.items():
            cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))
        print("Configurações padrão de taxas verificadas/inseridas.")


        conn.commit()
        print("Alterações salvas no banco de dados.")

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao trabalhar com o banco de dados: {e}")
    finally:
        if conn:
            conn.close()
            print("Conexão com o banco de dados fechada.")

if __name__ == '__main__':
    print("Iniciando configuração do banco de dados...")
    inicializar_banco()
    print("Configuração do banco de dados concluída.")