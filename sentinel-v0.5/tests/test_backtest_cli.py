# tests/test_backtest_cli.py
# TDD del CLI backtest.__main__ (#HE-4). Sin red: load_bars se monkeypatchea.

import json

import numpy as np
import pandas as pd
import pytest

from backtest import __main__ as cli
from backtest import runner


def _v_shaped_ohlcv(n_down=70, n_up=90):
    closes = list(np.linspace(120, 50, n_down)) + list(np.linspace(50, 160, n_up))
    idx = pd.date_range("2026-01-02 09:30", periods=len(closes), freq="15min", tz="UTC")
    c = pd.Series(closes, index=idx)
    return pd.DataFrame(
        {"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000.0}, index=idx
    )


@pytest.fixture
def _patched_data(monkeypatch):
    monkeypatch.setattr(cli.data, "load_bars", lambda *a, **k: _v_shaped_ohlcv())


# =============================================================================
# format_report (pura)
# =============================================================================

def test_format_report_contains_metrics():
    r = runner.BacktestResult(
        sentinel_key="s1", ticker="AAPL", n_bars=160,
        metrics={"sharpe": 1.23, "n_trades": 2, "profit_factor": float("inf")},
        native={"return_pct": 12.5, "n_trades": 2},
    )
    text = cli.format_report(r)
    assert "BACKTEST" in text
    assert "AAPL" in text
    assert "Sharpe" in text
    assert "n/a" in text  # métricas ausentes (total_return, etc.) → "n/a" vía _fmt


# =============================================================================
# main — JSON y texto
# =============================================================================

def test_main_json_output(_patched_data, capsys):
    rc = cli.main(["--sentinel", "s1", "--ticker", "TEST", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)  # salida JSON válida (inf convertido a null)
    assert parsed["ticker"] == "TEST"
    assert parsed["sentinel_key"] == "s1"
    assert "metrics" in parsed and "native" in parsed


def test_main_text_output(_patched_data, capsys):
    rc = cli.main(["--sentinel", "s1", "--ticker", "TEST"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BACKTEST" in out
    assert "TEST" in out


def test_main_with_paper_comparison(_patched_data, tmp_path, capsys):
    paper = tmp_path / "paper.json"
    paper.write_text(json.dumps({"sharpe": 0.5, "win_rate": 0.4, "profit_factor": 1.5}))
    rc = cli.main(["--sentinel", "s1", "--ticker", "TEST", "--json", "--paper-json", str(paper)])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "comparison" in parsed
    assert "sharpe" in parsed["comparison"]


def test_main_writes_output_file(_patched_data, tmp_path, capsys):
    out_path = tmp_path / "result.json"
    rc = cli.main(["--sentinel", "s1", "--ticker", "TEST", "--json", "--output", str(out_path)])
    assert rc == 0
    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved["ticker"] == "TEST"


def test_main_unknown_sentinel_returns_1(_patched_data, capsys):
    rc = cli.main(["--sentinel", "s99", "--ticker", "TEST"])
    assert rc == 1
    assert "error" in capsys.readouterr().err
