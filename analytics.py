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
    Busca os dados brutos e calcula os KPIs e o histórico paginado.
    """
    # === PASSO 1: BUSCAR A "MATÉRIA-PRIMA" DO BANCO DE DADOS ===
    pedidos_finalizados = gerenciador_db.obter_pedidos_finalizados_periodo(inicio, fim, local_id)
    mapa_produtos = gerenciador_db.obter_mapa_produtos_analytics()
    
    configuracoes = gerenciador_db.obter_configuracoes()
        
    # === PASSO 2: CALCULAR KPIS E AGREGAR DADOS ===
    total_pedidos = len(pedidos_finalizados)
    faturamento_bruto = sum(p['valor_total'] for p in pedidos_finalizados)
    total_itens_vendidos = 0
    lucro_estimado = 0
    total_perdas_ajustes = 0

    agregacao_pagamentos = {}
    agregacao_itens = {}

    for p in pedidos_finalizados:
        # Calcular Lucro Líquido do Pedido (descontando taxas)
        lucro_bruto_pedido = p['valor_total'] - (p.get('custo_total_pedido') or 0)
        taxa_percentual = configuracoes.get(f"taxa_{p['metodo_pagamento']}", 0)
        desconto_taxa = p['valor_total'] * (taxa_percentual / 100.0)
        lucro_estimado += (lucro_bruto_pedido - desconto_taxa)

        # Agregar por método de pagamento
        metodo = p['metodo_pagamento']
        if metodo not in agregacao_pagamentos:
            agregacao_pagamentos[metodo] = {'valor': 0, 'quantidade': 0}
        agregacao_pagamentos[metodo]['valor'] += p['valor_total']
        agregacao_pagamentos[metodo]['quantidade'] += 1

        # Agregar por item individual e categoria
        try:
            itens_do_pedido = json.loads(p['itens_json'])
            for item in itens_do_pedido:
                produto_id = item['id']
                total_itens_vendidos += item.get('quantidade', 0)

                if produto_id in mapa_produtos:
                    if produto_id not in agregacao_itens:
                        agregacao_itens[produto_id] = {'nome': mapa_produtos[produto_id]['nome'], 'quantidade': 0, 'receita': 0, 'lucro': 0}
                    
                    receita_item = item.get('preco', 0) * item.get('quantidade', 0)
                    custo_item = item.get('custo_unitario', 0) * item.get('quantidade', 0)
                    
                    agregacao_itens[produto_id]['quantidade'] += item.get('quantidade', 0)
                    agregacao_itens[produto_id]['receita'] += receita_item
                    agregacao_itens[produto_id]['lucro'] += (receita_item - custo_item)
        except (json.JSONDecodeError, TypeError):
            continue

    # Formatar dados para os gráficos e listas
    lista_pagamentos_labels = list(agregacao_pagamentos.keys())
    vendas_por_pagamento = {
        "labels": lista_pagamentos_labels,
        "data": [agregacao_pagamentos[label]['valor'] for label in lista_pagamentos_labels]
    }
    
    lista_itens_bruta = sorted(list(agregacao_itens.values()), key=lambda x: x['quantidade'], reverse=True)
    itens_top = lista_itens_bruta[:10]

    # Calcular KPIs Finais
    ticket_medio = faturamento_bruto / total_pedidos if total_pedidos > 0 else 0
    media_itens_pedido = total_itens_vendidos / total_pedidos if total_pedidos > 0 else 0

    
    # === PASSO 3: CALCULAR BALANÇO DE ESTOQUE A PARTIR DO LEDGER ===
    # Define o início absoluto para buscar saldos anteriores
    inicio_absoluto = datetime(2000, 1, 1).isoformat()

    # Busca todas as movimentações relevantes de uma só vez
    movimentacoes_ate_fim = gerenciador_db.obter_movimentacoes_periodo(inicio_absoluto, fim, local_id)

    # Processa as movimentações para calcular o balanço
    balanco_por_produto = {}
    for pid, pinfo in mapa_produtos.items():
        balanco_por_produto[pid] = {
            'nome': pinfo['nome'], 'saldo_anterior': 0,
            'entradas_periodo': 0, 'saidas_periodo': 0
        }

    for mov in movimentacoes_ate_fim:
        pid = mov['produto_id']
        if pid in balanco_por_produto:
            # Lógica do saldo anterior (inalterada)
            if mov['created_at'] < inicio:
                balanco_por_produto[pid]['saldo_anterior'] += mov['quantidade']
            # Lógica do período atual
            else:
                if mov['quantidade'] > 0:
                    balanco_por_produto[pid]['entradas_periodo'] += mov['quantidade']
                else:
                    balanco_por_produto[pid]['saidas_periodo'] += mov['quantidade']

                # NOVA LÓGICA: Se for um ajuste, calcula o valor da perda
                if mov['origem'] == 'ajuste':
                    # O valor da perda é a quantidade (negativa) * custo médio do item
                    valor_perda = mov['quantidade'] * mov['custo_medio']
                    total_perdas_ajustes += valor_perda

    # Formata a lista final de estoque para o frontend
    lista_estoque = []
    for pid, dados in balanco_por_produto.items():
        saldo_inicial = dados['saldo_anterior']
        entradas = dados['entradas_periodo']
        saidas = -dados['saidas_periodo'] # Inverte o sinal para exibição
        saldo_final = saldo_inicial + entradas - saidas

        # Adiciona à lista apenas se houve movimentação ou se ainda há estoque
        if saldo_inicial != 0 or entradas != 0 or saidas != 0 or saldo_final != 0:
            lista_estoque.append({
                "nome": dados['nome'],
                "inicial": saldo_inicial,
                "entradas": entradas,
                "saidas": saidas,
                "final": saldo_final,
                "estoque_do_dia": saldo_inicial + entradas
            })

    # === PASSO 3.5: AGREGAR VENDAS POR PERÍODO (BUCKETS DE 15 MIN) ===
    fuso_horario_local = pytz.timezone('America/Sao_Paulo')

    # O 'inicio' recebido é UTC, representando o início do dia operacional (05:00 em SP).
    # Convertemos para datetime local para servir de âncora para os buckets.
    try:
        inicio_operacional_local = datetime.fromisoformat(inicio.replace('Z', '+00:00')).astimezone(fuso_horario_local)
    except ValueError:
        inicio_operacional_local = datetime.fromisoformat(inicio).astimezone(fuso_horario_local)

    fim_operacional_local = inicio_operacional_local + timedelta(hours=24)

    # Prepara a estrutura de dados com 96 buckets (24h * 4 buckets/hora)
    vendas_por_periodo_labels = []
    vendas_por_periodo_data = [0.0] * 96
    for i in range(96):
        timestamp_bucket = inicio_operacional_local + timedelta(minutes=15 * i)
        vendas_por_periodo_labels.append(timestamp_bucket.strftime('%H:%M'))

    # Itera sobre os pedidos para preencher os buckets
    for p in pedidos_finalizados:
        timestamp_pagamento_str = p.get('timestamp_pagamento')
        if not timestamp_pagamento_str:
            continue

        try:
            # Converte o timestamp do pedido para o fuso local
            if 'Z' in timestamp_pagamento_str:
                timestamp_utc = datetime.fromisoformat(timestamp_pagamento_str.replace('Z', '+00:00'))
            else:
                timestamp_utc = datetime.fromisoformat(timestamp_pagamento_str).astimezone(pytz.utc)

            timestamp_local = timestamp_utc.astimezone(fuso_horario_local)

            # Garante que o pedido está dentro da janela de 24h (robustez)
            if not (inicio_operacional_local <= timestamp_local < fim_operacional_local):
                continue

            # Calcula em qual bucket de 15 minutos o pedido se encaixa
            delta_segundos = (timestamp_local - inicio_operacional_local).total_seconds()
            indice_bucket = int(delta_segundos // (15 * 60))

            if 0 <= indice_bucket < 96:
                vendas_por_periodo_data[indice_bucket] += p.get('valor_total') or 0

        except (ValueError, TypeError):
            continue

    vendas_por_periodo_final = {
        "labels": vendas_por_periodo_labels,
        "data": [round(valor, 2) for valor in vendas_por_periodo_data]
    }

    # === PASSO 4: PAGINAR O HISTÓRICO E PREPARAR PARA SERIALIZAÇÃO ===
    total_registros = len(pedidos_finalizados)
    inicio_paginacao = (page - 1) * limit
    fim_paginacao = inicio_paginacao + limit
    
    dados_brutos = {
        "kpis": {
            "faturamento_bruto": faturamento_bruto,
            "lucro_bruto": lucro_estimado,
            "perdas_ajustes": -total_perdas_ajustes,
            "pedidos": total_pedidos,
            "ticket_medio": ticket_medio,
            "media_itens_pedido": media_itens_pedido
        },
        "itens_top": itens_top,
        "historico_pedidos": {"items": pedidos_finalizados[inicio_paginacao:fim_paginacao]},
        "estoque": lista_estoque,
        # A agregação por período (dia/hora) é complexa e pode ser adicionada depois se necessário.
        # Por enquanto, enviamos vazio para cumprir o contrato da API.
        "vendasPorPeriodo": vendas_por_periodo_final,
        "vendasPorPagamento": vendas_por_pagamento,
        "configuracoes": configuracoes
    }
    
    paginacao = {
        'page': page,
        'limit': limit,
        'total': total_registros
    }

    # === PASSO 5: CHAMAR O SERIALIZER ===
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