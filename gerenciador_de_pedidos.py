import datetime

# nosso "banco de dados" em memória. Uma lista para guardar os pedidos.
PEDIDOS = []
_proximo_id = 1

def criar_novo_pedido(nome_cliente, itens_pedido, metodo_pagamento):
    """
    Cria um novo pedido, adiciona um status inicial e um timestamp,
    e o armazena na lista de PEDIDOS.
    """
    global _proximo_id

    # 1. Montar o dicionário completo do pedido
    novo_pedido = {
        'id': _proximo_id,
        'nome_cliente': nome_cliente,
        'itens': itens_pedido,
        'metodo_pagamento': metodo_pagamento,
        'status': 'recebido',  # Status inicial do pedido
        'timestamp': datetime.datetime.now().isoformat() # Registra quando o pedido foi criado
    }

    # 2. Adicionar o novo pedido à nossa lista "banco de dados"
    PEDIDOS.append(novo_pedido)

    # 3. Imprimir o estado atual da lista de pedidos para nosso controle
    print("\n--- BASE DE DADOS ATUALIZADA ---")
    for pedido in PEDIDOS:
        print(pedido)
    print("--------------------------------\n")

    # 4. Incrementar o ID para o próximo pedido e retornar o ID do pedido criado
    _proximo_id += 1
    return novo_pedido['id']

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