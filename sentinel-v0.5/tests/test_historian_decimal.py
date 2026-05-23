"""Tests del fix #H-4 en historian.py: dinero en Decimal por todo el pipeline.

Paths críticos (BUENAS_PRACTICAS_V2 §8.6): precios, qty, slippage y costo USD son
monetarios → Decimal. Antes se mezclaba float (params + `float(row[...])`) con el
Decimal que devuelve asyncpg para columnas NUMERIC, lo que rompía el cálculo de
slippage (`Decimal - float` → TypeError) y perdía precisión en returns.

`win_rate` y `sharpe_ratio` quedan float a propósito (ratios adimensionales, §8.6):
el cálculo de `returns` se hace en Decimal y se convierte a float al final.

Mock del pool asyncpg (sin DB real). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_historian_decimal.py -v
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


def _historian_con_conn(conn) -> Historian:
    """Historian con un pool mockeado cuyo `acquire()` entrega `conn` (bypass __init__)."""
    historian = Historian.__new__(Historian)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    historian.pool = pool
    return historian


def test_record_signal_con_decimal_persiste_sin_crashear():
    conn = MagicMock()
    sig_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"signal_id": sig_id})
    historian = _historian_con_conn(conn)

    resultado = _run(historian.record_signal(uuid4(), uuid4(), "SPY", "BUY", Decimal("712.50")))

    assert resultado == sig_id


def test_record_signal_acepta_float_del_caller_sin_crashear():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"signal_id": uuid4()})
    historian = _historian_con_conn(conn)

    _run(historian.record_signal(uuid4(), uuid4(), "SPY", "BUY", 712.50))  # float → conversión defensiva


def test_record_trade_con_decimal_persiste_sin_crashear():
    conn = MagicMock()
    trade_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"trade_id": trade_id})
    historian = _historian_con_conn(conn)

    resultado = _run(historian.record_trade(
        signal_id=uuid4(), sentinel_id=uuid4(), owner_id=uuid4(), ticker="NVDA",
        side="BUY", qty=Decimal("100"), filled_price=Decimal("218.34"),
        slippage=None, status="FILLED",
    ))

    assert resultado == trade_id


def test_update_trade_status_calcula_slippage_decimal_sin_perdida():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"price_at_signal": Decimal("712.50")})
    conn.execute = AsyncMock()
    historian = _historian_con_conn(conn)

    _run(historian.update_trade_status(
        order_id="o-1", status="FILLED", filled_price=Decimal("712.35"),
    ))

    # El slippage es el 4º arg posicional del UPDATE: (sql, status, filled_price, slippage, where)
    slippage = conn.execute.await_args.args[3]
    assert slippage == Decimal("-0.15")
    assert isinstance(slippage, Decimal)


def test_calculate_performance_win_rate_float_y_preciso():
    rows = [
        {"side": "BUY",  "filled_price": Decimal("100"), "created_at": 1},
        {"side": "SELL", "filled_price": Decimal("110"), "created_at": 2},
        {"side": "BUY",  "filled_price": Decimal("100"), "created_at": 3},
        {"side": "SELL", "filled_price": Decimal("90"),  "created_at": 4},
    ]
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    historian = _historian_con_conn(conn)

    resultado = _run(historian.calculate_performance(uuid4(), "NVDA"))

    assert resultado["total_trades"] == 2
    assert resultado["win_rate"] == 0.5            # 1 de 2 ciclos ganadores
    assert isinstance(resultado["win_rate"], float)


def test_calculate_performance_sharpe_sigue_siendo_float():
    rows = [
        {"side": "BUY",  "filled_price": Decimal("100"), "created_at": 1},
        {"side": "SELL", "filled_price": Decimal("110"), "created_at": 2},
        {"side": "BUY",  "filled_price": Decimal("100"), "created_at": 3},
        {"side": "SELL", "filled_price": Decimal("121"), "created_at": 4},
    ]
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    historian = _historian_con_conn(conn)

    resultado = _run(historian.calculate_performance(uuid4(), "NVDA"))

    assert isinstance(resultado["sharpe_ratio"], float)
    assert isinstance(resultado["win_rate"], float)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
