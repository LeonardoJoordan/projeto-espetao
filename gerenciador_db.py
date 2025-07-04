import datetime

# Cardápio com os preços dos itens
CARDAPIO = {
    'Espeto de Carne': 10.00,
    'Espeto de Frango': 9.00,
    'Coca-Cola': 5.00,
    'Pao de Alho': 7.00
}

# Voltando ao estado original: lista de pedidos vazia.
PEDIDOS = []
_proximo_id = 1

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