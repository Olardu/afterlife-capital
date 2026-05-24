"""Tests de #GR-2: position sizing por ATR (risk parity) + ATR Wilder.

`calculate_position_size` (dispatcher) dimensiona la posición arriesgando un % fijo
del equity por trade (risk parity), con cap por % de equity (anti-concentración) y
piso en USD (para que los fees no dominen). `_atr` (sentinels) calcula el Average
True Range con suavizado de Wilder. Todo monetario en Decimal (§8.6).

Flag-gated en producción (ATR_SIZING_ENABLED=False default): estos helpers existen
pero NO cambian el comportamiento del bot hasta que el flag se active (Bloque 3).

Correr:  venv\\Scripts\\python.exe -m pytest tests/test_position_sizing.py -v
"""
import os
import sys
from decimal import Decimal

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import calculate_position_size
from sentinels import _atr

_E = Decimal("100000")  # equity de referencia $100K


# =============================================================================
# calculate_position_size
# =============================================================================

# --- Caso 1: sizing puro, cap NO triggea -----------------------------------
def test_sizing_puro_sin_cap():
    r = calculate_position_size(
        ticker="SYN", equity=_E, current_price=Decimal("10.00"),
        atr=Decimal("0.50"),
    )
    assert r is not None
    assert r["qty"] == Decimal("1000")          # 1000/1.00, bajo el cap (1500)
    assert r["capped"] is False
    assert r["stop_price"] == Decimal("9.00")
    assert r["take_profit_price"] == Decimal("12.00")


# --- Caso 2: cap SÍ triggea (NVDA, típico en producción) -------------------
def test_sizing_cap_triggea_nvda():
    r = calculate_position_size(
        ticker="NVDA", equity=_E, current_price=Decimal("218.00"),
        atr=Decimal("4.50"), is_fractionable=False,
    )
    assert r is not None
    assert r["qty"] == Decimal("68")            # min(111, 68.8) → 68 (cap domina)
    assert r["capped"] is True
    assert r["stop_price"] == Decimal("209.00")
    assert r["take_profit_price"] == Decimal("236.00")


# --- Caso 3: XLU también triggea cap ---------------------------------------
def test_sizing_cap_triggea_xlu():
    r = calculate_position_size(
        ticker="XLU", equity=_E, current_price=Decimal("73.00"),
        atr=Decimal("0.60"), is_fractionable=False,
    )
    assert r is not None
    assert r["qty"] == Decimal("205")           # min(833, 205.5) → 205
    assert r["capped"] is True
    assert r["stop_price"] == Decimal("71.80")
    assert r["take_profit_price"] == Decimal("75.40")


# --- Caso 4: piso mínimo USD triggea (equity bajo) → None ------------------
def test_sizing_bajo_piso_minimo_es_none():
    r = calculate_position_size(
        ticker="SYN", equity=Decimal("100"), current_price=Decimal("50.00"),
        atr=Decimal("30.00"),
    )
    assert r is None  # position ≈ $0.83 < MIN_POSITION_USD ($25)


# --- Caso 5: ATR=0 (mercado plano) → None sin división por cero -------------
def test_sizing_atr_cero_es_none():
    r = calculate_position_size(
        ticker="SYN", equity=_E, current_price=Decimal("100.00"),
        atr=Decimal("0"),
    )
    assert r is None


# =============================================================================
# _atr (Wilder)
# =============================================================================

def _bars(highs, lows, closes):
    return pd.DataFrame({"high": highs, "low": lows, "close": closes})


# --- Caso 6: ATR Wilder con bars conocidos → match referencia --------------
def test_atr_wilder_match_referencia():
    # 19 barras planas (TR=2.0 cada una) + 1 barra con salto (TR=16.0).
    # seed = mean(TR[:14]) = 2.0; smoothing hasta idx 18 sigue 2.0;
    # idx 19: (2.0*13 + 16.0) / 14 = 42/14 = 3.0.
    highs  = [11.0] * 19 + [26.0]
    lows   = [9.0] * 19 + [10.0]
    closes = [10.0] * 20
    atr = _atr(_bars(highs, lows, closes), window=14)
    assert abs(atr - 3.0) < 1e-9


def test_atr_bars_insuficientes_es_nan():
    # Menos de `window` barras → no hay seed posible.
    bars = _bars([11.0] * 5, [9.0] * 5, [10.0] * 5)
    atr = _atr(bars, window=14)
    assert atr != atr  # NaN (NaN != NaN)
