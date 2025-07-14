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
    formatCurrency
} from './cliente-logica.js';


// ==========================================================
// 2. REFERÊNCIAS AO DOM E VARIÁVEIS DE UI
// ==========================================================
const mainContainer = document.getElementById('main-container');
const btnAcaoPrincipal = document.getElementById('btn-acao-principal');
const mainContent = document.getElementById('main-content');
const navLinks = document.querySelectorAll('#nav-categorias a');
const sections = document.querySelectorAll('.categoria-secao');
const lastSection = sections.length > 0 ? sections[sections.length - 1] : null;

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
// 3. FUNÇÕES DE UI (Manipulação da Interface)
// ==========================================================

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

function abrirPopupSimples(productCard) {
    if (!modalSimples) return;

    // Remove o event listener anterior se existir
    if (eventoPopupSimplesAtivo) {
        modalSimples.removeEventListener('click', eventoPopupSimplesAtivo);
    }

    const idProduto = productCard.dataset.id;
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
    mainContainer.classList.add('content-blurred');

    const quantidadeDisplay = document.getElementById('quantidade-display-simples');
    const precoTotalDisplay = document.getElementById('preco-total-simples');
    let quantidade = 1;

    function atualizarInterfaceSimples() {
        quantidadeDisplay.textContent = quantidade;
        const total = quantidade * precoProduto;
        precoTotalDisplay.textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
    }

    eventoPopupSimplesAtivo = (event) => {
        const target = event.target.closest('button');
        if (!target) return;

        if (target.id === 'btn-aumentar-simples') {
            const estoqueDisponivel = parseInt(productCard.dataset.estoque);
            if (quantidade < estoqueDisponivel) {
                quantidade++;
                atualizarInterfaceSimples();
            } else {
                alert(`Desculpe, temos apenas ${estoqueDisponivel} unidades deste item em estoque.`);
            }
        } else if (target.id === 'btn-diminuir-simples') {
            if (quantidade > 1) {
                quantidade--;
                atualizarInterfaceSimples();
            }
        } else if (target.id === 'btn-cancelar-simples') {
            modalSimples.classList.add('hidden');
            modalSimples.innerHTML = '';
            mainContainer.classList.remove('content-blurred');
        } else if (target.id === 'btn-adicionar-simples') {
            const novoItem = {
                id: idProduto,
                nome: nomeProduto,
                preco: precoProduto,
                quantidade: quantidade,
                requer_preparo: parseInt(productCard.dataset.requerPreparo)
            };
            adicionarItemAoPedido(novoItem);
            atualizarBotaoPrincipal();
            modalSimples.classList.add('hidden');
            modalSimples.innerHTML = '';
            mainContainer.classList.remove('content-blurred');
        }
    };

    modalSimples.addEventListener('click', eventoPopupSimplesAtivo);
    atualizarInterfaceSimples();
}

function abrirPopupCustomizacao(productCard) {
    if (!modalCustomizacao) return;

    // Remove o event listener anterior se existir
    if (eventoPopupAtivo) {
        modalCustomizacao.removeEventListener('click', eventoPopupAtivo);
    }

    const idProduto = productCard.dataset.id;
    const nomeProduto = productCard.dataset.nome;
    const precoProduto = parseFloat(productCard.dataset.preco);
    
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

    function criarLinhaHtml(numeroItem) {
        const uniqueIdPrefix = `item-${numeroItem}-`;
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
                            <label class="extra-item" for="${uniqueIdPrefix}farofa">
                                <input type="checkbox" id="${uniqueIdPrefix}farofa" class="hidden">
                                Farofa
                            </label>
                            <label class="extra-item" for="${uniqueIdPrefix}limao">
                                <input type="checkbox" id="${uniqueIdPrefix}limao" class="hidden">
                                Limão
                            </label>
                            <label class="extra-item" for="${uniqueIdPrefix}tempero">
                                <input type="checkbox" id="${uniqueIdPrefix}tempero" class="hidden">
                                Tempero Especial
                            </label>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function atualizarInterfacePopup() {
        quantidadeDisplay.textContent = quantidade;
        containerLinhas.innerHTML = '';
        for (let i = 1; i <= quantidade; i++) {
            containerLinhas.innerHTML += criarLinhaHtml(i);
        }
        const total = quantidade * precoProduto;
        precoTotalDisplay.textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
    }

    eventoPopupAtivo = (event) => {
        const target = event.target;
        
        if (target.closest('#btn-aumentar-popup')) {
            const estoqueDisponivel = parseInt(productCard.dataset.estoque);
            if (quantidade < estoqueDisponivel) {
                quantidade++;
                containerLinhas.insertAdjacentHTML('beforeend', criarLinhaHtml(quantidade));
                quantidadeDisplay.textContent = quantidade;
                precoTotalDisplay.textContent = `R$ ${(quantidade * precoProduto).toFixed(2).replace('.', ',')}`;
            } else {
                alert(`Desculpe, temos apenas ${estoqueDisponivel} espetinhos deste tipo em estoque.`);
            }
        }
        
        if (target.closest('#btn-diminuir-popup')) {
            if (quantidade > 1) {
                quantidade--;
                if (containerLinhas.lastElementChild) {
                    containerLinhas.lastElementChild.remove();
                }
                quantidadeDisplay.textContent = quantidade;
                precoTotalDisplay.textContent = `R$ ${(quantidade * precoProduto).toFixed(2).replace('.', ',')}`;
            }
        }
        
        const pontoOption = target.closest('.ponto-option');
        if (pontoOption) {
            const grupo = pontoOption.closest('.ponto-options');
            grupo.querySelectorAll('.ponto-option').forEach(opt => opt.classList.remove('selected'));
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
        
        if (target.closest('#btn-cancelar-item-popup')) {
            modalCustomizacao.classList.add('hidden');
            modalCustomizacao.innerHTML = '';
        }
        
        if (target.closest('#btn-adicionar-pedido-popup')) {
            const todosOsItensCustomizados = document.querySelectorAll('.item-customizacao');

            todosOsItensCustomizados.forEach((itemNode) => {
                const ponto = itemNode.querySelector('input[name$="ponto"]:checked').value;
                const extras = Array.from(itemNode.querySelectorAll('input[type="checkbox"]:checked'))
                                .map(cb => cb.closest('.extra-item').textContent.trim());
                
                const customizacaoDoItem = { ponto: ponto, extras: extras };

                const novoItem = {
                    id: idProduto,
                    nome: nomeProduto,
                    preco: precoProduto,
                    quantidade: 1,
                    customizacao: customizacaoDoItem,
                    requer_preparo: parseInt(productCard.dataset.requerPreparo)
                };
                
                adicionarItemAoPedido(novoItem);
            });

            atualizarBotaoPrincipal();
            modalCustomizacao.classList.add('hidden');
            modalCustomizacao.innerHTML = '';
        }
    };

    modalCustomizacao.addEventListener('click', eventoPopupAtivo);
    atualizarInterfacePopup();
}

function abrirPopupConfirmacao() {
    if (!modalConfirmacao || pedidoAtual.length === 0) return;

    const listaContainer = document.getElementById('lista-itens-confirmacao');
    const totalDisplay = document.getElementById('total-confirmacao');
    
    // Agora usamos a função importada para formatar o valor total
    const valorTotal = pedidoAtual.reduce((acc, item) => acc + (item.preco * item.quantidade), 0);
    totalDisplay.textContent = formatCurrency(valorTotal);

    listaContainer.innerHTML = pedidoAtual.map((item, index) => {
        let detalhesItem = '';
        if (item.customizacao) { 
            const mapaPonto = { 'mal': 'Mal Passado', 'ponto': 'Ao Ponto', 'bem': 'Bem Passado' };
            const pontoTexto = mapaPonto[item.customizacao.ponto] || item.customizacao.ponto;
            let extrasTexto = item.customizacao.extras?.length > 0 ? `com ${item.customizacao.extras.join(', ')}` : 'sem extras';
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
                    <button class="btn-remover-item text-red-500 hover:text-red-400" data-index="${index}" title="Remover Item">
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
                teclaBtn.classList.add('w-20');
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

function atualizarVisualAcento() {
    document.querySelectorAll('.keyboard-key').forEach(btn => {
        if (btn.dataset.key === '´' || btn.dataset.key === '~') {
            btn.classList.toggle('accent-active', btn.dataset.key === proximoAcento);
        }
    });
}

function atualizarTextoTeclado() {
    if (campoTextoNome) campoTextoNome.textContent = nomeDigitadoTemp;
}


// ==========================================================
// 5. EVENT LISTENERS
// ==========================================================

// Listener para o botão "NOVO PEDIDO"
if (btnNovoPedido) {
    btnNovoPedido.addEventListener('click', () => {
        if (telaInicial) telaInicial.classList.add('hidden');
        if (telaTeclado) telaTeclado.classList.remove('hidden');
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
    btnIniciar.addEventListener('click', () => {
        const nomeFinal = nomeDigitadoTemp.trim();
        if (nomeFinal === '') {
            alert("Por favor, digite um nome para o pedido.");
            return;
        }
        setNomeCliente(nomeFinal);
        if (telaTeclado) telaTeclado.classList.add('hidden');
        if (mainContainer) mainContainer.classList.remove('content-blurred');
        nomeDigitadoTemp = '';
        atualizarTextoTeclado();
        atualizarBotaoPrincipal();
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

// Listener de clique geral (para fogo e adicionar ao carrinho)
document.addEventListener('click', (event) => {
    const addButton = event.target.closest('.add-button');
    if (!addButton) return;

    // Lógica da animação de fogo
    addButton.classList.add('firing');
    setTimeout(() => addButton.classList.remove('firing'), 300);
    const fireContainer = addButton.querySelector('.fire-container');
    if (fireContainer) {
        fireContainer.innerHTML = '';
        const flame = document.createElement('div');
        flame.classList.add('flame');
        fireContainer.appendChild(flame);
        const core = document.createElement('div');
        core.classList.add('flame-core');
        flame.appendChild(core);
        for (let i = 0; i < 6; i++) {
            const p = document.createElement('div');
            p.classList.add('flame-particle');
            p.style.left = `${(Math.random() - 0.5) * 40}px`;
            p.style.animationDuration = `${Math.random() * 0.4 + 0.6}s`;
            flame.appendChild(p);
        }
        for (let i = 0; i < 8; i++) {
            const s = document.createElement('div');
            s.classList.add('spark');
            s.style.setProperty('--spark-x', `${(Math.random() - 0.5) * 60}px`);
            s.style.setProperty('--spark-y', `${-Math.random() * 80 - 20}px`);
            s.style.animationDuration = `${Math.random() * 0.3 + 0.5}s`;
            flame.appendChild(s);
        }
        setTimeout(() => flame.remove(), 1000);
    }

    // Lógica condicional: Decide qual popup abrir
    const productCard = addButton.closest('.product-card');
    if (productCard && productCard.dataset.id) {
        const categoriaNome = productCard.dataset.categoriaNome;

        if (categoriaNome === 'Espetinhos') {
            abrirPopupCustomizacao(productCard);
        } else {
            abrirPopupSimples(productCard);
        }
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
            pontoOption.closest('#opcoes-pagamento').querySelectorAll('.ponto-option').forEach(opt => opt.classList.remove('selected'));
            pontoOption.classList.add('selected');
            pontoOption.querySelector('input').checked = true;
            return;
        }

        // Remover um item do pedido
        const botaoRemover = target.closest('.btn-remover-item');
        if (botaoRemover) {
            const indexParaRemover = parseInt(botaoRemover.dataset.index);
            removerItemDoPedido(indexParaRemover);

            // Se o carrinho ficar vazio, fecha o popup e atualiza o botão principal
            if(pedidoAtual.length === 0) {
                modalConfirmacao.classList.add('hidden');
                mainContainer.classList.remove('content-blurred');
            } else {
                // Se ainda tiver itens, apenas redesenha o conteúdo do popup
                abrirPopupConfirmacao(); 
            }
            atualizarBotaoPrincipal();
            return;
        }

        // Confirmar e Enviar o Pedido para o Servidor
        if (target.id === 'btn-confirmar-pedido') {
            const metodoPagamento = document.querySelector('input[name="metodo_pagamento"]:checked').value;
            
            try {
                await salvarPedido(metodoPagamento);
                // A função salvarPedido já faz o location.reload() em caso de sucesso
            } catch (error) {
                // O erro já é tratado dentro da função salvarPedido
                console.error("Erro ao finalizar pedido:", error);
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