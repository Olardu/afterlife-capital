"""Tests T-O #TD-5 + #TD-6 (the_ear).

#TD-5: pct_change / _fetch_price_changes retorna None ante sin-datos (antes 0.0).
       check_circuit_breaker distingue None (no evaluar ese factor) de 0.0 (0% real).
#TD-6: flag news_disabled visible si falta NEWS_API_KEY (se expone en evaluate()).

Mock de _fetch_price_changes (sin red ni Alpaca). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_the_ear.py -v
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import the_ear
from the_ear import TheEar
from config import VIX_CIRCUIT_BREAKER_THRESHOLD, SPY_CIRCUIT_BREAKER_THRESHOLD


def _run(coro):
    return asyncio.run(coro)


def _cb_with(prices):
    """check_circuit_breaker con _fetch_price_changes mockeado al valor `prices`."""
    ear = TheEar(MagicMock())
    ear.circuit_breaker_active = False
    ear._fetch_price_changes = MagicMock(return_value=prices)
    return _run(ear.check_circuit_breaker())


# --- #TD-5 — None (sin datos) NO se trata como 0% (mercado quieto) -----------
def test_cb_sin_datos_no_dispara():
    # (None, None) = sin datos para ambos símbolos → NO se activa el breaker.
    assert _cb_with((None, None)) is False


def test_cb_cero_real_no_dispara():
    # (0.0, 0.0) = datos OK con 0% de movimiento → NO se activa (caso normal).
    assert _cb_with((0.0, 0.0)) is False


def test_cb_vix_dispara():
    # VIX por encima del umbral → se activa.
    assert _cb_with((VIX_CIRCUIT_BREAKER_THRESHOLD + 5, 0.0)) is True


def test_cb_spy_dispara_aunque_vix_none():
    # SPY por debajo del umbral dispara, aunque VIX sea None (sin datos → ignorado,
    # no rompe el f-string del log gracias al formateo None-safe).
    assert _cb_with((None, SPY_CIRCUIT_BREAKER_THRESHOLD - 1)) is True


# --- #TD-6 — flag news_disabled visible si falta la API key ------------------
def test_news_disabled_true_sin_key():
    with patch.object(the_ear, "NEWS_API_KEY", None):
        ear = TheEar(MagicMock())
        assert ear.news_disabled is True


def test_news_disabled_false_con_key():
    with patch.object(the_ear, "NEWS_API_KEY", "fake-key"):
        ear = TheEar(MagicMock())
        assert ear.news_disabled is False


def test_fetch_news_sin_key_retorna_vacio():
    # Sin key: fetch_news loggea warning y retorna [] sin tocar la red.
    with patch.object(the_ear, "NEWS_API_KEY", None):
        ear = TheEar(MagicMock())
        assert _run(ear.fetch_news()) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
