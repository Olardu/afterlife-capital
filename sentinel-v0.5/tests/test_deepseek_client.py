"""Tests de deepseek_client (swap FinBERT→DeepSeek).

Cubre: estimate_cost_usd (modelo conocido/desconocido), construcción sin key
(RuntimeError), call_json éxito (parseo + tokens + costo), HTTP != 200, timeout,
ClientError, respuesta malformada (sin choices), y JSON de contenido no parseable.
aiohttp mockeado — sin red.

Correr: venv\\Scripts\\python.exe -m pytest tests/test_deepseek_client.py -v
"""
import asyncio
import os
import sys
from unittest.mock import patch

import aiohttp
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deepseek_client
from deepseek_client import DeepSeekClient, estimate_cost_usd


def _run(coro):
    return asyncio.run(coro)


# --- estimate_cost_usd ------------------------------------------------------
def test_estimate_cost_modelo_conocido():
    # flash: input 0.14 / output 0.28 por 1M.
    cost = estimate_cost_usd("deepseek-v4-flash", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.14 + 0.28)


def test_estimate_cost_modelo_desconocido_es_cero():
    assert estimate_cost_usd("modelo-fantasma", 1000, 1000) == 0.0


# --- construcción -----------------------------------------------------------
def test_init_sin_key_lanza():
    with patch.object(deepseek_client, "DEEPSEEK_API_KEY", None):
        with pytest.raises(RuntimeError):
            DeepSeekClient(api_key=None)


def test_init_con_key_explicita_ok():
    c = DeepSeekClient(api_key="sk-test", model="deepseek-v4-flash")
    assert c.model == "deepseek-v4-flash" and c.base_url.startswith("https://")


# --- fakes de aiohttp -------------------------------------------------------
class _FakeResp:
    def __init__(self, status, json_data=None, text_data=""):
        self.status = status
        self._json = json_data if json_data is not None else {}
        self._text = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class _RaisingCM:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, post_cm):
        self._post_cm = post_cm

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, *a, **kw):
        return self._post_cm


def _patch_session(post_cm):
    return patch.object(deepseek_client.aiohttp, "ClientSession", lambda *a, **kw: _FakeSession(post_cm))


def _client():
    return DeepSeekClient(api_key="sk-test", model="deepseek-v4-flash")


def _call():
    return _client().call_json(system_prompt="sys", user_prompt="usr")


# --- call_json --------------------------------------------------------------
def test_call_json_exito_parsea_y_cuenta_tokens():
    payload = {
        "choices": [{"message": {"content": '{"risk_score": 0.8, "top_risk_ids": [0]}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }
    with _patch_session(_FakeResp(200, payload)):
        out = _run(_call())
    assert out["success"] is True
    assert out["parsed"] == {"risk_score": 0.8, "top_risk_ids": [0]}
    assert out["input_tokens"] == 100 and out["output_tokens"] == 20
    assert out["cost_usd"] > 0 and out["error"] is None


def test_call_json_http_no_200():
    with _patch_session(_FakeResp(429, text_data="rate limited")):
        out = _run(_call())
    assert out["success"] is False and out["error"].startswith("http_429")


def test_call_json_timeout():
    with _patch_session(_RaisingCM(aiohttp.ServerTimeoutError())):
        out = _run(_call())
    assert out["success"] is False and out["error"].startswith("timeout_")


def test_call_json_client_error():
    with _patch_session(_RaisingCM(aiohttp.ClientError("boom"))):
        out = _run(_call())
    assert out["success"] is False and out["error"].startswith("connection_error")


def test_call_json_excepcion_inesperada():
    with _patch_session(_RaisingCM(ValueError("raro"))):
        out = _run(_call())
    assert out["success"] is False and out["error"].startswith("unexpected")


def test_call_json_respuesta_malformada_sin_choices():
    # choices vacío → content "" → parse_failed (no JSON).
    with _patch_session(_FakeResp(200, {"choices": [], "usage": {}})):
        out = _run(_call())
    assert out["success"] is False and out["error"] == "parse_failed"


def test_call_json_contenido_no_parseable():
    payload = {"choices": [{"message": {"content": "no soy json {"}}], "usage": {}}
    with _patch_session(_FakeResp(200, payload)):
        out = _run(_call())
    assert out["success"] is False and out["error"] == "parse_failed"
    assert out["raw_text"] == "no soy json {"


def test_call_json_forma_inesperada_malformed():
    # message no es dict → choice.get("message").get(...) lanza AttributeError →
    # rama malformed_response.
    payload = {"choices": [{"message": "soy string"}], "usage": {}}
    with _patch_session(_FakeResp(200, payload)):
        out = _run(_call())
    assert out["success"] is False and out["error"] == "malformed_response"


def test_call_json_parsed_no_dict_es_parse_failed():
    # JSON válido pero array (no dict) → se normaliza a None.
    payload = {"choices": [{"message": {"content": "[1, 2, 3]"}}], "usage": {}}
    with _patch_session(_FakeResp(200, payload)):
        out = _run(_call())
    assert out["success"] is False and out["parsed"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
