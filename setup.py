import sys
import os
from cx_Freeze import setup, Executable

# Lista de arquivos e pastas a serem incluídos
include_files = [
    ("static/", "static/"),
    ("templates/", "templates/"),
    ("espetao.db", "espetao.db"),
    ("icon.png", "icon.png"),
    ("analytics.py", "analytics.py"),
    ("gerenciador_db.py", "gerenciador_db.py"), 
    ("database.py", "database.py"),
    ("serializers.py", "serializers.py")
]

# Pacotes que devem ser incluídos
packages = [
    "os",
    "sys", 
    "multiprocessing",
    "threading",
    "queue",
    "socket",
    "webbrowser",
    "requests",
    "json",
    "uuid",
    "time",
    "signal",
    "sqlite3",
    "pytz",
    "datetime",
    
    # Eventlet e dependências
    "eventlet",
    "eventlet.hubs",
    "eventlet.hubs.selects",
    "eventlet.hubs.poll", 
    "eventlet.hubs.epolls",
    "eventlet.support",
    "eventlet.support.greendns",
    "greenlet",
    
    # DNS
    "dns",
    "dns.rdtypes",
    "dns.rdatatype",
    "dns.rdataclass",
    
    # PySide6
    "PySide6.QtCore",
    "PySide6.QtWidgets", 
    "PySide6.QtGui",
    
    # Flask e SocketIO
    "flask",
    "flask_socketio",
    "socketio",
    "engineio",
    "engineio.async_drivers.eventlet",
    "werkzeug",
    "werkzeug.utils",
    "jinja2",
    
    # Seus módulos
    "analytics",
    "gerenciador_db", 
    "database",
    "serializers"
]

# Módulos que devem ser explicitamente incluídos
includes = [
    "eventlet.hubs.selects",
    "eventlet.hubs.poll",
    "eventlet.hubs.epolls", 
    "dns.rdtypes",
    "greenlet._greenlet"
]

# Módulos a serem excluídos para reduzir tamanho
excludes = [
    "tkinter",
    "unittest",
    "test", 
    "pydoc",
    "doctest",
    "pdb"
]

# Opções de build
build_exe_options = {
    "packages": packages,
    "includes": includes,
    "excludes": excludes,
    "include_files": include_files,
    "optimize": 2,
    "build_exe": "build/exe.linux-x86_64-3.10"
}

# Configuração do executável
executables = [
    Executable(
        "main.py",
        target_name="EspetaoApp",
        icon="icon.png"
    )
]

setup(
    name="EspetaoApp",
    version="1.0.0",
    description="Sistema do Espetão do Léo",
    author="Leonardo", 
    options={"build_exe": build_exe_options},
    executables=executables
)