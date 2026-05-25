# backtest/metrics.py
# Métricas de performance PURAS para el framework de backtesting (#HE-4).
# Sin dependencias externas (solo math/statistics) → 100% testeable contra
# cálculo manual, igual que los módulos puros simulated_costs / tax_lots /
# corporate_actions (#CR-1/2/3).
#
# Semántica (documentada y testeada en tests/test_backtest_metrics.py):
#   - sharpe/sortino operan sobre una secuencia de RETORNOS (fracciones).
#     std muestral (ddof=1). risk_free es por-período. Anualización opcional
#     vía sqrt(periods_per_year) — explícita, NO automática (el bot dejó de
#     anualizar a ciegas tras el bug #TECHDEBT-NEW-1 del Sharpe en historian).
#   - max_drawdown opera sobre una CURVA DE EQUITY (valores de portfolio).
#   - win_rate/profit_factor operan sobre PnLs absolutos por trade.
#   - inf en los edge cases sin pérdida / sin drawdown (mismo criterio que
#     historian.calculate_performance: profit_factor / return_to_drawdown).

import math
import statistics
from collections.abc import Sequence


def _as_floats(values) -> list[float]:
    """Normaliza cualquier secuencia (list, tuple, pandas Series, ndarray) a list[float]."""
    if values is None:
        return []
    return [float(v) for v in values]


def sharpe_ratio(returns: Sequence[float], risk_free: float = 0.0,
                 periods_per_year: int | None = None) -> float:
    """
    Sharpe = (mean(returns) - risk_free) / std(returns).
    std muestral (ddof=1). Retorna 0.0 con <2 puntos o std==0.
    Si periods_per_year se provee, anualiza multiplicando por sqrt(periods_per_year).
    """
    r = _as_floats(returns)
    if len(r) < 2:
        return 0.0
    std = statistics.stdev(r)
    if std == 0:
        return 0.0
    sharpe = (statistics.fmean(r) - risk_free) / std
    if periods_per_year:
        sharpe *= math.sqrt(periods_per_year)
    return sharpe


def sortino_ratio(returns: Sequence[float], risk_free: float = 0.0,
                  periods_per_year: int | None = None) -> float:
    """
    Sortino = (mean(returns) - risk_free) / downside_deviation.
    downside_deviation = sqrt( mean( min(r - risk_free, 0)^2 ) ) sobre TODOS los
    períodos N. Si no hay downside: inf cuando el exceso medio es >0, si no 0.0.
    Retorna 0.0 con <2 puntos.
    """
    r = _as_floats(returns)
    if len(r) < 2:
        return 0.0
    excess_mean = statistics.fmean(r) - risk_free
    downside_sq = [min(x - risk_free, 0.0) ** 2 for x in r]
    downside_dev = math.sqrt(sum(downside_sq) / len(r))
    if downside_dev == 0:
        return math.inf if excess_mean > 0 else 0.0
    sortino = excess_mean / downside_dev
    if periods_per_year:
        sortino *= math.sqrt(periods_per_year)
    return sortino


def max_drawdown(equity: Sequence[float]) -> float:
    """
    Máximo drawdown como fracción positiva en [0, 1]: peor caída pico→valle de la
    curva de equity. Retorna 0.0 con <2 puntos o curva monótona creciente.
    """
    e = _as_floats(equity)
    if len(e) < 2:
        return 0.0
    peak = e[0]
    max_dd = 0.0
    for value in e:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def win_rate(pnls: Sequence[float]) -> float:
    """Fracción de trades con PnL > 0. Retorna 0.0 sin trades."""
    p = _as_floats(pnls)
    if not p:
        return 0.0
    wins = sum(1 for x in p if x > 0)
    return wins / len(p)


def profit_factor(pnls: Sequence[float]) -> float:
    """
    profit_factor = ganancia bruta / |pérdida bruta|.
    inf si no hay pérdidas y sí ganancias; 0.0 si no hay ganancias (o sin trades).
    """
    p = _as_floats(pnls)
    gross_profit = sum(x for x in p if x > 0)
    gross_loss = abs(sum(x for x in p if x < 0))
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def return_to_drawdown(total_ret: float, max_dd: float) -> float:
    """
    return_to_drawdown = total_return / max_drawdown.
    inf si max_dd==0 y total_return>0; 0.0 si ambos son 0 (o return<=0 sin dd).
    """
    if max_dd == 0:
        return math.inf if total_ret > 0 else 0.0
    return total_ret / max_dd


def total_return(equity: Sequence[float]) -> float:
    """Retorno total de la curva: equity[-1]/equity[0] - 1. 0.0 con <2 puntos."""
    e = _as_floats(equity)
    if len(e) < 2 or e[0] == 0:
        return 0.0
    return e[-1] / e[0] - 1.0


def compute_metrics(equity: Sequence[float], trade_pnls: Sequence[float],
                    trade_returns: Sequence[float] | None = None,
                    risk_free: float = 0.0,
                    periods_per_year: int | None = None) -> dict:
    """
    Agrega todas las métricas en un dict. `trade_returns` (fracciones por trade)
    alimenta sharpe/sortino; `trade_pnls` (absolutos) alimenta win_rate/profit_factor;
    `equity` (curva) alimenta total_return/max_drawdown.
    Si trade_returns es None se usa trade_pnls como proxy de retornos.
    """
    rets = trade_returns if trade_returns is not None else trade_pnls
    tr = total_return(equity)
    mdd = max_drawdown(equity)
    return {
        "total_return": tr,
        "max_drawdown": mdd,
        "sharpe": sharpe_ratio(rets, risk_free=risk_free, periods_per_year=periods_per_year),
        "sortino": sortino_ratio(rets, risk_free=risk_free, periods_per_year=periods_per_year),
        "win_rate": win_rate(trade_pnls),
        "profit_factor": profit_factor(trade_pnls),
        "return_to_drawdown": return_to_drawdown(tr, mdd),
        "n_trades": len(_as_floats(trade_pnls)),
    }
