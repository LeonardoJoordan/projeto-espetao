# analytics.py
import gerenciador_db
import json
from datetime import datetime, timedelta
import pytz
import serializers

def insights_comparativos(periodoA_inicio, periodoA_fim, periodoB_inicio, periodoB_fim, filtros):
    """
    Calcula e compara KPIs entre dois períodos distintos, aplicando filtros.
    """
    local_id = filtros.get('local_id', 'todos')

    # 1. Pega os dados e calcula os KPIs para cada período
    pedidos_A = gerenciador_db.obter_pedidos_finalizados_periodo(periodoA_inicio, periodoA_fim, local_id)
    kpis_A = _calcular_kpis_para_periodo(pedidos_A)

    pedidos_B = gerenciador_db.obter_pedidos_finalizados_periodo(periodoB_inicio, periodoB_fim, local_id)
    kpis_B = _calcular_kpis_para_periodo(pedidos_B)

    # 2. Compara os resultados usando a função auxiliar de deltas
    kpis_comparados = {
        "faturamento": _calcular_deltas(kpis_A['faturamento'], kpis_B['faturamento']),
        "qtd_vendas": _calcular_deltas(kpis_A['qtd_vendas'], kpis_B['qtd_vendas']),
        "ticket_medio": _calcular_deltas(kpis_A['ticket_medio'], kpis_B['ticket_medio'])
    }

    # 3. Monta o resultado final no formato do contrato
    resultado = {
      "granularidade": filtros.get('granularidade', 'custom'),
      "periodoA":{"inicio": periodoA_inicio, "fim": periodoA_fim},
      "periodoB":{"inicio": periodoB_inicio, "fim": periodoB_fim},
      "kpis": kpis_comparados,
      "rankings":{ # A ser implementado depois
        "produtos":{"mais_vendidos":[],"menos_vendidos":[]},
        "locais":{"mais_lucrativos":[]}
      }
    }
    return resultado

def _calcular_kpis_para_periodo(pedidos_periodo):
    """Função auxiliar para calcular os KPIs de uma lista de pedidos."""
    qtd_vendas = len(pedidos_periodo)
    faturamento = sum(p['valor_total'] for p in pedidos_periodo)
    ticket_medio = faturamento / qtd_vendas if qtd_vendas > 0 else 0
    return {
        "faturamento": faturamento,
        "qtd_vendas": qtd_vendas,
        "ticket_medio": ticket_medio
    }

def _calcular_deltas(valor_A, valor_B):
    """Função auxiliar para calcular a diferença absoluta e percentual."""
    delta_abs = valor_A - valor_B
    # Evita divisão por zero se o valor do período B for 0
    delta_pct = (delta_abs / valor_B * 100) if valor_B != 0 else 0
    return {"A": valor_A, "B": valor_B, "delta_abs": delta_abs, "delta_pct": delta_pct}

def insights_heatmap(inicio, fim, filtros):
    """
    Agrupa os pedidos por dia da semana e hora para criar um heatmap de atividade.
    """
    local_id = filtros.get('local_id', 'todos')
    pedidos = gerenciador_db.obter_pedidos_finalizados_periodo(inicio, fim, local_id)

    # Define nosso fuso horário local
    fuso_horario_local = pytz.timezone('America/Sao_Paulo')
    
    # Dicionário para agregar os dados. A chave será uma tupla (dia_da_semana, hora)
    buckets = {}

    for p in pedidos:
        # Usamos o timestamp de pagamento, pois reflete melhor o início da atividade
        timestamp_pagamento_str = p.get('timestamp_pagamento')
        if not timestamp_pagamento_str:
            continue # Pula pedidos sem data de pagamento

        try:
            # Converte a string ISO para um objeto datetime ciente do fuso UTC
            timestamp_utc = datetime.fromisoformat(timestamp_pagamento_str).astimezone(pytz.utc)
            # Converte o datetime para o nosso fuso local
            timestamp_local = timestamp_utc.astimezone(fuso_horario_local)

            # Extrai o dia da semana (Segunda=0, Domingo=6) e a hora
            dia_semana = timestamp_local.weekday()
            hora = timestamp_local.hour
            
            chave = (dia_semana, hora)
            if chave not in buckets:
                buckets[chave] = {'qtd': 0, 'faturamento': 0}
            
            buckets[chave]['qtd'] += 1
            buckets[chave]['faturamento'] += p['valor_total']

        except (ValueError, TypeError):
            # Ignora timestamps em formato inesperado
            print(f"AVISO: Timestamp de pagamento inválido no pedido ID: {p['id']}")
            continue

    # Formata os buckets para o formato de lista esperado pela API
    lista_buckets = [
        {"dia_semana": chave[0], "hora": chave[1], "qtd": dados['qtd'], "faturamento": dados['faturamento']}
        for chave, dados in buckets.items()
    ]

    return {
      "inicio": inicio,
      "fim": fim,
      "buckets": lista_buckets
    }

# Ao final de analytics.py, adicione as novas funções
def fechamento_operacional_v2(inicio, fim, local_id, page, limit):
    """
    V2: Orquestra a busca de dados e a serialização para o novo formato da API.
    Calcula KPIs de lucro e perdas diretamente do ledger de estoque para máxima precisão.
    """
    # === PASSO 1: BUSCAR A "MATÉRIA-PRIMA" DO BANCO DE DADOS ===
    pedidos_finalizados = gerenciador_db.obter_pedidos_finalizados_periodo(inicio, fim, local_id)
    mapa_produtos = gerenciador_db.obter_mapa_produtos_analytics()
    configuracoes = gerenciador_db.obter_configuracoes()

    # Busca TODAS as movimentações de estoque no período para calcular custos
    movimentacoes_periodo = gerenciador_db.obter_movimentacoes_periodo(inicio, fim, local_id)

    # === PASSO 2: CALCULAR CUSTOS E KPIS DIRETAMENTE DO LEDGER ===
    faturamento_bruto = sum(p['valor_total'] for p in pedidos_finalizados)
    cogs_total = 0  # Custo dos Produtos Vendidos
    perdas_total = 0

    # Itera sobre as movimentações do período para calcular os custos de SAÍDA
    for mov in movimentacoes_periodo:
        if mov['quantidade'] < 0: # Apenas saídas
            custo_da_saida = abs(mov['quantidade']) * (mov.get('custo_unitario_aplicado') or 0)
            if mov['origem'] == 'pedido':
                cogs_total += custo_da_saida
            elif mov['origem'] == 'ajuste':
                perdas_total += custo_da_saida

    lucro_bruto = faturamento_bruto - cogs_total

    # Desconta as taxas de pagamento para chegar ao lucro líquido final
    desconto_total_taxas = 0
    for p in pedidos_finalizados:
        taxa_percentual = configuracoes.get(f"taxa_{p['metodo_pagamento']}", 0)
        desconto_total_taxas += p['valor_total'] * (taxa_percentual / 100.0)

    lucro_liquido_final = lucro_bruto - desconto_total_taxas

    # KPIs restantes
    total_pedidos = len(pedidos_finalizados)
    ticket_medio = faturamento_bruto / total_pedidos if total_pedidos > 0 else 0
    total_itens_vendidos = sum(sum(item.get('quantidade', 0) for item in json.loads(p.get('itens_json') or '[]')) for p in pedidos_finalizados)
    media_itens_pedido = total_itens_vendidos / total_pedidos if total_pedidos > 0 else 0

    # === PASSO 3: AGREGAR DADOS PARA GRÁFICOS E TABELAS ===
    agregacao_pagamentos = {}
    agregacao_itens = {}
    for p in pedidos_finalizados:
        metodo = p['metodo_pagamento']
        if metodo not in agregacao_pagamentos: agregacao_pagamentos[metodo] = {'valor': 0, 'quantidade': 0}
        agregacao_pagamentos[metodo]['valor'] += p['valor_total']
        agregacao_pagamentos[metodo]['quantidade'] += 1
        try:
            itens_do_pedido = json.loads(p.get('itens_json') or '[]')
            for item in itens_do_pedido:
                pid = item['id']
                if pid not in agregacao_itens: agregacao_itens[pid] = {'nome': item['nome'], 'quantidade': 0, 'receita': 0, 'lucro': 0}
                receita = item.get('preco', 0) * item.get('quantidade', 0)
                custo = (item.get('custo_unitario', 0) or 0) * item.get('quantidade', 0)
                agregacao_itens[pid]['quantidade'] += item.get('quantidade', 0)
                agregacao_itens[pid]['receita'] += receita
                agregacao_itens[pid]['lucro'] += (receita - custo)
        except (json.JSONDecodeError, TypeError): continue
    lista_pagamentos_labels = list(agregacao_pagamentos.keys())
    vendas_por_pagamento = {"labels": lista_pagamentos_labels, "data": [agregacao_pagamentos[label]['valor'] for label in lista_pagamentos_labels]}
    itens_top = sorted(list(agregacao_itens.values()), key=lambda x: x['quantidade'], reverse=True)[:10]

    # === PASSO 4: CALCULAR BALANÇO DE ESTOQUE ===
    inicio_absoluto = datetime(2000, 1, 1).isoformat()
    movimentacoes_ate_fim = gerenciador_db.obter_movimentacoes_periodo(inicio_absoluto, fim, local_id)
    balanco_por_produto = {pid: {'nome': pinfo['nome'], 'saldo_anterior': 0, 'entradas_periodo': 0, 'saidas_periodo': 0} for pid, pinfo in mapa_produtos.items()}
    for mov in movimentacoes_ate_fim:
        pid = mov['produto_id']
        if pid in balanco_por_produto:
            if mov['created_at'] < inicio:
                balanco_por_produto[pid]['saldo_anterior'] += mov['quantidade']
            else:
                if mov['quantidade'] > 0: balanco_por_produto[pid]['entradas_periodo'] += mov['quantidade']
                else: balanco_por_produto[pid]['saidas_periodo'] += mov['quantidade']
    lista_estoque = []
    for pid, dados in balanco_por_produto.items():
        saldo_inicial, entradas, saidas = dados['saldo_anterior'], dados['entradas_periodo'], -dados['saidas_periodo']
        saldo_final = saldo_inicial + entradas - saidas
        if saldo_inicial != 0 or entradas != 0 or saidas != 0 or saldo_final != 0:
            lista_estoque.append({"nome": dados['nome'], "inicial": saldo_inicial, "entradas": entradas, "saidas": saidas, "final": saldo_final, "estoque_do_dia": saldo_inicial + entradas})

    # === PASSO 5: AGREGAR VENDAS POR PERÍODO (BUCKETS DE 15 MIN) ===
    fuso_horario_local = pytz.timezone('America/Sao_Paulo')
    try:
        inicio_operacional_local = datetime.fromisoformat(inicio.replace('Z', '+00:00')).astimezone(fuso_horario_local)
    except ValueError:
        inicio_operacional_local = datetime.fromisoformat(inicio).astimezone(fuso_horario_local)
    vendas_por_periodo_labels = [(inicio_operacional_local + timedelta(minutes=15 * i)).strftime('%H:%M') for i in range(96)]
    vendas_por_periodo_data = [0.0] * 96
    for p in pedidos_finalizados:
        ts_pag_str = p.get('timestamp_pagamento')
        if not ts_pag_str: continue
        try:
            ts_utc = datetime.fromisoformat(ts_pag_str.replace('Z', '+00:00')) if 'Z' in ts_pag_str else datetime.fromisoformat(ts_pag_str).astimezone(pytz.utc)
            ts_local = ts_utc.astimezone(fuso_horario_local)
            delta_segundos = (ts_local - inicio_operacional_local).total_seconds()
            indice_bucket = int(delta_segundos // 900)
            if 0 <= indice_bucket < 96:
                vendas_por_periodo_data[indice_bucket] += p.get('valor_total') or 0
        except (ValueError, TypeError): continue
    vendas_por_periodo_final = {"labels": vendas_por_periodo_labels, "data": [round(valor, 2) for valor in vendas_por_periodo_data]}

    # === PASSO 6: PAGINAR O HISTÓRICO E PREPARAR PARA SERIALIZAÇÃO ===
    total_registros = len(pedidos_finalizados)
    inicio_paginacao = (page - 1) * limit
    fim_paginacao = inicio_paginacao + limit
    dados_brutos = {
        "kpis": {
            "faturamento_bruto": faturamento_bruto,
            "lucro_bruto": lucro_liquido_final,
            "perdas_ajustes": perdas_total,
            "pedidos": total_pedidos,
            "ticket_medio": ticket_medio,
            "media_itens_pedido": media_itens_pedido
        },
        "itens_top": itens_top,
        "historico_pedidos": {"items": pedidos_finalizados[inicio_paginacao:fim_paginacao]},
        "estoque": lista_estoque,
        "vendasPorPeriodo": vendas_por_periodo_final,
        "vendasPorPagamento": vendas_por_pagamento,
        "configuracoes": configuracoes
    }
    paginacao = {'page': page, 'limit': limit, 'total': total_registros}

    # === PASSO FINAL: CHAMAR O SERIALIZER ===
    return serializers.FechamentoSerializer.to_api_v2(dados_brutos, paginacao)


def insights_comparativos_v2(periodoA_inicio, periodoA_fim, periodoB_inicio, periodoB_fim, filtros):
    """
    Versão 2: Orquestra a busca e comparação de KPIs para o novo formato da API.
    """
    local_id = filtros.get('local_id', 'todos')

    # Fase 1: Busca os dados para cada período
    pedidos_A = gerenciador_db.obter_pedidos_finalizados_periodo(periodoA_inicio, periodoA_fim, local_id)
    kpis_A = _calcular_kpis_para_periodo(pedidos_A)

    pedidos_B = gerenciador_db.obter_pedidos_finalizados_periodo(periodoB_inicio, periodoB_fim, local_id)
    kpis_B = _calcular_kpis_para_periodo(pedidos_B)
    
    # Fase 2: Serializa os dados para o formato de comparação
    resultado_formatado = serializers.ComparativosSerializer.to_api_v2(kpis_A, kpis_B)

    return resultado_formatado