"""Relatórios derivados de pagamentos, itens fotografados e ledger global."""

from __future__ import annotations

import json
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

import database


TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


@contextmanager
def _conexao():
    conn = database.conectar()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _reais(centavos: int | float | None) -> float:
    return round(float(centavos or 0) / 100.0, 2)


def periodo_operacional(data_str: str) -> tuple[str, str]:
    dia = date.fromisoformat(data_str)
    inicio_local = datetime.combine(dia, time(5, 0), TZ_LOCAL)
    fim_local = inicio_local + timedelta(days=1)
    return (
        inicio_local.astimezone(timezone.utc).isoformat(),
        fim_local.astimezone(timezone.utc).isoformat(),
    )


def _eventos_pagamento(conn, inicio, fim, local_id):
    query = """
        SELECT pg.*, o.nome_cliente, o.senha_diaria, o.local_id,
               o.valor_total_centavos
        FROM pagamentos pg
        JOIN pedidos o ON o.id = pg.pedido_id
        WHERE pg.ocorrido_em >= ? AND pg.ocorrido_em < ?
    """
    params = [inicio, fim]
    if local_id not in ("todos", None):
        query += " AND o.local_id = ?"
        params.append(int(local_id))
    query += " ORDER BY pg.ocorrido_em, pg.id"
    return conn.execute(query, params).fetchall()


def _itens_pedido(conn, pedido_id):
    return conn.execute(
        """
        SELECT pi.*, pi.categoria_nome AS categoria
        FROM pedido_itens pi
        WHERE pi.pedido_id = ?
        ORDER BY pi.categoria_ordem, pi.produto_ordem, pi.id
        """,
        (pedido_id,),
    ).fetchall()


def _item_api(row):
    return {
        "id": row["produto_id"],
        "nome": row["nome_produto"],
        "preco": _reais(row["preco_unitario_centavos"]),
        "custo_unitario": _reais(row["custo_unitario_centavos"]),
        "quantidade": row["quantidade"],
        "customizacao": json.loads(row["customizacao_json"])
        if row["customizacao_json"]
        else None,
    }


def _percentual(parte, total):
    return round((parte / total) * 100, 2) if total else 0


def _classificar_produtos(itens, margem_referencia):
    """Cria uma matriz simples de contribuição x margem para orientar decisões."""
    candidatos = [item for item in itens if item["receita"] > 0]
    if not candidatos:
        return []

    mediana_receita = median(item["receita"] for item in candidatos)
    mediana_margem = median(item["margemPercentual"] for item in candidatos)
    referencia_margem = mediana_margem if len(candidatos) > 1 else margem_referencia

    orientacoes = {
        "estrela": (
            "Estrela",
            "Proteja a disponibilidade e mantenha o padrão: combina contribuição e margem.",
        ),
        "volume": (
            "Alto volume",
            "Vende bem, mas entrega margem menor. Revise custo, porção ou preço.",
        ),
        "oportunidade": (
            "Oportunidade",
            "Boa margem com menor participação. Teste mais destaque e oferta combinada.",
        ),
        "revisar": (
            "Revisar",
            "Baixa contribuição e margem. Reavalie preço, custo ou permanência no cardápio.",
        ),
    }
    for item in candidatos:
        alta_receita = item["receita"] >= mediana_receita
        alta_margem = item["margemPercentual"] >= referencia_margem
        if alta_receita and alta_margem:
            chave = "estrela"
        elif alta_receita:
            chave = "volume"
        elif alta_margem:
            chave = "oportunidade"
        else:
            chave = "revisar"
        item["classificacao"] = chave
        item["classificacaoLabel"], item["recomendacao"] = orientacoes[chave]
    return sorted(candidatos, key=lambda item: (item["lucro"], item["receita"]), reverse=True)


def _montar_insights(
    kpis, produtos, estoque, desempenho_hora, concentracao_top3
):
    insights = []
    faturamento = kpis["faturamentoLiquido"]
    resultado = kpis["resultadoOperacional"]

    if kpis["pedidosPagos"] == 0:
        insights.append(
            {
                "nivel": "informativo",
                "titulo": "Sem vendas pagas no período",
                "descricao": "Ainda não há base financeira para avaliar desempenho.",
                "acao": "Confirme a data selecionada e se os pagamentos foram registrados.",
            }
        )
    elif resultado < 0:
        insights.append(
            {
                "nivel": "critico",
                "titulo": "Operação fechou no negativo",
                "descricao": (
                    f"O resultado foi de -R$ {abs(resultado):.2f} "
                    f"e a margem operacional ficou em {kpis['margemOperacionalPct']:.1f}%."
                ),
                "acao": "Priorize custos dos produtos, perdas e taxas antes de buscar mais volume.",
            }
        )
    elif kpis["margemOperacionalPct"] < 15:
        insights.append(
            {
                "nivel": "atencao",
                "titulo": "Margem operacional apertada",
                "descricao": (
                    f"De cada R$ 100 vendidos, R$ {kpis['margemOperacionalPct']:.2f} "
                    "permaneceram após CMV, taxas e perdas."
                ),
                "acao": "Revise primeiro os itens classificados como “Alto volume” ou “Revisar”.",
            }
        )
    else:
        insights.append(
            {
                "nivel": "positivo",
                "titulo": "Resultado operacional saudável",
                "descricao": (
                    f"A operação reteve {kpis['margemOperacionalPct']:.1f}% "
                    "do faturamento líquido no período."
                ),
                "acao": "Preserve os produtos estrela e monitore a disponibilidade deles.",
            }
        )

    if produtos:
        campeao = produtos[0]
        insights.append(
            {
                "nivel": "positivo",
                "titulo": f"{campeao['nome']} liderou a contribuição",
                "descricao": (
                    f"Gerou R$ {campeao['lucro']:.2f} de lucro bruto, "
                    f"com margem de {campeao['margemPercentual']:.1f}%."
                ),
                "acao": campeao["recomendacao"],
            }
        )

    pico = max(desempenho_hora, key=lambda item: item["faturamento"], default=None)
    if pico and pico["faturamento"] > 0:
        insights.append(
            {
                "nivel": "informativo",
                "titulo": f"Maior janela de venda: {pico['label']}",
                "descricao": (
                    f"Essa hora concentrou R$ {pico['faturamento']:.2f} "
                    f"e {pico['pedidos']} pedidos pagos."
                ),
                "acao": "Garanta equipe, produção e reposição prontas antes desse horário.",
            }
        )

    riscos = [
        item
        for item in estoque
        if item.get("ativo") and item["status"] in {"ruptura", "critico", "atencao"}
    ]
    if riscos:
        urgente = riscos[0]
        cobertura = urgente.get("coberturaDias")
        detalhe = (
            "sem saldo disponível"
            if urgente["status"] == "ruptura"
            else f"cobertura estimada de {cobertura:.1f} dias no ritmo do período"
        )
        insights.append(
            {
                "nivel": "critico" if urgente["status"] in {"ruptura", "critico"} else "atencao",
                "titulo": f"Reposição: {urgente['nome']}",
                "descricao": f"O produto está {detalhe}.",
                "acao": f"Revise a compra e mais {max(len(riscos) - 1, 0)} alerta(s) de estoque.",
            }
        )

    if kpis["taxaEstornoPct"] >= 5:
        insights.append(
            {
                "nivel": "atencao",
                "titulo": "Estornos acima de 5% do faturamento bruto",
                "descricao": f"A taxa de estorno foi de {kpis['taxaEstornoPct']:.1f}%.",
                "acao": "Investigue os pedidos estornados e identifique causas recorrentes.",
            }
        )
    elif faturamento > 0 and concentracao_top3 >= 70:
        insights.append(
            {
                "nivel": "atencao",
                "titulo": "Receita concentrada em poucos produtos",
                "descricao": f"Os três principais itens representam {concentracao_top3:.1f}% da receita.",
                "acao": "Proteja o estoque desses itens e desenvolva alternativas de boa margem.",
            }
        )

    return insights[:5]


def _calcular_fechamento(inicio, fim, local_id="todos"):
    with _conexao() as conn:
        eventos = _eventos_pagamento(conn, inicio, fim, local_id)
        faturamento_bruto = 0
        estornos = 0
        taxas_liquidas = 0
        cmv_liquido = 0
        pedidos_pagos = 0
        pedidos_estornados = 0
        itens_pagos = 0
        itens_liquidos = 0
        pagamentos_por_metodo = defaultdict(int)
        itens_agregados = {}
        historico = []
        cache_itens = {}

        inicio_local = datetime.fromisoformat(inicio).astimezone(TZ_LOCAL)
        duracao = datetime.fromisoformat(fim) - datetime.fromisoformat(inicio)
        total_buckets = max(int(duracao.total_seconds() // 900), 1)
        labels = [
            (inicio_local + timedelta(minutes=15 * indice)).strftime("%H:%M")
            for indice in range(total_buckets)
        ]
        vendas_periodo = [0] * total_buckets
        pedidos_periodo = [0] * total_buckets
        estornos_periodo = [0] * total_buckets

        for evento in eventos:
            sinal = 1 if evento["tipo"] == "pagamento" else -1
            if evento["tipo"] == "pagamento":
                faturamento_bruto += evento["valor_centavos"]
                pedidos_pagos += 1
            else:
                estornos += evento["valor_centavos"]
                pedidos_estornados += 1
            taxas_liquidas += sinal * evento["taxa_centavos"]
            pagamentos_por_metodo[evento["metodo"]] += sinal * evento["valor_centavos"]

            pedido_id = evento["pedido_id"]
            if pedido_id not in cache_itens:
                cache_itens[pedido_id] = _itens_pedido(conn, pedido_id)
            itens = cache_itens[pedido_id]
            custo_pedido = sum(
                item["custo_unitario_centavos"] * item["quantidade"] for item in itens
            )
            cmv_liquido += sinal * custo_pedido
            if sinal > 0:
                itens_pagos += sum(item["quantidade"] for item in itens)
            itens_liquidos += sinal * sum(item["quantidade"] for item in itens)

            for item in itens:
                chave = item["produto_id"]
                agregado = itens_agregados.setdefault(
                    chave,
                    {
                        "produto_id": item["produto_id"],
                        "nome": item["nome_produto"],
                        "categoria": item["categoria"],
                        "quantidade": 0,
                        "receita_centavos": 0,
                        "custo_centavos": 0,
                    },
                )
                agregado["quantidade"] += sinal * item["quantidade"]
                agregado["receita_centavos"] += (
                    sinal * item["preco_unitario_centavos"] * item["quantidade"]
                )
                agregado["custo_centavos"] += (
                    sinal * item["custo_unitario_centavos"] * item["quantidade"]
                )

            horario = datetime.fromisoformat(evento["ocorrido_em"])
            indice = int(
                (horario - datetime.fromisoformat(inicio)).total_seconds() // 900
            )
            if 0 <= indice < total_buckets:
                vendas_periodo[indice] += sinal * evento["valor_centavos"]
                if sinal > 0:
                    pedidos_periodo[indice] += 1
                else:
                    estornos_periodo[indice] += 1

            itens_api = [_item_api(item) for item in itens]
            historico.append(
                {
                    "id": pedido_id,
                    "nome_cliente": evento["nome_cliente"],
                    "horario": evento["ocorrido_em"],
                    "valor_total": sinal * _reais(evento["valor_centavos"]),
                    "metodo_pagamento": evento["metodo"],
                    "tipo": evento["tipo"],
                    "senha_diaria": evento["senha_diaria"],
                    "itens_json": json.dumps(itens_api, ensure_ascii=False),
                }
            )

        faturamento_liquido = faturamento_bruto - estornos
        lucro_bruto = faturamento_liquido - cmv_liquido

        perdas_centavos = int(
            conn.execute(
                """
                SELECT COALESCE(SUM(ABS(quantidade) * custo_unitario_centavos), 0)
                FROM estoque_movimentacoes
                WHERE (
                    tipo = 'perda'
                    OR (tipo = 'ajuste' AND quantidade < 0)
                )
                  AND created_at >= ? AND created_at < ?
                """,
                (inicio, fim),
            ).fetchone()[0]
        )
        resultado_operacional = lucro_bruto - taxas_liquidas - perdas_centavos
        ticket_medio = (
            _reais(faturamento_bruto) / pedidos_pagos if pedidos_pagos else 0
        )
        media_itens = itens_pagos / pedidos_pagos if pedidos_pagos else 0
        margem_bruta_pct = _percentual(lucro_bruto, faturamento_liquido)
        margem_operacional_pct = _percentual(resultado_operacional, faturamento_liquido)
        taxa_estorno_pct = _percentual(estornos, faturamento_bruto)
        cmv_pct = _percentual(cmv_liquido, faturamento_liquido)
        taxas_pct = _percentual(taxas_liquidas, faturamento_liquido)
        duracao_dias = max(duracao.total_seconds() / 86400, 1)

        produtos = conn.execute(
            "SELECT id, nome, ativo FROM produtos ORDER BY nome"
        ).fetchall()
        estoque = []
        for produto in produtos:
            anterior = int(
                conn.execute(
                    """
                    SELECT COALESCE(SUM(quantidade), 0)
                    FROM estoque_movimentacoes
                    WHERE produto_id = ? AND created_at < ?
                    """,
                    (produto["id"], inicio),
                ).fetchone()[0]
            )
            movimentos = conn.execute(
                """
                SELECT quantidade FROM estoque_movimentacoes
                WHERE produto_id = ? AND created_at >= ? AND created_at < ?
                """,
                (produto["id"], inicio, fim),
            ).fetchall()
            entradas = sum(max(int(row["quantidade"]), 0) for row in movimentos)
            saidas = sum(abs(min(int(row["quantidade"]), 0)) for row in movimentos)
            final = anterior + entradas - saidas
            ativo = bool(produto["ativo"])
            if anterior or entradas or saidas or final:
                estoque.append(
                    {
                        "produtoId": produto["id"],
                        "nome": produto["nome"],
                        "ativo": ativo,
                        "inicial": anterior,
                        "entradas": entradas,
                        "saidas": saidas,
                        "final": final,
                    }
                )

    itens_formatados = [
        {
            "produtoId": dados["produto_id"],
            "nome": dados["nome"],
            "categoria": dados["categoria"],
            "quantidade": dados["quantidade"],
            "receita": _reais(dados["receita_centavos"]),
            "custo": _reais(dados["custo_centavos"]),
            "lucro": _reais(dados["receita_centavos"] - dados["custo_centavos"]),
            "margemPercentual": _percentual(
                dados["receita_centavos"] - dados["custo_centavos"],
                dados["receita_centavos"],
            ),
            "participacaoReceita": _percentual(
                dados["receita_centavos"], faturamento_liquido
            ),
            "precoMedio": _reais(
                dados["receita_centavos"] / dados["quantidade"]
                if dados["quantidade"]
                else 0
            ),
        }
        for dados in itens_agregados.values()
        if dados["quantidade"] or dados["receita_centavos"]
    ]
    itens_formatados.sort(key=lambda item: item["quantidade"], reverse=True)
    analise_produtos = _classificar_produtos(itens_formatados, margem_bruta_pct)

    por_categoria = {}
    for item in itens_formatados:
        categoria = por_categoria.setdefault(
            item["categoria"],
            {"nome": item["categoria"], "quantidade": 0, "receita": 0, "custo": 0, "lucro": 0},
        )
        categoria["quantidade"] += item["quantidade"]
        categoria["receita"] += item["receita"]
        categoria["custo"] += item["custo"]
        categoria["lucro"] += item["lucro"]
    categorias = []
    for categoria in por_categoria.values():
        categoria["receita"] = round(categoria["receita"], 2)
        categoria["custo"] = round(categoria["custo"], 2)
        categoria["lucro"] = round(categoria["lucro"], 2)
        categoria["margemPercentual"] = _percentual(
            categoria["lucro"], categoria["receita"]
        )
        categoria["participacaoReceita"] = _percentual(
            categoria["receita"], _reais(faturamento_liquido)
        )
        categorias.append(categoria)
    categorias.sort(key=lambda item: item["receita"], reverse=True)

    vendas_por_produto = {
        item["produtoId"]: max(item["quantidade"], 0) for item in itens_formatados
    }
    ordem_status = {"ruptura": 0, "critico": 1, "atencao": 2, "saudavel": 3, "sem_giro": 4, "arquivado": 5}
    for item in estoque:
        vendidas = vendas_por_produto.get(item["produtoId"], 0)
        ritmo = vendidas / duracao_dias
        cobertura = item["final"] / ritmo if ritmo > 0 else None
        if not item["ativo"]:
            status = "arquivado"
        elif item["final"] <= 0:
            status = "ruptura"
        elif cobertura is None:
            status = "sem_giro"
        elif cobertura <= 2:
            status = "critico"
        elif cobertura <= 7:
            status = "atencao"
        else:
            status = "saudavel"
        item.update(
            {
                "vendidas": vendidas,
                "ritmoDiario": round(ritmo, 2),
                "coberturaDias": round(cobertura, 1) if cobertura is not None else None,
                "status": status,
            }
        )
    estoque.sort(key=lambda item: (ordem_status[item["status"]], item["final"], item["nome"]))

    desempenho_hora = []
    for posicao_hora in range(24):
        receita = 0
        pedidos_hora = 0
        estornos_hora = 0
        for indice_hora in range(posicao_hora * 4, total_buckets, 24 * 4):
            receita += sum(vendas_periodo[indice_hora : indice_hora + 4])
            pedidos_hora += sum(pedidos_periodo[indice_hora : indice_hora + 4])
            estornos_hora += sum(estornos_periodo[indice_hora : indice_hora + 4])
        desempenho_hora.append(
            {
                "label": labels[posicao_hora * 4]
                if posicao_hora * 4 < len(labels)
                else f"{posicao_hora:02d}:00",
                "faturamento": _reais(receita),
                "pedidos": pedidos_hora,
                "estornos": estornos_hora,
            }
        )

    receita_positiva = sum(max(item["receita"], 0) for item in itens_formatados)
    concentracao_top3 = _percentual(
        sum(max(item["receita"], 0) for item in sorted(
            itens_formatados, key=lambda item: item["receita"], reverse=True
        )[:3]),
        receita_positiva,
    )

    metodos = ["pix", "cartao_credito", "cartao_debito", "dinheiro"]
    kpis = {
        "faturamentoBruto": _reais(faturamento_bruto),
        "estornos": _reais(estornos),
        "faturamentoLiquido": _reais(faturamento_liquido),
        "cmv": _reais(cmv_liquido),
        "lucroBruto": _reais(lucro_bruto),
        "taxasPagamento": _reais(taxas_liquidas),
        "perdasAjustes": _reais(perdas_centavos),
        "resultadoOperacional": _reais(resultado_operacional),
        "lucroEstimado": _reais(resultado_operacional),
        "pedidosPagos": pedidos_pagos,
        "pedidosEstornados": pedidos_estornados,
        "pedidosRealizados": pedidos_pagos,
        "ticketMedio": round(ticket_medio, 2),
        "mediaItensPedido": round(media_itens, 2),
        "unidadesVendidas": itens_liquidos,
        "margemBrutaPct": margem_bruta_pct,
        "margemOperacionalPct": margem_operacional_pct,
        "taxaEstornoPct": taxa_estorno_pct,
        "cmvPct": cmv_pct,
        "taxasPct": taxas_pct,
        "receitaPorItem": round(
            _reais(faturamento_liquido) / itens_liquidos, 2
        ) if itens_liquidos > 0 else 0,
    }
    insights = _montar_insights(
        kpis, analise_produtos, estoque, desempenho_hora, concentracao_top3
    )
    if total_buckets <= 24 * 4:
        serie_labels = labels
        serie_valores = vendas_periodo
        granularidade = "15_minutos"
        granularidade_label = "Intervalos de 15 minutos"
    else:
        quantidade_dias = (total_buckets + (24 * 4) - 1) // (24 * 4)
        serie_labels = [
            (inicio_local + timedelta(days=indice)).strftime("%d/%m")
            for indice in range(quantidade_dias)
        ]
        serie_valores = [
            sum(vendas_periodo[indice * 24 * 4 : (indice + 1) * 24 * 4])
            for indice in range(quantidade_dias)
        ]
        granularidade = "dia_operacional"
        granularidade_label = "Consolidado por dia operacional"

    return {
        "kpis": kpis,
        "itens": itens_formatados,
        "analiseProdutos": analise_produtos,
        "categorias": categorias,
        "desempenhoPorHora": desempenho_hora,
        "composicaoResultado": [
            {"chave": "faturamento", "label": "Faturamento bruto", "valor": _reais(faturamento_bruto), "tipo": "entrada"},
            {"chave": "estornos", "label": "Estornos", "valor": -_reais(estornos), "tipo": "saida"},
            {"chave": "cmv", "label": "CMV líquido", "valor": -_reais(cmv_liquido), "tipo": "saida"},
            {"chave": "taxas", "label": "Taxas de pagamento", "valor": -_reais(taxas_liquidas), "tipo": "saida"},
            {"chave": "perdas", "label": "Perdas e ajustes", "valor": -_reais(perdas_centavos), "tipo": "saida"},
            {"chave": "resultado", "label": "Resultado operacional", "valor": _reais(resultado_operacional), "tipo": "resultado"},
        ],
        "resumoExecutivo": {
            "insights": insights,
            "concentracaoTop3Pct": concentracao_top3,
            "alertasEstoque": sum(
                1 for item in estoque
                if item["ativo"] and item["status"] in {"ruptura", "critico", "atencao"}
            ),
        },
        "historico": historico,
        "estoque": estoque,
        "vendasPorPeriodo": {
            "labels": serie_labels,
            "data": [_reais(valor) for valor in serie_valores],
            "granularidade": granularidade,
            "granularidadeLabel": granularidade_label,
        },
        "vendasPorPagamento": {
            "labels": metodos,
            "data": [_reais(pagamentos_por_metodo[metodo]) for metodo in metodos],
        },
        "periodo": {"inicio": inicio, "fim": fim},
        "estoqueGlobal": True,
    }


def fechamento_operacional_v2(inicio, fim, local_id, page, limit):
    dados = _calcular_fechamento(inicio, fim, local_id)
    page = max(int(page or 1), 1)
    limit = min(max(int(limit or 50), 1), 100)
    inicio_slice = (page - 1) * limit
    historico = dados.pop("historico")
    itens = dados.pop("itens")
    dados["itens_top"] = itens[:10]
    dados["historico_pedidos"] = {
        "items": historico[inicio_slice : inicio_slice + limit],
        "page": page,
        "limit": limit,
        "total": len(historico),
    }
    return dados


def _delta(valor_a, valor_b):
    if valor_b == 0:
        percentual = 0 if valor_a == 0 else 100
    else:
        percentual = ((valor_a - valor_b) / abs(valor_b)) * 100
    return {
        "A": valor_a,
        "B": valor_b,
        "delta_abs": valor_a - valor_b,
        "delta_pct": percentual,
    }


def insights_comparativos_v2(
    periodoA_inicio, periodoA_fim, periodoB_inicio, periodoB_fim, filtros
):
    local_id = filtros.get("local_id", "todos")
    dados_a = _calcular_fechamento(periodoA_inicio, periodoA_fim, local_id)
    dados_b = _calcular_fechamento(periodoB_inicio, periodoB_fim, local_id)
    a = dados_a["kpis"]
    b = dados_b["kpis"]
    kpis = {
        "faturamento": _delta(a["faturamentoLiquido"], b["faturamentoLiquido"]),
        "qtd_vendas": _delta(a["pedidosPagos"], b["pedidosPagos"]),
        "ticket_medio": _delta(a["ticketMedio"], b["ticketMedio"]),
        "resultado_operacional": _delta(
            a["resultadoOperacional"], b["resultadoOperacional"]
        ),
        "margem_operacional": _delta(
            a["margemOperacionalPct"], b["margemOperacionalPct"]
        ),
        "estornos": _delta(a["estornos"], b["estornos"]),
        "unidades": _delta(a["unidadesVendidas"], b["unidadesVendidas"]),
    }

    leituras = []
    if a["faturamentoLiquido"] != b["faturamentoLiquido"]:
        melhorou = a["faturamentoLiquido"] > b["faturamentoLiquido"]
        leituras.append(
            {
                "nivel": "positivo" if melhorou else "atencao",
                "titulo": "Faturamento líquido "
                + ("cresceu" if melhorou else "recuou"),
                "descricao": (
                    f"O período A ficou R$ {abs(kpis['faturamento']['delta_abs']):.2f} "
                    + ("acima" if melhorou else "abaixo")
                    + " do período B."
                ),
            }
        )
    if a["margemOperacionalPct"] != b["margemOperacionalPct"]:
        melhorou = a["margemOperacionalPct"] > b["margemOperacionalPct"]
        leituras.append(
            {
                "nivel": "positivo" if melhorou else "atencao",
                "titulo": "Eficiência "
                + ("melhorou" if melhorou else "piorou"),
                "descricao": (
                    f"A margem operacional variou "
                    f"{abs(kpis['margem_operacional']['delta_abs']):.1f} ponto(s) percentual(is)."
                ),
            }
        )
    if a["estornos"] > b["estornos"]:
        leituras.append(
            {
                "nivel": "atencao",
                "titulo": "Estornos aumentaram",
                "descricao": (
                    f"O período A teve R$ {kpis['estornos']['delta_abs']:.2f} "
                    "a mais em estornos."
                ),
            }
        )

    return {
        "kpis": kpis,
        "leituras": leituras,
        "periodoA": {"kpis": a, "produtoDestaque": dados_a["analiseProdutos"][:1]},
        "periodoB": {"kpis": b, "produtoDestaque": dados_b["analiseProdutos"][:1]},
    }


def insights_heatmap(inicio, fim, filtros):
    local_id = filtros.get("local_id", "todos")
    buckets = defaultdict(lambda: {"qtd": 0, "faturamento": 0})
    with _conexao() as conn:
        for evento in _eventos_pagamento(conn, inicio, fim, local_id):
            sinal = 1 if evento["tipo"] == "pagamento" else -1
            local = datetime.fromisoformat(evento["ocorrido_em"]).astimezone(TZ_LOCAL)
            bucket = buckets[(local.weekday(), local.hour)]
            bucket["qtd"] += sinal
            bucket["faturamento"] += sinal * evento["valor_centavos"]
    return {
        "inicio": inicio,
        "fim": fim,
        "buckets": [
            {
                "dia_semana": chave[0],
                "hora": chave[1],
                "qtd": valor["qtd"],
                "faturamento": _reais(valor["faturamento"]),
            }
            for chave, valor in sorted(buckets.items())
        ],
    }


def relatorio_impressao(data_str):
    inicio, fim = periodo_operacional(data_str)
    dados = _calcular_fechamento(inicio, fim, "todos")
    if not dados["historico"]:
        return None
    por_categoria = defaultdict(list)
    for item in dados["itens"]:
        por_categoria[item["categoria"]].append(
            {
                "nome": item["nome"],
                "quantidade": item["quantidade"],
                "valor": item["receita"],
            }
        )
    horarios = [
        datetime.fromisoformat(evento["horario"])
        for evento in dados["historico"]
        if evento["tipo"] == "pagamento"
    ]
    duracao = "N/A"
    if horarios:
        segundos = int((max(horarios) - min(horarios)).total_seconds())
        horas, resto = divmod(max(segundos, 0), 3600)
        minutos = resto // 60
        duracao = f"{horas}h {minutos}min"
    kpis = dados["kpis"]
    return {
        "sumario": {
            "total_pedidos": kpis["pedidosPagos"],
            "faturamento_bruto": kpis["faturamentoBruto"],
            "estornos": kpis["estornos"],
            "faturamento_liquido": kpis["faturamentoLiquido"],
            "cmv": kpis["cmv"],
            "lucro_bruto_aproximado": kpis["lucroBruto"],
            "taxas_pagamento": kpis["taxasPagamento"],
            "perdas": kpis["perdasAjustes"],
            "resultado_operacional": kpis["resultadoOperacional"],
            "ticket_medio": kpis["ticketMedio"],
            "tempo_operacao": duracao,
            "data_relatorio": date.fromisoformat(data_str).strftime("%d/%m/%Y"),
        },
        "itens_por_categoria": dict(sorted(por_categoria.items())),
    }
