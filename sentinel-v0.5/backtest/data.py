# backtest/data.py
# Carga de barras OHLCV para el framework de backtesting (#HE-4).
#
# Backtesting.py exige un DataFrame indexado por datetime con columnas
# EXACTAS: Open, High, Low, Close, Volume (capitalizadas). `normalize_ohlcv`
# es la pieza pura que adapta cualquier origen a ese contrato; los loaders
# (Alpaca histórico, CSV, Yahoo) delegan en ella.

import pandas as pd

# Mapeo nombre-lógico → columna que espera Backtesting.py.
_OHLCV = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
_TIME_COLS = ("timestamp", "time", "date", "datetime")


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza un DataFrame OHLCV al contrato de Backtesting.py:
    índice DatetimeIndex ordenado + columnas Open/High/Low/Close/Volume (float).
    Acepta columnas en minúscula (estilo Alpaca .df) o ya capitalizadas, con o
    sin columna de tiempo (si falta, se asume que el índice ya es de tiempo).
    Descarta columnas extra (trade_count, vwap, ...). Lanza ValueError si falta
    alguna de las 5 columnas OHLCV.
    """
    df = df.copy()

    # 1) Columna de tiempo → índice (si existe como columna).
    time_col = next((c for c in df.columns if str(c).lower() in _TIME_COLS), None)
    if time_col is not None:
        df = df.set_index(time_col)
    df.index = pd.to_datetime(df.index)

    # 2) Renombrar OHLCV a capitalizado (case-insensitive).
    lower_map = {str(c).lower(): c for c in df.columns}
    rename = {lower_map[key]: cap for key, cap in _OHLCV.items() if key in lower_map}
    df = df.rename(columns=rename)

    # 3) Validar presencia de las 5 columnas.
    missing = [cap for cap in _OHLCV.values() if cap not in df.columns]
    if missing:
        raise ValueError(f"faltan columnas OHLCV tras normalizar: {missing}")

    # 4) Quedarse solo con OHLCV (float) y ordenar por tiempo.
    out = df[list(_OHLCV.values())].astype(float)
    return out.sort_index()


def load_csv(path: str) -> pd.DataFrame:
    """Carga barras desde un CSV con columnas open/high/low/close/volume + timestamp."""
    return normalize_ohlcv(pd.read_csv(path))


def _parse_timeframe(timeframe: str):
    """'15Min' / '1Hour' / '1Day' → (amount, TimeFrameUnit). Default 15 minutos."""
    from alpaca.data.timeframe import TimeFrameUnit

    units = {"min": TimeFrameUnit.Minute, "hour": TimeFrameUnit.Hour, "day": TimeFrameUnit.Day}
    tf = timeframe.strip().lower()
    for suffix, unit in units.items():
        if tf.endswith(suffix):
            amount = tf[: -len(suffix)] or "1"
            return int(amount), unit
    raise ValueError(f"timeframe no reconocido: {timeframe!r} (ej. '15Min', '1Hour', '1Day')")


def load_alpaca(ticker: str, start, end, timeframe: str = "15Min", feed: str = "IEX") -> pd.DataFrame:
    """
    Descarga barras históricas de Alpaca (mismo cliente/feed que BaseSentinel).
    `start`/`end`: datetime o str ISO. Devuelve OHLCV normalizado.
    """
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

    amount, unit = _parse_timeframe(timeframe)
    client = StockHistoricalDataClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY)
    request = StockBarsRequest(
        symbol_or_symbols=[ticker],
        timeframe=TimeFrame(amount, unit),
        start=pd.to_datetime(start),
        end=pd.to_datetime(end),
        feed=DataFeed[feed.upper()],
    )
    bars_df = client.get_stock_bars(request).df
    if bars_df.empty:
        raise ValueError(f"Alpaca no devolvió barras para {ticker} entre {start} y {end}")
    return normalize_ohlcv(bars_df.loc[ticker].reset_index())


def load_yahoo(ticker: str, start, end, interval: str = "15m") -> pd.DataFrame:
    """Fallback Yahoo Finance (yfinance lazy-import; opcional, no en requirements)."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError("yfinance no instalado: pip install yfinance, o usá source='alpaca'/'csv'") from exc

    df = yf.download(ticker, start=start, end=end, interval=interval, progress=False)
    if df.empty:
        raise ValueError(f"Yahoo no devolvió barras para {ticker} entre {start} y {end}")
    df = df.reset_index()
    return normalize_ohlcv(df)


def load_bars(ticker: str, source: str = "alpaca", start=None, end=None,
              timeframe: str = "15Min", feed: str = "IEX", csv_path: str | None = None) -> pd.DataFrame:
    """Dispatcher de carga. source ∈ {alpaca, csv, yahoo}."""
    if source == "csv":
        if not csv_path:
            raise ValueError("source='csv' requiere csv_path")
        return load_csv(csv_path)
    if source == "alpaca":
        return load_alpaca(ticker, start, end, timeframe=timeframe, feed=feed)
    if source == "yahoo":
        return load_yahoo(ticker, start, end)
    raise ValueError(f"source desconocido: {source!r} (alpaca | csv | yahoo)")
