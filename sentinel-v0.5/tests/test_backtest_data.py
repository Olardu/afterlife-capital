# tests/test_backtest_data.py
# TDD de backtest.data — normalización y carga de OHLCV (#HE-4).
# La carga vía Alpaca toca red/SDK: se testea por monkeypatch del loader, no por red real.

import pandas as pd
import pytest

from backtest import data


def _lowercase_df():
    """DataFrame estilo Alpaca .df.reset_index(): columnas minúsculas + timestamp + extras."""
    return pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2026-01-02 09:30", "2026-01-02 09:45", "2026-01-02 10:00"]
        ),
        "open":  [10.0, 11.0, 12.0],
        "high":  [10.5, 11.5, 12.5],
        "low":   [9.5, 10.5, 11.5],
        "close": [11.0, 12.0, 11.5],
        "volume": [1000, 1100, 900],
        "trade_count": [50, 55, 40],
        "vwap": [10.2, 11.2, 12.1],
    })


# =============================================================================
# normalize_ohlcv
# =============================================================================

def test_normalize_lowercase_to_backtesting_columns():
    out = data.normalize_ohlcv(_lowercase_df())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert len(out) == 3
    assert out["Close"].iloc[0] == 11.0


def test_normalize_drops_extra_columns():
    out = data.normalize_ohlcv(_lowercase_df())
    assert "trade_count" not in out.columns
    assert "vwap" not in out.columns
    assert "timestamp" not in out.columns


def test_normalize_sorts_by_time():
    df = _lowercase_df().iloc[::-1].reset_index(drop=True)  # invertido
    out = data.normalize_ohlcv(df)
    assert out.index.is_monotonic_increasing
    assert out["Open"].iloc[0] == 10.0  # la barra más temprana quedó primera


def test_normalize_already_capitalized_is_idempotent():
    once = data.normalize_ohlcv(_lowercase_df())
    twice = data.normalize_ohlcv(once)
    pd.testing.assert_frame_equal(once, twice)


def test_normalize_raises_on_missing_column():
    bad = _lowercase_df().drop(columns=["close"])
    with pytest.raises(ValueError, match="close|Close"):
        data.normalize_ohlcv(bad)


def test_normalize_coerces_to_float():
    out = data.normalize_ohlcv(_lowercase_df())
    assert out["Volume"].dtype == float


# =============================================================================
# load_csv
# =============================================================================

def test_load_csv_roundtrip(tmp_path):
    csv = tmp_path / "bars.csv"
    csv.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-02 09:30,10,10.5,9.5,11,1000\n"
        "2026-01-02 09:45,11,11.5,10.5,12,1100\n"
    )
    out = data.load_csv(str(csv))
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out) == 2
    assert isinstance(out.index, pd.DatetimeIndex)


# =============================================================================
# load_bars (dispatcher)
# =============================================================================

def test_load_bars_csv_source(tmp_path):
    csv = tmp_path / "bars.csv"
    csv.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-02 09:30,10,10.5,9.5,11,1000\n"
        "2026-01-02 09:45,11,11.5,10.5,12,1100\n"
    )
    out = data.load_bars("AAPL", source="csv", csv_path=str(csv))
    assert len(out) == 2


def test_load_bars_alpaca_delegates(monkeypatch):
    captured = {}

    def fake_alpaca(ticker, start, end, timeframe="15Min", feed="IEX"):
        captured.update(ticker=ticker, start=start, end=end, timeframe=timeframe)
        return data.normalize_ohlcv(_lowercase_df())

    monkeypatch.setattr(data, "load_alpaca", fake_alpaca)
    out = data.load_bars("MSFT", source="alpaca", start="2026-01-01", end="2026-02-01")
    assert captured["ticker"] == "MSFT"
    assert captured["start"] == "2026-01-01"
    assert len(out) == 3


def test_load_bars_unknown_source_raises():
    with pytest.raises(ValueError, match="source"):
        data.load_bars("AAPL", source="bloomberg")


def test_load_bars_csv_requires_path():
    with pytest.raises(ValueError, match="csv_path"):
        data.load_bars("AAPL", source="csv")
