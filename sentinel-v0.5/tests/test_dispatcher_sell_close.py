"""Tests TDD #BUG-SELL-BRACKET (P0, 09-jun-2026).

Un SELL en v0.5 es SIEMPRE cierre/reducción de un long (long-only; el gate
no_open_position ya rechaza SELL sin posición). Dos defectos detectados en
vivo (19 órdenes SELL rechazadas por Alpaca el 08/09-jun, código 42210000
"take_profit.limit_price must be < stop_loss.stop_price"):

1. El ATR sizing calcula TP/SL con fórmulas de LONG (SL bajo el precio, TP
   arriba) y process_signal los adjuntaba al SELL → bracket SELL inválido
   para Alpaca (exige TP < SL). Fix: el SELL va SIN bracket.
2. La qty del SELL viene del sizing (ATR o allocation) y puede exceder la
   posición abierta → flip a short no intencional. Fix: cap a la posición.

Correr: venv\\Scripts\\python.exe -m pytest tests/test_dispatcher_sell_close.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import Dispatcher


@pytest.fixture(autouse=True)
def _atr_sizing_off():
    """#TECH-004: default determinista (el .env local puede tener ATR=true).
    Los tests que necesitan el path ATR lo encienden explícitamente."""
    with patch("config.ATR_SIZING_ENABLED", False):
        yield


_EAR_OK = {"can_trade": True, "circuit_breaker": False, "parking_brake": False, "risk_score": 0.0}


def _run(coro):
    return asyncio.run(coro)


def _guard_echo(*, incoming_ticker, incoming_qty, open_positions, performance_scores, signal_type="BUY"):
    return {"approved": True, "original_qty": incoming_qty, "adjusted_qty": incoming_qty,
            "avg_correlation": 0.0, "reason": "approved"}


def _disp():
    d = Dispatcher.__new__(Dispatcher)
    d.kill_switch_active = False
    d.open_positions = {}
    d.owner_id = uuid4()
    d.regime_classifier = MagicMock()
    d.regime_classifier.get_regime = MagicMock(return_value="NEUTRAL")
    d.the_ear = MagicMock()
    d.the_ear.evaluate = AsyncMock(return_value=dict(_EAR_OK))
    d.correlation_guard = MagicMock()
    d.correlation_guard.evaluate_signal = AsyncMock(side_effect=_guard_echo)
    d.historian = MagicMock()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[])
    d.historian.record_signal = AsyncMock(return_value=uuid4())
    d.historian.record_trade = AsyncMock(return_value=uuid4())
    d.historian.record_shadow_fractional = AsyncMock()
    d.execute_order = AsyncMock(return_value={
        "status": "FILLED", "filled_price": Decimal("100.00"), "order_id": "o1"})
    return d


def _signal(d, **over):
    kw = dict(
        sentinel_id=uuid4(), owner_id=d.owner_id, ticker="NVDA", signal_type="SELL",
        price=Decimal("100.00"), qty=Decimal("5"), strategy_type="macd_volume",
        ear_state=dict(_EAR_OK), allocation={}, account_equity=Decimal("100000"),
    )
    kw.update(over)
    return d.process_signal(**kw)


def _hold(d, ticker="NVDA", qty="50"):
    d.open_positions[ticker] = {
        "ticker": ticker, "qty": Decimal(qty), "side": "BUY", "sentinel_id": None}


def _atr_on():
    """Enciende el path ATR con _atr mockeado (sin red); el sizing real corre."""
    return [patch("config.ATR_SIZING_ENABLED", True),
            patch("sentinels._atr", return_value=2.0)]


# ─── 1. SELL sin bracket (causa del rechazo 42210000) ───────────────────────

def test_sell_con_atr_va_sin_bracket():
    d = _disp()
    _hold(d, qty="50")
    d._fetch_bars_for_atr = AsyncMock(return_value=MagicMock())
    p1, p2 = _atr_on()
    with p1, p2:
        res = _run(_signal(d))
    assert res["approved"] is True
    kw = d.execute_order.await_args.kwargs
    assert kw["take_profit_price"] is None
    assert kw["stop_loss_price"] is None


def test_buy_con_atr_mantiene_bracket():
    # Regresión: el fix NO debe sacarle el bracket al BUY (protección TP/SL).
    d = _disp()
    d._fetch_bars_for_atr = AsyncMock(return_value=MagicMock())
    p1, p2 = _atr_on()
    with p1, p2:
        res = _run(_signal(d, signal_type="BUY"))
    assert res["approved"] is True
    kw = d.execute_order.await_args.kwargs
    assert kw["take_profit_price"] is not None
    assert kw["stop_loss_price"] is not None
    assert kw["stop_loss_price"] < kw["take_profit_price"]   # forma LONG


# ─── 2. Cap de qty a la posición abierta (anti flip-a-short) ─────────────────

def test_sell_qty_se_capea_a_la_posicion():
    d = _disp()
    _hold(d, qty="10")
    res = _run(_signal(d, qty=Decimal("30")))
    assert res["approved"] is True
    assert d.execute_order.await_args.kwargs["qty"] == Decimal("10")


def test_sell_qty_menor_que_posicion_no_cambia():
    d = _disp()
    _hold(d, qty="50")
    res = _run(_signal(d, qty=Decimal("5")))
    assert res["approved"] is True
    assert d.execute_order.await_args.kwargs["qty"] == Decimal("5")


def test_sell_con_atr_capea_a_la_posicion():
    # Caso real XLB: sizing ATR (~150 acá) > held → debe salir held completo.
    d = _disp()
    _hold(d, qty="50")
    d._fetch_bars_for_atr = AsyncMock(return_value=MagicMock())
    p1, p2 = _atr_on()
    with p1, p2:
        res = _run(_signal(d))
    assert res["approved"] is True
    assert d.execute_order.await_args.kwargs["qty"] == Decimal("50")


def test_sell_posicion_sin_qty_valida_rechazada():
    # Posición cacheada con qty 0/negativa (short) → no hay long que cerrar.
    d = _disp()
    _hold(d, qty="0")
    res = _run(_signal(d, qty=Decimal("5")))
    assert res["approved"] is False
    assert res["reason"] == "no_open_position"
    d.execute_order.assert_not_awaited()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
