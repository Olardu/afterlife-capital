"""Tests T-P — cobertura de universe_selector.py.

Complementa test_universe_selector_filters.py y _idle.py cubriendo: formatters
puros (_format_news/_failed/_classify_ticker/_portfolio/_pending_watchlist),
ramas faltantes de _filter_candidate_eligibility, y toda la orquestación
(evaluate_all_sentinels, _evaluate_one, _handle_warning, _handle_decay,
_request_candidate, _resolve_idle_pending, _evaluate_idle_timeout, rollback).

historian y claude_client mockeados — sin DB, sin red, sin Alpaca.

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_universe_selector_coverage.py -v
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import universe_selector as us
from universe_selector import (
    UniverseSelector,
    _classify_ticker,
    _filter_candidate_eligibility,
    _format_failed,
    _format_news,
    _format_pending_watchlist,
    _format_portfolio_composition,
    build_user_prompt,
)


def _run(coro):
    return asyncio.run(coro)


# =============================================================================
# Formatters puros
# =============================================================================

def test_format_news_vacio_y_con_titulares():
    assert "sin titulares" in _format_news([])
    out = _format_news([
        {"title": "Fed sube tasas", "source": "Reuters",
         "matched_keywords": ["fed", "rates"]},
        {"title": "Sin keywords", "source": "AP"},
    ])
    assert "Fed sube tasas" in out and "[fed, rates]" in out and "(AP)" in out


def test_format_failed_vacio_y_con_tickers():
    assert "ninguno" in _format_failed([])
    assert _format_failed(["NVDA", "TSLA"]) == "NVDA, TSLA"


def test_classify_ticker_buckets_y_otros():
    assert _classify_ticker("SPY") == "broad_market"
    assert _classify_ticker("nvda") == "tech_individual"  # case-insensitive
    assert _classify_ticker("ZZZZ") == "otros"
    assert _classify_ticker("") == "otros"


def test_format_portfolio_composition_vacio_y_con_resumen():
    assert "sin información" in _format_portfolio_composition([])
    out = _format_portfolio_composition([
        {"sentinel_codename": "MORPHEUS", "current_ticker": "SPY",
         "strategy_type": "sma"},
        {"sentinel_codename": "NEO", "current_ticker": "QQQ",
         "strategy_type": "rsi"},
    ])
    assert "MORPHEUS" in out and "Resumen automático" in out
    assert "broad_market" in out


def test_format_pending_watchlist_vacio_y_con_items():
    assert _format_pending_watchlist([]) == ""
    out = _format_pending_watchlist([
        {"sentinel_codename": "MORPHEUS", "proposed_ticker": "GLD",
         "trigger_reason": "pre_decay_warning"},
    ])
    assert "GLD" in out and "MORPHEUS" in out and "WATCHLIST" in out


def test_build_user_prompt_con_y_sin_deltas():
    sentinel = {"name": "NEO", "strategy_type": "rsi", "ticker": "SPY",
                "win_rate": 0.4, "sharpe_ratio": 0.5, "total_trades": 20}
    out_none = build_user_prompt(sentinel=sentinel, macro={}, failed_tickers=[],
                                 reason="decay_confirmed")
    assert "n/a" in out_none  # vix/spy None → 'n/a'
    out_vals = build_user_prompt(
        sentinel=sentinel,
        macro={"vix_delta": 1.5, "spy_delta": -0.8, "risk_score": 0.3},
        failed_tickers=["TSLA"], reason="pre_decay_warning",
    )
    assert "+1.50%" in out_vals and "-0.80%" in out_vals


# =============================================================================
# _filter_candidate_eligibility — ramas faltantes
# =============================================================================

def _asset(*, status=None, tradable=True, fractionable=True,
           marginable=True, shortable=True):
    from alpaca.trading.enums import AssetStatus
    a = MagicMock()
    a.status = status if status is not None else AssetStatus.ACTIVE
    a.tradable = tradable
    a.fractionable = fractionable
    a.marginable = marginable
    a.shortable = shortable
    return a


def test_filter_eligibility_no_tradable():
    client = MagicMock()
    client.get_asset = MagicMock(return_value=_asset(tradable=False))
    res = _run(_filter_candidate_eligibility("NVDA", client))
    assert res["eligible"] is False and res["reason"] == "not_tradable"


def test_filter_eligibility_ok_con_marginable_shortable_false():
    client = MagicMock()
    client.get_asset = MagicMock(
        return_value=_asset(marginable=False, shortable=False))
    res = _run(_filter_candidate_eligibility("NVDA", client))
    assert res["eligible"] is True and res["reason"] is None


# =============================================================================
# Helpers de mock para la clase
# =============================================================================

def _make_selector(*, email_sender=None):
    hist = MagicMock()
    claude = MagicMock()
    sel = UniverseSelector(
        historian=hist, claude_client=claude,
        owner_id=uuid.uuid4(), email_sender=email_sender,
    )
    return sel, hist, claude


# Sharpe que dispara warning-sin-decay vs decay (win_rate alto neutraliza el otro eje)
_WARN_SHARPE = (us.WARNING_THRESHOLD_SHARPE + us.DECAY_THRESHOLD_SHARPE) / 2
_DECAY_SHARPE = us.DECAY_THRESHOLD_SHARPE - 1.0
_OK_SHARPE = us.WARNING_THRESHOLD_SHARPE + 1.0


def _score(*, win=0.99, sharpe=_OK_SHARPE, trades=20, sid=None,
           ticker="SPY", name="NEO", strat="rsi"):
    return {"sentinel_id": sid or uuid.uuid4(), "ticker": ticker,
            "win_rate": win, "sharpe_ratio": sharpe, "total_trades": trades,
            "sentinel_name": name, "strategy_type": strat}


# =============================================================================
# _evaluate_one
# =============================================================================

def test_evaluate_one_sin_warmup_retorna_none():
    sel, hist, _ = _make_selector()
    hist.update_warning_status = AsyncMock()
    assert _run(sel._evaluate_one(_score(trades=1))) is None
    hist.update_warning_status.assert_not_called()


def test_evaluate_one_decay_delega_en_handle_decay():
    sel, hist, _ = _make_selector()
    hist.update_warning_status = AsyncMock()
    sel._handle_decay = AsyncMock(return_value="rotation")
    assert _run(sel._evaluate_one(_score(sharpe=_DECAY_SHARPE))) == "rotation"
    hist.update_warning_status.assert_awaited()


def test_evaluate_one_warning_delega_en_handle_warning():
    sel, hist, _ = _make_selector()
    hist.update_warning_status = AsyncMock()
    sel._handle_warning = AsyncMock(return_value="candidate")
    assert _run(sel._evaluate_one(_score(sharpe=_WARN_SHARPE))) == "candidate"


def test_evaluate_one_update_warning_status_falla_no_rompe():
    sel, hist, _ = _make_selector()
    hist.update_warning_status = AsyncMock(side_effect=RuntimeError("db"))
    sel._handle_warning = AsyncMock(return_value="warning")
    assert _run(sel._evaluate_one(_score(sharpe=_WARN_SHARPE))) == "warning"


def test_evaluate_one_recuperacion_descarta_candidato():
    sel, hist, _ = _make_selector()
    hist.update_warning_status = AsyncMock()
    hist.get_pending_candidate = AsyncMock(
        return_value={"candidate_id": uuid.uuid4(), "proposed_ticker": "GLD"})
    hist.discard_pending_candidate = AsyncMock()
    assert _run(sel._evaluate_one(_score(sharpe=_OK_SHARPE))) is None
    hist.discard_pending_candidate.assert_awaited()


def test_evaluate_one_recuperacion_discard_falla_no_rompe():
    sel, hist, _ = _make_selector()
    hist.update_warning_status = AsyncMock()
    hist.get_pending_candidate = AsyncMock(side_effect=RuntimeError("db"))
    assert _run(sel._evaluate_one(_score(sharpe=_OK_SHARPE))) is None


# =============================================================================
# _handle_warning
# =============================================================================

def test_handle_warning_con_candidato_existente():
    sel, hist, _ = _make_selector()
    hist.get_pending_candidate = AsyncMock(return_value={"candidate_id": uuid.uuid4()})
    assert _run(sel._handle_warning(_score())) == "warning"


def test_handle_warning_request_none():
    sel, hist, _ = _make_selector()
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=None)
    assert _run(sel._handle_warning(_score())) == "warning"


def test_handle_warning_request_genera_candidato():
    sel, hist, _ = _make_selector()
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=uuid.uuid4())
    assert _run(sel._handle_warning(_score())) == "candidate"


# =============================================================================
# _handle_decay
# =============================================================================

def test_handle_decay_candidato_preaprobado_ejecuta_y_emaila():
    sent = []
    async def _sender(d):
        sent.append(d)
        return True
    sel, hist, _ = _make_selector(email_sender=_sender)
    did = uuid.uuid4()
    hist.get_pending_candidate = AsyncMock(
        return_value={"decision_id": did, "proposed_ticker": "GLD"})
    hist.execute_rotation_in_db = AsyncMock(return_value=True)
    hist.get_rotation_decision = AsyncMock(return_value={"id": did})
    assert _run(sel._handle_decay(_score())) == "rotation"
    assert sent  # email enviado


def test_handle_decay_sin_candidato_request_none():
    sel, hist, _ = _make_selector()
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=None)
    assert _run(sel._handle_decay(_score())) == "warning"


def test_handle_decay_execute_lanza_descarta_y_warning():
    sel, hist, _ = _make_selector()
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=uuid.uuid4())
    hist.execute_rotation_in_db = AsyncMock(side_effect=RuntimeError("boom"))
    hist.discard_rotation_decision = AsyncMock()
    assert _run(sel._handle_decay(_score())) == "warning"
    hist.discard_rotation_decision.assert_awaited()


def test_handle_decay_execute_false_warning():
    sel, hist, _ = _make_selector()
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=uuid.uuid4())
    hist.execute_rotation_in_db = AsyncMock(return_value=False)
    hist.discard_rotation_decision = AsyncMock(side_effect=RuntimeError("x"))  # except pass
    assert _run(sel._handle_decay(_score())) == "warning"


def test_handle_decay_email_falla_igual_rota():
    async def _sender(d):
        raise RuntimeError("smtp down")
    sel, hist, _ = _make_selector(email_sender=_sender)
    hist.get_pending_candidate = AsyncMock(
        return_value={"decision_id": uuid.uuid4(), "proposed_ticker": "GLD"})
    hist.execute_rotation_in_db = AsyncMock(return_value=True)
    hist.get_rotation_decision = AsyncMock(return_value={"id": 1})
    assert _run(sel._handle_decay(_score())) == "rotation"


# =============================================================================
# evaluate_all_sentinels
# =============================================================================

def test_evaluate_all_get_scores_falla_retorna_errores():
    sel, hist, _ = _make_selector()
    hist.expire_old_pending_candidates = AsyncMock(side_effect=RuntimeError("x"))
    hist.get_sentinel_scores = AsyncMock(side_effect=RuntimeError("db down"))
    stats = _run(sel.evaluate_all_sentinels())
    assert stats["errors"] == 1 and stats["evaluated"] == 0


def test_evaluate_all_cuenta_acciones_y_aisla_errores():
    sel, hist, _ = _make_selector()
    hist.expire_old_pending_candidates = AsyncMock()
    hist.get_sentinel_scores = AsyncMock(return_value=[
        _score(), _score(), _score(), _score(), _score(),
    ])
    sel._evaluate_one = AsyncMock(side_effect=[
        "rotation", "candidate", "warning", None, RuntimeError("boom"),
    ])
    sel._evaluate_idle_timeout = AsyncMock()
    stats = _run(sel.evaluate_all_sentinels())
    assert stats["evaluated"] == 5
    assert stats["rotations"] == 1 and stats["candidates"] == 1
    assert stats["warning"] == 1 and stats["errors"] == 1
    sel._evaluate_idle_timeout.assert_awaited()


# =============================================================================
# rollback_rotation
# =============================================================================

def test_rollback_rotation_exito():
    sel, hist, _ = _make_selector()
    hist.rollback_rotation_in_db = AsyncMock(return_value=True)
    assert _run(sel.rollback_rotation(uuid.uuid4(), "admin@x.com")) is True


def test_rollback_rotation_excepcion_devuelve_false():
    sel, hist, _ = _make_selector()
    hist.rollback_rotation_in_db = AsyncMock(side_effect=RuntimeError("x"))
    assert _run(sel.rollback_rotation(uuid.uuid4(), "admin@x.com")) is False


# =============================================================================
# _request_candidate
# =============================================================================

def _claude_result(*, success=True, ticker="GLD", reasoning="r", factor="fe"):
    parsed = {}
    if success:
        parsed = {"recommended_ticker": ticker, "candidates": ["GDX"],
                  "reasoning": reasoning, "factor_exposure_analysis": factor,
                  "overall_confidence": 0.8}
    return {"success": success, "parsed": parsed,
            "error": None if success else "claude failed", "model": "claude-x",
            "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01}


def _wire_request(hist, *, macro_ok=True, active=None, pending=None):
    hist.get_recent_macro_context = (
        AsyncMock(return_value={"risk_score": 0.2, "circuit_breaker": False,
                                "vix_delta": 1.0, "spy_delta": -0.5,
                                "recent_titles": []})
        if macro_ok else AsyncMock(side_effect=RuntimeError("macro")))
    hist.get_failed_tickers_for_sentinel = AsyncMock(return_value=["TSLA"]) \
        if macro_ok else AsyncMock(side_effect=RuntimeError("failed"))
    hist.get_active_sentinels = AsyncMock(return_value=active) if active is not None \
        else AsyncMock(side_effect=RuntimeError("active"))
    hist.get_active_pending_candidates = AsyncMock(return_value=pending) \
        if pending is not None else AsyncMock(side_effect=RuntimeError("pending"))


def test_request_candidate_warning_completo_guarda_pending():
    sel, hist, claude = _make_selector()
    did = uuid.uuid4()
    _wire_request(
        hist,
        active=[{"name": "A", "strategy_type": "sma", "tickers": ["SPY", "QQQ"]},
                {"name": "B", "strategy_type": "rsi", "tickers": []}],
        pending=[{"sentinel_name": "OTHER", "proposed_ticker": "GLD",
                  "trigger_reason": "x"},
                 {"sentinel_name": "SELFNAME", "proposed_ticker": "SLV",
                  "trigger_reason": "y"}],
    )
    claude.call_json = AsyncMock(return_value=_claude_result())
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=did)
    hist.save_pending_candidate = AsyncMock()
    res = _run(sel._request_candidate(_score(name="SELFNAME"),
                                      trigger_reason="pre_decay_warning"))
    assert res == did
    hist.save_pending_candidate.assert_awaited()


def test_request_candidate_idle_usa_ttl_largo():
    sel, hist, claude = _make_selector()
    _wire_request(hist, active=[], pending=[])
    claude.call_json = AsyncMock(return_value=_claude_result())
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    hist.save_pending_candidate = AsyncMock()
    _run(sel._request_candidate(_score(), trigger_reason="idle_timeout"))
    kwargs = hist.save_pending_candidate.call_args.kwargs
    assert kwargs["ttl_days"] == us._IDLE_PENDING_TTL_DAYS


def test_request_candidate_fetch_excepciones_y_claude_falla():
    sel, hist, claude = _make_selector()
    _wire_request(hist, macro_ok=False)  # macro/failed/active/pending fallan
    claude.call_json = AsyncMock(return_value=_claude_result(success=False))
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    res = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert res is None  # Claude no produjo candidato


def test_request_candidate_factor_sin_reasoning():
    sel, hist, claude = _make_selector()
    _wire_request(hist, active=[], pending=[])
    claude.call_json = AsyncMock(
        return_value=_claude_result(reasoning=None, factor="solo factor"))
    sel._screen_candidate = AsyncMock(return_value=None)
    did = uuid.uuid4()
    hist.save_rotation_decision = AsyncMock(return_value=did)
    res = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert res == did


def test_request_candidate_save_rotation_falla():
    sel, hist, claude = _make_selector()
    _wire_request(hist, active=[], pending=[])
    claude.call_json = AsyncMock(return_value=_claude_result())
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(side_effect=RuntimeError("db"))
    res = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert res is None


def test_request_candidate_screen_bloquea():
    sel, hist, claude = _make_selector()
    _wire_request(hist, active=[], pending=[])
    claude.call_json = AsyncMock(return_value=_claude_result(ticker="SOXL"))
    sel._screen_candidate = AsyncMock(return_value="blocked_blacklist: SOXL leveraged")
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    res = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert res is None  # bloqueado → new_ticker None → failed


# =============================================================================
# _evaluate_idle_timeout
# =============================================================================

def _active_sentinel(sid=None, strat="rsi", name="NEO"):
    return {"sentinel_id": sid or uuid.uuid4(), "strategy_type": strat, "name": name}


def test_idle_timeout_get_active_falla():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(side_effect=RuntimeError("db"))
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats == {"idle": 0, "candidates": 0, "errors": 0}


def test_idle_timeout_check_falla_suma_error():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(side_effect=RuntimeError("boom"))
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats["errors"] == 1


def test_idle_timeout_con_pending_resuelve():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(return_value=["SPY"])
    hist.get_idle_pending_candidate = AsyncMock(return_value={"candidate_id": uuid.uuid4()})
    sel._resolve_idle_pending = AsyncMock()
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats["idle"] == 1
    sel._resolve_idle_pending.assert_awaited()


def test_idle_timeout_sin_pending_pide_candidato():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(return_value=["SPY"])
    hist.get_idle_pending_candidate = AsyncMock(return_value=None)
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=uuid.uuid4())
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats["candidates"] == 1


def test_idle_timeout_pending_de_otro_trigger_corta():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(return_value=["SPY"])
    hist.get_idle_pending_candidate = AsyncMock(return_value=None)
    hist.get_pending_candidate = AsyncMock(return_value={"candidate_id": uuid.uuid4()})
    sel._request_candidate = AsyncMock()
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    sel._request_candidate.assert_not_called()


def test_idle_timeout_resolve_falla_suma_error():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(return_value=["SPY"])
    hist.get_idle_pending_candidate = AsyncMock(return_value={"candidate_id": uuid.uuid4()})
    sel._resolve_idle_pending = AsyncMock(side_effect=RuntimeError("boom"))
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats["errors"] == 1


# =============================================================================
# _resolve_idle_pending — rama execute=False
# =============================================================================

def test_resolve_idle_pending_execute_false():
    sel, hist, _ = _make_selector()
    old = datetime.now() - timedelta(days=us._IDLE_EXECUTE_AFTER_DAYS + 1)
    pending = {"old_ticker": "SPY", "candidate_id": uuid.uuid4(),
               "proposed_ticker": "GLD", "proposed_at": old,
               "decision_id": uuid.uuid4()}
    hist.execute_rotation_in_db = AsyncMock(return_value=False)
    stats = {"rotations": 0}
    _run(sel._resolve_idle_pending(pending, {"SPY"}, stats))
    assert stats["rotations"] == 0  # no rotó porque execute devolvió False


def test_idle_timeout_get_idle_pending_falla_sigue_a_request():
    """get_idle_pending lanza → idle_pending None → cae al request branch."""
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(return_value=["SPY"])
    hist.get_idle_pending_candidate = AsyncMock(side_effect=RuntimeError("db"))
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(return_value=uuid.uuid4())
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats["candidates"] == 1


def test_idle_timeout_request_lanza_suma_error():
    sel, hist, _ = _make_selector()
    hist.get_active_sentinels = AsyncMock(return_value=[_active_sentinel()])
    sel._check_idle_tickers = AsyncMock(return_value=["SPY"])
    hist.get_idle_pending_candidate = AsyncMock(return_value=None)
    hist.get_pending_candidate = AsyncMock(return_value=None)
    sel._request_candidate = AsyncMock(side_effect=RuntimeError("claude boom"))
    stats = {"idle": 0, "candidates": 0, "errors": 0}
    _run(sel._evaluate_idle_timeout(stats))
    assert stats["errors"] == 1


def test_request_candidate_save_pending_falla_igual_retorna_id():
    sel, hist, claude = _make_selector()
    did = uuid.uuid4()
    _wire_request(hist, active=[], pending=[])
    claude.call_json = AsyncMock(return_value=_claude_result())
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=did)
    hist.save_pending_candidate = AsyncMock(side_effect=RuntimeError("unique"))
    res = _run(sel._request_candidate(_score(), trigger_reason="pre_decay_warning"))
    assert res == did  # save_pending falla pero la decisión ya está persistida


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
