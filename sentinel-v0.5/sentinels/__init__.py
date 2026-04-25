# sentinels/__init__.py
# Módulo base para los 10 Sentinels de Sentinel v0.5.
# Define la clase abstracta BaseSentinel y los 9 Sentinels concretos:
# S-1 SMA Crossover, S-2 RSI Short, S-3 Bollinger Bounce, S-4 MACD+Volume,
# S-5 ORB, S-6 EMA Triple, S-7 VWAP Reversion, S-8 RSI Divergence,
# S-9 Bollinger Squeeze. (S-10 RegimeClassifier vive en regime_classifier.py.)
# Cada Sentinel es un agente autónomo que emite señales hacia el Dispatcher.

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
    Implementa la protección contra señales duplicadas heredada del bot v0.0.
    Centraliza fetch_bars / run para que cada subclase solo defina analyze().
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        name: str,
        ticker: str,
        strategy_type: str,
    ):
        self.sentinel_id    = sentinel_id
        self.owner_id       = owner_id
        self.name           = name
        self.ticker         = ticker
        self.strategy_type  = strategy_type
        self.last_signal: Optional[str] = None  # protección contra señales duplicadas (v0.0)

    @abstractmethod
    async def analyze(self, bars) -> dict:
        """
        Lógica de análisis específica de cada estrategia.

        Recibe barras OHLCV como DataFrame y retorna:
            {signal_type: 'BUY'|'SELL'|'HOLD', price: float, qty: float}
        """

    def should_emit(self, signal_type: str) -> bool:
        """
        Valida si la señal puede emitirse. Solo lee estado, no lo muta.

        Retorna False si:
            - signal_type == "HOLD"
            - signal_type es igual al último confirmado (duplicado)

        Llamar confirm_signal() en run() DESPUÉS de decidir emitir,
        no aquí — así last_signal solo avanza cuando la señal se envía realmente.
        """
        if signal_type == "HOLD":
            return False
        if signal_type == self.last_signal:
            logger.debug(f"{self.name} | Señal duplicada ignorada: {signal_type}")
            return False
        return True

    def confirm_signal(self, signal_type: str):
        """
        Confirma que la señal se va a emitir y actualiza last_signal.
        Llamar solo desde run(), justo antes de retornar el paquete al Dispatcher.
        """
        self.last_signal = signal_type

    async def fetch_bars(self):
        """
        Descarga las últimas _BARS_LOOKBACK barras de 15 minutos del ticker vía Alpaca.
        Ejecuta el SDK síncrono en asyncio.to_thread.

        Returns:
            DataFrame con OHLCV, o None si falla.
        """
        try:
            return await asyncio.to_thread(self._fetch_bars_sync)
        except Exception as e:
            logger.warning(f"{self.name} | Error al descargar barras de {self.ticker}: {e}")
            return None

    def _fetch_bars_sync(self):
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
            symbol_or_symbols = [self.ticker],
            timeframe         = TimeFrame(15, TimeFrameUnit.Minute),
            start             = start,
            end               = end,
            feed              = DataFeed.IEX,
        )

        bars_df = client.get_stock_bars(request).df
        ticker_bars = bars_df.loc[self.ticker].reset_index()
        return ticker_bars.tail(_BARS_LOOKBACK)

    async def run(self) -> Optional[dict]:
        """
        Punto de entrada del grafo LangGraph para este Sentinel.

        Flujo:
            1. fetch_bars()
            2. analyze(bars)
            3. Si señal activa → retornar paquete completo para el Dispatcher
            4. Si HOLD o error → retornar None

        Returns:
            {sentinel_id, owner_id, ticker, signal_type, price, qty, strategy_type}
            o None si no hay señal que emitir.
        """
        bars = await self.fetch_bars()
        if bars is None:
            return None

        result = await self.analyze(bars)

        if result["signal_type"] == "HOLD" or result["qty"] == 0.0:
            return None

        # confirm_signal aquí — last_signal solo avanza cuando la señal se envía al Dispatcher
        self.confirm_signal(result["signal_type"])

        return {
            "sentinel_id":   self.sentinel_id,
            "owner_id":      self.owner_id,
            "ticker":        self.ticker,
            "signal_type":   result["signal_type"],
            "price":         result["price"],
            "qty":           result["qty"],
            "strategy_type": self.strategy_type,
        }


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


# =============================================================================
# S-1: SMA CROSSOVER — Trend Following
# =============================================================================

class SentinelSMACrossover(BaseSentinel):
    """
    S-1 — Trend Following por cruce de medias móviles simples.
    Golden cross (fast cruza arriba de slow) → BUY.
    Death cross  (fast cruza abajo de slow) → SELL.
    Estrategia directamente derivada del bot v0.0.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        sma_fast: int = 10,
        sma_slow: int = 50,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-1 SMA Crossover",
            ticker        = ticker,
            strategy_type = "sma_crossover",
        )
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow

    async def analyze(self, bars) -> dict:
        """
        Detecta cruces de SMA sobre las últimas barras de 15 minutos.

        Cruce alcista: SMA_fast[i-1] <= SMA_slow[i-1] y SMA_fast[i] > SMA_slow[i] → BUY
        Cruce bajista: SMA_fast[i-1] >= SMA_slow[i-1] y SMA_fast[i] < SMA_slow[i] → SELL

        qty = 1.0 como sugerencia base; el Dispatcher la ajusta por allocation.
        """
        if bars is None or len(bars) < self.sma_slow + 2:
            logger.warning(f"{self.name} | Barras insuficientes para calcular SMAs.")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {price:.4f} "
            f"(SMA{self.sma_fast}={fast_curr:.4f} / SMA{self.sma_slow}={slow_curr:.4f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-2: RSI SHORT — Mean Reversion
# =============================================================================

class SentinelRSIShort(BaseSentinel):
    """
    S-2 — RSI de período muy corto (2) para detectar extremos de muy corto plazo.
    RSI < 15 → BUY (sobrevendido extremo).
    RSI > 85 → SELL (sobrecomprado extremo).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        rsi_period: int = 2,
        oversold: float = 15.0,
        overbought: float = 85.0,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-2 RSI Short",
            ticker        = ticker,
            strategy_type = "rsi_short",
        )
        self.rsi_period = rsi_period
        self.oversold   = oversold
        self.overbought = overbought

    async def analyze(self, bars) -> dict:
        if bars is None or len(bars) < self.rsi_period + 2:
            logger.warning(f"{self.name} | Barras insuficientes para RSI({self.rsi_period}).")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {price:.4f} "
            f"(RSI{self.rsi_period}={rsi_curr:.2f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-3: BOLLINGER BOUNCE — Mean Reversion
# =============================================================================

class SentinelBollingerBounce(BaseSentinel):
    """
    S-3 — Bandas de Bollinger clásicas SMA(20) ± 2*std.
    Cierre bajo banda inferior → BUY (rebote esperado).
    Cierre sobre banda superior → SELL (reversión esperada).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        bb_period: int = 20,
        bb_std: float = 2.0,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-3 Bollinger Bounce",
            ticker        = ticker,
            strategy_type = "bollinger_bounce",
        )
        self.bb_period = bb_period
        self.bb_std    = bb_std

    async def analyze(self, bars) -> dict:
        if bars is None or len(bars) < self.bb_period + 1:
            logger.warning(f"{self.name} | Barras insuficientes para Bollinger.")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": last_close, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {last_close:.4f} "
            f"(BB lower={last_lower:.4f} / upper={last_upper:.4f})"
        )
        return {"signal_type": signal_type, "price": last_close, "qty": 1.0}


# =============================================================================
# S-4: MACD + VOLUME — Trend Following con confirmación
# =============================================================================

class SentinelMACDVolume(BaseSentinel):
    """
    S-4 — MACD(12,26,9) confirmado con volumen > 1.5x SMA(20) de volumen.
    Cruce alcista MACD/Signal + volumen confirmando → BUY.
    Cruce bajista MACD/Signal + volumen confirmando → SELL.
    Sin confirmación de volumen → HOLD aunque haya cruce.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
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
            ticker        = ticker,
            strategy_type = "macd_volume",
        )
        self.ema_fast          = ema_fast
        self.ema_slow          = ema_slow
        self.signal_span       = signal_span
        self.volume_window     = volume_window
        self.volume_multiplier = volume_multiplier

    async def analyze(self, bars) -> dict:
        min_required = self.ema_slow + self.signal_span + 2
        if bars is None or len(bars) < min_required:
            logger.warning(f"{self.name} | Barras insuficientes para MACD.")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {price:.4f} "
            f"(MACD={macd_curr:.4f} sig={sig_curr:.4f} vol={vol_curr:.0f} avg={vol_avg:.0f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-5: OPENING RANGE BREAKOUT — Momentum intradía
# =============================================================================

class SentinelORB(BaseSentinel):
    """
    S-5 — Marca high/low de la primera vela del día (apertura ET 9:30).
    Cierre rompe arriba del high del rango con volumen > 1.5x SMA(20) → BUY.
    Cierre rompe abajo del low del rango con volumen > 1.5x SMA(20) → SELL.
    El opening range se resetea al cambiar de día (timezone-aware ET).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        volume_window: int = 20,
        volume_multiplier: float = 1.5,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-5 ORB",
            ticker        = ticker,
            strategy_type = "orb_breakout",
        )
        self.volume_window     = volume_window
        self.volume_multiplier = volume_multiplier
        self.opening_range_high: Optional[float] = None
        self.opening_range_low:  Optional[float] = None
        self.opening_range_date = None

    async def analyze(self, bars) -> dict:
        if bars is None or len(bars) < self.volume_window + 1:
            logger.warning(f"{self.name} | Barras insuficientes para ORB.")
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        ts_et    = bars["timestamp"].dt.tz_convert("America/New_York")
        today_et = datetime.now(tz=ZoneInfo("America/New_York")).date()
        today_bars = bars[ts_et.dt.date == today_et]

        if len(today_bars) == 0:
            return {"signal_type": "HOLD", "price": 0.0, "qty": 0.0}

        opening = today_bars.iloc[0]
        if self.opening_range_date != today_et:
            self.opening_range_high = float(opening["high"])
            self.opening_range_low  = float(opening["low"])
            self.opening_range_date = today_et
            logger.info(
                f"{self.name} | Nuevo opening range {today_et}: "
                f"high={self.opening_range_high:.4f} low={self.opening_range_low:.4f}"
            )

        last_close = float(bars["close"].iloc[-1])
        last_vol   = float(bars["volume"].iloc[-1])
        vol_avg    = float(bars["volume"].rolling(self.volume_window).mean().iloc[-1])
        confirmed  = last_vol > self.volume_multiplier * vol_avg

        if last_close > self.opening_range_high and confirmed:
            signal_type = "BUY"
        elif last_close < self.opening_range_low and confirmed:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": last_close, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {last_close:.4f} "
            f"(ORB high={self.opening_range_high:.4f} low={self.opening_range_low:.4f} "
            f"vol={last_vol:.0f} avg={vol_avg:.0f})"
        )
        return {"signal_type": signal_type, "price": last_close, "qty": 1.0}


# =============================================================================
# S-6: EMA TRIPLE — Trend Following
# =============================================================================

class SentinelEMATriple(BaseSentinel):
    """
    S-6 — Tres EMAs (8, 21, 55) verificando alineación de tendencia.
    EMA8 > EMA21 > EMA55 → BUY (tendencia alcista confirmada).
    EMA8 < EMA21 < EMA55 → SELL (tendencia bajista confirmada).
    Cualquier mezcla → HOLD.
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        ema_short: int = 8,
        ema_mid: int = 21,
        ema_long: int = 55,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-6 EMA Triple",
            ticker        = ticker,
            strategy_type = "ema_triple",
        )
        self.ema_short = ema_short
        self.ema_mid   = ema_mid
        self.ema_long  = ema_long

    async def analyze(self, bars) -> dict:
        if bars is None or len(bars) < self.ema_long + 2:
            logger.warning(f"{self.name} | Barras insuficientes para EMA Triple.")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {price:.4f} "
            f"(EMA{self.ema_short}={e_s:.4f} EMA{self.ema_mid}={e_m:.4f} EMA{self.ema_long}={e_l:.4f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-7: VWAP MEAN REVERSION — Intraday
# =============================================================================

class SentinelVWAPReversion(BaseSentinel):
    """
    S-7 — VWAP intradía con bandas de ±2*std del precio típico vs VWAP.
    Precio < VWAP - 2*std → BUY (subvalorado vs fair value).
    Precio > VWAP + 2*std → SELL (sobrevalorado vs fair value).
    El VWAP se resetea cada día (intraday only).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        std_multiplier: float = 2.0,
        min_intraday_bars: int = 5,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-7 VWAP Reversion",
            ticker        = ticker,
            strategy_type = "vwap_reversion",
        )
        self.std_multiplier    = std_multiplier
        self.min_intraday_bars = min_intraday_bars

    async def analyze(self, bars) -> dict:
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {price:.4f} "
            f"(VWAP={v_last:.4f} std={std:.4f})"
        )
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-8: RSI DIVERGENCE — Reversal
# =============================================================================

def _find_swings(values, side: str, k: int = 3) -> list[int]:
    """
    Devuelve índices (posicionales) de swings.
    Swing high: high[i] mayor que las k barras anteriores y k siguientes.
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
    S-8 — Detección de divergencias entre precio y RSI(14).
    Divergencia bajista: nuevo high de precio sin nuevo high de RSI → SELL.
    Divergencia alcista: nuevo low de precio sin nuevo low de RSI → BUY.
    Compara los últimos 2 swing highs/lows confirmados (k=3 barras a cada lado).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        rsi_period: int = 14,
        swing_k: int = 3,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-8 RSI Divergence",
            ticker        = ticker,
            strategy_type = "rsi_divergence",
        )
        self.rsi_period = rsi_period
        self.swing_k    = swing_k

    async def analyze(self, bars) -> dict:
        if bars is None or len(bars) < self.rsi_period + 2 * self.swing_k + 5:
            logger.warning(f"{self.name} | Barras insuficientes para RSI Divergence.")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": price, "qty": 0.0}

        logger.info(f"{self.name} | {self.ticker} | {signal_type} @ {price:.4f} ({detail})")
        return {"signal_type": signal_type, "price": price, "qty": 1.0}


# =============================================================================
# S-9: BOLLINGER SQUEEZE BREAKOUT — Volatility Breakout
# =============================================================================

class SentinelBollingerSqueeze(BaseSentinel):
    """
    S-9 — Bollinger Band Width (BBW) en percentil 10 indica baja volatilidad (squeeze).
    Squeeze activo + cierre rompe banda superior → BUY.
    Squeeze activo + cierre rompe banda inferior → SELL.
    Sin squeeze → HOLD (no operar en volatilidad normal).
    """

    def __init__(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str = BASE_TICKER,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_window: int = 100,
        squeeze_quantile: float = 0.10,
    ):
        super().__init__(
            sentinel_id   = sentinel_id,
            owner_id      = owner_id,
            name          = "S-9 Bollinger Squeeze",
            ticker        = ticker,
            strategy_type = "bollinger_squeeze",
        )
        self.bb_period        = bb_period
        self.bb_std           = bb_std
        self.squeeze_window   = squeeze_window
        self.squeeze_quantile = squeeze_quantile

    async def analyze(self, bars) -> dict:
        min_required = self.bb_period + self.squeeze_window
        if bars is None or len(bars) < min_required:
            logger.warning(f"{self.name} | Barras insuficientes para Squeeze.")
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

        if not self.should_emit(signal_type):
            return {"signal_type": "HOLD", "price": last_close, "qty": 0.0}

        logger.info(
            f"{self.name} | {self.ticker} | {signal_type} @ {last_close:.4f} "
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
