// static/js/cliente-teclado.js

document.addEventListener('DOMContentLoaded', () => {
    // Referências aos elementos da UI
    const telaInicial = document.getElementById('tela-inicial');
    const telaTeclado = document.getElementById('tela-teclado');
    const btnNovoPedido = document.getElementById('btn-novo-pedido');
    const btnIniciar = document.getElementById('btn-iniciar');
    const campoTexto = document.getElementById('texto-nome');
    const tecladoContainer = document.getElementById('teclado-virtual');

    // Se os elementos não existirem, não faz nada.
    if (!telaInicial || !telaTeclado || !btnNovoPedido || !btnIniciar) {
        return;
    }

    let nomeCliente = '';
    let proximoAcento = null;

    // Mapa de acentuação
    const acentosMap = {
        '´': { 'A': 'Á', 'E': 'É', 'I': 'Í', 'O': 'Ó', 'U': 'Ú' },
        '~': { 'A': 'Ã', 'O': 'Õ' }
    };

    // Layout do teclado simplificado
    const layoutTeclas = [
        ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
        ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
        ['Z', 'X', 'C', 'V', 'B', 'N', 'M', '´', '~'],
        ['ESPAÇO', 'Backspace']
    ];

    // Função para renderizar o teclado
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

    // Função para atualizar o estado visual do acento
    function atualizarVisualAcento() {
        document.querySelectorAll('.keyboard-key').forEach(btn => {
            if (btn.dataset.key === '´' || btn.dataset.key === '~') {
                btn.classList.toggle('accent-active', btn.dataset.key === proximoAcento);
            }
        });
    }

    function atualizarTexto() {
        if (campoTexto) campoTexto.textContent = nomeCliente;
    }

    // Event Listeners
    btnNovoPedido.addEventListener('click', () => {
        telaInicial.classList.add('hidden');
        telaTeclado.classList.remove('hidden');
    });

    if (tecladoContainer) {
        tecladoContainer.addEventListener('click', (e) => {
            const key = e.target.closest('button')?.dataset.key;
            if (!key) return;

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
                nomeCliente = nomeCliente.slice(0, -1);
            } else if (key === 'ESPAÇO') {
                 if (nomeCliente.length < 20) nomeCliente += ' ';
            } else {
                if (nomeCliente.length < 20) {
                    nomeCliente += charToAdd;
                }
            }
            
            atualizarTexto();
        });
    }

    btnIniciar.addEventListener('click', () => {
        const nomeFinal = nomeCliente.trim();
        if (nomeFinal === '') {
            alert("Por favor, digite um nome para o pedido.");
            return;
        }
    
        // Verifica se a função global 'iniciarNovoPedido' existe antes de chamar
        if (typeof iniciarNovoPedido === 'function') {
            iniciarNovoPedido(nomeFinal); // Chama a função global diretamente
    
            // Esconde a tela do teclado
            telaTeclado.classList.add('hidden');
    
            // Limpa o campo para o próximo cliente
            nomeCliente = '';
            atualizarTexto();
    
        } else {
            console.error("Erro: A função iniciarNovoPedido() não foi encontrada.");
            alert("Ocorreu um erro ao iniciar o pedido. Tente recarregar a página.");
        }
    });

    renderizarTeclado();
});