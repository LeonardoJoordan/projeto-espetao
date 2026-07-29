(() => {
    "use strict";

    const DURACAO_ANIMACAO_MS = 7200;
    const TEMPO_LIMITE_ANIMACAO_MS = DURACAO_ANIMACAO_MS + 700;
    const INTERVALO_ATUALIZACAO_MS = 15000;
    const MAX_PEDIDOS_PREPARANDO = 8;
    const MAX_PEDIDOS_PRONTOS = 6;

    const listaPreparando = document.getElementById("lista-preparando");
    const listaPronto = document.getElementById("lista-pronto");
    const statusConexao = document.getElementById("status-conexao");
    const fogoOverlay = document.getElementById("animacao-fogo-overlay");
    const faiscasContainer = document.getElementById("container-faiscas");
    const textoNomeCliente = document.getElementById("texto-nome-cliente");
    const textoNumeroPedido = document.getElementById("texto-numero-pedido");

    if (
        !listaPreparando ||
        !listaPronto ||
        !statusConexao ||
        !fogoOverlay ||
        !faiscasContainer ||
        !textoNomeCliente ||
        !textoNumeroPedido
    ) {
        console.error("Monitor não iniciado: elementos obrigatórios não foram encontrados.");
        return;
    }

    let monitorInicializado = false;
    let carregamentoEmAndamento = false;
    let atualizacaoPendente = false;
    let animacaoEmAndamento = false;
    let idsProntosConhecidos = new Set();
    let idsRenderizados = new Set();

    const filaAnimacoes = [];
    const idsNaFila = new Set();

    function normalizarId(pedido) {
        return String(pedido?.id ?? "");
    }

    function normalizarNome(nome) {
        const nomeLimpo = String(nome ?? "").trim();
        return (nomeLimpo || "CLIENTE").toLocaleUpperCase("pt-BR");
    }

    function formatarNumero(senha) {
        const valor = String(senha ?? "").trim();
        if (!valor) return "";
        return valor.padStart(3, "0");
    }

    function criarCard(pedido, tipo, entrar) {
        const card = document.createElement("article");
        const id = normalizarId(pedido);
        const pronto = tipo === "pronto";

        card.className = `order-card ${pronto ? "is-ready" : "is-preparing"}`;
        card.dataset.id = id;

        if (entrar) card.classList.add("is-entering");

        const nome = document.createElement("div");
        const nomeFormatado = normalizarNome(pedido.nome_cliente);
        nome.className = "order-customer";
        nome.textContent = nomeFormatado;
        nome.classList.toggle("is-long-name", nomeFormatado.length > 16);
        nome.classList.toggle("is-very-long-name", nomeFormatado.length > 25);

        const numero = document.createElement("div");
        numero.className = "order-number";
        const senhaFormatada = formatarNumero(pedido.senha_diaria);
        numero.textContent = senhaFormatada ? `#${senhaFormatada}` : "—";

        card.append(nome, numero);
        return card;
    }

    function criarEstadoVazio(texto) {
        const vazio = document.createElement("p");
        vazio.className = "empty-list";
        vazio.textContent = texto;
        return vazio;
    }

    function renderizarLista(elemento, pedidos, tipo, textoVazio, novosIds) {
        const fragmento = document.createDocumentFragment();

        if (!pedidos.length) {
            fragmento.appendChild(criarEstadoVazio(textoVazio));
        } else {
            pedidos.forEach((pedido, indice) => {
                const id = normalizarId(pedido);
                const card = criarCard(pedido, tipo, novosIds.has(id));

                if (tipo === "pronto" && indice === 0) {
                    card.classList.add("is-featured");
                }

                fragmento.appendChild(card);
            });
        }

        elemento.replaceChildren(fragmento);
    }

    function renderizarColunas(pedidos) {
        const emPreparacao = pedidos
            .filter((pedido) => pedido.status === "em_producao")
            .slice(0, MAX_PEDIDOS_PREPARANDO);
        const prontos = pedidos
            .filter((pedido) => pedido.status === "aguardando_retirada")
            .slice(0, MAX_PEDIDOS_PRONTOS);

        const idsAtuais = new Set(
            [...emPreparacao, ...prontos].map((pedido) => normalizarId(pedido))
        );
        const novosIds = new Set();

        if (monitorInicializado) {
            idsAtuais.forEach((id) => {
                if (!idsRenderizados.has(id)) novosIds.add(id);
            });
        }

        renderizarLista(
            listaPronto,
            prontos,
            "pronto",
            "Nenhum pedido aguardando retirada",
            novosIds
        );
        renderizarLista(
            listaPreparando,
            emPreparacao,
            "preparacao",
            "A churrasqueira está livre no momento",
            novosIds
        );

        idsRenderizados = idsAtuais;
    }

    function criarFaiscas() {
        const fragmento = document.createDocumentFragment();
        const quantidade = 92;

        for (let indice = 0; indice < quantidade; indice += 1) {
            const faisca = document.createElement("span");
            const faiscaDistante = indice % 5 === 0;
            const origem = 12 + Math.random() * 76;
            const direcao = origem < 50 ? -1 : 1;
            const tamanho = faiscaDistante
                ? 1.8 + Math.random() * 2.8
                : 3 + Math.random() * 5.8;
            const duracao = 1.8 + Math.random() * 0.85;
            const atraso = indice < 68
                ? Math.random() * 0.45
                : 0.35 + Math.random() * 0.55;
            const deslocamento = direcao * (55 + Math.random() * 260);
            const altura = 58 + Math.random() * 68;
            const giro = -320 + Math.random() * 640;

            faisca.className = `spark${faiscaDistante ? " is-dim" : ""}`;
            faisca.style.setProperty("--origin-x", `${origem.toFixed(1)}vw`);
            faisca.style.setProperty("--size", `${tamanho.toFixed(1)}px`);
            faisca.style.setProperty("--duration", `${duracao.toFixed(2)}s`);
            faisca.style.setProperty("--delay", `${atraso.toFixed(2)}s`);
            faisca.style.setProperty("--drift-x", `${deslocamento.toFixed(0)}px`);
            faisca.style.setProperty("--rise-y", `-${altura.toFixed(1)}vh`);
            faisca.style.setProperty("--spin", `${giro.toFixed(0)}deg`);
            fragmento.appendChild(faisca);
        }

        faiscasContainer.replaceChildren(fragmento);
    }

    function aguardarFimDaAnimacao() {
        return new Promise((resolve) => {
            let concluida = false;

            const finalizar = () => {
                if (concluida) return;
                concluida = true;
                fogoOverlay.removeEventListener("animationend", aoFinalizar);
                clearTimeout(tempoLimite);
                resolve();
            };

            const aoFinalizar = (evento) => {
                if (evento.target === fogoOverlay && evento.animationName === "overlay-cycle") {
                    finalizar();
                }
            };

            const tempoLimite = window.setTimeout(finalizar, TEMPO_LIMITE_ANIMACAO_MS);
            fogoOverlay.addEventListener("animationend", aoFinalizar);
        });
    }

    async function exibirAnimacao(pedido) {
        const nome = normalizarNome(pedido.nome_cliente);
        const numero = formatarNumero(pedido.senha_diaria);

        textoNomeCliente.textContent = nome;
        textoNomeCliente.classList.toggle("is-long-name", nome.length > 18);
        textoNumeroPedido.textContent = numero ? `PEDIDO #${numero}` : "";
        criarFaiscas();

        fogoOverlay.hidden = false;
        fogoOverlay.setAttribute("aria-hidden", "false");
        fogoOverlay.classList.remove("is-active");

        // Força um novo ciclo CSS mesmo após reconexões ou chamadas muito próximas.
        void fogoOverlay.offsetWidth;
        fogoOverlay.classList.add("is-active");

        await aguardarFimDaAnimacao();

        fogoOverlay.classList.remove("is-active");
        fogoOverlay.setAttribute("aria-hidden", "true");
        fogoOverlay.hidden = true;
        faiscasContainer.replaceChildren();
    }

    async function processarFilaAnimacoes() {
        if (animacaoEmAndamento) return;
        animacaoEmAndamento = true;

        try {
            while (filaAnimacoes.length) {
                const pedido = filaAnimacoes.shift();
                const id = normalizarId(pedido);

                try {
                    await exibirAnimacao(pedido);
                } catch (erro) {
                    console.error("Falha ao exibir chamada de pedido pronto:", erro);
                    fogoOverlay.classList.remove("is-active");
                    fogoOverlay.hidden = true;
                } finally {
                    idsNaFila.delete(id);
                }
            }
        } finally {
            animacaoEmAndamento = false;
        }
    }

    function enfileirarPedidoPronto(pedido) {
        const id = normalizarId(pedido);
        if (!id || idsNaFila.has(id)) return;

        idsNaFila.add(id);
        filaAnimacoes.push({
            id: pedido.id,
            nome_cliente: pedido.nome_cliente,
            senha_diaria: pedido.senha_diaria,
        });
        void processarFilaAnimacoes();
    }

    function aplicarPedidos(pedidos) {
        const pedidosProntos = pedidos.filter(
            (pedido) => pedido.status === "aguardando_retirada"
        );
        const idsProntosAtuais = new Set(pedidosProntos.map(normalizarId));

        // A carga inicial apenas preenche a tela. Assim, atualizar o navegador não
        // chama novamente clientes que já estavam aguardando retirada.
        if (monitorInicializado) {
            pedidosProntos.forEach((pedido) => {
                const id = normalizarId(pedido);
                if (!idsProntosConhecidos.has(id)) {
                    enfileirarPedidoPronto(pedido);
                }
            });
        }

        idsProntosConhecidos = idsProntosAtuais;
        renderizarColunas(pedidos);
        monitorInicializado = true;
    }

    function definirStatusConexao(online) {
        statusConexao.dataset.state = online ? "online" : "offline";
    }

    async function buscarPedidos() {
        const resposta = await fetch("/api/pedidos_ativos", {
            cache: "no-store",
            headers: { Accept: "application/json" },
        });

        if (!resposta.ok) {
            throw new Error(`Servidor respondeu com status ${resposta.status}.`);
        }

        const pedidos = await resposta.json();
        if (!Array.isArray(pedidos)) {
            throw new Error("A resposta de pedidos ativos é inválida.");
        }

        return pedidos;
    }

    async function carregarEAtualizarMonitor() {
        if (carregamentoEmAndamento) {
            atualizacaoPendente = true;
            return;
        }

        carregamentoEmAndamento = true;

        try {
            do {
                atualizacaoPendente = false;

                try {
                    const pedidos = await buscarPedidos();
                    aplicarPedidos(pedidos);
                    definirStatusConexao(true);
                } catch (erro) {
                    definirStatusConexao(false);
                    console.error("Erro ao atualizar o monitor:", erro);
                }
            } while (atualizacaoPendente);
        } finally {
            carregamentoEmAndamento = false;
        }
    }

    const socket = window.io({
        reconnection: true,
        reconnectionDelay: 800,
        reconnectionDelayMax: 5000,
    });

    socket.on("connect", () => {
        definirStatusConexao(true);
        void carregarEAtualizarMonitor();
    });

    socket.on("novo_pedido", () => {
        void carregarEAtualizarMonitor();
    });

    socket.on("disconnect", () => {
        definirStatusConexao(false);
    });

    socket.on("connect_error", () => {
        definirStatusConexao(false);
    });

    window.setInterval(() => {
        void carregarEAtualizarMonitor();
    }, INTERVALO_ATUALIZACAO_MS);

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) void carregarEAtualizarMonitor();
    });

    void carregarEAtualizarMonitor();
})();
