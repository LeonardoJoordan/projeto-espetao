import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta

import analytics
import database
import gerenciador_db as db


class PDVTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "teste.db")
        os.environ["ESPETAO_DB_PATH"] = self.db_path
        database.inicializar_banco()
        self.assertTrue(db.adicionar_local("Loja Teste"))
        self.local_id = db.obter_todos_locais()[0]["id"]
        self.assertTrue(
            db.adicionar_novo_produto(
                "Espeto Teste", "Produto de teste", None, 10.00, 10, 4.00, 1, 0
            )
        )
        self.produto_id = db.obter_todos_produtos_para_gestao()[0]["id"]

    def tearDown(self):
        os.environ.pop("ESPETAO_DB_PATH", None)
        self.temp_dir.cleanup()

    def novo_pedido(self, quantidade=1, metodo="pix"):
        return db.salvar_novo_pedido(
            {
                "nome_cliente": "Cliente Teste",
                "itens": [
                    {
                        "id": self.produto_id,
                        "nome": "Nome adulterado",
                        "preco": 0.01,
                        "quantidade": quantidade,
                    }
                ],
                "metodo_pagamento": metodo,
                "modalidade": "local",
                "carrinho_id": "carrinho-teste",
            },
            self.local_id,
        )

    def periodo_do_pagamento(self, pedido_id):
        pedido = db.obter_pedido_por_id(pedido_id)
        dia = pedido["timestamp_pagamento"][:10]
        return f"{dia}T00:00:00+00:00", f"{dia}T23:59:59.999999+00:00"

    def test_schema_normalizado_e_chaves_estrangeiras_ativas(self):
        with closing(database.conectar()) as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            colunas_produto = {
                row["name"] for row in conn.execute("PRAGMA table_info(produtos)")
            }
            self.assertNotIn("estoque_atual", colunas_produto)
            self.assertNotIn("estoque_reservado", colunas_produto)
            self.assertNotIn("custo_medio", colunas_produto)
            self.assertIn("ocultar_quando_esgotado", colunas_produto)
            self.assertIn("pedido_itens", {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            })
            self.assertIn("estoque_lotes", {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            })
            self.assertIn("operacoes", {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            })
            self.assertIn("operacao_estoque", {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            })
            colunas_item = {
                row["name"] for row in conn.execute("PRAGMA table_info(pedido_itens)")
            }
            self.assertIn("custo_total_centavos", colunas_item)
            colunas_pedido = {
                row["name"] for row in conn.execute("PRAGMA table_info(pedidos)")
            }
            self.assertIn("operacao_id", colunas_pedido)
            colunas_movimento = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(estoque_movimentacoes)"
                )
            }
            self.assertTrue(
                {
                    "lote_id",
                    "pedido_item_id",
                    "movimento_origem_id",
                    "impacta_relatorio",
                }
                <= colunas_movimento
            )

    def test_extensao_de_visibilidade_preserva_banco_v2_existente(self):
        caminho_v2 = os.path.join(self.temp_dir.name, "schema-v2.db")
        conn = sqlite3.connect(caminho_v2)
        try:
            conn.executescript(
                """
                CREATE TABLE schema_version(
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE produtos(
                    id INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL UNIQUE,
                    descricao TEXT,
                    foto_url TEXT,
                    preco_centavos INTEGER NOT NULL,
                    categoria_id INTEGER,
                    ordem INTEGER NOT NULL DEFAULT 0,
                    requer_preparo INTEGER NOT NULL DEFAULT 0,
                    ativo INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE pedido_itens(
                    id INTEGER PRIMARY KEY,
                    pedido_id INTEGER NOT NULL,
                    produto_id INTEGER NOT NULL,
                    custo_unitario_centavos INTEGER NOT NULL,
                    quantidade INTEGER NOT NULL
                );
                CREATE TABLE estoque_movimentacoes(
                    id INTEGER PRIMARY KEY,
                    produto_id INTEGER NOT NULL,
                    pedido_id INTEGER,
                    tipo TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    custo_unitario_centavos INTEGER NOT NULL,
                    observacao TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            agora = datetime.now().isoformat()
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES (2, ?)",
                (agora,),
            )
            conn.execute(
                """
                INSERT INTO produtos(
                    id, nome, preco_centavos, categoria_id,
                    ordem, requer_preparo, ativo
                ) VALUES (1, 'Produto preservado', 1000, NULL, 0, 0, 1)
                """
            )
            conn.execute(
                """
                INSERT INTO estoque_movimentacoes(
                    id, produto_id, tipo, quantidade,
                    custo_unitario_centavos, created_at
                ) VALUES (1, 1, 'saldo_inicial', 5, 300, ?)
                """,
                (agora,),
            )
            conn.execute(
                """
                INSERT INTO estoque_movimentacoes(
                    id, produto_id, tipo, quantidade,
                    custo_unitario_centavos, created_at
                ) VALUES (2, 1, 'venda', -1, 300, ?)
                """,
                (agora,),
            )
            conn.commit()
        finally:
            conn.close()

        database.inicializar_banco(caminho_v2)

        with closing(database.conectar(caminho_v2)) as migrado:
            colunas = {
                row["name"] for row in migrado.execute("PRAGMA table_info(produtos)")
            }
            produto = migrado.execute(
                "SELECT nome, ocultar_quando_esgotado FROM produtos WHERE id = 1"
            ).fetchone()
            lote = migrado.execute(
                """
                SELECT l.quantidade_inicial,
                       l.quantidade_inicial + COALESCE(SUM(m.quantidade), 0) AS saldo
                FROM estoque_lotes l
                LEFT JOIN estoque_movimentacoes m ON m.lote_id = l.id
                WHERE l.produto_id = 1
                GROUP BY l.id
                """
            ).fetchone()
            self.assertIn("ocultar_quando_esgotado", colunas)
            self.assertEqual(produto["nome"], "Produto preservado")
            self.assertEqual(produto["ocultar_quando_esgotado"], 0)
            self.assertEqual(lote["quantidade_inicial"], 5)
            self.assertEqual(lote["saldo"], 4)
            self.assertEqual(
                migrado.execute("SELECT MAX(version) FROM schema_version").fetchone()[0],
                database.SCHEMA_VERSION,
            )

    def test_migracao_v3_habilita_ajuste_neutro_sem_apagar_movimentos(self):
        caminho_v3 = os.path.join(self.temp_dir.name, "schema-v3.db")
        conn = sqlite3.connect(caminho_v3)
        try:
            conn.executescript(
                """
                CREATE TABLE schema_version(
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE estoque_movimentacoes(
                    id INTEGER PRIMARY KEY,
                    produto_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    custo_unitario_centavos INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO schema_version(version, applied_at)
                VALUES (3, '2026-01-01T00:00:00+00:00');
                INSERT INTO estoque_movimentacoes(
                    id, produto_id, tipo, quantidade,
                    custo_unitario_centavos, created_at
                ) VALUES (1, 10, 'venda', -2, 350, '2026-01-01T00:00:00+00:00');
                """
            )
            conn.commit()
        finally:
            conn.close()

        database.inicializar_banco(caminho_v3)

        with closing(database.conectar(caminho_v3)) as migrado:
            movimento = migrado.execute(
                """
                SELECT quantidade, custo_unitario_centavos, impacta_relatorio
                FROM estoque_movimentacoes WHERE id = 1
                """
            ).fetchone()
            self.assertEqual(
                (
                    movimento["quantidade"],
                    movimento["custo_unitario_centavos"],
                    movimento["impacta_relatorio"],
                ),
                (-2, 350, 1),
            )
            self.assertEqual(
                migrado.execute("SELECT MAX(version) FROM schema_version").fetchone()[0],
                database.SCHEMA_VERSION,
            )

    def test_servidor_recalcula_preco_nome_custo_e_total(self):
        pedido = self.novo_pedido(2)
        self.assertIsNotNone(pedido)
        salvo = db.obter_pedido_por_id(pedido["id"])
        self.assertEqual(salvo["valor_total"], 20.0)
        self.assertEqual(salvo["itens"][0]["nome"], "Espeto Teste")
        self.assertEqual(salvo["itens"][0]["preco"], 10.0)
        self.assertEqual(salvo["itens"][0]["custo_unitario"], 4.0)
        disponibilidade = db.obter_disponibilidade_para_produtos([self.produto_id])
        self.assertEqual(disponibilidade[self.produto_id], 8)

    def test_fifo_consume_lotes_e_guarda_custo_total_exato(self):
        produto_id = db.adicionar_novo_produto(
            "Coca FIFO", None, None, 5.00, 10, 3.00, 1, 0
        )
        self.assertTrue(db.adicionar_estoque(produto_id, 20, 2.00))

        pedido = db.salvar_novo_pedido(
            {
                "nome_cliente": "Cliente FIFO",
                "itens": [{"id": produto_id, "quantidade": 11}],
                "metodo_pagamento": "pix",
                "modalidade": "local",
                "carrinho_id": "fifo-11",
            },
            self.local_id,
        )
        self.assertIsNotNone(pedido)
        salvo = db.obter_pedido_por_id(pedido["id"])
        self.assertEqual(salvo["itens"][0]["custo_total"], 32.00)
        self.assertEqual(salvo["itens"][0]["custo_unitario"], 2.91)

        lotes = db.obter_lotes_produto(produto_id)
        self.assertEqual(
            [lote["quantidade_disponivel"] for lote in lotes],
            [0, 19],
        )
        with closing(database.conectar()) as conn:
            saidas = conn.execute(
                """
                SELECT quantidade, custo_unitario_centavos
                FROM estoque_movimentacoes
                WHERE pedido_id = ? AND tipo = 'venda'
                ORDER BY id
                """,
                (pedido["id"],),
            ).fetchall()
            self.assertEqual(
                [(row["quantidade"], row["custo_unitario_centavos"]) for row in saidas],
                [(-10, 300), (-1, 200)],
            )

        self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
        inicio, fim = self.periodo_do_pagamento(pedido["id"])
        fechamento = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        item = next(
            item
            for item in fechamento["itens_top"]
            if item["nome"] == "Coca FIFO"
        )
        self.assertEqual(item["custo"], 32.00)
        self.assertEqual(item["lucro"], 23.00)

    def test_estorno_fifo_restaura_exatamente_os_lotes_consumidos(self):
        produto_id = db.adicionar_novo_produto(
            "Produto Estorno FIFO", None, None, 5.00, 2, 3.00, 1, 0
        )
        self.assertTrue(db.adicionar_estoque(produto_id, 3, 2.00))
        pedido = db.salvar_novo_pedido(
            {
                "nome_cliente": "Estorno FIFO",
                "itens": [{"id": produto_id, "quantidade": 4}],
                "metodo_pagamento": "dinheiro",
                "modalidade": "local",
                "carrinho_id": "estorno-fifo",
            },
            self.local_id,
        )
        self.assertTrue(db.cancelar_pedido(pedido["id"]))
        self.assertTrue(db.cancelar_pedido(pedido["id"]))

        lotes = db.obter_lotes_produto(produto_id)
        self.assertEqual(
            [lote["quantidade_disponivel"] for lote in lotes],
            [2, 3],
        )
        with closing(database.conectar()) as conn:
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM estoque_movimentacoes
                    WHERE pedido_id = ? AND tipo = 'estorno'
                    """,
                    (pedido["id"],),
                ).fetchone()[0],
                2,
            )

    def test_perda_fifo_consume_lotes_antigos_com_custo_exato(self):
        produto_id = db.adicionar_novo_produto(
            "Produto Perda FIFO", None, None, 8.00, 2, 3.00, 1, 0
        )
        self.assertTrue(db.adicionar_estoque(produto_id, 3, 2.00))
        resultado = db.registrar_perda_estoque(
            produto_id, 4, "Avaria no transporte"
        )
        self.assertTrue(resultado["sucesso"])
        self.assertEqual(resultado["custo_total"], 10.00)
        self.assertEqual(resultado["saldo"], 1)
        lotes = db.obter_lotes_produto(produto_id)
        self.assertEqual(
            [lote["quantidade_disponivel"] for lote in lotes],
            [0, 1],
        )

    def test_pedido_sem_estoque_falha_sem_gravacao_parcial(self):
        self.assertIsNone(self.novo_pedido(11))
        with closing(database.conectar()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0], 0)
            lote = conn.execute(
                """
                SELECT quantidade_inicial FROM estoque_lotes
                WHERE produto_id = ?
                """,
                (self.produto_id,),
            ).fetchone()
            self.assertEqual(lote["quantidade_inicial"], 10)
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM estoque_movimentacoes
                    WHERE produto_id = ?
                    """,
                    (self.produto_id,),
                ).fetchone()[0],
                0,
            )

    def test_reserva_absoluta_e_idempotente_com_liberacao_imediata(self):
        primeira = db.definir_reserva("carrinho-a", self.produto_id, 8)
        repetida = db.definir_reserva("carrinho-a", self.produto_id, 8)
        segundo_carrinho = db.definir_reserva("carrinho-b", self.produto_id, 5)

        self.assertTrue(primeira["sucesso"])
        self.assertTrue(repetida["sucesso"])
        self.assertEqual(repetida["quantidade_reservada"], 8)
        self.assertTrue(segundo_carrinho["ajustada"])
        self.assertEqual(segundo_carrinho["quantidade_reservada"], 2)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id])[
                self.produto_id
            ],
            0,
        )
        produto_no_cardapio = next(
            produto
            for produto in db.obter_todos_produtos()
            if produto["id"] == self.produto_id
        )
        self.assertEqual(produto_no_cardapio["estoque"], 0)

        liberacao = db.definir_reserva("carrinho-a", self.produto_id, 7)
        ampliacao = db.definir_reserva("carrinho-b", self.produto_id, 3)

        self.assertTrue(liberacao["sucesso"])
        self.assertTrue(ampliacao["sucesso"])
        self.assertEqual(ampliacao["quantidade_reservada"], 3)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id])[
                self.produto_id
            ],
            0,
        )

    def test_reservas_concorrentes_nao_ultrapassam_o_saldo(self):
        def reservar(indice):
            return db.definir_reserva(
                f"carrinho-concorrente-{indice}",
                self.produto_id,
                1,
            )["quantidade_reservada"]

        with ThreadPoolExecutor(max_workers=20) as executor:
            quantidades = list(executor.map(reservar, range(20)))

        self.assertEqual(sum(quantidades), 10)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id])[
                self.produto_id
            ],
            0,
        )

    def test_pagamento_define_receita_e_fotografa_taxa(self):
        self.assertTrue(
            db.salvar_configuracoes(
                {"taxa_credito": 10, "taxa_debito": 0, "taxa_pix": 0}
            )
        )
        pedido = self.novo_pedido(2, "cartao_credito")
        self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
        inicio, fim = self.periodo_do_pagamento(pedido["id"])

        # Alterar a configuração atual não pode reescrever uma venda passada.
        self.assertTrue(db.salvar_configuracoes({"taxa_credito": 50}))
        fechamento = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        kpis = fechamento["kpis"]
        self.assertEqual(kpis["faturamentoBruto"], 20.0)
        self.assertEqual(kpis["faturamentoLiquido"], 20.0)
        self.assertEqual(kpis["cmv"], 8.0)
        self.assertEqual(kpis["taxasPagamento"], 2.0)
        self.assertEqual(kpis["lucroBruto"], 12.0)
        self.assertEqual(kpis["resultadoOperacional"], 10.0)
        self.assertEqual(sum(fechamento["vendasPorPeriodo"]["data"]), 20.0)
        self.assertEqual(sum(fechamento["vendasPorPagamento"]["data"]), 20.0)

    def test_estorno_integral_e_idempotente(self):
        pedido = self.novo_pedido(2)
        self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
        inicio, fim = self.periodo_do_pagamento(pedido["id"])
        self.assertTrue(db.cancelar_pedido(pedido["id"]))
        self.assertTrue(db.cancelar_pedido(pedido["id"]))

        fechamento = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        kpis = fechamento["kpis"]
        self.assertEqual(kpis["faturamentoBruto"], 20.0)
        self.assertEqual(kpis["estornos"], 20.0)
        self.assertEqual(kpis["faturamentoLiquido"], 0.0)
        self.assertEqual(kpis["cmv"], 0.0)
        self.assertEqual(kpis["resultadoOperacional"], 0.0)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id])[
                self.produto_id
            ],
            10,
        )
        with closing(database.conectar()) as conn:
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM pagamentos
                    WHERE pedido_id = ? AND tipo = 'estorno'
                    """,
                    (pedido["id"],),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    """
                    SELECT SUM(quantidade) FROM estoque_movimentacoes
                    WHERE pedido_id = ?
                    """,
                    (pedido["id"],),
                ).fetchone()[0],
                0,
            )

    def test_perda_reduz_resultado_e_saldo(self):
        pedido = self.novo_pedido(1)
        self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
        self.assertTrue(db.adicionar_estoque(self.produto_id, -2, 0))
        inicio, fim = self.periodo_do_pagamento(pedido["id"])
        fechamento = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        self.assertEqual(fechamento["kpis"]["perdasAjustes"], 8.0)
        self.assertEqual(fechamento["kpis"]["resultadoOperacional"], -2.0)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id])[
                self.produto_id
            ],
            7,
        )

    def test_zeragem_operacional_e_neutra_no_relatorio(self):
        pedido = self.novo_pedido(1)
        self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
        self.assertEqual(
            db.definir_reserva("carrinho-antes-da-zeragem", self.produto_id, 3)[
                "quantidade_reservada"
            ],
            3,
        )
        inicio, fim = self.periodo_do_pagamento(pedido["id"])
        antes = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )

        resultado = db.zerar_estoque_produto(self.produto_id)
        self.assertTrue(resultado["sucesso"])
        self.assertEqual(resultado["quantidade_zerada"], 9)
        self.assertEqual(resultado["valor_zerado"], 36.0)
        self.assertEqual(resultado["reservas_liberadas"], 1)
        self.assertEqual(resultado["saldo"], 0)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id])[
                self.produto_id
            ],
            0,
        )

        depois = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        self.assertEqual(depois["kpis"]["perdasAjustes"], 0)
        self.assertEqual(
            depois["kpis"]["resultadoOperacional"],
            antes["kpis"]["resultadoOperacional"],
        )
        estoque = next(
            item
            for item in depois["estoque"]
            if item["produtoId"] == self.produto_id
        )
        self.assertEqual(
            (estoque["entradas"], estoque["saidas"], estoque["final"]),
            (1, 1, 0),
        )
        with closing(database.conectar()) as conn:
            movimento = conn.execute(
                """
                SELECT tipo, quantidade, impacta_relatorio, observacao
                FROM estoque_movimentacoes
                WHERE produto_id = ? AND impacta_relatorio = 0
                """,
                (self.produto_id,),
            ).fetchone()
            self.assertEqual(movimento["tipo"], "ajuste")
            self.assertEqual(movimento["quantidade"], -9)
            self.assertEqual(movimento["impacta_relatorio"], 0)
            self.assertIn("Zeragem operacional", movimento["observacao"])

        repeticao = db.zerar_estoque_produto(self.produto_id)
        self.assertTrue(repeticao["sucesso"])
        self.assertEqual(repeticao["quantidade_zerada"], 0)

    def test_zeragem_global_inclui_arquivados_e_libera_reservas(self):
        segundo_id = db.adicionar_novo_produto(
            "Produto para zeragem global", None, None, 7.0, 4, 2.5, 1, 0
        )
        self.assertTrue(db.excluir_produto(segundo_id))
        self.assertEqual(
            db.definir_reserva("reserva-global", self.produto_id, 2)[
                "quantidade_reservada"
            ],
            2,
        )

        resultado = db.zerar_todos_estoques()
        self.assertTrue(resultado["sucesso"])
        self.assertEqual(resultado["produtos_zerados"], 2)
        self.assertEqual(resultado["quantidade_zerada"], 14)
        self.assertEqual(resultado["valor_zerado"], 50.0)
        self.assertEqual(resultado["reservas_liberadas"], 1)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([self.produto_id, segundo_id]),
            {self.produto_id: 0, segundo_id: 0},
        )

    def test_analise_por_local_respeita_visitas_e_disponibilidade(self):
        self.assertTrue(db.adicionar_local("Evento Teste"))
        evento_id = next(
            item["id"]
            for item in db.obter_todos_locais()
            if item["nome"] == "Evento Teste"
        )
        produto_zero_id = db.adicionar_novo_produto(
            "Produto sem saída", None, None, 5.0, 5, 1.0, 1, 0
        )
        produto_indisponivel_id = db.adicionar_novo_produto(
            "Produto não levado", None, None, 6.0, 0, 1.0, 1, 0
        )

        operacao_um = db.iniciar_operacao(self.local_id)
        pedido_um = db.salvar_novo_pedido(
            {
                "nome_cliente": "Visita um",
                "itens": [{"id": self.produto_id, "quantidade": 2}],
                "metodo_pagamento": "pix",
                "modalidade": "local",
            },
            self.local_id,
            operacao_um,
        )
        self.assertTrue(db.confirmar_pagamento_pedido(pedido_um["id"]))
        self.assertTrue(db.encerrar_operacao(operacao_um))

        operacao_dois = db.iniciar_operacao(self.local_id)
        self.assertTrue(db.zerar_todos_estoques()["sucesso"])
        self.assertTrue(db.adicionar_estoque(self.produto_id, 4, 4.0))
        self.assertTrue(db.adicionar_estoque(produto_zero_id, 3, 1.0))
        pedido_dois = db.salvar_novo_pedido(
            {
                "nome_cliente": "Visita dois",
                "itens": [{"id": self.produto_id, "quantidade": 4}],
                "metodo_pagamento": "dinheiro",
                "modalidade": "local",
            },
            self.local_id,
            operacao_dois,
        )
        self.assertTrue(db.confirmar_pagamento_pedido(pedido_dois["id"]))
        self.assertTrue(db.encerrar_operacao(operacao_dois))

        self.assertTrue(db.zerar_todos_estoques()["sucesso"])
        self.assertTrue(db.adicionar_estoque(self.produto_id, 2, 4.0))
        operacao_evento = db.iniciar_operacao(evento_id)
        pedido_evento = db.salvar_novo_pedido(
            {
                "nome_cliente": "Evento",
                "itens": [{"id": self.produto_id, "quantidade": 1}],
                "metodo_pagamento": "pix",
                "modalidade": "local",
            },
            evento_id,
            operacao_evento,
        )
        self.assertTrue(db.confirmar_pagamento_pedido(pedido_evento["id"]))
        self.assertTrue(db.encerrar_operacao(operacao_evento))

        dados = analytics.desempenho_locais(
            [self.local_id, evento_id], modo="ultimas", limite=2
        )
        self.assertEqual(len(dados["locais"]), 2)
        loja = next(item for item in dados["locais"] if item["id"] == self.local_id)
        self.assertEqual(loja["visitas"], 2)
        principal = next(
            item
            for item in loja["produtos"]
            if item["produtoId"] == self.produto_id
        )
        self.assertEqual(principal["totalVendido"], 6)
        self.assertEqual(principal["mediaPorVisita"], 3)
        self.assertEqual(principal["visitasDisponivel"], 2)
        self.assertEqual(principal["esgotamentos"], 1)
        self.assertEqual(principal["mediaLevada"], 7)

        sem_saida = next(
            item
            for item in loja["produtos"]
            if item["produtoId"] == produto_zero_id
        )
        self.assertEqual(sem_saida["totalVendido"], 0)
        self.assertEqual(sem_saida["mediaPorVisita"], 0)
        self.assertEqual(sem_saida["visitasDisponivel"], 2)
        self.assertNotIn(
            produto_indisponivel_id,
            {item["produtoId"] for item in loja["produtos"]},
        )

    def test_produto_com_historico_e_apenas_arquivado(self):
        pedido = self.novo_pedido(1)
        self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
        inicio, fim = self.periodo_do_pagamento(pedido["id"])
        self.assertTrue(db.excluir_produto(self.produto_id))
        self.assertEqual(db.obter_todos_produtos_para_gestao(), [])
        fechamento = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        self.assertEqual(fechamento["itens_top"][0]["nome"], "Espeto Teste")
        self.assertEqual(fechamento["estoque"][0]["final"], 9)
        with closing(database.conectar()) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT ativo FROM produtos WHERE id = ?", (self.produto_id,)
                ).fetchone()[0],
                0,
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_painel_decisao_classifica_mix_e_cobertura(self):
        for nome, preco, custo in (
            ("Produto Volume", 20.00, 15.00),
            ("Produto Oportunidade", 15.00, 3.00),
            ("Produto Revisar", 8.00, 7.00),
        ):
            self.assertTrue(
                db.adicionar_novo_produto(
                    nome, None, None, preco, 10, custo, 1, 0
                )
            )
        produtos = {
            produto["nome"]: produto["id"]
            for produto in db.obter_todos_produtos_para_gestao()
        }
        vendas = (
            (self.produto_id, 4),
            (produtos["Produto Volume"], 2),
            (produtos["Produto Oportunidade"], 1),
            (produtos["Produto Revisar"], 1),
        )
        pedidos = []
        for indice, (produto_id, quantidade) in enumerate(vendas):
            pedido = db.salvar_novo_pedido(
                {
                    "nome_cliente": f"Cliente {indice}",
                    "itens": [{"id": produto_id, "quantidade": quantidade}],
                    "metodo_pagamento": "pix",
                    "modalidade": "local",
                    "carrinho_id": f"mix-{indice}",
                },
                self.local_id,
            )
            self.assertTrue(db.confirmar_pagamento_pedido(pedido["id"]))
            pedidos.append(pedido)

        inicio, fim = self.periodo_do_pagamento(pedidos[0]["id"])
        fechamento = analytics.fechamento_operacional_v2(
            inicio, fim, "todos", 1, 50
        )
        classificacoes = {
            item["nome"]: item["classificacao"]
            for item in fechamento["analiseProdutos"]
        }
        self.assertEqual(classificacoes["Espeto Teste"], "estrela")
        self.assertEqual(classificacoes["Produto Volume"], "volume")
        self.assertEqual(classificacoes["Produto Oportunidade"], "oportunidade")
        self.assertEqual(classificacoes["Produto Revisar"], "revisar")
        self.assertEqual(fechamento["kpis"]["unidadesVendidas"], 8)
        self.assertEqual(fechamento["kpis"]["faturamentoLiquido"], 103.0)
        self.assertEqual(fechamento["kpis"]["resultadoOperacional"], 47.0)
        self.assertEqual(fechamento["resumoExecutivo"]["alertasEstoque"], 2)
        self.assertTrue(fechamento["resumoExecutivo"]["insights"])
        self.assertEqual(len(fechamento["desempenhoPorHora"]), 24)
        comparativo = analytics.insights_comparativos_v2(
            inicio,
            fim,
            "2000-01-01T00:00:00+00:00",
            "2000-01-02T00:00:00+00:00",
            {"local_id": "todos"},
        )
        self.assertEqual(comparativo["kpis"]["faturamento"]["A"], 103.0)
        self.assertIn("margem_operacional", comparativo["kpis"])
        self.assertTrue(comparativo["leituras"])
        inicio_semana = datetime.fromisoformat(inicio)
        fechamento_semana = analytics.fechamento_operacional_v2(
            inicio_semana.isoformat(),
            (inicio_semana + timedelta(days=7)).isoformat(),
            "todos",
            1,
            50,
        )
        self.assertEqual(
            fechamento_semana["vendasPorPeriodo"]["granularidade"],
            "dia_operacional",
        )
        self.assertEqual(len(fechamento_semana["vendasPorPeriodo"]["labels"]), 7)
        self.assertEqual(
            sum(fechamento_semana["vendasPorPeriodo"]["data"]), 103.0
        )

    def test_dia_operacional_e_intervalo_final_exclusivo(self):
        inicio, fim = analytics.periodo_operacional("2026-07-29")
        self.assertEqual(inicio, "2026-07-29T08:00:00+00:00")
        self.assertEqual(fim, "2026-07-30T08:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
