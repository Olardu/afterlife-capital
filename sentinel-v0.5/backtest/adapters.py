# backtest/adapters.py
# Envuelve cada Sentinel del bot como una Strategy de Backtesting.py (#HE-4).
#
# Dos puentes:
#  1) async→sync: las analyze() de los Sentinels son `async def` pero NO tienen
#     awaits reales (son cálculos pandas). run_sync las ejecuta de un tirón.
#  2) formato de barras: Backtesting.py expone OHLCV capitalizado e indexado por
#     tiempo; los Sentinels esperan el formato live (columnas minúsculas + columna
#     `timestamp` tz-aware, como devuelve BaseSentinel._fetch_bars_sync). El adapter
#     reconstruye ese formato en cada next().

from uuid import uuid4

import pandas as pd
from backtesting import Strategy

from sentinels import SENTINEL_REGISTRY, BaseSentinel

# Alias amigables para CLI/uso: s1..s9 → strategy_type del registry.
_KEY_TO_TYPE = {
    "s1": "sma_crossover",
    "s2": "rsi_short",
    "s3": "bollinger_bounce",
    "s4": "macd_volume",
    "s5": "orb_breakout",
    "s6": "ema_triple",
    "s7": "vwap_reversion",
    "s8": "rsi_divergence",
    "s9": "bollinger_squeeze",
}

_RENAME_TO_LOWER = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


def run_sync(coro):
    """
    Ejecuta una coroutine SIN awaits reales hasta su return y devuelve el valor.
    Lanza RuntimeError si la coroutine suspende en un await (contrato roto).
    """
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    coro.close()
    raise RuntimeError("run_sync: la coroutine suspendió en un await; analyze() debe ser await-free")


def resolve_sentinel(key: str) -> type[BaseSentinel]:
    """Resuelve 's2' / 'S-2' / 'rsi_short' (case-insensitive) → clase del Sentinel."""
    k = str(key).strip().lower().replace("-", "")
    if k in _KEY_TO_TYPE:
        k = _KEY_TO_TYPE[k]
    if k in SENTINEL_REGISTRY:
        return SENTINEL_REGISTRY[k]
    raise ValueError(f"sentinel desconocido: {key!r} (usá s1..s9 o un strategy_type del registry)")


def build_sentinel(key: str, ticker: str) -> BaseSentinel:
    """Instancia un Sentinel para backtest (UUIDs dummy, un solo ticker)."""
    cls = resolve_sentinel(key)
    return cls(sentinel_id=uuid4(), owner_id=uuid4(), tickers=[ticker])


def _to_live_bars(window: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame de Backtesting.py (OHLCV capitalizado, índice datetime) → formato live:
    columna `timestamp` tz-aware (UTC si era naive) + columnas minúsculas.
    """
    bars = window.reset_index()
    bars = bars.rename(columns=_RENAME_TO_LOWER)
    time_col = bars.columns[0]
    if time_col not in ("open", "high", "low", "close", "volume"):
        bars = bars.rename(columns={time_col: "timestamp"})
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    if bars["timestamp"].dt.tz is None:
        bars["timestamp"] = bars["timestamp"].dt.tz_localize("UTC")
    return bars


def make_strategy(sentinel_key: str, ticker: str, allow_short: bool = False) -> type[Strategy]:
    """
    Construye una subclase de Strategy de Backtesting.py que delega las señales en
    el Sentinel `sentinel_key` sobre `ticker`.

    Mapeo de señales (long-only por defecto):
      BUY  → si no hay posición, abre long (con allow_short cierra short antes).
      SELL → si hay long, lo cierra (con allow_short abre short si queda flat).
    HOLD / qty=0 no hacen nada.
    """
    resolve_sentinel(sentinel_key)  # validación temprana (falla en build, no en next)

    class _SentinelStrategy(Strategy):
        def init(self):
            self._sentinel = build_sentinel(sentinel_key, ticker)
            self._ticker = ticker

        def next(self):
            bars = _to_live_bars(self.data.df)
            result = run_sync(self._sentinel.analyze(bars, self._ticker))
            signal = result.get("signal_type", "HOLD")
            if result.get("qty", 0.0) == 0.0 or signal == "HOLD":
                return

            if signal == "BUY":
                if self.position.is_short:
                    self.position.close()
                if not self.position:
                    self.buy()
            elif signal == "SELL":
                if self.position.is_long:
                    self.position.close()
                if allow_short and not self.position:
                    self.sell()

    _SentinelStrategy.__name__ = f"Strategy_{sentinel_key}_{ticker}"
    _SentinelStrategy.__qualname__ = _SentinelStrategy.__name__
    return _SentinelStrategy
