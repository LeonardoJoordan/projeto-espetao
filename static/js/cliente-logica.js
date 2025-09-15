// static/js/cliente-logica.js

// ==========================================================
// NOVO: LÓGICA DE RESERVA DE ESTOQUE
// ==========================================================

// Gera um ID único para a sessão do carrinho deste cliente.
// Ele persistirá enquanto a página não for recarregada.
// Gera um ID "único" simples para a sessão do carrinho, compatível com http.
function gerarUUIDSimples() {
    return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
        (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    );
}
export const carrinhoId = gerarUUIDSimples();

/**
 * Função para criar uma versão "debounced" de uma função.
 * Ela só será executada após um certo tempo sem ser chamada.
 * @param {Function} func A função a ser executada.
 * @param {number} delay O tempo de espera em milissegundos.
 * @returns {Function}
 */
function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

/**
 * Chama a API para renovar o TTL de todas as reservas no carrinho atual.
 */
async function renovarSessaoAPI() {
    if (pedidoAtual.length === 0) return; // Não renova carrinhos vazios

    console.log(`%cRENEW: Renovando sessão para carrinho ${carrinhoId}`, 'color: dodgerblue');
    try {
        await fetch('/api/carrinho/renovar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ carrinho_id: carrinhoId })
        });
    } catch (error) {
        console.error("Falha ao renovar a sessão do carrinho:", error);
    }
}

// Criamos uma versão da função de renovação que só pode ser chamada a cada 10 segundos.
export const renovarSessaoDebounced = debounce(renovarSessaoAPI, 10000);


/**
 * Chama a API para reservar ou liberar um item.
 * @param {number} produtoId - O ID do produto.
 * @param {number} delta - A quantidade a ser alterada (+1 para reservar, -1 para liberar).
 * @returns {Promise<object>}
 */
export async function gerenciarReservaAPI(produtoId, delta) {
    try {
        const response = await fetch('/api/carrinho/item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                carrinho_id: carrinhoId,
                produto_id: produtoId,
                quantidade_delta: delta
            })
        });
        return await response.json();
    } catch (error) {
        console.error("Falha ao gerenciar reserva:", error);
        return { sucesso: false, mensagem: "Erro de conexão." };
    }
}

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
    // Garante que o item tenha um UID antes de ser adicionado, para estabilidade na ordenação.
    if (!item.uid) {
        item.uid = Date.now() + Math.random();
    }
    // A lógica para agrupar itens ou adicionar novos permanece a mesma.
    if (!item.customizacao) {
        const itemExistente = pedidoAtual.find(i => i.id === item.id && !i.customizacao);
        if (itemExistente) {
            itemExistente.quantidade += item.quantidade;
        } else {
            pedidoAtual.push(item);
        }
    } else {
        pedidoAtual.push(item);
    }

    console.log("Pedido atualizado (ordem de inserção):", pedidoAtual);
    normalizeAndSortPedido(); // Garante que a lista esteja sempre ordenada após uma adição.
}

/**
 * Reordena o array `pedidoAtual` de forma "in-place" (modificando o original)
 * seguindo a chave de ordenação canônica do sistema.
 * Chave: categoria_ordem ASC, produto_ordem ASC, id ASC, uid ASC.
 */
function normalizeAndSortPedido() {
    // Mapa de ordem para o ponto da carne.
    const pontoOrder = { 'mal': 0, 'ponto': 1, 'bem': 2 };

    // Helper para normalizar a lista de acompanhamentos de um item.
    const getExtrasKey = (item) => {
        const extras = item.customizacao?.acompanhamentos || [];
        if (extras.length === 0) return { count: 0, key: '' };

        const normalized = [...new Set(extras.map(e => e.trim().toLowerCase()))];
        normalized.sort((a, b) => a.localeCompare(b, 'pt-BR'));

        return {
            count: normalized.length,
            key: normalized.join('|')
        };
    };

    pedidoAtual.sort((a, b) => {
        // Nível 1: Ordem da Categoria (sem alteração)
        if (a.categoria_ordem !== b.categoria_ordem) {
            return a.categoria_ordem - b.categoria_ordem;
        }
        // Nível 2: Ordem do Produto (sem alteração)
        if (a.produto_ordem !== b.produto_ordem) {
            return a.produto_ordem - b.produto_ordem;
        }
        // Nível 3: ID do Produto (sem alteração)
        if (a.id !== b.id) {
            return a.id - b.id;
        }

        // --- NOVOS NÍVEIS DE ORDENAÇÃO ---

        // Nível 4: Ponto da Carne (mal < ponto < bem)
        const pa = pontoOrder[a.customizacao?.ponto] ?? Infinity;
        const pb = pontoOrder[b.customizacao?.ponto] ?? Infinity;
        if (pa !== pb) {
            return pa - pb;
        }

        // Nível 5: Acompanhamentos (qtd descrescente -> alfabético)
        const extrasA = getExtrasKey(a);
        const extrasB = getExtrasKey(b);

        if (extrasA.count !== extrasB.count) {
            return extrasB.count - extrasA.count; // Ordena por mais acompanhamentos primeiro
        }
        if (extrasA.key !== extrasB.key) {
            return extrasA.key.localeCompare(extrasB.key, 'pt-BR');
        }

        // Nível 6: UID (desempate final, sem alteração)
        return a.uid - b.uid;
    });
    console.log("Pedido foi normalizado com a nova lógica de ordenação (ponto e extras).");
}

/**
 * Remove um item do pedido com base no seu índice no array.
 * @param {number} index - O índice do item a ser removido.
 */
export function removerItemDoPedido(uid) {
    const indexParaRemover = pedidoAtual.findIndex(item => item.uid === uid);
    if (indexParaRemover > -1) {
        pedidoAtual.splice(indexParaRemover, 1);
        normalizeAndSortPedido(); // Garante que a lista esteja sempre ordenada após uma remoção.
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
export async function salvarPedido(metodoPagamento, modalidade) { // <-- NOVO PARÂMETRO
    if (pedidoAtual.length === 0) {
        alert("Seu carrinho está vazio!");
        return Promise.reject("Carrinho vazio");
    }

    console.log("Enviando para o servidor:", {
        nome_cliente: nomeClienteAtual,
        itens: pedidoAtual,
        metodo_pagamento: metodoPagamento,
        modalidade: modalidade // <-- NOVO DADO
    });

    try {
        const response = await fetch('/salvar_pedido', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                carrinho_id: carrinhoId,
                nome_cliente: nomeClienteAtual,
                itens: pedidoAtual, // A lista já está sempre ordenada
                metodo_pagamento: metodoPagamento,
                modalidade: modalidade
            })
        });

        if (!response.ok) {
            throw new Error('Erro ao salvar pedido. Status: ' + response.status);
        }

        const result = await response.json();

        // Em vez de alert e reload, chamamos o modal de sucesso.
        // O reload agora será responsabilidade do botão "Fechar" no modal.
        mostrarModalSucesso(nomeClienteAtual, result.senha_diaria);

        return result;

    } catch (error) {
        console.error("Falha ao enviar o pedido:", error);
        alert("Não foi possível registrar o pedido. Tente novamente.");
        return Promise.reject(error);
    }
}

/**
 * Pega um objeto de pedido decodificado e envia diretamente para a API /salvar_pedido.
 * Usado no Cenário A, quando há estoque para todos os itens.
 * @param {object} pedidoDecodificado - O objeto retornado pela função decodificarPedido.
 * @returns {Promise<object>} - A resposta do servidor.
 */
export async function enviarPedidoDecodificado(pedidoDecodificado) {
    // Recriamos a estrutura de dados que a API /salvar_pedido espera
    const payload = {
        carrinho_id: carrinhoId, // Usa o ID do carrinho da sessão atual
        nome_cliente: pedidoDecodificado.nomeCliente,
        itens: pedidoDecodificado.itens,
        metodo_pagamento: pedidoDecodificado.metodoPagamento,
        modalidade: pedidoDecodificado.modalidade
    };

    console.log("Enviando pedido decodificado diretamente para o servidor:", payload);

    try {
        const response = await fetch('/salvar_pedido', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error('Erro ao salvar pedido direto. Status: ' + response.status);
        }

        const result = await response.json();
        mostrarModalSucesso(payload.nome_cliente, result.senha_diaria); // Reutiliza o modal de sucesso
        return result;

    } catch (error) {
        console.error("Falha ao enviar o pedido decodificado:", error);
        alert("Não foi possível registrar o pedido pré-preenchido. Tente novamente.");
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

/**
 * Exibe um modal de sucesso com o nome do cliente e a senha do pedido.
 * @param {string} nomeCliente - O nome do cliente.
 * @param {string} senhaPedido - A senha gerada para o pedido.
 */
function mostrarModalSucesso(nomeCliente, senhaPedido) {
    const telaSenha = document.getElementById('tela-senha');
    const textoConfirmacao = document.getElementById('texto-confirmacao-senha');
    const mainContainer = document.getElementById('main-container');

    if (telaSenha && textoConfirmacao && mainContainer) {
        textoConfirmacao.innerHTML = `
            <div class="block text-2xl text-zinc-300 mb-2">Pedido recebido ${nomeCliente}!</div>
            <div class="block text-2xl text-red-500 mb-2">Dirija-se ao caixa para o pagamento.</div>
            <div class="block text-xl text-zinc-400 my-2">A senha do seu pedido é</div>
            <div class="block text-5xl font-bold text-green-400 font-mono">#${senhaPedido}</div>
        `;
        telaSenha.classList.remove('hidden');
        mainContainer.classList.add('content-blurred');
    }
}