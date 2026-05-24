"""Tests #TECHDEBT-NEW-2 / EXP-003: persistencia del output de CorrelationGuard.

record_signal() ahora acepta 4 columnas nuevas (avg_correlation_at_decision,
original_qty, adjusted_qty, reduction_factor) y las incluye en el INSERT a
signals. Antes el output del risk manager solo quedaba en logs → no auditable.

Estos tests verifican que los valores pasados llegan al INSERT en la posición
correcta, que aceptan None (caso edge / backward compat) y que callers viejos
(sin los 4 params) siguen funcionando.

Rojo→verde: con el código viejo, record_signal NO aceptaba estos kwargs →
Casos 1-4 darían TypeError. Caso 5 (sin kwargs) pasaba en ambos.

Mock del pool asyncpg (sin DB real). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_correlation_guard_persistence.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian


def _run(coro):
    return asyncio.run(coro)


def _historian_con_conn(conn) -> Historian:
    historian = Historian.__new__(Historian)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    historian.pool = pool
    return historian


def _record(**extra):
    """Llama record_signal con base mínima + kwargs extra. Devuelve (resultado, sid, args_del_insert)."""
    conn = MagicMock()
    sid = uuid4()
    conn.fetchrow = AsyncMock(return_value={"signal_id": sid})
    h = _historian_con_conn(conn)
    base = dict(
        sentinel_id=uuid4(), owner_id=uuid4(), ticker="SPY",
        signal_type="BUY", price_at_signal=Decimal("100"),
    )
    base.update(extra)
    resultado = _run(h.record_signal(**base))
    # args del INSERT: (sql, sentinel_id, owner_id, ticker, signal_type, price,
    #                   avg_corr[6], original[7], adjusted[8], reduction[9])
    return resultado, sid, conn.fetchrow.await_args.args


# Caso 1 — Señal pasa intacta: reduction_factor=1.0, original==adjusted.
def test_persiste_signal_intacta():
    res, sid, args = _record(
        avg_correlation_at_decision=0.30,
        original_qty=Decimal("10"), adjusted_qty=Decimal("10"),
        reduction_factor=Decimal("1.0"),
    )
    assert res == sid
    assert args[6] == Decimal("0.3")     # avg_correlation_at_decision (→Decimal)
    assert args[7] == Decimal("10")      # original_qty
    assert args[8] == Decimal("10")      # adjusted_qty
    assert args[9] == Decimal("1.0")     # reduction_factor


# Caso 2 — Señal reducida: factor<1, original≠adjusted.
def test_persiste_signal_reducida():
    _, _, args = _record(
        avg_correlation_at_decision=0.85,
        original_qty=Decimal("10"), adjusted_qty=Decimal("6"),
        reduction_factor=Decimal("0.6"),
    )
    assert args[7] == Decimal("10")
    assert args[8] == Decimal("6")
    assert args[9] == Decimal("0.6")


# Caso 3 — Señal descartada: adjusted=0, factor=0.
def test_persiste_signal_descartada():
    _, _, args = _record(
        avg_correlation_at_decision=0.92,
        original_qty=Decimal("10"), adjusted_qty=Decimal("0"),
        reduction_factor=Decimal("0"),
    )
    assert args[6] == Decimal("0.92")
    assert args[8] == Decimal("0")
    assert args[9] == Decimal("0")


# Caso 4 — Edge sin CorrelationGuard (primera señal): avg_corr None, factor neutro.
def test_persiste_caso_edge_sin_guard():
    _, _, args = _record(
        avg_correlation_at_decision=None,
        original_qty=Decimal("10"), adjusted_qty=Decimal("10"),
        reduction_factor=Decimal("1.0"),
    )
    assert args[6] is None               # NULL en DB
    assert args[9] == Decimal("1.0")


# Caso 5 — Backward compat: caller viejo sin los 4 params → todo NULL, sin crashear.
def test_backward_compat_sin_columnas_nuevas():
    res, sid, args = _record()           # solo los 5 params originales
    assert res == sid
    assert args[6] is None
    assert args[7] is None
    assert args[8] is None
    assert args[9] is None


# Conversión defensiva: acepta float y lo persiste como Decimal.
def test_convierte_float_a_decimal():
    _, _, args = _record(
        avg_correlation_at_decision=0.5, original_qty=10.0,
        adjusted_qty=7.5, reduction_factor=0.75,
    )
    assert all(isinstance(args[i], Decimal) for i in (6, 7, 8, 9))
    assert args[8] == Decimal("7.5")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
