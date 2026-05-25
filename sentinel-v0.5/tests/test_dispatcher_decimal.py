"""Tests del fix #H-4 en dispatcher.py: dinero en Decimal por todo el pipeline.

Paths críticos (BUENAS_PRACTICAS_V2 §8.6): price, qty, account_equity, filled_price y
equity son monetarios → Decimal. Antes se mezclaba el Decimal del resto del pipeline
con float (params + `float(p.qty)` + `account_equity * (alloc/100.0)`), lo que rompía
el sizing (`Decimal * float` → TypeError) y perdía precisión en equity/filled_price.

sharpe/win_rate/ratios siguen float (§8.6). `allocate_capital` NO se toca (ya fixed
en 6a427c5). Mock del SDK Alpaca y de los colaboradores (sin red ni DB).

Correr:  venv\\Scripts\\python.exe -m pytest tests/test_dispatcher_decimal.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import Dispatcher


@pytest.fixture(autouse=True)
def _atr_sizing_off():
    """#TECH-004: estos tests asumen ATR_SIZING_ENABLED=False (process_signal sin
    el path ATR, que construye clients Alpaca reales). El .env de Roman lo tiene en
    true (pre-martes); sin este override heredarían el entorno y fallarían local.
    El CI (sin .env) ya corre con el default False."""
    with patch("config.ATR_SIZING_ENABLED", False):
        yield


def _run(coro):
    return asyncio.run(coro)


# --- Caso 1: _get_alpaca_positions ---------------------------------------------
def test_get_alpaca_positions_qty_es_decimal():
    pos = SimpleNamespace(symbol="NVDA", qty="100")  # Alpaca devuelve qty como string
    fake_client = MagicMock()
    fake_client.get_all_positions = MagicMock(return_value=[pos])
    dispatcher = Dispatcher.__new__(Dispatcher)

    with patch("alpaca.trading.client.TradingClient", return_value=fake_client):
        resultado = dispatcher._get_alpaca_positions()

    assert resultado["NVDA"]["qty"] == Decimal("100")
    assert isinstance(resultado["NVDA"]["qty"], Decimal)
    assert resultado["NVDA"]["side"] == "BUY"


# --- Helper para process_signal -------------------------------------------------
def _dispatcher_para_signal():
    d = Dispatcher.__new__(Dispatcher)
    d.kill_switch_active = False
    d.open_positions = {}
    d.regime_classifier = MagicMock()
    d.regime_classifier.get_regime = MagicMock(return_value="NEUTRAL")
    d.correlation_guard = MagicMock()
    d.correlation_guard.evaluate_signal = AsyncMock(return_value={
        "approved": True, "adjusted_qty": Decimal("5"),
        "original_qty": Decimal("5"), "avg_correlation": 0.0, "reason": "approved",
    })
    d.historian = MagicMock()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[])
    d.historian.record_signal = AsyncMock(return_value=uuid4())
    d.historian.record_trade = AsyncMock(return_value=uuid4())
    d.execute_order = AsyncMock(return_value={
        "status": "FILLED", "filled_price": Decimal("100"), "order_id": "o-1",
    })
    return d


_EAR_OK = {"can_trade": True, "circuit_breaker": False, "parking_brake": False, "risk_score": 0.1}


def _process(d, *, price, qty, account_equity, sentinel_id):
    return _run(d.process_signal(
        sentinel_id=sentinel_id, owner_id=uuid4(), ticker="NVDA", signal_type="BUY",
        price=price, qty=qty, strategy_type="sma_crossover",
        ear_state=_EAR_OK, allocation={str(sentinel_id): 15.0}, account_equity=account_equity,
    ))


def test_process_signal_acepta_decimal_sin_crashear():
    d = _dispatcher_para_signal()
    sid = uuid4()
    resultado = _process(d, price=Decimal("100"), qty=Decimal("10"),
                         account_equity=Decimal("50000"), sentinel_id=sid)
    assert resultado["approved"] is True


def test_process_signal_acepta_float_del_caller_sin_crashear():
    d = _dispatcher_para_signal()
    sid = uuid4()
    resultado = _process(d, price=100.0, qty=10.0,
                         account_equity=50000.0, sentinel_id=sid)  # floats → conversión defensiva
    assert resultado["approved"] is True


def test_process_signal_max_dollar_value_decimal_exacto():
    """alloc 15% de 100k = 15000; max_qty = 15000/100 = 150; qty=min(1000,150)=150,
    todo en Decimal sin TypeError. Se verifica el qty clampeado que llega a CorrelationGuard."""
    d = _dispatcher_para_signal()
    sid = uuid4()
    _process(d, price=Decimal("100"), qty=Decimal("1000"),
             account_equity=Decimal("100000"), sentinel_id=sid)
    incoming_qty = d.correlation_guard.evaluate_signal.await_args.kwargs["incoming_qty"]
    assert incoming_qty == Decimal("150")
    assert isinstance(incoming_qty, Decimal)


# --- Caso 5: _submit_order_sync acepta Decimal ----------------------------------
def test_submit_order_sync_acepta_decimal_sin_crashear():
    fake_order = SimpleNamespace(
        id="abc-123",
        filled_avg_price="218.34",
        status=SimpleNamespace(value="filled"),
    )
    fake_client = MagicMock()
    fake_client.submit_order = MagicMock(return_value=fake_order)
    dispatcher = Dispatcher.__new__(Dispatcher)

    with patch("alpaca.trading.client.TradingClient", return_value=fake_client):
        resultado = dispatcher._submit_order_sync(
            ticker="NVDA", side="BUY", qty=Decimal("10"),
            strategy_type="rsi_short", limit_price=Decimal("218.50"),
        )

    assert resultado["status"] == "FILLED"
    assert resultado["filled_price"] == Decimal("218.34")
    assert isinstance(resultado["filled_price"], Decimal)


# --- Caso 6: _get_account_equity ------------------------------------------------
def test_get_account_equity_retorna_decimal_exacto():
    fake_account = SimpleNamespace(equity="100143.45")
    fake_client = MagicMock()
    fake_client.get_account = MagicMock(return_value=fake_account)
    dispatcher = Dispatcher.__new__(Dispatcher)

    with patch("alpaca.trading.client.TradingClient", return_value=fake_client):
        equity = dispatcher._get_account_equity()

    assert equity == Decimal("100143.45")
    assert isinstance(equity, Decimal)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
