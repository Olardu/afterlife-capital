# TAREA T-U — distilFinBERT integration al The Ear (#FEAT-007)

> **Bloque grande PRIORITARIO** — implementación de sentiment analysis finance-tuned reemplazando keyword matching del The Ear. **DEADLINE: martes 26-may pre-apertura** (bot del martes debe arrancar con FinBERT activo). Roman lo decidió 2026-05-25.

**Origen:** decisión Roman 2026-05-25 noche basada en research preparatorio `docs/finbert_arquitectura_analysis.md`. Item #FEAT-007 sale de AFUERA y pasa a ACTIVO P0 urgente.

**Modelo elegido:** distilFinBERT (`yiyanghkust/finbert-tone`) — versión destilada, 60% más rápida que FinBERT base, ~95% de accuracy, footprint ~1GB, sin costos recurrentes, sin dependencia de red para sentiment.

---

## Contexto + razón del cambio

The Ear hoy usa **keyword matching** sobre titulares (palabras: "crisis", "recession", "fed"). Problemas documentados:
1. Confunde contexto histórico con crisis presente (titular sobre 2008 cuenta como señal actual).
2. Falsos positivos / falsos negativos por sofisticación de lenguaje.
3. Score depende del número de artículos (1 keyword en 1 artículo = 1.0; en 20 artículos = 0.05).
4. Período 1: The Ear nunca actuó (`risk_score` max = 0.32 < 0.5 threshold) → componente NO probado en stress.

FinBERT/distilFinBERT entrenado en Financial PhraseBank + corpus financieros → entiende contexto y emite sentiment score `[-1, 1]` por titular. Paper Kirtac & Germano (2024): 74.4% accuracy prediciendo retornos vs ~50-55% típico keyword matching.

---

## Aplicación obligatoria §14.0 v2.7

- Edit quirúrgico (the_ear.py >1000 LOC).
- Checklist post-edit por sub-commit.
- §14.0.7 cierre = cierre por sub-commit.
- Verificación de estado real ANTES de listar items (lección consolidada × 14+).
- Commits LOCALES sin push hasta orden Roman.
- Clean-git-locks autónomo.
- Drift adaptable.
- Decisiones técnicas en tu scope dentro de cada sub-objetivo.
- Suite 489+ verde por commit, validate-workspace 0/0, CI local verde.

**Autorización Roman explícita:** migración SQL próxima libre (probablemente 018 si #HE-2 toma la 017 en T-T). Mismo patrón 011/013/014/015/016/017.

---

## Sub-0 — Audit estado actual

Verificá con grep/Read antes de tocar nada:
- ¿Existe módulo `sentiment_analyzer.py`? (no debería).
- ¿`transformers` o `torch` en `requirements.txt` actual? (no debería).
- ¿Columnas `sentiment_score_finbert` / `sentiment_method` en `macro_events` schema? (no).
- ¿`THE_EAR_SENTIMENT_ENABLED` flag en `config.py`? (no).

Reportá hallazgos en commit message del Sub-1. Drifts esperados: bajos (es greenfield).

---

## Sub-1 — Dependencies + descarga modelo

**Cambios:**
- Agregar a `sentinel-v0.5/requirements.txt`:
  ```
  transformers==4.45.0
  torch==2.5.0+cpu --extra-index-url https://download.pytorch.org/whl/cpu
  ```
  (Versiones pineadas conforme política #FASE2-NEW-2; CPU build de PyTorch obligatorio — la GPU build pesa 5x y no la necesitamos).
- Instalar en venv: `pip install -r requirements.txt`.
- **Pre-descarga del modelo** para evitar latencia en el primer call: ejecutar 1 vez `python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='yiyanghkust/finbert-tone')"`. Esto baja el modelo a `~/.cache/huggingface/` (~250MB) y queda cacheado.
- Documentar en `README.md` (o `CONTRIBUTING.md`) los pasos para que Roman replique en su entorno.

**Aceptación:** `python -c "import torch; import transformers; print(torch.__version__, transformers.__version__)"` exit 0.

**Commit:** `chore(deps): transformers + torch CPU para distilFinBERT (#FEAT-007 prep)`.

---

## Sub-2 — Módulo `sentiment_analyzer.py` puro

**Diseño:**

```python
# sentinel-v0.5/sentiment_analyzer.py
from typing import Optional

class SentimentAnalyzer:
    """
    Wrapper finance-tuned para sentiment analysis. Lazy load del modelo
    al primer call. Devuelve score en [-1, 1]: -1 muy bajista, 0 neutral,
    +1 muy alcista. Si el modelo no carga, retorna None y caller usa fallback.
    """
    def __init__(self, model_name: str = "yiyanghkust/finbert-tone"):
        self.model_name = model_name
        self._pipeline = None
        self._load_failed = False

    def _ensure_loaded(self) -> bool:
        """Lazy load. Retorna True si el modelo está disponible, False sino."""
        if self._pipeline is not None:
            return True
        if self._load_failed:
            return False
        try:
            from transformers import pipeline
            self._pipeline = pipeline("sentiment-analysis", model=self.model_name)
            return True
        except Exception as e:
            logger.warning(f"FinBERT no carga ({e}). Fallback a None.")
            self._load_failed = True
            return False

    def score(self, text: str) -> Optional[float]:
        """Sentiment score [-1, 1] o None si modelo no disponible."""
        if not text or not text.strip():
            return None
        if not self._ensure_loaded():
            return None
        try:
            result = self._pipeline(text[:512])[0]  # truncate a 512 tokens
            label = result["label"].lower()
            confidence = result["score"]
            # yiyanghkust/finbert-tone: 'positive' / 'neutral' / 'negative'
            if "positive" in label:
                return float(confidence)
            elif "negative" in label:
                return -float(confidence)
            else:
                return 0.0
        except Exception as e:
            logger.warning(f"FinBERT inferencia falló para '{text[:50]}...': {e}")
            return None

    def batch_score(self, texts: list[str]) -> list[Optional[float]]:
        """Versión batch (más eficiente para N titulares)."""
        # Implementar con _pipeline en modo batch.
        # Mismo manejo de errores per-item.
        ...
```

**Restricciones:**
- Función pura, sin DB ni red (a salvedad de la descarga inicial del modelo, manejada por transformers).
- Lazy load: NO cargar el modelo en `__init__` (lo carga al primer `score()`).
- Truncate texto a 512 tokens (límite de BERT-family).
- Manejo defensivo: si modelo no disponible, return None — caller decide fallback.

**Tests TDD** `sentinel-v0.5/tests/test_sentiment_analyzer.py` (8-10 casos):
- Mock transformers.pipeline → score determinístico.
- Modelo no carga (ImportError o falla) → score retorna None, no crashea.
- Texto vacío → None.
- Texto muy largo → truncate a 512 sin error.
- Texto en español → manejado (probablemente score neutral o None — verificar comportamiento del modelo).
- batch_score con N=5 textos.
- batch_score con texto problemático en el medio → ese retorna None pero los otros OK.

**Suite esperada:** suite actual + 8-10 = ~499/499.

**Commit:** `feat(sentiment): #FEAT-007 modulo SentimentAnalyzer distilFinBERT puro + tests TDD`.

---

## Sub-3 — Migración SQL (018 o próxima libre)

**Archivo:** `sentinel-v0.5/db/018_add_sentiment_columns_to_macro_events.sql` (verificar próxima libre, podría ser 019 si T-T usó la 017 + 018 para #HE-2).

```sql
BEGIN;

ALTER TABLE macro_events
    ADD COLUMN IF NOT EXISTS sentiment_score_finbert NUMERIC(6,4),  -- [-1, 1]
    ADD COLUMN IF NOT EXISTS sentiment_method        VARCHAR(20);   -- 'keyword' | 'finbert' | 'hybrid'

COMMENT ON COLUMN macro_events.sentiment_score_finbert IS
    'Sentiment score [-1,1] del modelo distilFinBERT sobre el titular. NULL si el modelo no estaba disponible.';
COMMENT ON COLUMN macro_events.sentiment_method IS
    'Cuál método se usó para el risk_score que disparó la decisión: keyword (legacy) | finbert (FinBERT activo) | hybrid (ambos persistidos).';

COMMIT;
```

**Aplicación:** psql con `ON_ERROR_STOP=1`, reportá output literal en LOG (BEGIN/ALTER/COMMENT/COMMIT).

---

## Sub-4 — Integración a `the_ear.py` con DIP + flag + hybrid mode

**Cambios:**

1. `the_ear.py.__init__`: aceptar `sentiment_analyzer: Optional[SentimentAnalyzer] = None` como parámetro (inyección de dependencia, §3.5 manual).
2. Nuevo flag en `config.py`:
   ```python
   THE_EAR_SENTIMENT_ENABLED = os.environ.get("THE_EAR_SENTIMENT_ENABLED", "false").lower() == "true"
   ```
   Default `false` para arranque seguro. Roman lo activa en `.env` cuando esté listo.
3. En `_calculate_risk_score` (o equivalente que calcule el score actual):
   - Si `sentiment_analyzer is not None` y `config.THE_EAR_SENTIMENT_ENABLED`:
     - Calcular `keyword_score` con la lógica actual (no eliminar — mantener para hybrid).
     - Calcular `finbert_score = batch_score(titulares_matched)` y agregar (promedio negativo = bearish, etc.).
     - **Decidir cuál usar como `risk_score` final**: si FinBERT score promedio < -0.6 → veto (threshold a calibrar en post-implementación). Mientras tanto, usar threshold conservador.
   - Sino: `risk_score = keyword_score` (comportamiento actual).
4. **Hybrid mode persistente**: en `record_macro_event` (o equivalente), persistir **ambos** scores:
   - `risk_score` (el que efectivamente se usó para decidir).
   - `sentiment_score_finbert` (siempre, si analyzer disponible — aunque no se use para decidir).
   - `sentiment_method` ('keyword' / 'finbert' / 'hybrid').
5. **Fallback automático**: si analyzer retorna None para algún titular, ese titular se evalúa con keyword score. Si analyzer no disponible (carga falló), `sentiment_method` queda en 'keyword' para todo.

**Importante:** la decisión de cuál threshold usar para FinBERT es a calibrar **durante los primeros días del bot operando** (Roman ajustará en runtime). Para arrancar:
- Threshold inicial sugerido: **`finbert_score promedio < -0.6` dispara veto** (conservador).
- Roman puede ajustar via env var `THE_EAR_FINBERT_VETO_THRESHOLD` (agregalo también a config).

**Tests TDD** `tests/test_the_ear.py` (extender, +5-8 casos):
- `sentiment_analyzer=None` → comportamiento legacy keyword matching.
- Analyzer presente + flag OFF → comportamiento legacy.
- Analyzer presente + flag ON + scores negativos → veto.
- Analyzer presente + flag ON + scores positivos → no veto.
- Hybrid mode persiste ambos scores en macro_events.
- Edge case: analyzer retorna None para algunos titulares → fallback a keyword para ESOS.
- Verificar `sentiment_method` correcto en cada caso.

**Suite esperada:** suite actual + 5-8 = ~505/505.

**Commit:** `feat(the_ear): #FEAT-007 integración distilFinBERT con DIP + hybrid mode + flag + recalibración threshold`.

---

## Sub-5 — Wire-up en `main.py`

**Cambios:**
- En main.py donde se construye `the_ear`, pasar el analyzer:
  ```python
  if config.THE_EAR_SENTIMENT_ENABLED:
      from sentiment_analyzer import SentimentAnalyzer
      analyzer = SentimentAnalyzer()
  else:
      analyzer = None
  the_ear = TheEar(..., sentiment_analyzer=analyzer)
  ```
- Documentar en log al startup si analyzer cargó OK o no (visible en `/api/status`).

**Tests TDD:** 2-3 casos (flag ON con analyzer disponible, flag ON con analyzer falló, flag OFF).

**Commit:** `feat(main): wire-up SentimentAnalyzer al TheEar con flag-gating`.

---

## Sub-6 — Documentación + plan recalibración

**Cambios:**
1. Actualizar `docs/RATIONALE.md` con nueva sección "The Ear sentiment scoring (post-FinBERT)" — explicar threshold inicial y proceso de recalibración.
2. Actualizar `docs/INCIDENT_PLAYBOOK.md` con escenario "FinBERT modelo no carga" → automáticamente fallback a keyword.
3. **Doc nuevo `docs/finbert_recalibration_plan.md`** con plan concreto:
   - Días 1-3 post-arranque: persistir ambos scores en hybrid mode. NO ajustar threshold todavía. Observar distribución de scores FinBERT.
   - Día 4: análisis de la distribución observada → calibrar `THE_EAR_FINBERT_VETO_THRESHOLD` para que dispare veto en proporción razonable (no >5% de cycles ni <1%).
   - Día 7: revisar correspondencia veto FinBERT vs movimiento real del mercado ese día.
   - Días 10-30: bot opera con threshold calibrado. Si funciona, se mantiene.

**Commit:** `docs(finbert): rationale + incident playbook + plan recalibración threshold`.

---

## Restricciones globales T-U

- **Suite verde** antes de cada commit (489 → 505+ esperado).
- **Validate-workspace 0/0** por commit.
- **CI local verde** (test + lint + coverage).
- **Cero borrado de lógica existente** del keyword matching — mantener como fallback eterno + para hybrid mode.
- **DIP estricto:** the_ear NO importa SentimentAnalyzer directamente, lo recibe inyectado. Permite mockear sin cargar el modelo en tests.
- **NO crashear si el modelo no carga** — fallback automático a keyword + log warning.
- **Drift adaptable:** si algún ítem del schema ya existe o algún archivo ya está parcialmente preparado, ajustá scope.
- **Si tokens se acaban:** reportá parcial — sub-commits granulares permiten cortar limpio.

## Reporte final T-U

`[CODE DONE T-U]` con:
1. Lista commits con hashes (esperado 5-6).
2. `git status --short` literal.
3. Output `validate-workspace.ps1`.
4. Output `pytest tests/ -q` final.
5. Output literal psql de la migración aplicada + verificación information_schema.
6. Confirmación: `python -c "from sentiment_analyzer import SentimentAnalyzer; a=SentimentAnalyzer(); print(a.score('Stocks rallied as Fed signals dovish pivot'))"` → score positivo razonable.
7. Cobertura del módulo nuevo `sentiment_analyzer.py` (esperado ≥95%).
8. Cualquier drift detectado.
9. Pendientes Roman manual (activar `THE_EAR_SENTIMENT_ENABLED=true` en .env + restart bot martes).

---

## Después de T-U

- Cowork valida + Roman decide push del bundle (T-T + T-U + lo que haya).
- **Martes 26-may pre-apertura:** Roman activa `THE_EAR_SENTIMENT_ENABLED=true` en `.env` + restart `api.py` con los flags + `main.py` con heartbeat.
- **Días 1-3 post-arranque:** persistir ambos scores en hybrid mode. Roman + Cowork observan distribución.
- **Día 4-7:** recalibrar threshold con data real (proceso documentado en `finbert_recalibration_plan.md`).
- **Cuando estable + threshold calibrado:** período de observación formal arranca.

---

*TAREA T-U pre-armada por Cowork 2026-05-25 noche. Basada en research preparatorio `docs/finbert_arquitectura_analysis.md`. Code arranca apenas termine T-T. DEADLINE: martes 26-may pre-apertura.*
