# backtest/ — Framework de backtesting (#HE-4)

Herramienta de **validación on-demand** para correr las estrategias del bot
(Sentinels) sobre datos históricos amplios, sin esperar paper trading. Útil como
gate pre-Fase 5 (live).

> **No** es parte del runtime del bot. El loop de trading (`main.py`) y el
> dashboard (`api.py`) NO importan este paquete. La dependencia `backtesting`
> vive en `requirements-dev.txt`.

## Nombre del paquete

Se llama `backtest` (singular) **a propósito**, NO `backtesting`: la librería pip
[Backtesting.py](https://kernc.github.io/backtesting.py/) se importa como
`from backtesting import Backtest`, y un paquete local homónimo la shadowearía.

## Uso (CLI)

```powershell
# Backtest de S-2 (RSI Fast Reversion) sobre SPY con datos de Alpaca
python -m backtest --sentinel s2 --ticker SPY --start 2026-01-01 --end 2026-04-01

# Desde un CSV (timestamp,open,high,low,close,volume), salida JSON a archivo
python -m backtest --sentinel s1 --ticker AAPL --source csv --csv bars.csv --json --output r.json

# Comparar contra métricas del paper período 1 (JSON {sharpe, win_rate, profit_factor, ...})
python -m backtest --sentinel s2 --ticker SPY --start 2026-01-01 --end 2026-04-01 --paper-json paper.json
```

Flags: `--sentinel` (s1..s9 o strategy_type), `--ticker`, `--source`
(`alpaca`|`csv`|`yahoo`), `--start`/`--end`, `--csv`, `--timeframe` (`15Min`),
`--feed` (`IEX`), `--cash`, `--commission`, `--allow-short` (default long-only),
`--paper-json`, `--json`, `--output`.

## Uso (API)

```python
from backtest import data, runner

bars = data.load_bars("SPY", source="alpaca", start="2026-01-01", end="2026-04-01")
result = runner.run_backtest("s2", bars, ticker="SPY")
print(result.metrics)            # sharpe, sortino, max_drawdown, win_rate, profit_factor, ...
print(result.to_dict())          # JSON-safe (inf/nan → null)
```

## Estructura

| Módulo | Rol |
|---|---|
| `metrics.py` | Métricas puras (sharpe, sortino, max_dd, win_rate, profit_factor, ...). Sin dep externa. |
| `data.py` | Carga OHLCV: Alpaca histórico / CSV / Yahoo → contrato de Backtesting.py. |
| `adapters.py` | Envuelve cada Sentinel como `Strategy`. Bridge async→sync + formato de barras live. |
| `runner.py` | Orquesta Backtest → métricas + comparación vs paper. |
| `__main__.py` | CLI. |

## Decisiones de v1

- **Long-only por defecto.** `--allow-short` habilita shorts (S-2/S-8 shortean en
  vivo), pero el default evita complicaciones de margen al validar una estrategia.
- **`finalize_trades=True`**: la posición abierta al cierre del backtest se realiza
  para que cuente en las métricas.
- **Sharpe/Sortino per-trade** (sin anualizar por defecto), consistente con
  `historian.calculate_performance` tras el fix del bug #TECHDEBT-NEW-1.
