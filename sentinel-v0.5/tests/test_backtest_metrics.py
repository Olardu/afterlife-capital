# tests/test_backtest_metrics.py
# TDD del módulo puro backtest.metrics (#HE-4 — T-T Bloque E).
# Cada valor esperado está calculado a mano en el docstring del test para que
# la verificación sea independiente de la implementación.

import math

import pytest

from backtest import metrics


# =============================================================================
# sharpe_ratio
# =============================================================================

def test_sharpe_clean():
    # returns=[0.1,0.2,0.3]: mean=0.2; sample std (ddof=1): devs=[-0.1,0,0.1],
    # var=(0.01+0+0.01)/2=0.01, std=0.1; sharpe=0.2/0.1=2.0
    assert metrics.sharpe_ratio([0.1, 0.2, 0.3]) == pytest.approx(2.0)


def test_sharpe_with_risk_free():
    # mismo set, risk_free=0.1 → exceso mean=0.1; 0.1/0.1=1.0
    assert metrics.sharpe_ratio([0.1, 0.2, 0.3], risk_free=0.1) == pytest.approx(1.0)


def test_sharpe_annualized():
    # periods_per_year=4 → 2.0*sqrt(4)=4.0
    assert metrics.sharpe_ratio([0.1, 0.2, 0.3], periods_per_year=4) == pytest.approx(4.0)


def test_sharpe_zero_std_is_zero():
    assert metrics.sharpe_ratio([0.05, 0.05, 0.05]) == 0.0


def test_sharpe_insufficient_data_is_zero():
    assert metrics.sharpe_ratio([]) == 0.0
    assert metrics.sharpe_ratio([0.1]) == 0.0


# =============================================================================
# sortino_ratio
# =============================================================================

def test_sortino_clean():
    # returns=[0.3,-0.1,0.3,-0.1]: mean=0.1; downside sq vs target 0:
    # [0,0.01,0,0.01]/N=4 = 0.005; dd=sqrt(0.005)=0.0707107; 0.1/0.0707107=sqrt(2)
    assert metrics.sortino_ratio([0.3, -0.1, 0.3, -0.1]) == pytest.approx(math.sqrt(2))


def test_sortino_no_downside_is_inf():
    assert metrics.sortino_ratio([0.1, 0.2, 0.3]) == math.inf


def test_sortino_no_downside_negative_mean_is_zero():
    # sin retornos negativos pero mean<=0 (todos cero) → 0.0, no inf
    assert metrics.sortino_ratio([0.0, 0.0, 0.0]) == 0.0


def test_sortino_insufficient_data_is_zero():
    assert metrics.sortino_ratio([0.1]) == 0.0


# =============================================================================
# max_drawdown
# =============================================================================

def test_max_drawdown_clean():
    # equity=[100,120,90,110,80]: peak=120; peor caída (120-80)/120=0.33333
    assert metrics.max_drawdown([100, 120, 90, 110, 80]) == pytest.approx(1 / 3)


def test_max_drawdown_monotonic_is_zero():
    assert metrics.max_drawdown([100, 110, 120, 130]) == 0.0


def test_max_drawdown_empty_is_zero():
    assert metrics.max_drawdown([]) == 0.0
    assert metrics.max_drawdown([100]) == 0.0


# =============================================================================
# win_rate
# =============================================================================

def test_win_rate_clean():
    # pnls=[10,-5,20,-3,0]: wins(>0)=2, total=5 → 0.4
    assert metrics.win_rate([10, -5, 20, -3, 0]) == pytest.approx(0.4)


def test_win_rate_empty_is_zero():
    assert metrics.win_rate([]) == 0.0


# =============================================================================
# profit_factor
# =============================================================================

def test_profit_factor_clean():
    # pnls=[10,-5,20,-3]: gross_profit=30, gross_loss=8 → 3.75
    assert metrics.profit_factor([10, -5, 20, -3]) == pytest.approx(3.75)


def test_profit_factor_no_losses_is_inf():
    assert metrics.profit_factor([10, 20]) == math.inf


def test_profit_factor_no_profit_is_zero():
    assert metrics.profit_factor([-10, -20]) == 0.0


def test_profit_factor_empty_is_zero():
    assert metrics.profit_factor([]) == 0.0


# =============================================================================
# return_to_drawdown
# =============================================================================

def test_return_to_drawdown_clean():
    assert metrics.return_to_drawdown(0.5, 0.25) == pytest.approx(2.0)


def test_return_to_drawdown_zero_dd_is_inf():
    assert metrics.return_to_drawdown(0.5, 0.0) == math.inf
    assert metrics.return_to_drawdown(0.0, 0.0) == 0.0


# =============================================================================
# total_return
# =============================================================================

def test_total_return_clean():
    assert metrics.total_return([100, 150]) == pytest.approx(0.5)


def test_total_return_empty_is_zero():
    assert metrics.total_return([]) == 0.0
    assert metrics.total_return([100]) == 0.0


# =============================================================================
# compute_metrics (orquestador)
# =============================================================================

def test_compute_metrics_keys_and_values():
    equity = [100, 120, 90, 110, 80]
    trade_pnls = [10, -5, 20, -3]
    trade_returns = [0.3, -0.1, 0.3, -0.1]
    out = metrics.compute_metrics(
        equity=equity,
        trade_pnls=trade_pnls,
        trade_returns=trade_returns,
    )
    assert set(out) >= {
        "total_return", "max_drawdown", "sharpe", "sortino",
        "win_rate", "profit_factor", "return_to_drawdown", "n_trades",
    }
    assert out["n_trades"] == 4
    assert out["total_return"] == pytest.approx(80 / 100 - 1)  # -0.2
    assert out["max_drawdown"] == pytest.approx(1 / 3)
    assert out["sortino"] == pytest.approx(math.sqrt(2))
    assert out["win_rate"] == pytest.approx(0.5)  # 2 wins de 4
    assert out["profit_factor"] == pytest.approx(3.75)


def test_compute_metrics_empty_trades():
    out = metrics.compute_metrics(equity=[100, 110], trade_pnls=[], trade_returns=[])
    assert out["n_trades"] == 0
    assert out["win_rate"] == 0.0
    assert out["profit_factor"] == 0.0
    assert out["sharpe"] == 0.0
    assert out["total_return"] == pytest.approx(0.1)
