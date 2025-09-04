# serializers.py
import math

class FechamentoSerializer:
    """
    Serializa os dados brutos do fechamento para o formato da API v2.
    Invariantes:
    - ticketMedio = faturamentoBruto / max(pedidosRealizados, 1)
    - mediaItensPedido = total_itens_vendidos / max(pedidosRealizados, 1)
    - Datas são strings ISO UTC (YYYY-MM-DDTHH:mm:ssZ).
    - Campos numéricos são numbers.
    - Campos ausentes são representados por 0, [], ou "".
    """
    @staticmethod
    def to_api_v2(dados_brutos, paginacao):
        """
        Transforma os dados brutos do analytics em um dicionário formatado.
        
        Args:
            dados_brutos (dict): Um dicionário contendo os dados agregados.
                                 Ex: {'kpis':{...}, 'itens_top':[...], 'historico_pedidos':{...}, ...}
            paginacao (dict): Um dicionário com informações de paginação.
                              Ex: {'page': 1, 'limit': 50, 'total': 100}
        """
        # Garante que as chaves principais existem, mesmo que vazias
        kpis_brutos = dados_brutos.get('kpis', {})
        historico_bruto = dados_brutos.get('historico_pedidos', {})
        itens_paginados = historico_bruto.get('items', [])

        # Formata o histórico para garantir que a string JSON exista
        itens_historico_formatados = [
            {
                "id": item.get('id', 0),
                "nome_cliente": item.get('nome_cliente', ''),
                "horario": item.get('timestamp_finalizacao', ''), # Supondo que o DB retorna ISO UTC
                "valor_total": item.get('valor_total', 0),
                "metodo_pagamento": item.get('metodo_pagamento', ''),
                "itens_json": item.get('itens_json', '[]') or '[]',
                 "senha_diaria": item.get('senha_diaria', 0) # Garante que não seja None, e sim "[]"
            } for item in itens_paginados
        ]

        itens_estoque_formatados = [
            {
                "nome": item.get('nome', ''),
                "inicial": item.get('inicial', 0),
                "entradas": item.get('entradas', 0),
                "estoque_atual": item.get('estoque_do_dia', 0), # Novo campo
                "saidas": item.get('saidas', 0),
                "final": item.get('final', 0)
            } for item in dados_brutos.get('estoque', [])
        ]

        resultado = {
            "kpis": {
                "faturamentoBruto": kpis_brutos.get('faturamento_bruto', 0),
                "lucroEstimado": kpis_brutos.get('lucro_bruto', 0), # Ajustar se a lógica mudar
                "perdasAjustes": kpis_brutos.get('perdas_ajustes', 0),
                "pedidosRealizados": kpis_brutos.get('pedidos', 0),
                "ticketMedio": kpis_brutos.get('ticket_medio', 0),
                "mediaItensPedido": kpis_brutos.get('media_itens_pedido', 0)
            },
            "itens_top": dados_brutos.get('itens_top', []),
            "historico_pedidos": {
                "items": itens_historico_formatados,
                "page": paginacao.get('page', 1),
                "limit": paginacao.get('limit', 50),
                "total": paginacao.get('total', 0)
            },
            "estoque": itens_estoque_formatados,
            "vendasPorPeriodo": dados_brutos.get('vendasPorPeriodo', {"labels": [], "data": []}),
            "vendasPorPagamento": dados_brutos.get('vendasPorPagamento', {"labels": [], "data": []}),
            "configuracoes": dados_brutos.get('configuracoes', {"taxa_credito": 0, "taxa_debito": 0, "taxa_pix": 0})
        }
        return resultado

class ComparativosSerializer:
    """
    Serializa os dados brutos de dois períodos para o formato da API v2.
    Invariantes:
    - delta_pct = (A - B) / max(B, 1) * 100
    - delta_abs = A - B
    """
    @staticmethod
    def _calcular_deltas(valor_A, valor_B):
        """Função auxiliar para calcular a diferença absoluta e percentual."""
        delta_abs = valor_A - valor_B
        # Evita divisão por zero e lida com o caso de B=0 e A>0
        denominador = valor_B if valor_B != 0 else 1
        delta_pct = (delta_abs / denominador) * 100
        
        return {"A": valor_A, "B": valor_B, "delta_abs": delta_abs, "delta_pct": delta_pct}

    @staticmethod
    def to_api_v2(kpis_A, kpis_B):
        """
        Recebe os KPIs de dois períodos e retorna a comparação formatada.
        """
        # Garante que os valores padrão sejam usados se os KPIs estiverem ausentes
        faturamento_A = kpis_A.get('faturamento', 0)
        faturamento_B = kpis_B.get('faturamento', 0)
        qtd_vendas_A = kpis_A.get('qtd_vendas', 0)
        qtd_vendas_B = kpis_B.get('qtd_vendas', 0)
        ticket_medio_A = kpis_A.get('ticket_medio', 0)
        ticket_medio_B = kpis_B.get('ticket_medio', 0)

        # Remove o 'delta_abs' do faturamento e ticket médio conforme contrato
        delta_faturamento = ComparativosSerializer._calcular_deltas(faturamento_A, faturamento_B)
        delta_faturamento.pop('delta_abs', None)

        delta_ticket_medio = ComparativosSerializer._calcular_deltas(ticket_medio_A, ticket_medio_B)
        delta_ticket_medio.pop('delta_abs', None)

        # Mantém o 'delta_abs' para qtd_vendas conforme contrato
        delta_qtd_vendas = ComparativosSerializer._calcular_deltas(qtd_vendas_A, qtd_vendas_B)
        delta_qtd_vendas.pop('delta_pct', None)


        return {
            "kpis": {
                "faturamento": delta_faturamento,
                "qtd_vendas": delta_qtd_vendas,
                "ticket_medio": delta_ticket_medio
            }
        }