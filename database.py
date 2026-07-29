"""Infraestrutura e esquema canônico do banco de dados do PDV."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 4


def _diretorio_aplicacao() -> Path:
    """Mantém o banco gravável fora do bundle quando a aplicação está congelada."""
    override = os.environ.get("ESPETAO_DB_PATH")
    if override:
        return Path(override).expanduser().resolve().parent
    if getattr(sys, "frozen", False):
        return Path.home() / ".espetao"
    return Path(__file__).resolve().parent


def caminho_banco() -> Path:
    override = os.environ.get("ESPETAO_DB_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return _diretorio_aplicacao() / "espetao.db"


def _banco_embutido() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    candidatos = []
    if hasattr(sys, "_MEIPASS"):
        candidatos.append(Path(sys._MEIPASS) / "espetao.db")
    candidatos.append(Path(sys.executable).resolve().parent / "espetao.db")
    return next((path for path in candidatos if path.exists()), None)


NOME_BANCO_DADOS = str(caminho_banco())


def conectar(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Abre uma conexão sempre com as mesmas garantias de integridade."""
    path = str(db_path or caminho_banco())
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL COLLATE NOCASE UNIQUE
);

CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL COLLATE NOCASE UNIQUE,
    ordem INTEGER NOT NULL DEFAULT 0 CHECK (ordem >= 0)
);

CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL COLLATE NOCASE UNIQUE,
    descricao TEXT,
    foto_url TEXT,
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
    categoria_id INTEGER,
    ordem INTEGER NOT NULL DEFAULT 0 CHECK (ordem >= 0),
    requer_preparo INTEGER NOT NULL DEFAULT 0 CHECK (requer_preparo IN (0, 1)),
    ocultar_quando_esgotado INTEGER NOT NULL DEFAULT 0
        CHECK (ocultar_quando_esgotado IN (0, 1)),
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tempos_preparo (
    produto_id INTEGER NOT NULL,
    ponto TEXT NOT NULL CHECK (ponto IN ('mal', 'ponto', 'bem')),
    tempo_em_segundos INTEGER NOT NULL CHECK (tempo_em_segundos >= 0),
    PRIMARY KEY (produto_id, ponto),
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS acompanhamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL COLLATE NOCASE UNIQUE,
    is_visivel INTEGER NOT NULL DEFAULT 1 CHECK (is_visivel IN (0, 1))
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor REAL NOT NULL CHECK (valor >= 0)
);

CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_cliente TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'aguardando_pagamento', 'aguardando_producao', 'em_producao',
            'aguardando_retirada', 'finalizado', 'cancelado'
        )
    ),
    metodo_pagamento TEXT NOT NULL CHECK (
        metodo_pagamento IN ('pix', 'cartao_credito', 'cartao_debito', 'dinheiro')
    ),
    modalidade TEXT NOT NULL CHECK (modalidade IN ('local', 'viagem')),
    valor_total_centavos INTEGER NOT NULL CHECK (valor_total_centavos >= 0),
    timestamp_criacao TEXT NOT NULL,
    timestamp_pagamento TEXT,
    timestamp_finalizacao TEXT,
    timestamp_cancelamento TEXT,
    senha_diaria INTEGER NOT NULL CHECK (senha_diaria > 0),
    fluxo_simples INTEGER NOT NULL DEFAULT 0 CHECK (fluxo_simples IN (0, 1)),
    local_id INTEGER NOT NULL,
    FOREIGN KEY (local_id) REFERENCES locais(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS pedido_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    nome_produto TEXT NOT NULL,
    preco_unitario_centavos INTEGER NOT NULL CHECK (preco_unitario_centavos >= 0),
    custo_unitario_centavos INTEGER NOT NULL CHECK (custo_unitario_centavos >= 0),
    custo_total_centavos INTEGER NOT NULL DEFAULT 0 CHECK (custo_total_centavos >= 0),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    categoria_nome TEXT NOT NULL,
    customizacao_json TEXT,
    requer_preparo INTEGER NOT NULL DEFAULT 0 CHECK (requer_preparo IN (0, 1)),
    timestamp_inicio_item TEXT,
    categoria_ordem INTEGER NOT NULL DEFAULT 0,
    produto_ordem INTEGER NOT NULL DEFAULT 0,
    uid TEXT NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('pagamento', 'estorno')),
    metodo TEXT NOT NULL CHECK (
        metodo IN ('pix', 'cartao_credito', 'cartao_debito', 'dinheiro')
    ),
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
    taxa_centavos INTEGER NOT NULL DEFAULT 0 CHECK (taxa_centavos >= 0),
    ocorrido_em TEXT NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE RESTRICT,
    UNIQUE (pedido_id, tipo)
);

CREATE TABLE IF NOT EXISTS estoque_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL,
    quantidade_inicial INTEGER NOT NULL CHECK (quantidade_inicial > 0),
    custo_unitario_centavos INTEGER NOT NULL CHECK (custo_unitario_centavos >= 0),
    tipo TEXT NOT NULL CHECK (tipo IN ('saldo_inicial', 'compra', 'ajuste')),
    observacao TEXT,
    recebido_em TEXT NOT NULL,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS estoque_movimentacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL,
    pedido_id INTEGER,
    pedido_item_id INTEGER,
    lote_id INTEGER,
    movimento_origem_id INTEGER,
    tipo TEXT NOT NULL CHECK (
        tipo IN ('saldo_inicial', 'compra', 'venda', 'perda', 'ajuste', 'estorno')
    ),
    quantidade INTEGER NOT NULL CHECK (quantidade != 0),
    custo_unitario_centavos INTEGER NOT NULL CHECK (custo_unitario_centavos >= 0),
    impacta_relatorio INTEGER NOT NULL DEFAULT 1
        CHECK (impacta_relatorio IN (0, 1)),
    observacao TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE RESTRICT,
    FOREIGN KEY (pedido_item_id) REFERENCES pedido_itens(id) ON DELETE RESTRICT,
    FOREIGN KEY (lote_id) REFERENCES estoque_lotes(id) ON DELETE RESTRICT,
    FOREIGN KEY (movimento_origem_id) REFERENCES estoque_movimentacoes(id)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_estoque_estorno_movimento_origem
ON estoque_movimentacoes (movimento_origem_id)
WHERE tipo = 'estorno';

CREATE INDEX IF NOT EXISTS idx_pedidos_status_criacao
ON pedidos(status, timestamp_criacao);

CREATE INDEX IF NOT EXISTS idx_pedidos_local
ON pedidos(local_id);

CREATE INDEX IF NOT EXISTS idx_pagamentos_periodo
ON pagamentos(ocorrido_em, tipo);

CREATE INDEX IF NOT EXISTS idx_pagamentos_pedido
ON pagamentos(pedido_id);

CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido
ON pedido_itens(pedido_id);

CREATE INDEX IF NOT EXISTS idx_lotes_produto_fifo
ON estoque_lotes(produto_id, recebido_em, id);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_produto_data
ON estoque_movimentacoes(produto_id, created_at);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_periodo
ON estoque_movimentacoes(created_at, tipo);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_lote
ON estoque_movimentacoes(lote_id);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_pedido_item
ON estoque_movimentacoes(pedido_item_id);

CREATE TABLE IF NOT EXISTS reservas_carrinho (
    carrinho_id TEXT NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade_reservada INTEGER NOT NULL CHECK (quantidade_reservada > 0),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (carrinho_id, produto_id),
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reservas_expires
ON reservas_carrinho(expires_at);
"""


def _criar_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    colunas_produtos = {
        row["name"] for row in conn.execute("PRAGMA table_info(produtos)")
    }
    if "ocultar_quando_esgotado" not in colunas_produtos:
        conn.execute(
            """
            ALTER TABLE produtos
            ADD COLUMN ocultar_quando_esgotado INTEGER NOT NULL DEFAULT 0
                CHECK (ocultar_quando_esgotado IN (0, 1))
            """
        )
    conn.executemany(
        "INSERT OR IGNORE INTO configuracoes(chave, valor) VALUES (?, ?)",
        (("taxa_credito", 0.0), ("taxa_debito", 0.0), ("taxa_pix", 0.0)),
    )
    conn.execute(
        "INSERT OR IGNORE INTO categorias(id, nome, ordem) VALUES (1, 'Espetinhos', 0)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _tabelas(conn: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _versao_atual(conn: sqlite3.Connection) -> int | None:
    if "schema_version" not in _tabelas(conn):
        return None
    row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
    return int(row["version"]) if row and row["version"] is not None else None


def _backup_path(path: Path, rotulo: str) -> Path:
    base = path.with_suffix(path.suffix + f".{rotulo}.bak")
    if not base.exists():
        return base
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_suffix(path.suffix + f".{rotulo}-{stamp}.bak")


def _criar_backup_sqlite(path: Path, destino: Path) -> None:
    """Cria uma cópia consistente mesmo quando o banco usa WAL."""
    origem = sqlite3.connect(path)
    backup = sqlite3.connect(destino)
    try:
        origem.backup(backup)
    finally:
        backup.close()
        origem.close()


def _adicionar_coluna_se_ausente(
    conn: sqlite3.Connection,
    tabela: str,
    coluna: str,
    definicao: str,
) -> None:
    colunas = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({tabela})")
    }
    if coluna not in colunas:
        conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


def migrar_v2_para_v3(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Adiciona lotes FIFO preservando integralmente cadastros e pedidos v2."""
    path = Path(db_path or caminho_banco()).resolve()
    backup = _backup_path(path, "pre-v3")
    _criar_backup_sqlite(path, backup)

    conn = conectar(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP INDEX IF EXISTS uq_estoque_venda_pedido_produto")
        conn.execute("DROP INDEX IF EXISTS uq_estoque_estorno_pedido_produto")

        _adicionar_coluna_se_ausente(
            conn,
            "produtos",
            "ocultar_quando_esgotado",
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (ocultar_quando_esgotado IN (0, 1))",
        )
        _adicionar_coluna_se_ausente(
            conn,
            "pedido_itens",
            "custo_total_centavos",
            "INTEGER NOT NULL DEFAULT 0 CHECK (custo_total_centavos >= 0)",
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estoque_lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id INTEGER NOT NULL,
                quantidade_inicial INTEGER NOT NULL CHECK (quantidade_inicial > 0),
                custo_unitario_centavos INTEGER NOT NULL
                    CHECK (custo_unitario_centavos >= 0),
                tipo TEXT NOT NULL
                    CHECK (tipo IN ('saldo_inicial', 'compra', 'ajuste')),
                observacao TEXT,
                recebido_em TEXT NOT NULL,
                FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT
            )
            """
        )
        _adicionar_coluna_se_ausente(
            conn,
            "estoque_movimentacoes",
            "pedido_item_id",
            "INTEGER REFERENCES pedido_itens(id) ON DELETE RESTRICT",
        )
        _adicionar_coluna_se_ausente(
            conn,
            "estoque_movimentacoes",
            "lote_id",
            "INTEGER REFERENCES estoque_lotes(id) ON DELETE RESTRICT",
        )
        _adicionar_coluna_se_ausente(
            conn,
            "estoque_movimentacoes",
            "movimento_origem_id",
            "INTEGER REFERENCES estoque_movimentacoes(id) ON DELETE RESTRICT",
        )
        _adicionar_coluna_se_ausente(
            conn,
            "estoque_movimentacoes",
            "impacta_relatorio",
            "INTEGER NOT NULL DEFAULT 1 CHECK (impacta_relatorio IN (0, 1))",
        )

        # As entradas v2 viram um lote de abertura por produto. As saídas e
        # estornos antigos passam a apontar para esse lote, preservando saldo,
        # cancelamentos pendentes e o histórico necessário para os testes.
        quantidade_lotes = conn.execute(
            "SELECT COUNT(*) FROM estoque_lotes"
        ).fetchone()[0]
        if not quantidade_lotes:
            entradas = conn.execute(
                """
                SELECT p.id AS produto_id,
                       COALESCE(SUM(
                           CASE
                             WHEN m.quantidade > 0
                              AND m.tipo IN ('saldo_inicial', 'compra', 'ajuste')
                             THEN m.quantidade ELSE 0
                           END
                       ), 0) AS quantidade_inicial,
                       COALESCE(
                           SUM(
                               CASE
                                 WHEN m.quantidade > 0
                                  AND m.tipo IN (
                                      'saldo_inicial', 'compra', 'ajuste'
                                  )
                                 THEN m.quantidade * m.custo_unitario_centavos
                                 ELSE 0
                               END
                           ), 0
                       ) AS valor,
                       MIN(
                           CASE
                             WHEN m.quantidade > 0
                              AND m.tipo IN ('saldo_inicial', 'compra', 'ajuste')
                             THEN m.created_at
                           END
                       ) AS primeira_entrada
                FROM produtos p
                LEFT JOIN estoque_movimentacoes m ON m.produto_id = p.id
                GROUP BY p.id
                """
            ).fetchall()
            agora = datetime.now(timezone.utc).isoformat()
            for row in entradas:
                quantidade_inicial = int(row["quantidade_inicial"] or 0)
                if quantidade_inicial <= 0:
                    continue
                valor = int(row["valor"] or 0)
                custo = max(int(round(valor / quantidade_inicial)), 0)
                lote = conn.execute(
                    """
                    INSERT INTO estoque_lotes(
                        produto_id, quantidade_inicial,
                        custo_unitario_centavos, tipo, observacao, recebido_em
                    ) VALUES (?, ?, ?, 'saldo_inicial', ?, ?)
                    """,
                    (
                        row["produto_id"],
                        quantidade_inicial,
                        custo,
                        "Saldo preservado na migração para FIFO",
                        row["primeira_entrada"] or agora,
                    ),
                )
                lote_id = int(lote.lastrowid)
                conn.execute(
                    """
                    UPDATE estoque_movimentacoes
                    SET lote_id = ?
                    WHERE produto_id = ?
                      AND NOT (
                          quantidade > 0
                          AND tipo IN ('saldo_inicial', 'compra', 'ajuste')
                      )
                    """,
                    (lote_id, row["produto_id"]),
                )

            conn.execute(
                """
                UPDATE estoque_movimentacoes
                SET pedido_item_id = (
                    SELECT pi.id
                    FROM pedido_itens pi
                    WHERE pi.pedido_id = estoque_movimentacoes.pedido_id
                      AND pi.produto_id = estoque_movimentacoes.produto_id
                    ORDER BY pi.id
                    LIMIT 1
                )
                WHERE tipo = 'venda' AND pedido_id IS NOT NULL
                """
            )

        conn.execute(
            """
            UPDATE pedido_itens
            SET custo_total_centavos = custo_unitario_centavos * quantidade
            WHERE custo_total_centavos = 0
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_estoque_estorno_movimento_origem
            ON estoque_movimentacoes (movimento_origem_id)
            WHERE tipo = 'estorno'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lotes_produto_fifo
            ON estoque_lotes(produto_id, recebido_em, id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_movimentacoes_lote
            ON estoque_movimentacoes(lote_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_movimentacoes_pedido_item
            ON estoque_movimentacoes(pedido_item_id)
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise sqlite3.IntegrityError(
                "A migração FIFO criou referências inválidas"
            )
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.IntegrityError("Falha de integridade após a migração FIFO")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return backup


def migrar_v3_para_v4(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Marca ajustes operacionais neutros sem reescrever o histórico FIFO."""
    path = Path(db_path or caminho_banco()).resolve()
    backup = _backup_path(path, "pre-v4")
    _criar_backup_sqlite(path, backup)

    conn = conectar(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _adicionar_coluna_se_ausente(
            conn,
            "estoque_movimentacoes",
            "impacta_relatorio",
            "INTEGER NOT NULL DEFAULT 1 CHECK (impacta_relatorio IN (0, 1))",
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise sqlite3.IntegrityError(
                "A migração de ajustes neutros criou referências inválidas"
            )
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.IntegrityError(
                "Falha de integridade após habilitar ajustes neutros"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return backup


def _extrair_legado(conn: sqlite3.Connection) -> dict:
    """Extrai apenas cadastros e saldo operacional; pedidos antigos não migram."""
    tabelas = _tabelas(conn)
    dados: dict[str, list] = {
        "locais": [],
        "categorias": [],
        "produtos": [],
        "tempos": [],
        "acompanhamentos": [],
        "configuracoes": [],
        "saldos": [],
    }
    if "locais" in tabelas:
        dados["locais"] = [tuple(row) for row in conn.execute("SELECT id, nome FROM locais")]
    if "categorias" in tabelas:
        dados["categorias"] = [
            tuple(row)
            for row in conn.execute("SELECT id, nome, COALESCE(ordem, 0) FROM categorias")
        ]
    if "produtos" in tabelas:
        dados["produtos"] = [
            tuple(row)
            for row in conn.execute(
                """
                SELECT id, nome, descricao, foto_url,
                       CAST(ROUND(preco_venda * 100) AS INTEGER),
                       categoria_id, COALESCE(ordem, 0), COALESCE(requer_preparo, 0)
                FROM produtos
                """
            )
        ]
    ids_produtos = {row[0] for row in dados["produtos"]}
    if "tempos_preparo" in tabelas:
        dados["tempos"] = [
            tuple(row)
            for row in conn.execute(
                "SELECT produto_id, ponto, tempo_em_segundos FROM tempos_preparo"
            )
            if row[0] in ids_produtos
        ]
    if "acompanhamentos" in tabelas:
        dados["acompanhamentos"] = [
            tuple(row)
            for row in conn.execute(
                "SELECT id, nome, COALESCE(is_visivel, 1) FROM acompanhamentos"
            )
        ]
    if "configuracoes" in tabelas:
        dados["configuracoes"] = [
            tuple(row) for row in conn.execute("SELECT chave, valor FROM configuracoes")
        ]
    if "estoque_movimentacoes" in tabelas:
        saldos = conn.execute(
            """
            SELECT produto_id,
                   SUM(quantidade) AS saldo,
                   CASE
                     WHEN SUM(CASE WHEN quantidade > 0 THEN quantidade ELSE 0 END) > 0
                     THEN CAST(ROUND(
                       100.0 * SUM(CASE WHEN quantidade > 0
                                      THEN custo_total_movimentacao ELSE 0 END)
                       / SUM(CASE WHEN quantidade > 0 THEN quantidade ELSE 0 END)
                     ) AS INTEGER)
                     ELSE 0
                   END AS custo_centavos
            FROM estoque_movimentacoes
            GROUP BY produto_id
            """
        ).fetchall()
        dados["saldos"] = [
            (int(row["produto_id"]), max(int(row["saldo"] or 0), 0), int(row["custo_centavos"] or 0))
            for row in saldos
            if row["produto_id"] in ids_produtos and int(row["saldo"] or 0) > 0
        ]
    return dados


def migrar_banco_legado(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Migra o banco v1 de forma atômica, mantendo uma cópia recuperável."""
    path = Path(db_path or caminho_banco()).resolve()
    if not path.exists():
        conn = conectar(path)
        try:
            _criar_schema(conn)
        finally:
            conn.close()
        return path

    legado = sqlite3.connect(path)
    legado.row_factory = sqlite3.Row
    try:
        if _versao_atual(legado) == SCHEMA_VERSION:
            return path
        dados = _extrair_legado(legado)
    finally:
        legado.close()

    backup = _backup_path(path, "legacy-v1")
    _criar_backup_sqlite(path, backup)

    temporario = path.with_suffix(path.suffix + ".v3.tmp")
    if temporario.exists():
        temporario.unlink()
    novo = conectar(temporario)
    try:
        _criar_schema(novo)
        with novo:
            novo.executemany(
                "INSERT OR IGNORE INTO locais(id, nome) VALUES (?, ?)", dados["locais"]
            )
            novo.executemany(
                "INSERT OR REPLACE INTO categorias(id, nome, ordem) VALUES (?, ?, ?)",
                dados["categorias"],
            )
            novo.executemany(
                """
                INSERT INTO produtos(
                    id, nome, descricao, foto_url, preco_centavos,
                    categoria_id, ordem, requer_preparo, ativo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                dados["produtos"],
            )
            novo.executemany(
                """
                INSERT INTO tempos_preparo(produto_id, ponto, tempo_em_segundos)
                VALUES (?, ?, ?)
                """,
                dados["tempos"],
            )
            novo.executemany(
                """
                INSERT INTO acompanhamentos(id, nome, is_visivel)
                VALUES (?, ?, ?)
                """,
                dados["acompanhamentos"],
            )
            novo.executemany(
                "INSERT OR REPLACE INTO configuracoes(chave, valor) VALUES (?, ?)",
                dados["configuracoes"],
            )
            agora = datetime.now(timezone.utc).isoformat()
            novo.executemany(
                """
                INSERT INTO estoque_lotes(
                    produto_id, tipo, quantidade_inicial,
                    custo_unitario_centavos, observacao, recebido_em
                ) VALUES (?, 'saldo_inicial', ?, ?,
                          'Saldo consolidado da migração legada', ?)
                """,
                [(pid, saldo, custo, agora) for pid, saldo, custo in dados["saldos"]],
            )
        resultado = novo.execute("PRAGMA integrity_check").fetchone()[0]
        if resultado != "ok":
            raise sqlite3.IntegrityError(f"Falha na integridade do banco migrado: {resultado}")
        if novo.execute("PRAGMA foreign_key_check").fetchone():
            raise sqlite3.IntegrityError("O banco migrado contém chaves estrangeiras inválidas")
    finally:
        novo.close()

    os.replace(temporario, path)
    return backup


def inicializar_banco(db_path: str | os.PathLike[str] | None = None) -> None:
    path = Path(db_path or caminho_banco())
    if not path.exists() and db_path is None:
        embutido = _banco_embutido()
        if embutido and embutido.resolve() != path.resolve():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(embutido, path)
    if path.exists():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            versao = _versao_atual(conn)
        finally:
            conn.close()
        if versao == 2:
            migrar_v2_para_v3(path)
            return
        if versao == 3:
            migrar_v3_para_v4(path)
            return
        if versao != SCHEMA_VERSION:
            migrar_banco_legado(path)
            return
    conn = conectar(path)
    try:
        _criar_schema(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    inicializar_banco()
    print(f"Banco pronto em {caminho_banco()} (schema v{SCHEMA_VERSION}).")
