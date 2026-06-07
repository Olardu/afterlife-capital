"""Cobertura T-P del Dispatcher (#FASE2-NEW-4): lleva dispatcher.py a ≥95%.

Complementa los tests existentes (bracket_orders / allocation_cap / decimal /
position_sizing / process_signal_integration / drawdown_limits / reconciler)
cubriendo el wiring que esos no tocaban: __init__, sync con Alpaca, allocate_capital,
apply_regime_adjustment, las ramas de process_signal (kill switch, ear, allocation y
equity perezosos, guard descartado/excepción, duplicados, persistencia), execute_order
(qty<1, timeout, limit en background), los wrappers _sync del SDK (Alpaca mockeado),
drawdown del portafolio, kill switch y run_cycle.

Todo mockeado (sin red/DB/Alpaca). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_dispatcher_coverage.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dispatcher import Dispatcher


@pytest.fixture(autouse=True)
def _atr_sizing_off():
    """#TECH-004: estos tests asumen ATR_SIZING_ENABLED=False (process_signal sin
    el path ATR, que construye clients Alpaca reales). El .env de Roman lo tiene en
    true (pre-martes); sin este override los tests heredarían el entorno y fallarían
    localmente. El CI (sin .env) ya corre con el default False — esto lo hace
    determinista en ambos lados."""
    with patch("config.ATR_SIZING_ENABLED", False):
        yield


_EAR_OK = {"can_trade": True, "circuit_breaker": False, "parking_brake": False, "risk_score": 0.0}


def _run(coro):
    return asyncio.run(coro)


def _guard_echo(*, incoming_ticker, incoming_qty, open_positions, performance_scores, signal_type="BUY"):
    return {"approved": True, "original_qty": incoming_qty, "adjusted_qty": incoming_qty,
            "avg_correlation": 0.0, "reason": "approved"}


def _disp(*, guard=None):
    d = Dispatcher.__new__(Dispatcher)
    d.kill_switch_active = False
    d.open_positions = {}
    d.owner_id = uuid4()
    d.regime_classifier = MagicMock()
    d.regime_classifier.get_regime = MagicMock(return_value="NEUTRAL")
    d.regime_classifier.classify_today = AsyncMock(return_value="NEUTRAL")
    d.the_ear = MagicMock()
    d.the_ear.evaluate = AsyncMock(return_value=dict(_EAR_OK))
    d.correlation_guard = MagicMock()
    d.correlation_guard.evaluate_signal = AsyncMock(
        side_effect=guard if guard is not None else _guard_echo
    )
    d.historian = MagicMock()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[])
    d.historian.record_signal = AsyncMock(return_value=uuid4())
    d.historian.record_trade = AsyncMock(return_value=uuid4())
    d.historian.record_shadow_fractional = AsyncMock()
    d.historian.get_active_sentinels = AsyncMock(return_value=[])
    d.historian.evaluate_decay = AsyncMock()
    d.historian.get_drawdown_equities = AsyncMock(
        return_value={"day_open": None, "week_ago": None, "peak": None})
    d.execute_order = AsyncMock(return_value={
        "status": "FILLED", "filled_price": Decimal("100.00"), "order_id": "o1"})
    return d


def _signal(d, **over):
    kw = dict(
        sentinel_id=uuid4(), owner_id=d.owner_id, ticker="NVDA", signal_type="BUY",
        price=Decimal("100.00"), qty=Decimal("5"), strategy_type="macd_volume",
        ear_state=dict(_EAR_OK), allocation={}, account_equity=Decimal("100000"),
    )
    kw.update(over)
    return d.process_signal(**kw)


# ═══════════════════════ § 2 — __init__ ═══════════════════════

def test_init_setea_colaboradores():
    hist, ear, guard, regime = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    oid = uuid4()
    d = Dispatcher(hist, ear, guard, regime, oid)
    assert d.historian is hist and d.the_ear is ear
    assert d.correlation_guard is guard and d.regime_classifier is regime
    assert d.owner_id == oid and d.kill_switch_active is False
    assert d.open_positions == {}


# ═══════════════════════ § 3 — sincronización con Alpaca ═══════════════════════

def test_sync_positions_ghost_y_missing():
    d = _disp()
    d.open_positions = {"GHOST": {"ticker": "GHOST", "qty": Decimal("1"), "side": "BUY"}}
    d._get_alpaca_positions = MagicMock(return_value={
        "NVDA": {"ticker": "NVDA", "qty": Decimal("3"), "side": "BUY", "sentinel_id": None}})
    _run(d.sync_positions_from_alpaca())
    assert "NVDA" in d.open_positions and "GHOST" not in d.open_positions


def test_sync_positions_timeout():
    d = _disp()
    d._get_alpaca_positions = MagicMock(side_effect=asyncio.TimeoutError())
    _run(d.sync_positions_from_alpaca())  # no crashea, mantiene estado


def test_sync_positions_exception():
    d = _disp()
    d._get_alpaca_positions = MagicMock(side_effect=RuntimeError("alpaca down"))
    _run(d.sync_positions_from_alpaca())


def test_get_alpaca_positions_mapea_qty_y_side():
    d = _disp()
    pos_long = MagicMock(symbol="NVDA", qty="5")
    pos_short = MagicMock(symbol="TLT", qty="-3")
    with patch("alpaca.trading.client.TradingClient") as TC:
        TC.return_value.get_all_positions.return_value = [pos_long, pos_short]
        out = d._get_alpaca_positions()
    assert out["NVDA"]["side"] == "BUY" and out["NVDA"]["qty"] == Decimal("5")
    assert out["TLT"]["side"] == "SELL"


# ═══════════════════════ § 4 — allocate_capital / régimen ═══════════════════════

def test_allocate_capital_scores_exception_devuelve_vacio():
    d = _disp()
    d.historian.get_sentinel_scores = AsyncMock(side_effect=RuntimeError("db"))
    assert _run(d.allocate_capital()) == {}


def test_allocate_capital_sin_scores_devuelve_vacio():
    d = _disp()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[])
    assert _run(d.allocate_capital()) == {}


def test_allocate_capital_con_scores_agrega_y_normaliza():
    d = _disp()
    s1, s2 = uuid4(), uuid4()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[
        {"sentinel_id": s1, "sharpe_ratio": 1.5, "total_trades": 10},
        {"sentinel_id": s1, "sharpe_ratio": 0.5, "total_trades": 5},   # agrega al mismo sentinel
        {"sentinel_id": s2, "sharpe_ratio": None, "total_trades": 0},  # sin trades → 0
    ])
    out = _run(d.allocate_capital())
    assert str(s1) in out and str(s2) in out
    assert all(v > 0 for v in out.values())


def test_allocate_capital_todos_sharpe_cero():
    # total_sharpe == 0 → todos al piso MIN_CAPITAL_PER_SENTINEL.
    d = _disp()
    s1 = uuid4()
    d.historian.get_sentinel_scores = AsyncMock(return_value=[
        {"sentinel_id": s1, "sharpe_ratio": 0.0, "total_trades": 3},
    ])
    out = _run(d.allocate_capital())
    assert out[str(s1)] > 0


def test_apply_regime_adjustment_escala_y_bull_intacto():
    d = _disp()
    alloc = {"a": 40.0, "b": 20.0}
    neutral = d.apply_regime_adjustment(alloc, "NEUTRAL")  # x0.75
    assert neutral["a"] == 30.0 and neutral["b"] == 15.0
    bull = d.apply_regime_adjustment(alloc, "BULL")  # x1.0 sin log
    assert bull == alloc
    unknown = d.apply_regime_adjustment(alloc, "ZZZ")  # default 1.0
    assert unknown == alloc


# ═══════════════════════ § 5 — process_signal (ramas) ═══════════════════════

def test_process_signal_kill_switch():
    d = _disp()
    d.kill_switch_active = True
    res = _run(_signal(d))
    assert res["reason"] == "kill_switch_active"


def test_process_signal_signal_type_invalido():
    # #TD-2: HOLD (o cualquier valor != BUY/SELL) se rechaza, ya no cae en SELL.
    d = _disp()
    assert _run(_signal(d, signal_type="HOLD"))["reason"] == "invalid_signal_type"
    d.execute_order.assert_not_awaited()


def test_process_signal_ear_none_evaluate_falla_veta():
    d = _disp()
    d.the_ear.evaluate = AsyncMock(side_effect=RuntimeError("ear down"))
    res = _run(_signal(d, ear_state=None))
    assert res["reason"] == "risk_score_veto"


def test_process_signal_ear_none_evaluate_ok_procede():
    d = _disp()
    d.the_ear.evaluate = AsyncMock(return_value=dict(_EAR_OK))
    res = _run(_signal(d, ear_state=None))
    assert res["approved"] is True


def test_process_signal_circuit_breaker_y_parking_brake():
    d = _disp()
    cb = {"can_trade": False, "circuit_breaker": True, "parking_brake": False, "risk_score": 1.0}
    assert _run(_signal(d, ear_state=cb))["reason"] == "circuit_breaker"
    pb = {"can_trade": False, "circuit_breaker": False, "parking_brake": True, "risk_score": 1.0}
    assert _run(_signal(d, ear_state=pb))["reason"] == "parking_brake"


def test_process_signal_allocation_none_allocate_falla():
    d = _disp()
    d.allocate_capital = AsyncMock(side_effect=RuntimeError("alloc"))
    res = _run(_signal(d, allocation=None))  # except → allocation {}
    assert res["approved"] is True


def test_process_signal_equity_none_timeout_y_exception():
    d = _disp()
    d._get_account_equity = MagicMock(side_effect=asyncio.TimeoutError())
    assert _run(_signal(d, account_equity=None))["approved"] is True
    d2 = _disp()
    d2._get_account_equity = MagicMock(side_effect=RuntimeError("equity"))
    assert _run(_signal(d2, account_equity=None))["approved"] is True


def test_process_signal_equity_none_ok():
    d = _disp()
    d._get_account_equity = MagicMock(return_value=Decimal("100000"))
    assert _run(_signal(d, account_equity=None))["approved"] is True


def test_process_signal_scores_exception_sigue():
    d = _disp()
    d.historian.get_sentinel_scores = AsyncMock(side_effect=RuntimeError("db"))
    assert _run(_signal(d))["approved"] is True  # scores=[] y sigue


def test_process_signal_guard_exception_aprueba_con_qty_original():
    d = _disp()
    d.correlation_guard.evaluate_signal = AsyncMock(side_effect=RuntimeError("guard"))
    assert _run(_signal(d))["approved"] is True


def test_process_signal_guard_descarta_persiste():
    def _reject(**kw):
        return {"approved": False, "avg_correlation": 0.9, "original_qty": Decimal("5"),
                "adjusted_qty": Decimal("0"), "reason": "too_correlated"}
    d = _disp(guard=_reject)
    res = _run(_signal(d))
    assert res["reason"] == "too_correlated"
    d.historian.record_signal.assert_awaited()  # persistió la descartada
    d.execute_order.assert_not_awaited()


def test_process_signal_guard_descarta_persist_falla():
    def _reject(**kw):
        return {"approved": False, "avg_correlation": 0.9, "reason": "too_correlated"}
    d = _disp(guard=_reject)
    d.historian.record_signal = AsyncMock(side_effect=RuntimeError("db"))
    res = _run(_signal(d))  # except del persist no rompe
    assert res["reason"] == "too_correlated"


def test_process_signal_duplicate_buy():
    d = _disp()
    d.open_positions = {"NVDA": {"ticker": "NVDA", "qty": Decimal("1"), "side": "BUY"}}
    assert _run(_signal(d, signal_type="BUY"))["reason"] == "duplicate_ticker_buy"


# --- #FEAT-014 cooldown post-loss (flag-gated) ---
def test_process_signal_cooldown_bloquea_buy():
    d = _disp()
    d.historian.get_last_loss_on_ticker = AsyncMock(
        return_value={"ticker": "NVDA", "closed_at": "2026-05-20", "loss": -12.5})
    with patch("config.COOLDOWN_POST_LOSS_ENABLED", True):
        res = _run(_signal(d, signal_type="BUY"))
    assert res["reason"] == "cooldown_post_loss"
    d.execute_order.assert_not_awaited()


def test_process_signal_cooldown_sin_loss_procede():
    d = _disp()
    d.historian.get_last_loss_on_ticker = AsyncMock(return_value=None)
    with patch("config.COOLDOWN_POST_LOSS_ENABLED", True):
        res = _run(_signal(d, signal_type="BUY"))
    assert res["reason"] != "cooldown_post_loss"


def test_process_signal_cooldown_consulta_falla_fail_open():
    d = _disp()
    d.historian.get_last_loss_on_ticker = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("config.COOLDOWN_POST_LOSS_ENABLED", True):
        res = _run(_signal(d, signal_type="BUY"))
    assert res["reason"] != "cooldown_post_loss"   # fail-open: no bloquea


def test_process_signal_sell_sin_posicion():
    d = _disp()
    assert _run(_signal(d, signal_type="SELL"))["reason"] == "no_open_position"


def test_process_signal_sell_con_posicion_procede():
    d = _disp()
    d.open_positions = {"NVDA": {"ticker": "NVDA", "qty": Decimal("5"), "side": "BUY"}}
    res = _run(_signal(d, signal_type="SELL"))
    assert res["approved"] is True


def test_process_signal_execute_order_excepcion():
    d = _disp()
    d.execute_order = AsyncMock(side_effect=RuntimeError("alpaca"))
    res = _run(_signal(d))
    assert res["reason"] == "CANCELLED" and res["approved"] is False


def test_process_signal_persistencia_falla():
    d = _disp()
    d.historian.record_signal = AsyncMock(side_effect=RuntimeError("db"))
    res = _run(_signal(d))
    assert res["signal_id"] is None and res["trade_id"] is None


def test_process_signal_shadow_matched():
    d = _disp()
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        _run(_signal(d, qty=Decimal("5")))  # qty entero → diff 0 → matched
    assert d.historian.record_shadow_fractional.await_args.kwargs["status"] == "matched"


def test_process_signal_shadow_fractional_would_increase():
    def _adj(**kw):
        return {"approved": True, "original_qty": Decimal("5.5"), "adjusted_qty": Decimal("5.5"),
                "avg_correlation": 0.0, "reason": "approved"}
    d = _disp(guard=_adj)
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        _run(_signal(d, qty=Decimal("5.5")))
    assert d.historian.record_shadow_fractional.await_args.kwargs["status"] == "fractional_would_increase"


def test_process_signal_shadow_signal_lost_to_floor():
    def _adj(**kw):
        return {"approved": True, "original_qty": Decimal("0.5"), "adjusted_qty": Decimal("0.5"),
                "avg_correlation": 0.0, "reason": "approved"}
    d = _disp(guard=_adj)
    # execute_order con qty<1 cancelaría, pero el shadow usa final_qty=0.5 igual.
    d.execute_order = AsyncMock(return_value={"status": "CANCELLED", "filled_price": None, "order_id": None})
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        _run(_signal(d, qty=Decimal("0.5")))
    assert d.historian.record_shadow_fractional.await_args.kwargs["status"] == "signal_lost_to_int_floor"


def test_process_signal_shadow_falla_no_rompe():
    d = _disp()
    d.historian.record_shadow_fractional = AsyncMock(side_effect=RuntimeError("shadow"))
    with patch("config.SHADOW_FRACTIONAL_ENABLED", True):
        res = _run(_signal(d, qty=Decimal("5")))
    assert res["approved"] is True  # el fallo del shadow no afecta el flow


# ═══════════════════════ § 6 — execute_order y wrappers _sync ═══════════════════════

def test_execute_order_qty_menor_a_uno_cancela():
    d = _disp()
    out = _run(Dispatcher.execute_order(d, ticker="NVDA", side="BUY", qty=Decimal("0.5")))
    assert out["status"] == "CANCELLED" and out["order_id"] is None


def test_execute_order_market_devuelve_submit():
    d = _disp()
    d._submit_order_sync = MagicMock(return_value={
        "order_id": "o1", "filled_price": Decimal("100"), "status": "FILLED"})
    out = _run(Dispatcher.execute_order(d, ticker="NVDA", side="BUY", qty=Decimal("5"),
                                        strategy_type="macd_volume"))
    assert out["status"] == "FILLED"


def test_execute_order_timeout_cancela():
    d = _disp()
    d._submit_order_sync = MagicMock(side_effect=asyncio.TimeoutError())
    out = _run(Dispatcher.execute_order(d, ticker="NVDA", side="BUY", qty=Decimal("5")))
    assert out["status"] == "CANCELLED"


def test_execute_order_submit_excepcion_cancela():
    d = _disp()
    d._submit_order_sync = MagicMock(side_effect=RuntimeError("rechazo"))
    out = _run(Dispatcher.execute_order(d, ticker="NVDA", side="BUY", qty=Decimal("5")))
    assert out["status"] == "CANCELLED"


def test_execute_order_limit_agenda_background():
    d = _disp()
    d._submit_order_sync = MagicMock(return_value={
        "order_id": "o1", "filled_price": None, "status": "PENDING"})
    out = _run(Dispatcher.execute_order(
        d, ticker="NVDA", side="BUY", qty=Decimal("5"),
        strategy_type="rsi_short", limit_price=Decimal("100")))
    assert out["status"] == "PENDING"  # devuelve inmediato; verificación en background


async def _fast_sleep(*a, **k):
    return None


async def _drive_execute(d, **kw):
    """Corre execute_order y deja terminar la task de verificación en background."""
    out = await Dispatcher.execute_order(d, **kw)
    await asyncio.sleep(0)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return out


def _limit_kw():
    return dict(ticker="NVDA", side="BUY", qty=Decimal("5"),
               strategy_type="rsi_short", limit_price=Decimal("100"))


def test_execute_order_background_reconcilia_fill():
    d = _disp()
    d._submit_order_sync = MagicMock(return_value={
        "order_id": "o1", "filled_price": None, "status": "PENDING"})
    d._check_and_cancel_limit_sync = MagicMock(return_value={
        "status": "FILLED", "filled_price": Decimal("100")})
    d.historian.update_trade_status = AsyncMock()
    with patch("asyncio.sleep", _fast_sleep):
        _run(_drive_execute(d, **_limit_kw()))
    d.historian.update_trade_status.assert_awaited_once()


def test_execute_order_background_update_status_falla():
    d = _disp()
    d._submit_order_sync = MagicMock(return_value={
        "order_id": "o1", "filled_price": None, "status": "PENDING"})
    d._check_and_cancel_limit_sync = MagicMock(return_value={"status": "CANCELLED", "filled_price": None})
    d.historian.update_trade_status = AsyncMock(side_effect=RuntimeError("db"))
    with patch("asyncio.sleep", _fast_sleep):
        _run(_drive_execute(d, **_limit_kw()))  # error de DB en background no rompe


def test_execute_order_background_timeout_y_excepcion():
    d = _disp()
    d._submit_order_sync = MagicMock(return_value={
        "order_id": "o1", "filled_price": None, "status": "PENDING"})
    d.historian.update_trade_status = AsyncMock()
    d._check_and_cancel_limit_sync = MagicMock(side_effect=asyncio.TimeoutError())
    with patch("asyncio.sleep", _fast_sleep):
        _run(_drive_execute(d, **_limit_kw()))
    d2 = _disp()
    d2._submit_order_sync = MagicMock(return_value={
        "order_id": "o2", "filled_price": None, "status": "PENDING"})
    d2._check_and_cancel_limit_sync = MagicMock(side_effect=RuntimeError("limit check"))
    with patch("asyncio.sleep", _fast_sleep):
        _run(_drive_execute(d2, **_limit_kw()))


def test_execute_order_limit_sin_order_id_devuelve_submit():
    d = _disp()
    d._submit_order_sync = MagicMock(return_value={
        "order_id": None, "filled_price": None, "status": "CANCELLED"})
    out = _run(Dispatcher.execute_order(
        d, ticker="NVDA", side="BUY", qty=Decimal("5"),
        strategy_type="rsi_short", limit_price=Decimal("100")))
    assert out["order_id"] is None


def _patch_alpaca_requests():
    return patch.multiple(
        "alpaca.trading.requests",
        MarketOrderRequest=MagicMock(), LimitOrderRequest=MagicMock(),
        StopLossRequest=MagicMock(), TakeProfitRequest=MagicMock(),
    )


def _mock_order(order_id="o1", filled="100.00", status="filled"):
    o = MagicMock()
    o.id = order_id
    o.filled_avg_price = filled
    o.status = MagicMock(value=status) if status else None
    return o


def test_submit_order_sync_market_limit_bracket():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC, _patch_alpaca_requests():
        TC.return_value.submit_order.return_value = _mock_order()
        # MARKET (estrategia no-limit, sin bracket)
        m = d._submit_order_sync("NVDA", "BUY", Decimal("5"), "macd_volume", None)
        assert m["status"] == "FILLED" and m["filled_price"] == Decimal("100.00")
        # LIMIT (estrategia limit + limit_price)
        lim = d._submit_order_sync("NVDA", "BUY", Decimal("5"), "rsi_short", Decimal("100"))
        assert lim["order_id"] == "o1"
        # BRACKET (tp+sl)
        br = d._submit_order_sync("NVDA", "SELL", Decimal("5"), "macd_volume", None,
                                  Decimal("110"), Decimal("90"))
        assert br["status"] == "FILLED"


def test_submit_order_sync_status_y_fill_none():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC, _patch_alpaca_requests():
        TC.return_value.submit_order.return_value = _mock_order(filled=None, status=None)
        out = d._submit_order_sync("NVDA", "BUY", Decimal("5"), "macd_volume", None)
    assert out["status"] == "PENDING" and out["filled_price"] is None


def test_check_and_cancel_limit_sync_filled():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC:
        TC.return_value.get_order_by_id.return_value = _mock_order(status="filled")
        out = d._check_and_cancel_limit_sync("o1")
    assert out["status"] == "FILLED"


def test_check_and_cancel_limit_sync_cancela_y_error_al_cancelar():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC:
        TC.return_value.get_order_by_id.return_value = _mock_order(status="new")
        out = d._check_and_cancel_limit_sync("o1")
    assert out["status"] == "CANCELLED"
    with patch("alpaca.trading.client.TradingClient") as TC:
        client = TC.return_value
        client.get_order_by_id.return_value = _mock_order(status="new")
        client.cancel_order_by_id.side_effect = RuntimeError("no se pudo")
        out2 = d._check_and_cancel_limit_sync("o2")
    assert out2["status"] == "CANCELLED"  # error al cancelar no rompe


def test_get_account_equity():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC:
        TC.return_value.get_account.return_value = MagicMock(equity="123456.78")
        assert d._get_account_equity() == Decimal("123456.78")


def test_fetch_bars_for_atr_timeout_y_ok():
    d = _disp()
    d._fetch_bars_for_atr_sync = MagicMock(side_effect=asyncio.TimeoutError())
    assert _run(d._fetch_bars_for_atr("NVDA", 20)) is None
    d._fetch_bars_for_atr_sync = MagicMock(return_value="df")
    assert _run(d._fetch_bars_for_atr("NVDA", 20)) == "df"


def test_fetch_bars_for_atr_sync_ok_keyerror_y_excepcion():
    import pandas as pd
    d = _disp()
    idx = pd.MultiIndex.from_product([["NVDA"], range(25)], names=["symbol", "ts"])
    df = pd.DataFrame({"high": [1.0] * 25, "low": [0.5] * 25, "close": [0.8] * 25,
                       "open": [0.7] * 25, "volume": [100] * 25}, index=idx)
    with patch("alpaca.data.historical.StockHistoricalDataClient") as DC, \
         _patch_data_requests():
        DC.return_value.get_stock_bars.return_value = MagicMock(df=df)
        out = d._fetch_bars_for_atr_sync("NVDA", 20)
        assert list(out.columns) == ["high", "low", "close"] and len(out) == 20
        # KeyError: ticker no presente en el df
        DC.return_value.get_stock_bars.return_value = MagicMock(df=df)
        assert d._fetch_bars_for_atr_sync("ZZZ", 20) is None
        # Excepción del SDK al pedir barras
        DC.return_value.get_stock_bars.side_effect = RuntimeError("alpaca")
        assert d._fetch_bars_for_atr_sync("NVDA", 20) is None


def _patch_data_requests():
    return patch.multiple(
        "alpaca.data.requests", StockBarsRequest=MagicMock(),
    )


# ═══════════════════════ § 6b — drawdown del portafolio ═══════════════════════

def test_check_portfolio_drawdown_disabled():
    d = _disp()
    with patch("config.PORTFOLIO_DD_LIMITS_ENABLED", False):
        out = _run(d._check_portfolio_drawdown())
    assert out["reason"] == "dd_limits_disabled"


def test_check_portfolio_drawdown_equities_none():
    d = _disp()
    d._get_drawdown_equities = AsyncMock(return_value=None)
    with patch("config.PORTFOLIO_DD_LIMITS_ENABLED", True):
        out = _run(d._check_portfolio_drawdown())
    assert out["reason"] == "dd_equities_unavailable"


def test_check_portfolio_drawdown_evalua_niveles():
    d = _disp()
    d._get_drawdown_equities = AsyncMock(return_value={
        "current": Decimal("100000"), "day_open": Decimal("100000"),
        "week_ago": Decimal("100000"), "peak": Decimal("100000")})
    with patch("config.PORTFOLIO_DD_LIMITS_ENABLED", True):
        out = _run(d._check_portfolio_drawdown())
    assert out["should_pause"] is False


def test_get_drawdown_equities_ok():
    d = _disp()
    d._get_account_equity = MagicMock(return_value=Decimal("100000"))
    d.historian.get_drawdown_equities = AsyncMock(return_value={
        "day_open": Decimal("99000"), "week_ago": Decimal("98000"), "peak": Decimal("101000")})
    out = _run(d._get_drawdown_equities())
    assert out["current"] == Decimal("100000") and out["peak"] == Decimal("101000")


def test_get_drawdown_equities_equity_falla_none():
    d = _disp()
    d._get_account_equity = MagicMock(side_effect=RuntimeError("alpaca"))
    assert _run(d._get_drawdown_equities()) is None


def test_get_drawdown_equities_refs_falla_usa_defaults():
    d = _disp()
    d._get_account_equity = MagicMock(return_value=Decimal("100000"))
    d.historian.get_drawdown_equities = AsyncMock(side_effect=RuntimeError("db"))
    out = _run(d._get_drawdown_equities())
    assert out["current"] == Decimal("100000") and out["peak"] is None


# ═══════════════════════ § 7 — kill switch ═══════════════════════

def test_activate_kill_switch_confirmacion_incorrecta():
    d = _disp()
    _run(d.activate_kill_switch("NO"))
    assert d.kill_switch_active is False


def test_activate_kill_switch_ok():
    d = _disp()
    d._close_all_sync = MagicMock()
    d.open_positions = {"NVDA": {}}
    _run(d.activate_kill_switch("CONFIRMAR"))
    assert d.kill_switch_active is True and d.open_positions == {}


def test_activate_kill_switch_timeout_y_excepcion():
    d = _disp()
    d._close_all_sync = MagicMock(side_effect=asyncio.TimeoutError())
    _run(d.activate_kill_switch("CONFIRMAR"))
    assert d.kill_switch_active is True  # se activa igual tras timeout
    d2 = _disp()
    d2._close_all_sync = MagicMock(side_effect=RuntimeError("liquidación"))
    _run(d2.activate_kill_switch("CONFIRMAR"))
    assert d2.kill_switch_active is True


def test_deactivate_kill_switch_incorrecta_y_ok():
    d = _disp()
    d.kill_switch_active = True
    _run(d.deactivate_kill_switch("NO"))
    assert d.kill_switch_active is True
    _run(d.deactivate_kill_switch("CONFIRMAR"))
    assert d.kill_switch_active is False


def test_close_all_sync():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC:
        d._close_all_sync()
        TC.return_value.cancel_orders.assert_called_once()
        TC.return_value.close_all_positions.assert_called_once()


# ═══════════════════════ § 8 — run_cycle ═══════════════════════

def _disp_run_cycle(*, dd=None, ear=None):
    d = _disp()
    d.sync_positions_from_alpaca = AsyncMock()
    d.allocate_capital = AsyncMock(return_value={})
    d._get_account_equity = MagicMock(return_value=Decimal("100000"))
    d._get_account_long_market_value = MagicMock(return_value=Decimal("0"))
    d.process_signal = AsyncMock(return_value={"approved": True})
    d.activate_kill_switch = AsyncMock()
    d._check_portfolio_drawdown = AsyncMock(
        return_value=dd or {"should_pause": False, "level": None, "reason": "ok"})
    d.the_ear.evaluate = AsyncMock(return_value=ear if ear is not None else dict(_EAR_OK))
    return d


def test_run_cycle_kill_switch_activo():
    d = _disp_run_cycle()
    d.kill_switch_active = True
    _run(d.run_cycle([]))
    d.sync_positions_from_alpaca.assert_not_awaited()


def test_run_cycle_drawdown_pausa_daily():
    d = _disp_run_cycle(dd={"should_pause": True, "level": "daily", "reason": "dd"})
    _run(d.run_cycle([]))
    d.activate_kill_switch.assert_not_awaited()
    d.sync_positions_from_alpaca.assert_not_awaited()


def test_run_cycle_drawdown_cumulative_dispara_kill_switch():
    d = _disp_run_cycle(dd={"should_pause": True, "level": "cumulative", "reason": "dd"})
    _run(d.run_cycle([]))
    d.activate_kill_switch.assert_awaited_once()


def test_run_cycle_cumulative_kill_switch_falla():
    d = _disp_run_cycle(dd={"should_pause": True, "level": "cumulative", "reason": "dd"})
    d.activate_kill_switch = AsyncMock(side_effect=RuntimeError("ks"))
    _run(d.run_cycle([]))  # error al activar no rompe


def test_run_cycle_normal_procesa_y_evalua_decay():
    d = _disp_run_cycle()
    sid = uuid4()
    d.historian.get_active_sentinels = AsyncMock(return_value=[
        {"sentinel_id": sid, "tickers": ["SPY"]}])
    sig = {"sentinel_id": sid, "owner_id": d.owner_id, "ticker": "SPY",
           "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("1"),
           "strategy_type": "macd_volume"}
    _run(d.run_cycle([sig]))
    d.process_signal.assert_awaited_once()
    d.historian.evaluate_decay.assert_awaited_once()


def test_run_cycle_classify_y_ear_exception_fallback():
    d = _disp_run_cycle()
    d.regime_classifier.classify_today = AsyncMock(side_effect=RuntimeError("regime"))
    d.the_ear.evaluate = AsyncMock(side_effect=RuntimeError("ear"))
    _run(d.run_cycle([{"sentinel_id": uuid4()}]))  # can_trade=False tras fallo del ear
    d.process_signal.assert_not_awaited()


def test_run_cycle_allocate_exception():
    d = _disp_run_cycle()
    d.allocate_capital = AsyncMock(side_effect=RuntimeError("alloc"))
    sig = {"sentinel_id": uuid4(), "owner_id": d.owner_id, "ticker": "SPY",
           "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("1"),
           "strategy_type": "macd_volume"}
    _run(d.run_cycle([sig]))
    d.process_signal.assert_awaited_once()  # allocation {} pero procesa igual


def test_run_cycle_equity_timeout_y_exception():
    d = _disp_run_cycle()
    d._get_account_equity = MagicMock(side_effect=asyncio.TimeoutError())
    sig = {"sentinel_id": uuid4(), "owner_id": d.owner_id, "ticker": "SPY",
           "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("1"),
           "strategy_type": "macd_volume"}
    _run(d.run_cycle([sig]))
    d2 = _disp_run_cycle()
    d2._get_account_equity = MagicMock(side_effect=RuntimeError("equity"))
    _run(d2.run_cycle([sig]))


def test_run_cycle_process_signal_exception():
    d = _disp_run_cycle()
    d.process_signal = AsyncMock(side_effect=RuntimeError("signal"))
    sig = {"sentinel_id": uuid4(), "owner_id": d.owner_id, "ticker": "SPY",
           "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("1"),
           "strategy_type": "macd_volume"}
    _run(d.run_cycle([sig]))  # excepción capturada por señal


def test_run_cycle_can_trade_false():
    d = _disp_run_cycle(ear={"can_trade": False})
    _run(d.run_cycle([{"sentinel_id": uuid4()}]))
    d.process_signal.assert_not_awaited()


def test_run_cycle_get_active_sentinels_exception():
    d = _disp_run_cycle()
    d.historian.get_active_sentinels = AsyncMock(side_effect=RuntimeError("db"))
    _run(d.run_cycle([]))  # decay loop salta con lista vacía


def test_run_cycle_evaluate_decay_exception():
    d = _disp_run_cycle()
    d.historian.get_active_sentinels = AsyncMock(return_value=[
        {"sentinel_id": uuid4(), "tickers": ["SPY"]}])
    d.historian.evaluate_decay = AsyncMock(side_effect=RuntimeError("decay"))
    _run(d.run_cycle([]))  # excepción del decay capturada


# ═══════════════════════ § 9 — cap de exposición (#BUG-NEW-4) ═══════════════════════

def test_buy_descartada_si_exposicion_en_el_cap():
    """deployed = 85% del equity → headroom 0 → BUY rechazada (no entra en margen)."""
    d = _disp()
    out = _run(_signal(
        d, ticker="GLD", deployed_value=Decimal("85000"),
        account_equity=Decimal("100000"),
    ))
    assert out["approved"] is False
    assert out["reason"] == "exposure_cap_reached"
    d.execute_order.assert_not_awaited()


def test_buy_qty_recortada_por_headroom_parcial():
    """deployed deja headroom 200; qty 5×100=500 → se recorta a 2 antes de ejecutar."""
    d = _disp()
    _run(_signal(
        d, ticker="QQQ", qty=Decimal("5"), price=Decimal("100"),
        deployed_value=Decimal("84800"), account_equity=Decimal("100000"),
    ))
    # execute_order recibe la qty ya recortada (2), no 5.
    assert d.execute_order.await_args.kwargs["qty"] == Decimal("2")


def test_buy_sin_recorte_si_hay_headroom():
    """deployed bajo → la qty pasa intacta por el guard."""
    d = _disp()
    _run(_signal(
        d, ticker="SPY", qty=Decimal("5"), price=Decimal("100"),
        deployed_value=Decimal("0"), account_equity=Decimal("100000"),
    ))
    assert d.execute_order.await_args.kwargs["qty"] == Decimal("5")


def test_cap_omitido_si_deployed_value_none():
    """Sin deployed_value (call standalone) el guard no aplica (backward compat)."""
    d = _disp()
    _run(_signal(
        d, ticker="SPY", qty=Decimal("5"), price=Decimal("100"),
        deployed_value=None, account_equity=Decimal("100000"),
    ))
    assert d.execute_order.await_args.kwargs["qty"] == Decimal("5")


def test_get_account_long_market_value():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC:
        TC.return_value.get_account.return_value = MagicMock(long_market_value="94064.96")
        assert d._get_account_long_market_value() == Decimal("94064.96")


def test_get_account_long_market_value_none_es_cero():
    d = _disp()
    with patch("alpaca.trading.client.TradingClient") as TC:
        TC.return_value.get_account.return_value = MagicMock(long_market_value=None)
        assert d._get_account_long_market_value() == Decimal("0")


def test_run_cycle_long_value_exception_no_rompe():
    """Si el fetch de capital desplegado falla → deployed=0 y el ciclo sigue."""
    d = _disp_run_cycle()
    d.historian.get_active_sentinels = AsyncMock(return_value=[])
    d._get_account_long_market_value = MagicMock(side_effect=RuntimeError("alpaca"))
    sig = {"sentinel_id": uuid4(), "owner_id": d.owner_id, "ticker": "SPY",
           "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("5"),
           "strategy_type": "macd_volume"}
    _run(d.run_cycle([sig]))  # no crashea
    assert d.process_signal.await_args.kwargs["deployed_value"] == Decimal("0")


def test_run_cycle_acumula_exposicion_entre_senales():
    """run_cycle pasa deployed_value creciente: la 2da señal ve la exposición de la 1ra."""
    d = _disp_run_cycle()
    d.historian.get_active_sentinels = AsyncMock(return_value=[])
    # 1ra BUY aprueba qty 10 @ 100 = +1000 de exposición; 2da debe ver deployed=1000.
    d.process_signal = AsyncMock(return_value={"approved": True, "qty_executed": Decimal("10")})
    sigs = [
        {"sentinel_id": uuid4(), "owner_id": d.owner_id, "ticker": "SPY",
         "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("10"),
         "strategy_type": "macd_volume"},
        {"sentinel_id": uuid4(), "owner_id": d.owner_id, "ticker": "QQQ",
         "signal_type": "BUY", "price": Decimal("100"), "qty": Decimal("10"),
         "strategy_type": "macd_volume"},
    ]
    _run(d.run_cycle(sigs))
    # La 2da llamada a process_signal recibió deployed_value = 1000 (0 + 10×100).
    segunda = d.process_signal.await_args_list[1]
    assert segunda.kwargs["deployed_value"] == Decimal("1000")


# ═══════════════════════ § 10 — D-fix-a: qty ejecutada == ledger ═══════════════════════

def test_execute_order_expone_executed_qty_floored():
    """execute_order floorea la qty antes de enviarla y la devuelve en executed_qty."""
    d = Dispatcher.__new__(Dispatcher)  # execute_order REAL (no el mock de _disp)
    d._submit_order_sync = MagicMock(return_value={
        "order_id": "o1", "filled_price": Decimal("100.00"), "status": "FILLED"})
    out = _run(d.execute_order("AMD", "BUY", Decimal("14.33"), "macd_volume"))
    assert out["executed_qty"] == Decimal("14")        # 14.33 → floor 14
    assert d._submit_order_sync.call_args[0][2] == 14   # Alpaca recibió 14, no 14.33


def test_execute_order_qty_menor_1_executed_qty_cero():
    d = Dispatcher.__new__(Dispatcher)
    out = _run(d.execute_order("SPY", "BUY", Decimal("0.5"), "macd_volume"))
    assert out["status"] == "CANCELLED"
    assert out["executed_qty"] == Decimal("0")


def test_process_signal_persiste_qty_ejecutada_no_fraccional():
    """El ledger (record_trade + cache) guarda la qty entera ejecutada, no el fraccional."""
    d = _disp()
    d.execute_order = AsyncMock(return_value={
        "status": "FILLED", "filled_price": Decimal("100.00"), "order_id": "o1",
        "executed_qty": Decimal("14")})
    _run(_signal(d, ticker="AMD", qty=Decimal("14.33"), price=Decimal("100"),
                 account_equity=Decimal("100000")))
    assert d.historian.record_trade.await_args.kwargs["qty"] == Decimal("14")
    assert d.open_positions["AMD"]["qty"] == Decimal("14")  # cache también entero


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
