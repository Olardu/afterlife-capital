"""Tests T-U Sub-2 — SentimentAnalyzer (FinBERT) puro.

El modelo real (transformers.pipeline) se mockea — sin descargar pesos, sin red.
Cubre: lazy load OK/falla, mapeo de labels a [-1,1], texto vacío/largo, inferencia
que lanza, batch_score (OK / vacíos / modelo ausente / fallback per-item / item
ilegible).

Correr:
  venv\\Scripts\\python.exe -m pytest tests/test_sentiment_analyzer.py -v
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Materializa el atributo lazy `transformers.pipeline` UNA vez (sin cargar ningún
# modelo) para que mock.patch lo intercepte de forma fiable. Sin esto, el primer
# patch de la suite topa con el _LazyModule de transformers y deja pasar la
# función real (cargaría el modelo de verdad). Ver T-U Sub-2.
import transformers
_ = transformers.pipeline

from sentiment_analyzer import SentimentAnalyzer


def _make_pipe(label="positive", confidence=0.9):
    """Pipeline fake: acepta str (un titular) o list (batch) y devuelve dicts."""
    def _call(arg):
        if isinstance(arg, list):
            return [{"label": label, "score": confidence} for _ in arg]
        return [{"label": label, "score": confidence}]
    return MagicMock(side_effect=_call)


# =============================================================================
# Guard clauses (sin cargar el modelo)
# =============================================================================

def test_score_texto_vacio_retorna_none():
    a = SentimentAnalyzer()
    assert a.score("") is None
    assert a.score("   ") is None
    assert a.score(None) is None


def test_score_modelo_no_carga_retorna_none_y_no_reintenta():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", side_effect=RuntimeError("sin modelo")) as p:
        assert a.score("Stocks rallied") is None
        assert a._load_failed is True
        # Segunda llamada NO reintenta la carga (corto por _load_failed).
        assert a.score("More news") is None
    assert p.call_count == 1


# =============================================================================
# Mapeo de labels → [-1, 1]
# =============================================================================

def test_score_positive_devuelve_confianza_positiva():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe("positive", 0.84)):
        assert a.score("Apple beats expectations") == 0.84


def test_score_negative_devuelve_confianza_negativa():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe("negative", 0.97)):
        assert a.score("Markets crash") == -0.97


def test_score_neutral_devuelve_cero():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe("neutral", 0.99)):
        assert a.score("Earnings in line with estimates") == 0.0


def test_label_to_score_directo():
    assert SentimentAnalyzer._label_to_score({"label": "Positive", "score": 0.5}) == 0.5
    assert SentimentAnalyzer._label_to_score({"label": "NEGATIVE", "score": 0.3}) == -0.3
    assert SentimentAnalyzer._label_to_score({"label": "neutral", "score": 0.7}) == 0.0
    assert SentimentAnalyzer._label_to_score({}) == 0.0  # robusto ante dict vacío


# =============================================================================
# Truncado + inferencia que lanza
# =============================================================================

def test_score_trunca_a_512_chars():
    a = SentimentAnalyzer()
    pipe = _make_pipe("positive", 0.5)
    with patch("transformers.pipeline", return_value=pipe):
        a.score("x" * 1000)
    # el pipeline recibió como máximo 512 chars
    arg = pipe.call_args.args[0]
    assert len(arg) == 512


def test_score_inferencia_lanza_retorna_none():
    a = SentimentAnalyzer()
    pipe = MagicMock(side_effect=ValueError("boom"))
    with patch("transformers.pipeline", return_value=pipe):
        assert a.score("algo") is None


def test_ensure_loaded_cachea_pipeline():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe()) as p:
        a.score("uno")
        a.score("dos")
    # el modelo se carga una sola vez (lazy + cache)
    assert p.call_count == 1


# =============================================================================
# batch_score
# =============================================================================

def test_batch_score_devuelve_lista_misma_longitud():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe("negative", 0.6)):
        out = a.batch_score(["a", "b", "c"])
    assert out == [-0.6, -0.6, -0.6]


def test_batch_score_vacio_en_el_medio_es_none():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe("positive", 0.7)):
        out = a.batch_score(["bull news", "  ", "more bull"])
    assert out == [0.7, None, 0.7]


def test_batch_score_modelo_no_disponible_lista_de_none():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", side_effect=RuntimeError("no model")):
        out = a.batch_score(["a", "b"])
    assert out == [None, None]


def test_batch_score_todos_vacios_lista_de_none():
    a = SentimentAnalyzer()
    with patch("transformers.pipeline", return_value=_make_pipe()):
        out = a.batch_score(["", "   ", None])
    assert out == [None, None, None]


def test_batch_score_batch_lanza_cae_a_per_item():
    a = SentimentAnalyzer()
    # El pipeline lanza cuando recibe una lista (batch), pero responde OK por item.
    def _call(arg):
        if isinstance(arg, list):
            raise RuntimeError("batch no soportado")
        return [{"label": "positive", "score": 0.55}]
    with patch("transformers.pipeline", return_value=MagicMock(side_effect=_call)):
        out = a.batch_score(["uno", "dos"])
    assert out == [0.55, 0.55]


def test_batch_score_item_ilegible_es_none():
    a = SentimentAnalyzer()
    # El batch devuelve un item None en el medio → _label_to_score lanza → None.
    def _call(arg):
        return [{"label": "positive", "score": 0.8}, None, {"label": "negative", "score": 0.9}]
    with patch("transformers.pipeline", return_value=MagicMock(side_effect=_call)):
        out = a.batch_score(["a", "b", "c"])
    assert out == [0.8, None, -0.9]
