"""Tests del fix #TECHDEBT-NEW-1 (B.2): Sharpe SIN anualización falsa.

Bug: `calculate_performance` multiplicaba el Sharpe per-trade por
`sqrt(252*26) ≈ 80.94` (factor válido solo para returns por barra de 15min,
NO para returns por trade pareado BUY→SELL). Resultado: Sharpe imposibles
(93.9, -120.4) que distorsionaban `dispatcher.allocate_capital`.

Fix B.2: dejar el Sharpe per-trade puro (mean_r / std_r) y recalibrar
SHARPE_MINIMUM. Estos tests verifican rango sano, orden relativo, edge cases
y el threshold recalibrado.

Mock del pool asyncpg (sin DB real). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_historian_sharpe.py -v
"""
import asyncio
import os
import statistics
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian, _SHARPE_ANNUALIZATION_FACTOR
from config import SHARPE_MINIMUM


def _run(coro):
    return asyncio.run(coro)


def _historian_con_conn(conn) -> Historian:
    """Historian con pool mockeado cuyo acquire() entrega `conn` (bypass __init__)."""
    historian = Historian.__new__(Historian)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    historian.pool = pool
    return historian


def _rows_desde_sells(sells, buy="100"):
    """Construye rows BUY/SELL pareados. buy fijo, cada sell define un return."""
    rows = []
    ts = 0
    for s in sells:
        ts += 1
        rows.append({"side": "BUY", "filled_price": Decimal(buy), "created_at": ts})
        ts += 1
        rows.append({"side": "SELL", "filled_price": Decimal(str(s)), "created_at": ts})
    return rows


def _sharpe_de(sells, buy="100"):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows_desde_sells(sells, buy))
    historian = _historian_con_conn(conn)
    return _run(historian.calculate_performance(uuid4(), "TST"))


# Caso 1 — Sharpe per-trade en rango razonable, igual al oráculo `statistics`.
def test_sharpe_per_trade_sin_anualizar_en_rango():
    sells = [101, 99.5, 102, 100.5, 99, 101.5, 99.7, 100.8, 99.5, 101.2]
    returns = [float((Decimal(str(s)) - 100) / 100) for s in sells]
    esperado = statistics.mean(returns) / statistics.stdev(returns)  # oráculo independiente

    res = _sharpe_de(sells)

    assert res["total_trades"] == 10
    assert res["sharpe_ratio"] == pytest.approx(esperado, abs=1e-6)
    assert -3.0 <= res["sharpe_ratio"] <= 3.0          # rango sano (NO anualizado)
    # Prueba de que el bug está cerrado: el valor anualizado caería fuera de rango.
    assert abs(esperado * _SHARPE_ANNUALIZATION_FACTOR) > 3.0


# Caso 2 — Regresión: el valor ya NO está anualizado. Con baja varianza el Sharpe
# per-trade puede ser alto pero FINITO; el bug lo multiplicaba a un absurdo (>80).
def test_sharpe_regresion_no_devuelve_valores_absurdos():
    sells = [101, 101.2, 100.9, 101.1, 101.05, 100.95, 101.15, 101.0]
    returns = [float((Decimal(str(s)) - 100) / 100) for s in sells]
    esperado = statistics.mean(returns) / statistics.stdev(returns)   # per-trade puro
    res = _sharpe_de(sells)
    assert res["sharpe_ratio"] == pytest.approx(esperado, abs=1e-6)
    assert abs(esperado * _SHARPE_ANNUALIZATION_FACTOR) > 80.0          # lo que daba el bug
    assert abs(res["sharpe_ratio"]) < abs(esperado * _SHARPE_ANNUALIZATION_FACTOR)  # nuevo << viejo


# Caso 3 — Orden relativo preservado entre un sentinel bueno y uno malo.
def test_sharpe_preserva_orden_relativo():
    bueno = _sharpe_de([101, 101.5, 100.8, 101.2, 101.0, 101.3])     # consistente +
    malo  = _sharpe_de([99, 101, 98.5, 102, 97, 103])                # volátil, ~plano
    assert bueno["sharpe_ratio"] > malo["sharpe_ratio"]


# Caso 4 — Edge cases: 0 trades, 1 trade, std=0 → sharpe 0.0 sin crashear.
def test_sharpe_edge_cases():
    assert _sharpe_de([])["sharpe_ratio"] == 0.0                     # 0 pares
    assert _sharpe_de([101])["sharpe_ratio"] == 0.0                  # 1 par (total<2)
    iguales = _sharpe_de([101, 101, 101, 101])                       # returns idénticos → std=0
    assert iguales["sharpe_ratio"] == 0.0
    assert iguales["total_trades"] == 4


# Caso 5 — SHARPE_MINIMUM recalibrado a escala per-trade.
def test_sharpe_minimum_recalibrado_a_per_trade():
    # Tras B.2 el threshold se compara contra Sharpe per-trade, no anualizado.
    assert SHARPE_MINIMUM == 0.05
    # Un sentinel sano (Caso 1, ~0.47 per-trade) supera el umbral nuevo (no decay por Sharpe)...
    sano = _sharpe_de([101, 99.5, 102, 100.5, 99, 101.5, 99.7, 100.8, 99.5, 101.2])
    assert sano["sharpe_ratio"] > SHARPE_MINIMUM
    # ...pero habría sido marcado decay erróneamente contra el umbral viejo (0.5 per-period).
    assert sano["sharpe_ratio"] < 0.5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
