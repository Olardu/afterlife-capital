"""Tests T-P #FASE2-NEW-4 — the_ear (cobertura 29% → 95%).

Complementa test_the_ear.py (que cubre #TD-5/#TD-6). Acá: helpers de keywords,
fetch_news (status!=200 / éxito / timeout / ClientError), extract_top_negative_titles,
calculate_risk_score, check_circuit_breaker (timeout/excepción/transiciones),
_fetch_price_changes (alpaca + df mockeados), check_parking_brake, evaluate
(flujo completo, ambas ramas de articles, can_trade, error al persistir),
start_polling (un ciclo + except).

Correr: venv\\Scripts\\python.exe -m pytest tests/test_the_ear_coverage.py -v
"""
import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import aiohttp
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import the_ear
from the_ear import (
    TheEar,
    _count_matches,
    _dedup_articles,
    _matched_keywords,
    _NEGATIVE_PATTERNS,
    _POSITIVE_PATTERNS,
)


def _run(coro):
    return asyncio.run(coro)


def _ear():
    return TheEar(MagicMock())


# --- helpers de keywords ----------------------------------------------------
def test_matched_keywords_vacio():
    assert _matched_keywords("", _NEGATIVE_PATTERNS) == []


def test_matched_keywords_ordenado():
    out = _matched_keywords("war and crash incoming", _NEGATIVE_PATTERNS)
    assert out == sorted(out)
    assert "crash" in out and "war" in out


def test_count_matches_vacio_y_con_hits():
    assert _count_matches("", _POSITIVE_PATTERNS) == 0
    assert _count_matches("rally and growth", _POSITIVE_PATTERNS) == 2


# --- fetch_news (con NEWS_API_KEY presente, mock de aiohttp) ----------------
class _FakeResp:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload


class _FakeGetCM:
    """Lo que devuelve session.get(...) — async CM que da la respuesta o levanta."""
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        if self._exc is not None:
            raise self._exc
        return self._resp

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, get_cm):
        self._get_cm = get_cm

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, *a, **kw):
        return self._get_cm


def _patch_session(get_cm):
    fake = _FakeSession(get_cm)
    return patch.object(the_ear.aiohttp, "ClientSession", lambda *a, **kw: fake)


def test_fetch_news_status_no_200():
    with patch.object(the_ear, "NEWS_API_KEY", "k"), \
         _patch_session(_FakeGetCM(resp=_FakeResp(429))):
        assert _run(_ear().fetch_news()) == []


def test_fetch_news_exito_mapea_articulos():
    payload = {"articles": [
        {"title": "Crash", "description": "d", "publishedAt": "2026", "source": {"name": "WSJ"}},
        {"title": None, "description": None, "publishedAt": None, "source": None},
    ]}
    with patch.object(the_ear, "NEWS_API_KEY", "k"), \
         _patch_session(_FakeGetCM(resp=_FakeResp(200, payload))):
        out = _run(_ear().fetch_news())
    assert len(out) == 2
    assert out[0] == {"title": "Crash", "description": "d", "publishedAt": "2026", "source": "WSJ"}
    # segundo artículo con None → strings vacíos
    assert out[1]["title"] == "" and out[1]["source"] == ""


def test_fetch_news_timeout():
    with patch.object(the_ear, "NEWS_API_KEY", "k"), \
         _patch_session(_FakeGetCM(exc=asyncio.TimeoutError())):
        assert _run(_ear().fetch_news()) == []


def test_fetch_news_client_error():
    with patch.object(the_ear, "NEWS_API_KEY", "k"), \
         _patch_session(_FakeGetCM(exc=aiohttp.ClientError())):
        assert _run(_ear().fetch_news()) == []


# --- extract_top_negative_titles --------------------------------------------
def test_extract_top_negative_rankea_y_filtra():
    articles = [
        {"title": "crash and recession", "description": "panic", "source": "A", "publishedAt": "t1"},
        {"title": "crash only", "description": "", "source": "B", "publishedAt": "t2"},
        {"title": "good news", "description": "growth", "source": "C", "publishedAt": "t3"},
    ]
    out = _ear().extract_top_negative_titles(articles, top_n=5)
    # el de 3 keywords (crash, recession, panic) primero; el de "good news" se filtra
    assert len(out) == 2
    assert out[0]["matched_keywords"] == ["crash", "panic", "recession"]
    assert out[1]["title"] == "crash only"


def test_extract_top_negative_respeta_top_n():
    articles = [{"title": "crash", "description": "", "source": "X", "publishedAt": "t"}] * 4
    assert len(_ear().extract_top_negative_titles(articles, top_n=2)) == 2


# --- calculate_risk_score ---------------------------------------------------
def test_risk_score_sin_articulos_usa_ultimo():
    ear = _ear()
    ear.last_risk_score = 0.42
    assert ear.calculate_risk_score([]) == 0.42


def test_risk_score_clampa_y_pondera():
    ear = _ear()
    # 2 negativas (crash, recession) - 1 positiva*0.5 (rally) sobre 1 artículo
    articles = [{"title": "crash recession rally", "description": ""}]
    score = ear.calculate_risk_score(articles)
    assert score == pytest.approx(min(1.0, (2 - 0.5) / 1))  # = 1.0 (clamp)


def test_risk_score_negativo_clampa_a_cero():
    ear = _ear()
    articles = [{"title": "rally surge growth", "description": ""}]  # solo positivas
    assert ear.calculate_risk_score(articles) == 0.0


# --- check_circuit_breaker: timeout / excepción / transición ----------------
def test_cb_timeout_devuelve_estado_actual():
    ear = _ear()
    ear.circuit_breaker_active = True
    ear._fetch_price_changes = MagicMock(side_effect=lambda: (_ for _ in ()).throw(TimeoutError()))
    with patch.object(the_ear.asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
        assert _run(ear.check_circuit_breaker()) is True


def test_cb_excepcion_devuelve_estado_actual():
    ear = _ear()
    ear.circuit_breaker_active = False
    with patch.object(the_ear.asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("boom"))):
        assert _run(ear.check_circuit_breaker()) is False


def test_cb_desactivacion_transicion():
    # Estaba activo; ahora datos normales (0,0) → se desactiva (cubre rama elif).
    ear = _ear()
    ear.circuit_breaker_active = True
    ear._fetch_price_changes = MagicMock(return_value=(0.0, 0.0))
    assert _run(ear.check_circuit_breaker()) is False
    assert ear.circuit_breaker_active is False


# --- _fetch_price_changes (alpaca + df mockeados) ---------------------------
def _df(rows):
    import pandas as pd
    tuples, closes = [], []
    for sym, vals in rows.items():
        for i, c in enumerate(vals):
            tuples.append((sym, i))
            closes.append(c)
    idx = pd.MultiIndex.from_tuples(tuples, names=["symbol", "ts"])
    return pd.DataFrame({"close": closes}, index=idx)


def _patch_alpaca(df):
    client = MagicMock()
    client.get_stock_bars.return_value = MagicMock(df=df)
    return patch("alpaca.data.historical.StockHistoricalDataClient",
                 MagicMock(return_value=client))


def test_fetch_price_changes_normal():
    df = _df({"VIXY": [10.0, 12.0], "SPY": [100.0, 98.0]})
    with _patch_alpaca(df):
        vix, spy = _ear()._fetch_price_changes()
    assert vix == pytest.approx(20.0)
    assert spy == pytest.approx(-2.0)


def test_fetch_price_changes_simbolo_ausente_y_pocas_barras():
    # VIXY presente con 1 sola barra → None; SPY ausente → None.
    df = _df({"VIXY": [10.0]})
    with _patch_alpaca(df):
        vix, spy = _ear()._fetch_price_changes()
    assert vix is None and spy is None


def test_fetch_price_changes_prev_cero():
    df = _df({"VIXY": [0.0, 5.0], "SPY": [100.0, 100.0]})
    with _patch_alpaca(df):
        vix, spy = _ear()._fetch_price_changes()
    assert vix is None             # prev 0 → None
    assert spy == pytest.approx(0.0)


# --- check_parking_brake ----------------------------------------------------
class _FrozenDT(datetime):
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now


def _freeze_ear(dt):
    _FrozenDT._now = dt
    return patch.object(the_ear, "datetime", _FrozenDT)


def test_parking_brake_activo_despues_de_hora():
    ear = _ear()
    with _freeze_ear(datetime(2026, 5, 26, 15, 50, tzinfo=ZoneInfo("America/New_York"))):
        assert ear.check_parking_brake() is True
    assert ear.parking_brake_active is True


def test_parking_brake_inactivo_y_transicion_apagado():
    ear = _ear()
    ear.parking_brake_active = True   # venía activo → cubre rama de "desactivado"
    with _freeze_ear(datetime(2026, 5, 26, 10, 0, tzinfo=ZoneInfo("America/New_York"))):
        assert ear.check_parking_brake() is False


# --- evaluate (flujo completo) ----------------------------------------------
def _evaluable_ear(articles, *, parking=False, breaker=False):
    ear = TheEar(MagicMock())
    ear.historian.record_macro_event = AsyncMock()
    ear.fetch_news = AsyncMock(return_value=articles)
    ear.check_parking_brake = MagicMock(return_value=parking)
    ear.check_circuit_breaker = AsyncMock(return_value=breaker)
    return ear


def test_evaluate_con_articulos_can_trade_true():
    ear = _evaluable_ear([{"title": "rally", "description": ""}])
    out = _run(ear.evaluate())
    assert out["can_trade"] is True
    assert out["news_disabled"] == ear.news_disabled
    ear.historian.record_macro_event.assert_awaited_once()


def test_evaluate_sin_articulos_usa_last_score():
    ear = _evaluable_ear([])
    ear.last_risk_score = 0.9    # > veto threshold → can_trade False
    out = _run(ear.evaluate())
    assert out["risk_score"] == 0.9
    assert out["can_trade"] is False


def test_evaluate_breaker_bloquea():
    ear = _evaluable_ear([{"title": "x", "description": ""}], breaker=True)
    out = _run(ear.evaluate())
    assert out["circuit_breaker"] is True
    assert out["can_trade"] is False


def test_evaluate_error_al_persistir_no_rompe():
    ear = _evaluable_ear([{"title": "x", "description": ""}])
    ear.historian.record_macro_event = AsyncMock(side_effect=RuntimeError("db down"))
    out = _run(ear.evaluate())   # no debe propagar
    assert "can_trade" in out


# --- start_polling (un ciclo + except + sleep) ------------------------------
def test_start_polling_un_ciclo():
    ear = _ear()
    ear.evaluate = AsyncMock(side_effect=RuntimeError("falla ciclo"))  # cubre except
    with patch.object(the_ear.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError())):
        with pytest.raises(asyncio.CancelledError):
            _run(ear.start_polling())
    ear.evaluate.assert_awaited()


# --- #BUG-NEW-1: dedup de titulares -----------------------------------------
def test_dedup_articles_elimina_repetidos_preserva_orden():
    arts = [
        {"title": "Crash", "publishedAt": "2026-05-29T10:00:00Z"},
        {"title": "Rally", "publishedAt": "2026-05-29T10:05:00Z"},
        {"title": "Crash", "publishedAt": "2026-05-29T10:00:00Z"},  # dup exacto
    ]
    out = _dedup_articles(arts)
    assert [a["title"] for a in out] == ["Crash", "Rally"]


def test_dedup_articles_distingue_por_published_at():
    # Mismo título pero distinto publishedAt → son notas distintas, se conservan.
    arts = [
        {"title": "Fed hikes", "publishedAt": "2026-05-29T10:00:00Z"},
        {"title": "Fed hikes", "publishedAt": "2026-05-29T14:00:00Z"},
    ]
    assert len(_dedup_articles(arts)) == 2


def test_dedup_articles_lista_vacia():
    assert _dedup_articles([]) == []


def test_fetch_news_dedupea_repetidos():
    # NewsAPI devuelve el mismo artículo 3 veces → fetch_news entrega 1.
    art = {"title": "Recession fears", "description": "d",
           "publishedAt": "2026-05-29T10:00:00Z", "source": {"name": "WSJ"}}
    payload = {"articles": [art, dict(art), dict(art)]}
    with patch.object(the_ear, "NEWS_API_KEY", "k"), \
         _patch_session(_FakeGetCM(resp=_FakeResp(200, payload))):
        out = _run(_ear().fetch_news())
    assert len(out) == 1
    assert out[0]["title"] == "Recession fears"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
