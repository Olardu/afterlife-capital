"""Tests de #H-6b (reconciliación automática PENDING_NEW) + #H-4 Decimal en el reconciler.

`reconcile_pending(pool, apply, max_age_minutes, verbose)` cruza trades PENDING_NEW con
Alpaca y los actualiza. Se integra al main_loop como poller cada 5 min (#H-6b). Los
montos (filled_price, slippage) van en Decimal (§8.6, #H-4).

Mock del pool asyncpg + patch de TradingClient (sin red ni DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_reconciler.py -v
"""
import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reconcile_pending_trades
from reconcile_pending_trades import reconcile_pending


def _run(coro):
    return asyncio.run(coro)


def _trade(order_id, ticker="NVDA", side="BUY"):
    return {
        "trade_id": uuid4(), "order_id": order_id, "ticker": ticker, "side": side,
        "qty": 1, "status": "PENDING_NEW", "created_at": datetime(2026, 5, 20),
    }


def _order(oid, status="filled", price="218.34"):
    return SimpleNamespace(id=oid, status=SimpleNamespace(value=status), filled_avg_price=price)


def _pool(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


def _conn(trades, orders, price_at_signal=Decimal("218.50")):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=trades)
    conn.fetchrow = AsyncMock(return_value={"price_at_signal": price_at_signal})
    conn.execute = AsyncMock()
    return conn


def test_dry_run_no_aplica_pero_cuenta_pendientes():
    conn = _conn([_trade("o1"), _trade("o2"), _trade("o3")], [])
    with patch.object(reconcile_pending_trades, "TradingClient") as TC:
        TC.return_value.get_orders.return_value = []
        stats = _run(reconcile_pending(_pool(conn), apply=False, verbose=False))
    assert stats["pending_checked"] == 3
    assert stats["updates_applied"] == 0


def test_apply_actualiza_los_filled():
    trades = [_trade("o1"), _trade("o2")]
    orders = [_order("o1"), _order("o2")]
    conn = _conn(trades, orders)
    with patch.object(reconcile_pending_trades, "TradingClient") as TC:
        TC.return_value.get_orders.return_value = orders
        stats = _run(reconcile_pending(_pool(conn), apply=True, verbose=False))
    assert stats["updates_applied"] == 2
    assert stats["filled"] == 2


def test_filtro_max_age_minutes_en_query():
    conn = _conn([], [])
    with patch.object(reconcile_pending_trades, "TradingClient") as TC:
        TC.return_value.get_orders.return_value = []
        _run(reconcile_pending(_pool(conn), apply=True, max_age_minutes=5, verbose=False))
    sql, param = conn.fetch.await_args.args[0], conn.fetch.await_args.args[1]
    assert "minutes" in sql.lower()
    assert param == "5"


def test_trade_sin_order_id_no_crashea():
    conn = _conn([_trade(None)], [])
    with patch.object(reconcile_pending_trades, "TradingClient") as TC:
        TC.return_value.get_orders.return_value = []
        stats = _run(reconcile_pending(_pool(conn), apply=True, verbose=False))
    assert stats["no_order_id"] == 1
    assert stats["updates_applied"] == 0


def test_order_id_no_existe_en_alpaca_no_crashea():
    conn = _conn([_trade("o-inexistente")], [])
    with patch.object(reconcile_pending_trades, "TradingClient") as TC:
        TC.return_value.get_orders.return_value = [_order("otra-orden")]
        stats = _run(reconcile_pending(_pool(conn), apply=True, verbose=False))
    assert stats["not_found_in_alpaca"] == 1
    assert stats["updates_applied"] == 0


def test_filled_price_y_slippage_son_decimal():
    """#H-4: lo que se persiste (filled_price, slippage) debe ser Decimal, no float."""
    conn = _conn([_trade("o1")], [_order("o1", price="218.34")], price_at_signal=Decimal("218.50"))
    with patch.object(reconcile_pending_trades, "TradingClient") as TC:
        TC.return_value.get_orders.return_value = [_order("o1", price="218.34")]
        _run(reconcile_pending(_pool(conn), apply=True, verbose=False))
    # UPDATE: (sql, new_status, filled_price, slippage, trade_id)
    update_args = conn.execute.await_args.args
    filled_price, slippage = update_args[2], update_args[3]
    assert isinstance(filled_price, Decimal), f"filled_price debe ser Decimal, es {type(filled_price)}"
    assert isinstance(slippage, Decimal), f"slippage debe ser Decimal, es {type(slippage)}"
    assert filled_price == Decimal("218.34")
    assert slippage == Decimal("-0.16")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
