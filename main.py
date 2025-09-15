# main.py

# ===================================================================
# CORREÇÃO CRÍTICA PARA EMPACOTAMENTO COM CX_FREEZE
# ===================================================================
import sys
import os


def fix_dns_rdtypes():
    """
    Corrige o problema do dns.rdtypes.__all__ no cx_Freeze.
    Este é o bug específico que está causando o erro AttributeError.
    """
    try:
        import dns.rdtypes
        # Verifica se o atributo __all__ existe
        if not hasattr(dns.rdtypes, '__all__'):
            # Cria o atributo que está faltando no ambiente empacotado
            dns.rdtypes.__all__ = []
            print("DNS rdtypes __all__ corrigido para o cx_Freeze")
    except ImportError as e:
        print(f"Aviso: Não foi possível importar dns.rdtypes: {e}")
    except Exception as e:
        print(f"Erro ao corrigir dns.rdtypes: {e}")

# Aplica a correção ANTES de qualquer importação do eventlet
fix_dns_rdtypes()

# ===================================================================
# BLOCO DE INICIALIZAÇÃO DO EVENTLET - DEVE SER O PRIMEIRO DE TODOS
# ===================================================================
os.environ['EVENTLET_HUB'] = 'selects'
# A "Regra de Ouro": Prepara o ambiente para ser assíncrono ANTES de
# qualquer outra biblioteca de rede (socket, requests, PySide6, Flask) ser importada.
import eventlet
eventlet.monkey_patch()

# Garante que os hubs sejam incluídos no build congelado
import eventlet.hubs.selects   # noqa
import eventlet.hubs.poll      # noqa
import eventlet.hubs.epolls    # noqa
import eventlet.hubs.kqueue    # noqa
import engineio.async_drivers.eventlet  # noqa
import greenlet  # noqa
# ===================================================================


# ===================================================================
# AGORA, O RESTO DAS SUAS IMPORTACOES, EM QUALQUER ORDEM
# ===================================================================
import socket
import threading
import webbrowser
import requests
import os
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QTextEdit, QPushButton, QGroupBox, QGridLayout, 
                               QComboBox, QDialog, QListWidget, QLineEdit, 
                               QListWidgetItem, QMessageBox, QTabWidget)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QIcon, QPixmap, QFont
import json
# Importa o 'app' e o 'socketio' do seu arquivo app.py
from app import app, socketio
import gerenciador_db
import signal
import multiprocessing
from queue import Empty
# ===================================================================


# --- Classe para redirecionar os logs para a interface ---
class LogHandler(QObject):
    nova_mensagem = Signal(str)

    def write(self, msg):
        self.nova_mensagem.emit(msg)

    def flush(self):
        pass

# --- Classe para rodar o Flask em uma thread separada ---
class ServidorProcess(multiprocessing.Process):
    def __init__(self, host, port, log_queue, local_id): # Adicionamos local_id
        super().__init__()
        self.daemon = True
        self.host = host
        self.port = port
        self.log_queue = log_queue
        self.local_id = local_id # Armazenamos o local_id

    def run(self):
        sys.stdout = LogWriter(self.log_queue)
        sys.stderr = LogWriter(self.log_queue)
        try:
            # Importa a função aqui para evitar problemas de escopo
            from app import definir_local_sessao

            # Define o local ANTES de iniciar o servidor
            definir_local_sessao(self.local_id)

            print("Iniciando servidor Flask em um novo processo...")
            socketio.run(app, host=self.host, port=self.port, debug=False, allow_unsafe_werkzeug=True)
        except Exception as e:
            print(f"ERRO ao iniciar o servidor no processo filho: {e}")

# Classe auxiliar para capturar logs do processo filho
class LogWriter:
    def __init__(self, queue):
        self.queue = queue
    def write(self, message):
        self.queue.put(message)
    def flush(self):
        pass

# ===================================================================
# COLE ESTA VERSÃO CORRIGIDA NO main.py
# (Substitua a função _obter_config_impressora_localmente anterior)
# ===================================================================
def _obter_config_impressora_localmente():
    """
    Lê o arquivo de configuração da impressora diretamente do diretório
    do usuário, garantindo consistência com o app.py.
    """
    try:
        # Define o caminho no diretório do usuário, exatamente como em app.py
        config_dir = os.path.expanduser('~/.espetao')
        caminho_config = os.path.join(config_dir, 'config_impressora.json')

        if os.path.exists(caminho_config):
            with open(caminho_config, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config
    except Exception as e:
        print(f"[Keep-Alive] Erro ao ler config local da impressora: {e}")
    return {} # Retorna um dict vazio se o arquivo não existir ou der erro
# ===================================================================

def keepalive_printer(stop_event):
    """
    Função para rodar em uma thread, enviando um comando de status
    para a impressora em intervalos regulares para mantê-la ativa.
    """
    print("[Keep-Alive] Thread de monitoramento da impressora iniciada.")
    intervalo_segundos = 45 # Intervalo entre as verificações

    while not stop_event.is_set():
        config = _obter_config_impressora_localmente()
        ip_configurado = config.get('ip')

        if not ip_configurado:
            print("[Keep-Alive] IP da impressora não configurado. Aguardando...")
            stop_event.wait(intervalo_segundos)
            continue

        try:
            if ':' in ip_configurado:
                host, port_str = ip_configurado.split(':')
                port = int(port_str)
            else:
                host = ip_configurado
                port = 9100

            # Comando ESC/POS para solicitar status da impressora (DLE EOT n=1)
            comando_status = b'\x10\x04\x01'

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5) # Timeout de 5 segundos para conexão e resposta
                s.connect((host, port))
                s.sendall(comando_status)
                resposta = s.recv(1) # Espera 1 byte de resposta
                print(f"[Keep-Alive] Sucesso! Impressora {host}:{port} está online. Resposta: {resposta.hex()}")

        except socket.timeout:
            print(f"[Keep-Alive] ERRO: Timeout ao tentar conectar na impressora {ip_configurado}.")
        except Exception as e:
            print(f"[Keep-Alive] ERRO: Falha ao comunicar com a impressora {ip_configurado}. Detalhes: {e}")

        # Aguarda o próximo ciclo, mas obedece ao evento de parada
        stop_event.wait(intervalo_segundos)

    print("[Keep-Alive] Thread de monitoramento da impressora finalizada.")

# ===================================================================
# FIM DO BLOCO PARA ADICIONAR
# ===================================================================


class ModalConfiguracoesGerais(QDialog):
    """Nova janela de configurações com abas para Impressora e Locais."""
    def __init__(self, ip_servidor, porta, parent=None):
        super().__init__(parent)
        self.ip_servidor = ip_servidor
        self.porta = porta

        self.setWindowTitle("Configurações Gerais")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(parent.styleSheet())

        # Layout principal com abas
        layout_principal = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        layout_principal.addWidget(self.tab_widget)

        # Criar e adicionar as abas
        self.criar_aba_impressora()
        self.criar_aba_locais()
        self.criar_aba_js_site()

    # --- MÉTODOS DA ABA IMPRESSORA (Movidos para cá) ---
    def criar_aba_impressora(self):
        widget_aba = QWidget()
        layout = QVBoxLayout(widget_aba)
        
        grupo_ip = QGroupBox("Endereço da Impressora de Rede")
        layout_ip = QGridLayout(grupo_ip)

        self.input_ip_impressora = QLineEdit()
        self.input_ip_impressora.setPlaceholderText("Ex: 192.168.0.50 ou 192.168.0.50:9100")
        
        self.btn_salvar_impressora = QPushButton("Salvar")
        self.btn_testar_impressora = QPushButton("Testar Conexão")

        layout_ip.addWidget(QLabel("IP e Porta (opcional):"), 0, 0, 1, 2)
        layout_ip.addWidget(self.input_ip_impressora, 1, 0, 1, 2)
        layout_ip.addWidget(self.btn_testar_impressora, 2, 0)
        layout_ip.addWidget(self.btn_salvar_impressora, 2, 1)

        self.label_status_impressora = QLabel("")
        self.label_status_impressora.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(grupo_ip)
        layout.addWidget(self.label_status_impressora)
        layout.addStretch() # Empurra o conteúdo para cima

        self.btn_salvar_impressora.clicked.connect(self.salvar_configuracao_impressora)
        self.btn_testar_impressora.clicked.connect(self.testar_conexao_impressora)
        
        self.tab_widget.addTab(widget_aba, "Impressora")
        self.carregar_configuracao_atual_impressora()

    def carregar_configuracao_atual_impressora(self):
        try:
            url = f'http://{self.ip_servidor}:{self.porta}/api/config/impressora'
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                self.input_ip_impressora.setText(response.json().get('ip', ''))
            else:
                self.label_status_impressora.setText("<font color='#dc3545'>Servidor não respondeu.</font>")
        except requests.exceptions.RequestException:
            self.label_status_impressora.setText("<font color='#dc3545'>Erro ao conectar ao servidor.</font>")

    def salvar_configuracao_impressora(self):
        ip_digitado = self.input_ip_impressora.text().strip()
        try:
            url = f'http://{self.ip_servidor}:{self.porta}/api/config/impressora'
            response = requests.post(url, json={'ip': ip_digitado}, timeout=3)
            if response.status_code == 200:
                self.label_status_impressora.setText("<font color='#28a745'>Configuração salva!</font>")
            else:
                self.label_status_impressora.setText(f"<font color='#dc3545'>Falha: {response.json().get('mensagem', 'Erro')}</font>")
        except requests.exceptions.RequestException:
            self.label_status_impressora.setText("<font color='#dc3545'>Erro de comunicação.</font>")

    def testar_conexao_impressora(self):
        self.label_status_impressora.setText("<font color='#FBBF24'>Testando, aguarde...</font>")
        QApplication.processEvents()
        try:
            url = f'http://{self.ip_servidor}:{self.porta}/api/diagnostico_impressora'
            response = requests.get(url, timeout=10)
            resultado = response.json()
            if resultado.get('sucesso'):
                self.label_status_impressora.setText(f"<font color='#28a745'>{resultado.get('mensagem')}</font>")
            else:
                self.label_status_impressora.setText(f"<font color='#dc3545'>{resultado.get('mensagem')}</font>")
        except requests.exceptions.RequestException:
            self.label_status_impressora.setText("<font color='#dc3545'>Erro de comunicação.</font>")

    # --- MÉTODOS DA ABA LOCAIS (Movidos para cá) ---
    def criar_aba_locais(self):
        widget_aba = QWidget()
        layout = QVBoxLayout(widget_aba)
        
        self.lista_locais = QListWidget()
        self.carregar_locais()

        layout_botoes = QHBoxLayout()
        self.input_novo_local = QLineEdit()
        self.input_novo_local.setPlaceholderText("Nome do novo local")
        self.btn_adicionar_local = QPushButton("Adicionar")
        layout_botoes.addWidget(self.input_novo_local)
        layout_botoes.addWidget(self.btn_adicionar_local)

        self.btn_excluir_local = QPushButton("Excluir Selecionado")
        self.btn_excluir_local.setObjectName("btn_parar")

        layout.addLayout(layout_botoes)
        layout.addWidget(self.lista_locais)
        layout.addWidget(self.btn_excluir_local)

        self.btn_adicionar_local.clicked.connect(self.adicionar_local)
        self.btn_excluir_local.clicked.connect(self.excluir_local)

        self.tab_widget.addTab(widget_aba, "Locais de Trabalho")

    def carregar_locais(self):
        self.lista_locais.clear()
        locais = gerenciador_db.obter_todos_locais()
        if not locais:
            self.lista_locais.addItem("Nenhum local cadastrado.")
        else:
            for local in locais:
                item = QListWidgetItem(local['nome'])
                item.setData(Qt.UserRole, local['id'])
                self.lista_locais.addItem(item)

    def adicionar_local(self):
        nome_local = self.input_novo_local.text().strip()
        if nome_local and gerenciador_db.adicionar_local(nome_local):
            self.input_novo_local.clear()
            self.carregar_locais()
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível adicionar o local.")

    def excluir_local(self):
        item_selecionado = self.lista_locais.currentItem()
        if not item_selecionado or not item_selecionado.data(Qt.UserRole):
            return

        id_local = item_selecionado.data(Qt.UserRole)
        confirmacao = QMessageBox.question(self, "Confirmar", f"Excluir '{item_selecionado.text()}'?")
        if confirmacao == QMessageBox.StandardButton.Yes and gerenciador_db.excluir_local(id_local):
            self.carregar_locais()
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível excluir o local.")

    # --- MÉTODOS DA ABA JS SITE (Adicionar este bloco) ---
    def criar_aba_js_site(self):
        widget_aba = QWidget()
        layout = QVBoxLayout(widget_aba)
        
        grupo_gerador = QGroupBox("Gerador de Dicionário para o Site")
        layout_gerador = QVBoxLayout(grupo_gerador)

        self.btn_atualizar_js = QPushButton("1. Atualizar Dicionário a partir do PDV")
        
        self.text_area_js = QTextEdit()
        self.text_area_js.setReadOnly(True)
        self.text_area_js.setPlaceholderText("O conteúdo do arquivo 'cardapio-data.js' aparecerá aqui após a atualização...")
        self.text_area_js.setFont(QFont("Courier New", 10))

        self.btn_copiar_js = QPushButton("2. Copiar Conteúdo para a Área de Transferência")
        
        layout_gerador.addWidget(self.btn_atualizar_js)
        layout_gerador.addWidget(self.text_area_js)
        layout_gerador.addWidget(self.btn_copiar_js)

        layout.addWidget(grupo_gerador)
        self.tab_widget.addTab(widget_aba, "JS Site")

        # Conectar os botões às suas funções
        self.btn_atualizar_js.clicked.connect(self.atualizar_dicionario_js)
        self.btn_copiar_js.clicked.connect(self.copiar_conteudo_js)

    def atualizar_dicionario_js(self):
        """Busca os dados do DB, gera o código JS e o exibe na tela."""
        try:
            # 1. Pega os dados mais recentes do banco de dados
            dados_para_js = gerenciador_db.obter_dados_completos_para_js()
            
            # 2. Converte os dados para strings em formato JSON
            json_cardapio = json.dumps(dados_para_js["menuData"], indent=4, ensure_ascii=False)
            json_acompanhamentos = json.dumps(dados_para_js["acompanhamentosDisponiveis"], indent=4, ensure_ascii=False)
            
            # 3. Monta o template final do arquivo JavaScript
            template_js = f"""
// Este arquivo foi gerado automaticamente pelo PDV. NÃO EDITE MANUALMENTE.

export const menuData = {json_cardapio};

export const acompanhamentosDisponiveis = {json_acompanhamentos};
"""
            conteudo_final = template_js.strip()

            # 4. Exibe o conteúdo na caixa de texto
            self.text_area_js.setPlainText(conteudo_final)

            # 5. (Opcional) Salva o arquivo no diretório do PDV para conveniência
            with open('cardapio-data.js', 'w', encoding='utf-8') as f:
                f.write(conteudo_final)
            
            QMessageBox.information(self, "Sucesso", 
                "Dicionário JavaScript atualizado com sucesso!\n"
                "O conteúdo foi exibido na tela e salvo no arquivo 'cardapio-data.js'.")

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Ocorreu um erro ao gerar o dicionário: {e}")

    def copiar_conteudo_js(self):
        """Copia o conteúdo da caixa de texto para a área de transferência."""
        conteudo = self.text_area_js.toPlainText()
        if not conteudo:
            QMessageBox.warning(self, "Aviso", "A caixa de texto está vazia. Atualize o dicionário primeiro.")
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(conteudo)
        QMessageBox.information(self, "Copiado!", "O conteúdo do arquivo JS foi copiado para sua área de transferência.")

# --- Janela Principal do Aplicativo ---
class PainelControle(QWidget):
    def __init__(self):
        super().__init__()
        self.servidor_rodando = False
        self.servidor_process = None # CORREÇÃO: Atributo correto inicializado
        self.ip_servidor = self.detectar_ip()
        self.porta = 5001
        self.keepalive_stop_event = None # << ADICIONAR ESTA LINHA
        self.keepalive_thread = None     # << ADICIONAR ESTA LINHA
        
        self.log_queue = multiprocessing.Queue()
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.processar_fila_log)
        self.log_timer.start(100) # Checa a fila a cada 100ms

        self.configurar_ui()
        self.atualizar_status_ui()

    def configurar_ui(self):
        """Configura a interface gráfica da janela."""
        self.setWindowTitle('Painel de Controle - Espetão do Léo')
        self.setWindowIcon(QIcon(self.resource_path('icon.png')))
        self.setGeometry(100, 100, 700, 550)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #555; /* Cor de fundo padrão */
                border: none; /* Remove bordas padrão */
                padding: 10px; 
                border-radius: 5px; 
                font-weight: bold; 
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #666; /* Efeito ao passar o mouse */
            }
            QPushButton:disabled {
                background-color: #444; /* Estilo para botão desabilitado */
                color: #888;
            }

            QPushButton#btn_toggle_servidor_iniciar { background-color: #28a745; color: white; }
            QPushButton#btn_toggle_servidor_parar { background-color: #dc3545; color: white; }               

            QPushButton#btn_atalho, QPushButton#btn_gerenciar { background-color: #007bff; color: white; }
            QPushButton#btn_atalho:disabled, QPushButton#btn_gerenciar:disabled { background-color: #555; }
            QLabel { font-size: 14px; }
            QTextEdit {
                background-color: #121212; color: #f0f0f0; font-family: 'Consolas', 'Courier New', monospace;
                border: 1px solid #444; border-radius: 5px;
            }
            QGroupBox {
                font-weight: bold; font-size: 14px; border: 1px solid #444;
                border-radius: 5px; margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top center; padding: 0 10px;
            }
        """)

        layout_principal = QVBoxLayout(self)

        grupo_controle = QGroupBox("Controle do Servidor")
        layout_controle = QGridLayout()

        self.label_status = QLabel(f"<b>Status:</b> <font color='#dc3545'>Parado</font><br><b>IP para acesso:</b> <font color='#FBBF24'>{self.ip_servidor}</font>")
        self.label_status.setTextFormat(Qt.RichText)

        label_local = QLabel("<b>Local de Trabalho:</b>")
        self.combo_locais = QComboBox()
        self.combo_locais.setEnabled(False)

        # Novo botão de configurações (engrenagem)
        self.btn_config_geral = QPushButton("⚙️") # Usando o caractere de engrenagem
        self.btn_config_geral.setObjectName("btn_atalho") # Reutilizando um estilo
        self.btn_config_geral.setFixedSize(50, 42) # Ajusta o tamanho para parecer um ícone
        self.btn_config_geral.clicked.connect(self.abrir_modal_configuracoes)
        layout_controle.addWidget(self.btn_config_geral, 1, 2) # Adiciona na posição 2


        self.btn_toggle_servidor = QPushButton("Iniciar Servidor")
        self.btn_toggle_servidor.setObjectName("btn_toggle_servidor_iniciar")
        self.btn_toggle_servidor.clicked.connect(self.gerenciar_servidor)


        layout_controle.addWidget(self.label_status, 0, 0, 2, 1)
        layout_controle.addWidget(label_local, 0, 1)
        layout_controle.addWidget(self.combo_locais, 1, 1)
        layout_controle.addWidget(self.btn_toggle_servidor, 1, 4, 1, 2) # Ocupa 2 colunas



        grupo_controle.setLayout(layout_controle)

        grupo_atalhos = QGroupBox("Atalhos de Acesso")
        layout_atalhos = QGridLayout()
        self.botoes_atalho = {
            "Cardápio (Cliente)": "/cliente", "Painel da Cozinha": "/cozinha",
            "Monitor de Pedidos": "/monitor", "Gestão de Produtos": "/produtos",
            "Relatórios": "/fechamento"
        }
        posicoes = [(i, j) for i in range(2) for j in range(3)]
        for (texto_botao, rota), (linha, col) in zip(self.botoes_atalho.items(), posicoes):
            botao = QPushButton(texto_botao)
            botao.setObjectName("btn_atalho")
            botao.setEnabled(False)
            botao.clicked.connect(lambda checked, r=rota: self.abrir_navegador(r))
            layout_atalhos.addWidget(botao, linha, col)
        grupo_atalhos.setLayout(layout_atalhos)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        layout_principal.addWidget(grupo_controle)
        layout_principal.addWidget(grupo_atalhos)
        layout_principal.addWidget(QLabel("Log do Servidor:"))
        layout_principal.addWidget(self.log_area, 1)

    def abrir_modal_locais(self):
        modal = ModalGerenciarLocais(self)
        modal.exec() # Abre o modal e espera ele ser fechado
        self.carregar_locais() # Recarrega o dropdown principal após o modal fechar

    def abrir_modal_configuracoes(self):
        # A função que o botão chama agora abre o novo modal unificado
        modal = ModalConfiguracoesGerais(self.ip_servidor, self.porta, self)
        modal.exec()
        # Após fechar o modal, recarrega a lista de locais no painel principal
        self.carregar_locais()

    def carregar_locais(self):
        """Busca a lista de locais diretamente do DB e popula o QComboBox."""
        # REMOVEMOS A VERIFICAÇÃO DO SERVIDOR DAQUI
        try:
            locais = gerenciador_db.obter_todos_locais()
            self.combo_locais.clear()
            if not locais:
                self.combo_locais.addItem("Nenhum local cadastrado", -1)
                self.btn_toggle_servidor.setEnabled(False) # Desabilita se não houver locais
            else:
                for local in locais:
                    self.combo_locais.addItem(local['nome'], local['id'])
                self.btn_toggle_servidor.setEnabled(True) # Habilita se houver locais
        except Exception as e:
            print(f"Erro ao carregar locais no painel principal: {e}")
            self.combo_locais.addItem("Erro ao carregar", -1)
            self.btn_toggle_servidor.setEnabled(False)

    def definir_local_no_servidor(self):
        """Informa ao servidor Flask qual o local selecionado para a sessão."""
        local_id_selecionado = self.combo_locais.currentData()
        if local_id_selecionado == -1 or not self.servidor_rodando:
            print("Seleção de local inválida. O servidor não será iniciado.")
            self.parar_servidor() # Garante que pare se houver erro
            return False

        try:
            url = f'http://{self.ip_servidor}:{self.porta}/api/definir_local_sessao'
            payload = {'local_id': local_id_selecionado}
            response = requests.post(url, json=payload, timeout=2)
            if response.status_code == 200:
                print(f"Servidor configurado para o local: {self.combo_locais.currentText()}")
                return True
            else:
                print("Erro ao definir o local da sessão no servidor.")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Não foi possível conectar ao servidor para definir o local: {e}")
            return False
    
    def configurar_log_handler(self):
        """Redireciona o stdout e stderr para a área de log da UI."""
        log_handler = LogHandler()
        log_handler.nova_mensagem.connect(self.atualizar_log)
        sys.stdout = log_handler
        sys.stderr = log_handler

    def detectar_ip(self):
        """Tenta encontrar o IP local da máquina na rede."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80)) # Conecta a um IP externo para obter o IP local
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
            # ALERTA VISUAL AO USUÁRIO
            QMessageBox.warning(
            self,
            "Rede não encontrada",
            "Nenhuma conexão de rede válida foi detectada.\n"
            "O servidor será iniciado em modo LOCALHOST (127.0.0.1).\n\n"
            "Nesse modo, outros dispositivos não conseguirão acessar."
        )
        finally:
            s.close()
        return ip
    
    def processar_fila_log(self):
        """Verifica a fila de logs e atualiza a UI."""
        while not self.log_queue.empty():
            try:
                mensagem = self.log_queue.get_nowait()
                mensagem_str = mensagem.decode('utf-8', errors='ignore') if isinstance(mensagem, bytes) else mensagem
                self.atualizar_log(mensagem_str)
            except Empty:
                break

    def gerenciar_servidor(self):
        if not self.servidor_rodando:
            self.iniciar_servidor()
        else:
            self.parar_servidor()
            
    def iniciar_servidor(self):
        local_id_selecionado = self.combo_locais.currentData()
        if local_id_selecionado is None or local_id_selecionado == -1:
            QMessageBox.warning(self, "Local Inválido", "Por favor, cadastre e selecione um local de trabalho antes de iniciar.")
            return

        try:
            # Passa o local_id diretamente para o novo processo
            self.servidor_process = ServidorProcess(self.ip_servidor, self.porta, self.log_queue, local_id_selecionado)
            self.servidor_process.start()
            self.servidor_rodando = True

            # --- ADICIONE O BLOCO ABAIXO ---
            print("[Painel] Iniciando thread de keep-alive da impressora...")
            self.keepalive_stop_event = threading.Event()
            self.keepalive_thread = threading.Thread(target=keepalive_printer, args=(self.keepalive_stop_event,))
            self.keepalive_thread.daemon = True
            self.keepalive_thread.start()
            # --- FIM DO BLOCO ---

            self.atualizar_status_ui()
        except Exception as e:
            QMessageBox.critical(self, "Erro Fatal", f"Não foi possível iniciar o processo do servidor: {e}")

    def setup_sessao(self):
        """Carrega locais e define a sessão no servidor."""
        if self.definir_local_no_servidor():
            self.atualizar_status_ui()
        else:
            self.parar_servidor()

    def parar_servidor(self):

        # --- ADICIONE O BLOCO ABAIXO NO INÍCIO DA FUNÇÃO ---
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            print("[Painel] Encerrando a thread de keep-alive da impressora...")
            self.keepalive_stop_event.set()
            self.keepalive_thread.join(timeout=5) # Aguarda a thread finalizar
        self.keepalive_thread = None
        # --- FIM DO BLOCO ---

        print("Encerrando o processo do servidor...")
        if self.servidor_process and self.servidor_process.is_alive():
            self.servidor_process.terminate()
            self.servidor_process.join()
        
        self.servidor_rodando = False
        self.servidor_process = None
        self.atualizar_status_ui()
        print("Servidor parado com sucesso.")

    
    
    def checar_status_servidor(self):
        """Verifica se o servidor está respondendo."""
        if not self.servidor_rodando:
            return
        try:
            # Tenta acessar uma rota qualquer para ver se o servidor está no ar
            requests.get(f'http://{self.ip_servidor}:{self.porta}/cliente', timeout=1)
            self.atualizar_status_ui()
        except requests.exceptions.RequestException:
            # Se falhar, assume que o servidor caiu
            print("Erro: O servidor não está respondendo.")
            self.servidor_rodando = False
            self.atualizar_status_ui()

    def atualizar_status_ui(self):
        """Atualiza a interface com base no estado do servidor."""
        if self.servidor_rodando:
            self.label_status.setText(f"<b>Status:</b> <font color='#28a745'>Rodando</font><br><b>IP para acesso:</b> <font color='#FBBF24'>{self.ip_servidor}</font>")
            self.btn_toggle_servidor.setText("Finalizar Servidor")
            self.btn_toggle_servidor.setObjectName("btn_toggle_servidor_parar")
            self.combo_locais.setEnabled(False)
            self.btn_config_geral.setEnabled(False) # Desabilita config com servidor rodando
        else:
            self.label_status.setText(f"<b>Status:</b> <font color='#dc3545'>Parado</font><br><b>IP para acesso:</b> <font color='#FBBF24'>{self.ip_servidor}</font>")
            self.carregar_locais() 
            self.btn_toggle_servidor.setText("Iniciar Servidor")
            self.btn_toggle_servidor.setObjectName("btn_toggle_servidor_iniciar")
            self.combo_locais.setEnabled(True)
            self.btn_config_geral.setEnabled(True) # Habilita config com servidor parado

        # Aplica o estilo dinamicamente
        self.btn_toggle_servidor.style().polish(self.btn_toggle_servidor)

        for botao in self.findChildren(QPushButton):
            if botao.objectName() == "btn_atalho":
                botao.setEnabled(self.servidor_rodando)

    def abrir_navegador(self, rota):
        """Abre uma rota específica no navegador padrão."""
        url = f"http://{self.ip_servidor}:{self.porta}{rota}"
        webbrowser.open(url)

    def atualizar_log(self, mensagem):
        """Adiciona mensagens à área de log."""
        self.log_area.append(mensagem.strip())
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
        
    def closeEvent(self, event):
        """Garante que o servidor seja desligado ao fechar a janela."""
        if self.servidor_rodando:
            self.parar_servidor()
        event.accept()

    def resource_path(self, relative_path):
        """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

# --- Ponto de Entrada Principal ---
if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_IGN) # Ignora o sinal de interrupção na UI
    # Cria a aplicação PySide6
    app_gui = QApplication(sys.argv)
    
    # Cria e exibe a janela principal
    janela = PainelControle()
    janela.show()
    
    # Inicia o loop de eventos da aplicação
    sys.exit(app_gui.exec())
