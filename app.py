from flask import Flask, render_template, request, redirect, url_for, jsonify
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
    produtos_reais = gerenciador_db.obter_todos_produtos()
    
    # --- Lógica de Agrupamento COM IDs ---
    produtos_agrupados = {}
    for categoria in categorias_reais:
        produtos_agrupados[categoria['nome']] = {
            'id': categoria['id'],
            'produtos': []
        }

    # Agora o loop usa a lista de produtos reais do banco
    for produto in produtos_reais:
        categoria_do_produto = produto['categoria']
        if categoria_do_produto in produtos_agrupados:
            produtos_agrupados[categoria_do_produto]['produtos'].append(produto)
    
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

# Em app.py

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    """
    Rota inteligente que decide se deve criar um novo produto ou
    adicionar estoque a um produto existente.
    """
    try:
        # Pega o ID do produto do campo escondido do formulário
        id_produto = request.form.get('id_produto')
        
        # --- LÓGICA DE DECISÃO ---
        if id_produto:
            # Se existe um ID, significa que estamos ADICIONANDO ESTOQUE OU ATUALIZANDO DADOS
            id_produto = int(id_produto)
            
            # Pega a quantidade e o preço de compra para a adição de estoque
            quantidade_adicionada = request.form.get('quantidade') 
            preco_compra_unitario = request.form.get('preco_compra')
            
            # CORREÇÃO: Pega o preço de venda ANTES de usá-lo na condição
            novo_preco_venda_str = request.form.get('preco_venda') 

            # Se a quantidade e o preço de compra foram fornecidos, adiciona estoque
            if quantidade_adicionada and preco_compra_unitario:
                gerenciador_db.adicionar_estoque(id_produto, int(quantidade_adicionada), float(preco_compra_unitario))
            
            # Se um novo preço de venda foi fornecido, atualiza APENAS o preço de venda
            if novo_preco_venda_str: # AQUI A VARIÁVEL ESTÁ DEFINIDA
                gerenciador_db.atualizar_preco_venda_produto(id_produto, float(novo_preco_venda_str))
        
        else:
            # Se NÃO existe um ID, estamos CRIANDO UM NOVO PRODUTO
            nome = request.form.get('nome_produto')
            categoria_id = int(request.form.get('categoria_produto'))
            preco_venda = float(request.form.get('preco_venda'))
            preco_compra = float(request.form.get('preco_compra'))
            quantidade = int(request.form.get('quantidade'))

            if nome and preco_venda and preco_compra and quantidade:
                gerenciador_db.adicionar_novo_produto(nome, preco_venda, quantidade, preco_compra, categoria_id)

    except (ValueError, TypeError) as e:
        print(f"Erro ao converter dados do formulário: {e}")

    # Redireciona de volta para a página de produtos para vermos o resultado
    return redirect(url_for('tela_produtos'))

@app.route('/excluir_categoria/<int:id_categoria>')
def rota_excluir_categoria(id_categoria):
    """
    Rota para excluir uma categoria. Recebe o ID da categoria pela URL.
    """
    gerenciador_db.excluir_categoria(id_categoria)
    return redirect(url_for('tela_produtos'))

@app.route('/excluir_produto/<int:id_produto>')
def rota_excluir_produto(id_produto):
    """
    Rota para excluir um produto. Recebe o ID do produto pela URL.
    """
    gerenciador_db.excluir_produto(id_produto)
    return redirect(url_for('tela_produtos'))

@app.route('/atualizar_ordem', methods=['POST'])
def atualizar_ordem():
    """
    Recebe a nova ordem de categorias ou produtos do frontend
    e chama a função apropriada no gerenciador_db para atualizar o banco.
    """
    try:
        data = request.get_json() # Pega os dados JSON enviados pelo frontend
        tipo_item = data.get('tipo') # 'categoria' ou 'produto'
        ids_ordenados = data.get('ids_ordenados') # Lista de IDs na nova ordem

        if tipo_item and ids_ordenados:
            if tipo_item == 'categoria':
                gerenciador_db.atualizar_ordem_itens('categorias', ids_ordenados)
                print(f"DEBUG: Ordem das categorias atualizada: {ids_ordenados}")
            elif tipo_item == 'produto':
                gerenciador_db.atualizar_ordem_itens('produtos', ids_ordenados)
                print(f"DEBUG: Ordem dos produtos atualizada: {ids_ordenados}")
            else:
                return {"status": "erro", "mensagem": "Tipo de item inválido"}, 400
            
            return {"status": "sucesso", "mensagem": "Ordem atualizada com sucesso!"}
        else:
            return {"status": "erro", "mensagem": "Dados incompletos"}, 400

    except Exception as e:
        print(f"Erro ao atualizar ordem: {e}")
        return {"status": "erro", "mensagem": f"Erro interno: {str(e)}"}, 500

@app.route('/api/historico_produto/<int:id_produto>')
def api_historico_produto(id_produto):
    """
    Rota de API que retorna o histórico de um produto em formato JSON.
    """
    # Chama a nossa função "Trabalhadora" para buscar os dados
    historico = gerenciador_db.obter_historico_produto(id_produto)

    # Retorna a lista de dados no formato JSON
    return jsonify(historico)

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))

if __name__ == '__main__':
    # O 'debug=True' faz o servidor reiniciar automaticamente quando salvamos o arquivo.
    app.run(debug=True, host='0.0.0.0', port=5001)



