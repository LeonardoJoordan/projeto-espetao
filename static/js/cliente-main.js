// static/js/cliente-main.js

// ==========================================================
// 1. IMPORTAÇÕES
// ==========================================================
import {
    pedidoAtual,
    setNomeCliente,
    adicionarItemAoPedido,
    removerItemDoPedido,
    limparPedido,
    salvarPedido,
    formatCurrency,
    carrinhoId, // NOVO
    gerenciarReservaAPI, // NOVO
    renovarSessaoDebounced // NOVO
} from './cliente-logica.js';

import * as estoqueState from './cliente-estoque.js';


// ==========================================================
// 2. REFERÊNCIAS AO DOM E VARIÁVEIS DE UI
// ==========================================================
const mainContainer = document.getElementById('main-container');
const btnAcaoPrincipal = document.getElementById('btn-acao-principal');
const mainContent = document.getElementById('main-content');
const navLinks = document.querySelectorAll('#nav-categorias a');
const sections = document.querySelectorAll('.categoria-secao');
const lastSection = sections.length > 0 ? sections[sections.length - 1] : null;

// Elementos da tela de senha
const telaSenha = document.getElementById('tela-senha');
const btnIrCardapio = document.getElementById('btn-ir-cardapio');
const placeholderNome = document.getElementById('placeholder-nome');
const textoConfirmacaoSenha = document.getElementById('texto-confirmacao-senha');

// Elementos do fluxo de teclado
const telaInicial = document.getElementById('tela-inicial');
const telaTeclado = document.getElementById('tela-teclado');
const btnNovoPedido = document.getElementById('btn-novo-pedido');
const btnIniciar = document.getElementById('btn-iniciar');
const campoTextoNome = document.getElementById('texto-nome');
const tecladoContainer = document.getElementById('teclado-virtual');

// Elementos dos popups
const modalSimples = document.getElementById('modal-quantidade-simples');
const modalCustomizacao = document.getElementById('modal-customizacao');
const modalConfirmacao = document.getElementById('modal-confirmacao-pedido');

// Variáveis de controle de listeners para evitar duplicação
let eventoPopupSimplesAtivo = null;
let eventoPopupAtivo = null;

// ==========================================================
// 2.5. LÓGICA DE SESSÃO E TEMPO REAL (SOCKET.IO)
// ==========================================================

let socket = null;
if (window.io && typeof window.io === 'function') {
  socket = io();

  socket.on('connect', () => {
      console.log('Conectado ao servidor Socket.IO');
  });

    // Listener para receber atualizações de disponibilidade de estoque
    socket.on('atualizacao_disponibilidade', (payload) => {
        console.log('%cEstoque Atualizado via Socket.IO:', 'color: lightblue', payload);

        payload.updates.forEach(update => {
            const produtoId = update.produto_id;
            const disponivel = update.disponivel ?? update.disponibilidade_atual ?? 0;
            
            // PASSO 1: ATUALIZA NOSSO NOVO ESTADO COMPARTILHADO
            estoqueState.setEstoque(produtoId, disponivel);

            // PASSO 2: ATUALIZA A UI IMEDIATAMENTE
            const productCard = document.querySelector(`.product-card[data-id="${produtoId}"]`);
            if (productCard) {
                const addButton = productCard.querySelector('.add-button');
                // Sincroniza o data-attribute também, por consistência
                productCard.dataset.estoque = disponivel;

                if (disponivel <= 0) {
                    addButton.disabled = true;
                    addButton.style.backgroundColor = '#52525B';
                    addButton.style.cursor = 'not-allowed';
                } else {
                    addButton.disabled = false;
                    addButton.style.backgroundColor = '';
                    addButton.style.cursor = 'pointer';
                }
            }
        });
    });

} else {
  console.warn('Socket.IO não disponível; seguindo sem tempo real.');
}

//

// Listeners globais para renovar a sessão do carrinho em qualquer interação
mainContent.addEventListener('scroll', renovarSessaoDebounced); // Usando a referência já existente


// ==========================================================
// 3. FUNÇÕES DE UI (Manipulação da Interface)
// ==========================================================

async function mostrarAlerta(titulo, mensagem) {
    const modal = document.getElementById('modal-alerta');
    const tituloEl = document.getElementById('titulo-alerta');
    const mensagemEl = document.getElementById('mensagem-alerta');
    const btnOk = document.getElementById('btn-ok-alerta');

    if (!modal || !tituloEl || !mensagemEl || !btnOk) {
        console.error("Elementos do modal de alerta não encontrados.");
        alert(`${titulo}\n\n${mensagem}`); // Fallback para o alert nativo
        return;
    }

    return new Promise(resolve => {
        tituloEl.textContent = titulo;
        mensagemEl.textContent = mensagem;

        modal.classList.remove('hidden');
        mainContainer.classList.add('content-blurred');

        btnOk.addEventListener('click', () => {
            modal.classList.add('hidden');
            mainContainer.classList.remove('content-blurred');
            resolve();
        }, { once: true }); // O listener é removido automaticamente após o primeiro clique
    });
}

function atualizarBotaoPrincipal() {
    if (!btnAcaoPrincipal) return;

    if (pedidoAtual.length === 0) {
        btnAcaoPrincipal.textContent = 'Cancelar Pedido';
        btnAcaoPrincipal.classList.remove('btn-finalizar');
        btnAcaoPrincipal.classList.add('btn-cancelar');
    } else {
        const totalItens = pedidoAtual.reduce((acc, item) => acc + item.quantidade, 0);
        btnAcaoPrincipal.innerHTML = `Finalizar Pedido<br>(${totalItens} itens)`;
        btnAcaoPrincipal.classList.remove('btn-cancelar');
        btnAcaoPrincipal.classList.add('btn-finalizar');
    }
}

function updateActiveLinkOnScroll() {
    if (!mainContent || !lastSection) return;
    const containerTop = mainContent.getBoundingClientRect().top;
    let currentSectionId = '';
    for (const section of sections) {
        const rect = section.getBoundingClientRect();
        if (rect.bottom > containerTop + 1) {
            currentSectionId = section.id;
            break;
        }
    }
    const isAtBottom = mainContent.scrollTop + mainContent.clientHeight >= mainContent.scrollHeight - 5;
    if (isAtBottom) {
        currentSectionId = lastSection.id;
    }
    navLinks.forEach(link => {
        link.classList.toggle('active', link.getAttribute('href').substring(1) === currentSectionId);
    });
}

async function abrirPopupSimples(productCard) { // <-- Adicionamos 'async'
    const idProduto = parseInt(productCard.dataset.id);

    if (!modalSimples) return; // A validação original permanece

    // Remove o event listener anterior se existir
    if (eventoPopupSimplesAtivo) {
        modalSimples.removeEventListener('click', eventoPopupSimplesAtivo);
    }

    const nomeProduto = productCard.dataset.nome;
    const precoProduto = parseFloat(productCard.dataset.preco);

    modalSimples.innerHTML = `
        <div class="popup-container popup-enter bg-zinc-800 rounded-2xl shadow-2xl w-full max-w-md border border-zinc-700 flex flex-col">
            <header class="p-6 border-b border-zinc-700">
                <h2 class="text-2xl font-bold text-white">${nomeProduto}</h2>
                <p class="text-zinc-400">Selecione a quantidade desejada.</p>
            </header>
            <main class="p-6 flex-grow flex flex-col items-center justify-center">
                <div class="quantidade-control">
                    <button id="btn-diminuir-simples" class="quantidade-btn"><i class="fas fa-minus"></i></button>
                    <div id="quantidade-display-simples" class="quantidade-display">1</div>
                    <button id="btn-aumentar-simples" class="quantidade-btn"><i class="fas fa-plus"></i></button>
                </div>
            </main>
            <footer class="p-6 border-t border-zinc-700 bg-zinc-900/50 flex justify-between items-center">
                <button id="btn-cancelar-simples" class="btn-acao btn-cancelar">Cancelar</button>
                <div class="flex items-center gap-4">
                    <div class="text-right">
                        <div class="text-sm text-zinc-400">Total</div>
                        <div id="preco-total-simples" class="text-2xl font-bold text-green-400">R$ 0,00</div>
                    </div>
                    <button id="btn-adicionar-simples" class="btn-acao btn-adicionar">Adicionar</button>
                </div>
            </footer>
        </div>
    `;

    modalSimples.classList.remove('hidden');

    // NOVO: referenciar para remover depois
    let onBackdropClick = null;
    let onEscKey = null;

    // NOVO: Fechar por clique no backdrop (fora do container)
    onBackdropClick = (ev) => {
    // fecha só se clicou diretamente no backdrop (o próprio modalSimples)
    if (ev.target === modalSimples) {
        fecharPopupSimples('external');
    }
    };
    modalSimples.addEventListener('mousedown', onBackdropClick);

    // NOVO: Fechar por tecla ESC
    onEscKey = (ev) => {
    if (ev.key === 'Escape') {
        fecharPopupSimples('external');
    }
    };
    window.addEventListener('keydown', onEscKey);

    mainContainer.classList.add('content-blurred');

    const quantidadeDisplay = document.getElementById('quantidade-display-simples');
    const precoTotalDisplay = document.getElementById('preco-total-simples');
    let quantidade = 1;

    // NOVO: guardas para evitar liberação dupla
    let popupFechado = false;



    /**
     * NOVO: Fecha o popup garantindo liberação de reservas quando necessário.
     * @param {'cancel'|'confirm'|'external'} reason - motivo do fechamento
     */
    const fecharPopupSimples = async (reason) => {
    if (popupFechado) return; // evita corrida/double call
    popupFechado = true;

    const idProduto = parseInt(productCard.dataset.id);

    // Se NÃO confirmou, libera tudo que está reservado neste popup
    if (reason !== 'confirm' && quantidade > 0) {
        const resultado = await gerenciarReservaAPI(idProduto, -quantidade);
        if (resultado?.produtos_afetados?.length) {
        const upd = resultado.produtos_afetados[0];
        estoqueState.setEstoque(upd.produto_id, upd.disponivel);
        }
    }

    // Esconde UI e limpa blur
    modalSimples.classList.add('hidden');
    mainContainer.classList.remove('content-blurred');

    // Remove listeners do popup
    if (eventoPopupSimplesAtivo) {
        modalSimples.removeEventListener('click', eventoPopupSimplesAtivo);
        eventoPopupSimplesAtivo = null;
    }
    // Remove listeners externos
    if (onBackdropClick) {
        modalSimples.removeEventListener('mousedown', onBackdropClick);
        onBackdropClick = null;
    }
    if (onEscKey) {
        window.removeEventListener('keydown', onEscKey);
        onEscKey = null;
    }
    };

    function atualizarInterfaceSimples() {
        quantidadeDisplay.textContent = quantidade;
        const total = quantidade * precoProduto;
        precoTotalDisplay.textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
    }

    eventoPopupSimplesAtivo = async (event) => { // <-- Função agora é async
        const target = event.target.closest('button');
        if (!target) return;

        const idProduto = parseInt(productCard.dataset.id);

        if (target.id === 'btn-aumentar-simples') {
            // PONTO DE ATENÇÃO #1 e #3: VERIFICAÇÃO PREVENTIVA

            const resultadoReserva = await gerenciarReservaAPI(idProduto, 1);
            
            // PONTO DE ATENÇÃO #5: Sincroniza o estado local com a resposta da API
            if (resultadoReserva.produtos_afetados && resultadoReserva.produtos_afetados.length > 0) {
                const update = resultadoReserva.produtos_afetados[0];
                estoqueState.setEstoque(update.produto_id, update.disponivel);
            }

            if (resultadoReserva.sucesso) {
                quantidade++;
                atualizarInterfaceSimples();
            } else {
                await mostrarAlerta('Item Esgotado', resultadoReserva.mensagem || 'Não há mais unidades disponíveis.');
            }

        } else if (target.id === 'btn-diminuir-simples') {
            if (quantidade > 1) {
                const resultadoLiberacao = await gerenciarReservaAPI(idProduto, -1);

                // Sincroniza o estado local com a nova disponibilidade retornada pelo servidor.
                if (resultadoLiberacao.produtos_afetados && resultadoLiberacao.produtos_afetados.length > 0) {
                    const update = resultadoLiberacao.produtos_afetados[0];
                    estoqueState.setEstoque(update.produto_id, update.disponivel);
                }

                // Apenas decrementa a quantidade local se o servidor confirmar a liberação.
                if (resultadoLiberacao.sucesso) {
                    quantidade--;
                    atualizarInterfaceSimples();
                } else {
                    // Em caso de falha (ex: problema de rede), é mais seguro notificar o usuário.
                    await mostrarAlerta('Erro de Comunicação', 'Não foi possível atualizar a quantidade. Por favor, tente cancelar e adicionar o item novamente.');
                }
            }
        }   else if (target.id === 'btn-cancelar-simples') {
            await fecharPopupSimples('cancel');

        } else if (target.id === 'btn-adicionar-simples') {
            const novoItem = { id: idProduto, nome: productCard.dataset.nome, preco: parseFloat(productCard.dataset.preco), quantidade: quantidade, requer_preparo: parseInt(productCard.dataset.requerPreparo), categoria_ordem: parseInt(productCard.dataset.categoriaOrdem), produto_ordem: parseInt(productCard.dataset.produtoOrdem) };
            adicionarItemAoPedido(novoItem);
            atualizarBotaoPrincipal();
            await fecharPopupSimples('confirm'); // <-- não libera reservas
            modalSimples.classList.add('hidden');
            mainContainer.classList.remove('content-blurred');
        }
    };

    modalSimples.addEventListener('click', eventoPopupSimplesAtivo);
    atualizarInterfaceSimples();
}

async function abrirPopupCustomizacao(productCard) { // Adicionamos 'async' aqui
    if (!modalCustomizacao) return;

    // Remove o event listener anterior para segurança
    if (eventoPopupAtivo) {
        modalCustomizacao.removeEventListener('click', eventoPopupAtivo);
    }

    // PASSO 1: Buscar os acompanhamentos da API ANTES de montar o popup.
    let acompanhamentosDisponiveis = [];
    try {
        const response = await fetch('/api/acompanhamentos_visiveis');
        if (!response.ok) throw new Error('Falha na rede');
        acompanhamentosDisponiveis = await response.json();
    } catch (error) {
        console.error("Erro ao buscar acompanhamentos:", error);
        // Podemos alertar o usuário ou apenas não mostrar os extras.
    }

    const nomeProduto = productCard.dataset.nome;
    const precoProduto = parseFloat(productCard.dataset.preco);

    // A estrutura principal do modal permanece a mesma.
    modalCustomizacao.innerHTML = `
        <div class="popup-container popup-enter bg-zinc-800 rounded-3xl shadow-2xl w-full max-w-4xl border border-zinc-600 flex flex-col relative z-10 max-h-[90vh]">
            <header class="header-bg p-8 border-b border-zinc-600 relative">
                <div class="flex justify-between items-start relative z-10">
                    <div class="flex-1">
                        <div class="flex items-center gap-3 mb-2">
                            <div class="w-12 h-12 bg-orange-600 rounded-full flex items-center justify-center">
                                <i class="fas fa-fire text-white text-lg"></i>
                            </div>
                            <h2 class="text-3xl font-bold text-white">${nomeProduto}</h2>
                        </div>
                        <p class="text-zinc-300 text-lg">Escolha como você quer!</p>
                    </div>
                    <div class="quantidade-control">
                        <button id="btn-diminuir-popup" class="quantidade-btn"><i class="fas fa-minus"></i></button>
                        <div id="quantidade-display-popup" class="quantidade-display">1</div>
                        <button id="btn-aumentar-popup" class="quantidade-btn"><i class="fas fa-plus"></i></button>
                    </div>
                </div>
            </header>
            <main id="linhas-customizacao-popup" class="p-8 space-y-8 overflow-y-auto flex-1"></main>
            <footer class="p-8 border-t border-zinc-600 bg-zinc-900/50 flex justify-between items-center">
                <button id="btn-cancelar-item-popup" class="btn-acao btn-cancelar">
                    <i class="fas fa-times mr-2"></i>Cancelar
                </button>
                <div class="flex items-center gap-4">
                    <div class="text-right">
                        <div class="text-sm text-zinc-400">Total</div>
                        <div id="preco-total-popup" class="text-2xl font-bold text-green-400">R$ 0,00</div>
                    </div>
                    <button id="btn-adicionar-pedido-popup" class="btn-acao btn-adicionar">
                        <i class="fas fa-cart-plus mr-2"></i>Adicionar ao Pedido
                    </button>
                </div>
            </footer>
        </div>
    `;

    modalCustomizacao.classList.remove('hidden');

    const quantidadeDisplay = document.getElementById('quantidade-display-popup');
    const precoTotalDisplay = document.getElementById('preco-total-popup');
    const containerLinhas = document.getElementById('linhas-customizacao-popup');
    let quantidade = 1;

    // PASSO 2: A função de criar a linha agora RECEBE a lista de acompanhamentos.
    function criarLinhaHtml(numeroItem, acompanhamentos) {
        const uniqueIdPrefix = `item-${numeroItem}-`;

        // Gera os checkboxes dos acompanhamentos dinamicamente
        const acompanhamentosHtml = acompanhamentos.map(extra => `
            <label class="extra-item" for="${uniqueIdPrefix}${extra.id}">
                <input type="checkbox" id="${uniqueIdPrefix}${extra.id}" value="${extra.nome}" class="hidden">
                ${extra.nome}
            </label>
        `).join('');

        return `
            <div class="espetinho-card p-6 rounded-2xl item-customizacao">
                <h3 class="text-xl font-bold text-orange-400 mb-6">Espetinho #${numeroItem}</h3>
                <div class="space-y-6">
                    <div>
                        <h4 class="text-lg font-semibold mb-4">Ponto da Carne</h4>
                        <div class="ponto-options grid grid-cols-3 gap-4">
                            <label class="ponto-option" for="${uniqueIdPrefix}mal">
                                <input type="radio" id="${uniqueIdPrefix}mal" name="${uniqueIdPrefix}ponto" value="mal" class="hidden">
                                Mal Passado
                            </label>
                            <label class="ponto-option selected" for="${uniqueIdPrefix}ponto">
                                <input type="radio" id="${uniqueIdPrefix}ponto" name="${uniqueIdPrefix}ponto" value="ponto" class="hidden" checked>
                                Ao Ponto
                            </label>
                            <label class="ponto-option" for="${uniqueIdPrefix}bem">
                                <input type="radio" id="${uniqueIdPrefix}bem" name="${uniqueIdPrefix}ponto" value="bem" class="hidden">
                                Bem Passado
                            </label>
                        </div>
                    </div>
                    <div>
                        <h4 class="text-lg font-semibold">Complete seu espetinho</h4>
                        <p class="text-sm text-zinc-400 mb-4">Acompanhamentos inclusos no valor.</p>
                        <div class="extras-grid grid grid-cols-2 gap-3">
                            ${acompanhamentosHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    // A função de atualizar a UI agora passa a lista de acompanhamentos para a função de criar a linha.
    function atualizarInterfacePopup() {
        quantidadeDisplay.textContent = quantidade;
        containerLinhas.innerHTML = '';
        for (let i = 1; i <= quantidade; i++) {
            containerLinhas.innerHTML += criarLinhaHtml(i, acompanhamentosDisponiveis);
        }
        const total = quantidade * precoProduto;
        precoTotalDisplay.textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
    }

    // A lógica de eventos permanece a mesma...
    eventoPopupAtivo = async (event) => { // <-- Função agora é async
        const target = event.target;
        const idProduto = parseInt(productCard.dataset.id);
        
        if (target.closest('#btn-aumentar-popup')) {
            // PONTO DE ATENÇÃO #1 e #3: VERIFICAÇÃO PREVENTIVA
            const estoqueDisponivel = estoqueState.getEstoque(idProduto);
            if (estoqueDisponivel <= 0) {
                await mostrarAlerta('Putz, esses são os últimos', `Infelizmente já foi quase tudo, esses são os últimos ${estoqueDisponivel} em estoque.`);
                return;
            }

            const resultadoReserva = await gerenciarReservaAPI(idProduto, 1);
            
            // PONTO DE ATENÇÃO #5: Sincroniza o estado local com a resposta da API
            if (resultadoReserva.produtos_afetados && resultadoReserva.produtos_afetados.length > 0) {
                const update = resultadoReserva.produtos_afetados[0];
                estoqueState.setEstoque(update.produto_id, update.disponivel);
            }

            if (resultadoReserva.sucesso) {
                quantidade++;
                containerLinhas.insertAdjacentHTML('beforeend', criarLinhaHtml(quantidade, acompanhamentosDisponiveis));
                quantidadeDisplay.textContent = quantidade;
                precoTotalDisplay.textContent = formatCurrency(quantidade * precoProduto);
            } else {
                await mostrarAlerta('Item Esgotado', resultadoReserva.mensagem || 'Não há mais unidades disponíveis.');
            }
        } else if (target.closest('#btn-diminuir-popup')) {
            if (quantidade > 1) {
                await gerenciarReservaAPI(idProduto, -1); // Libera a reserva
                quantidade--;
                if (containerLinhas.lastElementChild) containerLinhas.lastElementChild.remove();
                quantidadeDisplay.textContent = quantidade;
                precoTotalDisplay.textContent = formatCurrency(quantidade * precoProduto);
            }
        } else if (target.closest('#btn-cancelar-item-popup')) {
            // Libera a quantidade TOTAL que estava reservada neste popup
            await gerenciarReservaAPI(idProduto, -quantidade);
            modalCustomizacao.classList.add('hidden');
            mainContainer.classList.remove('content-blurred');
        } else if (target.closest('#btn-adicionar-pedido-popup')) {
            document.querySelectorAll('.item-customizacao').forEach(itemNode => {
                const ponto = itemNode.querySelector('input[name$="ponto"]:checked').value;
                const acompanhamentos = Array.from(itemNode.querySelectorAll('.extras-grid input:checked')).map(cb => cb.value);
                const customizacao = { ponto, acompanhamentos };
                const novoItem = { id: idProduto, nome: nomeProduto, preco: parseFloat(productCard.dataset.preco), quantidade: 1, customizacao, requer_preparo: parseInt(productCard.dataset.requerPreparo), categoria_ordem: parseInt(productCard.dataset.categoriaOrdem), produto_ordem: parseInt(productCard.dataset.produtoOrdem) };
                adicionarItemAoPedido(novoItem);
            });
            atualizarBotaoPrincipal();
            modalCustomizacao.classList.add('hidden');
            mainContainer.classList.remove('content-blurred');
        } else {
            // Lógica de UI para seleção de ponto/extras (mantida)
            const pontoOption = target.closest('.ponto-option');
            if (pontoOption) {
                pontoOption.closest('.ponto-options').querySelectorAll('.ponto-option').forEach(opt => opt.classList.remove('selected'));
                pontoOption.classList.add('selected');
                pontoOption.querySelector('input').checked = true;
            }
            const extraItem = target.closest('.extra-item');
            if (extraItem) {
                event.preventDefault();
                const input = extraItem.querySelector('input');
                input.checked = !input.checked;
                extraItem.classList.toggle('selected', input.checked);
            }
        }
    };

    modalCustomizacao.addEventListener('click', eventoPopupAtivo);
    atualizarInterfacePopup();
}

function abrirPopupConfirmacao() {
    if (!modalConfirmacao || pedidoAtual.length === 0) return;

    const listaContainer = document.getElementById('lista-itens-confirmacao');
    const totalDisplay = document.getElementById('total-confirmacao');
    
    // Acessa diretamente o pedidoAtual, que já está sempre ordenado.
    const valorTotal = pedidoAtual.reduce((acc, item) => acc + (item.preco * item.quantidade), 0);
    totalDisplay.textContent = formatCurrency(valorTotal);

    listaContainer.innerHTML = pedidoAtual.map(item => {
        let detalhesItem = '';
        if (item.customizacao) {
            const mapaPonto = { 'mal': 'Mal Passado', 'ponto': 'Ao Ponto', 'bem': 'Bem Passado' };
            const pontoTexto = mapaPonto[item.customizacao.ponto] || item.customizacao.ponto;
            
            // CORREÇÃO APLICADA AQUI: lendo 'acompanhamentos' em vez de 'extras'.
            const extrasTexto = item.customizacao.acompanhamentos && item.customizacao.acompanhamentos.length > 0 
                ? `com ${item.customizacao.acompanhamentos.join(', ')}` 
                : 'sem extras';

            detalhesItem = `<div class="text-base font-semibold text-white">${item.nome}</div><div class="text-sm text-zinc-400 pl-4">↳ ${pontoTexto}, ${extrasTexto}</div>`;
        } else {
            detalhesItem = `<div class="text-base font-semibold text-white">${item.quantidade}x ${item.nome}</div>`;
        }
        
        // E também usamos aqui para os subtotais
        const subtotalFormatado = formatCurrency(item.preco * item.quantidade);

        return `
            <div class="flex items-center justify-between bg-zinc-900/50 p-3 rounded-lg">
                <div>${detalhesItem}</div>
                <div class="flex items-center gap-4">
                    <span class="font-semibold w-24 text-right">${subtotalFormatado}</span>
                    <button class="btn-remover-item text-red-500 hover:text-red-400" data-uid="${item.uid}" title="Remover Item">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </div>`;
    }).join('');

    modalConfirmacao.classList.remove('hidden');
    mainContainer.classList.add('content-blurred');
}

// ==========================================================
// 4. LÓGICA DO TECLADO VIRTUAL
// ==========================================================
let nomeDigitadoTemp = '';
let proximoAcento = null;
const acentosMap = {
    '´': { 'A': 'Á', 'E': 'É', 'I': 'Í', 'O': 'Ó', 'U': 'Ú' },
    '~': { 'A': 'Ã', 'O': 'Õ' }
};
const layoutTeclas = [
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', '´', '~'],
    ['ESPAÇO', 'Backspace']
];



function atualizarVisualAcento() {
    document.querySelectorAll('.keyboard-key').forEach(btn => {
        if (btn.dataset.key === '´' || btn.dataset.key === '~') {
            btn.classList.toggle('accent-active', btn.dataset.key === proximoAcento);
        }
    });
}

function atualizarTextoTeclado() {
    if (campoTextoNome && placeholderNome) {
        if (nomeDigitadoTemp === '') {
            placeholderNome.classList.remove('hidden');
            campoTextoNome.textContent = '';
        } else {
            placeholderNome.classList.add('hidden');
            campoTextoNome.textContent = nomeDigitadoTemp;
        }
    }
}


// ==========================================================
// 5. EVENT LISTENERS
// ==========================================================

// Listener para o botão "NOVO PEDIDO"
if (btnNovoPedido) {
    btnNovoPedido.addEventListener('click', () => {
        if (telaInicial) telaInicial.classList.add('hidden');
        if (telaTeclado) telaTeclado.classList.remove('hidden');
        if (mainContainer) mainContainer.classList.add('content-blurred');

        ajustarLarguraTeclas();
    });
}

// Listener para as teclas do teclado
if (tecladoContainer) {
    tecladoContainer.addEventListener('click', (e) => {
        const key = e.target.closest('button')?.dataset.key;
        if (!key) return;

        // Lógica especial para tela cheia
        if (nomeDigitadoTemp === '#telacheia') {
            if (document.fullscreenElement) {
                if (window.Android && typeof window.Android.sairDoApp === 'function') {
                    window.Android.sairDoApp();
                } else {
                    document.exitFullscreen();
                }
            } else {
                document.documentElement.requestFullscreen().catch(err => {
                    alert(`Erro ao tentar entrar em tela cheia: ${err.message}`);
                });
            }
            nomeDigitadoTemp = '';
            atualizarTextoTeclado();
            return;
        }

        if (key === '´' || key === '~') {
            proximoAcento = (proximoAcento === key) ? null : key;
            atualizarVisualAcento();
            return;
        }

        let charToAdd = key;
        if (proximoAcento) {
            const vogalAcentuada = acentosMap[proximoAcento]?.[key];
            charToAdd = vogalAcentuada ? vogalAcentuada : proximoAcento + key;
            proximoAcento = null;
            atualizarVisualAcento();
        }

        if (key === 'Backspace') {
            nomeDigitadoTemp = nomeDigitadoTemp.slice(0, -1);
        } else if (key === 'ESPAÇO') {
            if (nomeDigitadoTemp.length < 20) nomeDigitadoTemp += ' ';
        } else {
            if (nomeDigitadoTemp.length < 20) nomeDigitadoTemp += charToAdd;
        }
        atualizarTextoTeclado();
    });
}

// Listener para o botão "Iniciar Pedido" do teclado
if (btnIniciar) {
    btnIniciar.addEventListener('click', async () => {
        const nomeFinal = nomeDigitadoTemp.trim();
        if (nomeFinal === '') {
            await mostrarAlerta("Nome Inválido", "Por favor, digite um nome para o pedido.");
            return;
        }
        setNomeCliente(nomeFinal);

        // AGORA, VAI DIRETO PARA O CARDÁPIO
        if (telaTeclado) telaTeclado.classList.add('hidden');
        if (mainContainer) mainContainer.classList.remove('content-blurred');

        // Limpa o nome temporário e atualiza a UI para o estado inicial do cardápio
        nomeDigitadoTemp = '';
        atualizarTextoTeclado();
        atualizarBotaoPrincipal();
    });
}

// Listener para o botão "Fechar" da tela de sucesso (antigo btnIrCardapio)
if (btnIrCardapio) {
    btnIrCardapio.addEventListener('click', () => {
        // A única ação agora é recarregar a página para um novo pedido.
        location.reload();
    });
}

// Listener para o botão de ação principal (Finalizar/Cancelar)
if (btnAcaoPrincipal) {
    btnAcaoPrincipal.addEventListener('click', () => {
        if (pedidoAtual.length === 0) {
            limparPedido();
        } else {
            abrirPopupConfirmacao();
        }
    });
}

// Listener para a rolagem do menu
if (mainContent) {
    mainContent.addEventListener('scroll', updateActiveLinkOnScroll);
}

// Listener para os cliques nos links da sidebar (rolagem suave)
navLinks.forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        const alvo = document.querySelector(link.getAttribute('href'));
        if(alvo) {
            alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// Listener de clique geral (REVISADO para incluir reserva de estoque)
document.addEventListener('click', async (event) => { // <--- Função agora é ASYNC
    const addButton = event.target.closest('.add-button');
    if (!addButton || addButton.disabled) return; // Ignora cliques em botões desabilitados

    const productCard = addButton.closest('.product-card');
    const produtoId = productCard.dataset.id;

    // PONTO DE ATENÇÃO #1 e #3: VERIFICAÇÃO PREVENTIVA
    const estoqueDisponivel = estoqueState.getEstoque(produtoId);
    if (estoqueDisponivel <= 0) {
        await mostrarAlerta('Putz, esses são os últimos', `Infelizmente já foi quase tudo, esses são os últimos ${estoqueDisponivel} em estoque.`);
        return; // Impede a continuação
    }

    // Animação de "fogo" (lógica mantida)
    addButton.classList.add('firing');
    setTimeout(() => addButton.classList.remove('firing'), 300);

    // Tenta fazer a reserva na API
    const resultadoReserva = await gerenciarReservaAPI(produtoId, 1);

    // PONTO DE ATENÇÃO #5: Sincroniza o estado local com a resposta da API
    if (resultadoReserva.produtos_afetados && resultadoReserva.produtos_afetados.length > 0) {
        const update = resultadoReserva.produtos_afetados[0];
        estoqueState.setEstoque(update.produto_id, update.disponivel);
    }

    if (resultadoReserva.sucesso) {
        console.log(`Reserva para produto ${produtoId} bem-sucedida.`);
        // Se a reserva funcionou, executa a lógica original de abrir o popup
        if (productCard && productCard.dataset.id) {
            const categoriaNome = productCard.dataset.categoriaNome;
            if (categoriaNome === 'Espetinhos') {
                abrirPopupCustomizacao(productCard);
            } else {
                abrirPopupSimples(productCard);
            }
        }
    } else {
        // Se a reserva falhou (concorrência), informa o usuário e atualiza a UI
        console.warn(`Reserva para produto ${produtoId} falhou:`, resultadoReserva.mensagem);
        await mostrarAlerta('Item Esgotado', 'Desculpe, este item acabou de esgotar!');

        productCard.dataset.estoque = 0; // Sincroniza o data-attribute
        addButton.disabled = true;
        addButton.style.backgroundColor = '#52525B';
        addButton.style.cursor = 'not-allowed';
    }
});

// Listener para o popup de confirmação
if (modalConfirmacao) {
    modalConfirmacao.addEventListener('click', async (event) => {
        const target = event.target;

        // Voltar ou fechar o modal
        if (target.id === 'btn-continuar-comprando' || target === modalConfirmacao) {
            modalConfirmacao.classList.add('hidden');
            mainContainer.classList.remove('content-blurred');
            return;
        }

        // Selecionar método de pagamento
        const pontoOption = target.closest('.ponto-option');
        if (pontoOption) {
            const container = pontoOption.parentElement; 
            container.querySelectorAll('.ponto-option').forEach(opt => opt.classList.remove('selected'));
            pontoOption.classList.add('selected');
            pontoOption.querySelector('input').checked = true;
            return;
        }

        // Remover um item do pedido
        const botaoRemover = target.closest('.btn-remover-item');
        if (botaoRemover) {
            const uidParaRemover = parseFloat(botaoRemover.dataset.uid);

            // Encontra o item no pedido atual para pegar seu ID e quantidade
            const itemParaRemover = pedidoAtual.find(item => item.uid === uidParaRemover);

            if (itemParaRemover) {
                // Libera a reserva no backend ANTES de remover do estado local
                await gerenciarReservaAPI(itemParaRemover.id, -itemParaRemover.quantidade);
            }

            // Agora, remove do estado local
            removerItemDoPedido(uidParaRemover);

            // Lógica de UI existente
            if (pedidoAtual.length === 0) {
                modalConfirmacao.classList.add('hidden');
                mainContainer.classList.remove('content-blurred');
            } else {
                abrirPopupConfirmacao(); 
            }
            atualizarBotaoPrincipal();
            return;
        }

        // Confirmar e Enviar o Pedido para o Servidor
        if (target.id === 'btn-confirmar-pedido') {
            const metodoPagamentoInput = document.querySelector('input[name="metodo_pagamento"]:checked');
            const modalidadeEntregaInput = document.querySelector('input[name="modalidade_entrega"]:checked');

            // 1. LÓGICA DE VALIDAÇÃO
            target.disabled = true; // Desabilita o botão antes da validação

            if (!metodoPagamentoInput) {
                await mostrarAlerta('Pagamento Pendente', 'Por favor, selecione uma forma de pagamento.');
                target.disabled = false; // Reabilita o botão após o alerta
                return;
            }
            if (!modalidadeEntregaInput) {
                await mostrarAlerta('Modalidade Pendente', 'Por favor, selecione se o consumo é no local ou para viagem.');
                target.disabled = false; // Reabilita o botão após o alerta
                return;
            }

            // 2. CAPTURA DOS DADOS
            const metodoPagamento = metodoPagamentoInput.value;
            const modalidadeEntrega = modalidadeEntregaInput.value;

            try {
                // 3. ENVIO DOS DADOS (NOTE O NOVO ARGUMENTO)
                await salvarPedido(metodoPagamento, modalidadeEntrega);
                modalConfirmacao.classList.add('hidden'); // <-- ADICIONE ESTA LINHA
                // Se o pedido for salvo com sucesso, a página será recarregada
                // pela função salvarPedido, então não precisamos reativar o botão.
            } catch (error) {
                // Se ocorrer um erro, a página não recarrega.
                // Reativamos o botão para que o usuário possa tentar novamente.
                console.error("Erro ao finalizar pedido:", error);
                target.disabled = false;
            }
        }
    });
}


// ==========================================================
// 6. INICIALIZAÇÃO
// ==========================================================
document.addEventListener('DOMContentLoaded', () => {
    // Inicializa a tela de entrada
    if (mainContainer) {
        mainContainer.classList.add('content-blurred');
    }
    
    // Renderiza o teclado virtual
    renderizarTeclado();
    
    // Atualiza o estado inicial do botão principal
    atualizarBotaoPrincipal();

    // NOVO: Inicializa nosso estado de estoque local
    const todosOsCards = document.querySelectorAll('.product-card');
    estoqueState.inicializarEstoque(todosOsCards);
    
    // Debug: Verificar se todos os elementos existem
    console.log('Debug - Elementos encontrados:', {
        mainContainer: !!mainContainer,
        btnAcaoPrincipal: !!btnAcaoPrincipal,
        telaInicial: !!telaInicial,
        telaTeclado: !!telaTeclado,
        btnNovoPedido: !!btnNovoPedido,
        btnIniciar: !!btnIniciar
    });
});

// ==========================================================
// 5. LÓGICA DE AJUSTE DE LAYOUT DO TECLADO
// ==========================================================

/**
 * Calcula a largura ideal das teclas com base na fileira mais longa (10 teclas)
 * e a aplica a todas as teclas de letra/acento usando uma variável CSS.
 */
function ajustarLarguraTeclas() {
    if (!tecladoContainer || !tecladoContainer.isConnected) return;

    const QTD_TECLAS_FILA_LONGA = 10;
    const GAP_EM_PX = 8; // Corresponde a 'gap-2' no Tailwind. Mude se alterar o gap.

    // Calcula a largura total disponível dentro do container do teclado
    const larguraTotalContainer = tecladoContainer.clientWidth;

    // Calcula o espaço total ocupado pelos vãos (gaps) entre as teclas
    const espacoTotalGaps = (QTD_TECLAS_FILA_LONGA - 1) * GAP_EM_PX;

    // A largura disponível para as teclas é o total menos os gaps
    const larguraDisponivelParaTeclas = larguraTotalContainer - espacoTotalGaps;

    // A largura de cada tecla é o espaço disponível dividido pelo número de teclas
    const larguraCalculadaTecla = larguraDisponivelParaTeclas / QTD_TECLAS_FILA_LONGA;

    // Aplica a largura calculada como uma variável CSS no próprio container do teclado
    tecladoContainer.style.setProperty('--key-width', `${larguraCalculadaTecla}px`);
}

// Adiciona um listener para reajustar a largura das teclas caso o usuário redimensione a janela
// (por exemplo, virar o tablet de retrato para paisagem)
window.addEventListener('resize', ajustarLarguraTeclas);

// Também chamamos a função após o teclado ser renderizado pela primeira vez.
// Altere o final da função `renderizarTeclado` para incluir esta chamada:
function renderizarTeclado() {
    if (!tecladoContainer) return;
    tecladoContainer.innerHTML = '';
    layoutTeclas.forEach(linha => {
        const linhaDiv = document.createElement('div');
        linhaDiv.className = 'flex justify-center gap-2 md:gap-3';
        linha.forEach(tecla => {
            const teclaBtn = document.createElement('button');
            teclaBtn.className = 'keyboard-key h-16 rounded-lg font-bold text-xl flex items-center justify-center';
            if (tecla === 'Backspace') {
                teclaBtn.innerHTML = '<i class="fas fa-backspace"></i>';
                teclaBtn.classList.add('flex-grow', 'flex-grow-[2]', 'text-2xl', 'bg-red-700/80', 'hover:bg-red-600/80');
            } else if (tecla === 'ESPAÇO') {
                teclaBtn.textContent = 'ESPAÇO';
                teclaBtn.classList.add('flex-grow', 'flex-grow-[6]');
            } else {
                teclaBtn.classList.add('keyboard-letter-key');
                teclaBtn.textContent = tecla;
                if (tecla === '´' || tecla === '~') {
                    teclaBtn.classList.add('bg-blue-600/80', 'hover:bg-blue-500/80');
                }
            }
            teclaBtn.dataset.key = tecla;
            linhaDiv.appendChild(teclaBtn);
        });
        tecladoContainer.appendChild(linhaDiv);
    });
}

// ==========================================================
// 7. MONITOR DE INATIVIDADE
// ==========================================================

const TEMPO_INATIVIDADE = 50000; // 50 segundos
const TEMPO_CONTAGEM = 10; // 10 segundos

let timerInatividade = null;
let timerContagem = null;

const overlayInatividade = document.getElementById('overlay-inatividade');
const contadorInatividade = document.getElementById('contador-inatividade');
const mensagemPadraoContador = contadorInatividade ? contadorInatividade.dataset.mensagemReinicio : '';

function esconderOverlayInatividade() {
    if (!overlayInatividade || overlayInatividade.classList.contains('hidden')) return;
    
    overlayInatividade.classList.add('hidden');
    clearInterval(timerContagem);
    // Restaura a mensagem original para a próxima vez que o overlay for mostrado
    if(contadorInatividade) contadorInatividade.textContent = "Toque na tela para continuar seu pedido.";
}

function mostrarOverlayInatividade() {
    // Busca a referência à tela inicial dentro da função para garantir que está atualizada
    const telaInicial = document.getElementById('tela-inicial');

    // Se a tela inicial já estiver visível, não faz sentido recarregar.
    // Apenas reiniciamos o ciclo de monitoramento.
    if (telaInicial && !telaInicial.classList.contains('hidden')) {
        console.log("Inatividade detectada na tela inicial. O timer será reiniciado sem recarregar a página.");
        reiniciarTimerInatividade();
        return; 
    }

    if (!overlayInatividade) return;

    overlayInatividade.classList.remove('hidden');
    
    let segundosRestantes = TEMPO_CONTAGEM;
    if(contadorInatividade) contadorInatividade.textContent = mensagemPadraoContador.replace('%s', segundosRestantes);

    timerContagem = setInterval(() => {
        segundosRestantes--;
        if(contadorInatividade) contadorInatividade.textContent = mensagemPadraoContador.replace('%s', segundosRestantes);

        if (segundosRestantes <= 0) {
            clearInterval(timerContagem);
            location.reload();
        }
    }, 1000);
}

function reiniciarTimerInatividade() {
    esconderOverlayInatividade();
    clearTimeout(timerInatividade);
    timerInatividade = setTimeout(mostrarOverlayInatividade, TEMPO_INATIVIDADE);
}

function iniciarMonitorInatividade() {
    const eventosDeAtividade = ['click', 'touchstart', 'keydown'];
    
    eventosDeAtividade.forEach(evento => {
        window.addEventListener(evento, reiniciarTimerInatividade, { passive: true });
    });

    if (mainContent) {
        mainContent.addEventListener('scroll', reiniciarTimerInatividade, { passive: true });
    }

    // Também reseta o timer se o usuário voltar para a aba do totem
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            reiniciarTimerInatividade();
        }
    });

    // Inicia o timer pela primeira vez
    reiniciarTimerInatividade();
}

// Chame a função de inicialização quando o DOM estiver pronto.
document.addEventListener('DOMContentLoaded', () => {
    // ... (código existente dentro deste listener)
    
    // Adicione esta linha no final do listener 'DOMContentLoaded'
    iniciarMonitorInatividade(); 
});
