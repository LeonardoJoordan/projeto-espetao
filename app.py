from flask import Flask, render_template, request, redirect, url_for, jsonify
import gerenciador_db
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

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
    # 1. Busca a lista única e ordenada de todos os pedidos ativos
    todos_pedidos_ativos = gerenciador_db.obter_pedidos_ativos()

    # 2. Prepara as duas listas vazias para as "linhas" da cozinha
    pedidos_backlog = []      # Linha 1: Aguardando Pagamento e Aguardando Produção
    pedidos_em_producao = []  # Linha 2: Em Produção

    # 3. Itera sobre a lista ordenada e distribui cada pedido para a sua respectiva "linha"
    for pedido in todos_pedidos_ativos:
        if pedido['status'] in ['aguardando_pagamento', 'aguardando_producao']:
            pedidos_backlog.append(pedido)
        elif pedido['status'] == 'em_producao':
            pedidos_em_producao.append(pedido)

    # 4. Envia as duas listas separadas para o template da cozinha
    return render_template(
        'cozinha.html', 
        pedidos_backlog=pedidos_backlog, 
        pedidos_em_producao=pedidos_em_producao
    )

# Em app.py

@app.route('/produtos', methods=['GET'])
def tela_produtos():
    """
    Esta rota representa a tela de gestão de produtos.
    Ela busca os produtos e categorias REAIS do banco de dados e os agrupa.
    """
    # --- BUSCANDO DADOS 100% REAIS DO BANCO DE DADOS ---
    categorias_reais = gerenciador_db.obter_todas_categorias()
    # A ÚNICA MUDANÇA ESTÁ AQUI:
    produtos_reais = gerenciador_db.obter_todos_produtos_para_gestao() 
    
    # --- Lógica de Agrupamento COM IDs ---
    produtos_agrupados = {}
    for categoria in categorias_reais:
        produtos_agrupados[categoria['nome']] = {
            'id': categoria['id'],
            'produtos': []
        }

    # Agora o loop usa a lista de produtos reais do banco
    for produto in produtos_reais:
        # Verificação para evitar erro se um produto não tiver categoria associada
        if produto['categoria'] and produto['categoria'] in produtos_agrupados:
            produtos_agrupados[produto['categoria']]['produtos'].append(produto)
    
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

    socketio.emit('novo_pedido', {'msg': 'Um novo pedido chegou!'})

    return jsonify({
        "status": "sucesso",
        "mensagem": "Pedido recebido, em preparação!",
        "pedido_id": id_do_pedido_salvo,
        
    })

@app.route('/pedido/iniciar_preparo/<int:id_do_pedido>', methods=['POST'])
def rota_iniciar_preparo(id_do_pedido):
    """
    Rota para mudar o status do pedido para 'em_producao'.
    """
    sucesso = gerenciador_db.iniciar_preparo_pedido(id_do_pedido)
    if sucesso:
        # Emite o evento para notificar todos os clientes (inclusive a cozinha) que o estado mudou
        socketio.emit('novo_pedido', {'msg': f'Pedido {id_do_pedido} começou a ser preparado!'})
        return jsonify({"status": "sucesso", "mensagem": "Pedido iniciado com sucesso."})
    else:
        return jsonify({"status": "erro", "mensagem": "Pedido não pôde ser iniciado."}), 400

@app.route('/pedido/entregar/<int:id_do_pedido>', methods=['POST'])
def rota_entregar_pedido(id_do_pedido):
    """
    Rota para marcar um pedido como entregue (remove da lista ativa).
    """
    sucesso = gerenciador_db.entregar_pedido(id_do_pedido)
    if sucesso:
        socketio.emit('novo_pedido', {'msg': f'Pedido {id_do_pedido} foi entregue!'})
        return jsonify({"status": "sucesso"})
    else:
        return jsonify({"status": "erro"}), 400

@app.route('/pedido/cancelar/<int:id_do_pedido>', methods=['POST'])
def rota_cancelar_pedido(id_do_pedido):
    """
    Rota para cancelar um pedido (remove da lista ativa).
    """
    sucesso = gerenciador_db.cancelar_pedido(id_do_pedido)
    if sucesso:
        socketio.emit('novo_pedido', {'msg': f'Pedido {id_do_pedido} foi cancelado!'})
        return jsonify({"status": "sucesso"})
    else:
        return jsonify({"status": "erro"}), 400

@app.route('/pedido/confirmar_pagamento/<int:pedido_id>', methods=['POST'])
def rota_confirmar_pagamento(pedido_id):
    """
    Rota que o JavaScript da cozinha chama para confirmar o pagamento de um pedido.
    """
    sucesso = gerenciador_db.confirmar_pagamento_pedido(pedido_id)

    if sucesso:
        return jsonify({"status": "sucesso", "mensagem": f"Pagamento do pedido {pedido_id} confirmado."})
    else:
        return jsonify({"status": "erro", "mensagem": "Não foi possível confirmar o pagamento."}), 500

@app.route('/api/pedidos_ativos')
def api_pedidos_ativos():
    """
    Fornece a lista de todos os pedidos ativos em formato JSON.
    Esta API é consumida pela nova tela da cozinha para renderização dinâmica.
    """
    # 1. Chama nosso especialista em banco de dados, que já sabe como buscar e ordenar os pedidos.
    pedidos_ativos = gerenciador_db.obter_pedidos_ativos()

    # 2. Usa a função 'jsonify' do Flask para converter nossa lista Python em uma resposta JSON.
    return jsonify(pedidos_ativos)

@app.route('/pedido/chamar/<int:id_do_pedido>', methods=['POST'])
def rota_chamar_cliente(id_do_pedido):
    """
    Rota para mudar o status do pedido para 'aguardando_retirada'.
    """
    sucesso = gerenciador_db.chamar_cliente_pedido(id_do_pedido)
    if sucesso:
        # Emite o evento para notificar cozinha e monitor que o pedido está pronto
        socketio.emit('novo_pedido', {'msg': f'Pedido {id_do_pedido} está pronto para retirada!'})
        return jsonify({"status": "sucesso", "mensagem": "Cliente chamado com sucesso."})
    else:
        return jsonify({"status": "erro", "mensagem": "Pedido não pôde ser atualizado."}), 400

@app.route('/monitor')
def tela_monitor():
    """ Rota para exibir o monitor de pedidos para os clientes. """
    return render_template('monitor.html')

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))

if __name__ == '__main__':
    # O 'debug=True' faz o servidor reiniciar automaticamente quando salvamos o arquivo.
    socketio.run(app, debug=True, host='0.0.0.0', port=5001)



