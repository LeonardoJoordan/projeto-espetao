"""Operações transacionais do PDV sobre o esquema canônico v2."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import database


NOME_BANCO_DADOS = database.NOME_BANCO_DADOS
TIMEZONE_LOCAL = ZoneInfo("America/Sao_Paulo")
METODOS_PAGAMENTO = {"pix", "cartao_credito", "cartao_debito", "dinheiro"}
MODALIDADES = {"local", "viagem"}


def _conectar() -> sqlite3.Connection:
    return database.conectar()


@contextmanager
def _conexao():
    conn = _conectar()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _para_centavos(valor) -> int:
    return int(
        (Decimal(str(valor or 0)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _para_reais(centavos) -> float:
    return round(int(centavos or 0) / 100.0, 2)


def _limpar_reservas(cursor: sqlite3.Cursor) -> None:
    cursor.execute("DELETE FROM reservas_carrinho WHERE expires_at <= ?", (_agora(),))


def _saldo_produto(cursor: sqlite3.Cursor, produto_id: int) -> int:
    return int(
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantidade), 0)
            FROM estoque_movimentacoes
            WHERE produto_id = ?
            """,
            (produto_id,),
        ).fetchone()[0]
    )


def _custo_medio_centavos(cursor: sqlite3.Cursor, produto_id: int) -> int:
    row = cursor.execute(
        """
        SELECT COALESCE(SUM(quantidade), 0) AS quantidade,
               COALESCE(SUM(quantidade * custo_unitario_centavos), 0) AS valor
        FROM estoque_movimentacoes
        WHERE produto_id = ?
        """,
        (produto_id,),
    ).fetchone()
    quantidade = int(row["quantidade"] or 0)
    if quantidade <= 0:
        ultima = cursor.execute(
            """
            SELECT custo_unitario_centavos
            FROM estoque_movimentacoes
            WHERE produto_id = ? AND tipo IN ('compra', 'saldo_inicial')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (produto_id,),
        ).fetchone()
        return int(ultima[0]) if ultima else 0
    return max(int(Decimal(row["valor"] / quantidade).quantize(Decimal("1"))), 0)


def _inicio_dia_operacional(agora_utc: datetime | None = None) -> datetime:
    local = (agora_utc or datetime.now(timezone.utc)).astimezone(TIMEZONE_LOCAL)
    inicio = local.replace(hour=5, minute=0, second=0, microsecond=0)
    if local < inicio:
        inicio -= timedelta(days=1)
    return inicio.astimezone(timezone.utc)


def _item_para_api(row: sqlite3.Row) -> dict:
    customizacao = json.loads(row["customizacao_json"]) if row["customizacao_json"] else None
    return {
        "id": row["produto_id"],
        "nome": row["nome_produto"],
        "preco": _para_reais(row["preco_unitario_centavos"]),
        "custo_unitario": _para_reais(row["custo_unitario_centavos"]),
        "quantidade": row["quantidade"],
        "customizacao": customizacao,
        "requer_preparo": row["requer_preparo"],
        "timestamp_inicio_item": row["timestamp_inicio_item"],
        "categoria_ordem": row["categoria_ordem"],
        "produto_ordem": row["produto_ordem"],
        "uid": row["uid"],
    }


def _carregar_itens(cursor: sqlite3.Cursor, pedido_id: int) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT *
        FROM pedido_itens
        WHERE pedido_id = ?
        ORDER BY categoria_ordem, produto_ordem, produto_id, id
        """,
        (pedido_id,),
    ).fetchall()
    return [_item_para_api(row) for row in rows]


def _pedido_para_api(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    itens = _carregar_itens(cursor, row["id"])
    return {
        "id": row["id"],
        "nome_cliente": row["nome_cliente"],
        "status": row["status"],
        "metodo_pagamento": row["metodo_pagamento"],
        "modalidade": row["modalidade"],
        "valor_total": _para_reais(row["valor_total_centavos"]),
        "timestamp_criacao": row["timestamp_criacao"],
        "timestamp_pagamento": row["timestamp_pagamento"],
        "timestamp_finalizacao": row["timestamp_finalizacao"],
        "timestamp_cancelamento": row["timestamp_cancelamento"],
        "senha_diaria": row["senha_diaria"],
        "fluxo_simples": row["fluxo_simples"],
        "local_id": row["local_id"],
        "itens": itens,
        "itens_json": json.dumps(itens, ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# Categorias, produtos e estoque
# ---------------------------------------------------------------------------


def adicionar_nova_categoria(nome_categoria):
    nome = (nome_categoria or "").strip()
    if not nome:
        return False
    try:
        with _conexao() as conn:
            conn.execute("INSERT INTO categorias(nome) VALUES (?)", (nome,))
        return True
    except sqlite3.IntegrityError:
        return False


def obter_todas_categorias():
    with _conexao() as conn:
        return [
            {"id": row["id"], "nome": row["nome"]}
            for row in conn.execute("SELECT id, nome FROM categorias ORDER BY ordem, nome")
        ]


def excluir_categoria(id_categoria):
    try:
        with _conexao() as conn:
            cursor = conn.execute("DELETE FROM categorias WHERE id = ?", (id_categoria,))
        return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def adicionar_novo_produto(
    nome,
    descricao,
    foto_url,
    preco_venda,
    estoque_inicial,
    custo_inicial,
    categoria_id,
    requer_preparo,
):
    try:
        nome = (nome or "").strip()
        if not nome:
            return False
        quantidade = int(estoque_inicial or 0)
        if quantidade < 0:
            return False
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                INSERT INTO produtos(
                    nome, descricao, foto_url, preco_centavos, categoria_id,
                    requer_preparo, ativo
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    nome,
                    descricao,
                    foto_url,
                    _para_centavos(preco_venda),
                    categoria_id,
                    1 if requer_preparo else 0,
                ),
            )
            produto_id = cursor.lastrowid
            if quantidade > 0:
                cursor.execute(
                    """
                    INSERT INTO estoque_movimentacoes(
                        produto_id, tipo, quantidade, custo_unitario_centavos,
                        observacao, created_at
                    ) VALUES (?, 'saldo_inicial', ?, ?, ?, ?)
                    """,
                    (
                        produto_id,
                        quantidade,
                        _para_centavos(custo_inicial),
                        "Criação do produto",
                        _agora(),
                    ),
                )
        return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def _consulta_produtos_base(apenas_disponiveis: bool) -> tuple[str, list]:
    having = "HAVING (saldo - reservado) > 0" if apenas_disponiveis else ""
    return (
        f"""
        SELECT p.*, c.nome AS categoria_nome, c.ordem AS categoria_ordem,
               COALESCE(SUM(m.quantidade), 0) AS saldo,
               COALESCE((
                   SELECT SUM(r.quantidade_reservada)
                   FROM reservas_carrinho r
                   WHERE r.produto_id = p.id AND r.expires_at > ?
               ), 0) AS reservado,
               COALESCE(SUM(m.quantidade * m.custo_unitario_centavos), 0) AS valor_estoque
        FROM produtos p
        LEFT JOIN categorias c ON c.id = p.categoria_id
        LEFT JOIN estoque_movimentacoes m ON m.produto_id = p.id
        WHERE p.ativo = 1
        GROUP BY p.id
        {having}
        ORDER BY c.ordem, p.ordem, p.nome
        """,
        [_agora()],
    )


def obter_todos_produtos():
    with _conexao() as conn:
        query, params = _consulta_produtos_base(True)
        rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "nome": row["nome"],
                "descricao": row["descricao"],
                "foto_url": row["foto_url"],
                "preco_venda": _para_reais(row["preco_centavos"]),
                "estoque": int(row["saldo"] - row["reservado"]),
                "categoria": row["categoria_nome"],
                "categoria_id": row["categoria_id"],
                "requer_preparo": row["requer_preparo"],
                "categoria_ordem": row["categoria_ordem"] or 0,
                "produto_ordem": row["ordem"],
            }
            for row in rows
        ]


def obter_todos_produtos_para_gestao():
    with _conexao() as conn:
        query, params = _consulta_produtos_base(False)
        rows = conn.execute(query, params).fetchall()
        produtos = []
        for row in rows:
            saldo = int(row["saldo"])
            custo_centavos = (
                max(int(round(row["valor_estoque"] / saldo)), 0) if saldo > 0 else 0
            )
            ultima = conn.execute(
                """
                SELECT custo_unitario_centavos
                FROM estoque_movimentacoes
                WHERE produto_id = ? AND tipo IN ('compra', 'saldo_inicial')
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            ultimo_custo = int(ultima[0]) if ultima else custo_centavos
            preco = _para_reais(row["preco_centavos"])
            custo = _para_reais(custo_centavos)
            produtos.append(
                {
                    "id": row["id"],
                    "nome": row["nome"],
                    "descricao": row["descricao"],
                    "foto_url": row["foto_url"],
                    "preco_venda": preco,
                    "estoque": saldo,
                    "custo_medio": custo,
                    "lucro": round(preco - custo, 2),
                    "categoria": row["categoria_nome"],
                    "categoria_id": row["categoria_id"],
                    "ultimo_preco_compra": _para_reais(ultimo_custo),
                    "requer_preparo": row["requer_preparo"],
                }
            )
        return produtos


def excluir_produto(id_produto):
    """Produtos com histórico são arquivados, nunca removidos fisicamente."""
    with _conexao() as conn:
        cursor = conn.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (id_produto,))
    return cursor.rowcount > 0


def adicionar_estoque(id_produto, quantidade_adicionada, custo_unitario_movimentacao):
    try:
        quantidade = int(quantidade_adicionada)
        if quantidade == 0:
            return False
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            produto = cursor.execute(
                "SELECT ativo FROM produtos WHERE id = ?", (id_produto,)
            ).fetchone()
            if not produto or not produto["ativo"]:
                return False
            saldo = _saldo_produto(cursor, int(id_produto))
            if quantidade < 0 and saldo + quantidade < 0:
                return False
            if quantidade > 0:
                tipo = "compra"
                custo = _para_centavos(custo_unitario_movimentacao)
                observacao = "Entrada manual de estoque"
            else:
                tipo = "perda"
                custo = _custo_medio_centavos(cursor, int(id_produto))
                observacao = "Perda/ajuste manual de estoque"
            cursor.execute(
                """
                INSERT INTO estoque_movimentacoes(
                    produto_id, tipo, quantidade, custo_unitario_centavos,
                    observacao, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (id_produto, tipo, quantidade, custo, observacao, _agora()),
            )
        return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def atualizar_preco_venda_produto(id_produto, novo_preco_venda):
    try:
        with _conexao() as conn:
            cursor = conn.execute(
                "UPDATE produtos SET preco_centavos = ? WHERE id = ? AND ativo = 1",
                (_para_centavos(novo_preco_venda), id_produto),
            )
        return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def atualizar_dados_produto(
    id_produto, nome, descricao, foto_url, categoria_id, requer_preparo
):
    try:
        with _conexao() as conn:
            cursor = conn.execute(
                """
                UPDATE produtos
                SET nome = ?, descricao = ?, foto_url = ?, categoria_id = ?,
                    requer_preparo = ?
                WHERE id = ? AND ativo = 1
                """,
                (
                    (nome or "").strip(),
                    descricao,
                    foto_url,
                    categoria_id,
                    1 if requer_preparo else 0,
                    id_produto,
                ),
            )
        return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def atualizar_categoria_produto(id_produto, nova_categoria_id):
    try:
        with _conexao() as conn:
            cursor = conn.execute(
                "UPDATE produtos SET categoria_id = ? WHERE id = ? AND ativo = 1",
                (nova_categoria_id, id_produto),
            )
        return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def atualizar_ordem_itens(tabela, ids_ordenados):
    if tabela not in {"categorias", "produtos"}:
        return False
    try:
        with _conexao() as conn:
            for ordem, item_id in enumerate(ids_ordenados, 1):
                conn.execute(
                    f"UPDATE {tabela} SET ordem = ? WHERE id = ?", (ordem, item_id)
                )
        return True
    except sqlite3.Error:
        return False


def obter_historico_produto(id_produto):
    with _conexao() as conn:
        rows = conn.execute(
            """
            SELECT created_at, quantidade, custo_unitario_centavos, tipo
            FROM estoque_movimentacoes
            WHERE produto_id = ? AND tipo IN ('compra', 'saldo_inicial')
            ORDER BY created_at DESC, id DESC
            """,
            (id_produto,),
        ).fetchall()
    return [
        {
            "data": datetime.fromisoformat(row["created_at"])
            .astimezone(TIMEZONE_LOCAL)
            .strftime("%d/%m/%Y %H:%M"),
            "quantidade": row["quantidade"],
            "custo": _para_reais(row["custo_unitario_centavos"]),
            "tipo": row["tipo"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Pedidos, pagamentos e cancelamentos
# ---------------------------------------------------------------------------


def salvar_novo_pedido(dados_do_pedido, local_id):
    conn = None
    try:
        itens_recebidos = list((dados_do_pedido or {}).get("itens") or [])
        if not itens_recebidos or local_id is None:
            return None
        metodo = dados_do_pedido.get("metodo_pagamento")
        modalidade = dados_do_pedido.get("modalidade")
        if metodo not in METODOS_PAGAMENTO or modalidade not in MODALIDADES:
            return None
        nome_cliente = str(dados_do_pedido.get("nome_cliente") or "").strip()
        if not nome_cliente:
            return None

        quantidades = defaultdict(int)
        for item in itens_recebidos:
            produto_id = int(item["id"])
            quantidade = int(item["quantidade"])
            if quantidade <= 0:
                return None
            quantidades[produto_id] += quantidade

        conn = _conectar()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        _limpar_reservas(cursor)

        if not cursor.execute("SELECT 1 FROM locais WHERE id = ?", (local_id,)).fetchone():
            conn.rollback()
            return None

        placeholders = ",".join("?" for _ in quantidades)
        produtos_rows = cursor.execute(
            f"""
            SELECT p.*, COALESCE(c.ordem, 0) AS categoria_ordem,
                   COALESCE(c.nome, 'Sem categoria') AS categoria_nome
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE p.id IN ({placeholders}) AND p.ativo = 1
            """,
            list(quantidades),
        ).fetchall()
        produtos = {row["id"]: row for row in produtos_rows}
        if len(produtos) != len(quantidades):
            conn.rollback()
            return None

        carrinho_id = str(dados_do_pedido.get("carrinho_id") or "")
        custos = {}
        for produto_id, desejado in quantidades.items():
            saldo = _saldo_produto(cursor, produto_id)
            if carrinho_id:
                reservado_outros = cursor.execute(
                    """
                    SELECT COALESCE(SUM(quantidade_reservada), 0)
                    FROM reservas_carrinho
                    WHERE produto_id = ? AND carrinho_id != ?
                    """,
                    (produto_id, carrinho_id),
                ).fetchone()[0]
            else:
                reservado_outros = cursor.execute(
                    """
                    SELECT COALESCE(SUM(quantidade_reservada), 0)
                    FROM reservas_carrinho WHERE produto_id = ?
                    """,
                    (produto_id,),
                ).fetchone()[0]
            if saldo - int(reservado_outros or 0) < desejado:
                conn.rollback()
                return None
            custos[produto_id] = _custo_medio_centavos(cursor, produto_id)

        agora = _agora()
        inicio = _inicio_dia_operacional().isoformat()
        senha = int(
            cursor.execute(
                """
                SELECT COALESCE(MAX(senha_diaria), 0) + 1
                FROM pedidos
                WHERE timestamp_criacao >= ?
                """,
                (inicio,),
            ).fetchone()[0]
        )
        fluxo_simples = all(not produtos[pid]["requer_preparo"] for pid in quantidades)
        total_centavos = sum(
            produtos[pid]["preco_centavos"] * quantidade
            for pid, quantidade in quantidades.items()
        )
        cursor.execute(
            """
            INSERT INTO pedidos(
                nome_cliente, status, metodo_pagamento, modalidade,
                valor_total_centavos, timestamp_criacao, senha_diaria,
                fluxo_simples, local_id
            ) VALUES (?, 'aguardando_pagamento', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nome_cliente,
                metodo,
                modalidade,
                total_centavos,
                agora,
                senha,
                1 if fluxo_simples else 0,
                int(local_id),
            ),
        )
        pedido_id = cursor.lastrowid

        itens_ordenados = sorted(
            itens_recebidos,
            key=lambda item: (
                produtos[int(item["id"])]["categoria_ordem"],
                produtos[int(item["id"])]["ordem"],
                int(item["id"]),
                str(item.get("uid") or ""),
            ),
        )
        for item in itens_ordenados:
            pid = int(item["id"])
            produto = produtos[pid]
            customizacao = item.get("customizacao")
            cursor.execute(
                """
                INSERT INTO pedido_itens(
                    pedido_id, produto_id, nome_produto,
                    preco_unitario_centavos, custo_unitario_centavos,
                    quantidade, categoria_nome, customizacao_json, requer_preparo,
                    categoria_ordem, produto_ordem, uid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pedido_id,
                    pid,
                    produto["nome"],
                    produto["preco_centavos"],
                    custos[pid],
                    int(item["quantidade"]),
                    produto["categoria_nome"],
                    json.dumps(customizacao, ensure_ascii=False)
                    if customizacao is not None
                    else None,
                    produto["requer_preparo"],
                    produto["categoria_ordem"],
                    produto["ordem"],
                    str(item.get("uid") or uuid.uuid4()),
                ),
            )

        for pid, quantidade in quantidades.items():
            cursor.execute(
                """
                INSERT INTO estoque_movimentacoes(
                    produto_id, pedido_id, tipo, quantidade,
                    custo_unitario_centavos, observacao, created_at
                ) VALUES (?, ?, 'venda', ?, ?, ?, ?)
                """,
                (
                    pid,
                    pedido_id,
                    -quantidade,
                    custos[pid],
                    f"Reserva convertida no pedido #{pedido_id}",
                    agora,
                ),
            )
        if carrinho_id:
            cursor.execute(
                "DELETE FROM reservas_carrinho WHERE carrinho_id = ?", (carrinho_id,)
            )
        conn.commit()
        return {"id": pedido_id, "senha": senha}
    except (KeyError, ValueError, TypeError, sqlite3.Error):
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def confirmar_pagamento_pedido(id_do_pedido):
    conn = None
    try:
        conn = _conectar()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        pedido = cursor.execute(
            """
            SELECT * FROM pedidos
            WHERE id = ? AND status = 'aguardando_pagamento'
            """,
            (id_do_pedido,),
        ).fetchone()
        if not pedido:
            conn.rollback()
            return False
        chave_taxa = {
            "cartao_credito": "taxa_credito",
            "cartao_debito": "taxa_debito",
            "pix": "taxa_pix",
            "dinheiro": None,
        }[pedido["metodo_pagamento"]]
        taxa_percentual = 0.0
        if chave_taxa:
            row = cursor.execute(
                "SELECT valor FROM configuracoes WHERE chave = ?", (chave_taxa,)
            ).fetchone()
            taxa_percentual = float(row[0]) if row else 0.0
        taxa_centavos = int(
            (
                Decimal(pedido["valor_total_centavos"])
                * Decimal(str(taxa_percentual))
                / Decimal("100")
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        agora = _agora()
        cursor.execute(
            """
            INSERT INTO pagamentos(
                pedido_id, tipo, metodo, valor_centavos, taxa_centavos, ocorrido_em
            ) VALUES (?, 'pagamento', ?, ?, ?, ?)
            """,
            (
                id_do_pedido,
                pedido["metodo_pagamento"],
                pedido["valor_total_centavos"],
                taxa_centavos,
                agora,
            ),
        )
        cursor.execute(
            """
            UPDATE pedidos
            SET status = 'aguardando_producao', timestamp_pagamento = ?
            WHERE id = ?
            """,
            (agora, id_do_pedido),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def iniciar_preparo_pedido(id_do_pedido):
    try:
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            alterado = cursor.execute(
                """
                UPDATE pedidos SET status = 'em_producao'
                WHERE id = ? AND status = 'aguardando_producao'
                """,
                (id_do_pedido,),
            )
            if alterado.rowcount == 0:
                return False
            cursor.execute(
                """
                UPDATE pedido_itens SET timestamp_inicio_item = ?
                WHERE pedido_id = ? AND requer_preparo = 1
                """,
                (_agora(), id_do_pedido),
            )
        return True
    except sqlite3.Error:
        return False


def reiniciar_preparo_item(pedido_id, produto_id, k_posicao):
    try:
        with _conexao() as conn:
            itens = conn.execute(
                """
                SELECT id FROM pedido_itens
                WHERE pedido_id = ? AND produto_id = ? AND requer_preparo = 1
                ORDER BY id
                """,
                (pedido_id, produto_id),
            ).fetchall()
            if not 1 <= int(k_posicao) <= len(itens):
                return False
            conn.execute(
                "UPDATE pedido_itens SET timestamp_inicio_item = ? WHERE id = ?",
                (_agora(), itens[int(k_posicao) - 1]["id"]),
            )
        return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def pular_pedido_para_retirada(id_do_pedido):
    with _conexao() as conn:
        cursor = conn.execute(
            """
            UPDATE pedidos SET status = 'aguardando_retirada'
            WHERE id = ? AND status = 'aguardando_producao' AND fluxo_simples = 1
            """,
            (id_do_pedido,),
        )
    return cursor.rowcount > 0


def chamar_cliente_pedido(id_do_pedido):
    with _conexao() as conn:
        cursor = conn.execute(
            """
            UPDATE pedidos SET status = 'aguardando_retirada'
            WHERE id = ? AND status = 'em_producao'
            """,
            (id_do_pedido,),
        )
    return cursor.rowcount > 0


def entregar_pedido(id_do_pedido):
    with _conexao() as conn:
        cursor = conn.execute(
            """
            UPDATE pedidos
            SET status = 'finalizado', timestamp_finalizacao = ?
            WHERE id = ? AND status = 'aguardando_retirada'
            """,
            (_agora(), id_do_pedido),
        )
    return cursor.rowcount > 0


def cancelar_pedido(id_do_pedido):
    conn = None
    try:
        conn = _conectar()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        pedido = cursor.execute(
            "SELECT * FROM pedidos WHERE id = ?", (id_do_pedido,)
        ).fetchone()
        if not pedido:
            conn.rollback()
            return False
        if pedido["status"] == "cancelado":
            conn.rollback()
            return True
        agora = _agora()
        vendas = cursor.execute(
            """
            SELECT produto_id, quantidade, custo_unitario_centavos
            FROM estoque_movimentacoes
            WHERE pedido_id = ? AND tipo = 'venda'
            """,
            (id_do_pedido,),
        ).fetchall()
        for venda in vendas:
            cursor.execute(
                """
                INSERT OR IGNORE INTO estoque_movimentacoes(
                    produto_id, pedido_id, tipo, quantidade,
                    custo_unitario_centavos, observacao, created_at
                ) VALUES (?, ?, 'estorno', ?, ?, ?, ?)
                """,
                (
                    venda["produto_id"],
                    id_do_pedido,
                    abs(venda["quantidade"]),
                    venda["custo_unitario_centavos"],
                    f"Estorno integral do pedido #{id_do_pedido}",
                    agora,
                ),
            )
        pagamento = cursor.execute(
            """
            SELECT * FROM pagamentos
            WHERE pedido_id = ? AND tipo = 'pagamento'
            """,
            (id_do_pedido,),
        ).fetchone()
        if pagamento:
            cursor.execute(
                """
                INSERT OR IGNORE INTO pagamentos(
                    pedido_id, tipo, metodo, valor_centavos,
                    taxa_centavos, ocorrido_em
                ) VALUES (?, 'estorno', ?, ?, ?, ?)
                """,
                (
                    id_do_pedido,
                    pagamento["metodo"],
                    pagamento["valor_centavos"],
                    pagamento["taxa_centavos"],
                    agora,
                ),
            )
        cursor.execute(
            """
            UPDATE pedidos
            SET status = 'cancelado', timestamp_cancelamento = ?
            WHERE id = ?
            """,
            (agora, id_do_pedido),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def obter_pedidos_ativos():
    status = (
        "aguardando_pagamento",
        "aguardando_producao",
        "em_producao",
        "aguardando_retirada",
    )
    with _conexao() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in status)
        rows = cursor.execute(
            f"""
            SELECT * FROM pedidos
            WHERE status IN ({placeholders})
            ORDER BY CASE status
                       WHEN 'aguardando_pagamento' THEN 1
                       WHEN 'aguardando_producao' THEN 2
                       WHEN 'aguardando_retirada' THEN 3
                       WHEN 'em_producao' THEN 4
                     END,
                     COALESCE(timestamp_pagamento, timestamp_criacao)
            """,
            status,
        ).fetchall()
        return [_pedido_para_api(cursor, row) for row in rows]


def obter_pedido_por_id(id_do_pedido):
    with _conexao() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM pedidos WHERE id = ?", (id_do_pedido,)).fetchone()
        return _pedido_para_api(cursor, row) if row else None


def obter_produtos_de_pedido(id_do_pedido):
    with _conexao() as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT produto_id FROM pedido_itens WHERE pedido_id = ?",
                (id_do_pedido,),
            )
        ]


def obter_proximo_id_pedido():
    with _conexao() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM pedidos").fetchone()
        return int(row[0])


def obter_proxima_senha_diaria():
    with _conexao() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(senha_diaria), 0) + 1
            FROM pedidos WHERE timestamp_criacao >= ?
            """,
            (_inicio_dia_operacional().isoformat(),),
        ).fetchone()
        return int(row[0])


# ---------------------------------------------------------------------------
# Reservas globais
# ---------------------------------------------------------------------------


def obter_disponibilidade_para_produtos(produto_ids):
    ids = [int(pid) for pid in produto_ids]
    if not ids:
        return {}
    with _conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        _limpar_reservas(cursor)
        placeholders = ",".join("?" for _ in ids)
        saldos = {
            row["produto_id"]: int(row["saldo"])
            for row in cursor.execute(
                f"""
                SELECT produto_id, COALESCE(SUM(quantidade), 0) AS saldo
                FROM estoque_movimentacoes
                WHERE produto_id IN ({placeholders})
                GROUP BY produto_id
                """,
                ids,
            )
        }
        reservas = {
            row["produto_id"]: int(row["reservado"])
            for row in cursor.execute(
                f"""
                SELECT produto_id, COALESCE(SUM(quantidade_reservada), 0) AS reservado
                FROM reservas_carrinho
                WHERE produto_id IN ({placeholders})
                GROUP BY produto_id
                """,
                ids,
            )
        }
        resultado = {pid: saldos.get(pid, 0) - reservas.get(pid, 0) for pid in ids}
        conn.commit()
        return resultado


def gerenciar_reserva(carrinho_id, produto_id, quantidade_delta):
    conn = None
    try:
        carrinho_id = str(carrinho_id or "").strip()
        produto_id = int(produto_id)
        delta = int(quantidade_delta)
        if not carrinho_id or delta == 0:
            return {"sucesso": False, "mensagem": "Dados de reserva inválidos."}
        conn = _conectar()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        _limpar_reservas(cursor)
        produto = cursor.execute(
            "SELECT ativo FROM produtos WHERE id = ?", (produto_id,)
        ).fetchone()
        if not produto or not produto["ativo"]:
            conn.rollback()
            return {"sucesso": False, "mensagem": "Produto indisponível."}
        atual_row = cursor.execute(
            """
            SELECT quantidade_reservada FROM reservas_carrinho
            WHERE carrinho_id = ? AND produto_id = ?
            """,
            (carrinho_id, produto_id),
        ).fetchone()
        atual = int(atual_row[0]) if atual_row else 0
        nova = atual + delta
        if nova < 0:
            conn.rollback()
            return {"sucesso": False, "mensagem": "Quantidade de reserva inválida."}
        saldo = _saldo_produto(cursor, produto_id)
        outros = int(
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantidade_reservada), 0)
                FROM reservas_carrinho
                WHERE produto_id = ? AND carrinho_id != ?
                """,
                (produto_id, carrinho_id),
            ).fetchone()[0]
        )
        if saldo - outros < nova:
            conn.rollback()
            return {
                "sucesso": False,
                "mensagem": "Não há mais unidades deste item no momento.",
                "produtos_afetados": [
                    {"produto_id": produto_id, "disponivel": max(saldo - outros - atual, 0)}
                ],
            }
        if nova == 0:
            cursor.execute(
                """
                DELETE FROM reservas_carrinho
                WHERE carrinho_id = ? AND produto_id = ?
                """,
                (carrinho_id, produto_id),
            )
        else:
            agora = datetime.now(timezone.utc)
            cursor.execute(
                """
                INSERT INTO reservas_carrinho(
                    carrinho_id, produto_id, quantidade_reservada,
                    expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(carrinho_id, produto_id) DO UPDATE SET
                    quantidade_reservada = excluded.quantidade_reservada,
                    expires_at = excluded.expires_at
                """,
                (
                    carrinho_id,
                    produto_id,
                    nova,
                    (agora + timedelta(seconds=120)).isoformat(),
                    agora.isoformat(),
                ),
            )
        reservado_total = int(
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantidade_reservada), 0)
                FROM reservas_carrinho WHERE produto_id = ?
                """,
                (produto_id,),
            ).fetchone()[0]
        )
        conn.commit()
        return {
            "sucesso": True,
            "produtos_afetados": [
                {"produto_id": produto_id, "disponivel": saldo - reservado_total}
            ],
        }
    except (sqlite3.Error, ValueError, TypeError):
        if conn:
            conn.rollback()
        return {"sucesso": False, "mensagem": "Erro no servidor."}
    finally:
        if conn:
            conn.close()


def renovar_reservas_carrinho(carrinho_id):
    try:
        with _conexao() as conn:
            conn.execute(
                """
                UPDATE reservas_carrinho SET expires_at = ?
                WHERE carrinho_id = ?
                """,
                (
                    (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat(),
                    carrinho_id,
                ),
            )
        return {"sucesso": True}
    except sqlite3.Error:
        return {"sucesso": False}


def forcar_expirar_carrinho(carrinho_id):
    try:
        with _conexao() as conn:
            ids = [
                row[0]
                for row in conn.execute(
                    "SELECT produto_id FROM reservas_carrinho WHERE carrinho_id = ?",
                    (carrinho_id,),
                )
            ]
            conn.execute(
                "DELETE FROM reservas_carrinho WHERE carrinho_id = ?", (carrinho_id,)
            )
        disponibilidades = obter_disponibilidade_para_produtos(ids)
        return {
            "sucesso": True,
            "produtos_afetados": [
                {"produto_id": pid, "disponivel": disponibilidades.get(pid, 0)}
                for pid in ids
            ],
        }
    except sqlite3.Error:
        return {"sucesso": False, "mensagem": "Erro ao expirar carrinho."}


# ---------------------------------------------------------------------------
# Configurações auxiliares
# ---------------------------------------------------------------------------


def obter_tempos_por_produto_id(produto_id):
    tempos = {"mal": 0, "ponto": 0, "bem": 0}
    with _conexao() as conn:
        for row in conn.execute(
            "SELECT ponto, tempo_em_segundos FROM tempos_preparo WHERE produto_id = ?",
            (produto_id,),
        ):
            tempos[row["ponto"]] = row["tempo_em_segundos"] / 60
    return tempos


def salvar_tempos_preparo(produto_id, tempos_data):
    try:
        with _conexao() as conn:
            for ponto in ("mal", "ponto", "bem"):
                minutos = float(tempos_data.get(ponto, 0) or 0)
                segundos = max(int(round(minutos * 60)), 0)
                if segundos:
                    conn.execute(
                        """
                        INSERT INTO tempos_preparo(produto_id, ponto, tempo_em_segundos)
                        VALUES (?, ?, ?)
                        ON CONFLICT(produto_id, ponto) DO UPDATE SET
                            tempo_em_segundos = excluded.tempo_em_segundos
                        """,
                        (produto_id, ponto, segundos),
                    )
                else:
                    conn.execute(
                        "DELETE FROM tempos_preparo WHERE produto_id = ? AND ponto = ?",
                        (produto_id, ponto),
                    )
        return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def obter_tempo_preparo_especifico(produto_id, ponto):
    with _conexao() as conn:
        row = conn.execute(
            """
            SELECT tempo_em_segundos FROM tempos_preparo
            WHERE produto_id = ? AND ponto = ?
            """,
            (produto_id, ponto),
        ).fetchone()
        return int(row[0]) if row else 0


def adicionar_acompanhamento(nome):
    nome = (nome or "").strip()
    if not nome:
        return False
    try:
        with _conexao() as conn:
            conn.execute("INSERT INTO acompanhamentos(nome) VALUES (?)", (nome,))
        return True
    except sqlite3.Error:
        return False


def obter_todos_acompanhamentos():
    with _conexao() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id, nome, is_visivel FROM acompanhamentos ORDER BY nome"
            )
        ]


def obter_acompanhamentos_visiveis():
    with _conexao() as conn:
        return [
            {"id": row["id"], "nome": row["nome"]}
            for row in conn.execute(
                """
                SELECT id, nome FROM acompanhamentos
                WHERE is_visivel = 1 ORDER BY nome
                """
            )
        ]


def excluir_acompanhamento(id_acompanhamento):
    with _conexao() as conn:
        cursor = conn.execute(
            "DELETE FROM acompanhamentos WHERE id = ?", (id_acompanhamento,)
        )
    return cursor.rowcount > 0


def toggle_visibilidade_acompanhamento(id_acompanhamento):
    with _conexao() as conn:
        cursor = conn.execute(
            """
            UPDATE acompanhamentos
            SET is_visivel = CASE is_visivel WHEN 1 THEN 0 ELSE 1 END
            WHERE id = ?
            """,
            (id_acompanhamento,),
        )
    return cursor.rowcount > 0


def obter_configuracoes():
    with _conexao() as conn:
        return {
            row["chave"]: float(row["valor"])
            for row in conn.execute("SELECT chave, valor FROM configuracoes")
        }


def salvar_configuracoes(novas_taxas):
    permitidas = {"taxa_credito", "taxa_debito", "taxa_pix"}
    try:
        valores = {}
        for chave, valor in novas_taxas.items():
            if chave in permitidas:
                numero = float(valor)
                if numero < 0:
                    return False
                valores[chave] = numero
        with _conexao() as conn:
            for chave, numero in valores.items():
                conn.execute(
                    """
                    INSERT INTO configuracoes(chave, valor) VALUES (?, ?)
                    ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
                    """,
                    (chave, numero),
                )
        return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def adicionar_local(nome_local):
    nome = (nome_local or "").strip()
    if not nome:
        return False
    try:
        with _conexao() as conn:
            conn.execute("INSERT INTO locais(nome) VALUES (?)", (nome,))
        return True
    except sqlite3.Error:
        return False


def obter_todos_locais():
    with _conexao() as conn:
        return [dict(row) for row in conn.execute("SELECT id, nome FROM locais ORDER BY nome")]


def excluir_local(id_local):
    try:
        with _conexao() as conn:
            cursor = conn.execute("DELETE FROM locais WHERE id = ?", (id_local,))
        return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def obter_dados_para_menu_data_js():
    with _conexao() as conn:
        rows = conn.execute(
            """
            SELECT p.*, c.nome AS categoria_nome,
                   COALESCE(c.ordem, 0) AS categoria_ordem
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE p.ativo = 1
            ORDER BY c.ordem, p.ordem, p.nome
            """
        ).fetchall()
        return {
            row["id"]: {
                "id": row["id"],
                "nome": row["nome"],
                "preco_venda": _para_reais(row["preco_centavos"]),
                "descricao": row["descricao"],
                "foto_url": row["foto_url"],
                "requer_preparo": row["requer_preparo"],
                "categoria_id": row["categoria_id"],
                "categoria_nome": row["categoria_nome"],
                "categoria_ordem": row["categoria_ordem"],
                "produto_ordem": row["ordem"],
            }
            for row in rows
        }


def obter_dados_para_relatorio_fechamento(data_str):
    import analytics

    return analytics.relatorio_impressao(data_str)
