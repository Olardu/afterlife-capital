"""Tests T-V Sub-3 — Wilder RSI smoothing (flag WILDER_RSI_ENABLED).

Verifica que con el flag ON, _rsi() usa el smoothing de Wilder (RMA = EWMA con
alpha=1/period) y que coincide con el cálculo recursivo manual (ε=0.001); con el
flag OFF mantiene el SMA-smoothing histórico.

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_rsi_wilder.py -v
"""
import math
import os
import sys
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from sentinels import _rsi  # noqa: E402


def _last(closes, period):
    return float(_rsi(pd.Series(closes), period).iloc[-1])


def _rma_manual_rsi(closes, period):
    """RSI de referencia: RMA recursivo (Wilder/pandas_ta) sobre gains/losses."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    a = 1.0 / period
    ag, al = gains[0], losses[0]
    for g, ln in zip(gains[1:], losses[1:]):
        ag = ag * (1 - a) + g * a
        al = al * (1 - a) + ln * a
    al = al if al != 0 else 1e-10
    rs = ag / al
    return 100 - (100 / (1 + rs))


_PRICES = [100, 101, 102, 101, 103, 104, 103, 105, 106, 105,
           107, 108, 107, 109, 110, 109, 111, 112, 111, 113]


def test_flag_off_usa_sma_smoothing():
    # Comportamiento legacy: rolling mean (SMA). Distinto del Wilder.
    with patch.object(config, "WILDER_RSI_ENABLED", False):
        sma = _last(_PRICES, 14)
    with patch.object(config, "WILDER_RSI_ENABLED", True):
        wilder = _last(_PRICES, 14)
    assert abs(sma - wilder) > 0.01   # el flag cambia el método


def test_wilder_coincide_con_rma_manual():
    with patch.object(config, "WILDER_RSI_ENABLED", True):
        got = _last(_PRICES, 14)
    expected = _rma_manual_rsi(_PRICES, 14)
    assert abs(got - expected) < 0.001


def test_wilder_period_2_coincide_con_manual():
    with patch.object(config, "WILDER_RSI_ENABLED", True):
        got = _last(_PRICES, 2)
    expected = _rma_manual_rsi(_PRICES, 2)
    assert abs(got - expected) < 0.001


def test_wilder_monotona_creciente_rsi_alto():
    closes = list(range(100, 140))   # estrictamente creciente
    with patch.object(config, "WILDER_RSI_ENABLED", True):
        rsi = _last(closes, 14)
    assert rsi > 99.0   # sin pérdidas → RSI ≈ 100


def test_wilder_monotona_decreciente_rsi_bajo():
    closes = list(range(140, 100, -1))   # estrictamente decreciente
    with patch.object(config, "WILDER_RSI_ENABLED", True):
        rsi = _last(closes, 14)
    assert rsi < 1.0   # sin ganancias → RSI ≈ 0


def test_wilder_rsi_en_rango_valido():
    with patch.object(config, "WILDER_RSI_ENABLED", True):
        rsi = _last(_PRICES, 14)
    assert 0.0 <= rsi <= 100.0 and not math.isnan(rsi)
