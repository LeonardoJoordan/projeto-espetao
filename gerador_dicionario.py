import json
import pprint
import gerenciador_db  # <-- PASSO 1: Importamos nosso especialista em banco de dados

# ==============================================================================
# === FONTE DA VERDADE (AGORA LENDO DO BANCO DE DADOS) ===
# Esta seção agora busca os dados diretamente do gerenciador_db.
# As listas fixas foram removidas.
# ==============================================================================

print("Buscando dados atualizados do banco de dados...")
# PASSO 2: Chamamos a função que busca todos os dados reais do banco
dados_do_banco = gerenciador_db.obter_dados_completos_para_js()

# PASSO 3: Atribuímos os dados retornados a variáveis com os nomes que o resto do script espera
CARDAPIO_PARA_JS = dados_do_banco["menuData"]
ACOMPANHAMENTOS_PARA_JS = dados_do_banco["acompanhamentosDisponiveis"]
print("Dados recebidos com sucesso!")


# ==============================================================================
# === CONFIGURAÇÕES DE SAÍDA ===
# ==============================================================================
ARQUIVO_SAIDA_PYTHON_NAO_USADO = 'dicionario_pdv.py' # Este arquivo não é mais necessário
ARQUIVO_SAIDA_JS = 'cardapio-data.js'


# ==============================================================================
# === LÓGICA DE GERAÇÃO ===
# ==============================================================================

def gerar_script_javascript():
    """Gera um arquivo .js contendo os dados do cardápio para o site."""
    try:
        # PASSO 4: Usamos as variáveis que vieram do banco de dados
        json_cardapio = json.dumps(CARDAPIO_PARA_JS, indent=4, ensure_ascii=False)
        json_acompanhamentos = json.dumps(ACOMPANHAMENTOS_PARA_JS, indent=4, ensure_ascii=False)

        # O template permanece o mesmo, mas agora será preenchido com dados reais
        template_js = f"""
// Este arquivo foi gerado automaticamente pelo sistema. NÃO EDITE MANUALMENTE.
// Gerado por: gerador_dicionario.py (lendo do banco de dados)

export const menuData = {json_cardapio};

export const acompanhamentosDisponiveis = {json_acompanhamentos};
"""
        with open(ARQUIVO_SAIDA_JS, 'w', encoding='utf-8') as f:
            f.write(template_js.strip())
            
        print(f"[SUCESSO] Script JavaScript '{ARQUIVO_SAIDA_JS}' foi atualizado com os dados do banco.")
    except Exception as e:
        print(f"[ERRO] Falha ao gerar script JavaScript: {e}")


if __name__ == "__main__":
    print("\nIniciando a sincronização de dicionários...")
    # A geração do dicionario_pdv.py foi removida pois era baseada em dados falsos
    gerar_script_javascript()
    print("\nProcesso de geração concluído.")