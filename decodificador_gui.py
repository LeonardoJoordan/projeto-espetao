import tkinter as tk
from tkinter import scrolledtext, messagebox
import base64
import struct
import json
import re
import os

# ==============================================================================
# === MAPAS GLOBAIS ===
# Estes mapas serão preenchidos dinamicamente lendo o arquivo cardapio-data.js
# ==============================================================================
MAPA_PONTO_INVERSO = {0: 'N/A', 1: 'Mal Passado', 2: 'Ao Ponto', 3: 'Bem Passado'}
MAPA_PAGAMENTO_INVERSO = {}
MAPA_MODALIDADE_INVERSO = {}
MAPA_ACOMPANHAMENTOS_INVERSO = {}
MAPA_PRODUTOS = {} # Para traduzir ID para Nome

# ==============================================================================
# === LÓGICA DE CARREGAMENTO E PARSE DO ARQUIVO JS ===
# ==============================================================================
def carregar_mapas_do_js(caminho_arquivo='cardapio-data.js'):
    """
    Lê o arquivo cardapio-data.js, extrai os objetos e popula os mapas de tradução.
    """
    global MAPA_PAGAMENTO_INVERSO, MAPA_MODALIDADE_INVERSO
    global MAPA_ACOMPANHAMENTOS_INVERSO, MAPA_PRODUTOS

    try:
        if not os.path.exists(caminho_arquivo):
            raise FileNotFoundError(f"O arquivo '{caminho_arquivo}' não foi encontrado. "
                                    "Certifique-se de que ele está na mesma pasta do decodificador.")

        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            conteudo_js = f.read()

        # Usamos expressões regulares para extrair os objetos JSON do arquivo JS
        def extrair_objeto(nome_variavel, texto):
            padrao = re.search(f"export const {nome_variavel} = ({{.*?}});", texto, re.DOTALL)
            if not padrao:
                raise ValueError(f"Não foi possível encontrar o objeto '{nome_variavel}' no arquivo JS.")
            return json.loads(padrao.group(1))

        # Extrai e processa cada mapa
        menu_data = extrair_objeto("MENU_DATA", conteudo_js)
        mapa_pagamento = extrair_objeto("MAPA_PAGAMENTO", conteudo_js)
        mapa_modalidade = extrair_objeto("MAPA_MODALIDADE", conteudo_js)
        mapa_acompanhamentos = extrair_objeto("MAPA_ACOMPANHAMENTOS", conteudo_js)

        # Constrói os mapas inversos para decodificação
        MAPA_PRODUTOS = {int(k): v['nome'] for k, v in menu_data.items()}
        MAPA_PAGAMENTO_INVERSO = {v: k for k, v in mapa_pagamento.items()}
        MAPA_MODALIDADE_INVERSO = {v: k for k, v in mapa_modalidade.items()}
        MAPA_ACOMPANHAMENTOS_INVERSO = {v: k for k, v in mapa_acompanhamentos.items()}
        
        print("Mapas carregados com sucesso a partir de cardapio-data.js!")
        return True

    except Exception as e:
        messagebox.showerror("Erro ao Carregar Dicionário", str(e))
        return False

# ==============================================================================
# === LÓGICA DE DECODIFICAÇÃO (Usa os mapas carregados) ===
# ==============================================================================
def decodificar_pedido(codigo_base64: str) -> str:
    # (O conteúdo desta função permanece exatamente o mesmo, apenas ajustamos
    # a linha que exibe o nome do produto)
    try:
        resultado = [f"--- Decodificando o código: {codigo_base64[:30]}... ---\n"]
        dados_bytes = base64.b64decode(codigo_base64)
        offset = 0

        tamanho_nome = dados_bytes[offset]; offset += 1
        nome_bytes = dados_bytes[offset : offset + tamanho_nome]
        nome_cliente = nome_bytes.decode('utf-8'); offset += tamanho_nome
        
        cod_pagamento = dados_bytes[offset]; offset += 1
        metodo_pagamento = MAPA_PAGAMENTO_INVERSO.get(cod_pagamento, f"Código Inválido ({cod_pagamento})")
        
        cod_modalidade = dados_bytes[offset]; offset += 1
        modalidade = MAPA_MODALIDADE_INVERSO.get(cod_modalidade, f"Código Inválido ({cod_modalidade})")

        resultado.append("== CABEÇALHO DO PEDIDO ==")
        resultado.append(f"Nome do Cliente: {nome_cliente}")
        resultado.append(f"Forma de Pagamento: {metodo_pagamento}")
        resultado.append(f"Modalidade: {modalidade}\n")
        
        resultado.append("== ITENS DO PEDIDO ==")
        itens_decodificados = []
        bytes_por_item = 5

        while offset < len(dados_bytes):
            produto_id = struct.unpack('<H', dados_bytes[offset : offset + 2])[0]
            quantidade = dados_bytes[offset + 2]
            ponto_cod = dados_bytes[offset + 3]
            ponto_carne = MAPA_PONTO_INVERSO.get(ponto_cod, "Inválido")
            acompanhamentos_mask = dados_bytes[offset + 4]
            
            acompanhamentos = []
            for bit_valor, nome in MAPA_ACOMPANHAMENTOS_INVERSO.items():
                if acompanhamentos_mask & bit_valor:
                    acompanhamentos.append(nome)
            
            itens_decodificados.append({
                'id': produto_id, 'quantidade': quantidade, 'ponto': ponto_carne,
                'acompanhamentos': ', '.join(acompanhamentos) if acompanhamentos else 'Nenhum'
            })
            offset += bytes_por_item
        
        if not itens_decodificados:
            resultado.append("Nenhum item encontrado.")
        else:
            for i, item in enumerate(itens_decodificados, 1):
                resultado.append(f"\n--- Item #{i} ---")
                # AQUI a grande melhoria: usamos o MAPA_PRODUTOS
                nome_produto = MAPA_PRODUTOS.get(item['id'], f"ID Desconhecido ({item['id']})")
                resultado.append(f"   Produto: {nome_produto} (ID: {item['id']})")
                resultado.append(f"   Quantidade: {item['quantidade']}")
                resultado.append(f"   Ponto: {item['ponto']}")
                resultado.append(f"   Acompanhamentos: {item['acompanhamentos']}")
        
        return "\n".join(resultado)

    except Exception as e:
        return f"[!!! ERRO AO DECODIFICAR !!!]\n\nOcorreu um erro: {e}\n\nVerifique se o código Base64 está correto e completo."

# ==============================================================================
# === LÓGICA DA INTERFACE GRÁFICA (Tkinter) - SEM MUDANÇAS ===
# ==============================================================================
def handle_decode_button_click():
    log_box.config(state=tk.NORMAL)
    log_box.delete('1.0', tk.END)
    codigo = entry_box.get().strip()
    
    if not codigo:
        log_box.insert(tk.END, "Por favor, insira um código para decodificar.")
    else:
        resultado_formatado = decodificar_pedido(codigo)
        log_box.insert(tk.END, resultado_formatado)
        
    log_box.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Decodificador de Pedidos (Leitor de cardapio-data.js)")
    root.geometry("600x450")

    # Tenta carregar os mapas. Se falhar, a janela ainda abre para mostrar o erro.
    carregar_mapas_do_js()

    input_frame = tk.Frame(root, padx=10, pady=10)
    input_frame.pack(fill=tk.X)
    label = tk.Label(input_frame, text="Cole o Código Base64 do Site:")
    label.pack(side=tk.LEFT)
    entry_box = tk.Entry(input_frame, width=50)
    entry_box.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
    decode_button = tk.Button(input_frame, text="Decodificar", command=handle_decode_button_click)
    decode_button.pack(side=tk.LEFT)

    log_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=20, state=tk.DISABLED, padx=5, pady=5)
    log_box.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0, 10))

    root.mainloop()