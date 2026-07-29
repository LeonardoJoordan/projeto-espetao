"""Shapes vazios estáveis usados somente em respostas de erro da API."""


class FechamentoSerializer:
    @staticmethod
    def to_api_v2(dados_brutos=None, paginacao=None):
        dados_brutos = dados_brutos or {}
        paginacao = paginacao or {}
        return {
            "kpis": {
                "faturamentoBruto": 0,
                "estornos": 0,
                "faturamentoLiquido": 0,
                "cmv": 0,
                "lucroBruto": 0,
                "taxasPagamento": 0,
                "perdasAjustes": 0,
                "resultadoOperacional": 0,
                "lucroEstimado": 0,
                "pedidosPagos": 0,
                "pedidosEstornados": 0,
                "pedidosRealizados": 0,
                "ticketMedio": 0,
                "mediaItensPedido": 0,
                "unidadesVendidas": 0,
                "margemBrutaPct": 0,
                "margemOperacionalPct": 0,
                "taxaEstornoPct": 0,
                "cmvPct": 0,
                "taxasPct": 0,
                "receitaPorItem": 0,
                **dados_brutos.get("kpis", {}),
            },
            "itens_top": dados_brutos.get("itens_top", []),
            "analiseProdutos": dados_brutos.get("analiseProdutos", []),
            "categorias": dados_brutos.get("categorias", []),
            "desempenhoPorHora": dados_brutos.get("desempenhoPorHora", []),
            "composicaoResultado": dados_brutos.get("composicaoResultado", []),
            "resumoExecutivo": dados_brutos.get(
                "resumoExecutivo",
                {"insights": [], "concentracaoTop3Pct": 0, "alertasEstoque": 0},
            ),
            "historico_pedidos": {
                "items": [],
                "page": paginacao.get("page", 1),
                "limit": paginacao.get("limit", 50),
                "total": paginacao.get("total", 0),
                **dados_brutos.get("historico_pedidos", {}),
            },
            "estoque": dados_brutos.get("estoque", []),
            "vendasPorPeriodo": dados_brutos.get(
                "vendasPorPeriodo",
                {
                    "labels": [],
                    "data": [],
                    "granularidade": "15_minutos",
                    "granularidadeLabel": "Intervalos de 15 minutos",
                },
            ),
            "vendasPorPagamento": dados_brutos.get(
                "vendasPorPagamento", {"labels": [], "data": []}
            ),
            "estoqueGlobal": True,
        }


class ComparativosSerializer:
    @staticmethod
    def to_api_v2(kpis_a=None, kpis_b=None):
        vazio = {"A": 0, "B": 0, "delta_abs": 0, "delta_pct": 0}
        return {
            "kpis": {
                "faturamento": dict(vazio),
                "qtd_vendas": dict(vazio),
                "ticket_medio": dict(vazio),
                "resultado_operacional": dict(vazio),
                "margem_operacional": dict(vazio),
                "estornos": dict(vazio),
                "unidades": dict(vazio),
            }
        }
