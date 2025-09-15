import json
import pprint

# ==============================================================================
# === FONTE DA VERDADE (SIMULAÇÃO) ===
# No futuro, esta seção será substituída por uma leitura do seu banco de dados do PDV.
# Por agora, editamos os produtos diretamente aqui.
# ==============================================================================

# Definição dos acompanhamentos com IDs únicos
ACOMPANHAMENTOS = [
    {'id': 'extra1', 'nome': 'Farofa'},
    {'id': 'extra2', 'nome': 'Vinagrete'},
    {'id': 'extra3', 'nome': 'Maionese da Casa'},
]

# Definição dos pontos da carne
PONTOS_CARNE = [
    {'id': 'mal', 'nome': 'Mal Passado'},
    {'id': 'ponto', 'nome': 'Ao Ponto'},
    {'id': 'bem', 'nome': 'Bem Passado'},
]

# Cardápio principal, estruturado por categorias
CARDAPIO_PDV = [
    {
        'id': 1,
        'nome': "Espetinhos",
        'ordem': 1,
        'produtos': [
            {
                'id': 101,
                'nome': "Filé Mignon",
                'preco_venda': 15.00,
                'descricao': "Corte nobre, macio e suculento, feito na brasa.",
                'foto_url': "file_mignon.jpg",
                'requer_preparo': 1,
                'produto_ordem': 1
            },
            {
                'id': 102,
                'nome': "Alcatra",
                'preco_venda': 12.00,
                'descricao': "Carne saborosa com uma fina capa de gordura que garante a suculência.",
                'foto_url': "alcatra.jpg",
                'requer_preparo': 1,
                'produto_ordem': 2
            },
            {
                'id': 103,
                'nome': "Coração de Frango",
                'preco_venda': 10.00,
                'descricao': "Temperado com um toque especial da casa.",
                'foto_url': "coracao.jpg",
                'requer_preparo': 0,
                'produto_ordem': 3
            },
            {
                'id': 104,
                'nome': "Pão de Alho",
                'preco_venda': 8.00,
                'descricao': "Cremoso por dentro e crocante por fora.",
                'foto_url': "pao_alho.jpg",
                'requer_preparo': 0,
                'produto_ordem': 4
            }
        ]
    },
    {
        'id': 2,
        'nome': "Bebidas",
        'ordem': 2,
        'produtos': [
            {
                'id': 201,
                'nome': "Heineken Long Neck",
                'preco_venda': 8.00,
                'descricao': "Cerveja puro malte refrescante 330ml.",
                'foto_url': "heineken.jpg",
                'requer_preparo': 0,
                'produto_ordem': 1
            },
            {
                'id': 202,
                'nome': "Brahma Duplo Malte",
                'preco_venda': 7.00,
                'descricao': "Lata 350ml.",
                'foto_url': "brahma.jpg",
                'requer_preparo': 0,
                'produto_ordem': 2
            },
            {
                'id': 203,
                'nome': "Refrigerante Lata",
                'preco_venda': 5.00,
                'descricao': "Coca-Cola, Guaraná ou Fanta Laranja.",
                'foto_url': "refri_lata.jpg",
                'requer_preparo': 0,
                'produto_ordem': 3
            }
        ]
    }
]

# ==============================================================================
# === CONFIGURAÇÕES DE SAÍDA ===
# Nomes dos arquivos que serão gerados
# ==============================================================================
ARQUIVO_SAIDA_PYTHON = 'dicionario_pdv.py'
ARQUIVO_SAIDA_JS = 'cardapio-data.js'


# ==============================================================================
# === LÓGICA DE GERAÇÃO ===
# ==============================================================================

def gerar_dicionario_python():
    """Gera um arquivo .py contendo as estruturas de dados para o PDV."""
    try:
        with open(ARQUIVO_SAIDA_PYTHON, 'w', encoding='utf-8') as f:
            f.write("# Este arquivo foi gerado automaticamente. NÃO EDITE MANUALMENTE.\n")
            f.write("# Gerado por: gerador_dicionario.py\n\n")
            
            f.write("ACOMPANHAMENTOS = " + pprint.pformat(ACOMPANHAMENTOS) + "\n\n")
            f.write("PONTOS_CARNE = " + pprint.pformat(PONTOS_CARNE) + "\n\n")
            f.write("CARDAPIO_PDV = " + pprint.pformat(CARDAPIO_PDV) + "\n")
            
        print(f"[SUCESSO] Dicionário Python salvo em '{ARQUIVO_SAIDA_PYTHON}'")
    except Exception as e:
        print(f"[ERRO] Falha ao gerar dicionário Python: {e}")

def gerar_script_javascript():
    """Gera um arquivo .js contendo os dados do cardápio para o site."""
    try:
        # Converte as estruturas de dados Python para strings JSON formatadas
        json_cardapio = json.dumps(CARDAPIO_PDV, indent=4, ensure_ascii=False)
        json_acompanhamentos = json.dumps(ACOMPANHAMENTOS, indent=4, ensure_ascii=False)

        # Monta o conteúdo do arquivo JavaScript usando um template
        template_js = f"""
// Este arquivo foi gerado automaticamente. NÃO EDITE MANUALMENTE.
// Gerado por: gerador_dicionario.py

// EDITAR AQUI: Esta é a lista principal do seu cardápio.
// Adicione, remova ou altere as categorias e produtos conforme sua necessidade.
export const menuData = {json_cardapio};

// EDITAR AQUI: Lista de acompanhamentos disponíveis para os espetinhos.
export const acompanhamentosDisponiveis = {json_acompanhamentos};
"""
        with open(ARQUIVO_SAIDA_JS, 'w', encoding='utf-8') as f:
            f.write(template_js.strip())
            
        print(f"[SUCESSO] Script JavaScript salvo em '{ARQUIVO_SAIDA_JS}'")
    except Exception as e:
        print(f"[ERRO] Falha ao gerar script JavaScript: {e}")


if __name__ == "__main__":
    print("Iniciando a sincronização de dicionários...")
    gerar_dicionario_python()
    gerar_script_javascript()
    print("\nProcesso de geração concluído.")