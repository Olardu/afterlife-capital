"""Tests T-P #FASE2-NEW-4 — market_clock (cobertura → 95%, módulo sin tests).

Las helpers internas (_is_trading_day, _classify, _next_regular_open,
_today_regular_close) son puras dado un datetime ET → se testean directo.
get_market_status() usa datetime.now() → se congela con una subclase de datetime.

Fechas de referencia (2026):
  - Mar 2026-05-26: trading day normal.
  - Sáb 2026-05-23 / Dom 2026-05-24: fin de semana.
  - Lun 2026-05-25: Memorial Day (holiday en _NYSE_HOLIDAYS).

Correr: venv\\Scripts\\python.exe -m pytest tests/test_market_clock.py -v
"""
import os
import sys
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import market_clock
from market_clock import (
    _classify,
    _is_trading_day,
    _next_regular_open,
    _today_regular_close,
    get_market_status,
)

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


# --- _is_trading_day --------------------------------------------------------
def test_is_trading_day_weekday():
    assert _is_trading_day(_et(2026, 5, 26).date()) is True   # martes


def test_is_trading_day_sabado():
    assert _is_trading_day(_et(2026, 5, 23).date()) is False


def test_is_trading_day_domingo():
    assert _is_trading_day(_et(2026, 5, 24).date()) is False


def test_is_trading_day_holiday():
    assert _is_trading_day(_et(2026, 5, 25).date()) is False   # Memorial Day


# --- _classify (todas las ramas en un trading day) --------------------------
def test_classify_no_trading_day_es_closed():
    assert _classify(_et(2026, 5, 25, 10, 0)) == "CLOSED"      # holiday


def test_classify_antes_de_premarket():
    assert _classify(_et(2026, 5, 26, 3, 0)) == "CLOSED"       # < 04:00


def test_classify_premarket():
    assert _classify(_et(2026, 5, 26, 5, 0)) == "PRE_MARKET"   # 04:00–09:30


def test_classify_open():
    assert _classify(_et(2026, 5, 26, 10, 0)) == "OPEN"        # 09:30–16:00


def test_classify_after_hours():
    assert _classify(_et(2026, 5, 26, 16, 30)) == "AFTER_HOURS"  # 16:00–20:00


def test_classify_despues_after_hours():
    assert _classify(_et(2026, 5, 26, 20, 30)) == "CLOSED"     # >= 20:00


# --- _next_regular_open -----------------------------------------------------
def test_next_open_hoy_si_antes_de_apertura():
    r = _next_regular_open(_et(2026, 5, 26, 8, 0))
    assert r == _et(2026, 5, 26, 9, 30)


def test_next_open_salta_finde_y_holiday():
    # Viernes 22 post-cierre → salta sáb 23, dom 24, Memorial lun 25 → mar 26.
    r = _next_regular_open(_et(2026, 5, 22, 17, 0))
    assert r == _et(2026, 5, 26, 9, 30)


def test_next_open_durante_sesion_va_al_dia_siguiente():
    # Ya pasó la apertura de hoy (martes 26) → próxima es miércoles 27.
    r = _next_regular_open(_et(2026, 5, 26, 10, 0))
    assert r == _et(2026, 5, 27, 9, 30)


# --- _today_regular_close ---------------------------------------------------
def test_today_close_antes_del_cierre():
    assert _today_regular_close(_et(2026, 5, 26, 10, 0)) == _et(2026, 5, 26, 16, 0)


def test_today_close_despues_del_cierre_es_none():
    assert _today_regular_close(_et(2026, 5, 26, 17, 0)) is None


def test_today_close_no_trading_day_es_none():
    assert _today_regular_close(_et(2026, 5, 25, 10, 0)) is None   # holiday


# --- get_market_status (con datetime congelado) -----------------------------
class _Frozen(datetime):
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now


def _freeze(dt):
    _Frozen._now = dt
    return patch.object(market_clock, "datetime", _Frozen)


def test_status_open():
    with _freeze(_et(2026, 5, 26, 10, 0)):
        s = get_market_status()
    assert s["is_open"] is True
    assert s["status"] == "OPEN"
    assert s["next_close"] is not None     # cierre de hoy
    assert s["next_open"] is None          # no se calcula si está abierto


def test_status_closed_calcula_next_open():
    # Domingo 24: cerrado; próxima apertura salta el holiday del lunes 25 → mar 26.
    with _freeze(_et(2026, 5, 24, 10, 0)):
        s = get_market_status()
    assert s["is_open"] is False
    assert s["status"] == "CLOSED"
    assert s["next_open"] is not None
    assert s["next_open"].startswith("2026-05-26T09:30")
    assert s["next_close"] is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
