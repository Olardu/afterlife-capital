"""Tests del trigger idle_timeout del Universe Selector (zombies inversos).

`_check_idle_tickers(sentinel_id, strategy_type)` detecta tickers asignados que
no operan hace N días (N por `_IDLE_TIMEOUT_DAYS[strategy_type]`). Caso real que
motivó el trigger: AMD asignado a S-4/S-9 todo el período de observación sin
emitir señal. Guards: VIX promedio bajo (mercado plano) y tickers recién
agregados (aún sin tiempo de operar).

Mock de los helpers de historian (sin DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_universe_selector_idle.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universe_selector import UniverseSelector, _IDLE_VIX_GUARD_THRESHOLD


def _run(coro):
    return asyncio.run(coro)


def _selector(*, avg_vix, tickers, last_trade_at=None, added_at=None):
    """UniverseSelector con los 4 helpers de idle mockeados."""
    hist = MagicMock()
    hist.get_avg_vix = AsyncMock(return_value=avg_vix)
    hist.get_sentinel_tickers = AsyncMock(return_value=tickers)
    hist.get_last_trade_timestamp = AsyncMock(return_value=last_trade_at)
    hist.get_ticker_added_at = AsyncMock(return_value=added_at)
    return UniverseSelector(
        historian=hist, claude_client=MagicMock(), owner_id=uuid4(), email_sender=None,
    )


def _ago(days):
    return datetime.now() - timedelta(days=days)


# --- Caso 1: 0 trades, asignado hace 6d, rsi_short (5d), VIX 18 → idle ------
def test_ticker_sin_trades_supera_umbral_es_idle():
    sel = _selector(avg_vix=18.0, tickers=["AMD"], last_trade_at=None, added_at=_ago(6))
    idle = _run(sel._check_idle_tickers(uuid4(), "rsi_short"))
    assert idle == ["AMD"]


# --- Caso 2: 0 trades, asignado hace 3d, rsi_short (5d) → NO idle -----------
def test_ticker_recien_agregado_no_es_idle():
    sel = _selector(avg_vix=18.0, tickers=["AMD"], last_trade_at=None, added_at=_ago(3))
    idle = _run(sel._check_idle_tickers(uuid4(), "rsi_short"))
    assert idle == []


# --- Caso 3: 0 trades, asignado hace 30d, orb (10d) PERO VIX 12 → guard -----
def test_guard_vix_bajo_suspende_trigger():
    assert 12.0 < _IDLE_VIX_GUARD_THRESHOLD  # precondición
    sel = _selector(avg_vix=12.0, tickers=["AMD"], last_trade_at=None, added_at=_ago(30))
    idle = _run(sel._check_idle_tickers(uuid4(), "orb_breakout"))
    assert idle == []  # mercado plano: no es problema del ticker


# --- Caso 4: trade reciente (hace 2d), macd_volume (10d) → NO idle ----------
def test_ticker_con_trade_reciente_no_es_idle():
    sel = _selector(avg_vix=18.0, tickers=["NVDA"], last_trade_at=_ago(2))
    idle = _run(sel._check_idle_tickers(uuid4(), "macd_volume"))
    assert idle == []


# --- Caso 5: último trade hace 20d, ema_triple (14d) → idle ----------------
def test_ticker_inactivo_supera_umbral_es_idle():
    sel = _selector(avg_vix=18.0, tickers=["SPY"], last_trade_at=_ago(20))
    idle = _run(sel._check_idle_tickers(uuid4(), "ema_triple"))
    assert idle == ["SPY"]
