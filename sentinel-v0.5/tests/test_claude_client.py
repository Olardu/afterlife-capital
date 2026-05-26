"""Tests T-P #FASE2-NEW-4 — claude_client (cobertura 18% → 95%).

estimate_cost_usd: pricing conocido vs modelo desconocido.
ClaudeClient.__init__: defaults + RuntimeError sin API key.
call_json: éxito (JSON válido), costo sobre cap (warning), parse fallido, sin
TextBlock, y las 5 ramas de excepción (timeout/rate-limit/status/connection/
inesperada). close: éxito + excepción silenciada.

El cliente Anthropic real no se usa: se reemplaza por un MagicMock con
messages.create = AsyncMock. Las excepciones de la SDK se simulan con subclases
que no corren el __init__ original.

Correr: venv\\Scripts\\python.exe -m pytest tests/test_claude_client.py -v
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic

import claude_client
from claude_client import ClaudeClient, estimate_cost_usd


def _run(coro):
    return asyncio.run(coro)


# --- fakes de respuesta de la SDK -------------------------------------------
class _Usage:
    def __init__(self, inp, out, cache=0):
        self.input_tokens = inp
        self.output_tokens = out
        self.cache_read_input_tokens = cache


class _Block:
    def __init__(self, text, btype="text"):
        self.type = btype
        self.text = text


class _Resp:
    def __init__(self, usage, content, stop_reason="end_turn"):
        self.usage = usage
        self.content = content
        self.stop_reason = stop_reason


# --- fakes de excepciones de la SDK (sin correr __init__ original) ----------
class _FakeTimeout(anthropic.APITimeoutError):
    def __init__(self):
        pass


class _FakeRateLimit(anthropic.RateLimitError):
    def __init__(self):
        pass


class _FakeStatus(anthropic.APIStatusError):
    def __init__(self):
        self.status_code = 503
        self.message = "service down"


class _FakeConn(anthropic.APIConnectionError):
    def __init__(self):
        pass


def _client(**kw):
    """ClaudeClient con cliente Anthropic reemplazado por un mock."""
    cc = ClaudeClient(api_key="fake-key", model="claude-sonnet-4-6",
                      max_cost_per_call_usd=kw.get("max_cost", 0.20))
    cc.client = MagicMock()
    return cc


def _with_create(cc, *, returns=None, raises=None):
    cc.client.messages.create = AsyncMock(return_value=returns, side_effect=raises)
    return cc


# --- estimate_cost_usd ------------------------------------------------------
def test_cost_modelo_conocido():
    # sonnet: 1000 in * 3/1M + 500 out * 15/1M = 0.003 + 0.0075 = 0.0105
    assert estimate_cost_usd("claude-sonnet-4-6", 1000, 500) == pytest.approx(0.0105)


def test_cost_modelo_desconocido_es_cero():
    assert estimate_cost_usd("modelo-inexistente", 1000, 500) == 0.0


# --- __init__ ---------------------------------------------------------------
def test_init_sin_api_key_levanta():
    with patch.object(claude_client, "ANTHROPIC_API_KEY", None):
        with pytest.raises(RuntimeError):
            ClaudeClient(api_key=None)


def test_init_defaults():
    cc = _client()
    assert cc.model == "claude-sonnet-4-6"
    assert cc.max_cost == 0.20
    assert cc.timeout is not None


# --- call_json: camino feliz ------------------------------------------------
def _call(cc):
    return _run(cc.call_json(system_prompt="S", user_prompt="U", response_schema={}))


def test_call_json_exito():
    resp = _Resp(_Usage(1000, 500), [_Block('{"ticker": "NVDA"}')])
    cc = _with_create(_client(), returns=resp)
    out = _call(cc)
    assert out["success"] is True
    assert out["parsed"] == {"ticker": "NVDA"}
    assert out["cost_usd"] == pytest.approx(0.0105)
    assert out["stop_reason"] == "end_turn"
    assert out["error"] is None


def test_call_json_costo_sobre_cap_loggea_warning():
    resp = _Resp(_Usage(1_000_000, 0), [_Block('{"ok": true}')])  # ~$3 > cap 0.20
    cc = _with_create(_client(max_cost=0.20), returns=resp)
    with patch.object(claude_client, "logger") as log:
        out = _call(cc)
    assert out["success"] is True
    assert log.warning.called


def test_call_json_parse_fallido():
    resp = _Resp(_Usage(10, 10), [_Block("esto no es json")])
    cc = _with_create(_client(), returns=resp)
    out = _call(cc)
    assert out["success"] is False
    assert out["parsed"] is None
    assert out["error"] == "parse_failed"


def test_call_json_sin_textblock():
    resp = _Resp(_Usage(10, 10), [])   # sin bloques de texto
    cc = _with_create(_client(), returns=resp)
    out = _call(cc)
    assert out["success"] is False
    assert out["raw_text"] is None
    assert out["error"] == "parse_failed"


def test_call_json_truncado_por_max_tokens():
    """#TECH-005: JSON incompleto + stop_reason='max_tokens' → error tipificado
    'truncated_max_tokens' (no el genérico 'parse_failed'), para diagnóstico."""
    # JSON cortado a media string, como el caso NVDA→GLD del 26-may
    resp = _Resp(_Usage(10, 2000),
                 [_Block('{"recommended_ticker": "GLD", "reasoning": "ETF de oro líqui')],
                 stop_reason="max_tokens")
    cc = _with_create(_client(), returns=resp)
    out = _call(cc)
    assert out["success"] is False
    assert out["parsed"] is None
    assert out["error"] == "truncated_max_tokens"
    assert out["stop_reason"] == "max_tokens"


def test_call_json_truncado_pero_json_completo_es_exito():
    """stop_reason='max_tokens' pero el JSON alcanzó a cerrarse → success igual."""
    resp = _Resp(_Usage(10, 2000), [_Block('{"recommended_ticker": "NVDA"}')],
                 stop_reason="max_tokens")
    cc = _with_create(_client(), returns=resp)
    out = _call(cc)
    assert out["success"] is True
    assert out["error"] is None


# --- call_json: ramas de excepción ------------------------------------------
def test_call_json_timeout():
    cc = _with_create(_client(), raises=_FakeTimeout())
    out = _call(cc)
    assert out["success"] is False
    assert out["error"].startswith("timeout_")


def test_call_json_rate_limit():
    cc = _with_create(_client(), raises=_FakeRateLimit())
    out = _call(cc)
    assert out["error"] == "rate_limit"


def test_call_json_status_error():
    cc = _with_create(_client(), raises=_FakeStatus())
    out = _call(cc)
    assert out["error"].startswith("http_503")


def test_call_json_connection_error():
    cc = _with_create(_client(), raises=_FakeConn())
    out = _call(cc)
    assert out["error"] == "connection_error"


def test_call_json_excepcion_inesperada():
    cc = _with_create(_client(), raises=ValueError("raro"))
    out = _call(cc)
    assert out["error"].startswith("unexpected: ValueError")


# --- close ------------------------------------------------------------------
def test_close_ok():
    cc = _client()
    cc.client.close = AsyncMock()
    _run(cc.close())
    cc.client.close.assert_awaited_once()


def test_close_silencia_error():
    cc = _client()
    cc.client.close = AsyncMock(side_effect=RuntimeError("ya cerrado"))
    _run(cc.close())   # no debe propagar


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
