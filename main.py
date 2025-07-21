import sys
import socket
import threading
import webbrowser
import requests  # Importa a biblioteca de requisições
import os
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QTextEdit, QPushButton, QGroupBox, QGridLayout)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QIcon, QPixmap

# Importa o 'app' e o 'socketio' do seu arquivo app.py
# app.py agora funciona como uma "biblioteca" para o nosso programa principal
from app import app, socketio

# --- Classe para redirecionar os logs para a interface ---
class LogHandler(QObject):
    nova_mensagem = Signal(str)

    def write(self, msg):
        self.nova_mensagem.emit(msg)

    def flush(self):
        pass

# --- Classe para rodar o Flask em uma thread separada ---
class ServidorThread(threading.Thread):
    def __init__(self, host, port):
        super().__init__()
        self.daemon = True
        self.host = host
        self.port = port

    def run(self):
        try:
            print("Iniciando servidor Flask na thread...")
            # Usamos allow_unsafe_werkzeug=True para permitir o shutdown
            socketio.run(app, host=self.host, port=self.port, debug=False, allow_unsafe_werkzeug=True)
        except Exception as e:
            print(f"ERRO ao iniciar o servidor: {e}")

# --- Janela Principal do Aplicativo ---
class PainelControle(QWidget):
    def __init__(self):
        super().__init__()
        self.servidor_rodando = False
        self.servidor_thread = None
        self.ip_servidor = self.detectar_ip()
        self.porta = 5001

        self.configurar_ui()
        self.configurar_log_handler()

    def configurar_ui(self):
        """Configura a interface gráfica da janela."""
        self.setWindowTitle('Painel de Controle - Espetão do Léo')
        self.setWindowIcon(QIcon(self.resource_path('icon.png'))) # Adiciona um ícone
        self.setGeometry(100, 100, 600, 500)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Segoe UI';
            }
            QPushButton {
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#btn_iniciar {
                background-color: #28a745;
                color: white;
            }
            QPushButton#btn_iniciar:disabled {
                background-color: #555;
            }
            QPushButton#btn_parar {
                background-color: #dc3545;
                color: white;
            }
            QPushButton#btn_parar:disabled {
                background-color: #555;
            }
            QPushButton#btn_atalho {
                background-color: #007bff;
                color: white;
            }
            QPushButton#btn_atalho:disabled {
                background-color: #555;
            }
            QLabel {
                font-size: 14px;
            }
            QTextEdit {
                background-color: #121212;
                color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace;
                border: 1px solid #444;
                border-radius: 5px;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 10px;
            }
        """)

        layout_principal = QVBoxLayout(self)

        # --- Seção de Controle do Servidor ---
        grupo_controle = QGroupBox("Controle do Servidor")
        layout_controle = QHBoxLayout()
        
        self.label_status = QLabel(f"<b>Status:</b> <font color='#dc3545'>Parado</font><br><b>IP para acesso:</b> <font color='#FBBF24'>{self.ip_servidor}</font>")
        self.label_status.setTextFormat(Qt.RichText)

        self.btn_iniciar = QPushButton("Iniciar Servidor")
        self.btn_iniciar.setObjectName("btn_iniciar")
        self.btn_iniciar.clicked.connect(self.gerenciar_servidor)

        self.btn_parar = QPushButton("Parar Servidor")
        self.btn_parar.setObjectName("btn_parar")
        self.btn_parar.clicked.connect(self.gerenciar_servidor)
        self.btn_parar.setEnabled(False)

        layout_controle.addWidget(self.label_status, 1) # O 1 faz com que o label ocupe mais espaço
        layout_controle.addWidget(self.btn_iniciar)
        layout_controle.addWidget(self.btn_parar)
        grupo_controle.setLayout(layout_controle)

        # --- Seção de Atalhos ---
        grupo_atalhos = QGroupBox("Atalhos de Acesso")
        layout_atalhos = QGridLayout()
        
        self.botoes_atalho = {
            "Cardápio (Cliente)": "/cliente",
            "Painel da Cozinha": "/cozinha",
            "Monitor de Pedidos": "/monitor",
            "Gestão de Produtos": "/produtos",
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

        # --- Seção de Log ---
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        # Adicionando os grupos e widgets ao layout principal
        layout_principal.addWidget(grupo_controle)
        layout_principal.addWidget(grupo_atalhos)
        layout_principal.addWidget(QLabel("Log do Servidor:"))
        layout_principal.addWidget(self.log_area, 1) # O 1 faz com que a área de log se expanda

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

    def gerenciar_servidor(self):
        """Inicia ou para o servidor com base no estado atual."""
        sender = self.sender()
        if sender == self.btn_iniciar and not self.servidor_rodando:
            self.iniciar_servidor()
        elif sender == self.btn_parar and self.servidor_rodando:
            self.parar_servidor()
            
    def iniciar_servidor(self):
        self.servidor_thread = ServidorThread(self.ip_servidor, self.porta)
        self.servidor_thread.start()
        self.servidor_rodando = True
        self.atualizar_status_ui()
        # Dá um pequeno tempo para o servidor iniciar antes de checar
        QTimer.singleShot(1000, self.checar_status_servidor)

    def parar_servidor(self):
        print("Enviando comando para desligar o servidor...")
        try:
            # Envia uma requisição para a rota de shutdown que criaremos no Flask
            requests.post(f'http://{self.ip_servidor}:{self.porta}/shutdown')
        except requests.exceptions.ConnectionError:
            # É esperado que dê erro de conexão, pois o servidor desliga
            print("Servidor desligado com sucesso (erro de conexão esperado).")
        finally:
            self.servidor_rodando = False
            self.servidor_thread = None
            self.atualizar_status_ui()
    
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
        else:
            self.label_status.setText(f"<b>Status:</b> <font color='#dc3545'>Parado</font><br><b>IP para acesso:</b> <font color='#FBBF24'>{self.ip_servidor}</font>")
            self.btn_iniciar.setEnabled(True)
            self.btn_parar.setEnabled(False)
        
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
    # Cria a aplicação PySide6
    app_gui = QApplication(sys.argv)
    
    # Cria e exibe a janela principal
    janela = PainelControle()
    janela.show()
    
    # Inicia o loop de eventos da aplicação
    sys.exit(app_gui.exec())
