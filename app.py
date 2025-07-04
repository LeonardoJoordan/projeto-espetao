from flask import Flask, render_template, request, redirect, url_for
import gerenciador_de_pedidos

app = Flask(__name__)

@app.route('/cliente', methods=['GET', 'POST'])
def tela_cliente():
    """
    Esta rota representa a tela do cliente.
    'GET' é para quando o cliente abre a tela.
    'POST' é para quando o cliente envia o formulário de novo pedido.
    """
    if request.method == 'POST':
        # 1. Coletar os dados do formulário (que ainda não existe)
        nome_cliente = request.form.get('nome_cliente', 'Cliente Padrão')
        
        # Simulação dos itens do pedido
        itens_pedido = [
            {'item': 'Espeto de Carne', 'quantidade': 1},
            {'item': 'Coca-Cola', 'quantidade': 1}
        ]
        metodo_pagamento = 'dinheiro'

        # 2. Chamar a função do nosso gerenciador (o "contrato")
        novo_id = gerenciador_de_pedidos.criar_novo_pedido(nome_cliente, itens_pedido, metodo_pagamento)
        
        print(f"DEBUG: Pedido criado com ID: {novo_id}")

        # 3. Redirecionar para uma página de confirmação (que ainda não existe)
        # Por enquanto, apenas redirecionamos de volta para a mesma tela.
        return redirect(url_for('tela_cliente'))

    # Se o método for GET, apenas mostramos a página (que ainda está vazia)
    return render_template('cliente.html')

# --- NOVA ROTA DA COZINHA ---
@app.route('/cozinha')
def tela_cozinha():
    """
    Esta rota representa a tela da cozinha.
    Ela busca os pedidos que precisam de atenção e os envia para o template.
    """
    # 1. Definir quais status a cozinha quer ver
    status_de_interesse = ['recebido']

    # 2. Chamar a função do nosso gerenciador (o "contrato")
    pedidos_para_cozinha = gerenciador_de_pedidos.obter_pedidos_por_status(status_de_interesse)
    
    print(f"DEBUG: Pedidos encontrados para a cozinha: {pedidos_para_cozinha}")

    # 3. Enviar a lista de pedidos para o template 'cozinha.html' renderizar
    return render_template('cozinha.html', pedidos=pedidos_para_cozinha)

@app.route('/')
def index():
    # Redireciona a rota principal para a tela do cliente por padrão
    return redirect(url_for('tela_cozinha'))

if __name__ == '__main__':
    # O 'debug=True' faz o servidor reiniciar automaticamente quando salvamos o arquivo.
    app.run(debug=True, host='0.0.0.0', port=5001)