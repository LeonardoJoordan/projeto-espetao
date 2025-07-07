from flask import Flask, render_template, request, redirect, url_for, jsonify
import gerenciador_db

app = Flask(__name__)

@app.route('/cliente', methods=['GET', 'POST'])
def tela_cliente():
    """
    Rota para a tela do cliente.
    GET: Exibe o cardápio para o cliente.
    POST: (Ainda não implementado) Processa um novo pedido.
    """
    if request.method == 'POST':
        # A lógica de criar um pedido virá aqui em uma próxima etapa
        return redirect(url_for('tela_cliente'))

    # --- Lógica para exibir o cardápio ---
    # 1. Busca os dados brutos do banco, já ordenados
    categorias = gerenciador_db.obter_todas_categorias()
    produtos = gerenciador_db.obter_todos_produtos()
    
    # 2. Agrupa os produtos por categoria para a exibição
    produtos_agrupados = {cat['id']: [] for cat in categorias}
    for produto in produtos:
        if produto['categoria_id'] in produtos_agrupados:
            produtos_agrupados[produto['categoria_id']].append(produto)
    
    # 3. Envia os dados para o template renderizar
    return render_template('cliente.html', categorias=categorias, produtos_agrupados=produtos_agrupados)

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

@app.route('/salvar_pedido', methods=['POST'])
def salvar_pedido():
    """
    Esta é a rota "Porteiro". Ela recebe os dados do pedido do frontend,
    confirma o recebimento e (futuramente) os envia para o gerenciador_db.
    """
    # 1. Pega os dados JSON enviados pelo JavaScript
    dados_do_pedido = request.get_json()

    # 2. (Temporário) Imprime os dados no terminal para depuração
    # Isso nos permite ver no console do Flask se os dados chegaram corretamente.
    print("--- NOVO PEDIDO RECEBIDO ---")
    print(dados_do_pedido)
    print("-----------------------------")

    # 3. Chama a função "trabalhadora" para salvar o pedido no banco de dados
    id_do_pedido_salvo = gerenciador_db.salvar_novo_pedido(dados_do_pedido)

    # 4. Verifica se a operação foi bem-sucedida antes de responder
    if id_do_pedido_salvo is None:
        # Se deu erro, retorna uma resposta de erro para o frontend
        return jsonify({
            "status": "erro",
            "mensagem": "Ocorreu um erro ao processar o pedido no servidor."
        }), 500 # 500 é o código para "Erro Interno do Servidor"

    return jsonify({
        "status": "sucesso",
        "mensagem": "Pedido recebido, em preparação!",
        "pedido_id": id_do_pedido_salvo
    })

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))

if __name__ == '__main__':
    # O 'debug=True' faz o servidor reiniciar automaticamente quando salvamos o arquivo.
    app.run(debug=True, host='0.0.0.0', port=5001)



