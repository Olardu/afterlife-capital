"""Tests de #GR-1+#GR-2: integración en process_signal (gated por ATR_SIZING_ENABLED).

Con el flag OFF (default) el bot opera como siempre (qty del Sentinel, sin TP/SL):
backward compat estricto. Con el flag ON, process_signal dimensiona por ATR
(calculate_position_size), pasa el qty resultante por el CorrelationGuard
(respeta ambas restricciones) y manda una bracket order con TP/SL.

El flag se lee en runtime (`config.ATR_SIZING_ENABLED`) → se mockea con patch.
Mock de todos los colaboradores (sin red ni DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_process_signal_integration.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import Dispatcher

_EAR_OK = {"can_trade": True, "circuit_breaker": False, "parking_brake": False, "risk_score": 0.0}


def _run(coro):
    return asyncio.run(coro)


def _bars_atr_4_50():
    """20 barras planas con rango 4.50 → ATR Wilder = 4.50."""
    return pd.DataFrame({
        "high":  [222.50] * 20,
        "low":   [218.00] * 20,
        "close": [220.00] * 20,
    })


def _guard_echo(*, incoming_ticker, incoming_qty, open_positions, performance_scores):
    """CorrelationGuard que aprueba sin reducir (adjusted = incoming)."""
    return {"approved": True, "adjusted_qty": incoming_qty,
            "avg_correlation": 0.0, "reason": "approved"}


def _disp(*, guard=None):
    d = Dispatcher.__new__(Dispatcher)
    d.kill_switch_active = False
    d.open_positions = {}
    d.regime_classifier = MagicMock()
    d.regime_classifier.get_regime = MagicMock(return_value="NEUTRAL")
    d.correlation_guard = MagicMock()
    d.correlation_guard.evaluate_signal = AsyncMock(
        side_effect=guard if guard is not None else _guard_echo
    )
    d.historian = MagicMock()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[])
    d.historian.record_signal = AsyncMock(return_value=uuid4())
    d.historian.record_trade = AsyncMock(return_value=uuid4())
    d.execute_order = AsyncMock(return_value={
        "status": "FILLED", "filled_price": Decimal("218.00"), "order_id": "o1",
    })
    return d


def _signal(d, *, equity=Decimal("100000")):
    return d.process_signal(
        sentinel_id=uuid4(), owner_id=uuid4(), ticker="NVDA", signal_type="BUY",
        price=Decimal("218.00"), qty=Decimal("1"), strategy_type="macd_volume",
        ear_state=_EAR_OK, allocation={}, account_equity=equity,
    )


# --- Caso 1: flag OFF → backward compat (qty viejo, sin TP/SL) -------------
def test_flag_off_backward_compat_sin_bracket():
    d = _disp()
    with patch("config.ATR_SIZING_ENABLED", False):
        _run(_signal(d))
    _, kwargs = d.execute_order.call_args
    assert kwargs["take_profit_price"] is None
    assert kwargs["stop_loss_price"] is None
    # El branch OFF no setea _fetch_bars_for_atr en el helper; si lo llamara
    # (overhead indebido) sería AttributeError y el test fallaría.


# --- Caso 2: flag ON → sizing ATR + bracket (TP/SL computados) -------------
def test_flag_on_sizing_y_bracket():
    d = _disp()
    d._fetch_bars_for_atr = AsyncMock(return_value=_bars_atr_4_50())
    with patch("config.ATR_SIZING_ENABLED", True):
        _run(_signal(d))
    _, kwargs = d.execute_order.call_args
    # T-X (#FEAT-011): strategy_type=macd_volume → multipliers per-Sentinel
    # sl_mult=2.5, rr_ratio=2.5 (antes defaults globales 2.0/2.0). ATR=4.50:
    # stop_distance=11.25 → SL=218−11.25=206.75; TP=218+11.25×2.5=246.12.
    assert kwargs["take_profit_price"] == Decimal("246.12")
    assert kwargs["stop_loss_price"] == Decimal("206.75")
    assert float(kwargs["qty"]) > 1          # el sizing dimensionó (no el qty=1 viejo)
    assert float(kwargs["qty"]) < 100        # cap MAX_POSITION_PCT domina (~68.8)


# --- Caso 3: flag ON pero ATR no calculable → rechazo, sin orden -----------
def test_flag_on_atr_no_calculable_rechaza():
    d = _disp()
    d._fetch_bars_for_atr = AsyncMock(return_value=None)  # fetch falló
    with patch("config.ATR_SIZING_ENABLED", True):
        res = _run(_signal(d))
    assert res["reason"] == "atr_unavailable"
    d.execute_order.assert_not_awaited()


# --- Caso 4: flag ON + sizing no factible (equity bajo) → rechazo ----------
def test_flag_on_sizing_no_factible_rechaza():
    d = _disp()
    d._fetch_bars_for_atr = AsyncMock(return_value=_bars_atr_4_50())
    with patch("config.ATR_SIZING_ENABLED", True):
        res = _run(_signal(d, equity=Decimal("100")))  # posición < $25 piso
    assert res["reason"] == "sizing_not_feasible"
    d.execute_order.assert_not_awaited()


# --- Caso 5: combo con CorrelationGuard → final_qty respeta ambas ----------
def test_flag_on_combo_correlation_guard_reduce_qty():
    def _guard_reduce(*, incoming_ticker, incoming_qty, open_positions, performance_scores):
        # El guard reduce el qty del sizing por concentración.
        return {"approved": True, "adjusted_qty": Decimal("10"),
                "avg_correlation": 0.80, "reason": "approved"}
    d = _disp(guard=_guard_reduce)
    d._fetch_bars_for_atr = AsyncMock(return_value=_bars_atr_4_50())
    with patch("config.ATR_SIZING_ENABLED", True):
        _run(_signal(d))
    _, kwargs = d.execute_order.call_args
    assert kwargs["qty"] == Decimal("10")            # el guard redujo (respeta correlación)
    # T-X: TP/SL per-Sentinel (macd_volume 2.5/2.5) intactos pese a la reducción de qty
    assert kwargs["take_profit_price"] == Decimal("246.12")
    assert kwargs["stop_loss_price"] == Decimal("206.75")
