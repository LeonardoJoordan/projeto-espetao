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
    Ela busca os produtos e categorias REAIS do banco de dados e os agrupa.
    """
    # --- BUSCANDO DADOS 100% REAIS DO BANCO DE DADOS ---
    categorias_reais = gerenciador_db.obter_todas_categorias()
    produtos_reais = gerenciador_db.obter_todos_produtos() # Removemos a lista de teste!
    
    # --- Lógica de Agrupamento ---
    produtos_agrupados = {}
    for categoria in categorias_reais:
        produtos_agrupados[categoria['nome']] = []

    # Agora o loop usa a lista de produtos reais do banco
    for produto in produtos_reais:
        # produto['categoria'] agora já vem com o nome da categoria, graças ao JOIN
        categoria_do_produto = produto['categoria']
        if categoria_do_produto in produtos_agrupados:
            produtos_agrupados[categoria_do_produto].append(produto)
    
    # Envia os dados REAIS e AGRUPADOS para o template
    return render_template('produtos.html', produtos_agrupados=produtos_agrupados, categorias=categorias_reais)

@app.route('/adicionar_categoria', methods=['POST'])
def adicionar_categoria():
    """
    Rota para adicionar uma nova categoria.
    Recebe os dados do formulário e chama a função do gerenciador_db.
    """
    # 1. Pega o nome da categoria enviado pelo formulário
    nome_nova_categoria = request.form.get('nome_categoria')

    # 2. Verifica se o nome não está vazio
    if nome_nova_categoria:
        # 3. Chama a função "Trabalhadora" do nosso especialista em banco de dados
        gerenciador_db.adicionar_nova_categoria(nome_nova_categoria)
    
    # 4. Redireciona o usuário de volta para a página de produtos
    return redirect(url_for('tela_produtos'))

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    """
    Rota para adicionar um novo produto.
    Pega os dados do formulário e chama a função do gerenciador_db.
    """
    try:
        # Pega os dados do formulário e converte para os tipos corretos
        nome = request.form.get('nome_produto')
        categoria_id = int(request.form.get('categoria_produto'))
        preco_venda = float(request.form.get('preco_venda'))
        preco_compra = float(request.form.get('preco_compra'))
        quantidade = int(request.form.get('quantidade'))

        # Validação simples para garantir que os dados essenciais foram enviados
        if nome and preco_venda and preco_compra and quantidade:
            gerenciador_db.adicionar_novo_produto(nome, preco_venda, quantidade, preco_compra, categoria_id)

    except (ValueError, TypeError) as e:
        print(f"Erro ao converter dados do formulário: {e}")

    # Redireciona de volta para a página de produtos, que agora mostrará o novo item
    return redirect(url_for('tela_produtos'))

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))

if __name__ == '__main__':
    # O 'debug=True' faz o servidor reiniciar automaticamente quando salvamos o arquivo.
    app.run(debug=True, host='0.0.0.0', port=5001)