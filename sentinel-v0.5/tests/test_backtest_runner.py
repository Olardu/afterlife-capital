# tests/test_backtest_runner.py
# TDD de backtest.runner — orquestación Backtest→métricas + comparación vs paper (#HE-4).

import json
import math

import numpy as np
import pandas as pd
import pytest

from backtest import runner


def _v_shaped_ohlcv(n_down=70, n_up=90):
    closes = list(np.linspace(120, 50, n_down)) + list(np.linspace(50, 160, n_up))
    idx = pd.date_range("2026-01-02 09:30", periods=len(closes), freq="15min", tz="UTC")
    c = pd.Series(closes, index=idx)
    return pd.DataFrame(
        {"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000.0}, index=idx
    )


# =============================================================================
# run_backtest
# =============================================================================

def test_run_backtest_returns_result():
    df = _v_shaped_ohlcv()
    r = runner.run_backtest("s1", df, ticker="TEST", cash=100_000)
    assert r.sentinel_key == "s1"
    assert r.ticker == "TEST"
    assert r.n_bars == len(df)
    assert set(r.metrics) >= {"sharpe", "sortino", "max_drawdown", "win_rate",
                              "profit_factor", "return_to_drawdown", "total_return", "n_trades"}
    assert isinstance(r.metrics["n_trades"], int)
    assert r.native["n_trades"] >= 1  # el golden cross entró al menos una vez


def test_run_backtest_to_dict_is_json_safe():
    # V-shape → 1 trade long ganador, sin pérdidas → profit_factor = inf.
    df = _v_shaped_ohlcv()
    r = runner.run_backtest("s1", df, ticker="TEST")
    assert math.isinf(r.metrics["profit_factor"])  # confirma el edge
    blob = json.dumps(r.to_dict())  # NO debe explotar por inf/nan
    parsed = json.loads(blob)
    assert parsed["metrics"]["profit_factor"] is None  # inf → null en JSON


def test_run_backtest_unknown_sentinel_raises():
    df = _v_shaped_ohlcv()
    with pytest.raises(ValueError, match="sentinel"):
        runner.run_backtest("s99", df, ticker="TEST")


# =============================================================================
# compare_to_paper
# =============================================================================

def test_compare_to_paper_deltas():
    bt = {"sharpe": 2.0, "win_rate": 0.6, "profit_factor": 3.0}
    paper = {"sharpe": 1.0, "win_rate": 0.5, "profit_factor": 2.0}
    out = runner.compare_to_paper(bt, paper)
    assert out["sharpe"] == {"backtest": 2.0, "paper": 1.0, "delta": pytest.approx(1.0)}
    assert out["win_rate"]["delta"] == pytest.approx(0.1)
    assert out["profit_factor"]["delta"] == pytest.approx(1.0)


def test_compare_to_paper_handles_inf():
    bt = {"profit_factor": math.inf}
    paper = {"profit_factor": 2.0}
    out = runner.compare_to_paper(bt, paper)
    assert out["profit_factor"]["delta"] is None  # delta indefinido con inf


def test_compare_to_paper_only_common_keys():
    bt = {"sharpe": 2.0, "extra_bt": 9}
    paper = {"sharpe": 1.0, "extra_paper": 8}
    out = runner.compare_to_paper(bt, paper)
    assert set(out) == {"sharpe"}
