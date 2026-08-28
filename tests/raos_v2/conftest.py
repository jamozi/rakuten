"""RAOS V2-only deny-by-default network boundary for normal pytest runs."""

from __future__ import annotations

import socket
from typing import Any

import pytest


_REAL_SOCKET = socket.socket
_NETWORK_FAMILIES = {socket.AF_INET, socket.AF_INET6}
_DENIED = "RAOS_V2_TEST_NETWORK_DENIED"


def _deny_network_socket(
    family: socket.AddressFamily = socket.AF_INET,
    type: socket.SocketKind = socket.SOCK_STREAM,
    proto: int = 0,
    fileno: int | None = None,
) -> socket.socket:
    if family in _NETWORK_FAMILIES:
        raise RuntimeError(_DENIED)
    return _REAL_SOCKET(family, type, proto, fileno)


def _deny_network_call(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError(_DENIED)


@pytest.fixture(autouse=True)
def _raos_v2_network_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject Internet sockets and DNS only inside ``tests/raos_v2``."""

    monkeypatch.setattr(socket, "socket", _deny_network_socket)
    monkeypatch.setattr(socket, "create_connection", _deny_network_call)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network_call)
    monkeypatch.setattr(socket, "gethostbyname", _deny_network_call)
    monkeypatch.setattr(socket, "gethostbyname_ex", _deny_network_call)
    monkeypatch.setattr(socket, "gethostbyaddr", _deny_network_call)
