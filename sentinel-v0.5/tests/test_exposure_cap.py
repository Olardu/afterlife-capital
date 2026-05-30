"""Tests de #BUG-NEW-4: cap de exposición agregada (anti-margen).

`cap_qty_to_exposure_limit` recorta la qty de una nueva posición para que la
exposición total (capital ya desplegado + nueva posición) no exceda
equity × MAX_ALLOCATION_TOTAL/100 (85%). Garantiza la reserva mínima de cash y
evita que el bot entre en margen (cash negativo) al acumular posiciones — el
path de ATR sizing no pasaba por el cap de allocation, por eso la exposición
llegó a 1.38× el equity el 29-may.

Helper PURO (Decimal, sin red/DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_exposure_cap.py -v
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import cap_qty_to_exposure_limit


# --- Caso 1: la posición entra completa (headroom amplio) → qty sin cambios ---
def test_qty_entra_completa_sin_recorte():
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("0"),
        price=Decimal("100"), qty=Decimal("5"),
    )
    assert qty == Decimal("5")


# --- Caso 2: la posición excede el headroom → se recorta a headroom/price -----
def test_qty_se_recorta_al_headroom():
    # equity 100k, cap 85% = 85k. deployed 84.8k → headroom 200. qty 5 × 100 = 500.
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("84800"),
        price=Decimal("100"), qty=Decimal("5"), is_fractionable=False,
    )
    assert qty == Decimal("2")  # 200 / 100 = 2


# --- Caso 3: ya en o sobre el cap → 0 (no se abre nada) ----------------------
def test_sin_headroom_devuelve_cero():
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("85000"),
        price=Decimal("100"), qty=Decimal("5"),
    )
    assert qty == Decimal("0")


def test_sobre_el_cap_devuelve_cero():
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("90000"),
        price=Decimal("100"), qty=Decimal("5"),
    )
    assert qty == Decimal("0")


# --- Caso 4: inputs inválidos → 0 (defensivo) -------------------------------
def test_equity_cero_devuelve_cero():
    assert cap_qty_to_exposure_limit(
        equity=Decimal("0"), deployed_value=Decimal("0"),
        price=Decimal("100"), qty=Decimal("5"),
    ) == Decimal("0")


def test_price_cero_devuelve_cero():
    assert cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("0"),
        price=Decimal("0"), qty=Decimal("5"),
    ) == Decimal("0")


def test_qty_cero_devuelve_cero():
    assert cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("0"),
        price=Decimal("100"), qty=Decimal("0"),
    ) == Decimal("0")


# --- Caso 5: exactamente en el límite → entra completa -----------------------
def test_proposed_igual_al_headroom_entra_completa():
    # headroom = 85000 - 84500 = 500. qty 5 × 100 = 500 == headroom → entra.
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("84500"),
        price=Decimal("100"), qty=Decimal("5"),
    )
    assert qty == Decimal("5")


# --- Caso 6: fraccional quantiza a 9 decimales hacia abajo -------------------
def test_fraccional_quantiza_nueve_decimales():
    # headroom 250, price 70 → 3.571428... → trunca a 9 decimales.
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("84750"),
        price=Decimal("70"), qty=Decimal("100"), is_fractionable=True,
    )
    assert qty == Decimal("3.571428571")  # 250/70 truncado ROUND_DOWN


# --- Caso 7: respeta un max_total_pct custom --------------------------------
def test_respeta_max_total_pct_custom():
    # cap 50% = 50k. deployed 49.9k → headroom 100. qty 5 × 100 = 500 → 1.
    qty = cap_qty_to_exposure_limit(
        equity=Decimal("100000"), deployed_value=Decimal("49900"),
        price=Decimal("100"), qty=Decimal("5"),
        max_total_pct=Decimal("0.50"), is_fractionable=False,
    )
    assert qty == Decimal("1")
