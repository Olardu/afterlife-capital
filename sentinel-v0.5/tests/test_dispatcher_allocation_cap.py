"""Tests de #GR-4: cap de allocation total al MAX_ALLOCATION_TOTAL (85%).

`Dispatcher._cap_allocation(allocation)` escala las allocations por Sentinel para
que su suma no exceda MAX_ALLOCATION_TOTAL, dejando >= 15% del equity en cash
(fees, slippage, gaps, oportunidades asimétricas). Si la suma ya está bajo el cap,
las devuelve sin cambios.

Dispatcher.__new__ sin __init__ (no toca DB ni Alpaca). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_dispatcher_allocation_cap.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MAX_ALLOCATION_TOTAL
from dispatcher import Dispatcher

_EPS = 1e-6


def _disp():
    return Dispatcher.__new__(Dispatcher)


# --- Caso 1: bajo cap (70%) → no escala ------------------------------------
def test_bajo_cap_no_escala():
    alloc = {"a": 25.0, "b": 25.0, "c": 20.0}  # 70%
    assert _disp()._cap_allocation(alloc) == alloc


# --- Caso 2: 95% → escala a 85% --------------------------------------------
def test_sobre_cap_escala_a_85():
    out = _disp()._cap_allocation({"a": 50.0, "b": 45.0})  # 95%
    assert abs(sum(out.values()) - MAX_ALLOCATION_TOTAL) < _EPS


# --- Caso 3: exactamente 85% → no escala (borderline, > cap es False) ------
def test_exacto_85_no_escala():
    alloc = {"a": 60.0, "b": 25.0}  # 85%
    assert _disp()._cap_allocation(alloc) == alloc


# --- Caso 4: fallback 9×5% = 45% → no escala -------------------------------
def test_fallback_45_no_escala():
    alloc = {f"s{i}": 5.0 for i in range(9)}  # 45%
    assert _disp()._cap_allocation(alloc) == alloc


# --- Caso 5: extremo 120% → escala a 85% (factor más agresivo) -------------
def test_extremo_120_escala_a_85():
    alloc = {"a": 25.0, "b": 25.0, "c": 25.0, "d": 25.0, "e": 20.0}  # 120%
    out = _disp()._cap_allocation(alloc)
    assert abs(sum(out.values()) - MAX_ALLOCATION_TOTAL) < _EPS
    # cada peso se escala por el mismo factor (proporción preservada)
    factor = MAX_ALLOCATION_TOTAL / 120.0
    assert abs(out["a"] - 25.0 * factor) < _EPS
