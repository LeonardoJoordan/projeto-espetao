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
import json
import re
from datetime import datetime, timedelta

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
# Garante que o banco e as tabelas existam antes de o servidor iniciar.
from database import inicializar_banco
inicializar_banco()

# --- Dependência para Impressão ---
try:
    from escpos import printer
    ESCPOS_INSTALADO = True
except ImportError:
    ESCPOS_INSTALADO = False

# Inicializa o Flask com os caminhos corretos

def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para o cx_Freeze """
    try:
        # cx_Freeze cria uma pasta e armazena o caminho em sys.frozen
        if getattr(sys, 'frozen', False):
            # No cx_Freeze, o caminho base é onde o executável está
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller path (caso precise no futuro)
                base_path = sys._MEIPASS
            else:
                # cx_Freeze path
                base_path = os.path.dirname(sys.executable)
        else:
            # Se não estiver empacotado, o caminho base é o do próprio script
            base_path = os.path.dirname(os.path.abspath(__file__))
    except Exception as e:
        print(f"Erro ao detectar caminho base: {e}")
        base_path = os.path.dirname(os.path.abspath(__file__))

    full_path = os.path.join(base_path, relative_path)
    print(f"DEBUG: Caminho solicitado: {relative_path}")
    print(f"DEBUG: Caminho base: {base_path}")  
    print(f"DEBUG: Caminho final: {full_path}")
    print(f"DEBUG: Caminho existe? {os.path.exists(full_path)}")
    
    return full_path

# Define os caminhos corretos usando nossa nova função
static_folder_path = resource_path('static')
template_folder_path = resource_path('templates')

print(f"DEBUG: Static folder: {static_folder_path}")
print(f"DEBUG: Template folder: {template_folder_path}")

# Verifica se as pastas existem
if not os.path.exists(static_folder_path):
    print(f"ERRO: Pasta static não encontrada em: {static_folder_path}")
if not os.path.exists(template_folder_path):
    print(f"ERRO: Pasta templates não encontrada em: {template_folder_path}")

# Cria a instância do Flask informando os caminhos corretos
app = Flask(
    __name__,
    static_folder=static_folder_path,
    template_folder=template_folder_path
)

# Inicializa o SocketIO de forma explícita e robusta com 'eventlet'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')
print("SocketIO iniciado com async_mode='eventlet'")

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

# --- CONFIGURAÇÃO DA IMPRESSORA ---
CONFIG_IMPRESSORA_PATH = os.path.join(os.path.dirname(__file__), 'config_impressora.json')

def _obter_config_impressora():
    """Lê o arquivo de configuração da impressora e retorna como um dicionário."""
    try:
        if os.path.exists(CONFIG_IMPRESSORA_PATH):
            with open(CONFIG_IMPRESSORA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"ERRO ao ler config da impressora: {e}")
    return {} # Retorna um dict vazio se o arquivo não existir ou der erro

def _salvar_config_impressora(data):
    """Salva o dicionário de configuração no arquivo JSON."""
    try:
        with open(CONFIG_IMPRESSORA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"ERRO ao salvar config da impressora: {e}")
        return False




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
def definir_local_sessao_view():
    """View HTTP: lê JSON {local_id: ...} e define a sessão."""
    data = request.get_json(silent=True) or {}
    local_id = data.get('local_id')
    ok = definir_local_sessao(local_id)
    if ok:
        return jsonify({"status": "sucesso"}), 200
    return jsonify({"status": "erro"}), 400

def definir_local_sessao(local_id):
    """Função utilitária: pode ser chamada direto (como você já faz no main.py)."""
    global LOCAL_SESSAO_ATUAL
    try:
        if local_id is None:
            return False
        LOCAL_SESSAO_ATUAL = int(local_id)
        print(f"Sessão de trabalho definida para o local ID: {LOCAL_SESSAO_ATUAL}")
        return True
    except Exception as e:
        print(f"Falha ao definir local de sessão: {e}")
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

@app.route('/api/carrinho/forcar_expirar', methods=['POST'])
def api_forcar_expirar_carrinho():
    """ Endpoint para forçar a expiração imediata de todas as reservas de um carrinho no local atual. """
    dados = request.get_json(silent=True) or {}
    carrinho_id = dados.get('carrinho_id')
    local_id = LOCAL_SESSAO_ATUAL

    if not all([carrinho_id, local_id]):
        return jsonify({"sucesso": False, "mensagem": "Dados incompletos."}), 400

    resultado = gerenciador_db.forcar_expirar_carrinho(carrinho_id, local_id)

    if resultado.get('sucesso') and resultado.get('produtos_afetados'):
        emit_estoque_atualizado(
            local_id=local_id,
            updates=resultado.get('produtos_afetados', []),
            origem='forcar_expirar'
        )

    return jsonify(resultado)

@app.route('/api/config/impressora', methods=['GET'])
def api_obter_config_impressora():
    """Retorna a configuração atual da impressora."""
    config = _obter_config_impressora()
    ip_salvo = config.get('ip', None)
    return jsonify({'ip': ip_salvo})

@app.route('/api/config/impressora', methods=['POST'])
def api_salvar_config_impressora():
    """Valida e salva a configuração da impressora."""
    dados = request.get_json()
    if not dados or 'ip' not in dados:
        return jsonify({'mensagem': 'Dados ausentes no corpo da requisição.'}), 400

    ip_novo = dados['ip'].strip()

    # Expressão regular para validar IPv4 com porta opcional
    ip_pattern = re.compile(r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\:[0-9]{1,5})?$')
    
    if not ip_pattern.match(ip_novo):
        return jsonify({'mensagem': 'Formato de IP inválido. Use x.x.x.x ou x.x.x.x:porta'}), 400

    config = {'ip': ip_novo}
    sucesso = _salvar_config_impressora(config)

    if sucesso:
        return jsonify({'status': 'sucesso'})
    else:
        return jsonify({'mensagem': 'Erro interno ao salvar o arquivo de configuração.'}), 500

@app.route('/api/diagnostico_impressora', methods=['GET'])
def api_diagnostico_impressora():
    """Tenta conectar na impressora configurada e envia um ticket de teste."""
    if not ESCPOS_INSTALADO:
        return jsonify({'sucesso': False, 'mensagem': 'Biblioteca python-escpos não instalada.'})

    config = _obter_config_impressora()
    ip_configurado = config.get('ip')

    if not ip_configurado:
        return jsonify({'sucesso': False, 'mensagem': 'IP da impressora não configurado.'})

    try:
        # Separa o IP e a Porta. Usa 9100 como padrão se a porta não for especificada.
        if ':' in ip_configurado:
            host, port_str = ip_configurado.split(':')
            port = int(port_str)
        else:
            host = ip_configurado
            port = 9100
        
        # Tenta conectar e imprimir
        p = printer.Network(host=host, port=port, timeout=5)

        # Define o alinhamento e o tamanho da fonte
        p.set(align='center', width=2, height=2) 
        p.set(bold=True)  # Ativa o modo negrito
        p.text("Espetao\n")

        p.set(bold=False)  # Volta ao texto normal (desativa negrito)
        p.set(align='left', width=1, height=1) # Volta ao tamanho padrão
        p.text("Teste de impressao OK!\n")

        p.cut()

        return jsonify({'sucesso': True, 'mensagem': 'Teste de impressão enviado com sucesso!'})

    except Exception as e:
        print(f"ERRO DE IMPRESSAO: {e}")
        return jsonify({'sucesso': False, 'mensagem': f'Falha na conexão: {e}'})

def _formatar_e_imprimir_comanda(config_impressora, pedido):
    """Função executada em uma thread para formatar e imprimir a comanda."""
    traducoes_ponto = {
        "bem": "Bem passado",
        "mal": "Mal passado",
        "ponto": "Ao ponto"
    }

    try:
        ip_configurado = config_impressora.get('ip')
        if not ip_configurado:
            print("LOG IMPRESSAO: IP não configurado na thread.")
            return

        host, port = (ip_configurado.split(':') + ['9100'])[:2]
        port = int(port)
        p = printer.Network(host=host, port=port, timeout=5)

        # --- Cabeçalho ---
        p.set(align='center', width=2, height=2)
        p.text("\n\n")
        p.text(f"SENHA: {pedido['senha_diaria']}\n\n")

        p.set(bold=True)  # Ativa o negrito
        p.text(f"Pedido: {pedido['nome_cliente']}\n")
        p.set(bold=False)  # Desativa o negrito

        # 1. Converte o texto (string) de volta para um objeto datetime
        timestamp_obj = datetime.fromisoformat(pedido['timestamp_criacao'])

        # 2. Agora sim, aplica a conversão de fuso horário no objeto datetime
        data_hora_local = timestamp_obj.astimezone(
            pytz.timezone('America/Sao_Paulo')
        )
        p.text(data_hora_local.strftime('%d/%m/%Y - %H:%M:%S') + "\n")
        p.text("_" * 42 + "\n\n")

        # --- Itens ---

        # 1. Lê a string da coluna 'itens_json' de forma segura.
        #    Se a chave não existir, usa '[]' como padrão para evitar mais erros.
        itens_json_string = pedido.get('itens_json', '[]') 

        # 2. Converte a string JSON em uma lista Python.
        lista_de_itens = json.loads(itens_json_string)

        # 3. Agora, itera sobre a lista de itens que acabamos de criar.
        for idx, item in enumerate(lista_de_itens):
            nome_item = f"{item['quantidade']}x {item['nome']}"
            p.set(align='left')
            p.set(bold=True)  # Ativa o negrito
            p.text(nome_item + "\n")
            p.set(bold=False)  # Desativa o negrito

            # Customizações
            if item.get('customizacao'):
                custom = item['customizacao']
                if custom.get('ponto'):
                    ponto_original = custom['ponto']
                    ponto_traduzido = traducoes_ponto.get(ponto_original, ponto_original.title())
                    p.text(f"  - Ponto: {ponto_traduzido}\n")
                if custom.get('acompanhamentos'):
                    for acomp in custom['acompanhamentos']:
                        p.text(f"  - Com: {acomp}\n")
                if custom.get('observacoes'):
                    p.text(f"  - Obs: {custom['observacoes']}\n")

            p.text("\n")

        p.text("_" * 42 + "\n")

        # --- Modalidade ---
        if pedido['modalidade']:
            modalidade_texto = (
                "CONSUMO NO LOCAL" if pedido['modalidade'] == 'local' else "PARA VIAGEM"
            )
            p.set(align='center')
            p.set(bold=True)  # Ativa o negrito
            p.text(f"{modalidade_texto}\n")
            p.set(bold=False)  # Desativa o negrito
            p.text("\n")

        # --- Finaliza ---
        p.cut()
        print(f"LOG IMPRESSAO: Comanda para o pedido {pedido['id']} enviada com sucesso.")

    except Exception as e:
        print(f"LOG IMPRESSAO: ERRO na thread de impressão para o pedido {pedido['id']}: {e}")

@app.route('/api/pedido/<int:pedido_id>/imprimir_comanda', methods=['POST'])
def api_imprimir_comanda_pedido(pedido_id):
    """Recebe a requisição para imprimir uma comanda e dispara em uma thread."""
    if not ESCPOS_INSTALADO:
        return jsonify({'status': 'erro_config', 'mensagem': 'Biblioteca de impressão não instalada no servidor.'}), 500

    config = _obter_config_impressora()
    if not config.get('ip'):
        return jsonify({'status': 'erro_config', 'mensagem': 'IP da impressora não configurado no servidor.'}), 400

    pedido = gerenciador_db.obter_pedido_por_id(pedido_id)
    if not pedido:
        return jsonify({'status': 'nao_encontrado', 'mensagem': 'Pedido não encontrado.'}), 404

    # Dispara a impressão em uma nova thread para não bloquear a resposta
    thread = threading.Thread(target=_formatar_e_imprimir_comanda, args=(config, pedido))
    thread.start()

    return jsonify({'status': 'impressao_enfileirada', 'mensagem': 'Comanda enviada para a fila de impressão.'})

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cliente'))
