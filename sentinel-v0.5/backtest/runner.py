# backtest/runner.py
# Orquesta un backtest de un Sentinel: data → Backtest (Backtesting.py) → métricas
# propias (backtest.metrics) + stats nativas, con comparación opcional vs paper (#HE-4).

import math
from dataclasses import dataclass, field

import pandas as pd
from backtesting import Backtest

from backtest import adapters, metrics


def _f(value):
    """float JSON-safe: NaN/inf → None (json.dumps no produce JSON válido con Infinity)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else v


@dataclass
class BacktestResult:
    """Resultado de un backtest: meta + métricas propias + stats nativas de Backtesting.py."""
    sentinel_key: str
    ticker: str
    n_bars: int
    metrics: dict = field(default_factory=dict)   # backtest.metrics.compute_metrics
    native: dict = field(default_factory=dict)     # subset de stats de Backtesting.py

    def to_dict(self) -> dict:
        """Representación JSON-safe (inf/nan → null)."""
        return {
            "sentinel_key": self.sentinel_key,
            "ticker": self.ticker,
            "n_bars": self.n_bars,
            "metrics": {k: (_f(v) if isinstance(v, float) else v) for k, v in self.metrics.items()},
            "native": {k: _f(v) if isinstance(v, float) else v for k, v in self.native.items()},
        }


def run_backtest(sentinel_key: str, data: pd.DataFrame, ticker: str = "", cash: float = 100_000.0,
                 commission: float = 0.0, allow_short: bool = False) -> BacktestResult:
    """
    Corre un backtest del Sentinel sobre `data` (OHLCV normalizado de backtest.data).
    finalize_trades=True para que la posición abierta al final cuente en las métricas.
    """
    strat = adapters.make_strategy(sentinel_key, ticker or "TICKER", allow_short=allow_short)
    bt = Backtest(data, strat, cash=cash, commission=commission, finalize_trades=True)
    stats = bt.run()

    equity = list(stats["_equity_curve"]["Equity"])
    trades = stats["_trades"]
    trade_pnls = [float(x) for x in trades["PnL"]]
    trade_returns = [float(x) for x in trades["ReturnPct"]]

    computed = metrics.compute_metrics(
        equity=equity, trade_pnls=trade_pnls, trade_returns=trade_returns
    )

    native = {
        "return_pct": _f(stats.get("Return [%]")),
        "buy_hold_return_pct": _f(stats.get("Buy & Hold Return [%]")),
        "sharpe_native": _f(stats.get("Sharpe Ratio")),
        "sortino_native": _f(stats.get("Sortino Ratio")),
        "max_drawdown_pct": _f(stats.get("Max. Drawdown [%]")),
        "win_rate_pct": _f(stats.get("Win Rate [%]")),
        "profit_factor_native": _f(stats.get("Profit Factor")),
        "exposure_pct": _f(stats.get("Exposure Time [%]")),
        "equity_final": _f(stats.get("Equity Final [$]")),
        "n_trades": int(stats.get("# Trades", 0)),
    }

    return BacktestResult(
        sentinel_key=sentinel_key,
        ticker=ticker,
        n_bars=len(data),
        metrics=computed,
        native=native,
    )


def compare_to_paper(backtest_metrics: dict, paper_metrics: dict, keys=None) -> dict:
    """
    Comparación side-by-side de métricas backtest vs paper (período 1).
    Solo claves presentes en AMBOS dicts. delta = backtest - paper (None si alguno
    es inf/nan/no-numérico). Pura → testeable sin DB.
    """
    common = set(backtest_metrics) & set(paper_metrics)
    if keys is not None:
        common &= set(keys)
    out = {}
    for k in sorted(common):
        bt, pp = backtest_metrics[k], paper_metrics[k]
        bt_f, pp_f = _f(bt), _f(pp)
        delta = (bt_f - pp_f) if (bt_f is not None and pp_f is not None) else None
        out[k] = {"backtest": bt, "paper": pp, "delta": delta}
    return out
