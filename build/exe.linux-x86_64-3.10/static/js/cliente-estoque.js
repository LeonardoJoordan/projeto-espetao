// static/js/cliente-estoque.js

/**
 * @description O objeto que atua como nossa fonte da verdade local para o estoque.
 * A chave é o ID do produto, o valor é a quantidade disponível.
 * Ex: { '15': 10, '22': 5 }
 */
const restantePorProduto = {};

/**
 * @description Popula o estado inicial do estoque a partir dos cards de produto na tela.
 * Deve ser chamada uma vez, quando a página é carregada.
 * @param {NodeListOf<Element>} produtosCards - Uma lista de todos os elementos .product-card.
 */
export function inicializarEstoque(produtosCards) {
    produtosCards.forEach(card => {
        const id = card.dataset.id;
        // O valor inicial é o mesmo do data-estoque, que reflete a disponibilidade no momento do carregamento.
        const estoque = parseInt(card.dataset.estoque, 10);
        if (id && !isNaN(estoque)) {
            restantePorProduto[id] = estoque;
        }
    });
    console.log('%c[Estoque] Estado inicializado:', 'color: green', restantePorProduto);
}

/**
 * @description Consulta o estoque disponível para um determinado produto.
 * @param {number|string} produtoId - O ID do produto.
 * @returns {number} - A quantidade disponível. Retorna 0 se o produto não for encontrado.
 */
export function getEstoque(produtoId) {
    return restantePorProduto[produtoId] || 0;
}

/**
 * @description Atualiza o valor de estoque para um produto.
 * @param {number|string} produtoId - O ID do produto.
 * @param {number} quantidade - A nova quantidade disponível.
 */
export function setEstoque(produtoId, quantidade) {
    restantePorProduto[produtoId] = quantidade;
}