import sqlite3

NOME_BANCO_DADOS = 'espetao.db'

def migrar_tabela_reservas():
    """
    Atualiza a estrutura da tabela 'reservas_carrinho' para a nova versão global,
    removendo a dependência de 'local_id'.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        print("Conectado ao banco de dados para migração...")

        # Passo 1: Renomear a tabela antiga, caso ela exista.
        # Isso serve como um backup temporário e evita erros.
        try:
            cursor.execute("ALTER TABLE reservas_carrinho RENAME TO reservas_carrinho_old;")
            print("Tabela 'reservas_carrinho' antiga renomeada para 'reservas_carrinho_old'.")
        except sqlite3.OperationalError as e:
            # Se a tabela antiga não existir, não há nada a fazer.
            if "no such table" in str(e):
                print("Tabela 'reservas_carrinho' antiga não encontrada. A nova será criada.")
                pass # A tabela nova será criada no próximo passo de qualquer forma
            else:
                raise e # Lança outros erros inesperados

        # Passo 2: Criar a nova tabela 'reservas_carrinho' com a estrutura correta (global).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservas_carrinho (
                carrinho_id TEXT NOT NULL,
                produto_id INTEGER NOT NULL,
                quantidade_reservada INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (carrinho_id, produto_id),
                FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
            )
        ''')
        print("Nova tabela 'reservas_carrinho' com estrutura global criada com sucesso.")
        
        # Passo 3 (Opcional, mas recomendado): Criar o índice em 'expires_at' que removemos sem querer.
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_reservas_expires
            ON reservas_carrinho (expires_at);
        ''')
        print("Índice para 'reservas_carrinho' (expires_at) verificado/criado.")

        # Passo 4: Remover a tabela antiga permanentemente.
        try:
            cursor.execute("DROP TABLE reservas_carrinho_old;")
            print("Tabela 'reservas_carrinho_old' removida.")
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                pass # Se já não existia, tudo bem.
            else:
                raise e

        conn.commit()
        print("\nMigração concluída com sucesso!")

    except sqlite3.Error as e:
        print(f"\nOcorreu um erro durante a migração: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Conexão com o banco de dados fechada.")

if __name__ == '__main__':
    migrar_tabela_reservas()