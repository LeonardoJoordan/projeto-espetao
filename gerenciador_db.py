import sqlite3
import datetime
import json # Adicione esta importação no topo do seu arquivo, junto com as outras
from datetime import timedelta # Adicione esta importação também

NOME_BANCO_DADOS = 'espetao.db'

# Voltando ao estado original: lista de pedidos vazia.
PEDIDOS = []
_proximo_id = 1

def adicionar_nova_categoria(nome_categoria):
    """
    Adiciona uma nova categoria na tabela 'categorias' do banco de dados.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Executa o comando SQL para inserir a nova categoria
        # O '?' é um placeholder para evitar injeção de SQL, uma boa prática de segurança.
        cursor.execute("INSERT INTO categorias (nome) VALUES (?)", (nome_categoria,))

        conn.commit()
        print(f"Categoria '{nome_categoria}' adicionada com sucesso.")
        return True

    except sqlite3.IntegrityError:
        # Este erro acontece se tentarmos adicionar uma categoria que já existe (por causa do 'UNIQUE')
        print(f"Erro: A categoria '{nome_categoria}' já existe.")
        return False
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar a categoria: {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_todas_categorias():
    """
    Busca e retorna todas as categorias cadastradas no banco de dados, ordenadas pelo campo 'ordem'.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Adicionamos ORDER BY ordem
        cursor.execute("SELECT id, nome FROM categorias ORDER BY ordem, nome") 
        
        categorias_tuplas = cursor.fetchall()
        categorias_lista = []
        for tupla in categorias_tuplas:
            categorias_lista.append({'id': tupla[0], 'nome': tupla[1]})
        
        return categorias_lista

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter as categorias: {e}")
        return [] 
    finally:
        if conn:
            conn.close()

def criar_novo_pedido(nome_cliente, itens_pedido, metodo_pagamento):
    """
    Cria um novo pedido, calcula o valor total, adiciona status e timestamp,
    e o armazena na lista de PEDIDOS.
    """
    global _proximo_id

    valor_total = 0
    # Calcula o valor total do pedido buscando preços do banco de dados
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        
        for item in itens_pedido:
            # Busca o preço do produto no banco de dados
            cursor.execute("SELECT preco_venda FROM produtos WHERE nome = ?", (item['item'],))
            resultado = cursor.fetchone()
            
            if resultado:
                preco_unitario = resultado[0]
            else:
                preco_unitario = 0  # Se não encontrar o produto, preço = 0
            
            valor_total += preco_unitario * item['quantidade']
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Erro ao buscar preços do banco: {e}")
        valor_total = 0

    novo_pedido = {
        'id': _proximo_id,
        'nome_cliente': nome_cliente,
        'itens': itens_pedido,
        'metodo_pagamento': metodo_pagamento,
        'status': 'recebido',
        'timestamp': datetime.datetime.now().isoformat(),
        'valor_total': valor_total # Adicionamos o campo calculado
    }

    PEDIDOS.append(novo_pedido)

    print("\n--- BASE DE DADOS ATUALIZADA ---")
    for pedido in PEDIDOS:
        print(pedido)
    print("--------------------------------\n")

    _proximo_id += 1
    return novo_pedido['id']

def adicionar_novo_produto(nome, preco_venda, estoque_inicial, custo_inicial, categoria_id):
    """
    Adiciona um novo produto na tabela 'produtos'.
    Calcula o custo total inicial do estoque.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Calcula o custo total do estoque inicial
        custo_total_estoque = custo_inicial * estoque_inicial

        # Comando SQL para inserir um novo produto
        cursor.execute('''
            INSERT INTO produtos (nome, preco_venda, estoque_atual, custo_total_do_estoque, categoria_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (nome, preco_venda, estoque_inicial, custo_total_estoque, categoria_id))

        conn.commit()
        print(f"Produto '{nome}' adicionado com sucesso.")
        return True

    except sqlite3.IntegrityError:
        print(f"Erro: O produto '{nome}' já existe.")
        return False
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar o produto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_todos_produtos():
    """
    Busca todos os produtos, juntando com o nome da categoria,
    e calcula o custo médio e o lucro para cada um, ordenados pela 'ordem' do produto.
    Também busca o último preço de compra registrado.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Adicionamos ORDER BY p.ordem
        cursor.execute('''
            SELECT p.id, p.nome, p.preco_venda, p.estoque_atual, p.custo_total_do_estoque, c.nome as categoria_nome, p.categoria_id
            FROM produtos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.estoque_atual > 0
            ORDER BY c.ordem, p.ordem, p.nome 
        ''')
        
        produtos_tuplas = cursor.fetchall()
        produtos_lista = []
        for tupla in produtos_tuplas:
            id_produto, nome, preco_venda, estoque, custo_total, categoria, categoria_id = tupla
            
            if estoque > 0:
                custo_medio = custo_total / estoque
                lucro = preco_venda - custo_medio
            else:
                custo_medio = 0
                lucro = preco_venda 

            # Busca o último preço de compra registrado
            cursor.execute('''
                SELECT custo_unitario_compra 
                FROM entradas_de_estoque 
                WHERE id_produto = ? 
                ORDER BY data_entrada DESC 
                LIMIT 1
            ''', (id_produto,))
            
            ultimo_preco_compra_resultado = cursor.fetchone()
            ultimo_preco_compra = ultimo_preco_compra_resultado[0] if ultimo_preco_compra_resultado else custo_medio

            produtos_lista.append({
                'id': id_produto,
                'nome': nome,
                'preco_venda': preco_venda,
                'estoque': estoque,
                'custo_medio': custo_medio,
                'lucro': lucro,
                'categoria': categoria,
                'categoria_id': categoria_id,
                'ultimo_preco_compra': ultimo_preco_compra
            })
        
        return produtos_lista

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os produtos: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_todos_produtos_para_gestao():
    """
    Busca TODOS os produtos para a tela de gestão, incluindo os sem estoque.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # A consulta é idêntica à original, mas sem o filtro "WHERE"
        cursor.execute('''
            SELECT p.id, p.nome, p.preco_venda, p.estoque_atual, p.custo_total_do_estoque, c.nome as categoria_nome, p.categoria_id
            FROM produtos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            ORDER BY c.ordem, p.ordem, p.nome 
        ''')
        
        produtos_tuplas = cursor.fetchall()
        produtos_lista = []
        for tupla in produtos_tuplas:
            id_produto, nome, preco_venda, estoque, custo_total, categoria, categoria_id = tupla
            
            if estoque > 0:
                custo_medio = custo_total / estoque
                lucro = preco_venda - custo_medio
            else:
                custo_medio = 0
                lucro = preco_venda 

            cursor.execute('''
                SELECT custo_unitario_compra 
                FROM entradas_de_estoque 
                WHERE id_produto = ? 
                ORDER BY data_entrada DESC 
                LIMIT 1
            ''', (id_produto,))
            
            ultimo_preco_compra_resultado = cursor.fetchone()
            ultimo_preco_compra = ultimo_preco_compra_resultado[0] if ultimo_preco_compra_resultado else custo_medio

            produtos_lista.append({
                'id': id_produto,
                'nome': nome,
                'preco_venda': preco_venda,
                'estoque': estoque,
                'custo_medio': custo_medio,
                'lucro': lucro,
                'categoria': categoria,
                'categoria_id': categoria_id,
                'ultimo_preco_compra': ultimo_preco_compra
            })
        
        return produtos_lista

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os produtos para gestão: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_pedidos_ativos():
    """
    Busca no banco de dados todos os pedidos ativos, ordenando por
    prioridade de status e, em seguida, por data.
    """
    # Lista de todos os status que consideramos "ativos" na tela da cozinha
    lista_status_ativos = ['aguardando_pagamento', 'aguardando_producao', 'em_producao', 'aguardando_retirada']
    pedidos_encontrados = []
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        placeholders = ','.join(['?'] * len(lista_status_ativos))

        # A nova consulta com a lógica de ordenação complexa
        query = f"""
            SELECT * FROM pedidos 
            WHERE status IN ({placeholders}) 
            ORDER BY 
                CASE status
                    WHEN 'aguardando_pagamento' THEN 1 -- Prioridade 1
                    WHEN 'aguardando_producao'  THEN 2 -- Prioridade 2
                    WHEN 'aguardando_retirada'  THEN 3 -- Prioridade 3
                    WHEN 'em_producao'          THEN 4 -- Prioridade 4
                END,
                CASE status
                    WHEN 'aguardando_producao' THEN timestamp_pagamento -- Fila do pagamento
                    ELSE timestamp_criacao                           -- Fila de chegada
                END ASC
        """
        cursor.execute(query, lista_status_ativos)

        resultados = cursor.fetchall()

        for row in resultados:
            pedido = dict(row)
            pedido['itens'] = json.loads(pedido['itens_json'])
            pedidos_encontrados.append(pedido)

        return pedidos_encontrados

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os pedidos ativos: {e}")
        return [] 
    finally:
        if conn:
            conn.close()

def excluir_categoria(id_categoria):
    """
    Exclui uma categoria da tabela 'categorias' com base no seu ID.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Executa o comando SQL para deletar a categoria
        # A cláusula WHERE é crucial para garantir que estamos apagando a linha certa.
        cursor.execute("DELETE FROM categorias WHERE id = ?", (id_categoria,))

        conn.commit()
        print(f"Categoria com ID {id_categoria} excluída com sucesso.")
        return True

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao excluir a categoria: {e}")
        return False
    finally:
        if conn:
            conn.close()

def excluir_produto(id_produto):
    """
    Exclui um produto e todas as suas entradas de estoque associadas.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Primeiro, exclui o histórico de entradas para este produto
        cursor.execute("DELETE FROM entradas_de_estoque WHERE id_produto = ?", (id_produto,))
        
        # Depois, exclui o produto principal
        cursor.execute("DELETE FROM produtos WHERE id = ?", (id_produto,))

        conn.commit()
        print(f"Produto com ID {id_produto} e seu histórico foram excluídos com sucesso.")
        return True

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao excluir o produto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def adicionar_estoque(id_produto, quantidade_adicionada, custo_unitario_movimentacao):
    """
    Adiciona ou remove estoque, tratando os casos de Compra, Perda e Correção,
    e registra a entrada no histórico.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # PASSO 1: Ler o estado atual do produto
        cursor.execute("SELECT estoque_atual, custo_total_do_estoque FROM produtos WHERE id = ?", (id_produto,))
        resultado = cursor.fetchone()

        if not resultado:
            print(f"Erro: Produto com ID {id_produto} não encontrado.")
            return False

        estoque_atual, custo_total_atual = resultado
        novo_custo_total = custo_total_atual # Valor padrão

        # PASSO 2: A nova árvore de decisão de três vias
        if quantidade_adicionada > 0:
            # CASO 1: COMPRA (Quantidade positiva)
            print("INFO: Detectada operação de COMPRA.")
            custo_desta_compra = quantidade_adicionada * custo_unitario_movimentacao
            novo_custo_total = custo_total_atual + custo_desta_compra
        
        elif quantidade_adicionada < 0 and custo_unitario_movimentacao > 0:
            # CASO 2: CORREÇÃO DE ERRO (Qtd negativa, Custo positivo)
            print("INFO: Detectada operação de CORREÇÃO DE ERRO.")
            custo_a_reverter = abs(quantidade_adicionada) * custo_unitario_movimentacao
            novo_custo_total = custo_total_atual - custo_a_reverter
            
        elif quantidade_adicionada < 0 and custo_unitario_movimentacao == 0:
            # CASO 3: PERDA (Qtd negativa, Custo zero)
            print("INFO: Detectada operação de PERDA.")
            # O novo_custo_total já é igual ao custo_total_atual, nada a fazer aqui.

        # Calcula o novo estoque e valida para não ficar negativo
        novo_estoque = estoque_atual + quantidade_adicionada
        if novo_estoque < 0:
            print(f"Erro: A operação resultaria em estoque negativo ({novo_estoque}). Operação cancelada.")
            return False
        # Valida para o custo não ficar negativo
        if novo_custo_total < 0:
            print(f"Erro: A operação resultaria em custo total negativo (R$ {novo_custo_total:.2f}). Verifique os valores. Operação cancelada.")
            return False


        # PASSO 3: Atualizar o produto com os novos valores
        cursor.execute('''
            UPDATE produtos 
            SET estoque_atual = ?, custo_total_do_estoque = ?
            WHERE id = ?
        ''', (novo_estoque, novo_custo_total, id_produto))

        # PASSO 4: Registrar esta movimentação no histórico
        data_atual = datetime.datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO entradas_de_estoque (id_produto, quantidade_comprada, custo_unitario_compra, data_entrada)
            VALUES (?, ?, ?, ?)
        ''', (id_produto, quantidade_adicionada, custo_unitario_movimentacao, data_atual))

        conn.commit()
        print(f"Estoque do produto ID {id_produto} atualizado com sucesso. Novo estoque: {novo_estoque}.")
        return True

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar estoque: {e}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_preco_venda_produto(id_produto, novo_preco_venda):
    """
    Atualiza o preço de venda de um produto existente no banco de dados.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Comando SQL para atualizar o preco_venda do produto com base no ID
        cursor.execute('''
            UPDATE produtos 
            SET preco_venda = ?
            WHERE id = ?
        ''', (novo_preco_venda, id_produto))

        conn.commit()
        print(f"Preço de venda do produto ID {id_produto} atualizado para R$ {novo_preco_venda:.2f} com sucesso.")
        return True

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao atualizar o preço de venda do produto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_ordem_itens(tabela, ids_ordenados):
    """
    Atualiza a coluna 'ordem' de itens em uma tabela específica
    com base em uma lista de IDs ordenados.
    
    Args:
        tabela (str): O nome da tabela ('categorias' ou 'produtos').
        ids_ordenados (list): Uma lista de IDs na ordem desejada.
    """
    if tabela not in ['categorias', 'produtos']:
        print(f"Erro: Tabela '{tabela}' não suportada para atualização de ordem.")
        return False

    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Itera sobre a lista de IDs ordenados para atualizar a ordem de cada item
        for indice, item_id in enumerate(ids_ordenados):
            nova_ordem = indice + 1  # A ordem começa de 1 para facilitar
            cursor.execute(f"UPDATE {tabela} SET ordem = ? WHERE id = ?", (nova_ordem, item_id))

        conn.commit()
        print(f"Ordem dos itens na tabela '{tabela}' atualizada com sucesso.")
        return True

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao atualizar a ordem dos itens na tabela '{tabela}': {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_historico_produto(id_produto):
    """
    Busca e retorna o histórico de todas as entradas de estoque para um produto específico.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Seleciona todas as entradas de um produto, ordenadas pela mais recente primeiro
        cursor.execute('''
            SELECT data_entrada, quantidade_comprada, custo_unitario_compra 
            FROM entradas_de_estoque 
            WHERE id_produto = ? 
            ORDER BY data_entrada DESC
        ''', (id_produto,))
        
        historico_tuplas = cursor.fetchall()

        # Converte a lista de tuplas em uma lista de dicionários
        historico_lista = []
        for tupla in historico_tuplas:
            # Formata a data para um formato mais legível
            data_formatada = datetime.datetime.fromisoformat(tupla[0]).strftime('%d/%m/%Y %H:%M')
            
            historico_lista.append({
                'data': data_formatada, 
                'quantidade': tupla[1], 
                'custo': tupla[2]
            })
        
        return historico_lista

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter o histórico do produto: {e}")
        return []
    finally:
        if conn:
            conn.close()

def salvar_novo_pedido(dados_do_pedido):
    """
    Salva um novo pedido, buscando o custo médio de cada item no momento da venda
    e armazenando essa informação no JSON do pedido.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # --- LÓGICA DE ENRIQUECIMENTO: Buscar custo e adicionar ao item ---
        itens_enriquecidos = []
        for item in dados_do_pedido['itens']:
            # Busca o estado atual do produto para calcular o custo médio
            cursor.execute("SELECT custo_total_do_estoque, estoque_atual FROM produtos WHERE id = ?", (item['id'],))
            resultado = cursor.fetchone()
            
            custo_a_registrar = 0
            if resultado:
                custo_total_estoque, estoque_atual = resultado
                
                if estoque_atual > 0:
                    # CASO 1: Estoque positivo, usa a média ponderada.
                    custo_a_registrar = custo_total_estoque / estoque_atual
                else:
                    # CASO 2: Estoque zerado, busca o custo da última compra.
                    cursor.execute("""
                        SELECT custo_unitario_compra 
                        FROM entradas_de_estoque 
                        WHERE id_produto = ? AND quantidade_comprada > 0
                        ORDER BY data_entrada DESC 
                        LIMIT 1
                    """, (item['id'],))
                    ultimo_custo_resultado = cursor.fetchone()
                    
                    if ultimo_custo_resultado:
                        custo_a_registrar = ultimo_custo_resultado[0]

            # Adiciona o custo capturado ao dicionário do item
            item_com_custo = item.copy()
            item_com_custo['custo_unitario'] = custo_a_registrar
            itens_enriquecidos.append(item_com_custo)
        
        # --- Missão 1: Salvar o Pedido com os dados de custo já inclusos ---
        itens_como_json = json.dumps(itens_enriquecidos)
        timestamp_atual = datetime.datetime.now().isoformat()
        valor_total = sum(item['preco'] * item['quantidade'] for item in dados_do_pedido['itens'])

        cursor.execute('''
            INSERT INTO pedidos (nome_cliente, status, metodo_pagamento, valor_total, timestamp_criacao, itens_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            dados_do_pedido['nome_cliente'],
            'aguardando_pagamento',
            dados_do_pedido['metodo_pagamento'],
            valor_total,
            timestamp_atual,
            itens_como_json
        ))

        id_do_pedido_salvo = cursor.lastrowid

        # --- Missão 2: Mover o estoque de 'atual' para 'reservado' ---
        for item in dados_do_pedido['itens']:
            cursor.execute('''
                UPDATE produtos
                SET estoque_atual = estoque_atual - ?,
                    estoque_reservado = estoque_reservado + ?
                WHERE id = ?
            ''', (
                item['quantidade'],
                item['quantidade'],
                item['id']
            ))

        conn.commit()

        print(f"SUCESSO: Pedido #{id_do_pedido_salvo} criado com CUSTO REGISTRADO e estoque RESERVADO.")
        return id_do_pedido_salvo

    except sqlite3.Error as e:
        print(f"ERRO ao salvar o pedido: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def confirmar_pagamento_pedido(id_do_pedido):
    """
    Altera o status de um pedido para 'aguardando_producao' e registra
    o horário do pagamento.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        timestamp_atual = datetime.datetime.now().isoformat()

        cursor.execute("""
            UPDATE pedidos
            SET status = ?, timestamp_pagamento = ?
            WHERE id = ? AND status = ?
        """, ('aguardando_producao', timestamp_atual, id_do_pedido, 'aguardando_pagamento'))

        # cursor.rowcount nos diz quantas linhas foram afetadas.
        # Se for 0, o pedido não foi encontrado ou já tinha outro status.
        if cursor.rowcount == 0:
            print(f"AVISO: Nenhuma linha alterada para o pedido #{id_do_pedido}. Status pode não ser 'aguardando_pagamento'.")
            return False

        conn.commit()
        print(f"SUCESSO: Pagamento do pedido #{id_do_pedido} confirmado.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao confirmar pagamento do pedido #{id_do_pedido}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def iniciar_preparo_pedido(id_do_pedido):
    """
    Muda o status de um pedido para 'em_producao'.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Atualiza o status do pedido de 'aguardando_producao' para 'em_producao'
        cursor.execute(
            "UPDATE pedidos SET status = ? WHERE id = ? AND status = ?",
            ('em_producao', id_do_pedido, 'aguardando_producao')
        )

        # Verifica se alguma linha foi realmente alterada
        if cursor.rowcount == 0:
            print(f"AVISO: Pedido #{id_do_pedido} não encontrado ou não estava aguardando produção.")
            return False

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} movido para 'em produção'.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao iniciar preparo do pedido #{id_do_pedido}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def entregar_pedido(id_do_pedido):
    """
    Finaliza um pedido, mudando seu status para 'finalizado'.
    Calcula o custo total dos itens vendidos, baixa o estoque reservado
    e armazena o custo e o timestamp de finalização no registro do pedido.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        cursor.execute("SELECT itens_json FROM pedidos WHERE id = ?", (id_do_pedido,))
        resultado = cursor.fetchone()
        if not resultado:
            print(f"AVISO: Tentativa de entregar pedido #{id_do_pedido} que não existe.")
            return False

        itens_do_pedido = json.loads(resultado[0])
        custo_total_dos_itens_vendidos = 0

        for item in itens_do_pedido:
            id_produto = item['id']
            quantidade_vendida = item['quantidade']

            cursor.execute("""
                SELECT estoque_atual, estoque_reservado, custo_total_do_estoque
                FROM produtos WHERE id = ?
            """, (id_produto,))
            
            res_produto = cursor.fetchone()
            if not res_produto: continue

            estoque_atual, estoque_reservado, custo_total_atual = res_produto
            estoque_total_antes_da_venda = estoque_atual + estoque_reservado

            custo_medio_unitario = 0
            if estoque_total_antes_da_venda > 0:
                custo_medio_unitario = custo_total_atual / estoque_total_antes_da_venda

            custo_desta_venda_especifica = quantidade_vendida * custo_medio_unitario
            custo_total_dos_itens_vendidos += custo_desta_venda_especifica
            
            cursor.execute("""
                UPDATE produtos
                SET estoque_reservado = estoque_reservado - ?,
                    custo_total_do_estoque = custo_total_do_estoque - ?
                WHERE id = ?
            """, (quantidade_vendida, custo_desta_venda_especifica, id_produto))

        # AGORA, EM VEZ DE DELETAR, ATUALIZAMOS O PEDIDO
        timestamp_final = datetime.datetime.now().isoformat()
        cursor.execute("""
            UPDATE pedidos
            SET status = 'finalizado',
                custo_total_pedido = ?,
                timestamp_finalizacao = ?
            WHERE id = ?
        """, (custo_total_dos_itens_vendidos, timestamp_final, id_do_pedido))

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} finalizado e estoque/custos baixados.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao entregar o pedido #{id_do_pedido}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def cancelar_pedido(id_do_pedido):
    """
    Cancela um pedido, devolvendo o estoque reservado ao estoque atual
    e mudando o status para 'cancelado'.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        cursor.execute("SELECT itens_json FROM pedidos WHERE id = ?", (id_do_pedido,))
        resultado = cursor.fetchone()
        if not resultado:
            print(f"AVISO: Tentativa de cancelar pedido #{id_do_pedido} que não existe.")
            return False

        itens_do_pedido = json.loads(resultado[0])

        for item in itens_do_pedido:
            cursor.execute("""
                UPDATE produtos
                SET estoque_reservado = estoque_reservado - ?,
                    estoque_atual = estoque_atual + ?
                WHERE id = ?
            """, (item['quantidade'], item['quantidade'], item['id']))
        
        # ATUALIZA O STATUS PARA 'CANCELADO'
        timestamp_final = datetime.datetime.now().isoformat()
        cursor.execute("""
            UPDATE pedidos 
            SET status = 'cancelado', timestamp_finalizacao = ? 
            WHERE id = ?
        """, (timestamp_final, id_do_pedido))

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} cancelado e estoque devolvido.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao cancelar o pedido #{id_do_pedido}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def chamar_cliente_pedido(id_do_pedido):
    """
    Muda o status do pedido para 'aguardando_retirada', indicando que está pronto.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Altera o status de 'em_producao' para o novo status 'aguardando_retirada'
        cursor.execute(
            "UPDATE pedidos SET status = ? WHERE id = ? AND status = ?",
            ('aguardando_retirada', id_do_pedido, 'em_producao')
        )

        if cursor.rowcount == 0:
            print(f"AVISO: Pedido #{id_do_pedido} não encontrado ou não estava 'em produção'.")
            return False

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} movido para 'aguardando retirada'.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao chamar cliente para o pedido #{id_do_pedido}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def obter_dados_relatorio(data_inicio, data_fim):
    """
    Busca e calcula todos os dados para o relatório de fechamento
    dentro de um intervalo de datas.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # --- DADOS GERAIS DE PEDIDOS FINALIZADOS ---
        cursor.execute("""
            SELECT id, nome_cliente, valor_total, custo_total_pedido, metodo_pagamento, itens_json, timestamp_finalizacao
            FROM pedidos
            WHERE status = 'finalizado' AND timestamp_finalizacao BETWEEN ? AND ?
        """, (data_inicio, data_fim))
        pedidos_finalizados = cursor.fetchall()
        
        # --- DADOS GERAIS DE PERDAS E AJUSTES ---
        cursor.execute("""
            SELECT quantidade_comprada, custo_unitario_compra
            FROM entradas_de_estoque
            WHERE quantidade_comprada < 0 AND custo_unitario_compra = 0 AND data_entrada BETWEEN ? AND ?
        """,(data_inicio, data_fim))
        perdas_e_ajustes = cursor.fetchall()

        # --- CÁLCULO DOS KPIs ---
        faturamento_bruto = sum(p['valor_total'] for p in pedidos_finalizados)
        lucro_estimado = sum(p['valor_total'] - (p['custo_total_pedido'] or 0) for p in pedidos_finalizados)
        pedidos_realizados = len(pedidos_finalizados)
        ticket_medio = faturamento_bruto / pedidos_realizados if pedidos_realizados > 0 else 0
        total_itens_vendidos = sum(sum(item['quantidade'] for item in json.loads(p['itens_json'])) for p in pedidos_finalizados)
        media_itens_pedido = total_itens_vendidos / pedidos_realizados if pedidos_realizados > 0 else 0
        valor_perdas = 0
        for pa in perdas_e_ajustes:
            # Como é perda (custo_unitario = 0), buscamos o custo médio do produto na data
            cursor.execute("""
                SELECT p.custo_total_do_estoque, p.estoque_atual, p.estoque_reservado
                FROM produtos p
                JOIN entradas_de_estoque e ON p.id = e.id_produto
                WHERE e.quantidade_comprada = ? AND e.custo_unitario_compra = ? AND e.data_entrada BETWEEN ? AND ?
                LIMIT 1
            """, (pa['quantidade_comprada'], pa['custo_unitario_compra'], data_inicio, data_fim))
            
            produto_info = cursor.fetchone()
            if produto_info and (produto_info[1] + produto_info[2]) > 0:
                custo_medio = produto_info[0] / (produto_info[1] + produto_info[2])
                valor_perdas += abs(pa['quantidade_comprada']) * custo_medio
        
        # --- DADOS PARA GRÁFICOS E TABELAS ---
        vendas_por_pagamento = {'pix': 0, 'cartao': 0, 'dinheiro': 0}
        itens_vendidos_agregado = {}
        historico_pedidos_tabela = []

        for p in pedidos_finalizados:
            if p['metodo_pagamento'] in vendas_por_pagamento:
                vendas_por_pagamento[p['metodo_pagamento']] += p['valor_total']

            data_hora_obj = datetime.datetime.fromisoformat(p['timestamp_finalizacao'])
            data_hora_formatada = data_hora_obj.strftime('%d/%m %H:%M')
            historico_pedidos_tabela.append(dict(p, horario=data_hora_formatada))

            # Calcula a proporção de custo para este pedido específico
            ratio_custo = (p['custo_total_pedido'] or 0) / p['valor_total'] if p['valor_total'] > 0 else 0


            for item in json.loads(p['itens_json']):
                pid = item['id']
                if pid not in itens_vendidos_agregado:
                    # Inicializa o dicionário com o campo 'lucro'
                    itens_vendidos_agregado[pid] = {'nome': item['nome'], 'quantidade': 0, 'receita': 0, 'lucro': 0}

                # Usa o custo_unitario que foi 'fotografado' no momento da venda
                # O .get() garante que o código não quebre em pedidos antigos que não tinham esse dado
                custo_unitario = item.get('custo_unitario', 0)
                
                receita_do_item = item['preco'] * item['quantidade']
                lucro_do_item = (item['preco'] - custo_unitario) * item['quantidade']

                # Acumula os totais para o item agregado
                itens_vendidos_agregado[pid]['quantidade'] += item['quantidade']
                itens_vendidos_agregado[pid]['receita'] += receita_do_item
                itens_vendidos_agregado[pid]['lucro'] += lucro_do_item

        itens_mais_vendidos = sorted(list(itens_vendidos_agregado.values()), key=lambda x: x['quantidade'], reverse=True)[:10]

        # --- NOVA LÓGICA PARA DECIDIR O MODO DE AGREGAÇÃO ---
        dt_inicio = datetime.datetime.fromisoformat(data_inicio.replace('Z', '+00:00'))
        dt_fim = datetime.datetime.fromisoformat(data_fim.replace('Z', '+00:00'))
        
        modo_agregacao = '15min' if (dt_fim - dt_inicio) < timedelta(days=2) else 'dia'
        
        vendas_por_periodo = _agregar_vendas_por_periodo(pedidos_finalizados, modo_agregacao)

        # Monta o dicionário de resposta
        return {
            "kpis": {
                "faturamentoBruto": faturamento_bruto,
                "lucroEstimado": lucro_estimado,
                "perdasAjustes": -valor_perdas,
                "pedidosRealizados": pedidos_realizados,
                "ticketMedio": ticket_medio,
                "mediaItensPedido": media_itens_pedido,
            },
            "vendasPorPagamento": {
                "labels": list(vendas_por_pagamento.keys()),
                "data": list(vendas_por_pagamento.values()),
            },
            "itensMaisVendidos": itens_mais_vendidos,
            "historicoPedidos": [dict(p) for p in historico_pedidos_tabela],
            "vendasPorPeriodo": vendas_por_periodo # <-- DADOS DO GRÁFICO PRINCIPAL
        }

    except sqlite3.Error as e:
        print(f"ERRO ao obter dados do relatório: {e}")
        return None
    finally:
        if conn: conn.close()

def _agregar_vendas_por_periodo(pedidos, modo):
    """
    Agrega os dados de vendas por dia ou por hora a partir de uma lista de pedidos.
    """
    vendas_agregadas = {} # Dicionário para agrupar os valores

    for pedido in pedidos:
        # Converte o texto do timestamp para um objeto datetime
        timestamp_obj = datetime.datetime.fromisoformat(pedido['timestamp_finalizacao'])

        if modo == '15min':
            # Arredonda o minuto para o intervalo de 15 mais próximo (0, 15, 30, 45)
            minuto_arredondado = (timestamp_obj.minute // 15) * 15
            chave = f"{timestamp_obj.hour:02d}:{minuto_arredondado:02d}"
        else: # modo == 'dia'
            chave = timestamp_obj.strftime('%d/%m')

        # Pega o valor já acumulado para esta chave (ou 0 se for a primeira vez)
        valor_atual = vendas_agregadas.get(chave, 0)
        
        # Soma o valor do pedido atual e atualiza o dicionário
        vendas_agregadas[chave] = valor_atual + pedido['valor_total']
    
    if not vendas_agregadas:
        return {"labels": [], "data": []}

    # Ordena as chaves para garantir que o gráfico fique em ordem cronológica
    chaves_ordenadas = sorted(vendas_agregadas.keys())

    # Cria as listas finais de labels e dados a partir do dicionário ordenado
    labels_finais = chaves_ordenadas
    dados_finais = [vendas_agregadas[chave] for chave in chaves_ordenadas]

    return {"labels": labels_finais, "data": dados_finais}