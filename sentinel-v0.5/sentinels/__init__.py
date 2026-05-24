# sentinels/__init__.py
# Módulo base para los 10 Sentinels de Sentinel v0.5.
# Define la clase abstracta BaseSentinel y los 9 Sentinels concretos:
# S-1 SMA Crossover, S-2 RSI Fast Reversion, S-3 Bollinger Bounce, S-4 MACD+Volume,
# S-5 ORB, S-6 EMA Triple, S-7 VWAP Reversion, S-8 RSI Divergence,
# S-9 Bollinger Squeeze. (S-10 RegimeClassifier vive en regime_classifier.py.)
#
# Cada Sentinel opera múltiples tickers en paralelo (relación 1:N en DB:
# tabla sentinel_tickers). La protección contra señales duplicadas y los
# estados intra-día (ORB, VWAP) se mantienen por ticker.

import asyncio
import logging
import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_TICKER, CANDLE_INTERVAL

logger = logging.getLogger("sentinel.sentinels")

# Barras a descargar para garantizar suficiente historia para todas las estrategias
# (EMA 55 ~ 110, BBW percentile-10 sobre 100 velas + ventana 20 = 120).
_BARS_LOOKBACK = 150
_FETCH_DAYS    = 10   # 10 días calendario → ~120-150 barras de 15min en días hábiles


# =============================================================================
# CLASE BASE ABSTRACTA
# =============================================================================

class BaseSentinel(ABC):
    """
    Contrato común para todos los Sentinels.
    Multi-ticker: cada Sentinel opera una lista de tickers en paralelo.
    Mantiene last_signal por ticker para preservar la protección anti-duplicado
    heredada del bot v0.0 sin que el estado de un ticker afecte a otro.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        name: str,
        tickers: list[str],
        strategy_type: str,
    ):
        if not tickers:
            raise ValueError(f"Sentinel {name} no puede inicializarse sin tickers.")
        self.sentinel_id    = sentinel_id
        self.owner_id       = owner_id
        self.name           = name
        self.tickers        = list(tickers)
        self.strategy_type  = strategy_type
        # last_signal por ticker — el estado de un ticker no afecta a otro
        self.last_signal: dict[str, Optional[str]] = {t: None for t in self.tickers}

    @abstractmethod
    async def analyze(self, bars, ticker: str) -> dict:
        """
        Lógica de análisis específica de cada estrategia.
        Recibe barras OHLCV (DataFrame) de UN ticker y el nombre del ticker
        (para logs). Retorna:
            {signal_type: 'BUY'|'SELL'|'HOLD', price: float, qty: float}
        """

    def should_emit(self, signal_type: str, ticker: str) -> bool:
        """
        Valida si la señal puede emitirse para este ticker. Solo lee estado.
        Retorna False si signal_type es HOLD o duplica el último confirmado
        para el mismo ticker.
        """
        if signal_type == "HOLD":
            return False
        if signal_type == self.last_signal.get(ticker):
            logger.debug(f"{self.name} | {ticker} | Señal duplicada ignorada: {signal_type}")
            return False
        return True

    def confirm_signal(self, signal_type: str, ticker: str):
        """Avanza last_signal[ticker]. Llamar solo desde run() al emitir."""
        self.last_signal[ticker] = signal_type

    async def fetch_bars(self, ticker: str):
        """
        Descarga las últimas _BARS_LOOKBACK barras de 15 minutos del ticker.
        Returns: DataFrame con OHLCV o None si falla.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_bars_sync, ticker),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning(f"{self.name} | Timeout (15s) al descargar barras de {ticker}")
            return None
        except Exception as e:
            logger.warning(f"{self.name} | Error al descargar barras de {ticker}: {e}")
            return None

    def _fetch_bars_sync(self, ticker: str):
        """Descarga barras vía StockHistoricalDataClient. Ejecutado en thread."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed

        client = StockHistoricalDataClient(
            api_key    = ALPACA_API_KEY,
            secret_key = ALPACA_SECRET_KEY,
        )

        end   = datetime.now(tz=ZoneInfo("UTC"))
        start = end - timedelta(days=_FETCH_DAYS)

        request = StockBarsRequest(
            symbol_or_symbols = [ticker],
            timeframe         = TimeFrame(15, TimeFrameUnit.Minute),
            start             = start,
            end               = end,
            feed              = DataFeed.IEX,
        )

        bars_df = client.get_stock_bars(request).df
        ticker_bars = bars_df.loc[ticker].reset_index()
        return ticker_bars.tail(_BARS_LOOKBACK)

    async def _run_single(self, ticker: str) -> Optional[dict]:
        """Procesa un único ticker: fetch + analyze. Retorna paquete o None."""
        bars = await self.fetch_bars(ticker)
        if bars is None:
            return None

        result = await self.analyze(bars, ticker)

        if result["signal_type"] == "HOLD" or result["qty"] == 0.0:
            return None

        self.confirm_signal(result["signal_type"], ticker)

        return {
            "sentinel_id":   self.sentinel_id,
            "owner_id":      self.owner_id,
            "ticker":        ticker,
            "signal_type":   result["signal_type"],
            "price":         result["price"],
            "qty":           result["qty"],
            "strategy_type": self.strategy_type,
        }

    async def run(self) -> list[dict]:
        """
        Punto de entrada por ciclo. Procesa todos los tickers en paralelo
        con asyncio.gather. Cada ticker puede generar 0 o 1 señal.

        Returns:
            Lista de señales (dict). Vacía si ningún ticker emitió.
        """
        results = await asyncio.gather(
            *[self._run_single(t) for t in self.tickers],
            return_exceptions=True,
        )
        signals: list[dict] = []
        for ticker, result in zip(self.tickers, results):
            if isinstance(result, Exception):
                logger.error(f"{self.name} | {ticker} | excepción: {result}")
                continue
            if result is not None:
                signals.append(result)
        return signals


# =============================================================================
# HELPERS DE INDICADORES
# Cálculos manuales sin ta-lib — solo pandas.
# =============================================================================

def _rsi(closes, period: int):
    """RSI clásico (Wilder simplificado a SMA del cambio absoluto)."""
    deltas = closes.diff()
    gains  = deltas.clip(lower=0)
    losses = -deltas.clip(upper=0)
    avg_gain = gains.rolling(period).mean()
    avg_loss = losses.rolling(period).mean().replace(0, 1e-10)
    rs  = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(closes, span: int):
    return closes.ewm(span=span, adjust=False).mean()


def _atr(bars, window: int = 14) -> float:
    """
    Average True Range con suavizado de Wilder. Retorna el ÚLTIMO valor de ATR
    (escalar float) — es lo que el sizing por riesgo necesita; el caller lo
    convierte a Decimal en el borde monetario (#GR-2).

    TR_i = max(high_i - low_i, |high_i - close_(i-1)|, |low_i - close_(i-1)|).
    El primer ATR es la media simple de los primeros `window` TR; luego Wilder:
        ATR_i = (ATR_(i-1) * (window - 1) + TR_i) / window.

    Retorna NaN si hay menos de `window` barras (sin seed posible).
    """
    high   = bars["high"].tolist()
    low    = bars["low"].tolist()
    close  = bars["close"].tolist()
    n = len(close)
    if n < window:
        return float("nan")

    tr = [high[0] - low[0]]  # primera barra: sin close previo → solo el rango
    for i in range(1, n):
        tr.append(max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        ))

    atr = sum(tr[:window]) / window  # seed: SMA de los primeros `window` TR
    for i in range(window, n):
        atr = (atr * (window - 1) + tr[i]) / window
    return float(atr)


def _default_tickers(tickers: Optional[list[str]]) -> list[str]:
    """Default a [BASE_TICKER] si no se provee lista (evita default mutable)."""
    return list(tickers) if tickers else [BASE_TICKER]


# =============================================================================
# S-1: SMA CROSSOVER — Trend Following
# =============================================================================

class SentinelSMACrossover(BaseSentinel):
    """
    S-1 — Trend Following por cruce de medias móviles simples.
    Golden cross (fast cruza arriba de slow) → BUY.
    Death cross  (fast cruza abajo de slow) → SELL.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        sma_fast: int = 10,
        sma_slow: int = 50,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-1 SMA Crossover",
            tickers       = _default_tickers(tickers),
            strategy_type = "sma_crossover",
        )
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) < self.sma_slow + 2:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para SMAs.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes = bars["close"]
        sma_fast_series = closes.rolling(self.sma_fast).mean()
        sma_slow_series = closes.rolling(self.sma_slow).mean()

        valid = sma_fast_series.dropna().index.intersection(sma_slow_series.dropna().index)
        if len(valid) < 2:
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        prev_idx = valid[-2]
        curr_idx = valid[-1]

        fast_prev = sma_fast_series[prev_idx]
        slow_prev = sma_slow_series[prev_idx]
        fast_curr = sma_fast_series[curr_idx]
        slow_curr = sma_slow_series[curr_idx]
        price     = float(closes[curr_idx])

        if fast_prev <= slow_prev and fast_curr > slow_curr:
            signal_type = "BUY"
        elif fast_prev >= slow_prev and fast_curr < slow_curr:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {price:.4f} "
            f"(SMA{self.sma_fast}={fast_curr:.4f} / SMA{self.sma_slow}={slow_curr:.4f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-2: RSI FAST REVERSION — Mean Reversion
# =============================================================================

class SentinelRSIShort(BaseSentinel):
    """
    S-2 — RSI período 2 para extremos de muy corto plazo.
    RSI < 15 → BUY (sobrevendido extremo). RSI > 85 → SELL.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        rsi_period: int = 2,
        oversold: float = 15.0,
        overbought: float = 85.0,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-2 RSI Fast Reversion",
            tickers       = _default_tickers(tickers),
            strategy_type = "rsi_short",
        )
        self.rsi_period = rsi_period
        self.oversold   = oversold
        self.overbought = overbought

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) < self.rsi_period + 2:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para RSI.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes = bars["close"]
        rsi    = _rsi(closes, self.rsi_period)

        if rsi.dropna().empty:
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        rsi_curr = float(rsi.iloc[-1])
        price    = float(closes.iloc[-1])

        if rsi_curr < self.oversold:
            signal_type = "BUY"
        elif rsi_curr > self.overbought:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {price:.4f} "
            f"(RSI{self.rsi_period}={rsi_curr:.2f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-3: BOLLINGER BOUNCE — Mean Reversion
# =============================================================================

class SentinelBollingerBounce(BaseSentinel):
    """
    S-3 — Bandas de Bollinger SMA(20) ± 2*std.
    Cierre bajo banda inferior → BUY. Cierre sobre banda superior → SELL.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        bb_period: int = 20,
        bb_std: float = 2.0,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-3 Bollinger Bounce",
            tickers       = _default_tickers(tickers),
            strategy_type = "bollinger_bounce",
        )
        self.bb_period = bb_period
        self.bb_std    = bb_std

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) < self.bb_period + 1:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para Bollinger.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes = bars["close"]
        sma    = closes.rolling(self.bb_period).mean()
        std    = closes.rolling(self.bb_period).std()
        upper  = sma + self.bb_std * std
        lower  = sma - self.bb_std * std

        last_close = float(closes.iloc[-1])
        last_upper = float(upper.iloc[-1])
        last_lower = float(lower.iloc[-1])

        if last_close < last_lower:
            signal_type = "BUY"
        elif last_close > last_upper:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": last_close, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {last_close:.4f} "
            f"(BB lower={last_lower:.4f} / upper={last_upper:.4f})"
        )
        return {"signal_type": signal_type, "price": last_close, "qty": 1.0}


# =============================================================================
# S-4: MACD + VOLUME — Trend Following con confirmación
# =============================================================================

class SentinelMACDVolume(BaseSentinel):
    """
    S-4 — MACD(12,26,9) confirmado con volumen > 1.5×SMA(20).
    Sin confirmación de volumen → HOLD aunque haya cruce.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        ema_fast: int = 12,
        ema_slow: int = 26,
        signal_span: int = 9,
        volume_window: int = 20,
        volume_multiplier: float = 1.5,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-4 MACD+Volume",
            tickers       = _default_tickers(tickers),
            strategy_type = "macd_volume",
        )
        self.ema_fast          = ema_fast
        self.ema_slow          = ema_slow
        self.signal_span       = signal_span
        self.volume_window     = volume_window
        self.volume_multiplier = volume_multiplier

    async def analyze(self, bars, ticker: str) -> dict:
        min_required = self.ema_slow + self.signal_span + 2
        if bars is None or len(bars) < min_required:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para MACD.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes  = bars["close"]
        volumes = bars["volume"]

        macd_line = _ema(closes, self.ema_fast) - _ema(closes, self.ema_slow)
        signal    = _ema(macd_line, self.signal_span)

        macd_prev = float(macd_line.iloc[-2])
        macd_curr = float(macd_line.iloc[-1])
        sig_prev  = float(signal.iloc[-2])
        sig_curr  = float(signal.iloc[-1])

        vol_avg          = volumes.rolling(self.volume_window).mean().iloc[-1]
        vol_curr         = float(volumes.iloc[-1])
        volume_confirmed = vol_curr > self.volume_multiplier * float(vol_avg)

        price = float(closes.iloc[-1])

        cross_up   = macd_prev <= sig_prev and macd_curr > sig_curr
        cross_down = macd_prev >= sig_prev and macd_curr < sig_curr

        if cross_up and volume_confirmed:
            signal_type = "BUY"
        elif cross_down and volume_confirmed:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {price:.4f} "
            f"(MACD={macd_curr:.4f} sig={sig_curr:.4f} vol={vol_curr:.0f} avg={vol_avg:.0f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-5: OPENING RANGE BREAKOUT — Momentum intradía
# =============================================================================

class SentinelORB(BaseSentinel):
    """
    S-5 — Marca high/low de la primera vela del día (apertura ET 9:30).
    Estado de opening range mantenido por ticker (multi-ticker safe).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        volume_window: int = 20,
        volume_multiplier: float = 1.5,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-5 ORB",
            tickers       = _default_tickers(tickers),
            strategy_type = "orb_breakout",
        )
        self.volume_window     = volume_window
        self.volume_multiplier = volume_multiplier
        # Estado por ticker: {ticker: {"high": float, "low": float, "date": date}}
        self.opening_ranges: dict[str, dict] = {}

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) < self.volume_window + 1:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para ORB.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        ts_et    = bars["timestamp"].dt.tz_convert("America/New_York")
        today_et = datetime.now(tz=ZoneInfo("America/New_York")).date()
        today_bars = bars[ts_et.dt.date == today_et]

        if len(today_bars) == 0:
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        opening = today_bars.iloc[0]
        cached  = self.opening_ranges.get(ticker)
        if cached is None or cached["date"] != today_et:
            self.opening_ranges[ticker] = {
                "high": float(opening["high"]),
                "low":  float(opening["low"]),
                "date": today_et,
            }
            logger.info(
                f"{self.name} | {ticker} | Nuevo opening range {today_et}: "
                f"high={self.opening_ranges[ticker]['high']:.4f} "
                f"low={self.opening_ranges[ticker]['low']:.4f}"
            )

        rng = self.opening_ranges[ticker]
        last_close = float(bars["close"].iloc[-1])
        last_vol   = float(bars["volume"].iloc[-1])
        vol_avg    = float(bars["volume"].rolling(self.volume_window).mean().iloc[-1])
        confirmed  = last_vol > self.volume_multiplier * vol_avg

        if last_close > rng["high"] and confirmed:
            signal_type = "BUY"
        elif last_close < rng["low"] and confirmed:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": last_close, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {last_close:.4f} "
            f"(ORB high={rng['high']:.4f} low={rng['low']:.4f} "
            f"vol={last_vol:.0f} avg={vol_avg:.0f})"
        )
        return {"signal_type": signal_type, "price": last_close, "qty": 1.0}


# =============================================================================
# S-6: EMA TRIPLE — Trend Following
# =============================================================================

class SentinelEMATriple(BaseSentinel):
    """
    S-6 — EMA 8, 21, 55 verificando alineación.
    EMA8 > EMA21 > EMA55 → BUY. EMA8 < EMA21 < EMA55 → SELL. Mezcla → HOLD.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        ema_short: int = 8,
        ema_mid: int = 21,
        ema_long: int = 55,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-6 EMA Triple",
            tickers       = _default_tickers(tickers),
            strategy_type = "ema_triple",
        )
        self.ema_short = ema_short
        self.ema_mid   = ema_mid
        self.ema_long  = ema_long

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) < self.ema_long + 2:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para EMA Triple.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes = bars["close"]
        e_s = float(_ema(closes, self.ema_short).iloc[-1])
        e_m = float(_ema(closes, self.ema_mid).iloc[-1])
        e_l = float(_ema(closes, self.ema_long).iloc[-1])
        price = float(closes.iloc[-1])

        if e_s > e_m > e_l:
            signal_type = "BUY"
        elif e_s < e_m < e_l:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {price:.4f} "
            f"(EMA{self.ema_short}={e_s:.4f} EMA{self.ema_mid}={e_m:.4f} EMA{self.ema_long}={e_l:.4f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-7: VWAP MEAN REVERSION — Intraday
# =============================================================================

class SentinelVWAPReversion(BaseSentinel):
    """
    S-7 — VWAP intradía con bandas ±2*std del precio típico vs VWAP.
    Reset diario natural: el filtro por today_et descarta barras de días previos.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        std_multiplier: float = 2.0,
        min_intraday_bars: int = 5,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-7 VWAP Reversion",
            tickers       = _default_tickers(tickers),
            strategy_type = "vwap_reversion",
        )
        self.std_multiplier    = std_multiplier
        self.min_intraday_bars = min_intraday_bars

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) == 0:
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        ts_et    = bars["timestamp"].dt.tz_convert("America/New_York")
        today_et = datetime.now(tz=ZoneInfo("America/New_York")).date()
        today_bars = bars[ts_et.dt.date == today_et]

        if len(today_bars) < self.min_intraday_bars:
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        typical = (today_bars["high"] + today_bars["low"] + today_bars["close"]) / 3.0
        volume  = today_bars["volume"]

        cum_volume = volume.cumsum()
        if float(cum_volume.iloc[-1]) == 0.0:
            return {"signal_type": "HOLD", "price": float(today_bars["close"].iloc[-1]), "qty": 0.0}

        vwap   = (typical * volume).cumsum() / cum_volume
        diff   = typical - vwap
        std    = float(diff.std())
        price  = float(today_bars["close"].iloc[-1])
        v_last = float(vwap.iloc[-1])

        if std == 0.0:
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        if price < v_last - self.std_multiplier * std:
            signal_type = "BUY"
        elif price > v_last + self.std_multiplier * std:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {price:.4f} "
            f"(VWAP={v_last:.4f} std={std:.4f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-8: RSI DIVERGENCE — Reversal
# =============================================================================

def _find_swings(values, side: str, k: int = 3) -> list[int]:
    """
    Devuelve índices (posicionales) de swings.
    Swing high: high[i] > las k barras anteriores y k siguientes.
    Swing low : análogo con low.
    """
    out: list[int] = []
    n = len(values)
    if n < 2 * k + 1:
        return out
    for i in range(k, n - k):
        center = values[i]
        left   = values[i - k:i]
        right  = values[i + 1:i + k + 1]
        if side == "high":
            if center > max(left) and center > max(right):
                out.append(i)
        else:
            if center < min(left) and center < min(right):
                out.append(i)
    return out


class SentinelRSIDivergence(BaseSentinel):
    """
    S-8 — Divergencias entre precio y RSI(14) sobre los últimos 2 swings.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        rsi_period: int = 14,
        swing_k: int = 3,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-8 RSI Divergence",
            tickers       = _default_tickers(tickers),
            strategy_type = "rsi_divergence",
        )
        self.rsi_period = rsi_period
        self.swing_k    = swing_k

    async def analyze(self, bars, ticker: str) -> dict:
        if bars is None or len(bars) < self.rsi_period + 2 * self.swing_k + 5:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para divergencia.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes = bars["close"]
        highs  = bars["high"]
        lows   = bars["low"]

        rsi_series = _rsi(closes, self.rsi_period)
        rsi_vals   = rsi_series.values

        highs_arr = highs.values
        lows_arr  = lows.values

        swing_highs = _find_swings(highs_arr, "high", self.swing_k)
        swing_lows  = _find_swings(lows_arr,  "low",  self.swing_k)

        signal_type = "HOLD"
        price       = float(closes.iloc[-1])
        detail      = ""

        # Bearish divergence: precio nuevo high pero RSI no
        if len(swing_highs) >= 2:
            prev_i, last_i = swing_highs[-2], swing_highs[-1]
            if (
                highs_arr[last_i] > highs_arr[prev_i]
                and not math.isnan(rsi_vals[last_i])
                and not math.isnan(rsi_vals[prev_i])
                and rsi_vals[last_i] < rsi_vals[prev_i]
            ):
                signal_type = "SELL"
                detail = (
                    f"bearish div price {highs_arr[prev_i]:.4f}→{highs_arr[last_i]:.4f} "
                    f"RSI {rsi_vals[prev_i]:.2f}→{rsi_vals[last_i]:.2f}"
                )

        # Bullish divergence: precio nuevo low pero RSI no
        if signal_type == "HOLD" and len(swing_lows) >= 2:
            prev_i, last_i = swing_lows[-2], swing_lows[-1]
            if (
                lows_arr[last_i] < lows_arr[prev_i]
                and not math.isnan(rsi_vals[last_i])
                and not math.isnan(rsi_vals[prev_i])
                and rsi_vals[last_i] > rsi_vals[prev_i]
            ):
                signal_type = "BUY"
                detail = (
                    f"bullish div price {lows_arr[prev_i]:.4f}→{lows_arr[last_i]:.4f} "
                    f"RSI {rsi_vals[prev_i]:.2f}→{rsi_vals[last_i]:.2f}"
                )

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(f"{self.name} | {ticker} | {signal_type} @ {price:.4f} ({detail})")
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-9: BOLLINGER SQUEEZE BREAKOUT — Volatility Breakout
# =============================================================================

class SentinelBollingerSqueeze(BaseSentinel):
    """
    S-9 — BBW en percentil 10 (squeeze) + breakout de bandas.
    Sin squeeze → HOLD (no operar en volatilidad normal).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        tickers: Optional[list[str]] = None,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_window: int = 100,
        squeeze_quantile: float = 0.10,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-9 Bollinger Squeeze",
            tickers       = _default_tickers(tickers),
            strategy_type = "bollinger_squeeze",
        )
        self.bb_period        = bb_period
        self.bb_std           = bb_std
        self.squeeze_window   = squeeze_window
        self.squeeze_quantile = squeeze_quantile

    async def analyze(self, bars, ticker: str) -> dict:
        min_required = self.bb_period + self.squeeze_window
        if bars is None or len(bars) < min_required:
            logger.warning(f"{self.name} | {ticker} | Barras insuficientes para Squeeze.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        closes = bars["close"]
        sma    = closes.rolling(self.bb_period).mean()
        std    = closes.rolling(self.bb_period).std()
        upper  = sma + self.bb_std * std
        lower  = sma - self.bb_std * std
        bbw    = (upper - lower) / sma

        bbw_window = bbw.tail(self.squeeze_window).dropna()
        if len(bbw_window) < self.squeeze_window // 2:
            return {"signal_type": "HOLD", "price": float(closes.iloc[-1]), "qty": 0.0}

        threshold  = float(bbw_window.quantile(self.squeeze_quantile))
        last_bbw   = float(bbw.iloc[-1])
        in_squeeze = last_bbw <= threshold

        last_close = float(closes.iloc[-1])
        last_upper = float(upper.iloc[-1])
        last_lower = float(lower.iloc[-1])

        if in_squeeze and last_close > last_upper:
            signal_type = "BUY"
        elif in_squeeze and last_close < last_lower:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type, ticker):
            return {"signal_type": "HOLD", "price": last_close, "qty": 0.0}

        logger.info(
            f"{self.name} | {ticker} | {signal_type} @ {last_close:.4f} "
            f"(BBW={last_bbw:.6f} threshold={threshold:.6f} "
            f"upper={last_upper:.4f} lower={last_lower:.4f})"
        )
        return {"signal_type": signal_type, "price": last_close, "qty": 1.0}


# =============================================================================
# REGISTRO DE SENTINELS
# =============================================================================

SENTINEL_REGISTRY: dict[str, type[BaseSentinel]] = {
    "sma_crossover":     SentinelSMACrossover,
    "rsi_short":         SentinelRSIShort,
    "bollinger_bounce":  SentinelBollingerBounce,
    "macd_volume":       SentinelMACDVolume,
    "orb_breakout":      SentinelORB,
    "ema_triple":        SentinelEMATriple,
    "vwap_reversion":    SentinelVWAPReversion,
    "rsi_divergence":    SentinelRSIDivergence,
    "bollinger_squeeze": SentinelBollingerSqueeze,
}
