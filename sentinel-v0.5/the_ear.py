# the_ear.py
# Agente de contexto macro y protección del sistema Sentinel v0.5.
# Monitorea NewsAPI, VIX y SPY para activar Circuit Breaker o Parking Brake.
# Nunca debe crashear el sistema — todos los errores se manejan con gracia.
# VIX se aproxima con VIXY (ETF proxy) ya que Alpaca IEX no expone el índice directo.

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    NEWS_API_KEY,
    NEWS_FETCH_INTERVAL_SECONDS,
    PARKING_BRAKE_TIME,
    RISK_SCORE_VETO_THRESHOLD,
    SPY_CIRCUIT_BREAKER_THRESHOLD,
    TIMEZONE,
    VIX_CIRCUIT_BREAKER_THRESHOLD,
)
from historian import Historian

logger = logging.getLogger("sentinel.the_ear")

# VIXY como proxy de VIX — Alpaca IEX no expone el índice ^VIX directamente
VIX_PROXY_TICKER = "VIXY"
SPY_TICKER = "SPY"

_NEGATIVE_KEYWORDS = {
    "crash", "recession", "collapse", "crisis", "sell-off",
    "bankruptcy", "default", "downgrade", "panic", "war",
    "tariff", "sanctions",
}
_POSITIVE_KEYWORDS = {
    "rally", "surge", "growth", "recovery", "bullish", "record high",
}


class TheEar:
    def __init__(self, historian: Historian):
        self.historian = historian
        self.last_risk_score: float = 0.0
        self.circuit_breaker_active: bool = False
        self.parking_brake_active: bool = False
        self._last_vix_change: float | None = None
        self._last_spy_change: float | None = None
        # evaluate() es llamado en paralelo por start_polling() (task background)
        # y por Dispatcher.run_cycle() (task principal). Sin lock, ambos mutan
        # el estado compartido y duplican filas en macro_events. (#H-2)
        self._eval_lock = asyncio.Lock()

    async def fetch_news(self) -> list[dict]:
        """
        Consulta NewsAPI /v2/everything con query financiera.
        Si la API falla retorna lista vacía — el caller usa last_risk_score.

        Returns:
            Lista de artículos [{title, description, publishedAt}].
        """
        if not NEWS_API_KEY:
            logger.warning("NEWS_API_KEY no configurada. Saltando fetch de noticias.")
            return []

        url = "https://newsapi.org/v2/everything"
        params = {
            "q":        "stock market OR S&P 500 OR Federal Reserve OR recession",
            "language": "en",
            "sortBy":   "publishedAt",
            "pageSize": 20,
        }
        # API key en header para evitar que aparezca en logs de URL de NewsAPI
        headers = {"X-Api-Key": NEWS_API_KEY}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"NewsAPI respondió {resp.status}. Usando último risk_score conocido.")
                        return []
                    data = await resp.json()
                    articles = data.get("articles", [])
                    logger.debug(f"NewsAPI: {len(articles)} artículos recibidos.")
                    return [
                        {
                            "title":       a.get("title", ""),
                            "description": a.get("description", ""),
                            "publishedAt": a.get("publishedAt", ""),
                        }
                        for a in articles
                    ]
        except asyncio.TimeoutError:
            logger.warning("NewsAPI timeout. Usando último risk_score conocido.")
            return []
        except aiohttp.ClientError as e:
            logger.warning(f"Error de red al consultar NewsAPI: {e}. Usando último risk_score conocido.")
            return []

    def calculate_risk_score(self, articles: list[dict]) -> float:
        """
        Calcula un risk_score macro (0.0 – 1.0) por análisis de keywords.

        Peso por artículo:
            +1.0 por keyword negativa encontrada en título o descripción
            -0.5 por keyword positiva encontrada en título o descripción

        Score final = clamp((neg_hits - pos_hits * 0.5) / total_articles, 0.0, 1.0)

        Es un heurístico simple — suficiente para paper trading v0.5.
        """
        if not articles:
            logger.debug("Sin artículos para calcular risk_score. Retornando último conocido.")
            return self.last_risk_score

        neg_hits = 0.0
        pos_hits = 0.0

        for article in articles:
            text = f"{article.get('title', '')} {article.get('description', '')}".lower()
            neg_hits += sum(1 for kw in _NEGATIVE_KEYWORDS if kw in text)
            pos_hits += sum(1 for kw in _POSITIVE_KEYWORDS if kw in text)

        raw = (neg_hits - pos_hits * 0.5) / len(articles)
        score = max(0.0, min(1.0, raw))

        logger.debug(f"Risk score calculado: {score:.4f} (neg={neg_hits} pos={pos_hits} arts={len(articles)})")
        return score

    async def check_circuit_breaker(self) -> bool:
        """
        Consulta barras de 15 minutos de VIXY y SPY vía Alpaca para detectar
        movimientos extremos. Activa circuit_breaker_active si:
            - VIXY cambió > VIX_CIRCUIT_BREAKER_THRESHOLD %
            - SPY cambió < SPY_CIRCUIT_BREAKER_THRESHOLD %

        El cálculo de barras se corre en un executor para no bloquear el loop.

        Returns:
            True si el circuit breaker se activa en esta llamada.
        """
        try:
            vix_change, spy_change = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_price_changes),
                timeout=15.0,
            )
            self._last_vix_change = vix_change
            self._last_spy_change = spy_change
        except asyncio.TimeoutError:
            logger.warning("Timeout (15s) al consultar precios Alpaca para circuit breaker")
            return self.circuit_breaker_active
        except Exception as e:
            logger.warning(f"Error al consultar precios Alpaca para circuit breaker: {e}")
            return self.circuit_breaker_active

        triggered = (
            vix_change >= VIX_CIRCUIT_BREAKER_THRESHOLD
            or spy_change <= SPY_CIRCUIT_BREAKER_THRESHOLD
        )

        if triggered and not self.circuit_breaker_active:
            logger.warning(
                f"CIRCUIT BREAKER ACTIVADO — "
                f"VIXY cambio={vix_change:.2f}% | SPY cambio={spy_change:.2f}%"
            )
        elif not triggered and self.circuit_breaker_active:
            logger.info("Circuit breaker desactivado — condiciones normalizadas.")

        self.circuit_breaker_active = triggered
        return triggered

    def _fetch_price_changes(self) -> tuple[float, float]:
        """
        Descarga las últimas 2 barras de 15 minutos para VIXY y SPY usando
        alpaca-py StockHistoricalDataClient (síncrono, corre en executor).

        Returns:
            Tupla (vix_change_pct, spy_change_pct).
        """
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from alpaca.data.enums import DataFeed

        client = StockHistoricalDataClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
        )

        now   = datetime.now(tz=ZoneInfo("UTC"))
        start = now - timedelta(minutes=45)  # margen para garantizar 2 barras completas

        request = StockBarsRequest(
            symbol_or_symbols=[VIX_PROXY_TICKER, SPY_TICKER],
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=now,
            feed=DataFeed.IEX,
        )
        bars = client.get_stock_bars(request).df

        def pct_change(symbol: str) -> float:
            if symbol not in bars.index.get_level_values(0):
                return 0.0
            symbol_bars = bars.loc[symbol].tail(2)
            if len(symbol_bars) < 2:
                return 0.0
            prev  = float(symbol_bars.iloc[0]["close"])
            close = float(symbol_bars.iloc[1]["close"])
            return ((close - prev) / prev) * 100 if prev != 0 else 0.0

        return pct_change(VIX_PROXY_TICKER), pct_change(SPY_TICKER)

    def check_parking_brake(self) -> bool:
        """
        Activa el parking brake si la hora actual en ET >= PARKING_BRAKE_TIME.
        Loggea el cambio de estado solo cuando cambia para evitar spam.

        Returns:
            True si el parking brake está activo.
        """
        now_et = datetime.now(tz=ZoneInfo(TIMEZONE))
        brake_h, brake_m = map(int, PARKING_BRAKE_TIME.split(":"))
        active = (now_et.hour, now_et.minute) >= (brake_h, brake_m)

        if active and not self.parking_brake_active:
            logger.info(f"PARKING BRAKE activado a las {now_et.strftime('%H:%M')} ET.")
        elif not active and self.parking_brake_active:
            logger.info("Parking brake desactivado — nueva sesión.")

        self.parking_brake_active = active
        return active

    async def evaluate(self) -> dict:
        """
        Método principal. Llamado por el Dispatcher en cada ciclo de decisión.

        Flujo:
            1. Verifica Parking Brake
            2. Fetch noticias + calcula risk_score
            3. Verifica Circuit Breaker
            4. Persiste evento macro en Historian
            5. Retorna estado consolidado

        can_trade es False si cualquier protección está activa o risk_score > 0.7.

        El cuerpo se envuelve en self._eval_lock para evitar ejecución concurrente
        desde start_polling() y Dispatcher.run_cycle() — ver __init__ y #H-2.

        Returns:
            dict con risk_score, circuit_breaker, parking_brake y can_trade.
        """
        async with self._eval_lock:
            parking_brake = self.check_parking_brake()

            articles   = await self.fetch_news()
            risk_score = self.calculate_risk_score(articles)
            if articles:
                self.last_risk_score = risk_score
            else:
                risk_score = self.last_risk_score

            circuit_breaker = await self.check_circuit_breaker()

            try:
                await self.historian.record_macro_event(
                    risk_score=risk_score,
                    vix_level=self._last_vix_change,
                    spy_change_15min=self._last_spy_change,
                    circuit_breaker_triggered=circuit_breaker,
                )
            except Exception as e:
                logger.error(f"Error al persistir macro event: {e}")

            can_trade = not (parking_brake or circuit_breaker or risk_score > RISK_SCORE_VETO_THRESHOLD)

            logger.info(
                f"Ear evaluate — risk={risk_score:.4f} "
                f"circuit_breaker={circuit_breaker} parking_brake={parking_brake} "
                f"can_trade={can_trade}"
            )

            return {
                "risk_score":      risk_score,
                "circuit_breaker": circuit_breaker,
                "parking_brake":   parking_brake,
                "can_trade":       can_trade,
            }

    async def start_polling(self):
        """
        Loop infinito que llama evaluate() cada NEWS_FETCH_INTERVAL_SECONDS.
        Un error en un ciclo no mata el loop — se loggea y se continúa.
        """
        logger.info(
            f"The Ear iniciado — polling cada {NEWS_FETCH_INTERVAL_SECONDS}s "
            f"({NEWS_FETCH_INTERVAL_SECONDS // 60} min)."
        )
        while True:
            try:
                await self.evaluate()
            except Exception as e:
                logger.error(f"Error inesperado en ciclo de The Ear: {e}")
            await asyncio.sleep(NEWS_FETCH_INTERVAL_SECONDS)
