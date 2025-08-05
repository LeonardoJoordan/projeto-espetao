from flask import Flask, render_template, request, redirect, url_for, jsonify
import gerenciador_db
from flask_socketio import SocketIO
import os
import uuid
from werkzeug.utils import secure_filename
import sys

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
# Garante que o banco e as tabelas existam antes de o servidor iniciar.
from database import inicializar_banco
inicializar_banco()
# -----------------------------------------

# Determina o caminho base de forma universal
if getattr(sys, 'frozen', False):
    # Caminho para o executável (cx_Freeze, PyInstaller)
    base_path = os.path.dirname(sys.executable)
else:
    # Caminho para o script .py (desenvolvimento)
    base_path = os.path.dirname(os.path.abspath(__file__))

# Constrói os caminhos para as pastas 'templates' e 'static'
template_folder = os.path.join(base_path, 'templates')
static_folder = os.path.join(base_path, 'static')

# Inicializa o Flask com os caminhos corretos
app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

# Tenta diferentes modos até encontrar um que funcione
socketio = None
for mode in ['threading', 'gevent', None]:
    try:
        socketio = SocketIO(app, async_mode=mode, cors_allowed_origins='*')
        print(f"SocketIO iniciado com async_mode='{mode}'")
        break
    except:
        continue

# Se nenhum modo funcionar, cria sem especificar
if socketio is None:
    socketio = SocketIO(app, cors_allowed_origins='*')
    print("SocketIO iniciado com modo padrão")

# Variável global para armazenar o ID do local da sessão atual
LOCAL_SESSAO_ATUAL = None

@app.route('/api/definir_local_sessao', methods=['POST'])
def definir_local_sessao():
    """API para o painel de controle informar o local do dia."""
    global LOCAL_SESSAO_ATUAL
    dados = request.get_json()
    local_id = dados.get('local_id')
    if local_id:
        LOCAL_SESSAO_ATUAL = int(local_id)
        print(f"Sessão definida para o local ID: {LOCAL_SESSAO_ATUAL}")
        return jsonify({"status": "sucesso", "local_id": LOCAL_SESSAO_ATUAL})
    return jsonify({"status": "erro", "mensagem": "ID do local não fornecido"}), 400

@app.route('/api/locais')
def api_obter_locais():
    """API que retorna a lista de todos os locais cadastrados."""
    locais = gerenciador_db.obter_todos_locais()
    return jsonify(locais)

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
    todas_as_categorias = gerenciador_db.obter_todas_categorias()
    produtos = gerenciador_db.obter_todos_produtos()
    
    # 2. Agrupa os produtos por categoria para a exibição
    produtos_agrupados = {cat['id']: [] for cat in todas_as_categorias}
    for produto in produtos:
        if produto['categoria_id'] in produtos_agrupados:
            produtos_agrupados[produto['categoria_id']].append(produto)
    
    # --- AJUSTE DE 2 LINHAS PARA RESOLVER O PROBLEMA ---
    # 3. Filtra a lista de categorias para mostrar apenas as que têm produtos
    categorias_visiveis = [
        cat for cat in todas_as_categorias 
        if produtos_agrupados[cat['id']]
    ]

    # 4. Busca o ID do próximo pedido a ser criado
    proxima_senha = gerenciador_db.obter_proxima_senha_diaria()
    
    # 5. Envia todos os dados, incluindo o novo ID, para o template renderizar
    return render_template(
        'cliente.html', 
        categorias=categorias_visiveis, 
        produtos_agrupados=produtos_agrupados,
        proxima_senha=proxima_senha
    )
    
# --- NOVA ROTA DA COZINHA ---
@app.route('/cozinha')
def tela_cozinha():
    # 1. Busca a lista única e ordenada de todos os pedidos ativos
    todos_pedidos_ativos = gerenciador_db.obter_pedidos_ativos()

    # 2. Prepara as duas listas vazias para as "linhas" da cozinha
    pedidos_backlog = []
    pedidos_em_producao = []

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
    Rota inteligente que lida com a criação e atualização de produtos,
    incluindo o upload, salvamento e exclusão de fotos.
    """
    # --- Configurações de Upload ---
    PASTA_UPLOAD = os.path.join(app.static_folder, 'images', 'produtos')
    if not os.path.exists(PASTA_UPLOAD):
        os.makedirs(PASTA_UPLOAD)

    try:
        id_produto = request.form.get('id_produto')
        nome_foto_salva = request.form.get('foto_url_antiga') # Usaremos um campo auxiliar

        # 1. LÓGICA DE MANIPULAÇÃO DO ARQUIVO DE FOTO
        if 'foto_produto' in request.files:
            foto_arquivo = request.files['foto_produto']

            # Se um novo arquivo foi enviado e tem um nome...
            if foto_arquivo.filename != '':
                # Deleta a foto antiga, se existir
                if nome_foto_salva:
                    caminho_foto_antiga = os.path.join(PASTA_UPLOAD, nome_foto_salva)
                    if os.path.exists(caminho_foto_antiga):
                        os.remove(caminho_foto_antiga)

                # Gera um nome de arquivo seguro e único
                nome_seguro = secure_filename(foto_arquivo.filename)
                extensao = os.path.splitext(nome_seguro)[1]
                nome_foto_salva = str(uuid.uuid4()) + extensao

                # Salva o novo arquivo
                caminho_para_salvar = os.path.join(PASTA_UPLOAD, nome_foto_salva)
                foto_arquivo.save(caminho_para_salvar)

        # 2. LÓGICA DE MANIPULAÇÃO DOS DADOS DO FORMULÁRIO
        nome = request.form.get('nome_produto')
        descricao = request.form.get('descricao')
        categoria_id = int(request.form.get('categoria_produto'))
        preco_venda_str = request.form.get('preco_venda')

        requer_preparo_str = request.form.get('requer_preparo')
        requer_preparo = 1 if requer_preparo_str == 'on' else 0

        if id_produto:
            # --- CAMINHO DE ATUALIZAÇÃO ---
            id_produto = int(id_produto)
            # Passa o nome da foto (antiga ou a nova recém-salva) para o DB
            gerenciador_db.atualizar_dados_produto(id_produto, nome, descricao, nome_foto_salva, categoria_id, requer_preparo)

            quantidade_adicionada = request.form.get('quantidade') 
            preco_compra_unitario = request.form.get('preco_compra')
            if quantidade_adicionada and preco_compra_unitario:
                gerenciador_db.adicionar_estoque(id_produto, int(quantidade_adicionada), float(preco_compra_unitario))

            if preco_venda_str:
                gerenciador_db.atualizar_preco_venda_produto(id_produto, float(preco_venda_str))

        else:
            # --- CAMINHO DE CRIAÇÃO ---
            preco_venda = float(preco_venda_str)
            preco_compra = float(request.form.get('preco_compra'))
            quantidade = int(request.form.get('quantidade'))
            # Passa o nome da foto salva para o DB
            gerenciador_db.adicionar_novo_produto(nome, descricao, nome_foto_salva, preco_venda, quantidade, preco_compra, categoria_id, requer_preparo)

    except (ValueError, TypeError) as e:
        print(f"Erro ao converter dados do formulário: {e}")
    except Exception as e:
        print(f"Ocorreu um erro inesperado no upload: {e}")

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
    id_do_pedido_salvo = gerenciador_db.salvar_novo_pedido(dados_do_pedido, LOCAL_SESSAO_ATUAL)

    # 4. Verifica se a operação foi bem-sucedida antes de responder
    if id_do_pedido_salvo is None:
        return jsonify({
            "status": "erro",
            "mensagem": "Ocorreu um erro ao processar o pedido no servidor."
        }), 500

    socketio.emit('novo_pedido', {'msg': 'Um novo pedido chegou!'})
    return jsonify({
        "status": "sucesso",
        "mensagem": "Pedido recebido, em preparação!",
        "senha_diaria": id_do_pedido_salvo['senha']
    })

    socketio.emit('novo_pedido', {'msg': 'Um novo pedido chegou!'})

    return jsonify({
        "status": "sucesso",
        "mensagem": "Pedido recebido, em preparação!",
        "senha_diaria": id_do_pedido_salvo['senha']
        
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
    Rota inteligente que confirma o pagamento. Para pedidos de fluxo simples,
    o pedido pula diretamente para o status de 'aguardando_retirada'.
    """
    pedido = gerenciador_db.obter_pedido_por_id(pedido_id)
    if not pedido:
        return jsonify({"status": "erro", "mensagem": "Pedido não encontrado."}), 404

    # Ação 1: O pagamento é sempre confirmado primeiro.
    # Isso move o pedido para o estado 'aguardando_producao'.
    sucesso_pagamento = gerenciador_db.confirmar_pagamento_pedido(pedido_id)

    if not sucesso_pagamento:
        return jsonify({"status": "erro", "mensagem": "Falha ao confirmar o pagamento."}), 500

    # Ação 2: O Desvio Inteligente
    if pedido['fluxo_simples'] == 1:
        # Se for simples, usamos nossa nova função para pular para a retirada.
        sucesso = gerenciador_db.pular_pedido_para_retirada(pedido_id)
        mensagem_socket = f'Pedido simples {pedido_id} está pronto para retirada!'
    else:
        # Se for complexo, o trabalho aqui está feito. O pedido aguarda preparo.
        sucesso = True
        mensagem_socket = f'Pagamento do pedido {pedido_id} confirmado, aguardando preparo.'

    if sucesso:
        socketio.emit('novo_pedido', {'msg': mensagem_socket})
        return jsonify({"status": "sucesso"})
    else:
        return jsonify({"status": "erro", "mensagem": "Ação pós-pagamento falhou."}), 500

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

@app.route('/fechamento')
def tela_fechamento():
    """ Rota para exibir a página de fechamento de caixa e relatórios. """
    return render_template('fechamento.html')

@app.route('/api/relatorio')
def api_relatorio():
    """
    Endpoint da API para buscar os dados consolidados para o relatório.
    Recebe as datas como parâmetros na URL. Ex: /api/relatorio?inicio=...&fim=...
    """
    # Pega as datas da URL
    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    local_id = request.args.get('local_id', type=int, default=None)
    
    # Se não forem fornecidas, retorna um erro
    if not data_inicio_str or not data_fim_str:
        return jsonify({"erro": "As datas de início e fim são obrigatórias"}), 400

    # Chama nosso especialista para buscar os dados
    # Busca os dados do relatório e as configurações do sistema
    dados_relatorio = gerenciador_db.obter_dados_relatorio(data_inicio_str, data_fim_str, local_id)
    configuracoes = gerenciador_db.obter_configuracoes()

    if dados_relatorio:
        # Combina os dois dicionários em uma única resposta JSON
        dados = {**dados_relatorio, "configuracoes": configuracoes}
    else:
        dados = None # Mantém a lógica de erro original
        
    if dados:
        return jsonify(dados)
    else:
        return jsonify({"erro": "Não foi possível gerar o relatório"}), 500

@app.route('/monitor')
def tela_monitor():
    """ Rota para exibir o monitor de pedidos para os clientes. """
    return render_template('monitor.html')

@app.route('/pedido/entregar_direto/<int:id_do_pedido>', methods=['POST'])
def rota_entregar_direto(id_do_pedido):
    """
    Rota para finalizar um pedido de fluxo simples que pula a produção.
    """
    # A função entregar_pedido já faz tudo que precisamos:
    # baixa o estoque e marca o pedido como 'finalizado'.
    sucesso = gerenciador_db.entregar_pedido(id_do_pedido)
    if sucesso:
        socketio.emit('novo_pedido', {'msg': f'Pedido {id_do_pedido} (simples) foi entregue!'})
        return jsonify({"status": "sucesso"})
    else:
        return jsonify({"status": "erro"}), 400

@app.route('/api/tempos_produto/<int:produto_id>')
def api_obter_tempos(produto_id):
    """API para buscar os tempos de preparo de um produto."""
    tempos = gerenciador_db.obter_tempos_por_produto_id(produto_id)
    return jsonify(tempos)

@app.route('/salvar_tempos_produto', methods=['POST'])
def rota_salvar_tempos():
    """API para salvar os tempos de preparo de um produto."""
    data = request.get_json()
    produto_id = data.get('produto_id')
    tempos = data.get('tempos')
    if produto_id and tempos:
        sucesso = gerenciador_db.salvar_tempos_preparo(produto_id, tempos)
        if sucesso:
            return jsonify({"status": "sucesso"})
    return jsonify({"status": "erro"}), 400

@app.route('/api/tempo_preparo/<int:produto_id>/<string:ponto>')
def api_get_tempo_preparo(produto_id, ponto):
    """
    API para buscar o tempo de preparo de um item específico.
    """
    tempo_segundos = gerenciador_db.obter_tempo_preparo_especifico(produto_id, ponto)
    
    # Retorna o tempo em um formato JSON que o JavaScript espera
    return jsonify({'tempo_em_segundos': tempo_segundos})

@app.route('/pedido/<int:pedido_id>/item/<int:produto_id>/reiniciar', methods=['POST'])
def rota_reiniciar_item(pedido_id, produto_id):
    """
    Rota para reiniciar o tempo de preparo de um item específico.
    """
    sucesso = gerenciador_db.reiniciar_preparo_item(pedido_id, produto_id)
    if sucesso:
        # Emite um evento para que a cozinha recarregue e recalcule os timers
        socketio.emit('novo_pedido', {'msg': f'Item {produto_id} do pedido {pedido_id} reiniciado!'})
        return jsonify({"status": "sucesso", "mensagem": "Item reiniciado."})
    else:
        return jsonify({"status": "erro", "mensagem": "Item não pôde ser reiniciado."}), 400

# === NOVAS ROTAS PARA GERENCIAR ACOMPANHAMENTOS ===

@app.route('/adicionar_acompanhamento', methods=['POST'])
def rota_adicionar_acompanhamento():
    """ Rota para adicionar um novo acompanhamento via formulário. """
    nome_acompanhamento = request.form.get('nome_acompanhamento')
    if nome_acompanhamento:
        gerenciador_db.adicionar_acompanhamento(nome_acompanhamento)
    return redirect(url_for('tela_produtos'))

@app.route('/excluir_acompanhamento/<int:id_acompanhamento>')
def rota_excluir_acompanhamento(id_acompanhamento):
    """ Rota para excluir um acompanhamento. """
    gerenciador_db.excluir_acompanhamento(id_acompanhamento)
    return redirect(url_for('tela_produtos'))

@app.route('/toggle_acompanhamento/<int:id_acompanhamento>', methods=['POST'])
def rota_toggle_acompanhamento(id_acompanhamento):
    """ Rota para alternar a visibilidade de um acompanhamento. """
    sucesso = gerenciador_db.toggle_visibilidade_acompanhamento(id_acompanhamento)
    if sucesso:
        return jsonify({'status': 'sucesso'})
    else:
        return jsonify({'status': 'erro'}), 500

@app.route('/api/acompanhamentos_visiveis')
def api_get_acompanhamentos_visiveis():
    """ API que retorna apenas os acompanhamentos visíveis para o cliente. """
    acompanhamentos_visiveis = gerenciador_db.obter_acompanhamentos_visiveis()
    return jsonify(acompanhamentos_visiveis)

@app.route('/api/acompanhamentos')
def api_get_todos_acompanhamentos():
    """ API que retorna a lista completa de acompanhamentos para a gestão. """
    todos_acompanhamentos = gerenciador_db.obter_todos_acompanhamentos()
    return jsonify(todos_acompanhamentos)

@app.route('/salvar_configuracoes', methods=['POST'])
def rota_salvar_configuracoes():
    """ Rota para receber e salvar as novas taxas de pagamento. """
    try:
        dados = request.get_json()
        sucesso = gerenciador_db.salvar_configuracoes(dados)
        if sucesso:
            return jsonify({"status": "sucesso"})
        else:
            return jsonify({"status": "erro", "mensagem": "Erro ao salvar no banco de dados."}), 500
    except Exception as e:
        print(f"Erro ao salvar configurações: {e}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 400
    
@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Rota para desligar o servidor Flask de forma segura."""
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        # Para servidores de produção ou quando usando socketio
        import os
        import signal
        os.kill(os.getpid(), signal.SIGINT)
        return 'Servidor sendo desligado...', 200
    else:
        func()
        return 'Servidor desligado!', 200

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))
