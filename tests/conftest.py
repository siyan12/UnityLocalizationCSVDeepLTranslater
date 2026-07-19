import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    """Make accidental real API or network access fail every test immediately."""
    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in tests.")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
