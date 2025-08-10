import sqlite3
import datetime
import json # Adicione esta importação no topo do seu arquivo, junto com as outras
from datetime import timedelta, timezone # Adicione esta importação também
import random

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
        'timestamp': datetime.datetime.now(timezone.utc).isoformat(),
        'valor_total': valor_total # Adicionamos o campo calculado
    }

    PEDIDOS.append(novo_pedido)

    print("\n--- BASE DE DADOS ATUALIZADA ---")
    for pedido in PEDIDOS:
        print(pedido)
    print("--------------------------------\n")

    _proximo_id += 1
    return novo_pedido['id']

def adicionar_novo_produto(nome, descricao, foto_url, preco_venda, estoque_inicial, custo_inicial, categoria_id, requer_preparo):
    """
    Adiciona um novo produto na tabela 'produtos', salvando seu custo médio inicial.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # O custo_inicial de compra é o primeiro custo_medio do produto.
        custo_medio_inicial = custo_inicial

        # Comando SQL atualizado para usar a coluna `custo_medio`
        cursor.execute('''
            INSERT INTO produtos (nome, descricao, foto_url, preco_venda, estoque_atual, custo_medio, categoria_id, requer_preparo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nome, descricao, foto_url, preco_venda, estoque_inicial, custo_medio_inicial, categoria_id, requer_preparo))

        conn.commit()
        print(f"Produto '{nome}' adicionado com custo médio de {custo_medio_inicial:.2f} (Requer preparo: {requer_preparo}).")
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
    Busca todos os produtos com estoque, lendo o custo médio diretamente do banco
    e calculando o lucro.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # A query agora busca p.custo_medio em vez de p.custo_total_do_estoque
        cursor.execute('''
            SELECT p.id, p.nome, p.descricao, p.foto_url, p.preco_venda, p.estoque_atual, 
                p.custo_medio, c.nome as categoria_nome, p.categoria_id, p.requer_preparo,
                c.ordem as categoria_ordem, p.ordem as produto_ordem
            FROM produtos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.estoque_atual > 0
            ORDER BY c.ordem, p.ordem, p.nome 
        ''')
        
        produtos_tuplas = cursor.fetchall()
        produtos_lista = []
        for tupla in produtos_tuplas:
            # Desempacota os valores, incluindo o novo custo_medio
            id_produto, nome, descricao, foto_url, preco_venda, estoque, custo_medio, categoria, categoria_id, requer_preparo, categoria_ordem, produto_ordem = tupla
            
            # O lucro é simplesmente a diferença entre o preço de venda e o custo médio já armazenado
            lucro = preco_venda - custo_medio

            # A lógica para buscar o último preço de compra para o formulário continua útil
            cursor.execute('''
                SELECT custo_unitario_compra 
                FROM entradas_de_estoque 
                WHERE id_produto = ? AND quantidade_comprada > 0
                ORDER BY data_entrada DESC 
                LIMIT 1
            ''', (id_produto,))
            
            ultimo_preco_compra_resultado = cursor.fetchone()
            # Se não houver histórico de compra, o último preço é o custo médio atual.
            ultimo_preco_compra = ultimo_preco_compra_resultado[0] if ultimo_preco_compra_resultado else custo_medio

            produtos_lista.append({
                'id': id_produto, 'nome': nome, 'descricao': descricao, 'foto_url': foto_url,
                'preco_venda': preco_venda, 'estoque': estoque, 'custo_medio': custo_medio,
                'lucro': lucro, 'categoria': categoria, 'categoria_id': categoria_id,
                'ultimo_preco_compra': ultimo_preco_compra, 'requer_preparo': requer_preparo,
                'categoria_ordem': categoria_ordem, # <-- Ordem da categoria adicionada
                'produto_ordem': produto_ordem      # <-- Ordem do produto adicionada
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
    Busca TODOS os produtos para a tela de gestão, lendo o custo médio diretamente
    do banco e calculando o lucro.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Query atualizada para buscar p.custo_medio
        cursor.execute('''
            SELECT p.id, p.nome, p.descricao, p.foto_url, p.preco_venda, p.estoque_atual, p.custo_medio, c.nome as categoria_nome, p.categoria_id, p.requer_preparo
            FROM produtos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            ORDER BY c.ordem, p.ordem, p.nome 
        ''')
        
        produtos_tuplas = cursor.fetchall()
        produtos_lista = []
        for tupla in produtos_tuplas:
            # Desempacota os valores, incluindo o novo custo_medio
            id_produto, nome, descricao, foto_url, preco_venda, estoque, custo_medio, categoria, categoria_id, requer_preparo = tupla
            
            # Cálculo de lucro simplificado
            lucro = preco_venda - custo_medio

            # Lógica para buscar o último preço de compra para preencher o formulário
            cursor.execute('''
                SELECT custo_unitario_compra 
                FROM entradas_de_estoque 
                WHERE id_produto = ? AND quantidade_comprada > 0
                ORDER BY data_entrada DESC 
                LIMIT 1
            ''', (id_produto,))
            
            ultimo_preco_compra_resultado = cursor.fetchone()
            ultimo_preco_compra = ultimo_preco_compra_resultado[0] if ultimo_preco_compra_resultado else custo_medio

            produtos_lista.append({
                'id': id_produto, 'nome': nome, 'descricao': descricao, 'foto_url': foto_url,
                'preco_venda': preco_venda, 'estoque': estoque, 'custo_medio': custo_medio,
                'lucro': lucro, 'categoria': categoria, 'categoria_id': categoria_id,
                'ultimo_preco_compra': ultimo_preco_compra, 'requer_preparo': requer_preparo
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
    Adiciona ou remove estoque, recalculando o custo médio ponderado do produto
    e registrando a entrada no histórico.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # PASSO 1: Ler o estado atual do produto (estoque e custo médio)
        cursor.execute("SELECT estoque_atual, custo_medio FROM produtos WHERE id = ?", (id_produto,))
        resultado = cursor.fetchone()
        if not resultado:
            print(f"Erro: Produto com ID {id_produto} não encontrado.")
            return False
        
        estoque_atual, custo_medio_atual = resultado
        novo_custo_medio = custo_medio_atual # Valor padrão inicial

        # PASSO 2: Calcular o novo estoque
        novo_estoque = estoque_atual + quantidade_adicionada
        if novo_estoque < 0:
            print(f"Erro: A operação resultaria em estoque negativo ({novo_estoque}). Operação cancelada.")
            return False

        # PASSO 3: Calcular o novo custo médio com base na operação
        if novo_estoque > 0:
            # Calcula o valor total do estoque antigo
            valor_total_estoque_antigo = estoque_atual * custo_medio_atual

            if quantidade_adicionada > 0:
                # LÓGICA DE COMPRA (Cenário 1)
                valor_da_nova_compra = quantidade_adicionada * custo_unitario_movimentacao
                novo_valor_total = valor_total_estoque_antigo + valor_da_nova_compra
                novo_custo_medio = novo_valor_total / novo_estoque
            
            elif quantidade_adicionada < 0 and custo_unitario_movimentacao == 0:
                # LÓGICA DE PERDA (Cenário 2)
                # O valor total do estoque permanece o mesmo, mas é dividido por menos itens.
                novo_custo_medio = valor_total_estoque_antigo / novo_estoque

            elif quantidade_adicionada < 0 and custo_unitario_movimentacao > 0:
                # LÓGICA DE CORREÇÃO DE ERRO
                valor_a_reverter = abs(quantidade_adicionada) * custo_unitario_movimentacao
                novo_valor_total = valor_total_estoque_antigo - valor_a_reverter
                novo_custo_medio = novo_valor_total / novo_estoque

        else: # Se o novo estoque for 0, o custo médio também deve ser 0
            novo_custo_medio = 0

        # PASSO 4: Atualizar o produto com os novos valores de estoque e custo médio
        cursor.execute('''
            UPDATE produtos 
            SET estoque_atual = ?, custo_medio = ?
            WHERE id = ?
        ''', (novo_estoque, novo_custo_medio, id_produto))

        # PASSO 5: Registrar esta movimentação no histórico (esta parte não muda)
        data_atual = datetime.datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO entradas_de_estoque (id_produto, quantidade_comprada, custo_unitario_compra, data_entrada)
            VALUES (?, ?, ?, ?)
        ''', (id_produto, quantidade_adicionada, custo_unitario_movimentacao, data_atual))

        conn.commit()
        print(f"Estoque do produto ID {id_produto} atualizado. Novo estoque: {novo_estoque}. Novo Custo Médio: {novo_custo_medio:.2f}.")
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

def _normalizar_e_ordenar_itens(itens_recebidos, cursor):
    """
    Garante que uma lista de itens de pedido esteja ordenada pela chave canônica.
    Chave: categoria_ordem ASC, produto_ordem ASC, id ASC, uid ASC.
    Esta função também enriquece itens que não possuem os campos de ordenação,
    buscando-os no banco de dados (para compatibilidade com dados legados).
    """
    itens_enriquecidos = []
    for item in itens_recebidos:
        # Verifica se os campos de ordenação existem. Se não, busca no DB.
        if 'categoria_ordem' not in item or 'produto_ordem' not in item:
            cursor.execute("""
                SELECT c.ordem, p.ordem
                FROM produtos p
                JOIN categorias c ON p.categoria_id = c.id
                WHERE p.id = ?
            """, (item['id'],))
            resultado_ordem = cursor.fetchone()
            if resultado_ordem:
                item['categoria_ordem'] = resultado_ordem[0]
                item['produto_ordem'] = resultado_ordem[1]
            else: # Fallback para o caso de um produto não ser encontrado
                item['categoria_ordem'] = 999
                item['produto_ordem'] = 999

        # Garante que o item tenha um uid para desempate
        if 'uid' not in item:
            item['uid'] = datetime.datetime.now().timestamp() + random.random()

        itens_enriquecidos.append(item)

    # Ordena a lista enriquecida usando uma função lambda como chave de múltiplos níveis
    itens_enriquecidos.sort(key=lambda x: (
        x.get('categoria_ordem', 999),
        x.get('produto_ordem', 999),
        x.get('id', 0),
        x.get('uid', 0)
    ))

    return itens_enriquecidos

def salvar_novo_pedido(dados_do_pedido, local_id):
    """
    Salva um novo pedido, lendo o custo médio de cada item no momento da venda
    e armazenando essa informação no JSON do pedido.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        proxima_senha = obter_proxima_senha_diaria()

        ids_dos_produtos = [item['id'] for item in dados_do_pedido['itens']]
        if not ids_dos_produtos: 
            return None

        placeholders = ','.join('?' for _ in ids_dos_produtos)
        cursor.execute(f"SELECT requer_preparo FROM produtos WHERE id IN ({placeholders})", ids_dos_produtos)
        resultados_preparo = cursor.fetchall()

        fluxo_e_simples = all(resultado[0] == 0 for resultado in resultados_preparo)

        # Primeiro, normaliza e ordena a lista de itens recebida
        itens_ordenados = _normalizar_e_ordenar_itens(dados_do_pedido['itens'], cursor)

        # Depois, enriquece a lista JÁ ORDENADA com os dados de custo
        itens_finais_para_salvar = []
        for item in itens_ordenados:
            cursor.execute("SELECT custo_medio FROM produtos WHERE id = ?", (item['id'],))
            resultado = cursor.fetchone()
            custo_a_registrar = resultado[0] if resultado else 0
            item_com_custo = item.copy()
            item_com_custo['custo_unitario'] = custo_a_registrar
            itens_finais_para_salvar.append(item_com_custo)

        itens_como_json = json.dumps(itens_finais_para_salvar)
        timestamp_atual = datetime.datetime.now().isoformat()
        valor_total = sum(item['preco'] * item['quantidade'] for item in dados_do_pedido['itens'])

        # COMANDO SQL ATUALIZADO
        cursor.execute('''
            INSERT INTO pedidos (nome_cliente, status, metodo_pagamento, modalidade, valor_total, timestamp_criacao, itens_json, fluxo_simples, senha_diaria, local_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            dados_do_pedido['nome_cliente'], 'aguardando_pagamento',
            dados_do_pedido['metodo_pagamento'], dados_do_pedido['modalidade'], # <-- Dado da modalidade extraído
            valor_total, timestamp_atual, itens_como_json, 1 if fluxo_e_simples else 0, proxima_senha,
            local_id # <-- Dado do local_id agora sendo usado
        ))

        id_do_pedido_salvo = cursor.lastrowid

        for item in dados_do_pedido['itens']:
            cursor.execute('''
                UPDATE produtos
                SET estoque_atual = estoque_atual - ?,
                    estoque_reservado = estoque_reservado + ?
                WHERE id = ?
            ''', (item['quantidade'], item['quantidade'], item['id']))

        conn.commit()

        print(f"SUCESSO: Pedido #{id_do_pedido_salvo} criado com SENHA DIÁRIA #{proxima_senha}, CUSTO REGISTRADO e estoque RESERVADO.")
        return {'id': id_do_pedido_salvo, 'senha': proxima_senha}

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
    Muda o status do pedido para 'em_producao' e adiciona um timestamp
    de início em cada item que requer preparo dentro do itens_json.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # 1. Busca o JSON de itens atual do pedido.
        cursor.execute("SELECT itens_json FROM pedidos WHERE id = ? AND status = ?", (id_do_pedido, 'aguardando_producao'))
        resultado = cursor.fetchone()

        if not resultado:
            print(f"AVISO: Pedido #{id_do_pedido} não encontrado ou não estava aguardando produção.")
            return False

        itens_atuais = json.loads(resultado[0])
        timestamp_inicio = datetime.datetime.now().isoformat()
        itens_modificados = []

        # 2. Itera sobre os itens e adiciona o timestamp naqueles que precisam.
        for item in itens_atuais:
            if item.get('requer_preparo') == 1:
                item['timestamp_inicio_item'] = timestamp_inicio
            itens_modificados.append(item)
            
        novo_itens_json = json.dumps(itens_modificados)

        # 3. Atualiza o pedido com o novo status e o JSON modificado.
        cursor.execute(
            "UPDATE pedidos SET status = ?, itens_json = ? WHERE id = ?",
            ('em_producao', novo_itens_json, id_do_pedido)
        )

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} movido para 'em produção'. Timestamps adicionados aos itens.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao iniciar preparo do pedido #{id_do_pedido}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def reiniciar_preparo_item(pedido_id, produto_id, k_posicao):
    """
    Encontra o k-ésimo item de um produto dentro de um pedido e
    atualiza seu timestamp_inicio_item para o horário atual.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        cursor.execute("SELECT itens_json FROM pedidos WHERE id = ?", (pedido_id,))
        resultado = cursor.fetchone()

        if not resultado:
            print(f"ERRO: Pedido #{pedido_id} não encontrado ao reiniciar item.")
            return False

        itens_atuais = json.loads(resultado[0])
        timestamp_novo = datetime.datetime.now().isoformat()

        # Filtra apenas os itens que correspondem ao produto e que requerem preparo.
        # A ordem é preservada da forma como os itens estão no pedido.
        itens_alvo_do_grupo = [
            item for item in itens_atuais 
            if str(item.get('id')) == str(produto_id) and item.get('requer_preparo') == 1
        ]

        # Valida se a posição 'k' é válida para o grupo encontrado.
        if not (1 <= k_posicao <= len(itens_alvo_do_grupo)):
            print(f"AVISO: Posição k={k_posicao} inválida para o item {produto_id} no pedido {pedido_id}. (Grupo tem {len(itens_alvo_do_grupo)} itens)")
            return False

        # Pega a referência exata do item a ser modificado (lembrando que k é base-1 e lista é base-0).
        item_para_reiniciar = itens_alvo_do_grupo[k_posicao - 1]

        # Atualiza o timestamp diretamente na referência do item dentro da lista original.
        item_para_reiniciar['timestamp_inicio_item'] = timestamp_novo

        novo_itens_json = json.dumps(itens_atuais)

        cursor.execute("UPDATE pedidos SET itens_json = ? WHERE id = ?", (novo_itens_json, pedido_id))
        conn.commit()

        print(f"SUCESSO: {k_posicao}º item do produto #{produto_id} no pedido #{pedido_id} reiniciado.")
        return True

    except (sqlite3.Error, IndexError) as e:
        print(f"ERRO ao reiniciar item {produto_id} (k={k_posicao}) do pedido #{pedido_id}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def entregar_pedido(id_do_pedido):
    """
    Finaliza um pedido. Lê o custo médio de cada item para registrar o custo da venda,
    dá baixa no estoque reservado e atualiza o status do pedido para 'finalizado'.
    Esta função NÃO altera mais o custo médio dos produtos.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Busca os itens do pedido para saber o que foi vendido
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

            # LÊ o custo médio do produto para registrar o custo desta venda
            cursor.execute("SELECT custo_medio FROM produtos WHERE id = ?", (id_produto,))
            res_produto = cursor.fetchone()
            custo_medio_unitario = res_produto[0] if res_produto else 0
            
            # Acumula o custo total para este pedido específico
            custo_total_dos_itens_vendidos += quantidade_vendida * custo_medio_unitario
            
            # ATUALIZA a tabela de produtos, dando baixa APENAS no estoque reservado
            cursor.execute("""
                UPDATE produtos
                SET estoque_reservado = estoque_reservado - ?
                WHERE id = ?
            """, (quantidade_vendida, id_produto))

        # Atualiza o pedido para 'finalizado' e salva o custo total daquela venda
        timestamp_final = datetime.datetime.now().isoformat()
        cursor.execute("""
            UPDATE pedidos
            SET status = 'finalizado',
                custo_total_pedido = ?,
                timestamp_finalizacao = ?
            WHERE id = ?
        """, (custo_total_dos_itens_vendidos, timestamp_final, id_do_pedido))

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} finalizado e estoque baixado. O custo médio dos produtos não foi alterado.")
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

def obter_dados_relatorio(data_inicio, data_fim, local_id=None):
    """
    Busca e calcula todos os dados para o relatório de fechamento
    dentro de um intervalo de datas, aplicando as taxas de pagamento.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # PASSO 1: Obter as taxas de configuração primeiro.
        taxas = {}
        cursor.execute("SELECT chave, valor FROM configuracoes")
        for chave, valor in cursor.fetchall():
            taxas[chave] = valor

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
        lucro_estimado = 0  # Inicializa o lucro

        # PASSO 2: Loop detalhado para calcular o lucro líquido
        for p in pedidos_finalizados:
            lucro_bruto_pedido = p['valor_total'] - (p['custo_total_pedido'] or 0)
            
            # Descobre a taxa para este método de pagamento
            taxa_aplicada = 0
            if p['metodo_pagamento'] == 'cartao_credito':
                taxa_aplicada = taxas.get('taxa_credito', 0.0)
            elif p['metodo_pagamento'] == 'cartao_debito':
                taxa_aplicada = taxas.get('taxa_debito', 0.0)
            elif p['metodo_pagamento'] == 'pix':
                taxa_aplicada = taxas.get('taxa_pix', 0.0)
            
            # Calcula o valor do desconto
            desconto_taxa = p['valor_total'] * (taxa_aplicada / 100.0)
            
            # Calcula o lucro líquido do pedido e o acumula
            lucro_liquido_pedido = lucro_bruto_pedido - desconto_taxa
            lucro_estimado += lucro_liquido_pedido

        pedidos_realizados = len(pedidos_finalizados)
        ticket_medio = faturamento_bruto / pedidos_realizados if pedidos_realizados > 0 else 0
        total_itens_vendidos = sum(sum(item['quantidade'] for item in json.loads(p['itens_json'])) for p in pedidos_finalizados)
        media_itens_pedido = total_itens_vendidos / pedidos_realizados if pedidos_realizados > 0 else 0
        valor_perdas = 0
        
        
        # --- DADOS PARA GRÁFICOS E TABELAS ---
        vendas_por_pagamento = {'pix': 0, 'cartao_credito': 0, 'cartao_debito': 0, 'dinheiro': 0}
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

def obter_tempos_por_produto_id(produto_id):
    """
    Busca os tempos de preparo (mal, ponto, bem) para um produto específico.
    """
    tempos = {'mal': 0, 'ponto': 0, 'bem': 0}
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("SELECT ponto, tempo_em_segundos FROM tempos_preparo WHERE produto_id = ?", (produto_id,))
        for row in cursor.fetchall():
            ponto, tempo_em_segundos = row
            if ponto in tempos:
                # Converte segundos para minutos para exibição na interface
                tempos[ponto] = tempo_em_segundos / 60
        return tempos
    except sqlite3.Error as e:
        print(f"Erro ao obter tempos para o produto {produto_id}: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def salvar_tempos_preparo(produto_id, tempos_data):
    """
    Salva ou atualiza os tempos de preparo para um produto.
    Usa a lógica 'UPSERT' (INSERT OR REPLACE) e itera sobre
    qualquer dicionário de tempos recebido.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        for ponto, minutos_str in tempos_data.items():
            # Verifica se o valor de minutos não é nulo ou uma string vazia
            if minutos_str is not None and str(minutos_str).strip() != '':
                minutos = float(minutos_str)
                tempo_em_segundos = int(minutos * 60)
                
                # Se o tempo for zero ou negativo, remove o registro do banco
                if tempo_em_segundos <= 0:
                    cursor.execute(
                        "DELETE FROM tempos_preparo WHERE produto_id = ? AND ponto = ?",
                        (produto_id, ponto)
                    )
                else:
                    # Senão, insere ou atualiza o tempo
                    cursor.execute('''
                        INSERT OR REPLACE INTO tempos_preparo (produto_id, ponto, tempo_em_segundos)
                        VALUES (?, ?, ?)
                    ''', (produto_id, ponto, tempo_em_segundos))
        conn.commit()
        return True
    except (ValueError, TypeError) as e:
        print(f"Erro de conversão de tipo ao salvar tempos para o produto {produto_id}: {e}")
        return False
    except sqlite3.Error as e:
        print(f"Erro de banco de dados ao salvar tempos para o produto {produto_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_dados_produto(id_produto, nome, descricao, foto_url, categoria_id, requer_preparo):
    """
    Atualiza os dados principais de um produto existente (nome, categoria, flag de preparo).
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Comando SQL para atualizar os dados do produto com base no ID
        cursor.execute('''
            UPDATE produtos 
            SET nome = ?,
                descricao = ?,
                foto_url = ?,
                categoria_id = ?,
                requer_preparo = ?
            WHERE id = ?
        ''', (nome, descricao, foto_url, categoria_id, requer_preparo, id_produto))

        conn.commit()
        print(f"Dados do produto ID {id_produto} atualizados com sucesso.")
        return True

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao atualizar os dados do produto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_tempo_preparo_especifico(produto_id, ponto):
    """
    Busca no banco de dados o tempo de preparo em segundos para um 
    produto e um ponto de cozimento específicos.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT tempo_em_segundos 
            FROM tempos_preparo 
            WHERE produto_id = ? AND ponto = ?
        """, (produto_id, ponto))
        
        resultado = cursor.fetchone()

        # Se encontrar um tempo, retorna os segundos. Senão, retorna 0.
        return resultado[0] if resultado else 0

    except sqlite3.Error as e:
        print(f"Erro ao obter tempo de preparo para produto {produto_id} e ponto {ponto}: {e}")
        return 0 # Retorna 0 em caso de erro
    finally:
        if conn:
            conn.close()

# gerenciador_db.py

def obter_proximo_id_pedido():
    """
    Consulta o banco de dados para determinar qual será o próximo ID
    da tabela de pedidos. Retorna 1 se a tabela estiver vazia.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        # A tabela sqlite_sequence guarda o último ID usado em tabelas com AUTOINCREMENT
        cursor.execute("SELECT seq FROM sqlite_sequence WHERE name = 'pedidos'")
        resultado = cursor.fetchone()
        
        if resultado:
            return resultado[0] + 1
        else:
            # Se não houver sequência (tabela vazia), o próximo ID será 1
            return 1
            
    except sqlite3.Error as e:
        print(f"ERRO ao obter o próximo ID do pedido: {e}")
        return "?" # Retorna um placeholder em caso de erro
    finally:
        if conn:
            conn.close()

def obter_pedido_por_id(id_do_pedido):
    """
    Busca um único pedido no banco de dados pelo seu ID.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        # Usamos a row_factory para que o resultado venha como um dicionário
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM pedidos WHERE id = ?", (id_do_pedido,))
        
        pedido = cursor.fetchone()
        
        # Retorna o pedido encontrado (ou None se não existir)
        return dict(pedido) if pedido else None

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter o pedido por ID: {e}")
        return None
    finally:
        if conn:
            conn.close()

def pular_pedido_para_retirada(id_do_pedido):
    """
    Muda o status de um pedido de 'aguardando_producao' diretamente para
    'aguardando_retirada', para ser usado em fluxos simples.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE pedidos SET status = ? WHERE id = ? AND status = ?",
            ('aguardando_retirada', id_do_pedido, 'aguardando_producao')
        )

        if cursor.rowcount == 0:
            print(f"AVISO: Pedido #{id_do_pedido} não pôde ser pulado para retirada (status pode não ser 'aguardando_producao').")
            return False

        conn.commit()
        print(f"SUCESSO: Pedido #{id_do_pedido} pulou para 'aguardando retirada'.")
        return True

    except sqlite3.Error as e:
        print(f"ERRO ao pular pedido para retirada #{id_do_pedido}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def obter_proxima_senha_diaria():
    """
    Calcula a próxima senha diária com base no horário de trabalho que
    começa às 5h da manhã.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        agora = datetime.datetime.now()
        horario_corte = agora.replace(hour=5, minute=0, second=0, microsecond=0)

        # Define a data de início da busca pela última senha
        if agora < horario_corte:
            # Regra 1 (Antes das 5h): Busca nas últimas 8 horas
            data_inicio_busca = agora - datetime.timedelta(hours=8)
        else:
            # Regra 2 (Depois das 5h): Busca a partir das 5h de hoje
            data_inicio_busca = horario_corte

        # Busca a maior senha usada desde o início do ciclo de trabalho
        cursor.execute(
            "SELECT MAX(senha_diaria) FROM pedidos WHERE timestamp_criacao >= ?",
            (data_inicio_busca.isoformat(),)
        )
        resultado = cursor.fetchone()

        # Calcula a próxima senha
        if resultado and resultado[0] is not None:
            return resultado[0] + 1
        else:
            return 1 # Se não houver pedidos no ciclo, começa do 1

    except sqlite3.Error as e:
        print(f"ERRO ao obter a próxima senha diária: {e}")
        return 1 # Retorna 1 como segurança em caso de erro
    finally:
        if conn:
            conn.close()

# === NOVAS FUNÇÕES PARA GERENCIAR ACOMPANHAMENTOS ===

def adicionar_acompanhamento(nome):
    """Adiciona um novo acompanhamento à tabela."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO acompanhamentos (nome) VALUES (?)", (nome,))
        conn.commit()
        print(f"Acompanhamento '{nome}' adicionado com sucesso.")
        return True
    except sqlite3.IntegrityError:
        print(f"Erro: O acompanhamento '{nome}' já existe.")
        return False
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar o acompanhamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_todos_acompanhamentos():
    """Busca todos os acompanhamentos (visíveis e ocultos) para a tela de gestão."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, is_visivel FROM acompanhamentos ORDER BY nome")

        acompanhamentos_tuplas = cursor.fetchall()
        lista_final = []
        for tupla in acompanhamentos_tuplas:
            lista_final.append({'id': tupla[0], 'nome': tupla[1], 'is_visivel': tupla[2]})

        return lista_final
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os acompanhamentos: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_acompanhamentos_visiveis():
    """Busca apenas os acompanhamentos visíveis para a tela do cliente."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM acompanhamentos WHERE is_visivel = 1 ORDER BY nome")

        acompanhamentos_tuplas = cursor.fetchall()
        lista_final = []
        for tupla in acompanhamentos_tuplas:
            lista_final.append({'id': tupla[0], 'nome': tupla[1]})

        return lista_final
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os acompanhamentos visíveis: {e}")
        return []
    finally:
        if conn:
            conn.close()

def excluir_acompanhamento(id_acompanhamento):
    """Exclui um acompanhamento da tabela."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM acompanhamentos WHERE id = ?", (id_acompanhamento,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao excluir o acompanhamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def toggle_visibilidade_acompanhamento(id_acompanhamento):
    """Alterna o status de visibilidade de um acompanhamento."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        # Esta sintaxe SQL alterna o valor de is_visivel entre 0 e 1 de forma eficiente
        cursor.execute("UPDATE acompanhamentos SET is_visivel = CASE WHEN is_visivel = 1 THEN 0 ELSE 1 END WHERE id = ?", (id_acompanhamento,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao alternar a visibilidade do acompanhamento: {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_configuracoes():
    """
    Busca todas as configurações da tabela 'configuracoes' e retorna como um dicionário.
    """
    configs = {}
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("SELECT chave, valor FROM configuracoes")
        for chave, valor in cursor.fetchall():
            configs[chave] = valor
        return configs
    except sqlite3.Error as e:
        print(f"ERRO ao obter configurações: {e}")
        # Retorna um dicionário vazio em caso de erro para não quebrar o sistema
        return {}
    finally:
        if conn:
            conn.close()

def salvar_configuracoes(novas_taxas):
    """
    Recebe um dicionário de taxas e as salva no banco de dados.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        for chave, valor in novas_taxas.items():
            # Usamos UPDATE para alterar os valores existentes com base na chave primária
            cursor.execute("UPDATE configuracoes SET valor = ? WHERE chave = ?", (valor, chave))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"ERRO ao salvar configurações: {e}")
        return False
    finally:
        if conn:
            conn.close()

# === NOVAS FUNÇÕES PARA GERENCIAR LOCAIS ===

def adicionar_local(nome_local):
    """Adiciona um novo local à tabela 'locais'."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO locais (nome) VALUES (?)", (nome_local,))
        conn.commit()
        print(f"Local '{nome_local}' adicionado com sucesso.")
        return True
    except sqlite3.IntegrityError:
        print(f"Erro: O local '{nome_local}' já existe.")
        return False
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar o local: {e}")
        return False
    finally:
        if conn:
            conn.close()

def obter_todos_locais():
    """Busca todos os locais cadastrados, ordenados por nome."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM locais ORDER BY nome")
        locais_tuplas = cursor.fetchall()
        
        # Converte a lista de tuplas para uma lista de dicionários para a API
        locais_lista = [{'id': tupla[0], 'nome': tupla[1]} for tupla in locais_tuplas]
        
        return locais_lista
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os locais: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_pedidos_finalizados_periodo(inicio, fim, local_id):
    """
    Busca no banco de dados todos os pedidos com status 'finalizado'
    dentro de um intervalo de datas e, opcionalmente, filtrando por local.

    Args:
        inicio (str): Timestamp ISO 8601 do início do período.
        fim (str): Timestamp ISO 8601 do fim do período.
        local_id (str ou int): O ID do local ou a string 'todos'.

    Returns:
        list: Uma lista de dicionários, onde cada dicionário é um pedido.
              Retorna uma lista vazia em caso de erro.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row  # Isso faz o fetch retornar dicionários
        cursor = conn.cursor()

        # Constrói a query base
        query = """
            SELECT * FROM pedidos
            WHERE status = 'finalizado' AND timestamp_finalizacao BETWEEN ? AND ?
        """
        params = [inicio, fim]

        # Adiciona o filtro de local dinamicamente se não for 'todos'
        if local_id != 'todos':
            query += " AND local_id = ?"
            params.append(int(local_id))
        
        # Adiciona ordenação para consistência
        query += " ORDER BY timestamp_finalizacao ASC"

        cursor.execute(query, params)
        resultados = cursor.fetchall()

        # Converte os resultados (Row objects) para dicionários Python puros
        pedidos_finalizados = [dict(row) for row in resultados]
        
        return pedidos_finalizados

    except sqlite3.Error as e:
        print(f"ERRO ao obter pedidos finalizados por período: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_mapa_produtos_analytics():
    """
    Busca todos os produtos e cria um mapa de consulta rápida para o módulo de analytics.
    Otimizado para evitar múltiplas consultas ao banco de dados.

    Returns:
        dict: Um dicionário onde a chave é o ID do produto e o valor é um
              dicionário com detalhes do produto, como {'nome': ..., 'categoria': ..., 'custo_medio': ...}.
              Retorna um dicionário vazio em caso de erro.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # A consulta agora também busca o custo_medio de cada produto
        query = """
            SELECT
                p.id,
                p.nome,
                p.custo_medio,
                c.nome as categoria_nome
            FROM produtos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
        """
        cursor.execute(query)
        resultados = cursor.fetchall()

        # Transforma a lista de resultados em um dicionário para busca rápida (mapa)
        mapa_produtos = {
            row['id']: {
                'nome': row['nome'],
                'categoria': row['categoria_nome'],
                'custo_medio': row['custo_medio']
            }
            for row in resultados
        }
        
        return mapa_produtos

    except sqlite3.Error as e:
        print(f"ERRO ao criar mapa de produtos para analytics: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def excluir_local(id_local):
    """
    Exclui um local da tabela.
    Nota: Isso falhará se o local estiver sendo usado por algum pedido,
    devido à restrição de chave estrangeira, o que protege a integridade dos dados.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM locais WHERE id = ?", (id_local,))
        conn.commit()
        # Verifica se alguma linha foi realmente deletada
        if cursor.rowcount > 0:
            print(f"Local com ID {id_local} excluído com sucesso.")
            return True
        else:
            print(f"Nenhum local com ID {id_local} encontrado para excluir.")
            return False
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao excluir o local: {e}")
        return False
    finally:
        if conn:
            conn.close()

def atualizar_categoria_produto(id_produto, nova_categoria_id):
    """Altera a categoria de um produto específico no banco de dados."""
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Comando SQL para atualizar a categoria_id do produto
        cursor.execute("""
            UPDATE produtos 
            SET categoria_id = ? 
            WHERE id = ?
        """, (nova_categoria_id, id_produto))

        conn.commit()
        print(f"Produto ID {id_produto} movido para a categoria ID {nova_categoria_id}.")
        return True
    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao atualizar a categoria do produto: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def obter_entradas_estoque_por_produto(data_fim):
    """
    Calcula o total de movimentações de entrada (compras, ajustes positivos/negativos)
    para cada produto até uma data específica.

    Args:
        data_fim (str): Timestamp ISO 8601 do fim do período de contagem.

    Returns:
        dict: Um dicionário no formato {id_produto: total_movimentado}.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        query = """
            SELECT id_produto, SUM(quantidade_comprada)
            FROM entradas_de_estoque
            WHERE data_entrada <= ?
            GROUP BY id_produto
        """
        cursor.execute(query, (data_fim,))
        # Converte a lista de tuplas em um dicionário para fácil acesso
        return {row[0]: row[1] for row in cursor.fetchall()}

    except sqlite3.Error as e:
        print(f"ERRO ao obter entradas de estoque agregadas: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def obter_saidas_venda_por_produto(data_fim):
    """
    Calcula o total de saídas por venda para cada produto, analisando
    os pedidos finalizados até uma data específica.

    Args:
        data_fim (str): Timestamp ISO 8601 do fim do período de contagem.

    Returns:
        dict: Um dicionário no formato {id_produto: total_vendido}.
    """
    saidas_por_produto = {}
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        query = """
            SELECT itens_json FROM pedidos
            WHERE status = 'finalizado' AND timestamp_finalizacao <= ?
        """
        cursor.execute(query, (data_fim,))
        
        for row in cursor.fetchall():
            try:
                itens_do_pedido = json.loads(row[0])
                for item in itens_do_pedido:
                    produto_id = item['id']
                    quantidade = item.get('quantidade', 0)
                    saidas_por_produto[produto_id] = saidas_por_produto.get(produto_id, 0) + quantidade
            except (json.JSONDecodeError, TypeError):
                # Ignora pedidos com JSON malformado, como planejado
                continue
        
        return saidas_por_produto

    except sqlite3.Error as e:
        print(f"ERRO ao obter saídas por venda agregadas: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def obter_perdas_periodo(inicio, fim):
    """
    Busca todos os registros de perdas (movimentações negativas com custo zero)
    dentro de um período.

    Args:
        inicio (str): Timestamp ISO 8601 do início do período.
        fim (str): Timestamp ISO 8601 do fim do período.

    Returns:
        list: Uma lista de dicionários, onde cada um representa uma perda.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = """
            SELECT id_produto, quantidade_comprada
            FROM entradas_de_estoque
            WHERE quantidade_comprada < 0
              AND custo_unitario_compra = 0
              AND data_entrada BETWEEN ? AND ?
        """
        cursor.execute(query, (inicio, fim))
        # Retorna a lista de perdas já no formato de dicionário
        return [dict(row) for row in cursor.fetchall()]

    except sqlite3.Error as e:
        print(f"ERRO ao obter perdas do período: {e}")
        return []
    finally:
        if conn:
            conn.close()

def _normalizar_e_ordenar_itens(itens_recebidos, cursor):
    """
    Garante que uma lista de itens de pedido esteja ordenada pela chave canônica.
    Chave: categoria_ordem ASC, produto_ordem ASC, id ASC, uid ASC.
    Esta função não existe no arquivo original e precisará ser criada.
    O cursor é necessário para buscar dados de ordenação de produtos legados, se necessário.
    """
    # Lógica a ser implementada na Tarefa 2
    print("Aviso: _normalizar_e_ordenar_itens ainda não implementada.")
    return itens_recebidos # Retorna a lista original por enquanto

def obter_entradas_positivas_periodo(inicio, fim):
    """
    Busca o total de entradas de estoque (somente quantidades positivas, i.e., compras)
    para cada produto dentro de um período específico.

    Args:
        inicio (str): Timestamp ISO 8601 do início do período.
        fim (str): Timestamp ISO 8601 do fim do período.

    Returns:
        dict: Um dicionário no formato {id_produto: total_comprado}.
    """
    conn = None
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()
        query = """
            SELECT id_produto, SUM(quantidade_comprada)
            FROM entradas_de_estoque
            WHERE data_entrada BETWEEN ? AND ?
              AND quantidade_comprada > 0
            GROUP BY id_produto
        """
        cursor.execute(query, (inicio, fim))
        # Converte a lista de tuplas em um dicionário para fácil acesso
        return {row[0]: row[1] for row in cursor.fetchall()}

    except sqlite3.Error as e:
        print(f"ERRO ao obter entradas positivas do período: {e}")
        return {}
    finally:
        if conn:
            conn.close()