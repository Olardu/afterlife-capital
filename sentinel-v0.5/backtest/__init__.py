# backtest/ — framework de backtesting de Sentinel v0.5 (#HE-4, T-T Bloque E).
#
# OJO con el nombre: este paquete se llama `backtest` (singular) a propósito,
# NO `backtesting`. La librería pip Backtesting.py se importa como
# `from backtesting import Backtest, Strategy`; un paquete local llamado
# `backtesting` la shadowearía (el dir del script va primero en sys.path).
#
# Estructura:
#   metrics.py   — métricas puras (sharpe, sortino, max_dd, win_rate, ...).
#   data.py      — carga de OHLCV (Alpaca histórico o CSV) para Backtesting.py.
#   adapters.py  — envuelve cada Sentinel del bot como Strategy de Backtesting.py.
#   runner.py    — orquesta backtest → métricas → comparación opcional vs paper.
#   __main__.py  — CLI: python -m backtest --sentinel s2 --start ... --end ...

from backtest import adapters, data, metrics, runner

__all__ = ["adapters", "data", "metrics", "runner"]
