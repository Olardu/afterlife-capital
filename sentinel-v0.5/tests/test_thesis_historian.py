# Tests del wire-up de #HE-2 en historian (save/update_state/find/feedback).
# Mismo patrón de mock de asyncpg que test_historian_coverage.py: pool/conn
# mockeados, sin DB real → cubre las ramas de los métodos nuevos.

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from historian import Historian


def _run(coro):
    return asyncio.run(coro)


def _conn(**kw):
    c = MagicMock()
    c.execute = AsyncMock()
    c.fetch = AsyncMock()
    c.fetchrow = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    c.transaction = MagicMock(return_value=tx)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _hist(conn) -> Historian:
    h = Historian.__new__(Historian)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    h.pool = pool
    return h


def _pg(cls=asyncpg.PostgresError):
    e = cls.__new__(cls)
    e.args = ("mock pg error",)
    return e


def _row(**over):
    base = {
        "thesis_id": uuid4(), "sentinel_id": uuid4(), "decision_id": uuid4(),
        "ticker": "AAPL", "direction": "LONG", "state": "CLOSED",
        "entry_price_target": Decimal("100"), "exit_target": Decimal("110"),
        "stop_loss": Decimal("95"), "entry_price": Decimal("100.5"),
        "exit_price": Decimal("108"), "outcome": "win",
        "gain": Decimal("7.5"), "gain_pct": Decimal("7.46"),
        "mae": Decimal("2"), "mfe": Decimal("9"), "mae_pct": Decimal("2"),
        "mfe_pct": Decimal("9"), "holding_days": 3,
        "created_at": datetime(2026, 5, 1, 10), "entry_at": datetime(2026, 5, 1, 11),
        "closed_at": datetime(2026, 5, 4, 15),
    }
    base.update(over)
    return base


# --- save_investment_thesis --------------------------------------------------

def test_save_thesis_returns_id():
    tid = uuid4()
    conn = _conn(fetchrow=AsyncMock(return_value={"thesis_id": tid}))
    out = _run(_hist(conn).save_investment_thesis(
        sentinel_id=uuid4(), owner_id=uuid4(), ticker="AAPL"))
    assert out == tid
    conn.fetchrow.assert_awaited_once()


def test_save_thesis_pg_error_reraise():
    conn = _conn(fetchrow=AsyncMock(side_effect=_pg()))
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).save_investment_thesis(
            sentinel_id=uuid4(), owner_id=uuid4(), ticker="AAPL"))


# --- update_thesis_state -----------------------------------------------------

def test_update_state_valid_sets_extra_fields():
    conn = _conn(fetchrow=AsyncMock(return_value={"state": "ENTRY_READY"}))
    ok = _run(_hist(conn).update_thesis_state(
        uuid4(), "ACTIVE", entry_price=Decimal("100.5"), entry_at=datetime(2026, 5, 1)))
    assert ok is True
    sql = conn.execute.call_args[0][0]
    assert "state = $2" in sql
    assert "entry_price = $" in sql and "entry_at = $" in sql


def test_update_state_not_found():
    conn = _conn(fetchrow=AsyncMock(return_value=None))
    assert _run(_hist(conn).update_thesis_state(uuid4(), "ACTIVE")) is False
    conn.execute.assert_not_awaited()


def test_update_state_invalid_transition_returns_false_no_raise():
    conn = _conn(fetchrow=AsyncMock(return_value={"state": "IDEA"}))
    # IDEA → ACTIVE salta ENTRY_READY → inválido.
    assert _run(_hist(conn).update_thesis_state(uuid4(), "ACTIVE")) is False
    conn.execute.assert_not_awaited()


def test_update_state_skips_none_fields():
    conn = _conn(fetchrow=AsyncMock(return_value={"state": "ACTIVE"}))
    ok = _run(_hist(conn).update_thesis_state(
        uuid4(), "CLOSED", exit_price=Decimal("108"), notes=None))
    assert ok is True
    sql = conn.execute.call_args[0][0]
    assert "exit_price = $" in sql
    assert "notes" not in sql


def test_update_state_pg_error_reraise():
    conn = _conn(fetchrow=AsyncMock(side_effect=_pg()))
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).update_thesis_state(uuid4(), "ACTIVE"))


# --- find_open_thesis --------------------------------------------------------

def test_find_open_thesis_serialized():
    conn = _conn(fetchrow=AsyncMock(return_value=_row(state="ACTIVE")))
    out = _run(_hist(conn).find_open_thesis(uuid4(), uuid4(), "AAPL"))
    assert out["ticker"] == "AAPL" and out["state"] == "ACTIVE"
    assert out["entry_price"] == 100.5


def test_find_open_thesis_none():
    conn = _conn(fetchrow=AsyncMock(return_value=None))
    assert _run(_hist(conn).find_open_thesis(uuid4(), uuid4(), "AAPL")) is None


def test_find_open_thesis_pg_error_reraise():
    conn = _conn(fetchrow=AsyncMock(side_effect=_pg()))
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).find_open_thesis(uuid4(), uuid4(), "AAPL"))


# --- get_closed_theses_feedback ----------------------------------------------

def test_feedback_no_filter_reverses_to_chronological():
    rows = [_row(ticker="A"), _row(ticker="B")]  # vienen DESC del SQL
    conn = _conn(fetch=AsyncMock(return_value=rows))
    out = _run(_hist(conn).get_closed_theses_feedback(uuid4()))
    assert [t["ticker"] for t in out] == ["B", "A"]


def test_feedback_sentinel_filter_uses_param():
    conn = _conn(fetch=AsyncMock(return_value=[_row()]))
    out = _run(_hist(conn).get_closed_theses_feedback(uuid4(), sentinel_id=uuid4(), limit=5))
    assert len(out) == 1
    assert "sentinel_id = $2" in conn.fetch.call_args[0][0]


def test_feedback_pg_error_reraise():
    conn = _conn(fetch=AsyncMock(side_effect=_pg()))
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).get_closed_theses_feedback(uuid4()))


# --- _serialize_thesis nulls -------------------------------------------------

def test_serialize_thesis_handles_nulls():
    out = Historian._serialize_thesis(
        _row(decision_id=None, entry_price=None, closed_at=None, mae=None))
    assert out["decision_id"] is None
    assert out["entry_price"] is None
    assert out["closed_at"] is None
    assert out["mae"] is None
    assert out["gain"] == 7.5
