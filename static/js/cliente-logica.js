// static/js/cliente-logica.js

// ==========================================================
// 1. ESTADO DA APLICAÇÃO
// (As variáveis centrais que controlam o funcionamento)
// ==========================================================

// Exportamos as variáveis para que outros arquivos possam lê-las,
// mas a modificação delas deve ser feita apenas através das funções abaixo.
export let pedidoAtual = [];
export let nomeClienteAtual = '';


// ==========================================================
// 2. FUNÇÕES DE MANIPULAÇÃO DE ESTADO
// (As "ferramentas" que alteram as variáveis de estado)
// ==========================================================

/**
 * Define o nome do cliente para a sessão de pedido atual.
 * @param {string} nome - O nome do cliente.
 */
export function setNomeCliente(nome) {
    nomeClienteAtual = nome;
    console.log(`Sessão de pedido iniciada para: ${nomeClienteAtual}`);
}

/**
 * Adiciona um item (ou um grupo de itens) ao pedido.
 * @param {object} item - O objeto do item a ser adicionado.
 */
export function adicionarItemAoPedido(item) {
    // Se o item não tem customização, verificamos se já existe um igual no carrinho.
    if (!item.customizacao) {
        const itemExistente = pedidoAtual.find(i => i.id === item.id && !i.customizacao);
        if (itemExistente) {
            itemExistente.quantidade += item.quantidade;
        } else {
            pedidoAtual.push(item);
        }
    } else {
        // Se for customizado, é sempre um novo item no carrinho.
        pedidoAtual.push(item);
    }
    console.log("Pedido atualizado:", pedidoAtual);
}

/**
 * Remove um item do pedido com base no seu índice no array.
 * @param {number} index - O índice do item a ser removido.
 */
export function removerItemDoPedido(index) {
    if (index > -1 && index < pedidoAtual.length) {
        pedidoAtual.splice(index, 1);
        console.log("Item removido. Pedido atual:", pedidoAtual);
    }
}

/**
 * Limpa completamente o pedido e o nome do cliente, resetando o estado para um novo cliente.
 * Esta função recarrega a página para garantir que tudo volte ao estado inicial.
 */
export function limparPedido() {
    pedidoAtual = [];
    nomeClienteAtual = '';
    console.log("Estado do pedido foi resetado.");
    // Recarrega a página para voltar ao estado inicial, como no código original
    location.reload();
}


// ==========================================================
// 3. FUNÇÕES DE COMUNICAÇÃO COM O BACKEND
// ==========================================================

/**
 * Envia o pedido finalizado para o servidor.
 * @param {string} metodoPagamento - O método de pagamento escolhido ('pix', 'cartao', 'dinheiro').
 * @returns {Promise<object>} - Uma promessa que resolve com a resposta do servidor se bem-sucedido.
 */
export async function salvarPedido(metodoPagamento) {
    if (pedidoAtual.length === 0) {
        alert("Seu carrinho está vazio!");
        return Promise.reject("Carrinho vazio");
    }

    console.log("Enviando para o servidor:", {
        nome_cliente: nomeClienteAtual,
        itens: pedidoAtual,
        metodo_pagamento: metodoPagamento
    });

    try {
        const response = await fetch('/salvar_pedido', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nome_cliente: nomeClienteAtual,
                itens: pedidoAtual,
                metodo_pagamento: metodoPagamento
            })
        });

        if (!response.ok) {
            throw new Error('Erro ao salvar pedido. Status: ' + response.status);
        }

        const result = await response.json();
        alert(`Pedido #${result.pedido_id} recebido com sucesso!`);
        
        // Após salvar com sucesso, recarrega a página para um novo pedido
        location.reload();
        
        return result;

    } catch (error) {
        console.error("Falha ao enviar o pedido:", error);
        alert("Não foi possível registrar o pedido. Tente novamente.");
        // Rejeita a promessa para que o código que chamou saiba que deu erro.
        return Promise.reject(error);
    }
}

// ==========================================================
// 4. FUNÇÕES AUXILIARES (Helpers)
// ==========================================================

/**
 * Formata um número para a moeda brasileira (BRL).
 * @param {number} value - O valor numérico.
 * @returns {string} - O valor formatado como string (ex: "R$ 10,50").
 */
export function formatCurrency(value) {
    if (typeof value !== 'number') value = 0;
    return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}
