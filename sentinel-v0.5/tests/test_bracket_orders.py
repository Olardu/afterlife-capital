"""Tests de #GR-1: bracket orders (TP/SL automáticos) en execute_order.

`execute_order` / `_submit_order_sync` aceptan `take_profit_price` y
`stop_loss_price` opcionales. Si ambos están presentes → MarketOrderRequest con
order_class=BRACKET + TakeProfitRequest/StopLossRequest. Si ambos None →
comportamiento de hoy (backward compat). Si solo uno → ValueError (bracket es
"both or none", decisión Cowork LOG 04:11).

Precios quantizados a 2 decimales con banker's rounding (ROUND_HALF_EVEN). Flag-
gated en producción: process_signal recién pasa tp/sl con ATR_SIZING_ENABLED (Bloque 3).

Mock del SDK Alpaca (sin red). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_bracket_orders.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpaca.trading.enums import OrderClass
from dispatcher import Dispatcher


def _run(coro):
    return asyncio.run(coro)


def _disp():
    return Dispatcher.__new__(Dispatcher)


def _fake_client(filled="218.0", status="filled", raises=None):
    client = MagicMock()
    if raises is not None:
        client.submit_order = MagicMock(side_effect=raises)
    else:
        client.submit_order = MagicMock(return_value=SimpleNamespace(
            id="oid-1", filled_avg_price=filled, status=SimpleNamespace(value=status),
        ))
    return client


def _order_data(fake_client):
    """El OrderRequest que se pasó a client.submit_order."""
    return fake_client.submit_order.call_args[0][0]


# --- Caso 1: bracket completo (tp + sl) → MarketOrderRequest BRACKET --------
def test_bracket_completo_construye_bracket_order():
    fc = _fake_client()
    with patch("alpaca.trading.client.TradingClient", return_value=fc):
        res = _disp()._submit_order_sync(
            "NVDA", "BUY", 68, "", None,
            Decimal("236.00"), Decimal("209.00"),
        )
    od = _order_data(fc)
    assert od.order_class == OrderClass.BRACKET
    assert float(od.take_profit.limit_price) == 236.00
    assert float(od.stop_loss.stop_price) == 209.00
    assert res["status"] == "FILLED"


# --- Caso 2: sin tp/sl → MarketOrderRequest SIMPLE (backward compat) --------
def test_sin_bracket_construye_market_simple():
    fc = _fake_client()
    with patch("alpaca.trading.client.TradingClient", return_value=fc):
        _disp()._submit_order_sync("SPY", "BUY", 5, "", None)
    od = _order_data(fc)
    assert od.order_class is None  # SIMPLE, sin bracket


# --- Caso 3: quantize a 2 decimales con banker's rounding -------------------
def test_bracket_quantiza_precios_banker_rounding():
    fc = _fake_client()
    with patch("alpaca.trading.client.TradingClient", return_value=fc):
        _disp()._submit_order_sync(
            "SPY", "BUY", 5, "", None,
            Decimal("400.345"), Decimal("300.005"),
        )
    od = _order_data(fc)
    assert float(od.take_profit.limit_price) == 400.34  # 5 con previo par (4) → baja
    assert float(od.stop_loss.stop_price) == 300.00     # 5 con previo par (0) → baja


# --- Caso 4: qty Decimal del sizing se serializa sin romper -----------------
def test_bracket_qty_decimal_se_serializa():
    fc = _fake_client()
    with patch("alpaca.trading.client.TradingClient", return_value=fc):
        _disp()._submit_order_sync(
            "NVDA", "BUY", Decimal("68"), "", None,
            Decimal("236.00"), Decimal("209.00"),
        )
    od = _order_data(fc)
    assert float(od.qty) == 68.0


# --- Caso 5: Alpaca rechaza la orden → manejo limpio (CANCELLED) ------------
def test_execute_order_rechazo_alpaca_retorna_cancelled():
    fc = _fake_client(raises=Exception("not tradable"))
    with patch("alpaca.trading.client.TradingClient", return_value=fc):
        res = _run(_disp().execute_order(
            "SPY", "BUY", Decimal("5"),
            take_profit_price=Decimal("400.00"), stop_loss_price=Decimal("300.00"),
        ))
    assert res["status"] == "CANCELLED"
    assert res["order_id"] is None


# --- Caso 6: solo tp sin sl (xor) → ValueError (bracket es both or none) ----
def test_execute_order_solo_tp_sin_sl_lanza_valueerror():
    with pytest.raises(ValueError):
        _run(_disp().execute_order(
            "SPY", "BUY", Decimal("5"), take_profit_price=Decimal("400.00"),
        ))
