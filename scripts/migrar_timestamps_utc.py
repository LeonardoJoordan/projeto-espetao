import sqlite3
from datetime import datetime, timezone
import pytz # Biblioteca necessária para lidar com fusos horários de forma robusta
import os

# --- Configuração ---
# Navega um nível acima para encontrar o banco de dados na raiz do projeto
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'espetao.db')
TIMEZONE_LOCAL = 'America/Sao_Paulo' # Fuso horário original dos timestamps

def migrar_timestamps():
    """
    Conecta ao banco de dados, lê os timestamps de pedidos, converte-os
    de um fuso horário local para UTC e os salva de volta.
    """
    conn = None
    registros_atualizados = 0
    try:
        conn = sqlite3.connect(DB_PATH)
        # Usamos row_factory para acessar colunas pelo nome
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Seleciona os campos de timestamp que precisam de migração
        cursor.execute("SELECT id, timestamp_criacao, timestamp_pagamento, timestamp_finalizacao FROM pedidos")
        pedidos = cursor.fetchall()

        fuso_local = pytz.timezone(TIMEZONE_LOCAL)

        print(f"Iniciando migração de {len(pedidos)} registros...")

        for pedido in pedidos:
            updates = {}
            # Lista dos campos de timestamp a serem verificados no pedido
            campos_timestamp = ['timestamp_criacao', 'timestamp_pagamento', 'timestamp_finalizacao']

            for campo in campos_timestamp:
                timestamp_str = pedido[campo]

                # Pula se o campo for nulo ou se já parece estar em formato UTC
                if not timestamp_str or '+' in timestamp_str or 'Z' in timestamp_str:
                    continue

                try:
                    # 1. Converte a string para um objeto datetime "naive" (sem fuso)
                    dt_naive = datetime.fromisoformat(timestamp_str)

                    # 2. "Localiza" o datetime, informando que ele representa o fuso local
                    dt_local_aware = fuso_local.localize(dt_naive)

                    # 3. Converte o datetime "aware" para UTC
                    dt_utc = dt_local_aware.astimezone(timezone.utc)

                    # 4. Formata de volta para string no padrão ISO, que agora terá o fuso
                    updates[campo] = dt_utc.isoformat()

                except (ValueError, TypeError) as e:
                    print(f"AVISO: Não foi possível converter o timestamp '{timestamp_str}' do pedido ID {pedido['id']}. Erro: {e}")
                    continue

            # Se houver timestamps para atualizar, monta e executa o UPDATE
            if updates:
                set_clauses = ", ".join([f"{key} = ?" for key in updates.keys()])
                params = list(updates.values())
                params.append(pedido['id'])

                query_update = f"UPDATE pedidos SET {set_clauses} WHERE id = ?"
                cursor.execute(query_update, params)
                registros_atualizados += 1

        conn.commit()
        print("\nMigração concluída com sucesso!")
        print(f"{registros_atualizados} registros foram atualizados com timestamps em UTC.")

    except sqlite3.Error as e:
        print(f"\nERRO CRÍTICO durante a migração: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # É uma boa prática fazer um backup do banco de dados antes de rodar!
    print("--- SCRIPT DE MIGRAÇÃO DE TIMESTAMPS PARA UTC ---")
    backup_path = DB_PATH + '.backup'
    if not os.path.exists(backup_path):
         with open(DB_PATH, 'rb') as f_read:
            with open(backup_path, 'wb') as f_write:
                f_write.write(f_read.read())
         print(f"Backup do banco de dados criado em: {backup_path}")

    migrar_timestamps()