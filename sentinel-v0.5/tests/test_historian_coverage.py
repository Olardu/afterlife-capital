"""Cobertura T-P del Historian (#FASE2-NEW-4): lleva historian.py a ≥95%.

Complementa los tests existentes (test_historian_decimal / _sharpe /
signals_breakdown / daily_equity_snapshots / drawdown_limits /
correlation_guard_persistence / decay_pf_rtd) cubriendo los métodos SQL y
ramas que esos no tocaban: connect() (DDL idempotente), getters/setters de
sentinels, tickers, scores, usuarios, system flags, api_keys (Fernet
mockeado), warning status, Universe Selector (candidatos + rotaciones con
transacción) y macro context, incluyendo el path `except asyncpg.PostgresError`
de cada uno.

Mock del pool asyncpg (sin DB real). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_historian_coverage.py -v
"""
import asyncio
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from historian import Historian, _slippage_to_bps


def _run(coro):
    return asyncio.run(coro)


def _conn(**kw):
    """Conn mock con métodos async + transaction() como async CM."""
    c = MagicMock()
    c.execute = AsyncMock()
    c.fetch = AsyncMock()
    c.fetchrow = AsyncMock()
    c.fetchval = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    c.transaction = MagicMock(return_value=tx)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _hist(conn) -> Historian:
    """Historian con pool mockeado cuyo acquire() entrega `conn` (bypass __init__)."""
    h = Historian.__new__(Historian)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    h.pool = pool
    return h


def _pg(cls=asyncpg.PostgresError):
    """Instancia de excepción asyncpg sin invocar __init__; con args para que
    su __str__ (lee args[0]) no reviente al loguearse."""
    e = cls.__new__(cls)
    e.args = ("mock pg error",)
    return e


# ═══════════════════════ § 2 — __init__ / connect / close ═══════════════════════

def test_init_setea_atributos():
    h = Historian("postgresql://postgres:x@localhost/sentinel")
    assert h.database_url == "postgresql://postgres:x@localhost/sentinel"
    assert h.pool is None


def test_connect_ejecuta_ddl_idempotente():
    conn = _conn()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)

    with patch("historian.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = pool
        h = Historian.__new__(Historian)
        h.database_url = "postgresql://x"
        h.pool = None
        _run(h.connect())

    assert h.pool is pool
    mock_create.assert_awaited_once()
    # Corrió el bloque DDL completo (CREATE TABLE / ALTER / INSERT flags / UPDATE owner).
    assert conn.execute.await_count > 15


def test_connect_create_pool_falla_reraise():
    with patch("historian.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = RuntimeError("postgres caído")
        h = Historian.__new__(Historian)
        h.database_url = "postgresql://x"
        h.pool = None
        with pytest.raises(RuntimeError):
            _run(h.connect())


def test_close_cierra_pool():
    pool = MagicMock()
    pool.close = AsyncMock()
    h = Historian.__new__(Historian)
    h.pool = pool
    _run(h.close())
    pool.close.assert_awaited_once()


def test_close_sin_pool_no_crashea():
    h = Historian.__new__(Historian)
    h.pool = None
    _run(h.close())  # no-op


# ═══════════════════════ § 3 — signals / trades (ramas except) ═══════════════════════

def test_record_signal_pgerror_reraise():
    conn = _conn()
    conn.fetchrow = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.record_signal(uuid4(), uuid4(), "SPY", "BUY", Decimal("100")))


def test_record_signal_con_metricas_correlation():
    conn = _conn()
    sid = uuid4()
    conn.fetchrow = AsyncMock(return_value={"signal_id": sid})
    h = _hist(conn)
    out = _run(h.record_signal(
        uuid4(), uuid4(), "SPY", "BUY", Decimal("100"),
        avg_correlation_at_decision=Decimal("0.8"), original_qty=Decimal("10"),
        adjusted_qty=Decimal("5"), reduction_factor=Decimal("0.5"),
    ))
    assert out == sid


def test_record_shadow_fractional_ok():
    conn = _conn()
    h = _hist(conn)
    _run(h.record_shadow_fractional(
        signal_id=uuid4(), ticker="NVDA", sentinel_id=uuid4(),
        price_at_signal=Decimal("200"), equity_at_decision=Decimal("100000"),
        allocation_pct=Decimal("0.05"), max_dollar_value=Decimal("5000"),
        qty_real_executed=Decimal("25"), qty_fractional_would=Decimal("25.5"),
        notional_real=Decimal("5000"), notional_fractional_would=Decimal("5100"),
        dollar_diff=Decimal("100"), status="WOULD_DIFFER",
    ))
    conn.execute.assert_awaited_once()


def test_record_shadow_fractional_pgerror_reraise():
    conn = _conn()
    conn.execute = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.record_shadow_fractional(
            signal_id=uuid4(), ticker="NVDA", sentinel_id=uuid4(),
            price_at_signal=Decimal("200"), equity_at_decision=Decimal("100000"),
            allocation_pct=Decimal("0.05"), max_dollar_value=Decimal("5000"),
            qty_real_executed=Decimal("25"), qty_fractional_would=Decimal("25"),
            notional_real=Decimal("5000"), notional_fractional_would=Decimal("5000"),
            dollar_diff=Decimal("0"), status="MATCH",
        ))


def test_record_trade_pgerror_reraise():
    conn = _conn()
    conn.fetchrow = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.record_trade(
            signal_id=uuid4(), sentinel_id=uuid4(), owner_id=uuid4(), ticker="X",
            side="BUY", qty=Decimal("1"), filled_price=None, slippage=None, status="NEW",
        ))


def test_update_trade_status_sin_identificador_valueerror():
    h = _hist(_conn())
    with pytest.raises(ValueError):
        _run(h.update_trade_status(status="FILLED"))


def test_update_trade_status_ambos_identificadores_valueerror():
    h = _hist(_conn())
    with pytest.raises(ValueError):
        _run(h.update_trade_status(trade_id=uuid4(), order_id="o-1", status="FILLED"))


def test_update_trade_status_por_trade_id_sin_calcular_slippage():
    conn = _conn()
    h = _hist(conn)
    _run(h.update_trade_status(trade_id=uuid4(), status="CANCELLED"))
    conn.execute.assert_awaited_once()
    conn.fetchrow.assert_not_awaited()  # no calcula slippage si no es FILLED


def test_update_trade_status_pgerror_reraise():
    conn = _conn()
    conn.execute = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.update_trade_status(order_id="o-1", status="CANCELLED"))


# ═══════════════════════ § 4 — performance / decay (ramas) ═══════════════════════

def test_calculate_performance_pgerror_reraise():
    conn = _conn()
    conn.fetch = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.calculate_performance(uuid4(), "NVDA"))


def test_evaluate_decay_warmup_insuficiente_devuelve_false():
    # 1 ciclo BUY→SELL → total_trades=1 < _PARTIAL_SCORE_MIN_TRADES (2) → False sin upsert.
    rows = [
        {"side": "BUY", "filled_price": Decimal("100"), "qty": 1, "created_at": datetime(2026, 1, 1)},
        {"side": "SELL", "filled_price": Decimal("110"), "qty": 1, "created_at": datetime(2026, 1, 2)},
    ]
    conn = _conn()
    conn.fetch = AsyncMock(return_value=rows[:2])
    # Forzar total_trades=1: solo un par. Con 1 BUY y 1 SELL son 1 par => total=1.
    h = _hist(conn)
    out = _run(h.evaluate_decay(uuid4(), "NVDA"))
    assert out is False
    conn.execute.assert_not_awaited()


def test_evaluate_decay_pgerror_en_upsert_reraise():
    # 4 ciclos → warmup parcial, intenta upsert que falla.
    rows = [
        {"side": "BUY", "filled_price": Decimal("100"), "qty": 1, "created_at": datetime(2026, 1, 1) + timedelta(days=i)}
        for i in range(0, 8, 2)
    ]
    sells = [
        {"side": "SELL", "filled_price": Decimal("105"), "qty": 1, "created_at": datetime(2026, 1, 1) + timedelta(days=i + 1)}
        for i in range(0, 8, 2)
    ]
    merged = []
    for b, s in zip(rows, sells):
        merged.append(b)
        merged.append(s)
    conn = _conn()
    conn.fetch = AsyncMock(return_value=merged)
    conn.execute = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.evaluate_decay(uuid4(), "NVDA"))


# ═══════════════════════ § 5 — sentinels y tickers ═══════════════════════

def test_get_active_sentinels_ok():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"sentinel_id": uuid4(), "name": "MORPHEUS", "strategy_type": "sma", "tickers": ["SPY"]},
    ])
    h = _hist(conn)
    out = _run(h.get_active_sentinels(uuid4()))
    assert out[0]["name"] == "MORPHEUS"


def test_get_active_sentinels_pgerror_reraise():
    conn = _conn()
    conn.fetch = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.get_active_sentinels(uuid4()))


def test_get_sentinel_tickers_ok():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"ticker": "SPY"}, {"ticker": "QQQ"}])
    h = _hist(conn)
    assert _run(h.get_sentinel_tickers(uuid4())) == ["SPY", "QQQ"]


def test_get_sentinel_tickers_pgerror_reraise():
    conn = _conn()
    conn.fetch = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.get_sentinel_tickers(uuid4()))


# ═══════════════════════ § 6 — helpers VIX / idle / drawdown ═══════════════════════

def test_get_avg_vix_ok():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=18.5)
    h = _hist(conn)
    assert _run(h.get_avg_vix(5)) == 18.5


def test_get_avg_vix_pgerror_devuelve_none():
    conn = _conn()
    conn.fetchval = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    assert _run(h.get_avg_vix(5)) is None  # fail-safe, no reraise


def test_get_last_trade_timestamp_ok_y_pgerror():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=123)
    h = _hist(conn)
    assert _run(h.get_last_trade_timestamp(uuid4(), "SPY")) == 123
    conn.fetchval = AsyncMock(side_effect=_pg())
    h2 = _hist(conn)
    assert _run(h2.get_last_trade_timestamp(uuid4(), "SPY")) is None


def test_get_ticker_added_at_ok_y_pgerror():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=456)
    h = _hist(conn)
    assert _run(h.get_ticker_added_at(uuid4(), "SPY")) == 456
    conn.fetchval = AsyncMock(side_effect=_pg())
    h2 = _hist(conn)
    assert _run(h2.get_ticker_added_at(uuid4(), "SPY")) is None


def test_record_daily_equity_snapshot_pgerror_reraise():
    conn = _conn()
    conn.execute = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.record_daily_equity_snapshot(uuid4(), Decimal("100000")))


def test_has_equity_snapshot_today_true_false_y_pgerror():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=1)
    assert _run(_hist(conn).has_equity_snapshot_today(uuid4())) is True
    conn2 = _conn()
    conn2.fetchval = AsyncMock(return_value=None)
    assert _run(_hist(conn2).has_equity_snapshot_today(uuid4())) is False
    conn3 = _conn()
    conn3.fetchval = AsyncMock(side_effect=_pg())
    assert _run(_hist(conn3).has_equity_snapshot_today(uuid4())) is False


def test_get_drawdown_equities_pgerror_devuelve_nones():
    conn = _conn()
    conn.fetchval = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    out = _run(h.get_drawdown_equities(uuid4()))
    assert out == {"day_open": None, "week_ago": None, "peak": None}


def test_get_drawdown_equities_day_open_fallback():
    # day_open del día actual None → usa equity_close del último snapshot.
    conn = _conn()
    conn.fetchval = AsyncMock(side_effect=[
        Decimal("110000"),  # peak
        None,               # day_open hoy
        Decimal("105000"),  # fallback day_open (último close)
        Decimal("100000"),  # week_ago
    ])
    h = _hist(conn)
    out = _run(h.get_drawdown_equities(uuid4()))
    assert out["day_open"] == Decimal("105000")
    assert out["peak"] == Decimal("110000")


# ═══════════════════════ § 7 — scores / trade history / breakdown ═══════════════════════

def test_get_sentinel_scores_ok_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"sentinel_id": uuid4(), "sharpe_ratio": 1.2}])
    assert _run(_hist(conn).get_sentinel_scores(uuid4()))[0]["sharpe_ratio"] == 1.2
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_sentinel_scores(uuid4()))


def test_get_signals_breakdown_today_pgerror_reraise():
    conn = _conn()
    conn.fetch = AsyncMock(side_effect=_pg())
    h = _hist(conn)
    with pytest.raises(asyncpg.PostgresError):
        _run(h.get_signals_breakdown_today(uuid4()))


def test_slippage_to_bps_casos():
    # 0 → 0 bps
    assert _slippage_to_bps(Decimal("100"), Decimal("0")) == 0.0
    # positivo: filled 100.5, slip 0.5 → price_at_signal 100 → 50 bps
    assert _slippage_to_bps(Decimal("100.5"), Decimal("0.5")) == pytest.approx(50.0)
    # negativo: filled 99.5, slip -0.5 → price_at_signal 100 → -50 bps
    assert _slippage_to_bps(Decimal("99.5"), Decimal("-0.5")) == pytest.approx(-50.0)
    # sin filled_price / sin slippage → None
    assert _slippage_to_bps(None, Decimal("0.5")) is None
    assert _slippage_to_bps(Decimal("100"), None) is None
    # price_at_signal <= 0 (filled == slippage) → None
    assert _slippage_to_bps(Decimal("0.5"), Decimal("0.5")) is None


def test_get_slippage_stats_today_con_datos():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"filled_price": Decimal("100.5"), "slippage": Decimal("0.5")},   # +50 bps
        {"filled_price": Decimal("99.5"),  "slippage": Decimal("-0.5")},  # -50 bps
    ])
    out = _run(_hist(conn).get_slippage_stats_today(uuid4()))
    assert out["n"] == 2
    assert out["avg_slippage_usd"] == pytest.approx(0.0)
    assert out["avg_slippage_bps"] == pytest.approx(0.0)


def test_get_slippage_stats_today_vacio_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[])
    assert _run(_hist(conn).get_slippage_stats_today(uuid4())) == {
        "n": 0, "avg_slippage_usd": None, "avg_slippage_bps": None}
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_slippage_stats_today(uuid4()))


def test_get_claude_cost_by_sentinel_today_con_datos_vacio_y_pgerror():
    s1, s2 = uuid4(), uuid4()
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"sentinel_id": s1, "cost": 0.0142},
        {"sentinel_id": s2, "cost": 0.05},
    ])
    out = _run(_hist(conn).get_claude_cost_by_sentinel_today(uuid4()))
    assert out == {str(s1): 0.0142, str(s2): 0.05}
    conn2 = _conn()
    conn2.fetch = AsyncMock(return_value=[])
    assert _run(_hist(conn2).get_claude_cost_by_sentinel_today(uuid4())) == {}
    conn3 = _conn()
    conn3.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_claude_cost_by_sentinel_today(uuid4()))


def test_get_simulated_costs_today_con_datos_vacio_y_pgerror():
    # #CR-3: agrega fees on-the-fly de las ventas FILLED de hoy.
    # SELL 100@50  → sec 0.1390, finra 0.0166, exch 0.0100
    # SELL 1e5@10  → sec 27.8000, finra 8.3000 (cap), exch 10.0000
    # agregados: sec 27.9390, finra 8.3166, exch 10.01, total 46.2656
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"qty": Decimal("100"), "filled_price": Decimal("50")},
        {"qty": Decimal("100000"), "filled_price": Decimal("10")},
    ])
    out = _run(_hist(conn).get_simulated_costs_today(uuid4()))
    assert out["n_sells"] == 2
    assert out["sec_fee"] == pytest.approx(27.9390)
    assert out["finra_taf"] == pytest.approx(8.3166)
    assert out["exchange_fee"] == pytest.approx(10.01)
    assert out["total"] == pytest.approx(46.2656)
    # vacío → todo 0
    conn2 = _conn()
    conn2.fetch = AsyncMock(return_value=[])
    assert _run(_hist(conn2).get_simulated_costs_today(uuid4())) == {
        "n_sells": 0, "sec_fee": 0.0, "finra_taf": 0.0,
        "exchange_fee": 0.0, "total": 0.0}
    # pgerror se propaga
    conn3 = _conn()
    conn3.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_simulated_costs_today(uuid4()))


def test_get_tax_report_con_datos_vacio_y_pgerror():
    # #CR-1: FIFO + holding + wash sale on-the-fly sobre los FILLED del owner.
    # BUY 10@100 (ene-1) / SELL 10@90 (ene-11, pérdida -100) / BUY 10@92 (ene-21)
    # → 1 disposal LONG short-term con wash sale; realized -100, neto 0.
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "AAA", "side": "BUY",  "qty": Decimal("10"),
         "filled_price": Decimal("100"), "created_at": datetime(2026, 1, 1)},
        {"ticker": "AAA", "side": "SELL", "qty": Decimal("10"),
         "filled_price": Decimal("90"),  "created_at": datetime(2026, 1, 11)},
        {"ticker": "AAA", "side": "BUY",  "qty": Decimal("10"),
         "filled_price": Decimal("92"),  "created_at": datetime(2026, 1, 21)},
    ])
    out = _run(_hist(conn).get_tax_report(uuid4()))
    assert out["summary"]["n_disposals"] == 1
    assert out["summary"]["realized_gain"] == -100.0
    assert out["summary"]["wash_sale_count"] == 1
    assert out["summary"]["net_realized_gain"] == 0.0
    d = out["disposals"][0]
    # disposals JSON-safe: fechas ISO (str), montos float, flags nativos.
    assert isinstance(d["opened_at"], str) and isinstance(d["closed_at"], str)
    assert d["term"] == "short" and d["direction"] == "LONG"
    assert d["wash_sale"] is True and d["disallowed_loss"] == 100.0
    # vacío → summary en cero, sin disposals
    conn2 = _conn()
    conn2.fetch = AsyncMock(return_value=[])
    empty = _run(_hist(conn2).get_tax_report(uuid4()))
    assert empty["summary"]["n_disposals"] == 0
    assert empty["disposals"] == []
    # pgerror se propaga
    conn3 = _conn()
    conn3.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_tax_report(uuid4()))


def test_get_corporate_actions_report_dividendo_split_y_pgerror():
    # #CR-2: CA inyectadas (DIP). AAPL: compra 1 (nunca vende) → long en ex_date
    # 2026-05-11 ⇒ income 1*0.27. Split XLU pre-período no afecta (sin trades pre-ex).
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "AAPL", "side": "BUY", "qty": Decimal("1"),
         "filled_price": Decimal("200"), "created_at": datetime(2026, 4, 28)},
    ])
    ca = {
        "splits": [{"symbol": "XLU", "ex_date": date(2025, 12, 5), "ratio": Decimal("2")}],
        "dividends": [{"symbol": "AAPL", "ex_date": date(2026, 5, 11),
                       "rate": Decimal("0.27"), "special": False}],
    }
    out = _run(_hist(conn).get_corporate_actions_report(uuid4(), ca))
    assert out["dividends"]["total_income"] == 0.27
    assert out["dividends"]["items"][0]["shares"] == 1.0
    assert out["splits"][0]["affected_trades"] is False  # XLU pre-período
    # tax_report viene serializado (summary + disposals JSON-safe)
    assert "summary" in out["tax_report"] and isinstance(out["tax_report"]["disposals"], list)
    # CA vacías → income 0, sin splits, tax_report coherente
    conn2 = _conn()
    conn2.fetch = AsyncMock(return_value=[])
    empty = _run(_hist(conn2).get_corporate_actions_report(uuid4(), {"splits": [], "dividends": []}))
    assert empty["dividends"]["total_income"] == 0.0 and empty["splits"] == []
    # pgerror del fetch se propaga
    conn3 = _conn()
    conn3.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_corporate_actions_report(uuid4(), {"splits": [], "dividends": []}))


# ═══════════════════════ § 8 — macro events ═══════════════════════

def test_record_macro_event_ok_y_pgerror():
    conn = _conn()
    eid = uuid4()
    conn.fetchrow = AsyncMock(return_value={"event_id": eid})
    out = _run(_hist(conn).record_macro_event(
        0.5, 18.0, -0.3, False, news_titles=[{"title": "x"}],
    ))
    assert out == eid
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).record_macro_event(0.5, None, None, True))


# ═══════════════════════ § 9 — usuarios ═══════════════════════

def test_get_user_by_email_encontrado_y_no():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"user_id": uuid4(), "email": "a@b.com"})
    assert _run(_hist(conn).get_user_by_email("a@b.com"))["email"] == "a@b.com"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_user_by_email("x@y.com")) is None


def test_get_user_by_email_pgerror_reraise():
    conn = _conn()
    conn.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).get_user_by_email("a@b.com"))


def test_list_users_ok_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"user_id": uuid4(), "email": "a@b.com"}])
    assert len(_run(_hist(conn).list_users())) == 1
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).list_users())


def test_add_user_role_invalido():
    with pytest.raises(ValueError):
        _run(_hist(_conn()).add_user("a@b.com", role="SUPER"))


def test_add_user_email_invalido():
    with pytest.raises(ValueError):
        _run(_hist(_conn()).add_user("no-arroba", role="VIEWER"))


def test_add_user_ok_con_colision_de_username():
    conn = _conn()
    # 1ª iteración del while: username existe → genera sufijo; 2ª: libre.
    conn.fetchval = AsyncMock(side_effect=[1, None])
    new = {"user_id": uuid4(), "username": "ana_2", "email": "ana@b.com", "role": "VIEWER"}
    conn.fetchrow = AsyncMock(return_value=new)
    out = _run(_hist(conn).add_user("Ana@B.com", role="VIEWER"))
    assert out["email"] == "ana@b.com"


def test_add_user_email_duplicado_unique_violation():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=None)  # username libre
    conn.fetchrow = AsyncMock(side_effect=_pg(asyncpg.UniqueViolationError))
    with pytest.raises(ValueError):
        _run(_hist(conn).add_user("dup@b.com", role="VIEWER"))


def test_add_user_pgerror_externo_reraise():
    conn = _conn()
    conn.fetchval = AsyncMock(side_effect=_pg())  # falla dentro de la transacción
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).add_user("nuevo@b.com", role="VIEWER"))


def test_remove_user_id_invalido():
    with pytest.raises(ValueError):
        _run(_hist(_conn()).remove_user("no-es-uuid"))


def test_remove_user_no_existe_devuelve_false():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn).remove_user(str(uuid4()))) is False


def test_remove_user_owner_protegido():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"email": "***REMOVED-EMAIL***"})
    with pytest.raises(ValueError):
        _run(_hist(conn).remove_user(str(uuid4())))


def test_remove_user_ok():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"email": "viewer@x.com"})
    conn.execute = AsyncMock(return_value="DELETE 1")
    assert _run(_hist(conn).remove_user(uuid4())) is True


def test_remove_user_pgerror_reraise():
    conn = _conn()
    conn.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).remove_user(str(uuid4())))


# ═══════════════════════ § 10 — system flags ═══════════════════════

def test_get_system_flag_valor_none_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"value": "true"})
    assert _run(_hist(conn).get_system_flag("halt_requested")) == "true"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_system_flag("x")) is None
    conn3 = _conn()
    conn3.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_system_flag("x"))


def test_set_system_flag_ok_y_pgerror():
    conn = _conn()
    _run(_hist(conn).set_system_flag("halt_requested", "true"))
    conn.execute.assert_awaited_once()
    conn2 = _conn()
    conn2.execute = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).set_system_flag("x", "y"))


# ═══════════════════════ § 11 — api_keys (Fernet mockeado) ═══════════════════════

def test_list_api_keys_ok_y_fila_indesencriptable():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[
        {"key_id": uuid4(), "service_name": "alpaca", "encrypted_value": "ok",
         "description": "d", "last_rotated_at": 1, "created_at": 2, "updated_at": 3},
        {"key_id": uuid4(), "service_name": "broken", "encrypted_value": "bad",
         "description": None, "last_rotated_at": 1, "created_at": 2, "updated_at": 3},
    ])
    h = _hist(conn)
    with patch("crypto_utils.decrypt", side_effect=["secret", Exception("corrupto")]), \
         patch("crypto_utils.mask", return_value="se****et"):
        out = _run(h.list_api_keys())
    assert out[0]["masked_value"] == "se****et"
    assert out[1]["masked_value"] == "<UNAVAILABLE>"  # decrypt falló → no rompe el listado


def test_list_api_keys_pgerror_reraise():
    conn = _conn()
    conn.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).list_api_keys())


def test_get_api_key_value_ok_none_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"encrypted_value": "enc"})
    with patch("crypto_utils.decrypt", return_value="plain"):
        assert _run(_hist(conn).get_api_key_value("alpaca")) == "plain"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_api_key_value("nope")) is None
    conn3 = _conn()
    conn3.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_api_key_value("x"))


def test_get_api_key_by_id_ok_none_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"service_name": "alpaca", "encrypted_value": "enc"})
    with patch("crypto_utils.decrypt", return_value="plain"):
        assert _run(_hist(conn).get_api_key_by_id(uuid4())) == "plain"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_api_key_by_id(uuid4())) is None
    conn3 = _conn()
    conn3.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_api_key_by_id(uuid4()))


def test_upsert_api_key_validaciones():
    h = _hist(_conn())
    with pytest.raises(ValueError):
        _run(h.upsert_api_key("  ", "value"))
    with pytest.raises(ValueError):
        _run(h.upsert_api_key("alpaca", "  "))


def test_upsert_api_key_ok_y_pgerror():
    conn = _conn()
    row = {"key_id": uuid4(), "service_name": "alpaca", "encrypted_value": "enc",
           "description": "d", "last_rotated_at": 1, "created_at": 2, "updated_at": 3}
    conn.fetchrow = AsyncMock(return_value=row)
    with patch("crypto_utils.encrypt", return_value="enc"), \
         patch("crypto_utils.mask", return_value="se****et"):
        out = _run(_hist(conn).upsert_api_key("alpaca", "secret", "d"))
    assert out["masked_value"] == "se****et"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(side_effect=_pg())
    with patch("crypto_utils.encrypt", return_value="enc"):
        with pytest.raises(asyncpg.PostgresError):
            _run(_hist(conn2).upsert_api_key("alpaca", "secret"))


def test_delete_api_key_ok_no_existe_y_pgerror():
    conn = _conn()
    conn.execute = AsyncMock(return_value="DELETE 1")
    assert _run(_hist(conn).delete_api_key(uuid4())) is True
    conn2 = _conn()
    conn2.execute = AsyncMock(return_value="DELETE 0")
    assert _run(_hist(conn2).delete_api_key(uuid4())) is False
    conn3 = _conn()
    conn3.execute = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).delete_api_key(uuid4()))


# ═══════════════════════ § 12 — warning status ═══════════════════════

def test_get_sentinels_with_warning_ok_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"sentinel_id": uuid4(), "ticker": "SPY"}])
    assert len(_run(_hist(conn).get_sentinels_with_warning(uuid4()))) == 1
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_sentinels_with_warning(uuid4()))


def test_update_warning_status_entra_y_sale_de_warning():
    conn = _conn()
    h = _hist(conn)
    # win_rate bajo el umbral → entra en warning.
    assert _run(h.update_warning_status(uuid4(), "SPY", 0.3, 1.0, 0.5, 0.05)) is True
    # ambas métricas sobre umbral → no warning.
    assert _run(h.update_warning_status(uuid4(), "SPY", 0.9, 2.0, 0.5, 0.05)) is False


def test_update_warning_status_pgerror_reraise():
    conn = _conn()
    conn.execute = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).update_warning_status(uuid4(), "SPY", 0.3, 1.0, 0.5, 0.05))


# ═══════════════════════ § 13 — candidatos y rotaciones ═══════════════════════

def test_get_pending_candidate_ok_none_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"candidate_id": uuid4(), "status": "watching"})
    assert _run(_hist(conn).get_pending_candidate(uuid4()))["status"] == "watching"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_pending_candidate(uuid4())) is None
    conn3 = _conn()
    conn3.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_pending_candidate(uuid4()))


def test_get_idle_pending_candidate_ok_none_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"candidate_id": uuid4(), "old_ticker": "SPY"})
    assert _run(_hist(conn).get_idle_pending_candidate(uuid4()))["old_ticker"] == "SPY"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_idle_pending_candidate(uuid4())) is None
    conn3 = _conn()
    conn3.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_idle_pending_candidate(uuid4()))


def test_save_pending_candidate_ok_y_pgerror():
    conn = _conn()
    cid = uuid4()
    conn.fetchrow = AsyncMock(return_value={"candidate_id": cid})
    assert _run(_hist(conn).save_pending_candidate(uuid4(), "QQQ", uuid4())) == cid
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).save_pending_candidate(uuid4(), "QQQ", uuid4()))


def test_discard_pending_candidate_ok_no_match_y_pgerror():
    conn = _conn()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    assert _run(_hist(conn).discard_pending_candidate(uuid4(), "razón")) is True
    conn2 = _conn()
    conn2.execute = AsyncMock(return_value="UPDATE 0")
    assert _run(_hist(conn2).discard_pending_candidate(uuid4())) is False
    conn3 = _conn()
    conn3.execute = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).discard_pending_candidate(uuid4()))


def test_expire_old_pending_candidates_cuenta_y_pgerror():
    conn = _conn()
    conn.execute = AsyncMock(return_value="UPDATE 3")
    assert _run(_hist(conn).expire_old_pending_candidates()) == 3
    conn2 = _conn()
    conn2.execute = AsyncMock(return_value="UPDATE 0")
    assert _run(_hist(conn2).expire_old_pending_candidates()) == 0
    conn3 = _conn()
    conn3.execute = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).expire_old_pending_candidates())


def _save_rotation_kwargs(**over):
    base = dict(
        sentinel_id=uuid4(), owner_id=uuid4(), trigger_reason="pre_decay_warning",
        old_ticker="SPY", old_win_rate=0.4, old_sharpe_ratio=0.1, old_total_trades=10,
        new_ticker="QQQ", candidates_proposed=[{"ticker": "QQQ"}],
        claude_reasoning="razón", claude_confidence=0.8, claude_model="sonnet",
        claude_input_tokens=100, claude_output_tokens=50, claude_cost_usd=Decimal("0.01"),
    )
    base.update(over)
    return base


def test_save_rotation_decision_ok_y_pgerror():
    conn = _conn()
    did = uuid4()
    conn.fetchrow = AsyncMock(return_value={"decision_id": did})
    assert _run(_hist(conn).save_rotation_decision(**_save_rotation_kwargs())) == did
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).save_rotation_decision(**_save_rotation_kwargs()))


def test_execute_rotation_decision_inexistente():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn).execute_rotation_in_db(uuid4())) is False


def test_execute_rotation_no_pending():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={
        "sentinel_id": uuid4(), "old_ticker": "SPY", "new_ticker": "QQQ", "status": "executed"})
    assert _run(_hist(conn).execute_rotation_in_db(uuid4())) is False


def test_execute_rotation_sin_new_ticker():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={
        "sentinel_id": uuid4(), "old_ticker": "SPY", "new_ticker": None, "status": "pending"})
    assert _run(_hist(conn).execute_rotation_in_db(uuid4())) is False
    conn.execute.assert_awaited()  # marcó la decisión como failed


def test_execute_rotation_ok():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={
        "sentinel_id": uuid4(), "old_ticker": "SPY", "new_ticker": "QQQ", "status": "pending"})
    assert _run(_hist(conn).execute_rotation_in_db(uuid4())) is True
    assert conn.execute.await_count >= 4


def test_execute_rotation_pgerror_reraise():
    conn = _conn()
    conn.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).execute_rotation_in_db(uuid4()))


def test_rollback_rotation_inexistente_y_no_executed():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn).rollback_rotation_in_db(uuid4(), "admin@x.com")) is False
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value={
        "sentinel_id": uuid4(), "old_ticker": "SPY", "new_ticker": "QQQ", "status": "pending"})
    assert _run(_hist(conn2).rollback_rotation_in_db(uuid4(), "admin@x.com")) is False


def test_rollback_rotation_ok_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={
        "sentinel_id": uuid4(), "old_ticker": "SPY", "new_ticker": "QQQ", "status": "executed"})
    assert _run(_hist(conn).rollback_rotation_in_db(uuid4(), "admin@x.com")) is True
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).rollback_rotation_in_db(uuid4(), "admin@x.com"))


def test_discard_rotation_decision_ok_no_match_y_pgerror():
    conn = _conn()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    assert _run(_hist(conn).discard_rotation_decision(uuid4(), "razón")) is True
    conn2 = _conn()
    conn2.execute = AsyncMock(return_value="UPDATE 0")
    assert _run(_hist(conn2).discard_rotation_decision(uuid4())) is False
    conn3 = _conn()
    conn3.execute = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).discard_rotation_decision(uuid4()))


def test_get_recent_rotations_con_status_sin_status_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"decision_id": uuid4()}])
    h = _hist(conn)
    assert len(_run(h.get_recent_rotations(uuid4(), status="executed"))) == 1
    assert len(_run(h.get_recent_rotations(uuid4()))) == 1  # rama sin filtro
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_recent_rotations(uuid4()))


def test_get_rotation_decision_ok_none_y_pgerror():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"decision_id": uuid4(), "status": "executed"})
    assert _run(_hist(conn).get_rotation_decision(uuid4()))["status"] == "executed"
    conn2 = _conn()
    conn2.fetchrow = AsyncMock(return_value=None)
    assert _run(_hist(conn2).get_rotation_decision(uuid4())) is None
    conn3 = _conn()
    conn3.fetchrow = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn3).get_rotation_decision(uuid4()))


def test_get_active_pending_candidates_ok_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"candidate_id": uuid4()}])
    assert len(_run(_hist(conn).get_active_pending_candidates(uuid4()))) == 1
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_active_pending_candidates(uuid4()))


def test_get_failed_tickers_for_sentinel_ok_y_pgerror():
    conn = _conn()
    conn.fetch = AsyncMock(return_value=[{"old_ticker": "SPY"}, {"old_ticker": "TSLA"}])
    assert _run(_hist(conn).get_failed_tickers_for_sentinel(uuid4())) == ["SPY", "TSLA"]
    conn2 = _conn()
    conn2.fetch = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_failed_tickers_for_sentinel(uuid4()))


# ═══════════════════════ § 14 — macro context ═══════════════════════

def test_get_recent_macro_events_col_existe_normaliza():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=True)  # news_titles existe
    conn.fetch = AsyncMock(return_value=[
        {"event_id": uuid4(), "news_titles": '[{"title": "a"}]'},   # str JSON
        {"event_id": uuid4(), "news_titles": [{"title": "b"}]},     # ya list
        {"event_id": uuid4(), "news_titles": None},                 # otro → []
        {"event_id": uuid4(), "news_titles": "no-json{"},           # str inválido → []
    ])
    out = _run(_hist(conn).get_recent_macro_events(limit=10))
    assert out[0]["news_titles"] == [{"title": "a"}]
    assert out[1]["news_titles"] == [{"title": "b"}]
    assert out[2]["news_titles"] == []
    assert out[3]["news_titles"] == []


def test_get_recent_macro_events_col_no_existe():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=False)  # rama legacy sin news_titles
    conn.fetch = AsyncMock(return_value=[{"event_id": uuid4()}])
    out = _run(_hist(conn).get_recent_macro_events())
    assert out[0]["news_titles"] == []


def test_get_recent_macro_events_pgerror_reraise():
    conn = _conn()
    conn.fetchval = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn).get_recent_macro_events())


def test_get_recent_macro_context_vacio():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=True)
    conn.fetch = AsyncMock(return_value=[])
    out = _run(_hist(conn).get_recent_macro_context())
    assert out["risk_score"] == 0.0 and out["recent_titles"] == []


def test_get_recent_macro_context_con_datos():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=True)
    conn.fetch = AsyncMock(return_value=[
        {"risk_score": 0.7, "vix_level": 20.0, "spy_change_15min": -0.5,
         "circuit_breaker_triggered": True, "news_titles": [{"title": "T1"}],
         "created_at": 9},
        {"risk_score": 0.3, "vix_level": None, "spy_change_15min": None,
         "circuit_breaker_triggered": False, "news_titles": '[{"title": "T1"}, {"title": "T2"}]',
         "created_at": 8},
    ])
    out = _run(_hist(conn).get_recent_macro_context(hours=6))
    assert out["risk_score"] == 0.7
    assert out["circuit_breaker"] is True
    assert out["vix_delta"] == 20.0  # solo un valor no-None
    titles = [t["title"] for t in out["recent_titles"]]
    assert titles == ["T1", "T2"]  # únicos, dedup del T1 repetido


def test_get_recent_macro_context_loop_edge_cases():
    # Cubre las ramas del loop de dedup de títulos: raw None con key presente,
    # JSON inválido, JSON que no es lista, y corte a 5 títulos (break interno+externo).
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=True)
    conn.fetch = AsyncMock(return_value=[
        {"risk_score": 0.5, "vix_level": None, "spy_change_15min": None,
         "circuit_breaker_triggered": False, "news_titles": None, "created_at": 4},
        {"risk_score": 0.5, "vix_level": None, "spy_change_15min": None,
         "circuit_breaker_triggered": False, "news_titles": "bad{json", "created_at": 3},
        {"risk_score": 0.5, "vix_level": None, "spy_change_15min": None,
         "circuit_breaker_triggered": False, "news_titles": '{"not": "una lista"}', "created_at": 2},
        {"risk_score": 0.5, "vix_level": None, "spy_change_15min": None,
         "circuit_breaker_triggered": False,
         "news_titles": [{"title": t} for t in ("A", "B", "C", "D", "E", "F")],
         "created_at": 1},
    ])
    out = _run(_hist(conn).get_recent_macro_context())
    assert [t["title"] for t in out["recent_titles"]] == ["A", "B", "C", "D", "E"]


def test_get_recent_macro_context_col_no_existe_y_pgerror():
    conn = _conn()
    conn.fetchval = AsyncMock(return_value=False)  # rama legacy
    conn.fetch = AsyncMock(return_value=[])
    assert _run(_hist(conn).get_recent_macro_context())["recent_titles"] == []
    conn2 = _conn()
    conn2.fetchval = AsyncMock(side_effect=_pg())
    with pytest.raises(asyncpg.PostgresError):
        _run(_hist(conn2).get_recent_macro_context())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
