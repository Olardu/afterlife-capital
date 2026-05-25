# regime_classifier.py
# S-10 — meta-agente clasificador de régimen de mercado.
# Se ejecuta una vez al día, antes de la apertura. Entrena un Random Forest
# sobre 25 años de barras diarias de SPY y clasifica la sesión como
# BULL, NEUTRAL o BEAR. El Dispatcher usa el régimen para ajustar agresividad.

import asyncio
import logging
import time as time_module
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    BASE_TICKER,
    SPY_HISTORICAL_YEARS,
)

logger = logging.getLogger("sentinel.regime_classifier")

_FEATURE_COLS = [
    "return_1d",
    "return_5d",
    "return_20d",
    "volatility_20d",
    "sma_ratio",
    "volume_ratio",
]

# Días calendario a descargar para garantizar ~60 barras de trading (SMA50 + margen)
_RECENT_BARS_LOOKBACK_DAYS = 90


class RegimeClassifier:
    def __init__(self):
        self.model = None
        self.current_regime: str = "NEUTRAL"   # default hasta primer clasificación
        self.last_classified_date = None

    # -------------------------------------------------------------------------
    # Feature engineering
    # -------------------------------------------------------------------------

    def build_features(self, bars_df) -> list[list[float]]:
        """
        Calcula features técnicas sobre un DataFrame de barras diarias de SPY.

        Features por barra:
            return_1d     — retorno diario (close / prev_close - 1)
            return_5d     — retorno acumulado 5 días
            return_20d    — retorno acumulado 20 días
            volatility_20d — std de retornos diarios rolling 20 días
            sma_ratio     — close / SMA(50) - 1 (distancia relativa a la media)
            volume_ratio  — volume / SMA(volume, 20)

        Las primeras ~49 filas se descartan (NaN por SMA50).

        Returns:
            Lista de feature vectors [return_1d, ..., volume_ratio].
        """
        df = bars_df.copy()

        df["return_1d"]      = df["close"].pct_change(1)
        df["return_5d"]      = df["close"].pct_change(5)
        df["return_20d"]     = df["close"].pct_change(20)
        df["volatility_20d"] = df["return_1d"].rolling(20).std()
        df["sma_50"]         = df["close"].rolling(50).mean()
        df["sma_ratio"]      = df["close"] / df["sma_50"] - 1
        df["vol_sma_20"]     = df["volume"].rolling(20).mean()
        df["volume_ratio"]   = df["volume"] / df["vol_sma_20"]

        df_clean = df.dropna(subset=_FEATURE_COLS)
        return df_clean[_FEATURE_COLS].values.tolist()

    def build_labels(self, bars_df) -> list[str]:
        """
        Genera etiquetas de régimen basadas en el retorno forward de 5 días.

            forward_return > +1%  → BULL
            forward_return < -1%  → BEAR
            else                  → NEUTRAL

        Las últimas 5 filas se descartan (no tienen retorno forward).
        Solo se usa en entrenamiento — no en predicción live.

        Returns:
            Lista de etiquetas ['BULL'|'NEUTRAL'|'BEAR'] para filas 0..N-6.
        """
        df = bars_df.copy()
        # #TD: verificado sin off-by-one. pct_change(5)[i] = close[i]/close[i-5]-1;
        # shift(-5) lo mueve a forward_return[i] = close[i+5]/close[i]-1 (retorno de los
        # PRÓXIMOS 5 bars). Las últimas 5 filas quedan NaN y se dropean → etiquetas 0..N-6.
        df["forward_return"] = df["close"].pct_change(5).shift(-5)
        df_clean = df.dropna(subset=["forward_return"])

        labels = []
        for fr in df_clean["forward_return"]:
            if fr > 0.01:
                labels.append("BULL")
            elif fr < -0.01:
                labels.append("BEAR")
            else:
                labels.append("NEUTRAL")
        return labels

    # -------------------------------------------------------------------------
    # Entrenamiento
    # -------------------------------------------------------------------------

    def train(self, bars_df):
        """
        Entrena el Random Forest con los features y labels derivados de bars_df.

        Alineación:
            build_features descarta las primeras ~49 filas (NaN por SMA50).
            build_labels descarta las últimas 5 filas (sin retorno forward).
            La intersección válida es bars[49..N-6].

        Split: últimos 252 días (1 año bursátil) como test set.
        Loggea accuracy y tiempo de entrenamiento.
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score
        import numpy as np

        t0 = time_module.time()

        features = self.build_features(bars_df)
        labels   = self.build_labels(bars_df)

        # feature_offset = cuántas filas iniciales fueron descartadas por build_features
        feature_offset = len(bars_df) - len(features)
        # n_samples = intersección válida (features hasta N-6, labels desde feature_offset)
        n_samples = min(len(features) - 5, len(labels) - feature_offset)

        if n_samples <= 0:
            logger.error("Datos insuficientes para entrenar RegimeClassifier.")
            return

        X = np.array(features[:n_samples])
        y = np.array(labels[feature_offset : feature_offset + n_samples])

        split = max(len(X) - 252, 1)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            random_state=42,
        )
        self.model.fit(X_train, y_train)

        accuracy = accuracy_score(y_test, self.model.predict(X_test))
        elapsed  = time_module.time() - t0

        logger.info(
            f"RegimeClassifier entrenado en {elapsed:.1f}s — "
            f"accuracy={accuracy:.4f} | train={len(X_train)} test={len(X_test)} muestras"
        )

    # -------------------------------------------------------------------------
    # Datos históricos
    # -------------------------------------------------------------------------

    async def fetch_training_data(self):
        """
        Descarga SPY_HISTORICAL_YEARS años de barras diarias vía Alpaca.

        NOTA: 15s puede ser corto para descargar 25 años de SPY desde Alpaca.
        Cuando se reactive S-10 (hoy desactivado por accuracy insuficiente),
        evaluar si elevar el timeout específicamente para este path.

        Returns:
            DataFrame con columnas [date, open, high, low, close, volume].
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_bars_sync, SPY_HISTORICAL_YEARS * 365),
                timeout=15.0,
            )
        except asyncio.TimeoutError as e:
            logger.error("Timeout (15s) descargando training data de SPY")
            raise RuntimeError("Alpaca fetch_training_data timeout") from e

    def _fetch_bars_sync(self, lookback_days: int):
        """Descarga barras diarias de BASE_TICKER. Ejecutado en thread separado."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import DataFeed

        client = StockHistoricalDataClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
        )

        end   = datetime.now(tz=ZoneInfo("UTC"))
        start = end - timedelta(days=lookback_days)

        request = StockBarsRequest(
            symbol_or_symbols=[BASE_TICKER],
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )

        bars_df = client.get_stock_bars(request).df
        spy_bars = bars_df.loc[BASE_TICKER].reset_index()
        spy_bars = spy_bars.rename(columns={"timestamp": "date"})

        logger.info(f"Barras descargadas: {len(spy_bars)} días de {BASE_TICKER}.")
        return spy_bars

    # -------------------------------------------------------------------------
    # Inicialización y clasificación
    # -------------------------------------------------------------------------

    async def initialize(self):
        """
        Descarga datos históricos y entrena el modelo.
        Llamar una sola vez al arrancar el sistema, antes de abrir el mercado.
        """
        # S-10 desactivado — no descargar 25 años de datos ni entrenar RF.
        # Para reactivar: eliminar las dos líneas siguientes.
        logger.info("RegimeClassifier desactivado temporalmente (accuracy insuficiente). Régimen fijo: NEUTRAL.")
        return

        logger.info(
            f"Inicializando RegimeClassifier — "
            f"descargando {SPY_HISTORICAL_YEARS} años de {BASE_TICKER}..."
        )
        t0 = time_module.time()

        bars_df = await self.fetch_training_data()
        self.train(bars_df)

        logger.info(f"RegimeClassifier listo. Tiempo total: {time_module.time() - t0:.1f}s.")

    async def classify_today(self) -> str:
        """
        Clasifica el régimen de la sesión actual.

        Si ya se clasificó hoy retorna self.current_regime sin recalcular.
        Si el modelo no está entrenado retorna NEUTRAL con warning.
        Si ocurre cualquier error retorna el último régimen conocido.

        Returns:
            'BULL', 'NEUTRAL' o 'BEAR'.
        """
        # =====================================================================
        # TODO: S-10 desactivado temporalmente — accuracy 0.3849 no es útil.
        # Reactivar cuando:
        #   1. Haya 50-100 trades reales para evaluar correlación régimen/resultados
        #   2. Se agreguen features adicionales (RSI, MACD, breadth, yield curve)
        #   3. Accuracy supere 0.50 en test set
        # Para reactivar: eliminar las dos líneas siguientes.
        # Fecha de desactivación: 25 abril 2026
        # =====================================================================
        return "NEUTRAL"

        # #TD-22: TODO el bloque de abajo queda INALCANZABLE mientras S-10 esté
        # desactivado (el return de arriba corta). Se conserva a propósito — es la
        # lógica real de clasificación que se reactiva al quitar el early return.
        if self.model is None:
            logger.warning("RegimeClassifier sin modelo entrenado. Retornando NEUTRAL.")
            return "NEUTRAL"

        today = datetime.now(tz=ZoneInfo("America/New_York")).date()
        if self.last_classified_date == today:
            logger.debug(f"Régimen ya clasificado hoy: {self.current_regime}.")
            return self.current_regime

        try:
            bars_df  = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_bars_sync, _RECENT_BARS_LOOKBACK_DAYS),
                timeout=15.0,
            )
            features = self.build_features(bars_df)

            if not features:
                logger.warning("Sin features suficientes para clasificar. Retornando NEUTRAL.")
                return "NEUTRAL"

            regime = self.model.predict([features[-1]])[0]

            self.current_regime      = regime
            self.last_classified_date = today

            logger.info(f"Régimen del día {today}: {regime}")
            return regime

        except asyncio.TimeoutError:
            logger.error(
                f"Timeout (15s) al clasificar régimen. "
                f"Retornando último conocido: {self.current_regime}."
            )
            return self.current_regime
        except Exception as e:
            logger.error(
                f"Error al clasificar régimen: {e}. "
                f"Retornando último conocido: {self.current_regime}."
            )
            return self.current_regime

    def get_regime(self) -> str:
        """
        Retorna el régimen actual sin await.
        Usado por el Dispatcher en cada ciclo de decisión.
        """
        return self.current_regime
