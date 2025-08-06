import sys
import socket
import threading
import webbrowser
import requests  # Importa a biblioteca de requisições
import os
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QTextEdit, QPushButton, QGroupBox, QGridLayout, 
                               QComboBox, QDialog, QListWidget, QLineEdit, 
                               QListWidgetItem, QMessageBox)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QIcon, QPixmap
import json
# Importa o 'app' e o 'socketio' do seu arquivo app.py
# app.py agora funciona como uma "biblioteca" para o nosso programa principal
from app import app, socketio
import gerenciador_db
# Adicione esta importação no topo do main.py
import signal
import multiprocessing
from queue import Empty 

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

# Coloque esta nova classe ANTES da classe PainelControle
class ModalGerenciarLocais(QDialog):
    """Janela modal para adicionar, visualizar e excluir locais."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar Locais de Trabalho")
        self.setMinimumSize(400, 300)
        self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)

        self.lista_locais = QListWidget()
        self.carregar_locais() # Agora chama a função interna

        layout_botoes = QHBoxLayout()
        self.input_novo_local = QLineEdit()
        self.input_novo_local.setPlaceholderText("Nome do novo local")
        self.btn_adicionar = QPushButton("Adicionar")
        self.btn_adicionar.clicked.connect(self.adicionar_local)

        layout_botoes.addWidget(self.input_novo_local)
        layout_botoes.addWidget(self.btn_adicionar)

        self.btn_excluir = QPushButton("Excluir Selecionado")
        self.btn_excluir.setObjectName("btn_parar")
        self.btn_excluir.clicked.connect(self.excluir_local)

        layout.addLayout(layout_botoes)
        layout.addWidget(self.lista_locais)
        layout.addWidget(self.btn_excluir)

    def carregar_locais(self):
        """Busca locais diretamente do banco de dados e popula a lista do modal."""
        self.lista_locais.clear() # CORREÇÃO: Usa self.lista_locais
        locais = gerenciador_db.obter_todos_locais()
        if not locais:
            self.lista_locais.addItem("Nenhum local cadastrado.")
        else:
            for local in locais:
                item = QListWidgetItem(local['nome'])
                item.setData(Qt.UserRole, local['id']) # Armazena o ID no item
                self.lista_locais.addItem(item)

    def adicionar_local(self):
        """Adiciona local diretamente no banco de dados."""
        nome_local = self.input_novo_local.text().strip()
        if not nome_local:
            return

        sucesso = gerenciador_db.adicionar_local(nome_local) # CHAMADA DIRETA
        if sucesso:
            self.input_novo_local.clear()
            self.carregar_locais()
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível adicionar o local. Ele já pode existir.")

    def excluir_local(self):
        """Exclui local diretamente do banco de dados."""
        item_selecionado = self.lista_locais.currentItem()
        if not item_selecionado or not item_selecionado.data(Qt.UserRole):
            return

        id_local = item_selecionado.data(Qt.UserRole)
        nome_local = item_selecionado.text()

        confirmacao = QMessageBox.question(self, "Confirmar Exclusão", 
            f"Tem certeza que deseja excluir o local '{nome_local}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if confirmacao == QMessageBox.StandardButton.Yes:
            sucesso = gerenciador_db.excluir_local(id_local) # CHAMADA DIRETA
            if sucesso:
                self.carregar_locais()
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível excluir. Verifique se o local não está sendo usado em algum pedido.")

# --- Janela Principal do Aplicativo ---
class PainelControle(QWidget):
    def __init__(self):
        super().__init__()
        self.servidor_rodando = False
        self.servidor_process = None # CORREÇÃO: Atributo correto inicializado
        self.ip_servidor = self.detectar_ip()
        self.porta = 5001
        
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
                padding: 10px; border-radius: 5px; font-weight: bold; font-size: 14px;
            }
            QPushButton#btn_iniciar { background-color: #28a745; color: white; }
            QPushButton#btn_iniciar:disabled { background-color: #555; }
            QPushButton#btn_parar { background-color: #dc3545; color: white; }
            QPushButton#btn_parar:disabled { background-color: #555; }
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

        self.btn_gerenciar_locais = QPushButton("Gerenciar Locais")
        self.btn_gerenciar_locais.setObjectName("btn_gerenciar")
        self.btn_gerenciar_locais.clicked.connect(self.abrir_modal_locais)

        self.btn_iniciar = QPushButton("Iniciar Servidor")
        self.btn_iniciar.setObjectName("btn_iniciar")
        self.btn_iniciar.clicked.connect(self.gerenciar_servidor)

        self.btn_parar = QPushButton("Parar Servidor")
        self.btn_parar.setObjectName("btn_parar")
        self.btn_parar.clicked.connect(self.gerenciar_servidor)
        self.btn_parar.setEnabled(False)

        layout_controle.addWidget(self.label_status, 0, 0, 2, 1)
        layout_controle.addWidget(label_local, 0, 1)
        layout_controle.addWidget(self.combo_locais, 1, 1)
        layout_controle.addWidget(self.btn_gerenciar_locais, 1, 2)
        layout_controle.addWidget(self.btn_iniciar, 1, 3)
        layout_controle.addWidget(self.btn_parar, 1, 4)
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

    def carregar_locais(self):
        """Busca a lista de locais diretamente do DB e popula o QComboBox."""
        # REMOVEMOS A VERIFICAÇÃO DO SERVIDOR DAQUI
        try:
            locais = gerenciador_db.obter_todos_locais()
            self.combo_locais.clear()
            if not locais:
                self.combo_locais.addItem("Nenhum local cadastrado", -1)
                self.btn_iniciar.setEnabled(False) # Desabilita se não houver locais
            else:
                for local in locais:
                    self.combo_locais.addItem(local['nome'], local['id'])
                self.btn_iniciar.setEnabled(True) # Habilita se houver locais
        except Exception as e:
            print(f"Erro ao carregar locais no painel principal: {e}")
            self.combo_locais.addItem("Erro ao carregar", -1)
            self.btn_iniciar.setEnabled(False)

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
        sender = self.sender()
        if sender == self.btn_iniciar and not self.servidor_rodando:
            self.iniciar_servidor()
        elif sender == self.btn_parar and self.servidor_rodando:
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
            self.btn_iniciar.setEnabled(False)
            self.btn_parar.setEnabled(True)
            self.btn_gerenciar_locais.setEnabled(False) # Desabilita com servidor rodando
            self.combo_locais.setEnabled(False)
        else:
            self.label_status.setText(f"<b>Status:</b> <font color='#dc3545'>Parado</font><br><b>IP para acesso:</b> <font color='#FBBF24'>{self.ip_servidor}</font>")
            self.carregar_locais() # Carrega os locais quando o servidor está parado
            self.btn_parar.setEnabled(False)
            self.btn_gerenciar_locais.setEnabled(True) # Habilita com servidor parado
            self.combo_locais.setEnabled(True)

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
