# analytics.py
import gerenciador_db
import json
from datetime import datetime
import pytz

def fechamento_operacional(inicio, fim, local_id, page, limit):
    """
    Função principal para calcular os dados operacionais do fechamento.
    Busca os dados brutos e calcula os KPIs e o histórico paginado.
    """
    # Passo 1: Buscar a "matéria-prima" do nosso gerenciador de banco de dados
    pedidos_finalizados = gerenciador_db.obter_pedidos_finalizados_periodo(inicio, fim, local_id)
    mapa_produtos = gerenciador_db.obter_mapa_produtos_analytics()
    # Pré-busca todos os dados de movimentação para o cálculo de estoque
    entradas_ate_inicio = gerenciador_db.obter_entradas_estoque_por_produto(inicio)
    saidas_ate_inicio = gerenciador_db.obter_saidas_venda_por_produto(inicio)
    entradas_ate_fim = gerenciador_db.obter_entradas_estoque_por_produto(fim)
    saidas_ate_fim = gerenciador_db.obter_saidas_venda_por_produto(fim)
    lista_de_perdas = gerenciador_db.obter_perdas_periodo(inicio, fim)


    # Passo 2: Calcular os KPIs básicos
    total_pedidos = len(pedidos_finalizados)
    faturamento_bruto = sum(p['valor_total'] for p in pedidos_finalizados)
    ticket_medio = faturamento_bruto / total_pedidos if total_pedidos > 0 else 0
    # O lucro bruto já vem calculado por pedido, então podemos somá-lo
    lucro_bruto = sum(p['custo_total_pedido'] for p in pedidos_finalizados if p['custo_total_pedido'] is not None)
    
    # Passo 3: Paginar o histórico de pedidos
    total_registros = len(pedidos_finalizados)
    inicio_paginacao = (page - 1) * limit
    fim_paginacao = inicio_paginacao + limit
    itens_paginados = pedidos_finalizados[inicio_paginacao:fim_paginacao]

    # Passo 3.5: Calcular agregações
    agregacao_pagamentos = {}
    agregacao_categorias = {}
    agregacao_itens = {}

    for p in pedidos_finalizados:
        # Agregação por método de pagamento
        metodo = p['metodo_pagamento']
        if metodo not in agregacao_pagamentos:
            agregacao_pagamentos[metodo] = {'valor': 0, 'quantidade': 0}
        agregacao_pagamentos[metodo]['valor'] += p['valor_total']
        agregacao_pagamentos[metodo]['quantidade'] += 1

        # Agregação por categoria (requer análise do JSON de itens)
        try:
            itens_do_pedido = json.loads(p['itens_json'])
            for item in itens_do_pedido:
                produto_id = item['id']
                if produto_id in mapa_produtos:
                    categoria = mapa_produtos[produto_id]['categoria']
                    if categoria not in agregacao_categorias:
                        agregacao_categorias[categoria] = {'qtd': 0, 'receita': 0, 'custo': 0, 'lucro': 0}

                    receita_item = item.get('preco', 0) * item.get('quantidade', 0)
                    custo_item = item.get('custo_unitario', 0) * item.get('quantidade', 0)
                    
                    agregacao_categorias[categoria]['qtd'] += item.get('quantidade', 0)
                    agregacao_categorias[categoria]['receita'] += receita_item
                    agregacao_categorias[categoria]['custo'] += custo_item
                    agregacao_categorias[categoria]['lucro'] += (receita_item - custo_item)

                # Agregação por item individual
                    if produto_id not in agregacao_itens:
                        agregacao_itens[produto_id] = {'nome': mapa_produtos[produto_id]['nome'], 'qtd': 0, 'receita': 0, 'custo': 0, 'lucro': 0}

                    agregacao_itens[produto_id]['qtd'] += item.get('quantidade', 0)
                    agregacao_itens[produto_id]['receita'] += receita_item
                    agregacao_itens[produto_id]['custo'] += custo_item
                    agregacao_itens[produto_id]['lucro'] += (receita_item - custo_item)

        except (json.JSONDecodeError, TypeError):
            print(f"AVISO: Não foi possível decodificar itens_json para o pedido ID: {p['id']}")
            continue # Pula para o próximo pedido

    # Formata a saída das agregações para o formato de lista esperado pelo contrato da API
    lista_pagamentos = [
        {"metodo": metodo, "valor": dados['valor'], "quantidade": dados['quantidade']}
        for metodo, dados in agregacao_pagamentos.items()
    ]
    lista_categorias = [
        {"categoria": cat, "qtd": dados['qtd'], "receita": dados['receita'], "custo": dados['custo'], "lucro": dados['lucro']}
        for cat, dados in agregacao_categorias.items()
    ]

    # Formata a lista de itens e ordena para pegar o Top N (ex: Top 10)
    lista_itens_bruta = list(agregacao_itens.values())
    lista_itens_bruta.sort(key=lambda x: x['qtd'], reverse=True)
    lista_itens_top = lista_itens_bruta[:10]

    # Cálculo de estoque por movimento
    lista_estoque = []
    # Usamos as chaves do mapa de produtos como a lista definitiva de todos os produtos existentes
    for pid, pinfo in mapa_produtos.items():
        # Calcula o estoque inicial
        total_entradas_inicio = entradas_ate_inicio.get(pid, 0)
        total_saidas_inicio = saidas_ate_inicio.get(pid, 0)
        estoque_inicial = total_entradas_inicio - total_saidas_inicio

        # Calcula as movimentações no período
        total_entradas_fim = entradas_ate_fim.get(pid, 0)
        total_saidas_fim = saidas_ate_fim.get(pid, 0)
        entradas_periodo = total_entradas_fim - total_entradas_inicio
        saidas_periodo = total_saidas_fim - total_saidas_inicio
        
        # Calcula o estoque final
        estoque_final = estoque_inicial + entradas_periodo - saidas_periodo

        # Adiciona à lista apenas se houve alguma movimentação ou se o estoque não é zero
        if estoque_inicial != 0 or entradas_periodo != 0 or saidas_periodo != 0 or estoque_final != 0:
            lista_estoque.append({
                "produto_id": pid,
                "nome": pinfo['nome'],
                "inicial": estoque_inicial,
                "entradas": entradas_periodo,
                "saidas": -saidas_periodo, # Mostra as saídas como um número positivo
                "final": estoque_final
            })

        # Cálculo do valor de perdas e ajustes
        total_perdas_ajustes = 0
        for perda in lista_de_perdas:
            pid = perda['id_produto']
            if pid in mapa_produtos:
                custo_medio = mapa_produtos[pid].get('custo_medio', 0)
                quantidade_perdida = perda['quantidade_comprada']
                total_perdas_ajustes += abs(quantidade_perdida) * custo_medio

    # Passo 4: Montar o dicionário de resposta
    resultado = {
      "kpis": {
          "faturamento_bruto": faturamento_bruto,
          "ticket_medio": ticket_medio,
          "pedidos": total_pedidos,
          "perdas_ajustes": -total_perdas_ajustes, # Mostrado como negativo
          "lucro_bruto": lucro_bruto
      },
      "pagamentos": lista_pagamentos,
      "categorias": lista_categorias,
      "itens_top": lista_itens_top,
      "estoque": lista_estoque,
      "historico_pedidos": {
          "page": page,
          "limit": limit,
          "total": total_registros,
          "items": itens_paginados
      }
    }

    return resultado

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