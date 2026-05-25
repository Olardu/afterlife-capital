"""SentimentAnalyzer — sentiment analysis finance-tuned para The Ear (#FEAT-007).

Wrapper sobre un modelo FinBERT (`ProsusAI/finbert` por defecto) que convierte un
titular en un score de sentimiento en `[-1, 1]`:
  -1  muy bajista (negative con alta confianza)
   0  neutral
  +1  muy alcista (positive con alta confianza)

Diseño:
- **Lazy load**: el modelo NO se carga en `__init__`, sino al primer `score()`
  (evita el costo de importar torch/transformers + descargar pesos en arranque).
- **Defensivo**: si el modelo no carga o la inferencia falla, devuelve `None` y el
  caller (The Ear) cae al keyword matching legacy. NUNCA lanza al caller.
- **Puro**: sin DB ni red propia (la descarga del modelo la maneja transformers).
- Inyectado en The Ear vía DIP (the_ear NO importa este módulo) → testeable sin
  cargar el modelo real.

Nota de modelo (T-U): la spec pedía `yiyanghkust/finbert-tone`, pero ese checkpoint
no carga su cabeza de clasificación en `transformers` 5.x (predice basura). Se usa
`ProsusAI/finbert` (FinBERT estándar, config bien formado). Labels del pipeline:
`positive` / `negative` / `neutral`.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Límite de tokens de la familia BERT. Truncamos a este nº de CARACTERES antes de
# pasar al pipeline (conservador: 1 token ≥ 1 char, así nunca excedemos el límite
# real de tokens y evitamos el costo de tokenizar para medir).
_MAX_CHARS = 512

_DEFAULT_MODEL = "ProsusAI/finbert"


class SentimentAnalyzer:
    """Sentiment finance-tuned con lazy load y fallback a None."""

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        self.model_name = model_name
        self._pipeline = None
        self._load_failed = False

    def _ensure_loaded(self) -> bool:
        """Lazy load del pipeline. True si está disponible, False si no."""
        if self._pipeline is not None:
            return True
        if self._load_failed:
            return False
        try:
            # Import diferido (transformers es pesado) + acceso calificado al
            # atributo en el momento de la llamada — `transformers.pipeline(...)`
            # en vez de `from transformers import pipeline` para que el lazy
            # module de transformers no esquive un mock en los tests.
            import transformers
            self._pipeline = transformers.pipeline(
                "sentiment-analysis", model=self.model_name)
            logger.info(f"SentimentAnalyzer: modelo '{self.model_name}' cargado.")
            return True
        except Exception as e:
            logger.warning(
                f"SentimentAnalyzer: el modelo '{self.model_name}' no carga "
                f"({e}). Fallback a keyword matching."
            )
            self._load_failed = True
            return False

    @staticmethod
    def _label_to_score(result: dict) -> float:
        """Mapea {label, score} del pipeline a un float en [-1, 1].

        positive → +confidence, negative → -confidence, neutral/otro → 0.0.
        """
        label = str(result.get("label", "")).lower()
        confidence = float(result.get("score", 0.0))
        if "positive" in label:
            return confidence
        if "negative" in label:
            return -confidence
        return 0.0

    def score(self, text: str) -> Optional[float]:
        """Sentiment score en [-1, 1] de un titular, o None si no disponible."""
        if not text or not text.strip():
            return None
        if not self._ensure_loaded():
            return None
        try:
            result = self._pipeline(text[:_MAX_CHARS])[0]
            return self._label_to_score(result)
        except Exception as e:
            logger.warning(
                f"SentimentAnalyzer: inferencia falló para '{text[:50]}...': {e}"
            )
            return None

    def batch_score(self, texts: list[str]) -> list[Optional[float]]:
        """Scores de N titulares preservando posición.

        Textos vacíos → None en su posición. Si el modelo no está disponible →
        lista de None. Intenta una pasada batch sobre los textos no vacíos; si esa
        pasada lanza, cae a evaluación per-item (cada uno con su propio manejo de
        error) para no perder los titulares sanos.
        """
        results: list[Optional[float]] = [None] * len(texts)
        if not self._ensure_loaded():
            return results
        valid_idx = [i for i, t in enumerate(texts) if t and t.strip()]
        if not valid_idx:
            return results
        try:
            batch_out = self._pipeline([texts[i][:_MAX_CHARS] for i in valid_idx])
        except Exception as e:
            logger.warning(
                f"SentimentAnalyzer: batch falló ({e}); reintento per-item."
            )
            for i in valid_idx:
                results[i] = self.score(texts[i])
            return results
        for pos, i in enumerate(valid_idx):
            try:
                results[i] = self._label_to_score(batch_out[pos])
            except Exception as e:
                logger.warning(f"SentimentAnalyzer: item batch {i} ilegible ({e}).")
                results[i] = None
        return results
