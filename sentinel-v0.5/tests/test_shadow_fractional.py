"""Tests EXP-005 (T-K): Modo Observador Fractional.

El bot opera IDÉNTICO (qty entera). Con SHADOW_FRACTIONAL_ENABLED=true, al final de
process_signal el dispatcher calcula qué HABRÍA operado con fractional (final_qty
pre-floor) vs lo real (floor(final_qty), que es lo que execute_order manda a Alpaca)
y persiste el delta en signals_shadow_fractional via historian.record_shadow_fractional.
NO altera ninguna orden enviada a Alpaca.

Rojo→verde: con el código viejo (sin el bloque shadow ni record_shadow_fractional),
los casos 1-2 fallan (record_shadow_fractional nunca se llama / no existe el método).

Mock de los colaboradores (sin red ni DB). Patrón tomado de test_dispatcher_decimal.py.
Correr:  venv\\Scripts\\python.exe -m pytest tests/test_shadow_fractional.py -v
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


def _run(coro):
    return asyncio.run(coro)


_EAR_OK = {"can_trade": True, "circuit_breaker": False, "parking_brake": False, "risk_score": 0.1}


def _dispatcher(adjusted_qty: Decimal, *, shadow_raises: bool = False) -> Dispatcher:
    """Dispatcher con colaboradores mockeados. final_qty == adjusted_qty del guard."""
    d = Dispatcher.__new__(Dispatcher)
    d.kill_switch_active = False
    d.open_positions = {}
    d.regime_classifier = MagicMock()
    d.regime_classifier.get_regime = MagicMock(return_value="NEUTRAL")
    d.correlation_guard = MagicMock()
    d.correlation_guard.evaluate_signal = AsyncMock(return_value={
        "approved": True, "adjusted_qty": adjusted_qty,
        "original_qty": adjusted_qty, "avg_correlation": 0.0, "reason": "approved",
    })
    d.historian = MagicMock()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[])
    d.historian.record_signal = AsyncMock(return_value=uuid4())
    d.historian.record_trade = AsyncMock(return_value=uuid4())
    if shadow_raises:
        d.historian.record_shadow_fractional = AsyncMock(side_effect=RuntimeError("boom DB"))
    else:
        d.historian.record_shadow_fractional = AsyncMock()
    d.execute_order = AsyncMock(return_value={
        "status": "FILLED", "filled_price": Decimal("100"), "order_id": "o-1",
    })
    return d


def _process(d, *, price, account_equity, sid):
    return _run(d.process_signal(
        sentinel_id=sid, owner_id=uuid4(), ticker="NVDA", signal_type="BUY",
        price=price, qty=Decimal("999"), strategy_type="sma_crossover",
        ear_state=_EAR_OK, allocation={str(sid): 15.0}, account_equity=account_equity,
    ))


# Caso (a) — matched: final_qty entero (floor no cambia nada) → diff < $1.
def test_shadow_matched():
    d = _dispatcher(Decimal("150"))
    sid = uuid4()
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        _process(d, price=Decimal("100"), account_equity=Decimal("100000"), sid=sid)
    d.historian.record_shadow_fractional.assert_awaited_once()
    kw = d.historian.record_shadow_fractional.await_args.kwargs
    assert kw["status"] == "matched"
    assert kw["qty_real_executed"] == Decimal("150")
    assert kw["qty_fractional_would"] == Decimal("150")
    assert kw["dollar_diff"] == Decimal("0")


# Caso (b) — signal_lost_to_int_floor: final_qty fraccional <1 → floor=0, frac>0.
def test_shadow_signal_lost_to_int_floor():
    d = _dispatcher(Decimal("0.5"))
    sid = uuid4()
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        _process(d, price=Decimal("100"), account_equity=Decimal("100000"), sid=sid)
    d.historian.record_shadow_fractional.assert_awaited_once()
    kw = d.historian.record_shadow_fractional.await_args.kwargs
    assert kw["status"] == "signal_lost_to_int_floor"
    assert kw["qty_real_executed"] == Decimal("0")
    assert kw["qty_fractional_would"] == Decimal("0.5")
    assert kw["notional_fractional_would"] == Decimal("50.0")
    assert kw["dollar_diff"] == Decimal("50.0")


# Caso (c) — el shadow NO debe romper el flow: si record_shadow_fractional lanza,
# process_signal devuelve aprobado normal (la excepción se loguea y no propaga).
def test_shadow_falla_no_propaga():
    d = _dispatcher(Decimal("150"), shadow_raises=True)
    sid = uuid4()
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        resultado = _process(d, price=Decimal("100"), account_equity=Decimal("100000"), sid=sid)
    assert resultado["approved"] is True            # flow intacto pese al fallo del shadow
    d.historian.record_shadow_fractional.assert_awaited_once()


# Caso (d) — flag OFF: no se intenta el shadow en absoluto.
def test_shadow_flag_off_no_registra():
    d = _dispatcher(Decimal("0.5"))
    sid = uuid4()
    with patch("config.SHADOW_FRACTIONAL_ENABLED", False):
        resultado = _process(d, price=Decimal("100"), account_equity=Decimal("100000"), sid=sid)
    assert resultado["approved"] is True
    d.historian.record_shadow_fractional.assert_not_awaited()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
