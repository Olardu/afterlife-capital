"""Tests de #GR-3 (fuente persistente del drawdown): daily_equity_snapshots.

`record_daily_equity_snapshot` registra el equity EOD (idempotente por día, con
peak running). `get_drawdown_equities` devuelve {day_open, week_ago, peak} para
los drawdown limits. Reemplazan el stub fail-safe del Bloque 1 (opción B, tabla DB).

Mock del pool asyncpg (sin DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_daily_equity_snapshots.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian


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


# --- Caso 1: record inserta el snapshot con (owner_id, equity) --------------
def test_record_inserta_snapshot():
    conn = MagicMock()
    conn.execute = AsyncMock()
    h = _historian(conn)
    oid = uuid4()
    _run(h.record_daily_equity_snapshot(oid, Decimal("100000.00")))
    args = conn.execute.call_args[0]
    assert args[1] == oid
    assert args[2] == Decimal("100000.00")


# --- Caso 2: el SQL mantiene el peak (GREATEST + ON CONFLICT) ---------------
def test_record_sql_mantiene_peak():
    conn = MagicMock()
    conn.execute = AsyncMock()
    h = _historian(conn)
    _run(h.record_daily_equity_snapshot(uuid4(), Decimal("95000")))
    sql = conn.execute.call_args[0][0]
    assert "ON CONFLICT" in sql
    # El peak nunca baja: se conserva el mayor entre el previo y el nuevo.
    assert "GREATEST(daily_equity_snapshots.peak_to_date" in sql


# --- Caso 3: day_open usa el snapshot de HOY si existe (no el proxy) --------
def test_get_drawdown_day_open_usa_snapshot_hoy():
    conn = MagicMock()
    # orden de fetchval en get_drawdown_equities: peak, day_open(hoy), week_ago
    conn.fetchval = AsyncMock(side_effect=[
        Decimal("110000"),  # peak
        Decimal("100500"),  # day_open (snapshot de hoy presente)
        Decimal("99000"),   # week_ago
    ])
    h = _historian(conn)
    r = _run(h.get_drawdown_equities(uuid4()))
    assert r["day_open"] == Decimal("100500")   # del snapshot de hoy, no proxy
    assert conn.fetchval.await_count == 3        # no consultó el proxy (4ta query)


# --- Caso 4: get_drawdown_equities calcula los 3 valores --------------------
def test_get_drawdown_tres_valores():
    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=[
        Decimal("110000"),  # peak
        None,               # day_open de hoy ausente → usa proxy
        Decimal("100200"),  # proxy: último equity_close
        Decimal("98000"),   # week_ago
    ])
    h = _historian(conn)
    r = _run(h.get_drawdown_equities(uuid4()))
    assert r == {
        "day_open": Decimal("100200"),  # proxy (último close)
        "week_ago": Decimal("98000"),
        "peak":     Decimal("110000"),
    }
