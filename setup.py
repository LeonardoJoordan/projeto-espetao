import sys
import os
from cx_Freeze import setup, Executable

# Lista de arquivos e pastas que precisam ser incluídos no pacote final.
# O formato é uma tupla: ('caminho/do/arquivo/ou/pasta', 'caminho/dentro/do/pacote')
# Adicionamos a base de dados aqui também!
arquivos_para_incluir = [
    'static',
    'templates',
    'icon.png',
    'espetao.db' 
]

# Opções de build. Aqui listamos pacotes que podem ser difíceis de detectar.
build_exe_options = {
    "packages": [
        "sys",
        "os",
        "eventlet", # Essencial para o SocketIO
        "socketio",
        "engineio"
    ],
    "include_files": arquivos_para_incluir,
    # Se houver algum erro de módulo não encontrado, adicionamos aqui:
    "excludes": [] 
}

# Configuração da base do executável.
# 'Win32GUI' é usado para aplicações com interface gráfica no Windows,
# para que o console preto não apareça.
base = None
if sys.platform == "win32":
    base = "Win32GUI"

# Definição do nosso executável principal
executables = [
    Executable(
        "main.py",                # Nosso script de entrada
        base=base,
        target_name="Espetao.exe", # O nome do arquivo .exe final
        icon="icon.png"           # O ícone do programa
    )
]

# Chamada final para a função de setup
setup(
    name="Espetão do Léo",
    version="1.0",
    description="Sistema de Gestão para o Espetão do Léo",
    options={"build_exe": build_exe_options},
    executables=executables
)