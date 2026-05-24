"""Tests T-O #ME-3 — desglose de señales de hoy por destino.

historian._bucket_signal_rows (pura) clasifica el status del trade más reciente
de cada signal en {filled, cancelled, pending, no_trade}.
historian.get_signals_breakdown_today corre la query (subquery LIMIT 1 por signal,
filtrada a HOY + owner) y delega el conteo al bucket.

Mock del pool asyncpg (sin DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_signals_breakdown.py -v
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian, _bucket_signal_rows


def _run(coro):
    return asyncio.run(coro)


def _historian(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    h = Historian.__new__(Historian)
    h.pool = pool
    return h


def _rows(*statuses):
    """Filas tipo asyncpg Record (acceso por clave) a partir de los status."""
    return [{"trade_status": s} for s in statuses]


# --- _bucket_signal_rows: clasificación pura --------------------------------
def test_bucket_vacio():
    assert _bucket_signal_rows([]) == {
        "filled": 0, "cancelled": 0, "pending": 0, "no_trade": 0,
    }


def test_bucket_cuenta_cada_categoria():
    rows = _rows("FILLED", "FILLED", "CANCELLED", None, "PENDING")
    assert _bucket_signal_rows(rows) == {
        "filled": 2, "cancelled": 1, "pending": 1, "no_trade": 1,
    }


def test_bucket_estados_intermedios_son_pending():
    # Cualquier status no FILLED/CANCELLED y no nulo cae en pending
    # (PENDING_NEW, ACCEPTED, NEW, ... — Alpaca usa varios).
    rows = _rows("PENDING_NEW", "ACCEPTED", "NEW")
    out = _bucket_signal_rows(rows)
    assert out["pending"] == 3
    assert out["filled"] == 0 and out["cancelled"] == 0 and out["no_trade"] == 0


def test_bucket_none_es_no_trade():
    # Señales sin trade (descartadas por kill_switch/can_trade/CorrelationGuard).
    assert _bucket_signal_rows(_rows(None, None, None))["no_trade"] == 3


# --- get_signals_breakdown_today: query + bucket ----------------------------
def test_breakdown_today_devuelve_conteo():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows("FILLED", None, "CANCELLED", "FILLED"))
    h = _historian(conn)
    out = _run(h.get_signals_breakdown_today(uuid4()))
    assert out == {"filled": 2, "cancelled": 1, "pending": 0, "no_trade": 1}


def test_breakdown_today_filtra_hoy_y_owner():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    h = _historian(conn)
    oid = uuid4()
    _run(h.get_signals_breakdown_today(oid))
    sql = conn.fetch.call_args[0][0]
    assert "CURRENT_DATE" in sql          # corte por día de mercado ET
    assert "owner_id = $1" in sql         # multi-tenant
    assert "LIMIT 1" in sql               # status del trade más reciente por signal
    assert conn.fetch.call_args[0][1] == oid


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
