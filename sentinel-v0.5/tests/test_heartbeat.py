"""Tests T-O #OP-2 — heartbeat externo (healthchecks.io) en main._send_heartbeat.

El ping es best-effort: flag-gated por HEARTBEAT_URL, no bloquea ni rompe el
ciclo. Un fallo de red se loggea como warning y NO se propaga.

Mock de aiohttp (sin red). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_heartbeat.py -v
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


def _run(coro):
    return asyncio.run(coro)


class _FakeSession:
    """ClientSession falsa: async CM cuyo .get() devuelve una corutina que o
    bien resuelve OK o bien levanta la excepción configurada."""

    def __init__(self, get_behavior):
        self._get_behavior = get_behavior  # "ok" o una Exception
        self.get_called_with = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url):
        self.get_called_with = url
        behavior = self._get_behavior

        async def _coro():
            if isinstance(behavior, Exception):
                raise behavior
            return MagicMock()  # respuesta simulada

        return _coro()


# --- Gate: sin HEARTBEAT_URL no se hace ningún ping --------------------------
def test_heartbeat_deshabilitado_no_pinguea():
    with patch.object(main, "HEARTBEAT_URL", ""), \
         patch.object(main, "aiohttp") as mock_aiohttp:
        _run(main._send_heartbeat())
    mock_aiohttp.ClientSession.assert_not_called()


# --- Éxito: ping OK no levanta y usa la URL configurada ----------------------
def test_heartbeat_exito_no_levanta():
    session = _FakeSession("ok")
    with patch.object(main, "HEARTBEAT_URL", "https://hc-ping.com/fake"), \
         patch.object(main, "aiohttp") as mock_aiohttp:
        mock_aiohttp.ClientSession = lambda: session
        _run(main._send_heartbeat())  # no debe levantar
    assert session.get_called_with == "https://hc-ping.com/fake"


# --- Fallo de red: se captura, loggea warning y NO se propaga ----------------
def test_heartbeat_fallo_no_propaga():
    session = _FakeSession(ConnectionError("boom"))
    with patch.object(main, "HEARTBEAT_URL", "https://hc-ping.com/fake"), \
         patch.object(main, "aiohttp") as mock_aiohttp, \
         patch.object(main, "logger") as mock_logger:
        mock_aiohttp.ClientSession = lambda: session
        _run(main._send_heartbeat())  # no debe levantar pese al error
        assert mock_logger.warning.called


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
