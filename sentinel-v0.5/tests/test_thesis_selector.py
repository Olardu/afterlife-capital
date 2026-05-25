"""Tests #HE-2 — enganche de Investment Thesis Tracking en universe_selector.

Flag-gated (THESIS_TRACKING_ENABLED) + error-isolado: una falla del tracking
nunca aborta la rotación. historian mockeado (AsyncMock por método).
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import universe_selector as us
from universe_selector import UniverseSelector, _thesis_direction, build_user_prompt


def _run(coro):
    return asyncio.run(coro)


def _sel():
    hist = MagicMock()
    sel = UniverseSelector(
        historian=hist, claude_client=MagicMock(),
        owner_id=uuid.uuid4(), email_sender=None,
    )
    return sel, hist


def _score(**over):
    base = {
        "sentinel_id": uuid.uuid4(), "ticker": "SPY", "win_rate": 0.6,
        "sharpe_ratio": 1.0, "total_trades": 20, "sentinel_name": "NEO",
        "strategy_type": "sma_crossover",
    }
    base.update(over)
    return base


# --- _thesis_direction -------------------------------------------------------

def test_thesis_direction_long_and_short():
    assert _thesis_direction("sma_crossover") == "LONG"
    assert _thesis_direction("rsi_short") == "SHORT"
    assert _thesis_direction("rsi_divergence") == "SHORT"
    assert _thesis_direction(None) == "LONG"


# --- build_user_prompt: sección de feedback ----------------------------------

def test_build_user_prompt_includes_feedback_block():
    p = build_user_prompt(sentinel=_score(), macro={}, failed_tickers=[],
                          reason="decay_confirmed", thesis_feedback="BLOQUE_FEEDBACK_X")
    assert "BLOQUE_FEEDBACK_X" in p


def test_build_user_prompt_no_feedback_when_empty():
    p = build_user_prompt(sentinel=_score(), macro={}, failed_tickers=[],
                          reason="decay_confirmed", thesis_feedback="")
    assert "Historial de tesis" not in p


# --- _fetch_thesis_feedback --------------------------------------------------

def test_fetch_feedback_flag_off(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", False)
    sel, hist = _sel()
    hist.get_closed_theses_feedback = AsyncMock()
    assert _run(sel._fetch_thesis_feedback(uuid.uuid4())) == ""
    hist.get_closed_theses_feedback.assert_not_called()


def test_fetch_feedback_flag_on_builds_block(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.get_closed_theses_feedback = AsyncMock(return_value=[
        {"ticker": "AAPL", "direction": "LONG", "outcome": "win",
         "gain_pct": 5.0, "mae_pct": 2.0, "mfe_pct": 6.0, "holding_days": 3},
    ])
    out = _run(sel._fetch_thesis_feedback(uuid.uuid4()))
    assert "AAPL" in out


def test_fetch_feedback_error_returns_empty(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.get_closed_theses_feedback = AsyncMock(side_effect=RuntimeError("db"))
    assert _run(sel._fetch_thesis_feedback(uuid.uuid4())) == ""


# --- _track_thesis_idea ------------------------------------------------------

def test_track_idea_flag_off_noop(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", False)
    sel, hist = _sel()
    hist.save_investment_thesis = AsyncMock()
    _run(sel._track_thesis_idea(decision_id=uuid.uuid4(), score=_score(),
                                new_ticker="QQQ", reasoning="r", trigger_reason="decay_confirmed"))
    hist.save_investment_thesis.assert_not_called()


def test_track_idea_flag_on_creates_with_direction(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.save_investment_thesis = AsyncMock(return_value=uuid.uuid4())
    _run(sel._track_thesis_idea(decision_id=uuid.uuid4(),
                                score=_score(strategy_type="rsi_short"),
                                new_ticker="QQQ", reasoning="r", trigger_reason="decay_confirmed"))
    kw = hist.save_investment_thesis.call_args.kwargs
    assert kw["ticker"] == "QQQ" and kw["direction"] == "SHORT" and kw["state"] == "IDEA"


def test_track_idea_error_no_raise(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.save_investment_thesis = AsyncMock(side_effect=RuntimeError("x"))
    _run(sel._track_thesis_idea(decision_id=uuid.uuid4(), score=_score(),
                                new_ticker="QQQ", reasoning=None, trigger_reason="x"))


# --- _track_rotation_executed ------------------------------------------------

def test_track_executed_flag_off_noop(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", False)
    sel, hist = _sel()
    hist.get_rotation_decision = AsyncMock()
    _run(sel._track_rotation_executed(decision_id=uuid.uuid4(), score=_score()))
    hist.get_rotation_decision.assert_not_called()


def test_track_executed_promotes_new_and_closes_old(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.get_rotation_decision = AsyncMock(return_value={"new_ticker": "QQQ"})
    hist.find_open_thesis = AsyncMock(side_effect=[
        {"thesis_id": str(uuid.uuid4())},   # nueva tesis (QQQ)
        {"thesis_id": str(uuid.uuid4())},   # tesis vieja (SPY)
    ])
    hist.update_thesis_state = AsyncMock(return_value=True)
    _run(sel._track_rotation_executed(decision_id=uuid.uuid4(), score=_score(win_rate=0.3)))
    assert hist.update_thesis_state.await_count == 2
    states = [c.args[1] for c in hist.update_thesis_state.await_args_list]
    assert states == ["ENTRY_READY", "CLOSED"]


def test_track_executed_no_open_theses(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.get_rotation_decision = AsyncMock(return_value={"new_ticker": "QQQ"})
    hist.find_open_thesis = AsyncMock(return_value=None)
    hist.update_thesis_state = AsyncMock()
    _run(sel._track_rotation_executed(decision_id=uuid.uuid4(), score=_score()))
    hist.update_thesis_state.assert_not_called()


def test_track_executed_decision_error_still_closes_old(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.get_rotation_decision = AsyncMock(side_effect=RuntimeError("x"))
    hist.find_open_thesis = AsyncMock(return_value={"thesis_id": str(uuid.uuid4())})
    hist.update_thesis_state = AsyncMock(return_value=True)
    _run(sel._track_rotation_executed(decision_id=uuid.uuid4(), score=_score(win_rate=0.8)))
    # new_ticker None (la decisión falló) → no ENTRY_READY; solo cierra la vieja.
    assert hist.update_thesis_state.await_count == 1
    assert hist.update_thesis_state.await_args.args[1] == "CLOSED"


def test_track_executed_update_errors_are_isolated(monkeypatch):
    monkeypatch.setattr(us, "THESIS_TRACKING_ENABLED", True)
    sel, hist = _sel()
    hist.get_rotation_decision = AsyncMock(return_value={"new_ticker": "QQQ"})
    hist.find_open_thesis = AsyncMock(return_value={"thesis_id": str(uuid.uuid4())})
    hist.update_thesis_state = AsyncMock(side_effect=RuntimeError("boom"))
    # Ambos except (ENTRY_READY y CLOSE) capturan → no propaga.
    _run(sel._track_rotation_executed(decision_id=uuid.uuid4(), score=_score()))
    assert hist.update_thesis_state.await_count == 2
