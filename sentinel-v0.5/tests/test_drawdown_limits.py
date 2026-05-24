"""Tests de #GR-3: límites de drawdown del portafolio (diario/semanal/acumulado).

`_evaluate_drawdown_levels(current, day_open, week_ago, peak)` aplica los 3
umbrales y devuelve el nivel más grave superado (cumulative > weekly > daily).
`_check_portfolio_drawdown` es flag-gated (PORTFOLIO_DD_LIMITS_ENABLED). La
obtención del equity histórico está pendiente de diseño (stub fail-safe).

Lógica pura testeable sin red. Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_drawdown_limits.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import Dispatcher


def _run(coro):
    return asyncio.run(coro)


def _D(x):
    return Decimal(str(x)) if x is not None else None


def _ev(current, day_open=None, week_ago=None, peak=None):
    return Dispatcher._evaluate_drawdown_levels(_D(current), _D(day_open), _D(week_ago), _D(peak))


# --- Caso 1: DD día 3% + semana ~8% → ambos bajo umbral, no pausa ----------
def test_dentro_de_limites_no_pausa():
    r = _ev(current=97, day_open=100, week_ago=105, peak=100)  # 3% día, 7.6% sem, 3% peak
    assert r["should_pause"] is False
    assert r["level"] is None


# --- Caso 2: DD día 6% → pausa nivel daily ---------------------------------
def test_drawdown_diario_supera_pausa():
    r = _ev(current=94, day_open=100)  # 6% > 5%
    assert r["should_pause"] is True
    assert r["level"] == "daily"


# --- Caso 3: DD semanal 12% → pausa nivel weekly (kill switch) -------------
def test_drawdown_semanal_supera_kill_switch():
    r = _ev(current=88, week_ago=100)  # 12% > 10%; sin day_open → daily no aplica
    assert r["should_pause"] is True
    assert r["level"] == "weekly"


# --- Caso 4: DD acumulado 16% → pausa indefinida nivel cumulative ----------
def test_drawdown_acumulado_supera_pausa_indefinida():
    r = _ev(current=84, peak=100)  # 16% > 15%
    assert r["should_pause"] is True
    assert r["level"] == "cumulative"


# --- Caso 5: flag OFF → no se evalúa ---------------------------------------
def test_flag_off_no_evalua():
    d = Dispatcher.__new__(Dispatcher)
    with patch("config.PORTFOLIO_DD_LIMITS_ENABLED", False):
        r = _run(d._check_portfolio_drawdown())
    assert r["should_pause"] is False
    assert r["reason"] == "dd_limits_disabled"


# --- Caso 6: peak/refs vacíos → no crashea (within_limits) -----------------
def test_referencias_vacias_no_crashea():
    r = _ev(current=84, day_open=None, week_ago=None, peak=None)
    assert r["should_pause"] is False
    assert r["level"] is None
