"""Relatórios derivados de pagamentos, itens fotografados e ledger global."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
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
               o.operacao_id, o.valor_total_centavos, l.nome AS local_nome
        FROM pagamentos pg
        JOIN pedidos o ON o.id = pg.pedido_id
        JOIN locais l ON l.id = o.local_id
        WHERE pg.ocorrido_em >= ? AND pg.ocorrido_em < ?
    """
    params = [inicio, fim]
    if local_id not in ("todos", None):
        query += " AND o.local_id = ?"
        params.append(int(local_id))
    query += " ORDER BY pg.ocorrido_em, pg.id"
    return conn.execute(query, params).fetchall()


def _visitas_periodo(conn, inicio, fim, local_id):
    query = """
        SELECT o.*, l.nome AS local_nome
        FROM operacoes o
        JOIN locais l ON l.id = o.local_id
        WHERE o.iniciada_em >= ? AND o.iniciada_em < ?
    """
    params = [inicio, fim]
    if local_id not in ("todos", None):
        query += " AND o.local_id = ?"
        params.append(int(local_id))
    query += " ORDER BY o.iniciada_em, o.id"
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
        "custo_total": _reais(row["custo_total_centavos"]),
        "quantidade": row["quantidade"],
        "customizacao": json.loads(row["customizacao_json"])
        if row["customizacao_json"]
        else None,
    }


def _percentual(parte, total):
    return round((parte / total) * 100, 2) if total else 0


def _estrelas_frequencia(percentual):
    """Converte somente a frequência de saída em uma escala de zero a cinco."""
    if percentual is None:
        return None
    if percentual >= 80:
        return 5
    if percentual >= 60:
        return 4
    if percentual >= 40:
        return 3
    if percentual >= 20:
        return 2
    if percentual > 0:
        return 1
    return 0


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
                "acao": "Compare margem, lucro bruto e participação dos produtos antes de ajustar preços.",
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
                "acao": "Preserve a disponibilidade dos itens que sustentam o resultado.",
            }
        )

    produtos_com_contribuicao = [
        produto for produto in produtos if produto["receita"] > 0
    ]
    if produtos_com_contribuicao:
        campeao = produtos_com_contribuicao[0]
        insights.append(
            {
                "nivel": "positivo",
                "titulo": f"{campeao['nome']} liderou a contribuição",
                "descricao": (
                    f"Gerou R$ {campeao['lucro']:.2f} de lucro bruto, "
                    f"com margem de {campeao['margemPercentual']:.1f}%."
                ),
                "acao": "Acompanhe sua frequência de venda e preserve a disponibilidade sem excesso de carga.",
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
        visitas_por_local = defaultdict(set)
        nomes_locais = {}
        visitas_periodo = _visitas_periodo(conn, inicio, fim, local_id)
        frequencias_produtos = defaultdict(
            lambda: {"visitas_disponivel": 0, "visitas_com_venda": 0}
        )
        for visita in visitas_periodo:
            visita_local_id = int(visita["local_id"])
            visitas_por_local[visita_local_id].add(int(visita["id"]))
            nomes_locais[visita_local_id] = visita["local_nome"]
            dados_visita = _analisar_operacao_local(conn, visita)
            for produto_id, produto in dados_visita["produtos"].items():
                frequencia = frequencias_produtos[int(produto_id)]
                frequencia["visitas_disponivel"] += 1
                if int(produto["vendidas"]) > 0:
                    frequencia["visitas_com_venda"] += 1

        inicio_local = datetime.fromisoformat(inicio).astimezone(TZ_LOCAL)
        duracao = datetime.fromisoformat(fim) - datetime.fromisoformat(inicio)
        total_buckets = max(math.ceil(duracao.total_seconds() / 900), 1)
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
            local_evento_id = int(evento["local_id"])
            nomes_locais[local_evento_id] = evento["local_nome"]
            if pedido_id not in cache_itens:
                cache_itens[pedido_id] = _itens_pedido(conn, pedido_id)
            itens = cache_itens[pedido_id]
            custo_pedido = sum(item["custo_total_centavos"] for item in itens)
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
                agregado["custo_centavos"] += sinal * item["custo_total_centavos"]

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
                WHERE impacta_relatorio = 1
                  AND (
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
            """
            SELECT p.id, p.nome, p.ativo,
                   COALESCE(c.nome, 'Sem categoria') AS categoria
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            ORDER BY p.nome
            """
        ).fetchall()
        catalogo_produtos = {
            int(produto["id"]): {
                "nome": produto["nome"],
                "categoria": produto["categoria"],
            }
            for produto in produtos
        }
        estoque = []
        for produto in produtos:
            anterior = int(
                conn.execute(
                    """
                    SELECT COALESCE(SUM(quantidade), 0)
                    FROM (
                        SELECT l.quantidade_inicial + COALESCE((
                                   SELECT SUM(neutro.quantidade)
                                   FROM estoque_movimentacoes neutro
                                   WHERE neutro.lote_id = l.id
                                     AND neutro.impacta_relatorio = 0
                                     AND neutro.created_at < ?
                               ), 0) AS quantidade
                        FROM estoque_lotes l
                        WHERE l.produto_id = ? AND l.recebido_em < ?
                        UNION ALL
                        SELECT quantidade
                        FROM estoque_movimentacoes
                        WHERE produto_id = ? AND lote_id IS NOT NULL
                          AND impacta_relatorio = 1 AND created_at < ?
                    )
                    """,
                    (fim, produto["id"], inicio, produto["id"], inicio),
                ).fetchone()[0]
            )
            movimentos = conn.execute(
                """
                SELECT quantidade
                FROM (
                    SELECT l.quantidade_inicial + COALESCE((
                               SELECT SUM(neutro.quantidade)
                               FROM estoque_movimentacoes neutro
                               WHERE neutro.lote_id = l.id
                                 AND neutro.impacta_relatorio = 0
                                 AND neutro.created_at < ?
                           ), 0) AS quantidade,
                           l.recebido_em AS ocorrido_em
                    FROM estoque_lotes l
                    WHERE l.produto_id = ?
                    UNION ALL
                    SELECT quantidade, created_at AS ocorrido_em
                    FROM estoque_movimentacoes
                    WHERE produto_id = ? AND lote_id IS NOT NULL
                      AND impacta_relatorio = 1
                )
                WHERE ocorrido_em >= ? AND ocorrido_em < ?
                """,
                (fim, produto["id"], produto["id"], inicio, fim),
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
    analise_produtos_por_id = {
        int(item["produtoId"]): dict(item)
        for item in itens_formatados
        if item["receita"] > 0
    }
    for produto_id, frequencia in frequencias_produtos.items():
        if frequencia["visitas_disponivel"] <= 0:
            continue
        if produto_id not in analise_produtos_por_id:
            produto = catalogo_produtos.get(produto_id)
            if not produto:
                continue
            analise_produtos_por_id[produto_id] = {
                "produtoId": produto_id,
                "nome": produto["nome"],
                "categoria": produto["categoria"],
                "quantidade": 0,
                "receita": 0,
                "custo": 0,
                "lucro": 0,
                "margemPercentual": 0,
                "participacaoReceita": 0,
                "precoMedio": 0,
            }

    analise_produtos = []
    for produto_id, item in analise_produtos_por_id.items():
        frequencia = frequencias_produtos.get(produto_id)
        visitas_disponivel = (
            int(frequencia["visitas_disponivel"]) if frequencia else 0
        )
        visitas_com_venda = (
            int(frequencia["visitas_com_venda"]) if frequencia else 0
        )
        frequencia_pct = (
            round(visitas_com_venda / visitas_disponivel * 100, 2)
            if visitas_disponivel > 0
            else None
        )
        item.update(
            {
                "frequenciaPct": frequencia_pct,
                "frequenciaEstrelas": _estrelas_frequencia(frequencia_pct),
                "visitasDisponivel": visitas_disponivel,
                "visitasComVenda": visitas_com_venda,
            }
        )
        analise_produtos.append(item)
    analise_produtos.sort(
        key=lambda item: (-item["lucro"], -item["receita"], item["nome"])
    )

    por_categoria = {}
    for item in itens_formatados:
        categoria = por_categoria.setdefault(
            item["categoria"],
            {
                "nome": item["categoria"],
                "quantidade": 0,
                "receita": 0,
                "custo": 0,
                "lucro": 0,
                "itens": [],
            },
        )
        categoria["quantidade"] += item["quantidade"]
        categoria["receita"] += item["receita"]
        categoria["custo"] += item["custo"]
        categoria["lucro"] += item["lucro"]
        if item["quantidade"] >= 1:
            categoria["itens"].append(
                {
                    "produtoId": item["produtoId"],
                    "nome": item["nome"],
                    "quantidade": item["quantidade"],
                    "receita": item["receita"],
                    "lucro": item["lucro"],
                    "margemPercentual": item["margemPercentual"],
                    "participacaoReceita": item["participacaoReceita"],
                }
            )
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
        categoria["itens"].sort(
            key=lambda item: (
                -item["quantidade"],
                -item["receita"],
                item["nome"],
            )
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
        "contextoAmostra": {
            "visitas": sum(len(ids) for ids in visitas_por_local.values()),
            "locais": len(visitas_por_local),
            "visitasPorLocal": [
                {
                    "localId": local_id,
                    "nome": nomes_locais.get(local_id, f"Local {local_id}"),
                    "visitas": len(visitas_por_local[local_id]),
                }
                for local_id in sorted(visitas_por_local)
            ],
            "tipoValores": "totais",
        },
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
        "periodoA": {
            "kpis": a,
            "produtoDestaque": [
                item for item in dados_a["analiseProdutos"] if item["receita"] > 0
            ][:1],
        },
        "periodoB": {
            "kpis": b,
            "produtoDestaque": [
                item for item in dados_b["analiseProdutos"] if item["receita"] > 0
            ][:1],
        },
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


def _selecionar_operacoes_local(
    conn,
    local_id,
    modo,
    limite,
    inicio,
    fim,
):
    query = """
        SELECT * FROM operacoes
        WHERE local_id = ?
    """
    params = [local_id]
    if modo == "periodo":
        query += " AND iniciada_em >= ? AND iniciada_em < ?"
        params.extend((inicio, fim))
    query += " ORDER BY iniciada_em DESC, id DESC"
    if modo == "ultimas":
        query += " LIMIT ?"
        params.append(limite)
    return list(reversed(conn.execute(query, params).fetchall()))


def _saldo_atual_produto(conn, produto_id):
    return int(
        conn.execute(
            """
            SELECT COALESCE(SUM(
                l.quantidade_inicial + COALESCE((
                    SELECT SUM(m.quantidade)
                    FROM estoque_movimentacoes m
                    WHERE m.lote_id = l.id
                ), 0)
            ), 0)
            FROM estoque_lotes l
            WHERE l.produto_id = ?
            """,
            (produto_id,),
        ).fetchone()[0]
    )


def _analisar_operacao_local(conn, operacao):
    eventos = conn.execute(
        """
        SELECT pg.*, p.id AS pedido_id
        FROM pagamentos pg
        JOIN pedidos p ON p.id = pg.pedido_id
        WHERE p.operacao_id = ?
        ORDER BY pg.ocorrido_em, pg.id
        """,
        (operacao["id"],),
    ).fetchall()
    receita = 0
    taxas = 0
    custo = 0
    pedidos_liquidos = 0
    estornos = 0
    itens_liquidos = defaultdict(int)
    itens_brutos = defaultdict(int)
    horas = defaultdict(lambda: {"faturamento": 0, "pedidos": 0, "unidades": 0})
    cache_itens = {}

    for evento in eventos:
        sinal = 1 if evento["tipo"] == "pagamento" else -1
        pedido_id = int(evento["pedido_id"])
        if pedido_id not in cache_itens:
            cache_itens[pedido_id] = _itens_pedido(conn, pedido_id)
        itens = cache_itens[pedido_id]
        receita += sinal * int(evento["valor_centavos"])
        taxas += sinal * int(evento["taxa_centavos"])
        custo += sinal * sum(int(item["custo_total_centavos"]) for item in itens)
        pedidos_liquidos += sinal
        if sinal < 0:
            estornos += int(evento["valor_centavos"])
        for item in itens:
            produto_id = int(item["produto_id"])
            quantidade = int(item["quantidade"])
            itens_liquidos[produto_id] += sinal * quantidade
            if sinal > 0:
                itens_brutos[produto_id] += quantidade

        if sinal > 0:
            hora = datetime.fromisoformat(evento["ocorrido_em"]).astimezone(
                TZ_LOCAL
            ).hour
            horas[hora]["faturamento"] += int(evento["valor_centavos"])
            horas[hora]["pedidos"] += 1
            horas[hora]["unidades"] += sum(
                int(item["quantidade"]) for item in itens
            )

    snapshots = {
        int(row["produto_id"]): row
        for row in conn.execute(
            """
            SELECT * FROM operacao_estoque
            WHERE operacao_id = ?
            """,
            (operacao["id"],),
        )
    }
    if not snapshots and operacao["status"] == "aberta":
        for produto in conn.execute("SELECT id, ativo FROM produtos"):
            produto_id = int(produto["id"])
            saldo = max(_saldo_atual_produto(conn, produto_id), 0)
            snapshots[produto_id] = {
                "produto_id": produto_id,
                "quantidade_inicial": saldo,
                "quantidade_final": saldo,
                "ativo_no_inicio": int(bool(produto["ativo"])),
            }
    fim_operacao = operacao["encerrada_em"] or datetime.now(timezone.utc).isoformat()
    entradas_durante = set()
    if operacao["origem"] == "real":
        entradas_durante = {
            int(row["produto_id"])
            for row in conn.execute(
                """
                SELECT DISTINCT produto_id
                FROM estoque_lotes
                WHERE recebido_em >= ? AND recebido_em <= ?
                """,
                (operacao["iniciada_em"], fim_operacao),
            )
        }
    ultimo_movimento = {}
    for movimento in conn.execute(
        """
        SELECT produto_id, tipo
        FROM estoque_movimentacoes
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at, id
        """,
        (operacao["iniciada_em"], fim_operacao),
    ):
        ultimo_movimento[int(movimento["produto_id"])] = movimento["tipo"]
    disponiveis = set(itens_brutos) | entradas_durante
    for produto_id, snapshot in snapshots.items():
        final = snapshot["quantidade_final"]
        if bool(snapshot["ativo_no_inicio"]) and (
            int(snapshot["quantidade_inicial"]) > 0
            or (final is not None and int(final) > 0)
        ):
            disponiveis.add(produto_id)

    produtos = {}
    for produto_id in disponiveis:
        snapshot = snapshots.get(produto_id)
        final = snapshot["quantidade_final"] if snapshot else None
        if final is None and operacao["status"] == "aberta":
            final = max(_saldo_atual_produto(conn, produto_id), 0)
        produtos[produto_id] = {
            "vendidas": int(itens_liquidos.get(produto_id, 0)),
            "levadas": (
                int(snapshot["quantidade_inicial"]) if snapshot is not None else None
            ),
            "restantes": int(final) if final is not None else None,
            "esgotou": (
                bool(
                    final == 0
                    and ultimo_movimento.get(produto_id) == "venda"
                )
                if final is not None
                else None
            ),
        }

    return {
        "receita_centavos": receita,
        "taxas_centavos": taxas,
        "custo_centavos": custo,
        "resultado_centavos": receita - custo - taxas,
        "pedidos": pedidos_liquidos,
        "estornos_centavos": estornos,
        "unidades": sum(itens_liquidos.values()),
        "horas": horas,
        "produtos": produtos,
    }


def desempenho_locais(
    local_ids,
    modo="historico",
    limite=6,
    inicio=None,
    fim=None,
):
    """Compara até três locais usando visitas e disponibilidade fotografada."""
    ids = []
    for valor in local_ids or []:
        local_id = int(valor)
        if local_id not in ids:
            ids.append(local_id)
    if not 1 <= len(ids) <= 3:
        raise ValueError("Selecione entre um e três locais.")
    if modo not in {"historico", "ultimas", "periodo"}:
        raise ValueError("Amostra inválida.")
    limite = min(max(int(limite or 1), 1), 100)
    if modo == "periodo" and (not inicio or not fim):
        raise ValueError("O período da análise é obrigatório.")

    with _conexao() as conn:
        placeholders = ",".join("?" for _ in ids)
        locais_rows = conn.execute(
            f"SELECT id, nome FROM locais WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        locais_por_id = {int(row["id"]): row for row in locais_rows}
        if len(locais_por_id) != len(ids):
            raise ValueError("Um dos locais selecionados não existe.")
        produtos_rows = conn.execute(
            """
            SELECT p.id, p.nome, COALESCE(c.nome, 'Sem categoria') AS categoria
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            ORDER BY c.ordem, p.ordem, p.nome
            """
        ).fetchall()
        catalogo = {int(row["id"]): row for row in produtos_rows}

        resultado_locais = []
        for local_id in ids:
            operacoes = _selecionar_operacoes_local(
                conn, local_id, modo, limite, inicio, fim
            )
            agregados_produtos = defaultdict(
                lambda: {
                    "total": 0,
                    "disponivel_visitas": 0,
                    "vendas_por_visita": [],
                    "levadas": [],
                    "restantes": [],
                    "esgotamentos": 0,
                }
            )
            horas = [
                {"faturamento": 0, "pedidos": 0, "unidades": 0}
                for _ in range(24)
            ]
            totais = {
                "receita": 0,
                "taxas": 0,
                "custo": 0,
                "resultado": 0,
                "pedidos": 0,
                "estornos": 0,
                "unidades": 0,
            }

            for operacao in operacoes:
                dados = _analisar_operacao_local(conn, operacao)
                totais["receita"] += dados["receita_centavos"]
                totais["taxas"] += dados["taxas_centavos"]
                totais["custo"] += dados["custo_centavos"]
                totais["resultado"] += dados["resultado_centavos"]
                totais["pedidos"] += dados["pedidos"]
                totais["estornos"] += dados["estornos_centavos"]
                totais["unidades"] += dados["unidades"]
                for hora, valores in dados["horas"].items():
                    for chave in ("faturamento", "pedidos", "unidades"):
                        horas[hora][chave] += valores[chave]
                for produto_id, produto in dados["produtos"].items():
                    agregado = agregados_produtos[produto_id]
                    vendidas = int(produto["vendidas"])
                    agregado["total"] += vendidas
                    agregado["disponivel_visitas"] += 1
                    agregado["vendas_por_visita"].append(vendidas)
                    if produto["levadas"] is not None:
                        agregado["levadas"].append(int(produto["levadas"]))
                    if produto["restantes"] is not None:
                        agregado["restantes"].append(int(produto["restantes"]))
                    if produto["esgotou"]:
                        agregado["esgotamentos"] += 1

            visitas = len(operacoes)
            divisor = max(visitas, 1)
            produtos = []
            for produto_id, agregado in agregados_produtos.items():
                catalogo_item = catalogo.get(produto_id)
                if not catalogo_item:
                    continue
                amostras = agregado["vendas_por_visita"]
                produtos.append(
                    {
                        "produtoId": produto_id,
                        "nome": catalogo_item["nome"],
                        "categoria": catalogo_item["categoria"],
                        "totalVendido": agregado["total"],
                        "mediaPorVisita": round(
                            agregado["total"] / max(len(amostras), 1), 2
                        ),
                        "menorVenda": min(amostras) if amostras else 0,
                        "maiorVenda": max(amostras) if amostras else 0,
                        "visitasDisponivel": agregado["disponivel_visitas"],
                        "visitasSelecionadas": visitas,
                        "mediaLevada": (
                            round(sum(agregado["levadas"]) / len(agregado["levadas"]), 2)
                            if agregado["levadas"]
                            else None
                        ),
                        "mediaRestante": (
                            round(
                                sum(agregado["restantes"])
                                / len(agregado["restantes"]),
                                2,
                            )
                            if agregado["restantes"]
                            else None
                        ),
                        "esgotamentos": agregado["esgotamentos"],
                    }
                )
            produtos.sort(
                key=lambda item: (
                    -item["mediaPorVisita"],
                    -item["totalVendido"],
                    item["nome"],
                )
            )

            pico = max(
                range(24),
                key=lambda hora: (
                    horas[hora]["pedidos"],
                    horas[hora]["faturamento"],
                ),
                default=0,
            )
            tem_atividade = any(item["pedidos"] for item in horas)
            resultado_locais.append(
                {
                    "id": local_id,
                    "nome": locais_por_id[local_id]["nome"],
                    "visitas": visitas,
                    "operacoesInferidas": sum(
                        1 for operacao in operacoes if operacao["origem"] == "inferida"
                    ),
                    "kpis": {
                        "faturamentoTotal": _reais(totais["receita"]),
                        "faturamentoMedio": _reais(totais["receita"] / divisor),
                        "resultadoTotal": _reais(totais["resultado"]),
                        "resultadoMedio": _reais(totais["resultado"] / divisor),
                        "ticketMedio": (
                            _reais(totais["receita"] / totais["pedidos"])
                            if totais["pedidos"] > 0
                            else 0
                        ),
                        "pedidosTotal": totais["pedidos"],
                        "pedidosPorVisita": round(totais["pedidos"] / divisor, 2),
                        "unidadesTotal": totais["unidades"],
                        "unidadesPorVisita": round(totais["unidades"] / divisor, 2),
                        "estornos": _reais(totais["estornos"]),
                        "margemContribuicaoPct": _percentual(
                            totais["resultado"], totais["receita"]
                        ),
                    },
                    "pico": (
                        {
                            "hora": pico,
                            "label": f"{pico:02d}h–{(pico + 1) % 24:02d}h",
                            "pedidosMedios": round(
                                horas[pico]["pedidos"] / divisor, 2
                            ),
                        }
                        if tem_atividade
                        else None
                    ),
                    "horas": [
                        {
                            "hora": hora,
                            "label": f"{hora:02d}h",
                            "faturamentoMedio": _reais(
                                valores["faturamento"] / divisor
                            ),
                            "pedidosMedios": round(
                                valores["pedidos"] / divisor, 2
                            ),
                            "unidadesMedias": round(
                                valores["unidades"] / divisor, 2
                            ),
                        }
                        for hora, valores in enumerate(horas)
                    ],
                    "produtos": produtos,
                }
            )

    return {
        "amostra": {
            "modo": modo,
            "limite": limite if modo == "ultimas" else None,
            "inicio": inicio if modo == "periodo" else None,
            "fim": fim if modo == "periodo" else None,
        },
        "locais": resultado_locais,
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
