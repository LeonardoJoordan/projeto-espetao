# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    
    # --- ALTERAÇÃO PRINCIPAL AQUI ---
    # Informa ao PyInstaller quais pastas e arquivos devem ser copiados para o pacote final.
    # O formato é uma lista de tuplas: ('origem', 'destino_no_pacote')
    datas=[
        ('static', 'static'),         # Copia a pasta 'static' inteira
        ('templates', 'templates'),     # Copia a pasta 'templates' inteira
        ('espetao.db', '.'),          # Copia o banco de dados para a raiz do pacote ('.')
        ('icon.png', '.')             # Copia o ícone para a raiz do pacote
    ],

    # --- OUTRA ALTERAÇÃO IMPORTANTE ---
    # Força a inclusão de módulos que o PyInstaller pode não encontrar sozinho.
    # Resolvemos aqui os problemas de 'eventlet' e 'dns' que tivemos antes.
    
    hiddenimports=[
        # já tinha:
        'eventlet',
        'dns',
        'engineio.async_drivers.eventlet',
        'eventlet.hubs.epolls',
        'eventlet.hubs.kqueue',
        # adições essenciais:
        'eventlet.hubs.selects',
        'eventlet.hubs.poll',
        # sugestão extra (não faz mal e evita surpresas):
        'greenlet'
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EspetaoApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True, # Mantemos True para ver a saída do servidor no terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    
    # --- ADIÇÃO FINAL ---
    # Define o ícone da aplicação.
    icon='icon.png'
)
coll = COLLECT(
    exe,
    a.binaries,
    # A linha abaixo foi corrigida para usar a.datas, que definimos acima
    a.datas, 
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EspetaoApp',
)