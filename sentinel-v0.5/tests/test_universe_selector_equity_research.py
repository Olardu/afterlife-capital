"""Tests T-T Sub-3 — integración Equity Research al system prompt del Universe Selector.

Verifica que el SYSTEM_PROMPT instruya análisis fundamental (10-K/10-Q, valuación,
comparables) además de macro+técnico, que el schema de respuesta acepte el campo
`fundamental_analysis`, que `build_user_prompt` lo solicite, y que el reasoning
expandido se persista concatenado en `rotation_decisions.claude_reasoning` (sin
migración — la columna es TEXT, mismo patrón que `factor_exposure_analysis`).

historian y claude_client mockeados — sin DB, sin red, sin Alpaca.

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_universe_selector_equity_research.py -v
"""
import asyncio
import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import universe_selector as us
from universe_selector import UniverseSelector, build_user_prompt


def _run(coro):
    return asyncio.run(coro)


def _make_selector(*, email_sender=None):
    hist = MagicMock()
    claude = MagicMock()
    sel = UniverseSelector(
        historian=hist, claude_client=claude,
        owner_id=uuid.uuid4(), email_sender=email_sender,
    )
    return sel, hist, claude


def _score(*, name="NEO", ticker="SPY", strat="rsi"):
    return {"sentinel_id": uuid.uuid4(), "ticker": ticker,
            "win_rate": 0.99, "sharpe_ratio": 5.0, "total_trades": 20,
            "sentinel_name": name, "strategy_type": strat}


def _claude_result(*, success=True, ticker="GLD", reasoning="r",
                   factor=None, fundamental=None):
    parsed = {}
    if success:
        parsed = {"recommended_ticker": ticker, "candidates": ["GDX"],
                  "reasoning": reasoning, "overall_confidence": 0.8}
        if factor is not None:
            parsed["factor_exposure_analysis"] = factor
        if fundamental is not None:
            parsed["fundamental_analysis"] = fundamental
    return {"success": success, "parsed": parsed,
            "error": None if success else "claude failed", "model": "claude-x",
            "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01}


def _wire_request(hist, *, active=None, pending=None):
    hist.get_recent_macro_context = AsyncMock(return_value={
        "risk_score": 0.2, "circuit_breaker": False,
        "vix_delta": 1.0, "spy_delta": -0.5, "recent_titles": []})
    hist.get_failed_tickers_for_sentinel = AsyncMock(return_value=["TSLA"])
    hist.get_active_sentinels = AsyncMock(return_value=active if active is not None else [])
    hist.get_active_pending_candidates = AsyncMock(
        return_value=pending if pending is not None else [])


def _persisted_reasoning(hist):
    """Devuelve el claude_reasoning con el que se llamó a save_rotation_decision."""
    return hist.save_rotation_decision.call_args.kwargs["claude_reasoning"]


# =============================================================================
# SYSTEM_PROMPT + schema + build_user_prompt (estáticos)
# =============================================================================

def test_system_prompt_instruye_analisis_fundamental():
    p = us.SYSTEM_PROMPT.lower()
    # Debe instruir el marco de análisis fundamental, no solo macro+técnico.
    assert "fundamental" in p
    # Algún anclaje concreto del toolkit Equity Research (10-K/10-Q, valuación,
    # comparables) para que Claude sepa qué dimensiones evaluar.
    assert "10-k" in p or "10-q" in p or "comparable" in p or "valuaci" in p


def test_system_prompt_distingue_acciones_de_etfs():
    # No queremos que Claude alucine un DCF sobre un ETF/commodity: el prompt
    # debe acotar el análisis fundamental a acciones individuales.
    p = us.SYSTEM_PROMPT.lower()
    assert "etf" in p and ("acciones individuales" in p or "acción individual" in p
                           or "individual stock" in p)


def test_response_schema_acepta_fundamental_analysis():
    props = us._RESPONSE_SCHEMA["properties"]
    assert "fundamental_analysis" in props
    assert props["fundamental_analysis"]["type"] == "string"
    # Sigue siendo opcional (no se fuerza para ETFs / contexto sin datos).
    assert "fundamental_analysis" not in us._RESPONSE_SCHEMA["required"]


def test_build_user_prompt_solicita_fundamental():
    out = build_user_prompt(sentinel=_score(), macro={}, failed_tickers=[],
                            reason="decay_confirmed")
    assert "fundamental_analysis" in out


# =============================================================================
# Persistencia del reasoning expandido (concatenación, sin migración)
# =============================================================================

def test_request_candidate_concatena_fundamental_al_reasoning():
    sel, hist, claude = _make_selector()
    _wire_request(hist)
    claude.call_json = AsyncMock(return_value=_claude_result(
        reasoning="base", fundamental="P/E bajo vs sector, FCF positivo"))
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    hist.save_pending_candidate = AsyncMock()
    _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    reasoning = _persisted_reasoning(hist)
    assert "base" in reasoning
    assert "[Fundamental analysis]" in reasoning
    assert "P/E bajo vs sector" in reasoning


def test_request_candidate_fundamental_sin_reasoning_arranca_bloque():
    sel, hist, claude = _make_selector()
    _wire_request(hist)
    claude.call_json = AsyncMock(return_value=_claude_result(
        reasoning=None, fundamental="solo fundamental"))
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    hist.save_pending_candidate = AsyncMock()
    _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    reasoning = _persisted_reasoning(hist)
    assert reasoning.startswith("[Fundamental analysis]")
    assert "solo fundamental" in reasoning


def test_request_candidate_fundamental_y_factor_ambos_presentes():
    sel, hist, claude = _make_selector()
    _wire_request(hist)
    claude.call_json = AsyncMock(return_value=_claude_result(
        reasoning="base", factor="cubre Ambiente 3", fundamental="balance sólido"))
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    hist.save_pending_candidate = AsyncMock()
    _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    reasoning = _persisted_reasoning(hist)
    assert "[Factor exposure analysis]" in reasoning
    assert "[Fundamental analysis]" in reasoning
    assert "balance sólido" in reasoning and "cubre Ambiente 3" in reasoning


def test_request_candidate_sin_fundamental_no_agrega_bloque():
    sel, hist, claude = _make_selector()
    _wire_request(hist)
    claude.call_json = AsyncMock(return_value=_claude_result(reasoning="base"))
    sel._screen_candidate = AsyncMock(return_value=None)
    hist.save_rotation_decision = AsyncMock(return_value=uuid.uuid4())
    hist.save_pending_candidate = AsyncMock()
    _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    reasoning = _persisted_reasoning(hist)
    assert "[Fundamental analysis]" not in reasoning
