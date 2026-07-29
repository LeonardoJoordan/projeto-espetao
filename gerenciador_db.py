"""Operações transacionais do PDV sobre o esquema canônico v3 com FIFO."""

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


def _custo_medio_centavos(cursor: sqlite3.Cursor, produto_id: int) -> int:
    row = cursor.execute(
        """
        SELECT COALESCE(SUM(disponivel), 0) AS quantidade,
               COALESCE(SUM(disponivel * custo_unitario_centavos), 0) AS valor
        FROM (
            SELECT l.custo_unitario_centavos,
                   l.quantidade_inicial + COALESCE((
                       SELECT SUM(m.quantidade)
                       FROM estoque_movimentacoes m
                       WHERE m.lote_id = l.id
                   ), 0) AS disponivel
            FROM estoque_lotes l
            WHERE l.produto_id = ?
        )
        """,
        (produto_id,),
    ).fetchone()
    quantidade = int(row["quantidade"] or 0)
    if quantidade <= 0:
        ultima = cursor.execute(
            """
            SELECT custo_unitario_centavos
            FROM estoque_lotes
            WHERE produto_id = ?
            ORDER BY recebido_em DESC, id DESC
            LIMIT 1
            """,
            (produto_id,),
        ).fetchone()
        return int(ultima[0]) if ultima else 0
    return max(int(Decimal(row["valor"] / quantidade).quantize(Decimal("1"))), 0)


def _criar_lote(
    cursor: sqlite3.Cursor,
    produto_id: int,
    quantidade: int,
    custo_unitario_centavos: int,
    *,
    tipo: str,
    observacao: str,
    recebido_em: str | None = None,
) -> int:
    if quantidade <= 0 or custo_unitario_centavos < 0:
        raise ValueError("Dados do lote inválidos")
    cursor.execute(
        """
        INSERT INTO estoque_lotes(
            produto_id, quantidade_inicial, custo_unitario_centavos,
            tipo, observacao, recebido_em
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            produto_id,
            quantidade,
            custo_unitario_centavos,
            tipo,
            observacao,
            recebido_em or _agora(),
        ),
    )
    return int(cursor.lastrowid)


def _lotes_fifo_disponiveis(
    cursor: sqlite3.Cursor,
    produto_id: int,
) -> list[sqlite3.Row]:
    return cursor.execute(
        """
        SELECT *
        FROM (
            SELECT l.*,
                   l.quantidade_inicial + COALESCE((
                       SELECT SUM(m.quantidade)
                       FROM estoque_movimentacoes m
                       WHERE m.lote_id = l.id
                   ), 0) AS disponivel
            FROM estoque_lotes l
            WHERE l.produto_id = ?
        )
        WHERE disponivel > 0
        ORDER BY recebido_em, id
        """,
        (produto_id,),
    ).fetchall()


def _consumir_fifo(
    cursor: sqlite3.Cursor,
    produto_id: int,
    quantidade: int,
    *,
    tipo: str,
    observacao: str,
    pedido_id: int | None = None,
    pedido_item_id: int | None = None,
    ocorrido_em: str | None = None,
    impacta_relatorio: bool = True,
) -> dict:
    """Consome lotes em PEPS e fotografa cada parcela do custo."""
    quantidade = int(quantidade)
    if quantidade <= 0 or tipo not in {"venda", "perda", "ajuste"}:
        raise ValueError("Saída FIFO inválida")
    restante = quantidade
    custo_total = 0
    movimentos = []
    agora = ocorrido_em or _agora()

    for lote in _lotes_fifo_disponiveis(cursor, produto_id):
        if restante <= 0:
            break
        retirada = min(restante, int(lote["disponivel"]))
        custo = int(lote["custo_unitario_centavos"])
        cursor.execute(
            """
            INSERT INTO estoque_movimentacoes(
                produto_id, pedido_id, pedido_item_id, lote_id,
                tipo, quantidade, custo_unitario_centavos,
                impacta_relatorio, observacao, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                produto_id,
                pedido_id,
                pedido_item_id,
                lote["id"],
                tipo,
                -retirada,
                custo,
                1 if impacta_relatorio else 0,
                observacao,
                agora,
            ),
        )
        movimentos.append(int(cursor.lastrowid))
        custo_total += retirada * custo
        restante -= retirada

    if restante:
        raise ValueError("Estoque insuficiente para a saída FIFO")
    return {
        "quantidade": quantidade,
        "custo_total_centavos": custo_total,
        "movimentos": movimentos,
    }


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
        "custo_total": _para_reais(row["custo_total_centavos"]),
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
    ocultar_quando_esgotado=0,
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
                    requer_preparo, ocultar_quando_esgotado, ativo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    nome,
                    descricao,
                    foto_url,
                    _para_centavos(preco_venda),
                    categoria_id,
                    1 if requer_preparo else 0,
                    1 if ocultar_quando_esgotado else 0,
                ),
            )
            produto_id = cursor.lastrowid
            if quantidade > 0:
                _criar_lote(
                    cursor,
                    int(produto_id),
                    quantidade,
                    _para_centavos(custo_inicial),
                    tipo="saldo_inicial",
                    observacao="Estoque inicial na criação do produto",
                )
        return int(produto_id)
    except (sqlite3.Error, ValueError, TypeError):
        return False


def _consulta_produtos_base(apenas_disponiveis: bool) -> tuple[str, list]:
    filtro = "WHERE (saldo - reservado) > 0" if apenas_disponiveis else ""
    return (
        f"""
        SELECT *
        FROM (
            SELECT p.*, c.nome AS categoria_nome, c.ordem AS categoria_ordem,
                   COALESCE((
                       SELECT SUM(
                           l.quantidade_inicial + COALESCE((
                               SELECT SUM(m.quantidade)
                               FROM estoque_movimentacoes m
                               WHERE m.lote_id = l.id
                           ), 0)
                       )
                       FROM estoque_lotes l
                       WHERE l.produto_id = p.id
                   ), 0) AS saldo,
                   COALESCE((
                       SELECT SUM(r.quantidade_reservada)
                       FROM reservas_carrinho r
                       WHERE r.produto_id = p.id AND r.expires_at > ?
                   ), 0) AS reservado,
                   COALESCE((
                       SELECT SUM(
                           (
                               l.quantidade_inicial + COALESCE((
                                   SELECT SUM(m.quantidade)
                                   FROM estoque_movimentacoes m
                                   WHERE m.lote_id = l.id
                               ), 0)
                           ) * l.custo_unitario_centavos
                       )
                       FROM estoque_lotes l
                       WHERE l.produto_id = p.id
                   ), 0) AS valor_estoque,
                   (
                       SELECT l.custo_unitario_centavos
                       FROM estoque_lotes l
                       WHERE l.produto_id = p.id
                         AND (
                             l.quantidade_inicial + COALESCE((
                                 SELECT SUM(m.quantidade)
                                 FROM estoque_movimentacoes m
                                 WHERE m.lote_id = l.id
                             ), 0)
                         ) > 0
                       ORDER BY l.recebido_em, l.id
                       LIMIT 1
                   ) AS proximo_custo,
                   (
                       SELECT COUNT(*)
                       FROM estoque_lotes l
                       WHERE l.produto_id = p.id
                         AND (
                             l.quantidade_inicial + COALESCE((
                                 SELECT SUM(m.quantidade)
                                 FROM estoque_movimentacoes m
                                 WHERE m.lote_id = l.id
                             ), 0)
                         ) > 0
                   ) AS lotes_ativos
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE p.ativo = 1
        )
        {filtro}
        ORDER BY categoria_ordem, ordem, nome
        """,
        [_agora()],
    )


def obter_todos_produtos():
    with _conexao() as conn:
        # O cardápio mantém os itens esgotados renderizados para que uma unidade
        # liberada por outro carrinho reapareça em tempo real, sem recarregar.
        query, params = _consulta_produtos_base(False)
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
                "ocultar_quando_esgotado": row["ocultar_quando_esgotado"],
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
                FROM estoque_lotes
                WHERE produto_id = ?
                ORDER BY recebido_em DESC, id DESC LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            ultimo_custo = int(ultima[0]) if ultima else custo_centavos
            preco = _para_reais(row["preco_centavos"])
            custo = _para_reais(custo_centavos)
            proximo_custo = _para_reais(row["proximo_custo"] or 0)
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
                    "valor_estoque": _para_reais(row["valor_estoque"]),
                    "custo_proxima_unidade": proximo_custo,
                    "lucro_proxima_unidade": round(preco - proximo_custo, 2),
                    "lotes_ativos": int(row["lotes_ativos"] or 0),
                    "categoria": row["categoria_nome"],
                    "categoria_id": row["categoria_id"],
                    "ultimo_preco_compra": _para_reais(ultimo_custo),
                    "requer_preparo": row["requer_preparo"],
                    "ocultar_quando_esgotado": row["ocultar_quando_esgotado"],
                }
            )
        return produtos


def obter_produto_para_gestao(id_produto):
    return next(
        (
            produto
            for produto in obter_todos_produtos_para_gestao()
            if produto["id"] == int(id_produto)
        ),
        None,
    )


def excluir_produto(id_produto):
    """Produtos com histórico são arquivados, nunca removidos fisicamente."""
    with _conexao() as conn:
        cursor = conn.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (id_produto,))
    return cursor.rowcount > 0


def adicionar_estoque(id_produto, quantidade_adicionada, custo_unitario_movimentacao):
    """Compatibilidade: entrada positiva cria lote; negativa registra perda FIFO."""
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
                _criar_lote(
                    cursor,
                    int(id_produto),
                    quantidade,
                    _para_centavos(custo_unitario_movimentacao),
                    tipo="compra",
                    observacao="Entrada manual de estoque",
                )
            else:
                _consumir_fifo(
                    cursor,
                    int(id_produto),
                    abs(quantidade),
                    tipo="perda",
                    observacao="Perda manual de estoque",
                )
        return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def registrar_entrada_estoque(
    id_produto,
    quantidade,
    custo_unitario,
    observacao=None,
):
    try:
        quantidade = int(quantidade)
        custo_centavos = _para_centavos(custo_unitario)
        if quantidade <= 0 or custo_centavos < 0:
            return {"sucesso": False, "mensagem": "Entrada de estoque inválida."}
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            produto = cursor.execute(
                "SELECT ativo FROM produtos WHERE id = ?", (int(id_produto),)
            ).fetchone()
            if not produto or not produto["ativo"]:
                return {"sucesso": False, "mensagem": "Produto não encontrado."}
            lote_id = _criar_lote(
                cursor,
                int(id_produto),
                quantidade,
                custo_centavos,
                tipo="compra",
                observacao=(observacao or "").strip() or "Entrada de estoque",
            )
            saldo = _saldo_produto(cursor, int(id_produto))
        return {
            "sucesso": True,
            "lote_id": lote_id,
            "saldo": saldo,
        }
    except (sqlite3.Error, ValueError, TypeError):
        return {"sucesso": False, "mensagem": "Não foi possível registrar a entrada."}


def registrar_perda_estoque(id_produto, quantidade, motivo=None):
    try:
        quantidade = int(quantidade)
        if quantidade <= 0:
            return {"sucesso": False, "mensagem": "Informe uma quantidade válida."}
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            if _saldo_produto(cursor, int(id_produto)) < quantidade:
                return {
                    "sucesso": False,
                    "mensagem": "A perda não pode superar o estoque disponível.",
                }
            consumo = _consumir_fifo(
                cursor,
                int(id_produto),
                quantidade,
                tipo="perda",
                observacao=(motivo or "").strip() or "Perda de estoque",
            )
            saldo = _saldo_produto(cursor, int(id_produto))
        return {
            "sucesso": True,
            "saldo": saldo,
            "custo_total": _para_reais(consumo["custo_total_centavos"]),
        }
    except (sqlite3.Error, ValueError, TypeError):
        return {"sucesso": False, "mensagem": "Não foi possível registrar a perda."}


def zerar_estoque_produto(id_produto):
    """Encerra o saldo FIFO como ajuste operacional neutro e libera reservas."""
    try:
        produto_id = int(id_produto)
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            produto = cursor.execute(
                "SELECT id, nome FROM produtos WHERE id = ? AND ativo = 1",
                (produto_id,),
            ).fetchone()
            if not produto:
                return {"sucesso": False, "mensagem": "Produto não encontrado."}

            _limpar_reservas(cursor)
            reservas_liberadas = cursor.execute(
                "DELETE FROM reservas_carrinho WHERE produto_id = ?",
                (produto_id,),
            ).rowcount
            quantidade = _saldo_produto(cursor, produto_id)
            custo_total_centavos = 0
            if quantidade > 0:
                consumo = _consumir_fifo(
                    cursor,
                    produto_id,
                    quantidade,
                    tipo="ajuste",
                    observacao="Zeragem operacional do estoque",
                    impacta_relatorio=False,
                )
                custo_total_centavos = consumo["custo_total_centavos"]

        return {
            "sucesso": True,
            "produto_id": produto_id,
            "produto_nome": produto["nome"],
            "quantidade_zerada": quantidade,
            "valor_zerado": _para_reais(custo_total_centavos),
            "reservas_liberadas": reservas_liberadas,
            "saldo": 0,
            "produtos_afetados": [{"produto_id": produto_id, "disponivel": 0}],
        }
    except (sqlite3.Error, ValueError, TypeError):
        return {
            "sucesso": False,
            "mensagem": "Não foi possível zerar o estoque do produto.",
        }


def obter_resumo_zeragem_estoques():
    """Resume todos os saldos físicos que a zeragem global encerrará."""
    with _conexao() as conn:
        cursor = conn.cursor()
        quantidade_total = 0
        custo_total_centavos = 0
        produtos_com_saldo = 0
        for produto in cursor.execute("SELECT id FROM produtos ORDER BY id").fetchall():
            lotes = _lotes_fifo_disponiveis(cursor, int(produto["id"]))
            quantidade = sum(int(lote["disponivel"]) for lote in lotes)
            if quantidade <= 0:
                continue
            produtos_com_saldo += 1
            quantidade_total += quantidade
            custo_total_centavos += sum(
                int(lote["disponivel"]) * int(lote["custo_unitario_centavos"])
                for lote in lotes
            )
    return {
        "sucesso": True,
        "quantidade_zerada": quantidade_total,
        "valor_zerado": _para_reais(custo_total_centavos),
        "produtos_zerados": produtos_com_saldo,
    }


def zerar_todos_estoques():
    """Zera atomicamente todos os saldos, inclusive de produtos arquivados."""
    try:
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            _limpar_reservas(cursor)
            ids_reservados = {
                int(row["produto_id"])
                for row in cursor.execute(
                    "SELECT DISTINCT produto_id FROM reservas_carrinho"
                )
            }
            reservas_liberadas = cursor.execute(
                "DELETE FROM reservas_carrinho"
            ).rowcount
            produtos = cursor.execute(
                "SELECT id, nome FROM produtos ORDER BY id"
            ).fetchall()
            agora = _agora()
            quantidade_total = 0
            custo_total_centavos = 0
            produtos_zerados = 0
            ids_afetados = set(ids_reservados)

            for produto in produtos:
                produto_id = int(produto["id"])
                quantidade = _saldo_produto(cursor, produto_id)
                if quantidade <= 0:
                    continue
                consumo = _consumir_fifo(
                    cursor,
                    produto_id,
                    quantidade,
                    tipo="ajuste",
                    observacao="Zeragem operacional global do estoque",
                    ocorrido_em=agora,
                    impacta_relatorio=False,
                )
                quantidade_total += quantidade
                custo_total_centavos += consumo["custo_total_centavos"]
                produtos_zerados += 1
                ids_afetados.add(produto_id)

        return {
            "sucesso": True,
            "quantidade_zerada": quantidade_total,
            "valor_zerado": _para_reais(custo_total_centavos),
            "produtos_zerados": produtos_zerados,
            "reservas_liberadas": reservas_liberadas,
            "produtos_afetados": [
                {"produto_id": produto_id, "disponivel": 0}
                for produto_id in sorted(ids_afetados)
            ],
        }
    except (sqlite3.Error, ValueError, TypeError):
        return {
            "sucesso": False,
            "mensagem": "Não foi possível zerar todos os estoques.",
        }


def obter_lotes_produto(id_produto):
    with _conexao() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM (
                SELECT l.id, l.quantidade_inicial,
                       l.custo_unitario_centavos, l.tipo,
                       l.observacao, l.recebido_em,
                       l.quantidade_inicial + COALESCE((
                           SELECT SUM(m.quantidade)
                           FROM estoque_movimentacoes m
                           WHERE m.lote_id = l.id
                       ), 0) AS quantidade_disponivel
                FROM estoque_lotes l
                WHERE l.produto_id = ?
            )
            ORDER BY recebido_em, id
            """,
            (int(id_produto),),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "quantidade_inicial": row["quantidade_inicial"],
            "quantidade_disponivel": row["quantidade_disponivel"],
            "custo_unitario": _para_reais(row["custo_unitario_centavos"]),
            "valor_disponivel": _para_reais(
                row["quantidade_disponivel"] * row["custo_unitario_centavos"]
            ),
            "tipo": row["tipo"],
            "observacao": row["observacao"],
            "recebido_em": row["recebido_em"],
            "data": datetime.fromisoformat(row["recebido_em"])
            .astimezone(TIMEZONE_LOCAL)
            .strftime("%d/%m/%Y %H:%M"),
        }
        for row in rows
    ]


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
    id_produto,
    nome,
    descricao,
    foto_url,
    categoria_id,
    requer_preparo,
    ocultar_quando_esgotado=0,
):
    try:
        with _conexao() as conn:
            cursor = conn.execute(
                """
                UPDATE produtos
                SET nome = ?, descricao = ?, foto_url = ?, categoria_id = ?,
                    requer_preparo = ?, ocultar_quando_esgotado = ?
                WHERE id = ? AND ativo = 1
                """,
                (
                    (nome or "").strip(),
                    descricao,
                    foto_url,
                    categoria_id,
                    1 if requer_preparo else 0,
                    1 if ocultar_quando_esgotado else 0,
                    id_produto,
                ),
            )
        return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def atualizar_produto(
    id_produto,
    nome,
    descricao,
    foto_url,
    categoria_id,
    preco_venda,
    requer_preparo,
    ocultar_quando_esgotado,
):
    """Atualiza todos os dados cadastrais em uma única transação."""
    try:
        nome = (nome or "").strip()
        preco_centavos = _para_centavos(preco_venda)
        categoria_id = int(categoria_id)
        if not nome or preco_centavos < 0:
            return {"sucesso": False, "mensagem": "Dados do produto inválidos."}
        with _conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            if not cursor.execute(
                "SELECT 1 FROM categorias WHERE id = ?", (categoria_id,)
            ).fetchone():
                return {"sucesso": False, "mensagem": "Categoria inválida."}
            atualizado = cursor.execute(
                """
                UPDATE produtos
                SET nome = ?, descricao = ?, foto_url = ?, categoria_id = ?,
                    preco_centavos = ?, requer_preparo = ?,
                    ocultar_quando_esgotado = ?
                WHERE id = ? AND ativo = 1
                """,
                (
                    nome,
                    descricao,
                    foto_url,
                    categoria_id,
                    preco_centavos,
                    1 if requer_preparo else 0,
                    1 if ocultar_quando_esgotado else 0,
                    int(id_produto),
                ),
            )
            if atualizado.rowcount == 0:
                return {"sucesso": False, "mensagem": "Produto não encontrado."}
        return {"sucesso": True}
    except sqlite3.IntegrityError:
        return {
            "sucesso": False,
            "mensagem": "Já existe um produto com esse nome.",
        }
    except (sqlite3.Error, ValueError, TypeError):
        return {"sucesso": False, "mensagem": "Não foi possível salvar o produto."}


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
            SELECT recebido_em AS created_at,
                   quantidade_inicial AS quantidade,
                   custo_unitario_centavos, tipo
            FROM estoque_lotes
            WHERE produto_id = ?
            ORDER BY recebido_em DESC, id DESC
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
                    custo_total_centavos,
                    quantidade, categoria_nome, customizacao_json, requer_preparo,
                    categoria_ordem, produto_ordem, uid
                ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pedido_id,
                    pid,
                    produto["nome"],
                    produto["preco_centavos"],
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
            pedido_item_id = int(cursor.lastrowid)
            quantidade_item = int(item["quantidade"])
            consumo = _consumir_fifo(
                cursor,
                pid,
                quantidade_item,
                tipo="venda",
                observacao=f"Consumo FIFO do pedido #{pedido_id}",
                pedido_id=int(pedido_id),
                pedido_item_id=pedido_item_id,
                ocorrido_em=agora,
            )
            custo_total = int(consumo["custo_total_centavos"])
            custo_unitario = int(
                (Decimal(custo_total) / Decimal(quantidade_item)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            cursor.execute(
                """
                UPDATE pedido_itens
                SET custo_unitario_centavos = ?, custo_total_centavos = ?
                WHERE id = ?
                """,
                (custo_unitario, custo_total, pedido_item_id),
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
            SELECT id, produto_id, pedido_item_id, lote_id,
                   quantidade, custo_unitario_centavos
            FROM estoque_movimentacoes
            WHERE pedido_id = ? AND tipo = 'venda'
            """,
            (id_do_pedido,),
        ).fetchall()
        for venda in vendas:
            lote_id = venda["lote_id"]
            if lote_id is None:
                # Compatibilidade com uma venda criada no schema v2: o saldo
                # devolvido passa a existir como um lote de ajuste no FIFO.
                lote_id = _criar_lote(
                    cursor,
                    int(venda["produto_id"]),
                    abs(int(venda["quantidade"])),
                    int(venda["custo_unitario_centavos"]),
                    tipo="ajuste",
                    observacao=f"Estorno legado do pedido #{id_do_pedido}",
                    recebido_em=agora,
                )
            cursor.execute(
                """
                INSERT OR IGNORE INTO estoque_movimentacoes(
                    produto_id, pedido_id, pedido_item_id, lote_id,
                    movimento_origem_id, tipo, quantidade,
                    custo_unitario_centavos, observacao, created_at
                ) VALUES (?, ?, ?, ?, ?, 'estorno', ?, ?, ?, ?)
                """,
                (
                    venda["produto_id"],
                    id_do_pedido,
                    venda["pedido_item_id"],
                    lote_id if venda["lote_id"] is not None else None,
                    venda["id"],
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
        saldos = {pid: _saldo_produto(cursor, pid) for pid in ids}
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


def _aplicar_quantidade_reservada(
    cursor: sqlite3.Cursor,
    carrinho_id: str,
    produto_id: int,
    quantidade_desejada: int,
    *,
    ajustar_ao_disponivel: bool,
):
    produto = cursor.execute(
        "SELECT ativo FROM produtos WHERE id = ?", (produto_id,)
    ).fetchone()
    atual_row = cursor.execute(
        """
        SELECT quantidade_reservada FROM reservas_carrinho
        WHERE carrinho_id = ? AND produto_id = ?
        """,
        (carrinho_id, produto_id),
    ).fetchone()
    atual = int(atual_row[0]) if atual_row else 0

    # Uma reserva existente sempre pode ser liberada, mesmo que o produto tenha
    # sido arquivado depois de entrar no carrinho.
    if (
        quantidade_desejada > atual
        and (not produto or not produto["ativo"])
    ):
        return {
            "sucesso": False,
            "mensagem": "Produto indisponível.",
            "quantidade_solicitada": quantidade_desejada,
            "quantidade_reservada": atual,
            "ajustada": False,
            "produtos_afetados": [],
        }

    saldo = _saldo_produto(cursor, produto_id) if produto else 0
    reservado_outros = int(
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantidade_reservada), 0)
            FROM reservas_carrinho
            WHERE produto_id = ? AND carrinho_id != ?
            """,
            (produto_id, carrinho_id),
        ).fetchone()[0]
    )
    maximo_para_carrinho = max(saldo - reservado_outros, 0)
    quantidade_aplicada = quantidade_desejada

    if quantidade_desejada > maximo_para_carrinho:
        if not ajustar_ao_disponivel:
            return {
                "sucesso": False,
                "mensagem": "Não há mais unidades deste item no momento.",
                "quantidade_solicitada": quantidade_desejada,
                "quantidade_reservada": atual,
                "maximo_disponivel": maximo_para_carrinho,
                "ajustada": False,
                "produtos_afetados": [
                    {
                        "produto_id": produto_id,
                        "disponivel": max(saldo - reservado_outros - atual, 0),
                    }
                ],
            }
        quantidade_aplicada = maximo_para_carrinho

    if quantidade_aplicada == 0:
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
                quantidade_aplicada,
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
    ajustada = quantidade_aplicada != quantidade_desejada
    return {
        "sucesso": not ajustada,
        "mensagem": (
            f"Quantidade ajustada para {quantidade_aplicada}, o máximo disponível."
            if ajustada
            else None
        ),
        "quantidade_solicitada": quantidade_desejada,
        "quantidade_reservada": quantidade_aplicada,
        "maximo_disponivel": maximo_para_carrinho,
        "ajustada": ajustada,
        "produtos_afetados": [
            {"produto_id": produto_id, "disponivel": saldo - reservado_total}
        ],
    }


def definir_reserva(carrinho_id, produto_id, quantidade_desejada):
    """Define de forma idempotente a reserva total de um produto no carrinho."""
    conn = None
    try:
        carrinho_id = str(carrinho_id or "").strip()
        produto_id = int(produto_id)
        desejada = int(quantidade_desejada)
        if not carrinho_id or desejada < 0:
            return {"sucesso": False, "mensagem": "Dados de reserva inválidos."}

        conn = _conectar()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        _limpar_reservas(cursor)
        resultado = _aplicar_quantidade_reservada(
            cursor,
            carrinho_id,
            produto_id,
            desejada,
            ajustar_ao_disponivel=True,
        )
        conn.commit()
        return resultado
    except (sqlite3.Error, ValueError, TypeError):
        if conn:
            conn.rollback()
        return {"sucesso": False, "mensagem": "Erro no servidor."}
    finally:
        if conn:
            conn.close()


def gerenciar_reserva(carrinho_id, produto_id, quantidade_delta):
    """Compatibilidade com clientes antigos que ainda enviam deltas."""
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
        resultado = _aplicar_quantidade_reservada(
            cursor,
            carrinho_id,
            produto_id,
            nova,
            ajustar_ao_disponivel=False,
        )
        if not resultado.get("sucesso"):
            conn.rollback()
            return resultado
        conn.commit()
        return resultado
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
