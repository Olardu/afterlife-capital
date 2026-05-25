"""Tests T-V Sub-2 — #TECH-003: calculate_performance usa motor FIFO (cierra #TD-1).

El pareo viejo `zip(buys, sells)` emparejaba por posición en listas separadas, lo
que desparejaba fills parciales (qty distintas) y BUYs huérfanos. `match_fifo`
casa por cantidad exacta y maneja LONG/SHORT. Estos tests cubren la equivalencia en
el caso simple y la DIFERENCIA en el caso de qty parciales.

historian con pool/conn mockeados — sin DB real.

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_calculate_performance_fifo.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian


def _run(coro):
    return asyncio.run(coro)


def _historian_con_rows(rows):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    h = Historian.__new__(Historian)
    h.pool = pool
    return h


_BASE = datetime(2026, 1, 1)


def _t(side, price, qty=1, day=0):
    return {"side": side, "filled_price": Decimal(str(price)), "qty": qty,
            "created_at": _BASE + timedelta(days=day)}


def _perf(rows):
    return _run(_historian_con_rows(rows).calculate_performance(uuid4(), "NVDA"))


# =============================================================================
# Equivalencia con el caso simple (donde zip y FIFO coinciden)
# =============================================================================

def test_buy_sell_simple_un_ciclo():
    out = _perf([_t("BUY", 100, day=1), _t("SELL", 110, day=2)])
    assert out["total_trades"] == 1
    assert out["win_rate"] == 1.0


def test_buy_sell_buy_sell_dos_ciclos():
    out = _perf([_t("BUY", 100, day=1), _t("SELL", 110, day=2),
                 _t("BUY", 100, day=3), _t("SELL", 90, day=4)])
    assert out["total_trades"] == 2
    assert out["win_rate"] == 0.5   # un ganador, un perdedor


# =============================================================================
# DIFERENCIA FIFO vs zip — fills parciales (qty distintas)
# =============================================================================

def test_fill_parcial_qty_distintas_fifo_separa_disposals():
    # BUY 10@100, luego SELL 5@110 y SELL 5@120.
    # zip(buys, sells) ingenuo: 1 par (BUY 10, SELL 5@110) → 1 trade, pierde la 2ª venta.
    # match_fifo: casa 5+5 contra el lote de 10 → 2 disposals (returns 0.10 y 0.20).
    out = _perf([_t("BUY", 100, qty=10, day=1),
                 _t("SELL", 110, qty=5, day=2),
                 _t("SELL", 120, qty=5, day=3)])
    assert out["total_trades"] == 2   # FIFO captura ambos cierres; zip daría 1
    assert out["win_rate"] == 1.0     # ambos ganadores


def test_buy_huerfano_no_inventa_ciclo():
    # BUY 1@100, BUY 1@110, SELL 1@120: solo 1 cierre real; el 2º BUY queda abierto.
    out = _perf([_t("BUY", 100, day=1), _t("BUY", 110, day=2), _t("SELL", 120, day=3)])
    assert out["total_trades"] == 1


def test_solo_buys_sin_sell_cero_trades():
    out = _perf([_t("BUY", 100, day=1), _t("BUY", 110, day=2)])
    assert out["total_trades"] == 0
    assert out["win_rate"] == 0.0
    assert out["sharpe_ratio"] == 0.0


# =============================================================================
# SHORT (S-2 / S-8 shortean) — match_fifo es firmado
# =============================================================================

def test_short_sell_primero_luego_cover():
    # SELL 1@120 (abre short), BUY 1@100 (cubre): ganancia del short.
    out = _perf([_t("SELL", 120, day=1), _t("BUY", 100, day=2)])
    assert out["total_trades"] == 1
    assert out["win_rate"] == 1.0   # cubrió más barato → ganador
