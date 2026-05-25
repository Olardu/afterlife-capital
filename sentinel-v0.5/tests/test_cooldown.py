"""Tests T-V Sub-1 — #FEAT-014: historian.get_last_loss_on_ticker (cooldown post-loss).

Detecta el cierre con pérdida más reciente de un ticker dentro de una ventana, vía
el motor FIFO de #CR-1. _fetch_filled_trades mockeado — sin DB real. (El gating en
dispatcher.process_signal se cubre en test_dispatcher_coverage.)

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_cooldown.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian


def _run(coro):
    return asyncio.run(coro)


def _hist(trades):
    h = Historian.__new__(Historian)
    h._fetch_filled_trades = AsyncMock(return_value=trades)
    return h


_NOW = datetime.now()


def _t(side, price, days_ago, ticker="NVDA", qty=1):
    return {"ticker": ticker, "side": side, "qty": qty,
            "price": Decimal(str(price)), "dt": _NOW - timedelta(days=days_ago)}


def test_sin_trades_del_ticker_none():
    h = _hist([_t("BUY", 100, 6, ticker="AAPL"), _t("SELL", 90, 5, ticker="AAPL")])
    assert _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=7)) is None


def test_sin_trades_en_absoluto_none():
    h = _hist([])
    assert _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=7)) is None


def test_sell_con_ganancia_no_es_loss():
    # BUY@100 → SELL@110: gain > 0, no dispara cooldown.
    h = _hist([_t("BUY", 100, 6), _t("SELL", 110, 5)])
    assert _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=7)) is None


def test_perdida_dentro_de_ventana_bloquea():
    # BUY@100 → SELL@90 cerrado hace 5 días, ventana 7 → loss dentro.
    h = _hist([_t("BUY", 100, 6), _t("SELL", 90, 5)])
    out = _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=7))
    assert out is not None
    assert out["ticker"] == "NVDA"
    assert out["loss"] < 0


def test_perdida_fuera_de_ventana_no_bloquea():
    # Pérdida cerrada hace 10 días, ventana 7 → fuera.
    h = _hist([_t("BUY", 100, 12), _t("SELL", 90, 10)])
    assert _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=7)) is None


def test_toma_la_perdida_mas_reciente():
    # Dos pérdidas dentro de ventana: cerrada hace 6d (−20) y hace 2d (−10).
    # Debe devolver la más reciente (hace 2d).
    h = _hist([
        _t("BUY", 100, 7), _t("SELL", 80, 6),   # pérdida −20, cierre hace 6d
        _t("BUY", 100, 3), _t("SELL", 90, 2),   # pérdida −10, cierre hace 2d
    ])
    out = _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=7))
    assert out is not None
    # La más reciente cerró hace ~2 días.
    assert (datetime.now() - out["closed_at"]).days <= 2


def test_ventana_grande_incluye_perdida_vieja():
    h = _hist([_t("BUY", 100, 40), _t("SELL", 90, 35)])
    assert _run(h.get_last_loss_on_ticker(uuid4(), "NVDA", days=60)) is not None
