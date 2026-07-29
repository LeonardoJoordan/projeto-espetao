import os
import tempfile
import unittest
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
            self.assertIn("pedido_itens", {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            })

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

    def test_pedido_sem_estoque_falha_sem_gravacao_parcial(self):
        self.assertIsNone(self.novo_pedido(11))
        with closing(database.conectar()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0], 0)
            saldo = conn.execute(
                """
                SELECT SUM(quantidade) FROM estoque_movimentacoes
                WHERE produto_id = ?
                """,
                (self.produto_id,),
            ).fetchone()[0]
            self.assertEqual(saldo, 10)

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
