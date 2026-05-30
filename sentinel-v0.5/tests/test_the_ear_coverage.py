"""Tests de cobertura de the_ear tras el swap FinBERT→DeepSeek + Alpaca News.

Cubre: build_risk_user_prompt, _dedup_articles, fetch_news (Alpaca, éxito/timeout/
excepción), _fetch_news_sync (mapeo del modelo News), assess_risk (éxito/clamp/ids
inválidos/no-numérico/fallo/sin-cliente/sin-artículos), _map_top_titles,
_update_news_veto (entra a los N ciclos / spike aislado no frena / histéresis de
salida), check_circuit_breaker, _fetch_price_changes, check_parking_brake,
evaluate (con/ sin assessment, veto, breaker, error al persistir) y start_polling.

Correr: venv\\Scripts\\python.exe -m pytest tests/test_the_ear_coverage.py -v
"""
import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import the_ear
from the_ear import TheEar, _dedup_articles, build_risk_user_prompt


def _run(coro):
    return asyncio.run(coro)


def _ear(deepseek=None):
    return TheEar(MagicMock(), deepseek_client=deepseek)


# --- build_risk_user_prompt -------------------------------------------------
def test_build_user_prompt_numera_y_pone_timestamp():
    arts = [
        {"title": "Crash", "summary": "markets fall", "published_at": "2026-05-30T10:00:00Z"},
        {"title": "Rally", "summary": "", "published_at": ""},
    ]
    out = build_risk_user_prompt(arts)
    assert "0 | 2026-05-30T10:00:00Z | Crash - markets fall" in out
    assert "1 |  | Rally -" in out
    assert out.strip().endswith("Return only the JSON object.")


# --- _dedup_articles (por title, published_at) ------------------------------
def test_dedup_elimina_repetidos_preserva_orden():
    arts = [
        {"title": "Crash", "published_at": "t1"},
        {"title": "Rally", "published_at": "t2"},
        {"title": "Crash", "published_at": "t1"},   # dup exacto
    ]
    assert [a["title"] for a in _dedup_articles(arts)] == ["Crash", "Rally"]


def test_dedup_distingue_por_published_at():
    arts = [
        {"title": "Fed hikes", "published_at": "t1"},
        {"title": "Fed hikes", "published_at": "t2"},
    ]
    assert len(_dedup_articles(arts)) == 2


def test_dedup_lista_vacia():
    assert _dedup_articles([]) == []


# --- fetch_news (Alpaca News, vía to_thread) --------------------------------
def test_fetch_news_exito_dedupea_y_capea():
    ear = _ear()
    dup = {"title": "A", "summary": "s", "published_at": "t", "source": "WSJ"}
    ear._fetch_news_sync = MagicMock(return_value=[dup, dict(dup), {"title": "B", "summary": "", "published_at": "t2", "source": "BZ"}])
    out = _run(ear.fetch_news())
    assert [a["title"] for a in out] == ["A", "B"]   # dup descartado


def test_fetch_news_timeout_retorna_vacio():
    ear = _ear()

    async def _raise(coro, *a, **k):
        coro.close()   # evita el RuntimeWarning de coroutine no-awaited
        raise asyncio.TimeoutError()

    with patch.object(the_ear.asyncio, "wait_for", _raise):
        assert _run(ear.fetch_news()) == []


def test_fetch_news_excepcion_retorna_vacio():
    ear = _ear()
    ear._fetch_news_sync = MagicMock(side_effect=RuntimeError("alpaca down"))
    assert _run(ear.fetch_news()) == []


def test_fetch_news_capea_al_maximo():
    ear = _ear()
    big = [{"title": f"t{i}", "summary": "", "published_at": f"p{i}", "source": "S"} for i in range(100)]
    ear._fetch_news_sync = MagicMock(return_value=big)
    out = _run(ear.fetch_news())
    assert len(out) == the_ear.NEWS_BATCH_MAX_ARTICLES


# --- _fetch_news_sync (mapeo del modelo News de Alpaca) ---------------------
def _patch_newsclient(items):
    fake_set = SimpleNamespace(data={"news": items})
    client = MagicMock()
    client.get_news.return_value = fake_set
    return patch("alpaca.data.historical.news.NewsClient", MagicMock(return_value=client))


def test_fetch_news_sync_mapea_headline_y_created_at():
    n = SimpleNamespace(
        headline="Recession fears", summary="bad", source="Benzinga",
        created_at=datetime(2026, 5, 30, 12, 0, tzinfo=ZoneInfo("UTC")),
    )
    with _patch_newsclient([n]):
        out = _ear()._fetch_news_sync()
    assert out[0]["title"] == "Recession fears"
    assert out[0]["summary"] == "bad" and out[0]["source"] == "Benzinga"
    assert out[0]["published_at"].startswith("2026-05-30T12:00")


def test_fetch_news_sync_sin_items():
    with _patch_newsclient([]):
        assert _ear()._fetch_news_sync() == []


def test_fetch_news_sync_result_dict_crudo():
    # get_news devuelve dict plano {"news": [...]} (sin atributo .data) → rama elif.
    n = SimpleNamespace(headline="H", summary="s", source="BZ", created_at=None)
    client = MagicMock()
    client.get_news.return_value = {"news": [n]}
    with patch("alpaca.data.historical.news.NewsClient", MagicMock(return_value=client)):
        out = _ear()._fetch_news_sync()
    assert out[0]["title"] == "H" and out[0]["published_at"] == ""   # created_at None → ""


def test_fetch_news_sync_result_inesperado_vacio():
    # get_news devuelve algo sin .data ni dict → items = [] (rama else).
    client = MagicMock()
    client.get_news.return_value = 42
    with patch("alpaca.data.historical.news.NewsClient", MagicMock(return_value=client)):
        assert _ear()._fetch_news_sync() == []


# --- assess_risk ------------------------------------------------------------
def _ds(parsed, success=True, error=None):
    client = MagicMock()
    client.call_json = AsyncMock(return_value={
        "success": success, "parsed": parsed, "cost_usd": 0.0, "error": error,
    })
    return client


_ARTS = [{"title": "Crash", "summary": "s", "published_at": "t", "source": "WSJ"},
         {"title": "Rally", "summary": "s", "published_at": "t2", "source": "BZ"}]


def test_assess_risk_sin_cliente_o_sin_articulos():
    assert _run(_ear().assess_risk(_ARTS)) is None          # sin cliente DeepSeek
    assert _run(_ear(_ds({})).assess_risk([])) is None      # con cliente pero sin artículos


def test_assess_risk_exito_mapea_top_titles():
    ear = _ear(_ds({"risk_score": 0.82, "top_risk_ids": [0], "rationale": "cluster risk-off"}))
    out = _run(ear.assess_risk(_ARTS))
    assert out["risk_score"] == 0.82
    assert out["top_titles"] == [{"title": "Crash", "source": "WSJ", "published_at": "t"}]
    assert out["rationale"] == "cluster risk-off"


def test_assess_risk_clampa_score():
    ear = _ear(_ds({"risk_score": 1.7, "top_risk_ids": [], "rationale": "x"}))
    assert _run(ear.assess_risk(_ARTS))["risk_score"] == 1.0


def test_assess_risk_filtra_ids_invalidos():
    # ids fuera de rango / no-int se descartan (anti-hallucination).
    ear = _ear(_ds({"risk_score": 0.5, "top_risk_ids": [9, "x", 1], "rationale": None}))
    out = _run(ear.assess_risk(_ARTS))
    assert out["top_titles"] == [{"title": "Rally", "source": "BZ", "published_at": "t2"}]
    assert out["rationale"] is None


def test_assess_risk_score_no_numerico_devuelve_none():
    ear = _ear(_ds({"risk_score": "alto", "top_risk_ids": []}))
    assert _run(ear.assess_risk(_ARTS)) is None


def test_assess_risk_call_fallida_devuelve_none():
    ear = _ear(_ds(None, success=False, error="timeout_20s"))
    assert _run(ear.assess_risk(_ARTS)) is None


# --- _update_news_veto (histéresis stateful) --------------------------------
def test_veto_no_entra_con_spike_aislado():
    ear = _ear()
    assert ear._update_news_veto(0.9) is False   # 1 ciclo alto → todavía NO
    assert ear._news_veto_active is False


def test_veto_entra_a_los_dos_ciclos():
    ear = _ear()
    ear._update_news_veto(0.9)
    assert ear._update_news_veto(0.9) is True     # 2º ciclo consecutivo → entra
    assert ear._news_veto_active is True


def test_veto_reset_si_baja_antes_del_segundo():
    ear = _ear()
    ear._update_news_veto(0.9)
    ear._update_news_veto(0.3)                     # corta la racha
    assert ear._consecutive_high_cycles == 0
    assert ear._news_veto_active is False


def test_veto_histeresis_se_mantiene_en_banda_muerta():
    ear = _ear()
    ear._update_news_veto(0.9); ear._update_news_veto(0.9)   # activo
    assert ear._update_news_veto(0.65) is True     # 0.60<=0.65<0.70 → sigue activo
    assert ear._update_news_veto(0.55) is False    # <EXIT → sale
    assert ear._news_veto_active is False


# --- check_circuit_breaker / _fetch_price_changes (intactos) ----------------
def test_cb_timeout_devuelve_estado_actual():
    ear = _ear()
    ear.circuit_breaker_active = True
    with patch.object(the_ear.asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
        assert _run(ear.check_circuit_breaker()) is True


def test_cb_excepcion_devuelve_estado_actual():
    ear = _ear()
    with patch.object(the_ear.asyncio, "wait_for", AsyncMock(side_effect=RuntimeError("boom"))):
        assert _run(ear.check_circuit_breaker()) is False


def test_cb_desactivacion_transicion():
    ear = _ear()
    ear.circuit_breaker_active = True
    ear._fetch_price_changes = MagicMock(return_value=(0.0, 0.0))
    assert _run(ear.check_circuit_breaker()) is False


def _df(rows):
    import pandas as pd
    tuples, closes = [], []
    for sym, vals in rows.items():
        for i, c in enumerate(vals):
            tuples.append((sym, i)); closes.append(c)
    idx = pd.MultiIndex.from_tuples(tuples, names=["symbol", "ts"])
    return pd.DataFrame({"close": closes}, index=idx)


def _patch_alpaca(df):
    client = MagicMock()
    client.get_stock_bars.return_value = MagicMock(df=df)
    return patch("alpaca.data.historical.StockHistoricalDataClient", MagicMock(return_value=client))


def test_fetch_price_changes_normal():
    with _patch_alpaca(_df({"VIXY": [10.0, 12.0], "SPY": [100.0, 98.0]})):
        vix, spy = _ear()._fetch_price_changes()
    assert vix == pytest.approx(20.0) and spy == pytest.approx(-2.0)


def test_fetch_price_changes_ausente_y_prev_cero():
    with _patch_alpaca(_df({"VIXY": [0.0, 5.0]})):
        vix, spy = _ear()._fetch_price_changes()
    assert vix is None and spy is None   # VIXY prev 0 → None; SPY ausente → None


def test_fetch_price_changes_pocas_barras():
    # VIXY con 1 sola barra → <2 → None (cubre la rama de pocas barras).
    with _patch_alpaca(_df({"VIXY": [10.0]})):
        vix, spy = _ear()._fetch_price_changes()
    assert vix is None and spy is None


# --- check_parking_brake ----------------------------------------------------
class _FrozenDT(datetime):
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now


def _freeze(dt):
    _FrozenDT._now = dt
    return patch.object(the_ear, "datetime", _FrozenDT)


def test_parking_brake_activo_despues_de_hora():
    with _freeze(datetime(2026, 5, 26, 15, 50, tzinfo=ZoneInfo("America/New_York"))):
        assert _ear().check_parking_brake() is True


def test_parking_brake_transicion_apagado():
    ear = _ear()
    ear.parking_brake_active = True
    with _freeze(datetime(2026, 5, 26, 10, 0, tzinfo=ZoneInfo("America/New_York"))):
        assert ear.check_parking_brake() is False


# --- evaluate (flujo completo) ----------------------------------------------
def _evaluable(assessment, *, parking=False, breaker=False, articles=None):
    ear = TheEar(MagicMock(), deepseek_client=MagicMock())
    ear.historian.record_macro_event = AsyncMock()
    ear.fetch_news = AsyncMock(return_value=articles if articles is not None else _ARTS)
    ear.assess_risk = AsyncMock(return_value=assessment)
    ear.check_parking_brake = MagicMock(return_value=parking)
    ear.check_circuit_breaker = AsyncMock(return_value=breaker)
    return ear


def test_evaluate_con_assessment_can_trade_true():
    ear = _evaluable({"risk_score": 0.1, "top_titles": [], "rationale": "calm"})
    out = _run(ear.evaluate())
    assert out["can_trade"] is True and out["risk_score"] == 0.1
    assert out["sentiment_method"] == "deepseek"
    ear.historian.record_macro_event.assert_awaited_once()


def test_evaluate_sin_assessment_usa_last_score():
    ear = _evaluable(None)
    ear.last_risk_score = 0.42
    out = _run(ear.evaluate())
    assert out["risk_score"] == 0.42 and out["risk_rationale"] is None


def test_evaluate_veto_tras_dos_ciclos_altos():
    ear = _evaluable({"risk_score": 0.95, "top_titles": [], "rationale": "crash"})
    assert _run(ear.evaluate())["can_trade"] is True    # 1er ciclo: aún no veta
    assert _run(ear.evaluate())["can_trade"] is False   # 2º ciclo: veta
    assert _run(ear.evaluate())["news_veto_active"] is True


def test_evaluate_breaker_bloquea():
    ear = _evaluable({"risk_score": 0.0, "top_titles": [], "rationale": "x"}, breaker=True)
    out = _run(ear.evaluate())
    assert out["circuit_breaker"] is True and out["can_trade"] is False


def test_evaluate_error_al_persistir_no_rompe():
    ear = _evaluable({"risk_score": 0.1, "top_titles": [], "rationale": "x"})
    ear.historian.record_macro_event = AsyncMock(side_effect=RuntimeError("db down"))
    assert "can_trade" in _run(ear.evaluate())


# --- start_polling ----------------------------------------------------------
def test_start_polling_un_ciclo_y_except():
    ear = _ear()
    ear.evaluate = AsyncMock(side_effect=RuntimeError("falla ciclo"))
    with patch.object(the_ear.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError())):
        with pytest.raises(asyncio.CancelledError):
            _run(ear.start_polling())
    ear.evaluate.assert_awaited()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
