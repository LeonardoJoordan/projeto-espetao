import importlib
import os
import re
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import database
import gerenciador_db as db


class APITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["ESPETAO_DB_PATH"] = os.path.join(cls.temp_dir.name, "api.db")
        database.inicializar_banco()
        cls.modulo_app = importlib.import_module("app")
        db.adicionar_local("Loja API")
        cls.local_id = db.obter_todos_locais()[0]["id"]
        cls.modulo_app.definir_local_sessao(cls.local_id)
        db.adicionar_novo_produto(
            "Produto API", None, None, 12.50, 5, 5.00, 1, 0
        )
        cls.produto_id = db.obter_todos_produtos()[0]["id"]
        cls.client = cls.modulo_app.app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ESPETAO_DB_PATH", None)
        cls.temp_dir.cleanup()

    def test_telas_e_relatorio_vazio(self):
        for rota in ("/cliente", "/cozinha", "/produtos", "/fechamento", "/monitor"):
            resposta = self.client.get(rota)
            self.assertEqual(resposta.status_code, 200, rota)
        resposta = self.client.get(
            "/api/fechamento_dia_v2?data=2000-01-01&local_id=todos"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["kpis"]["faturamentoLiquido"], 0)
        cozinha = self.client.get("/cozinha").get_data(as_text=True)
        self.assertIn('id="modal-pagamento"', cozinha)
        self.assertIn('data-method="cartao_credito"', cozinha)
        self.assertIn('id="pagamento-modal-confirmar"', cozinha)

    def test_fluxo_http_usa_valores_do_servidor(self):
        resposta = self.client.post(
            "/salvar_pedido",
            json={
                "carrinho_id": "api-test",
                "nome_cliente": "Cliente API",
                "itens": [
                    {
                        "id": self.produto_id,
                        "nome": "Nome falso",
                        "preco": 0.01,
                        "quantidade": 1,
                    }
                ],
                "metodo_pagamento": "pix",
                "modalidade": "local",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        pedido = db.obter_pedidos_ativos()[0]
        self.assertEqual(pedido["valor_total"], 12.50)
        self.assertEqual(pedido["itens"][0]["nome"], "Produto API")

        self.assertEqual(
            self.client.post(
                f"/pedido/confirmar_pagamento/{pedido['id']}"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(f"/pedido/entregar_direto/{pedido['id']}").status_code,
            200,
        )
        pago = db.obter_pedido_por_id(pedido["id"])
        dia = (
            datetime.fromisoformat(pago["timestamp_pagamento"])
            .astimezone(ZoneInfo("America/Sao_Paulo"))
            .date()
            .isoformat()
        )
        fechamento = self.client.get(
            f"/api/fechamento_dia_v2?data={dia}&local_id=todos"
        )
        self.assertEqual(fechamento.status_code, 200)
        self.assertEqual(fechamento.json["kpis"]["faturamentoLiquido"], 12.50)
        self.assertEqual(fechamento.json["kpis"]["cmv"], 5.00)
        self.assertEqual(fechamento.json["kpis"]["unidadesVendidas"], 1)
        self.assertEqual(
            fechamento.json["analiseProdutos"][0]["frequenciaEstrelas"], 5
        )
        self.assertNotIn(
            "classificacao", fechamento.json["analiseProdutos"][0]
        )
        self.assertTrue(fechamento.json["resumoExecutivo"]["insights"])
        self.assertEqual(len(fechamento.json["desempenhoPorHora"]), 24)
        locais = self.client.get(
            f"/api/insights/locais?local_ids={self.local_id}&amostra=historico"
        )
        self.assertEqual(locais.status_code, 200)
        self.assertEqual(locais.json["locais"][0]["visitas"], 1)
        self.assertEqual(
            locais.json["locais"][0]["produtos"][0]["mediaPorVisita"], 1
        )

    def test_produto_pode_ocultar_e_reaparecer_quando_esgotado(self):
        resposta = self.client.post(
            "/adicionar_produto",
            data={
                "nome_produto": "Produto Ocultável",
                "descricao": "Visibilidade automática",
                "categoria_produto": "1",
                "preco_venda": "9.00",
                "preco_compra": "3.00",
                "quantidade": "0",
                "ocultar_quando_esgotado": "on",
            },
        )
        self.assertEqual(resposta.status_code, 302)

        produto = next(
            item
            for item in db.obter_todos_produtos_para_gestao()
            if item["nome"] == "Produto Ocultável"
        )
        self.assertEqual(produto["ocultar_quando_esgotado"], 1)

        html_esgotado = self.client.get("/cliente").get_data(as_text=True)
        card_esgotado = re.search(
            rf'<div class="([^"]*product-card[^"]*)"[^>]*data-id="{produto["id"]}"'
            rf'[^>]*data-ocultar-quando-esgotado="1"',
            html_esgotado,
        )
        self.assertIsNotNone(card_esgotado)
        self.assertIn("catalog-hidden", card_esgotado.group(1))

        self.assertTrue(db.adicionar_estoque(produto["id"], 1, 3.00))
        html_disponivel = self.client.get("/cliente").get_data(as_text=True)
        card_disponivel = re.search(
            rf'<div class="([^"]*product-card[^"]*)"[^>]*data-id="{produto["id"]}"',
            html_disponivel,
        )
        self.assertIsNotNone(card_disponivel)
        self.assertNotIn("catalog-hidden", card_disponivel.group(1))

        resposta_edicao = self.client.post(
            "/adicionar_produto",
            data={
                "id_produto": str(produto["id"]),
                "nome_produto": "Produto Ocultável",
                "descricao": "Visibilidade automática",
                "categoria_produto": "1",
                "preco_venda": "9.00",
                "foto_url_antiga": "",
            },
        )
        self.assertEqual(resposta_edicao.status_code, 302)
        atualizado = next(
            item
            for item in db.obter_todos_produtos_para_gestao()
            if item["id"] == produto["id"]
        )
        self.assertEqual(atualizado["ocultar_quando_esgotado"], 0)

    def test_modal_separa_cadastro_edicao_e_movimentacoes_fifo(self):
        pagina = self.client.get("/produtos").get_data(as_text=True)
        self.assertIn('id="btn-novo-produto"', pagina)
        self.assertIn('id="modal-produto"', pagina)
        self.assertIn('id="modal-estoque"', pagina)
        self.assertIn('class="btn-estoque icon-btn is-info"', pagina)
        self.assertIn('id="btn-zerar-estoques"', pagina)

        relatorio = self.client.get("/fechamento").get_data(as_text=True)
        self.assertIn('data-section="locations"', relatorio)
        self.assertIn('id="location-products-table"', relatorio)
        self.assertIn('id="chart-location-hours"', relatorio)
        self.assertIn('class="category-toggle"', relatorio)
        self.assertIn('id="sales-context"', relatorio)
        self.assertIn('class="frequency-heading"', relatorio)
        self.assertIn('frequencyCell(item)', relatorio)

        criacao = self.client.post(
            "/api/produtos",
            data={
                "nome_produto": "Produto Modal",
                "descricao": "Criado sem estoque",
                "categoria_produto": "1",
                "preco_venda": "7.50",
                "ocultar_quando_esgotado": "on",
            },
        )
        self.assertEqual(criacao.status_code, 201)
        produto_id = criacao.json["produto_id"]
        produto = db.obter_produto_para_gestao(produto_id)
        self.assertEqual(produto["estoque"], 0)
        self.assertEqual(produto["ocultar_quando_esgotado"], 1)
        self.assertEqual(db.obter_lotes_produto(produto_id), [])

        edicao = self.client.post(
            f"/api/produtos/{produto_id}",
            data={
                "nome_produto": "Produto Modal",
                "descricao": "Apenas dados cadastrais",
                "categoria_produto": "1",
                "preco_venda": "7.50",
                "requer_preparo": "on",
            },
        )
        self.assertEqual(edicao.status_code, 200)
        atualizado = db.obter_produto_para_gestao(produto_id)
        self.assertEqual(atualizado["descricao"], "Apenas dados cadastrais")
        self.assertEqual(atualizado["requer_preparo"], 1)
        self.assertEqual(atualizado["ocultar_quando_esgotado"], 0)
        self.assertEqual(db.obter_lotes_produto(produto_id), [])

        entrada = self.client.post(
            f"/api/produtos/{produto_id}/estoque/entradas",
            json={
                "quantidade": 5,
                "custo_unitario": 2.25,
                "observacao": "Compra de teste",
            },
        )
        self.assertEqual(entrada.status_code, 200)
        self.assertEqual(entrada.json["saldo"], 5)

        perda = self.client.post(
            f"/api/produtos/{produto_id}/estoque/perdas",
            json={"quantidade": 2, "motivo": "Teste de perda"},
        )
        self.assertEqual(perda.status_code, 200)
        self.assertEqual(perda.json["saldo"], 3)
        self.assertEqual(perda.json["custo_total"], 4.50)

    def test_api_define_quantidade_total_sem_somar_reenvios(self):
        self.assertTrue(
            db.adicionar_novo_produto(
                "Produto Reserva API", None, None, 8.00, 5, 3.00, 1, 0
            )
        )
        produto_id = next(
            produto["id"]
            for produto in db.obter_todos_produtos_para_gestao()
            if produto["nome"] == "Produto Reserva API"
        )
        payload = {
            "carrinho_id": "reserva-api",
            "produto_id": produto_id,
            "quantidade_desejada": 3,
        }

        primeira = self.client.post("/api/carrinho/item", json=payload)
        repetida = self.client.post("/api/carrinho/item", json=payload)

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(repetida.status_code, 200)
        self.assertEqual(primeira.json["quantidade_reservada"], 3)
        self.assertEqual(repetida.json["quantidade_reservada"], 3)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([produto_id])[produto_id],
            2,
        )

        segundo_carrinho = self.client.post(
            "/api/carrinho/item",
            json={
                **payload,
                "carrinho_id": "reserva-api-b",
                "quantidade_desejada": 3,
            },
        )
        self.assertTrue(segundo_carrinho.json["ajustada"])
        self.assertEqual(segundo_carrinho.json["quantidade_reservada"], 2)

        liberacao = self.client.post(
            "/api/carrinho/item",
            json={
                **payload,
                "quantidade_desejada": 2,
            },
        )
        self.assertEqual(liberacao.status_code, 200)
        self.assertEqual(liberacao.json["quantidade_reservada"], 2)
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([produto_id])[produto_id],
            1,
        )

        ampliacao = self.client.post(
            "/api/carrinho/item",
            json={
                **payload,
                "carrinho_id": "reserva-api-b",
                "quantidade_desejada": 3,
            },
        )
        self.assertTrue(ampliacao.json["sucesso"])
        self.assertEqual(ampliacao.json["quantidade_reservada"], 3)

        for carrinho_id in ("reserva-api", "reserva-api-b"):
            self.client.post(
                "/api/carrinho/item",
                json={
                    **payload,
                    "carrinho_id": carrinho_id,
                    "quantidade_desejada": 0,
                },
            )
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([produto_id])[produto_id],
            5,
        )

    def test_zeragem_http_individual_e_global(self):
        produto_id = db.adicionar_novo_produto(
            "Produto Zeragem HTTP", None, None, 9.00, 6, 3.00, 1, 0
        )
        self.assertEqual(
            db.definir_reserva("zeragem-http", produto_id, 2)[
                "quantidade_reservada"
            ],
            2,
        )

        individual = self.client.post(
            f"/api/produtos/{produto_id}/estoque/zerar"
        )
        self.assertEqual(individual.status_code, 200)
        self.assertEqual(individual.json["quantidade_zerada"], 6)
        self.assertEqual(individual.json["valor_zerado"], 18.0)
        self.assertEqual(individual.json["saldo"], 0)

        outro_id = db.adicionar_novo_produto(
            "Produto Zeragem Global HTTP", None, None, 5.00, 3, 2.00, 1, 0
        )
        resumo = self.client.get("/api/produtos/estoque/resumo-zeragem")
        self.assertEqual(resumo.status_code, 200)
        self.assertGreaterEqual(resumo.json["quantidade_zerada"], 3)

        global_ = self.client.post("/api/produtos/estoque/zerar")
        self.assertEqual(global_.status_code, 200)
        self.assertEqual(
            global_.json["quantidade_zerada"],
            resumo.json["quantidade_zerada"],
        )
        self.assertEqual(
            db.obter_disponibilidade_para_produtos([produto_id, outro_id]),
            {produto_id: 0, outro_id: 0},
        )


if __name__ == "__main__":
    unittest.main()
