// static/js/protocolo-serializacao.js

/**
 * Decodifica um código Base64 usando mapas dinâmicos fornecidos.
 * @param {string} codigoBase64 - O código do pedido vindo do cliente.
 * @param {object} menuCompleto - O mapa de todos os produtos para consulta.
 * @param {object} mapas - Um objeto contendo os mapas de tradução (pagamento, modalidade, ponto, acompanhamentos).
 * @returns {{sucesso: boolean, erro?: string, ...}}
 */
export function decodificarPedido(codigoBase64, menuCompleto, mapas) {
    try {
        const { mapaPagamentoInverso, mapaModalidadeInverso, mapaPontoInverso, mapaAcompanhamentosInverso } = mapas;

        const binaryString = atob(codigoBase64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        let offset = 0;

        const tamanhoNome = bytes[offset++];
        if (offset + tamanhoNome > bytes.length) throw new Error("Cabeçalho de nome inválido.");

        const nomeBytes = bytes.subarray(offset, offset + tamanhoNome);
        const decoder = new TextDecoder('utf-8');
        const nomeCliente = decoder.decode(nomeBytes);
        offset += tamanhoNome;

        const codPagamento = bytes[offset++];
        const codModalidade = bytes[offset++];

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
            if (pontoCod > 0) {
                customizacao.ponto = mapaPontoInverso[pontoCod] || 'indefinido';
            }
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
                ...produtoBase,
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