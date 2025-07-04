import datetime

# Cardápio com os preços dos itens
CARDAPIO = {
    'Espeto de Carne': 10.00,
    'Espeto de Frango': 9.00,
    'Coca-Cola': 5.00,
    'Pao de Alho': 7.00
}

# DADOS DE TESTE PARA A TELA DA COZINHA
PEDIDOS = [
    {'id': 1, 'nome_cliente': 'Carlos', 'itens': [{'item': 'Espeto de Carne', 'quantidade': 2}], 'metodo_pagamento': 'pix', 'status': 'recebido', 'timestamp': '2025-07-04T00:30:00', 'valor_total': 20.00},
    {'id': 2, 'nome_cliente': 'Juliana', 'itens': [{'item': 'Espeto de Frango', 'quantidade': 1}, {'item': 'Coca-Cola', 'quantidade': 1}], 'metodo_pagamento': 'dinheiro', 'status': 'recebido', 'timestamp': '2025-07-04T00:32:00', 'valor_total': 14.00},
    {'id': 3, 'nome_cliente': 'Família Souza', 'itens': [{'item': 'Pao de Alho', 'quantidade': 3}, {'item': 'Espeto de Carne', 'quantidade': 4}], 'metodo_pagamento': 'dinheiro', 'status': 'recebido', 'timestamp': '2025-07-04T00:35:00', 'valor_total': 61.00}
]
_proximo_id = 4 # Importante: ajustar para o próximo ID ser 4

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