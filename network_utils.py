"""Descoberta de IPv4 local sem depender de endereço ou serviço externo."""

from __future__ import annotations

import ipaddress
import socket
import struct
from collections.abc import Iterable


REDES_PRIVADAS = tuple(
    ipaddress.ip_network(rede)
    for rede in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
PREFIXOS_VIRTUAIS = (
    "lo",
    "docker",
    "br-",
    "veth",
    "virbr",
    "vmnet",
    "vboxnet",
    "podman",
    "cni",
    "flannel",
    "tun",
    "tap",
    "wg",
    "tailscale",
    "zt",
)
PREFIXOS_FISICOS = ("en", "eth", "wl", "wlan", "wifi")


def _ipv4_utilizavel(endereco: str) -> bool:
    try:
        ip = ipaddress.ip_address(endereco)
    except ValueError:
        return False
    return (
        ip.version == 4
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_unspecified
    )


def _interface_rota_padrao_linux() -> str | None:
    """Lê a tabela de rotas do kernel; não abre conexão de rede."""
    try:
        with open("/proc/net/route", encoding="ascii") as arquivo:
            next(arquivo, None)
            for linha in arquivo:
                campos = linha.split()
                if len(campos) < 4:
                    continue
                interface, destino, _, flags = campos[:4]
                if destino == "00000000" and int(flags, 16) & 0x1:
                    return interface
    except (OSError, ValueError):
        pass
    return None


def _enderecos_interfaces_linux() -> list[tuple[str, str]]:
    """Obtém os IPv4 configurados diretamente do kernel via ioctl."""
    try:
        import fcntl
    except ImportError:
        return []

    enderecos = []
    try:
        interfaces = socket.if_nameindex()
    except OSError:
        return []

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for _, nome in interfaces:
            try:
                requisicao = struct.pack("256s", nome[:15].encode("utf-8"))
                resposta = fcntl.ioctl(sock.fileno(), 0x8915, requisicao)
                endereco = socket.inet_ntoa(resposta[20:24])
            except (OSError, UnicodeError):
                continue
            if _ipv4_utilizavel(endereco):
                enderecos.append((nome, endereco))
    return enderecos


def _enderecos_interfaces_qt() -> list[tuple[str, str]]:
    """Fallback multiplataforma pela enumeração local oferecida pelo Qt."""
    try:
        from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface
    except ImportError:
        return []

    enderecos = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not flags & QNetworkInterface.InterfaceFlag.IsUp:
            continue
        if flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        for entrada in interface.addressEntries():
            endereco = entrada.ip()
            if (
                endereco.protocol()
                != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol
            ):
                continue
            texto = endereco.toString()
            if _ipv4_utilizavel(texto):
                enderecos.append((interface.name(), texto))
    return enderecos


def escolher_ipv4_local(
    candidatos: Iterable[tuple[str, str]], interface_padrao: str | None = None
) -> str | None:
    """Escolhe a interface mais apropriada para atender dispositivos da LAN."""
    unicos = []
    vistos = set()
    for interface, endereco in candidatos:
        if endereco in vistos or not _ipv4_utilizavel(endereco):
            continue
        vistos.add(endereco)
        unicos.append((str(interface), endereco))
    if not unicos:
        return None

    def prioridade(candidato):
        interface, endereco = candidato
        nome = interface.lower()
        ip = ipaddress.ip_address(endereco)
        virtual = nome.startswith(PREFIXOS_VIRTUAIS)
        fisica = nome.startswith(PREFIXOS_FISICOS)
        privada = any(ip in rede for rede in REDES_PRIVADAS)
        return (
            1 if virtual else 0,
            0 if interface == interface_padrao else 1,
            0 if privada else 1,
            0 if fisica else 1,
            interface,
            endereco,
        )

    return min(unicos, key=prioridade)[1]


def detectar_ipv4_local() -> str | None:
    """Retorna um IPv4 da máquina usando somente informações locais."""
    interface_padrao = _interface_rota_padrao_linux()
    candidatos = _enderecos_interfaces_linux()
    candidatos.extend(_enderecos_interfaces_qt())
    return escolher_ipv4_local(candidatos, interface_padrao)
