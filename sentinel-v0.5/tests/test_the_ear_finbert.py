"""Tests T-U Sub-4 — integración FinBERT (hybrid mode) en The Ear.

SentimentAnalyzer mockeado (DIP) — sin cargar el modelo real. Cubre
_compute_finbert_score y las ramas de evaluate (flag off/on, analyzer
ausente/presente, score disponible o no, veto sí/no) + persistencia de los
campos sentiment en macro_events.

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_the_ear_finbert.py -v
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import the_ear
from the_ear import TheEar


def _run(coro):
    return asyncio.run(coro)


def _analyzer(scores):
    """SentimentAnalyzer fake: batch_score devuelve `scores` (lista [-1,1]/None)."""
    a = MagicMock()
    a.batch_score = MagicMock(return_value=scores)
    return a


def _evaluable_ear(articles, *, analyzer=None, parking=False, breaker=False):
    ear = TheEar(MagicMock(), sentiment_analyzer=analyzer)
    ear.historian.record_macro_event = AsyncMock()
    ear.fetch_news = AsyncMock(return_value=articles)
    ear.check_parking_brake = MagicMock(return_value=parking)
    ear.check_circuit_breaker = AsyncMock(return_value=breaker)
    return ear


# =============================================================================
# _compute_finbert_score
# =============================================================================

def test_compute_finbert_sin_analyzer_none():
    ear = TheEar(MagicMock(), sentiment_analyzer=None)
    assert ear._compute_finbert_score([{"title": "x", "description": ""}]) is None


def test_compute_finbert_sin_articulos_none():
    ear = TheEar(MagicMock(), sentiment_analyzer=_analyzer([0.5]))
    assert ear._compute_finbert_score([]) is None


def test_compute_finbert_todos_none_devuelve_none():
    ear = TheEar(MagicMock(), sentiment_analyzer=_analyzer([None, None]))
    out = ear._compute_finbert_score([{"title": "a"}, {"title": "b"}])
    assert out is None


def test_compute_finbert_promedia_no_none():
    ear = TheEar(MagicMock(), sentiment_analyzer=_analyzer([0.4, -0.2, None]))
    out = ear._compute_finbert_score([{"title": "a"}, {"title": "b"}, {"title": "c"}])
    assert abs(out - 0.1) < 1e-9   # promedio de [0.4, -0.2]


# =============================================================================
# evaluate — flag gating + hybrid mode + veto
# =============================================================================

def test_evaluate_flag_off_es_keyword_aunque_haya_analyzer():
    analyzer = _analyzer([-0.9])
    ear = _evaluable_ear([{"title": "x", "description": ""}], analyzer=analyzer)
    with patch.object(the_ear, "THE_EAR_SENTIMENT_ENABLED", False):
        out = _run(ear.evaluate())
    assert out["sentiment_method"] == "keyword"
    assert out["sentiment_score_finbert"] is None
    assert out["finbert_veto"] is False
    analyzer.batch_score.assert_not_called()   # ni se invoca FinBERT


def test_evaluate_flag_on_sin_analyzer_es_keyword():
    ear = _evaluable_ear([{"title": "x", "description": ""}], analyzer=None)
    with patch.object(the_ear, "THE_EAR_SENTIMENT_ENABLED", True):
        out = _run(ear.evaluate())
    assert out["sentiment_method"] == "keyword"
    assert out["sentiment_score_finbert"] is None


def test_evaluate_flag_on_finbert_positivo_hybrid_sin_veto():
    ear = _evaluable_ear([{"title": "rally", "description": ""}],
                         analyzer=_analyzer([0.7]))
    with patch.object(the_ear, "THE_EAR_SENTIMENT_ENABLED", True):
        out = _run(ear.evaluate())
    assert out["sentiment_method"] == "hybrid"
    assert out["sentiment_score_finbert"] == 0.7
    assert out["finbert_veto"] is False
    assert out["can_trade"] is True


def test_evaluate_flag_on_finbert_bajista_veta():
    ear = _evaluable_ear([{"title": "x", "description": ""}],
                         analyzer=_analyzer([-0.8]))
    with patch.object(the_ear, "THE_EAR_SENTIMENT_ENABLED", True):
        out = _run(ear.evaluate())
    assert out["sentiment_method"] == "hybrid"
    assert out["finbert_veto"] is True
    assert out["can_trade"] is False   # veto FinBERT bloquea aunque keyword no


def test_evaluate_flag_on_finbert_sin_score_cae_a_keyword():
    # analyzer presente pero todos los titulares dan None → method keyword.
    ear = _evaluable_ear([{"title": "x", "description": ""}],
                         analyzer=_analyzer([None]))
    with patch.object(the_ear, "THE_EAR_SENTIMENT_ENABLED", True):
        out = _run(ear.evaluate())
    assert out["sentiment_method"] == "keyword"
    assert out["sentiment_score_finbert"] is None


def test_evaluate_persiste_sentiment_en_macro_event():
    ear = _evaluable_ear([{"title": "x", "description": ""}],
                         analyzer=_analyzer([-0.3]))
    with patch.object(the_ear, "THE_EAR_SENTIMENT_ENABLED", True):
        _run(ear.evaluate())
    kwargs = ear.historian.record_macro_event.call_args.kwargs
    assert kwargs["sentiment_method"] == "hybrid"
    assert kwargs["sentiment_score_finbert"] == -0.3
