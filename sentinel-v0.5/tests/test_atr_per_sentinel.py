"""Tests T-X (#FEAT-011) — multipliers ATR per-Sentinel (Opción B).

Verifica:
- `config.get_atr_multipliers_for_strategy` devuelve el par correcto por cada
  strategy_type y hace fallback a los defaults globales si no figura.
- `dispatcher.calculate_position_size` con esos overrides produce los stop/TP
  esperados (matemática per-Sentinel).
- El dict `ATR_PER_SENTINEL` cubre exactamente los 9 strategy_types del bot.

Justificación de cada par: docs/TAREA_T-X_tpsl_per_sentinel.md §1.
Correr: venv\\Scripts\\python.exe -m pytest tests/test_atr_per_sentinel.py -v
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    ATR_PER_SENTINEL,
    ATR_STOP_MULTIPLIER,
    RR_RATIO_TAKE_PROFIT,
    get_atr_multipliers_for_strategy,
)
from dispatcher import calculate_position_size

# (strategy_type, sl_mult, rr_ratio) — tabla de la spec §2
_EXPECTED = [
    ("sma_crossover",     Decimal("2.0"), Decimal("3.0")),
    ("rsi_short",         Decimal("1.5"), Decimal("1.0")),
    ("bollinger_bounce",  Decimal("2.0"), Decimal("1.5")),
    ("macd_volume",       Decimal("2.5"), Decimal("2.5")),
    ("orb_breakout",      Decimal("1.0"), Decimal("2.0")),
    ("ema_triple",        Decimal("2.0"), Decimal("3.0")),
    ("vwap_reversion",    Decimal("1.0"), Decimal("1.0")),
    ("rsi_divergence",    Decimal("2.0"), Decimal("2.0")),
    ("bollinger_squeeze", Decimal("1.5"), Decimal("3.0")),
]


# --- helper: override por strategy_type --------------------------------------
@pytest.mark.parametrize("strat,sl,rr", _EXPECTED)
def test_get_atr_multipliers_override(strat, sl, rr):
    m = get_atr_multipliers_for_strategy(strat)
    assert m["sl_mult"] == sl
    assert m["rr_ratio"] == rr


# --- helper: fallback a defaults globales ------------------------------------
def test_get_atr_multipliers_unknown_falls_back():
    m = get_atr_multipliers_for_strategy("desconocido")
    assert m["sl_mult"] == ATR_STOP_MULTIPLIER
    assert m["rr_ratio"] == RR_RATIO_TAKE_PROFIT


def test_get_atr_multipliers_empty_falls_back():
    # strategy_type vacío (process_signal default "") → defaults globales
    m = get_atr_multipliers_for_strategy("")
    assert m["sl_mult"] == ATR_STOP_MULTIPLIER
    assert m["rr_ratio"] == RR_RATIO_TAKE_PROFIT


def test_atr_per_sentinel_cubre_los_9_strategy_types():
    assert set(ATR_PER_SENTINEL) == {s for s, _, _ in _EXPECTED}
    assert len(ATR_PER_SENTINEL) == 9


# --- integración con calculate_position_size ---------------------------------
# price=100, atr=2 → stop_distance = 2×sl_mult; stop=100−sd; tp=100+sd×rr_ratio
@pytest.mark.parametrize("strat,sl,rr", _EXPECTED)
def test_sizing_per_sentinel(strat, sl, rr):
    m = get_atr_multipliers_for_strategy(strat)
    sizing = calculate_position_size(
        ticker="TEST",
        equity=Decimal("100000"),
        current_price=Decimal("100"),
        atr=Decimal("2"),
        atr_multiplier=m["sl_mult"],
        rr_ratio=m["rr_ratio"],
    )
    assert sizing is not None
    stop_distance = Decimal("2") * sl
    exp_stop = (Decimal("100") - stop_distance).quantize(Decimal("0.01"))
    exp_tp = (Decimal("100") + stop_distance * rr).quantize(Decimal("0.01"))
    assert sizing["stop_price"] == exp_stop
    assert sizing["take_profit_price"] == exp_tp


def test_sizing_unknown_usa_defaults_globales():
    # un strategy_type fuera del dict cae a SL=2.0/RR=2.0 → stop 96, tp 108
    m = get_atr_multipliers_for_strategy("unknown")
    sizing = calculate_position_size(
        ticker="TEST", equity=Decimal("100000"), current_price=Decimal("100"),
        atr=Decimal("2"), atr_multiplier=m["sl_mult"], rr_ratio=m["rr_ratio"],
    )
    assert sizing["stop_price"] == Decimal("96.00")
    assert sizing["take_profit_price"] == Decimal("108.00")


def test_multipliers_son_decimal():
    # §8.6: los multipliers son Decimal (no float) para no contaminar el cálculo
    for strat, _, _ in _EXPECTED:
        m = get_atr_multipliers_for_strategy(strat)
        assert isinstance(m["sl_mult"], Decimal)
        assert isinstance(m["rr_ratio"], Decimal)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
