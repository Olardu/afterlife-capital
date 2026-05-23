# correlation_guard.py
# Módulo anti-concentración del Dispatcher.
# Corre antes de cada orden para evitar que el portafolio acumule posiciones
# altamente correlacionadas. Reduce qty proporcionalmente o descarta la señal.
# Sin estado persistente — trabaja con datos frescos en cada ciclo.

import asyncio
import logging
import math
from decimal import Decimal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    CORRELATION_ROLLING_WINDOW,
    CORRELATION_THRESHOLD,
    MIN_POSITION_SIZE,
)

logger = logging.getLogger("sentinel.correlation_guard")


class CorrelationGuard:
    def __init__(self):
        # Sin estado persistente — cada ciclo trabaja con datos frescos de Alpaca.
        pass

    async def fetch_bars(self, tickers: list[str], window: int) -> dict[str, list[float]]:
        """
        Obtiene los últimos `window` precios de cierre para cada ticker vía Alpaca.

        Usa StockHistoricalDataClient (síncrono) envuelto en asyncio.to_thread
        para no bloquear el grafo LangGraph. Timeout 15s — si Alpaca no responde,
        propaga RuntimeError que el caller (evaluate_signal) captura como
        warning y aprueba la señal sin chequeo de correlación.

        Tickers sin suficientes barras se excluyen del resultado con un WARNING.
        El rango de búsqueda es 5 días calendario — suficiente para garantizar
        60 barras de 15 minutos considerando huecos de fin de semana.

        Returns:
            {ticker: [close_prices]} solo para tickers con datos suficientes.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_bars_sync, tickers, window),
                timeout=15.0,
            )
        except asyncio.TimeoutError as e:
            logger.warning("Timeout (15s) en CorrelationGuard.fetch_bars")
            raise RuntimeError("Alpaca fetch_bars timeout") from e

    def _fetch_bars_sync(self, tickers: list[str], window: int) -> dict[str, list[float]]:
        """Versión síncrona de fetch_bars, ejecutada en thread separado."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed

        client = StockHistoricalDataClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
        )

        now   = datetime.now(tz=ZoneInfo("UTC"))
        start = now - timedelta(days=5)   # margen amplio para cubrir fines de semana

        request = StockBarsRequest(
            symbol_or_symbols=tickers,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=now,
            feed=DataFeed.IEX,
        )

        try:
            bars_df = client.get_stock_bars(request).df
        except Exception as e:
            raise RuntimeError(f"Alpaca fetch_bars falló: {e}") from e

        result: dict[str, list[float]] = {}
        for ticker in tickers:
            try:
                ticker_bars = bars_df.loc[ticker]
            except KeyError:
                logger.warning(f"Ticker {ticker} sin datos en Alpaca. Excluido del análisis.")
                continue

            closes = ticker_bars["close"].tolist()[-window:]
            if len(closes) < window:
                logger.warning(
                    f"Ticker {ticker} tiene solo {len(closes)}/{window} barras. "
                    "Excluido del análisis de correlación."
                )
                continue

            result[ticker] = closes

        return result

    def calculate_correlation(
        self, prices_a: list[float], prices_b: list[float]
    ) -> float:
        """
        Calcula correlación de Pearson entre dos series de precios.

        r = Σ((xi − x̄)(yi − ȳ)) / sqrt(Σ(xi − x̄)² · Σ(yi − ȳ)²)

        Retorna 0.0 si alguna de las series es constante (std = 0),
        ya que la correlación no está definida en ese caso.

        Requiere len(prices_a) == len(prices_b).
        """
        n = len(prices_a)
        if n != len(prices_b) or n == 0:
            return 0.0

        mean_a = sum(prices_a) / n
        mean_b = sum(prices_b) / n

        deviations_a = [x - mean_a for x in prices_a]
        deviations_b = [y - mean_b for y in prices_b]

        numerator    = sum(da * db for da, db in zip(deviations_a, deviations_b))
        sum_sq_a     = sum(da ** 2 for da in deviations_a)
        sum_sq_b     = sum(db ** 2 for db in deviations_b)
        denominator  = math.sqrt(sum_sq_a * sum_sq_b)

        if denominator == 0.0:
            return 0.0

        return numerator / denominator

    async def evaluate_signal(
        self,
        incoming_ticker: str,
        incoming_qty: Decimal,
        open_positions: list[dict],
        performance_scores: list[dict],
    ) -> dict:
        """
        Evalúa si una señal entrante puede ejecutarse dada la cartera actual.

        Parámetros:
            incoming_ticker:   ticker de la señal a evaluar
            incoming_qty:      tamaño de posición propuesto por el Dispatcher (Decimal;
                               se convierte defensivamente si un caller aún pasa float)
            open_positions:    [{ticker, qty, sentinel_id}, ...]
            performance_scores: [{sentinel_id, ticker, sharpe_ratio}, ...]
                               usado para priorizar señales (descendente por sharpe)

        Flujo:
            1. Sin posiciones abiertas → aprueba inmediatamente
            2. fetch_bars() para incoming + todos los tickers abiertos
            3. Correlación de Pearson entre incoming y cada posición abierta
            4. avg_correlation = promedio de todas las correlaciones calculadas
            5. Si avg_correlation > CORRELATION_THRESHOLD:
                   reduction_factor = 1 − (avg − threshold) / (1 − threshold)
                   adjusted_qty = incoming_qty × reduction_factor
                   Si adjusted_qty < MIN_POSITION_SIZE → descartar señal
            6. Si avg_correlation ≤ CORRELATION_THRESHOLD → qty sin cambios

        Retorna:
            {
                "approved":        bool,
                "original_qty":    Decimal,
                "adjusted_qty":    Decimal,
                "avg_correlation": float,
                "reason":          str   # "approved" | "reduced" | "discarded_high_correlation"
            }
        """
        # qty es monetaria → Decimal en todo el pipeline (#H-4). Conversión defensiva:
        # acepta callers que aún pasen float durante la migración gradual del dispatcher.
        incoming_qty = Decimal(str(incoming_qty))

        if not open_positions:
            logger.debug(f"Sin posiciones abiertas — señal {incoming_ticker} aprobada directamente.")
            return {
                "approved":        True,
                "original_qty":    incoming_qty,
                "adjusted_qty":    incoming_qty,
                "avg_correlation": 0.0,
                "reason":          "approved",
            }

        open_tickers = list({pos["ticker"] for pos in open_positions})
        all_tickers  = list({incoming_ticker} | set(open_tickers))

        try:
            bars = await self.fetch_bars(all_tickers, CORRELATION_ROLLING_WINDOW)
        except Exception as e:
            logger.warning(
                f"fetch_bars falló ({e}). Aprobando señal {incoming_ticker} "
                "con warning — no bloquear el sistema por error de datos."
            )
            return {
                "approved":        True,
                "original_qty":    incoming_qty,
                "adjusted_qty":    incoming_qty,
                "avg_correlation": 0.0,
                "reason":          "approved",
            }

        if incoming_ticker not in bars:
            logger.warning(
                f"Sin barras para {incoming_ticker}. Aprobando con warning."
            )
            return {
                "approved":        True,
                "original_qty":    incoming_qty,
                "adjusted_qty":    incoming_qty,
                "avg_correlation": 0.0,
                "reason":          "approved",
            }

        incoming_prices = bars[incoming_ticker]
        correlations: list[float] = []

        for pos in open_positions:
            pos_ticker = pos["ticker"]
            if pos_ticker == incoming_ticker:
                # Misma posición ya abierta — correlación perfecta, contar como 1.0
                correlations.append(1.0)
                continue
            if pos_ticker not in bars:
                logger.debug(f"Sin barras para posición abierta {pos_ticker}. Omitido del cálculo.")
                continue
            r = self.calculate_correlation(incoming_prices, bars[pos_ticker])
            correlations.append(abs(r))   # correlación negativa también es concentración

        if not correlations:
            avg_correlation = 0.0
        else:
            avg_correlation = sum(correlations) / len(correlations)

        logger.debug(
            f"CorrelationGuard | {incoming_ticker} | "
            f"avg_corr={avg_correlation:.4f} threshold={CORRELATION_THRESHOLD}"
        )

        if avg_correlation <= CORRELATION_THRESHOLD:
            return {
                "approved":        True,
                "original_qty":    incoming_qty,
                "adjusted_qty":    incoming_qty,
                "avg_correlation": avg_correlation,
                "reason":          "approved",
            }

        # Reducción proporcional — cuanto más cerca de 1.0, más se reduce
        reduction_factor = 1.0 - (avg_correlation - CORRELATION_THRESHOLD) / (1.0 - CORRELATION_THRESHOLD)
        adjusted_qty     = incoming_qty * Decimal(str(reduction_factor))

        if adjusted_qty < Decimal(MIN_POSITION_SIZE):
            logger.info(
                f"Señal {incoming_ticker} DESCARTADA — "
                f"avg_corr={avg_correlation:.4f} qty ajustada={adjusted_qty:.4f} "
                f"< MIN_POSITION_SIZE={MIN_POSITION_SIZE}"
            )
            return {
                "approved":        False,
                "original_qty":    incoming_qty,
                "adjusted_qty":    Decimal("0"),
                "avg_correlation": avg_correlation,
                "reason":          "discarded_high_correlation",
            }

        logger.info(
            f"Señal {incoming_ticker} REDUCIDA — "
            f"avg_corr={avg_correlation:.4f} | "
            f"qty: {incoming_qty:.4f} → {adjusted_qty:.4f} "
            f"(factor={reduction_factor:.4f})"
        )
        return {
            "approved":        True,
            "original_qty":    incoming_qty,
            "adjusted_qty":    adjusted_qty,
            "avg_correlation": avg_correlation,
            "reason":          "reduced",
        }
