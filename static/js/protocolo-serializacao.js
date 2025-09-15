// static/js/protocolo-serializacao.js

/**
 * Decodifica um código Base64 e o transforma em um objeto de pedido estruturado.
 * @param {string} codigoBase64 - O código do pedido vindo do cliente.
 * @param {object} menuCompleto - O mapa de todos os produtos para consulta de dados (chave = ID do produto).
 * @returns {{sucesso: boolean, erro?: string, nomeCliente?: string, metodoPagamento?: string, modalidade?: string, itens?: Array<object>}}
 */
export function decodificarPedido(codigoBase64, menuCompleto) {
    try {
        // --- MAPEAMENTOS INVERSOS ---
        const mapaPagamentoInverso = { 1: 'pix', 2: 'cartao_credito', 3: 'cartao_debito', 4: 'dinheiro' };
        const mapaModalidadeInverso = { 1: 'local', 2: 'viagem' };
        const mapaPontoInverso = { 1: 'mal', 2: 'ponto', 3: 'bem' };
        const mapaAcompanhamentosInverso = { 1: 'Farofa', 2: 'Limão' }; // Bit 0, Bit 1...

        // --- DECODIFICAÇÃO E LEITURA DOS BYTES ---
        const binaryString = atob(codigoBase64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        let offset = 0;

        // --- LEITURA DO CABEÇALHO ---
        const tamanhoNome = bytes[offset++];
        if (offset + tamanhoNome > bytes.length) throw new Error("Cabeçalho de nome inválido.");

        const nomeBytes = bytes.subarray(offset, offset + tamanhoNome);
        const decoder = new TextDecoder('utf-8');
        const nomeCliente = decoder.decode(nomeBytes);
        offset += tamanhoNome;

        const codPagamento = bytes[offset++];
        const codModalidade = bytes[offset++];

        // --- LEITURA DO CORPO (ITENS) ---
        const itens = [];
        const bytesPorItem = 5;

        while (offset < bytes.length) {
            if (offset + bytesPorItem > bytes.length) throw new Error("Dados de item incompletos.");
            
            const view = new DataView(bytes.buffer, offset, bytesPorItem);
            const produtoId = view.getUint16(0, true);
            const quantidade = view.getUint8(2);
            const pontoCod = view.getUint8(3);
            const acompanhamentosMask = view.getUint8(4);
            
            const produtoBase = menuCompleto[produtoId];
            if (!produtoBase) throw new Error(`Produto com ID ${produtoId} não encontrado no cardápio.`);

            const customizacao = {};
            // Decodifica ponto
            if (pontoCod > 0) {
                customizacao.ponto = mapaPontoInverso[pontoCod] || 'indefinido';
            }
            // Decodifica acompanhamentos (bitmask)
            const acompanhamentos = [];
            for (const [bitValue, nomeAcompanhamento] of Object.entries(mapaAcompanhamentosInverso)) {
                if ((acompanhamentosMask & parseInt(bitValue)) !== 0) {
                    acompanhamentos.push(nomeAcompanhamento);
                }
            }
            if (acompanhamentos.length > 0) {
                customizacao.acompanhamentos = acompanhamentos;
            }

            itens.push({
                ...produtoBase, // Pega nome, preço, etc. do nosso mapa
                quantidade,
                customizacao: Object.keys(customizacao).length > 0 ? customizacao : null
            });
            
            offset += bytesPorItem;
        }

        return {
            sucesso: true,
            nomeCliente: nomeCliente,
            metodoPagamento: mapaPagamentoInverso[codPagamento] || 'pix',
            modalidade: mapaModalidadeInverso[codModalidade] || 'viagem',
            itens: itens
        };

    } catch (e) {
        console.error("Falha na decodificação:", e);
        return { sucesso: false, erro: e.message };
    }
}