"""Tests del fix #H-4: `CorrelationGuard.evaluate_signal` opera la qty en Decimal.

Path crítico (BUENAS_PRACTICAS_V2 §8.6): la qty es monetaria → Decimal en todo el
pipeline. Antes `evaluate_signal` mezclaba float (qty) con Decimal del dispatcher,
rompiendo el sizing. El fix: signature `incoming_qty: Decimal` + conversión defensiva
(acepta callers que aún pasen float durante la migración gradual) + returns en Decimal.

`avg_correlation` y `reduction_factor` quedan float a propósito (ratios adimensionales,
§8.6). `calculate_correlation` (Pearson) no se toca.

Correr:  venv\\Scripts\\python.exe -m pytest tests/test_correlation_guard_decimal.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from correlation_guard import CorrelationGuard


def _run(coro):
    return asyncio.run(coro)


def _guard_con_correlacion(valor: float) -> CorrelationGuard:
    """CorrelationGuard con fetch_bars y calculate_correlation mockeados para
    forzar un `avg_correlation` determinístico, sin pegarle a Alpaca."""
    guard = CorrelationGuard()

    async def _fake_fetch(tickers, window):
        return {t: [1.0, 2.0, 3.0] for t in tickers}

    guard.fetch_bars = _fake_fetch
    guard.calculate_correlation = lambda prices_a, prices_b: valor
    return guard


_POS_AMD = [{"ticker": "AMD", "qty": 1, "sentinel_id": "s-test"}]


def test_sin_posiciones_aprueba_con_qty_decimal_intacta():
    """Sin posiciones abiertas → aprueba y devuelve la qty Decimal sin tocar."""
    resultado = _run(CorrelationGuard().evaluate_signal("NVDA", Decimal("10"), [], []))
    assert resultado["adjusted_qty"] == Decimal("10")
    assert isinstance(resultado["adjusted_qty"], Decimal)


def test_caller_pasa_float_no_crashea_y_devuelve_decimal():
    """Conversión defensiva: un caller que aún pasa float no rompe y sale Decimal."""
    resultado = _run(CorrelationGuard().evaluate_signal("NVDA", 10.0, [], []))
    assert isinstance(resultado["adjusted_qty"], Decimal)
    assert resultado["adjusted_qty"] == Decimal("10.0")


def test_correlacion_alta_reduce_qty_y_la_devuelve_decimal():
    """avg_correlation > threshold pero qty reducida ≥ MIN → reduced, Decimal, < original."""
    guard = _guard_con_correlacion(0.875)  # reduction_factor = 0.5
    resultado = _run(guard.evaluate_signal("NVDA", Decimal("10"), _POS_AMD, []))
    assert resultado["reason"] == "reduced"
    assert isinstance(resultado["adjusted_qty"], Decimal)
    assert resultado["adjusted_qty"] < Decimal("10")


def test_correlacion_muy_alta_descarta_con_qty_cero_decimal():
    """qty reducida < MIN_POSITION_SIZE → descarta, approved=False, adjusted_qty=Decimal('0')."""
    guard = _guard_con_correlacion(0.99)  # reduction_factor ≈ 0.04 → adjusted < 1
    resultado = _run(guard.evaluate_signal("NVDA", Decimal("1"), _POS_AMD, []))
    assert resultado["approved"] is False
    assert resultado["adjusted_qty"] == Decimal("0")
    assert isinstance(resultado["adjusted_qty"], Decimal)


def test_adjusted_qty_siempre_es_decimal():
    """Invariante de tipo: el return siempre trae adjusted_qty como Decimal."""
    resultado = _run(CorrelationGuard().evaluate_signal("NVDA", Decimal("5"), [], []))
    assert isinstance(resultado["adjusted_qty"], Decimal)
