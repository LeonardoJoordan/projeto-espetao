from flask import Flask, render_template, request, redirect, url_for
import gerenciador_db

app = Flask(__name__)

@app.route('/cliente', methods=['GET', 'POST'])
def tela_cliente():
    """
    Esta rota representa a tela do cliente.
    'GET' é para quando o cliente abre a tela.
    'POST' é para quando o cliente envia o formulário de novo pedido.
    """
    if request.method == 'POST':
        # 1. Coletar os dados do formulário (que ainda não existe)
        nome_cliente = request.form.get('nome_cliente', 'Cliente Padrão')
        
        # Simulação dos itens do pedido
        itens_pedido = [
            {'item': 'Espeto de Carne', 'quantidade': 1},
            {'item': 'Coca-Cola', 'quantidade': 1}
        ]
        metodo_pagamento = 'dinheiro'

        # 2. Chamar a função do nosso gerenciador (o "contrato")
        novo_id = gerenciador_db.criar_novo_pedido(nome_cliente, itens_pedido, metodo_pagamento)
        
        print(f"DEBUG: Pedido criado com ID: {novo_id}")

        # 3. Redirecionar para uma página de confirmação (que ainda não existe)
        # Por enquanto, apenas redirecionamos de volta para a mesma tela.
        return redirect(url_for('tela_cliente'))

    # Se o método for GET, apenas mostramos a página (que ainda está vazia)
    return render_template('cliente.html')

# --- NOVA ROTA DA COZINHA ---
@app.route('/cozinha')
def tela_cozinha():
    """
    Esta rota representa a tela da cozinha.
    Ela busca os pedidos que precisam de atenção e os envia para o template.
    """
    # 1. Definir quais status a cozinha quer ver
    status_de_interesse = ['recebido']

    # 2. Chamar a função do nosso gerenciador (o "contrato")
    pedidos_para_cozinha = gerenciador_db.obter_pedidos_por_status(status_de_interesse)
    
    print(f"DEBUG: Pedidos encontrados para a cozinha: {pedidos_para_cozinha}")

    # 3. Enviar a lista de pedidos para o template 'cozinha.html' renderizar
    return render_template('cozinha.html', pedidos=pedidos_para_cozinha)

# Em app.py

@app.route('/produtos', methods=['GET'])
def tela_produtos():
    """
    Esta rota representa a tela de gestão de produtos.
    Ela busca os produtos, AGRUPA-OS POR CATEGORIA, e os envia para o template.
    """
    # DADOS DE TESTE (os mesmos de antes)
    produtos_cadastrados = [
        {'id': 1, 'nome': 'Espeto de Carne', 'categoria': 'Espetinhos', 'preco_venda': 12.00, 'custo_medio': 6.50, 'lucro': 5.50, 'estoque': 50},
        {'id': 2, 'nome': 'Coca-Cola Lata', 'categoria': 'Bebidas', 'preco_venda': 5.00, 'custo_medio': 2.80, 'lucro': 2.20, 'estoque': 100},
        {'id': 3, 'nome': 'Pão de Alho', 'categoria': 'Acompanhamentos', 'preco_venda': 7.00, 'custo_medio': 3.00, 'lucro': 4.00, 'estoque': 30},
        {'id': 4, 'nome': 'Espeto de Frango', 'categoria': 'Espetinhos', 'preco_venda': 10.00, 'custo_medio': 5.00, 'lucro': 5.00, 'estoque': 40}
    ]
    categorias_cadastradas = [
        {'id': 1, 'nome': 'Espetinhos'},
        {'id': 2, 'nome': 'Bebidas'},
        {'id': 3, 'nome': 'Acompanhamentos'}
    ]

    # --- LÓGICA DE AGRUPAMENTO ---
    # 1. Cria um dicionário vazio para guardar os dados agrupados.
    produtos_agrupados = {}

    # 2. Itera sobre a lista de categorias para inicializar as chaves do dicionário.
    for categoria in categorias_cadastradas:
        produtos_agrupados[categoria['nome']] = []

    # 3. Itera sobre a lista de produtos e os coloca na categoria correta.
    for produto in produtos_cadastrados:
        categoria_do_produto = produto['categoria']
        if categoria_do_produto in produtos_agrupados:
            produtos_agrupados[categoria_do_produto].append(produto)
    
    # Envia os dados AGRUPADOS para o template
    return render_template('produtos.html', produtos_agrupados=produtos_agrupados, categorias=categorias_cadastradas)

@app.route('/adicionar_categoria', methods=['POST'])
def adicionar_categoria():
    """
    CASCA da rota para adicionar uma nova categoria.
    A lógica será implementada quando conectarmos ao banco de dados.
    """
    nome_nova_categoria = request.form.get('nome_categoria')
    print(f"DEBUG: Tentativa de adicionar categoria: {nome_nova_categoria}")
    
    # Redireciona de volta para a página de produtos
    return redirect(url_for('tela_produtos'))

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    """
    CASCA da rota para adicionar um novo produto.
    A lógica será implementada quando conectarmos ao banco de dados.
    """
    dados_novo_produto = {
        'nome': request.form.get('nome_produto'),
        'categoria': request.form.get('categoria_produto'),
        'preco': request.form.get('preco_venda'),
        'lucro': request.form.get('lucro_unidade'),
        'estoque': request.form.get('estoque'),
    }
    print(f"DEBUG: Tentativa de adicionar produto: {dados_novo_produto}")

    # Redireciona de volta para a página de produtos
    return redirect(url_for('tela_produtos'))

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))

if __name__ == '__main__':
    # O 'debug=True' faz o servidor reiniciar automaticamente quando salvamos o arquivo.
    app.run(debug=True, host='0.0.0.0', port=5001)