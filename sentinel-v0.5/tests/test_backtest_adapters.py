# tests/test_backtest_adapters.py
# TDD de backtest.adapters — bridge async→sync + Sentinel→Strategy de Backtesting.py (#HE-4).

import numpy as np
import pandas as pd
import pytest
from backtesting import Backtest

from backtest import adapters
from sentinels import SentinelRSIShort, SentinelSMACrossover


# =============================================================================
# run_sync — driver de coroutines sin await real
# =============================================================================

def test_run_sync_returns_value():
    async def f():
        return 42
    assert adapters.run_sync(f()) == 42


def test_run_sync_returns_dict():
    async def f():
        return {"signal_type": "BUY", "price": 1.0, "qty": 5}
    assert adapters.run_sync(f())["signal_type"] == "BUY"


def test_run_sync_raises_if_awaits():
    async def f():
        import asyncio
        await asyncio.sleep(0)  # suspende de verdad
        return 1
    with pytest.raises(RuntimeError, match="suspend"):
        adapters.run_sync(f())


# =============================================================================
# resolve_sentinel / build_sentinel
# =============================================================================

@pytest.mark.parametrize("key", ["s2", "S-2", "rsi_short", "RSI_SHORT"])
def test_resolve_sentinel_aliases(key):
    assert adapters.resolve_sentinel(key) is SentinelRSIShort


def test_resolve_sentinel_unknown_raises():
    with pytest.raises(ValueError, match="sentinel"):
        adapters.resolve_sentinel("s99")


def test_build_sentinel():
    s = adapters.build_sentinel("s1", "AAPL")
    assert isinstance(s, SentinelSMACrossover)
    assert s.tickers == ["AAPL"]
    assert s.strategy_type == "sma_crossover"


# =============================================================================
# make_strategy — integración con un Backtest real sobre data sintética
# =============================================================================

def _v_shaped_ohlcv(n_down=70, n_up=90):
    """Precio en V (baja y sube) → fuerza un golden cross de S-1 en el ascenso."""
    closes = list(np.linspace(120, 50, n_down)) + list(np.linspace(50, 160, n_up))
    idx = pd.date_range("2026-01-02 09:30", periods=len(closes), freq="15min", tz="UTC")
    c = pd.Series(closes, index=idx)
    return pd.DataFrame(
        {"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000.0},
        index=idx,
    )


def test_make_strategy_runs_and_enters_long():
    df = _v_shaped_ohlcv()
    strat = adapters.make_strategy("s1", "TEST")
    stats = Backtest(df, strat, cash=100_000, commission=0.0, finalize_trades=True).run()
    # El golden cross durante el ascenso debe disparar al menos 1 trade long.
    assert stats["# Trades"] >= 1
    trades = stats["_trades"]
    assert (trades["Size"] > 0).all()  # long-only por defecto (allow_short=False)


def test_make_strategy_long_only_never_shorts():
    # Precio en pico invertido (sube y baja) → S-1 daría death cross (SELL) sin posición.
    closes = list(np.linspace(50, 160, 80)) + list(np.linspace(160, 40, 90))
    idx = pd.date_range("2026-01-02 09:30", periods=len(closes), freq="15min", tz="UTC")
    c = pd.Series(closes, index=idx)
    df = pd.DataFrame(
        {"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000.0}, index=idx
    )
    strat = adapters.make_strategy("s1", "TEST", allow_short=False)
    stats = Backtest(df, strat, cash=100_000, commission=0.0).run()
    trades = stats["_trades"]
    if len(trades):
        assert (trades["Size"] > 0).all()  # nunca abrió short


def test_make_strategy_intraday_sentinel_no_crash():
    # S-7 VWAP usa bars['timestamp'].dt.tz_convert → el adapter debe darle timestamp tz-aware.
    df = _v_shaped_ohlcv()
    strat = adapters.make_strategy("s7", "TEST")
    stats = Backtest(df, strat, cash=100_000, commission=0.0).run()
    assert "# Trades" in stats.index  # corrió sin excepción
