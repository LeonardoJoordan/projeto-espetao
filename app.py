from flask import Flask, render_template, request, redirect, url_for, jsonify
import gerenciador_db
from flask_socketio import SocketIO, join_room
import os
import uuid
from werkzeug.utils import secure_filename
import sys
import threading
import time
import analytics
import pytz
from datetime import datetime, timedelta

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

def emit_estoque_atualizado(local_id, updates, origem="desconhecida"):
    """
    Agrega e emite atualizações de disponibilidade de estoque para um local específico.
    """
    if not updates or not local_id:
        return

    payload = {
        "local_id": local_id,
        "origem": origem,
        "version": int(time.time() * 1000),
        "updates": updates
    }
    room = f"local:{local_id}"
    socketio.emit('atualizacao_disponibilidade', payload, to=room)
    print(f"Emitido 'atualizacao_disponibilidade' para a sala {room}: {len(updates)} updates.")


@socketio.on('connect')
def handle_connect():
    """
    Quando um cliente se conecta, ele entra em uma "sala" específica
    para o local de trabalho atual. Isso garante que ele só receba
    atualizações de estoque relevantes para o seu totem.
    """
    if LOCAL_SESSAO_ATUAL:
        room = f"local:{LOCAL_SESSAO_ATUAL}"
        join_room(room)
        print(f"Cliente conectado e ingressou na sala: {room}")
    else:
        print("AVISO: Cliente conectado, mas nenhum local de sessão foi definido.")

@app.route('/api/definir_local_sessao', methods=['POST'])
def definir_local_sessao(local_id):
    """Função para definir o local da sessão a partir de outro módulo."""
    global LOCAL_SESSAO_ATUAL
    if local_id:
        LOCAL_SESSAO_ATUAL = int(local_id)
        print(f"Sessão de trabalho definida para o local ID: {LOCAL_SESSAO_ATUAL}")
        return True
    return False

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
    proxima_senha = gerenciador_db.obter_proxima_senha_diaria(LOCAL_SESSAO_ATUAL)
    
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
    Rota para reiniciar o tempo de preparo de um item específico,
    identificado pela sua posição 'k' no grupo.
    """
    # Captura o parâmetro 'k' da URL. Se não vier, assume 1 por segurança.
    k_posicao = request.args.get('k', default=1, type=int)

    sucesso = gerenciador_db.reiniciar_preparo_item(pedido_id, produto_id, k_posicao)
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
    
    
@app.route('/api/produto/mudar_categoria', methods=['POST'])
def api_mudar_categoria_produto():
    """API para alterar a categoria de um produto via drag-and-drop."""
    dados = request.get_json()
    id_produto = dados.get('id_produto')
    nova_categoria_id = dados.get('nova_categoria_id')

    if not id_produto or not nova_categoria_id:
        return jsonify({"status": "erro", "mensagem": "Dados incompletos."}), 400

    sucesso = gerenciador_db.atualizar_categoria_produto(id_produto, nova_categoria_id)

    if sucesso:
        return jsonify({"status": "sucesso", "mensagem": "Categoria do produto atualizada."})
    else:
        return jsonify({"status": "erro", "mensagem": "Falha ao atualizar o banco de dados."}), 500

@app.route('/api/insights/comparativos')
def api_insights_comparativos():
    """
    Nova rota para servir dados comparativos entre dois períodos.
    """
    # 1. Extrai os parâmetros obrigatórios dos períodos
    periodoA_inicio = request.args.get('periodoA_inicio')
    periodoA_fim = request.args.get('periodoA_fim')
    periodoB_inicio = request.args.get('periodoB_inicio')
    periodoB_fim = request.args.get('periodoB_fim')

    # Validação básica
    if not all([periodoA_inicio, periodoA_fim, periodoB_inicio, periodoB_fim]):
        return jsonify({"erro": "Os quatro parâmetros de data (periodoA_inicio, etc.) são obrigatórios."}), 400

    # 2. Coleta todos os outros parâmetros como filtros opcionais
    filtros = {
        'granularidade': request.args.get('granularidade', 'custom'),
        'local_id': request.args.get('local_id', 'todos')
        # Outros filtros como 'categoria_id' podem ser adicionados aqui no futuro
    }

    # 3. Chama a função especialista em analytics
    dados_comparativos = analytics.insights_comparativos(
        periodoA_inicio, periodoA_fim,
        periodoB_inicio, periodoB_fim,
        filtros
    )

    # 4. Retorna o resultado
    return jsonify(dados_comparativos)

@app.route('/api/insights/heatmap')
def api_insights_heatmap():
    """
    Nova rota para servir dados para o heatmap de atividade.
    """
    # 1. Extrai os parâmetros de data
    inicio = request.args.get('inicio')
    fim = request.args.get('fim')

    # Validação básica
    if not all([inicio, fim]):
        return jsonify({"erro": "Os parâmetros 'inicio' e 'fim' são obrigatórios."}), 400

    # 2. Coleta filtros opcionais
    filtros = {
        'local_id': request.args.get('local_id', 'todos')
    }

    # 3. Chama a função especialista em analytics
    dados_heatmap = analytics.insights_heatmap(inicio, fim, filtros)

    # 4. Retorna o resultado
    return jsonify(dados_heatmap)

@app.route('/api/fechamento_dia_v2')
def api_fechamento_dia_v2():
    """
    V2: Rota para servir os dados operacionais do dia/período no novo formato canônico.
    """
    try:
        # 1. Validação e normalização dos parâmetros da query
        date_str = request.args.get('data')
        inicio_str = request.args.get('inicio')
        fim_str = request.args.get('fim')

        if date_str:
            # Prioridade para o parâmetro 'data'
            try:
                tz_sp = pytz.timezone('America/Sao_Paulo')
                dia_selecionado = datetime.strptime(date_str, '%Y-%m-%d')

                # O dia de trabalho começa às 05:00 do dia D
                inicio_local = tz_sp.localize(dia_selecionado.replace(hour=5, minute=0, second=0, microsecond=0))
                # E termina 1 microssegundo antes das 05:00 do dia D+1
                fim_local = inicio_local + timedelta(days=1, microseconds=-1)

                # Converte para UTC para as queries no banco
                inicio_str = inicio_local.astimezone(pytz.utc).isoformat()
                fim_str = fim_local.astimezone(pytz.utc).isoformat()
            except (ValueError, TypeError):
                return jsonify({"erro": "Formato de data inválido. Use AAAA-MM-DD."}), 400
        elif not inicio_str or not fim_str:
            return jsonify({"erro": "Os parâmetros 'inicio' e 'fim' (ou 'data') são obrigatórios."}), 400
        
        # Leitura dos outros parâmetros
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=50, type=int)
        local_id = request.args.get('local_id', default='todos')

        # Garante que page e limit sejam sensatos
        if page < 1: page = 1
        if limit > 100: limit = 100

        # 2. Chama a nova função orquestradora no módulo de analytics
        dados_fechamento = analytics.fechamento_operacional_v2(
            inicio=inicio_str,
            fim=fim_str,
            page=page,
            limit=limit,
            local_id=local_id
        )

        # 3. Retorna os dados já serializados no formato correto
        return jsonify(dados_fechamento)

    except Exception as e:
        print(f"ERRO CRÍTICO em /api/fechamento_dia_v2: {e}")
        # Retorna o shape vazio em caso de erro, para não quebrar o frontend
        return jsonify(serializers.FechamentoSerializer.to_api_v2({}, {})), 500


@app.route('/api/insights/comparativos_v2')
def api_insights_comparativos_v2():
    """
    V2: Rota para servir dados comparativos entre dois períodos no novo formato canônico.
    """
    try:
        # 1. Extrai e valida os parâmetros obrigatórios
        periodoA_inicio = request.args.get('periodoA_inicio')
        periodoA_fim = request.args.get('periodoA_fim')
        periodoB_inicio = request.args.get('periodoB_inicio')
        periodoB_fim = request.args.get('periodoB_fim')

        if not all([periodoA_inicio, periodoA_fim, periodoB_inicio, periodoB_fim]):
            return jsonify({"erro": "Todos os parâmetros de data dos períodos A e B são obrigatórios."}), 400

        # 2. Coleta filtros opcionais
        filtros = {
            'local_id': request.args.get('local_id', 'todos')
        }

        # 3. Chama a nova função orquestradora em analytics
        dados_comparativos = analytics.insights_comparativos_v2(
            periodoA_inicio, periodoA_fim,
            periodoB_inicio, periodoB_fim,
            filtros
        )

        # 4. Retorna o resultado já serializado
        return jsonify(dados_comparativos)

    except Exception as e:
        print(f"ERRO CRÍTICO em /api/insights/comparativos_v2: {e}")
        return jsonify(serializers.ComparativosSerializer.to_api_v2({}, {})), 500
    
# === NOVAS ROTAS PARA RESERVA DE ESTOQUE ===

@app.route('/api/carrinho/item', methods=['POST'])
def api_gerenciar_reserva_item():
    """ Endpoint para adicionar/remover itens do carrinho (reservar/liberar). """
    dados = request.get_json()
    carrinho_id = dados.get('carrinho_id')
    produto_id = dados.get('produto_id')
    quantidade_delta = dados.get('quantidade_delta')
    # Usamos o local da sessão como autoridade máxima
    local_id = LOCAL_SESSAO_ATUAL 

    if not all([carrinho_id, produto_id, quantidade_delta, local_id]):
        return jsonify({"sucesso": False, "mensagem": "Dados incompletos."}), 400

    resultado = gerenciador_db.gerenciar_reserva(carrinho_id, local_id, produto_id, quantidade_delta)

    if resultado.get('sucesso'):
        emit_estoque_atualizado(
            local_id=local_id,
            updates=resultado.get('produtos_afetados', []),
            origem='reserva_item'
        )

    return jsonify(resultado)

@app.route('/api/carrinho/renovar', methods=['POST'])
def api_renovar_carrinho():
    """ Endpoint para estender a validade das reservas do carrinho. """
    dados = request.get_json()
    carrinho_id = dados.get('carrinho_id')
    local_id = LOCAL_SESSAO_ATUAL

    if not all([carrinho_id, local_id]):
        return jsonify({"sucesso": False, "mensagem": "Dados incompletos."}), 400

    # Aplica o rate limit do servidor: ignora se chamado há menos de 5s
    # Implementação simples sem cache:
    # (uma implementação real usaria Redis ou um dict em memória com timestamps)
    # Por agora, vamos delegar a lógica para o gerenciador_db.

    resultado = gerenciador_db.renovar_reservas_carrinho(carrinho_id, local_id)
    return jsonify(resultado)

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))
