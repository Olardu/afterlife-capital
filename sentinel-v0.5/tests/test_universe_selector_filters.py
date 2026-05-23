"""Tests de la lista negra del Universe Selector + filtros técnicos de elegibilidad.

Cubre:
  - `_filter_candidate_eligibility(ticker, client)`: valida que un asset esté
    ACTIVE, tradable y fractionable vía Alpaca Assets API antes de proponerlo o
    confirmarlo como rotación (defensa técnica).
  - `SYSTEM_PROMPT`: contiene la lista negra explícita de productos leveraged /
    inverse / volatilidad / decay (defensa preventiva — evita el bucle de
    rotación zombie tipo Mantis 08-may con SQQQ / UVXY / USO).

Mock del client Alpaca (sin red ni DB). Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_universe_selector_filters.py -v
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from alpaca.trading.enums import AssetStatus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universe_selector import (
    SYSTEM_PROMPT,
    UniverseSelector,
    _BLACKLIST,
    _filter_candidate_eligibility,
)


def _run(coro):
    return asyncio.run(coro)


def _asset(*, status=AssetStatus.ACTIVE, tradable=True, fractionable=True,
           marginable=True, shortable=True):
    """Asset Alpaca falso con los flags que mira el filtro."""
    return SimpleNamespace(
        status=status, tradable=tradable, fractionable=fractionable,
        marginable=marginable, shortable=shortable,
    )


def _client(asset=None, raises=None):
    """Client Alpaca mock. get_asset es SÍNCRONO (la función lo corre en to_thread)."""
    client = MagicMock()
    if raises is not None:
        client.get_asset = MagicMock(side_effect=raises)
    else:
        client.get_asset = MagicMock(return_value=asset)
    return client


# --- Caso 1: asset elegible -------------------------------------------------
def test_asset_activo_tradable_fractionable_es_elegible():
    result = _run(_filter_candidate_eligibility("NVDA", _client(_asset())))
    assert result["eligible"] is True
    assert result["reason"] is None
    assert result["asset"] is not None


# --- Caso 2: no fractionable (Sentinel opera fraccional) --------------------
def test_asset_no_fractionable_es_rechazado():
    result = _run(_filter_candidate_eligibility("XYZ", _client(_asset(fractionable=False))))
    assert result["eligible"] is False
    assert result["reason"] == "not_fractionable"


# --- Caso 3: lookup falla (ticker inexistente / error de red) ---------------
def test_lookup_fallido_es_rechazado_sin_crashear():
    result = _run(_filter_candidate_eligibility("ZZZZ", _client(raises=Exception("404 not found"))))
    assert result["eligible"] is False
    assert result["reason"].startswith("asset_lookup_failed")


# --- Caso 4: asset inactivo -------------------------------------------------
def test_asset_inactivo_es_rechazado():
    result = _run(_filter_candidate_eligibility("DEAD", _client(_asset(status=AssetStatus.INACTIVE))))
    assert result["eligible"] is False
    assert result["reason"].startswith("not_active")


# --- Caso 5: lista negra presente en el SYSTEM_PROMPT -----------------------
def test_system_prompt_contiene_lista_negra():
    # Símbolos representativos de cada familia prohibida (decay / contango).
    for simbolo in ("SQQQ", "TQQQ", "UVXY", "VXX", "USO", "BITI"):
        assert simbolo in SYSTEM_PROMPT, f"{simbolo} falta en la lista negra del prompt"
    assert "PROHIBIDO PROPONER" in SYSTEM_PROMPT


# =============================================================================
# Cableo POST-Claude en _request_candidate — defensa doble (blacklist + filtro)
# =============================================================================

def _claude_result(ticker):
    """Resultado exitoso de claude.call_json proponiendo `ticker`."""
    return {
        "success": True,
        "parsed": {
            "recommended_ticker": ticker,
            "candidates": [],
            "reasoning": "razonamiento de prueba",
            "overall_confidence": 0.8,
            "factor_exposure_analysis": "cubre Ambiente 2",
        },
        "error": None,
        "model": "claude-sonnet-4-6",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.01,
    }


def _selector(claude_ticker):
    """UniverseSelector con historian + claude mockeados; Claude propone claude_ticker."""
    hist = MagicMock()
    hist.get_recent_macro_context = AsyncMock(return_value={
        "risk_score": 0.0, "circuit_breaker": False,
        "vix_delta": None, "spy_delta": None, "recent_titles": [],
    })
    hist.get_failed_tickers_for_sentinel = AsyncMock(return_value=[])
    hist.get_active_sentinels = AsyncMock(return_value=[])
    hist.get_active_pending_candidates = AsyncMock(return_value=[])
    hist.save_rotation_decision = AsyncMock(return_value=uuid4())
    hist.save_pending_candidate = AsyncMock()

    claude = MagicMock()
    claude.call_json = AsyncMock(return_value=_claude_result(claude_ticker))

    sel = UniverseSelector(
        historian=hist, claude_client=claude, owner_id=uuid4(), email_sender=None,
    )
    return sel, hist


def _score(ticker="OLDT"):
    return {
        "sentinel_id": uuid4(), "ticker": ticker, "sentinel_name": "S-X TEST",
        "strategy_type": "macd_volume", "win_rate": 0.3,
        "sharpe_ratio": -0.5, "total_trades": 20,
    }


# --- Caso 6: ticker en blacklist → bloqueado, fail-cerrada ------------------
def test_request_candidate_bloquea_ticker_en_blacklist():
    assert "SQQQ" in _BLACKLIST  # precondición
    sel, hist = _selector("SQQQ")
    # SQQQ se bloquea por lista negra SIN tocar Alpaca.
    result = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert result is None  # fail-cerrada, no rota
    _, kwargs = hist.save_rotation_decision.call_args
    assert kwargs["status"] == "failed"
    assert kwargs["new_ticker"] is None
    assert "blocked_blacklist" in kwargs["claude_reasoning"]


# --- Caso 7: ticker no fractionable → bloqueado por filtro técnico ----------
def test_request_candidate_bloquea_ticker_no_elegible():
    sel, hist = _selector("XYZ")
    fake_client = MagicMock()
    fake_client.get_asset = MagicMock(return_value=_asset(fractionable=False))
    with patch("alpaca.trading.client.TradingClient", return_value=fake_client):
        result = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert result is None
    _, kwargs = hist.save_rotation_decision.call_args
    assert kwargs["status"] == "failed"
    assert "blocked_eligibility" in kwargs["claude_reasoning"]
    assert "not_fractionable" in kwargs["claude_reasoning"]


# --- Caso 8: ticker válido → procede normalmente (no bloquea) ---------------
def test_request_candidate_permite_ticker_valido():
    sel, hist = _selector("MSFT")
    fake_client = MagicMock()
    fake_client.get_asset = MagicMock(return_value=_asset())
    with patch("alpaca.trading.client.TradingClient", return_value=fake_client):
        result = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert result is not None  # decision_id devuelto, rotación procede
    _, kwargs = hist.save_rotation_decision.call_args
    assert kwargs["status"] == "pending"
    assert kwargs["new_ticker"] == "MSFT"


# --- Caso 9: falla de red en get_asset → fail-cerrada -----------------------
def test_request_candidate_falla_red_alpaca_es_fail_cerrada():
    sel, hist = _selector("ABCD")
    fake_client = MagicMock()
    fake_client.get_asset = MagicMock(side_effect=Exception("connection reset"))
    with patch("alpaca.trading.client.TradingClient", return_value=fake_client):
        result = _run(sel._request_candidate(_score(), trigger_reason="decay_confirmed"))
    assert result is None
    _, kwargs = hist.save_rotation_decision.call_args
    assert kwargs["status"] == "failed"
    assert "asset_lookup_failed" in kwargs["claude_reasoning"]
