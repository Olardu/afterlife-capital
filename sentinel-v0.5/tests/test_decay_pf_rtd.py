"""Tests #FASE2-NEW-5 / EXP-002: decay multifactor con profit_factor + RTD.

El decay viejo (win_rate < 0.4 OR sharpe < min) daba falsos positivos
(estrategia rentable con WR bajo pero buen payoff → se mataba) y falsos
negativos (WR alto pero pierde plata → no se detectaba). Opción C combina:
  pf_wr_fail        = pf < 1.0 AND win_rate < 0.4
  sharpe_rtd_fail   = sharpe < SHARPE_MINIMUM AND rtd < RTD_MINIMUM
  rescued_by_pf_rtd = pf >= PROFIT_FACTOR_MINIMUM AND rtd >= RTD_MINIMUM
  decay = (pf_wr_fail OR sharpe_rtd_fail) AND NOT rescued_by_pf_rtd

Mock del pool asyncpg (sin DB real). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_decay_pf_rtd.py -v
"""
import asyncio
import math
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historian import Historian


def _run(coro):
    return asyncio.run(coro)


def _historian_con_conn(conn) -> Historian:
    historian = Historian.__new__(Historian)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    historian.pool = pool
    return historian


def _metrics(win_rate, sharpe, pf, rtd, total_trades=20):
    return {
        "win_rate": win_rate, "sharpe_ratio": sharpe, "total_trades": total_trades,
        "profit_factor": pf, "return_to_drawdown_ratio": rtd,
    }


def _evaluate_decay(metrics):
    """evaluate_decay con calculate_performance mockeado → (decay, conn.execute_mock)."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    h = _historian_con_conn(conn)
    h.calculate_performance = AsyncMock(return_value=metrics)
    decay = _run(h.evaluate_decay(uuid4(), "TST"))
    return decay, conn.execute


def _rows_desde_sells(sells, buy="100"):
    rows = []
    base = datetime(2026, 1, 1)
    ts = 0
    for s in sells:
        ts += 1
        rows.append({"side": "BUY", "filled_price": Decimal(buy), "qty": 1, "created_at": base + timedelta(days=ts)})
        ts += 1
        rows.append({"side": "SELL", "filled_price": Decimal(str(s)), "qty": 1, "created_at": base + timedelta(days=ts)})
    return rows


def _calc(sells):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows_desde_sells(sells))
    h = _historian_con_conn(conn)
    return _run(h.calculate_performance(uuid4(), "TST"))


# Caso 1 — Rescatada por PF+RTD: WR y Sharpe malos pero PF≥1.3 y RTD≥1.0 → NO decay.
def test_rescatada_por_pf_rtd():
    decay, _ = _evaluate_decay(_metrics(win_rate=0.30, sharpe=0.01, pf=1.5, rtd=1.2))
    assert decay is False


# Caso 2 — pf_wr combined fail (sin rescate) → decay.
def test_pf_wr_combined_fail():
    decay, _ = _evaluate_decay(_metrics(win_rate=0.30, sharpe=0.10, pf=0.7, rtd=0.5))
    assert decay is True


# Caso 3 — sharpe_rtd combined fail (sin rescate) → decay.
def test_sharpe_rtd_combined_fail():
    decay, _ = _evaluate_decay(_metrics(win_rate=0.60, sharpe=0.01, pf=1.1, rtd=0.5))
    assert decay is True


# Caso 4 — Todo OK → NO decay.
def test_todo_ok_sin_decay():
    decay, _ = _evaluate_decay(_metrics(win_rate=0.60, sharpe=0.50, pf=2.0, rtd=1.5))
    assert decay is False


# Caso 5 — Warmup incompleto (< WARMUP) → NO juzga decay pero SÍ escribe scores.
def test_warmup_no_juzga_pero_persiste():
    decay, execute_mock = _evaluate_decay(
        _metrics(win_rate=0.20, sharpe=-1.0, pf=0.3, rtd=-2.0, total_trades=5)
    )
    assert decay is False                      # no se juzga en warmup parcial
    assert execute_mock.await_count == 1       # pero igual hace upsert


# Caso 6 — Edge gross_loss=0 y max_dd=0 (todos ganadores) → pf=inf, rtd=inf, NULL al persistir.
def test_edge_todos_ganadores_inf():
    res = _calc([101, 102, 101.5, 103, 102.5])   # serie monótona creciente
    assert math.isinf(res["profit_factor"])
    assert math.isinf(res["return_to_drawdown_ratio"])
    # evaluate_decay no debe crashear y persiste NULL (inf no es NUMERIC).
    conn = MagicMock()
    conn.execute = AsyncMock()
    h = _historian_con_conn(conn)
    h.calculate_performance = AsyncMock(return_value=res)
    _run(h.evaluate_decay(uuid4(), "TST"))
    args = conn.execute.await_args.args   # (sql, sid, ticker, sharpe, wr, trades, decay, pf_db, rtd_db)
    assert args[7] is None and args[8] is None


# Caso 7 — Cálculo normal: pf y rtd finitos con valores esperados.
def test_calculo_pf_rtd_normal():
    # returns: +0.02, -0.01, +0.03, -0.015
    res = _calc([102, 99, 103, 98.5])
    # gross_profit=0.05, gross_loss=0.025 → pf=2.0
    assert res["profit_factor"] == pytest.approx(2.0, abs=1e-6)
    # serie acum: .02,.01,.04,.025 → max_dd=0.015, total=0.025 → rtd≈1.667
    assert res["return_to_drawdown_ratio"] == pytest.approx(0.025 / 0.015, abs=1e-6)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
