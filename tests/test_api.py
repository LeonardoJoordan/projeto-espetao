import importlib
import os
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
            fechamento.json["analiseProdutos"][0]["classificacao"], "estrela"
        )
        self.assertTrue(fechamento.json["resumoExecutivo"]["insights"])
        self.assertEqual(len(fechamento.json["desempenhoPorHora"]), 24)


if __name__ == "__main__":
    unittest.main()
