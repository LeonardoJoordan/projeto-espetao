import unittest
from unittest.mock import patch

import network_utils


class NetworkUtilsTestCase(unittest.TestCase):
    def test_prioriza_interface_fisica_da_rota_padrao(self):
        candidatos = [
            ("wlan0", "192.168.1.30"),
            ("eth0", "192.168.1.20"),
        ]
        self.assertEqual(
            network_utils.escolher_ipv4_local(candidatos, "eth0"),
            "192.168.1.20",
        )

    def test_evitar_interface_virtual_quando_existe_fisica(self):
        candidatos = [
            ("docker0", "172.17.0.1"),
            ("tailscale0", "100.90.80.70"),
            ("wlp2s0", "192.168.0.42"),
        ]
        self.assertEqual(
            network_utils.escolher_ipv4_local(candidatos, "docker0"),
            "192.168.0.42",
        )

    def test_usa_interface_virtual_se_for_a_unica_disponivel(self):
        self.assertEqual(
            network_utils.escolher_ipv4_local(
                [("tailscale0", "100.90.80.70")], "tailscale0"
            ),
            "100.90.80.70",
        )

    def test_ignora_loopback_link_local_e_endereco_invalido(self):
        candidatos = [
            ("lo", "127.0.0.1"),
            ("eth0", "169.254.10.20"),
            ("eth1", "endereco-invalido"),
        ]
        self.assertIsNone(network_utils.escolher_ipv4_local(candidatos))

    @patch("network_utils._enderecos_interfaces_qt", return_value=[])
    @patch(
        "network_utils._enderecos_interfaces_linux",
        return_value=[("enp3s0", "192.168.10.15")],
    )
    @patch("network_utils._interface_rota_padrao_linux", return_value="enp3s0")
    def test_deteccao_usa_somente_fontes_locais(
        self, rota_mock, linux_mock, qt_mock
    ):
        self.assertEqual(network_utils.detectar_ipv4_local(), "192.168.10.15")
        rota_mock.assert_called_once_with()
        linux_mock.assert_called_once_with()
        qt_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
