import sqlite3
import datetime

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
    Busca e retorna todas as categorias cadastradas no banco de dados.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        # conn.row_factory = sqlite3.Row nos permitiria acessar colunas por nome
        # mas vamos fazer manualmente para o aprendizado ser mais claro.
        cursor = conn.cursor()

        cursor.execute("SELECT id, nome FROM categorias ORDER BY nome")
        
        # fetchall() busca todas as linhas do resultado da consulta
        categorias_tuplas = cursor.fetchall()

        # Converte a lista de tuplas em uma lista de dicionários
        categorias_lista = []
        for tupla in categorias_tuplas:
            categorias_lista.append({'id': tupla[0], 'nome': tupla[1]})
        
        return categorias_lista

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter as categorias: {e}")
        return [] # Retorna uma lista vazia em caso de erro
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
    # Calcula o valor total do pedido
    for item in itens_pedido:
        preco_unitario = CARDAPIO.get(item['item'], 0) # Pega o preço do cardápio, ou 0 se não encontrar
        valor_total += preco_unitario * item['quantidade']

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
    e calcula o custo médio e o lucro para cada um.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # Comando SQL que busca os produtos e "cruza" com a tabela de categorias
        # para pegar o nome da categoria, em vez de só o ID.
        cursor.execute('''
            SELECT p.id, p.nome, p.preco_venda, p.estoque_atual, p.custo_total_do_estoque, c.nome as categoria_nome
            FROM produtos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            ORDER BY c.nome, p.nome
        ''')
        
        produtos_tuplas = cursor.fetchall()

        # Converte a lista de tuplas em uma lista de dicionários, já fazendo os cálculos
        produtos_lista = []
        for tupla in produtos_tuplas:
            id_produto, nome, preco_venda, estoque, custo_total, categoria = tupla
            
            # Lógica para calcular o custo médio e o lucro
            if estoque > 0:
                custo_medio = custo_total / estoque
                lucro = preco_venda - custo_medio
            else:
                custo_medio = 0
                lucro = preco_venda # Ou 0, dependendo da regra de negócio

            produtos_lista.append({
                'id': id_produto,
                'nome': nome,
                'preco_venda': preco_venda,
                'estoque': estoque,
                'custo_medio': custo_medio,
                'lucro': lucro,
                'categoria': categoria
            })
        
        return produtos_lista

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao obter os produtos: {e}")
        return []
    finally:
        if conn:
            conn.close()

def obter_pedidos_por_status(lista_de_status):
    """
    Encontra e retorna todos os pedidos que correspondem a qualquer um
    dos status na lista fornecida.
    """
    pedidos_encontrados = []
    for pedido in PEDIDOS:
        if pedido['status'] in lista_de_status:
            pedidos_encontrados.append(pedido)
    
    return pedidos_encontrados

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

def adicionar_estoque(id_produto, quantidade_adicionada, custo_da_nova_compra):
    """
    Adiciona novo estoque a um produto existente, recalcula o custo total
    e registra a entrada no histórico.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # PASSO 1: Ler o estado atual do produto
        cursor.execute("SELECT estoque_atual, custo_total_do_estoque FROM produtos WHERE id = ?", (id_produto,))
        resultado = cursor.fetchone()

        if resultado:
            estoque_atual, custo_total_atual = resultado

            # PASSO 2: Calcular os novos valores em Python
            novo_estoque = estoque_atual + quantidade_adicionada
            custo_desta_compra = quantidade_adicionada * custo_da_nova_compra
            novo_custo_total = custo_total_atual + custo_desta_compra

            # PASSO 3: Atualizar o produto com os novos valores
            cursor.execute('''
                UPDATE produtos 
                SET estoque_atual = ?, custo_total_do_estoque = ?
                WHERE id = ?
            ''', (novo_estoque, novo_custo_total, id_produto))

            # PASSO 4: Registrar esta compra no histórico
            data_atual = datetime.datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO entradas_de_estoque (id_produto, quantidade_comprada, custo_unitario_compra, data_entrada)
                VALUES (?, ?, ?, ?)
            ''', (id_produto, quantidade_adicionada, custo_da_nova_compra, data_atual))

            conn.commit()
            print(f"Estoque do produto ID {id_produto} atualizado com sucesso.")
            return True
        else:
            print(f"Erro: Produto com ID {id_produto} não encontrado.")
            return False

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar estoque: {e}")
        return False
    finally:
        if conn:
            conn.close()

def adicionar_estoque(id_produto, quantidade_adicionada, custo_da_nova_compra):
    """
    Adiciona novo estoque a um produto existente, recalcula o custo total
    e registra a entrada no histórico.
    """
    try:
        conn = sqlite3.connect(NOME_BANCO_DADOS)
        cursor = conn.cursor()

        # PASSO A: Ler o estado atual do produto
        cursor.execute("SELECT estoque_atual, custo_total_do_estoque FROM produtos WHERE id = ?", (id_produto,))
        resultado = cursor.fetchone()

        if resultado:
            estoque_atual, custo_total_atual = resultado

            # PASSO B: Calcular os novos valores em Python
            novo_estoque = estoque_atual + quantidade_adicionada
            custo_desta_compra = quantidade_adicionada * custo_da_nova_compra
            novo_custo_total = custo_total_atual + custo_desta_compra

            # PASSO C: Atualizar o produto com os novos valores
            cursor.execute('''
                UPDATE produtos 
                SET estoque_atual = ?, custo_total_do_estoque = ?
                WHERE id = ?
            ''', (novo_estoque, novo_custo_total, id_produto))

            # PASSO D: Registrar esta compra no histórico (entradas_de_estoque)
            data_atual = datetime.datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO entradas_de_estoque (id_produto, quantidade_comprada, custo_unitario_compra, data_entrada)
                VALUES (?, ?, ?, ?)
            ''', (id_produto, quantidade_adicionada, custo_da_nova_compra, data_atual))

            conn.commit()
            print(f"Estoque do produto ID {id_produto} atualizado com sucesso.")
            return True
        else:
            print(f"Erro: Produto com ID {id_produto} não encontrado.")
            return False

    except sqlite3.Error as e:
        print(f"Ocorreu um erro ao adicionar estoque: {e}")
        return False
    finally:
        if conn:
            conn.close()