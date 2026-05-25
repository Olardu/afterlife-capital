# FinBERT Architecture Analysis — The Ear upgrade (#FEAT-007)

> **Mini-investigación preparatoria** para el upgrade futuro de The Ear de keyword matching a sentiment analysis con modelo finance-tuned. Status del item: **AFUERA** del scope activo (Roman decidió no priorizar pre-Fase 5). Este doc queda como base de contexto para cuando se reactive.

**Mantenedor:** Cowork (Roma).
**Fecha:** 2026-05-25.
**Caveat:** análisis técnico-arquitectónico **sin** validación contra los 25 macro_events del período 1 (Cowork no tiene acceso directo a DB). Cuando se reactive #FEAT-007, agregar fase de validación con datos reales antes de elegir opción final.

---

## §1 — Contexto y motivación

**Estado actual de The Ear:**
- Filtro macro vía NewsAPI + keyword matching (palabras: "crisis", "recession", "fed", "rate", "crash", etc.).
- Score derivado: suma ponderada de keywords matched en titulares recientes, normalizado por número de artículos.
- Threshold de veto: `risk_score > 0.7` bloquea trading.
- **Observación período 1:** The Ear nunca actuó (`risk_score` máximo observado = 0.32 en 26 días). No probado en condiciones de stress.

**Problema documentado** (Rec 1 investigación, Kirtac & Germano 2024):
- Keyword matching **confunde contexto histórico con crisis presente**.
- Ejemplo: titular *"In 2008, banks collapsed during the recession"* en un artículo retrospectivo cuenta como señal de riesgo presente.
- Falsos positivos cuando un artículo cubre crisis pasadas.
- Falsos negativos cuando el sentimiento es negativo sin disparar los keywords específicos (lenguaje sofisticado, eufemismos).

**Solución propuesta:** reemplazar (o complementar) keyword matching con **sentiment analysis usando un modelo de lenguaje finance-tuned**. Paper Kirtac & Germano: OPT-based sentiment predijo retornos con 74.4% accuracy vs ~50-55% típico de keyword matching.

---

## §2 — Estado actual de las opciones evaluadas

### Opción A — FinBERT base (HuggingFace transformers + PyTorch)

**Modelo:** `ProsusAI/finbert` u otros forks (yiyanghkust/finbert-tone, ahmedrachid/FinancialBERT). Modelo BERT-base con fine-tuning sobre Financial PhraseBank + corpus financieros.

**Dependencias:**
- `transformers>=4.30`
- `torch>=2.0` (CPU build ~700MB, GPU build varios GB)
- Modelo descargado: ~440MB primera vez (`pytorch_model.bin`)

**Performance esperada:**
- CPU (i5/i7 típico): ~200-500ms por titular (depende length + batch size).
- GPU NVIDIA dedicada: ~10-50ms por titular.
- Accuracy reportada literatura: ~85-87% en Financial PhraseBank.

**Pros:**
- Maduro, ampliamente usado en research.
- Open source, sin costos recurrentes.
- Procesamiento 100% local, sin dependencia de red.
- Soporta batch processing.

**Cons:**
- Footprint pesado (~1.5GB total con deps).
- Latencia CPU significativa para N titulares por cycle.
- Bot Sentinel corre en PC de Roman (no se sabe si tiene GPU NVIDIA).

### Opción B — distilFinBERT (BERT destilado)

**Modelo:** versiones destiladas de FinBERT, ~40% menor en parámetros, ~60% más rápido en inferencia, mantiene ~95-97% de la accuracy del modelo full.

**Ejemplos disponibles:** `yiyanghkust/finbert-tone` (DistilBERT-based), `huawei-noah/TinyBERT_financial` (más extremo, ~10x más rápido pero accuracy menor).

**Dependencias:** mismas que FinBERT base (`transformers` + `torch`), pero modelo descargado ~250MB.

**Performance:**
- CPU: ~80-200ms por titular (60% más rápido que FinBERT base).
- Memoria RAM: ~500MB cargado.

**Pros:**
- Trade-off accuracy/velocidad muy favorable para uso production en CPU.
- Misma API que FinBERT base — código idéntico, solo cambia el `from_pretrained()`.
- Open source, sin costos recurrentes.

**Cons:**
- ~2-5 puntos de accuracy menores que FinBERT base.
- Sigue requiriendo PyTorch (~700MB CPU build).

### Opción C — HuggingFace Inference API (cloud)

**Servicio:** API REST de HuggingFace que aloja modelos pre-entrenados. Plan free incluye rate limit, plan Pro $9/mes para más throughput.

**Endpoint:** `POST https://api-inference.huggingface.co/models/ProsusAI/finbert` con texto en body, retorna `{label, score}`.

**Performance:**
- Latencia red: ~100-300ms por call (USA-EU/JP servers).
- Cold start: primer call de un modelo no-popular puede tardar 10-30s mientras se levanta.
- Rate limit free: ~30 calls/minuto.
- Rate limit Pro: ~1000 calls/hora.

**Pros:**
- Cero instalación local. Cero footprint en disco. Cero RAM consumida en el bot.
- Modelos siempre actualizados.
- Fácil cambiar de modelo (solo cambia URL).

**Cons:**
- Dependencia de red — si HF cae o internet de Roman cae, The Ear queda sin sentiment.
- Costo recurrente si se va a plan Pro.
- Latencia variable + cold starts impredecibles.
- Rate limits pueden ser limitantes en horario macro intenso (FOMC, NFP).
- Privacidad: los titulares se envían a servidores HF (no es secret pero es dependencia externa).

### Opción D — Claude API directo (LLM general)

**Servicio:** llamar a Claude (que ya está integrado en el bot) con un prompt tipo: *"Evalúa el siguiente titular financiero. Responde solo con un score [-1, 1] donde -1=muy bajista, 0=neutral, 1=muy alcista. Titular: '[X]'"*.

**Performance:**
- Latencia: ~500-1500ms por titular (Claude Sonnet 4.6).
- Costo: ~$0.001-0.003 por titular (input + output chico).
- Con N=10-20 titulares por cycle → ~$0.01-0.06 por cycle.
- Mes operativo (~26 días × ~50 cycles/día × ~$0.03) = **~$40-80/mes**.

**Pros:**
- Cero instalación adicional (Claude ya integrado).
- Contexto extenso: Claude puede leer 5-10 titulares de una vez + contexto macro.
- Reasoning explícito (logra explicar por qué un titular es bullish/bearish).
- Multi-idioma sin esfuerzo.

**Cons:**
- Latencia mayor que las otras opciones.
- Costo recurrente significativo ($40-80/mes solo para sentiment).
- Dependencia de Anthropic API (caída = sin sentiment).
- Sobrespecificado para tarea de sentiment scoring (es un LLM general usado para algo que un modelo finance-tuned haría mejor y más barato).

---

## §3 — Tabla comparativa

| Criterio | FinBERT base | distilFinBERT | HF API cloud | Claude directo |
|---|---|---|---|---|
| Accuracy esperada | 85-87% | 82-85% | 85-87% | 75-80% (sin fine-tune) |
| Latencia (CPU) | 200-500ms | 80-200ms | 100-300ms + cold | 500-1500ms |
| Footprint inicial | ~1.5GB | ~1GB | ~0MB | ~0MB |
| RAM operativa | ~1GB | ~500MB | ~0MB | ~0MB |
| Costo mensual | $0 | $0 | $0-$9 | ~$40-80 |
| Dependencia red | NO | NO | SÍ | SÍ |
| Privacidad | Local | Local | Cloud HF | Cloud Anthropic |
| Fallback fácil | A keyword | A keyword | A local model | A keyword |
| Update modelo | Manual | Manual | Automático | N/A |

---

## §4 — Recomendación: **distilFinBERT**

**Razones:**

1. **Trade-off óptimo accuracy/performance** para uso production en PC de Roman (asumiendo sin GPU NVIDIA dedicada). 2-5 puntos de accuracy menor que FinBERT base no justifican 60% más latencia.

2. **Cero costos recurrentes** — alineado con filosofía de Sentinel (capital chico, costos operativos mínimos).

3. **Sin dependencia de red para sentiment** — si HuggingFace cloud o Anthropic API caen, The Ear sigue funcionando con sentiment local. Solo NewsAPI queda como dependencia externa para los titulares (ya existente).

4. **Privacidad y control** — modelo local, sin enviar titulares a servidores externos.

5. **Mismo código que FinBERT base** — si en el futuro Roman tiene GPU dedicada y quiere upgrade a FinBERT base, es cambiar 1 línea (`from_pretrained()`).

6. **Fallback simple a keyword matching** — si el modelo no carga o falla en inferencia, fallback automático a la lógica actual sin interrumpir el bot.

**Cuándo reconsiderar:**
- Si en Fase 5 live el bot opera con $10K+ de capital, los $40-80/mes de Claude API se vuelven despreciables → reconsiderar Claude directo por el reasoning explícito.
- Si Roman migra el bot a server con GPU NVIDIA, considerar FinBERT base por el upgrade de accuracy.
- Si la latencia per-titular se vuelve bottleneck del cycle de 15min, considerar HF API cloud con cache.

---

## §5 — Pre-spec técnica (para Code futuro)

Cuando se reactive #FEAT-007, la implementación sigue este esqueleto:

**1. Nuevas dependencias en `requirements.txt`:**
```
transformers==4.45.0
torch==2.5.0+cpu (CPU build)
```
(Versiones pineadas al momento de implementación, según política #FASE2-NEW-2.)

**2. Nuevo módulo `sentinel-v0.5/sentiment_analyzer.py`** (puro, testeable, sin red):
- `class SentimentAnalyzer` con `__init__(model_name='yiyanghkust/finbert-tone')`.
- Carga lazy del modelo al primer call.
- Método `score(text) -> float` retorna [-1, 1].
- Método `batch_score(texts) -> list[float]` para procesar varios titulares en batch (más eficiente).
- Fallback a `None` si el modelo no carga → caller usa keyword matching.

**3. Modificaciones en `the_ear.py`:**
- Inyectar `SentimentAnalyzer` opcional (DIP).
- En `evaluate()`: si analyzer disponible, usar sentiment scoring; sino keyword matching.
- Nuevo flag `THE_EAR_SENTIMENT_ENABLED` en config (default `false`, se activa cuando se quiere migrar).
- **Hybrid mode:** durante un período (3er observación), correr AMBOS en paralelo y persistir ambos scores. Permite calibración del threshold nuevo + validación que FinBERT mejora vs keyword.

**4. Migración SQL para hybrid:**
- Tabla `macro_events` agregar columnas `sentiment_score_finbert` (NUMERIC) y `sentiment_method` (VARCHAR). Migración nueva (probablemente 018 o más).

**5. Tests TDD:**
- Mock del modelo HF cargado → score determinístico para titular sintético.
- Modelo no carga → fallback a None testeado.
- Hybrid mode → ambos scores persistidos.
- Edge cases: texto vacío, texto en español (FinBERT es inglés-only por defecto), texto muy largo (truncar a 512 tokens).

**6. Recalibración del threshold:**
- Threshold actual `RISK_SCORE_VETO_THRESHOLD = 0.7` calibrado para keyword matching.
- FinBERT devuelve score en [-1, 1] con distribución distinta. Necesita calibración nueva.
- **Estrategia:** durante 3er período (con hybrid mode), recopilar pares `(keyword_score, finbert_score, outcome)`. Encontrar threshold FinBERT que dispara veto en aproximadamente los mismos días que keyword matching los dispararía (asumiendo que la lógica de veto general es correcta, solo cambia el método de scoring).

**7. Documentación:**
- Actualizar `RATIONALE.md` con la nueva sección "The Ear sentiment scoring" + threshold justificado.
- Documentar el fallback a keyword en `INCIDENT_PLAYBOOK.md` (escenario "FinBERT no carga").

---

## §6 — Plan de validación post-implementación

Lo crítico: el upgrade cambia el comportamiento del bot. Si se mergea durante el período 2, los datos del período quedan "antes/después FinBERT" y NO comparables.

**Estrategia recomendada:**

1. **Fase A (durante período 2):** NO mergear FinBERT. Período 2 corre con keyword matching para que los datos sean comparables al período 1.

2. **Fase B (post-cierre período 2):** evaluar si los hallazgos del período 2 justifican el upgrade. Si sí:
   - Implementar T-T (cuando #FEAT-007 se reactive) con hybrid mode activado.
   - Mergear post-cierre.
   - Recalibrar threshold con datos históricos.

3. **Fase C (3er período de observación, ~julio 2026):** correr el bot con hybrid mode (ambos scores persistidos pero solo uno activo para veto). Decidir cuál usar para veto en base a evidencia. Esto es el período de evaluación dedicado de #FEAT-007.

4. **Fase D (post-3er período):** decidir si quitar keyword matching definitivamente o mantenerlo como fallback eterno.

---

## §7 — Caveats de este análisis

1. **Sin validación contra los 25 macro_events del período 1.** Cowork no tiene acceso directo a DB. Cuando se reactive #FEAT-007, agregar fase de validación: tomar los 25 eventos, calcular sentiment con cada opción (FinBERT, distilFinBERT, HF API, Claude), comparar contra una clasificación manual de los 25 (Cowork puede ayudar a clasificar manualmente). Esto confirma cuál opción discrimina mejor entre riesgo real vs falso positivo.

2. **Hardware de Roman no verificado.** Asumí "PC sin GPU dedicada". Si tiene GPU NVIDIA, FinBERT base se vuelve viable y se prefiere por accuracy.

3. **Versiones de modelos pueden cambiar.** Los modelos FinBERT/distilFinBERT en HuggingFace pueden tener updates entre ahora y cuando se implemente. Al momento de implementar, verificar el modelo más actualizado del autor original.

4. **Mercado USA-céntrico.** FinBERT está entrenado principalmente en inglés / mercado USA. Si Sentinel migra a multi-mercado (#multimarket está afuera), reconsiderar modelos específicos por mercado.

---

## §8 — Referencias

**Académicas:**
- Kirtac, K. & Germano, G. (2024). *"Sentiment trading with large language models"*. Finance Research Letters.
- Araci, D. (2019). *"FinBERT: Financial Sentiment Analysis with Pre-trained Language Models"*. arXiv:1908.10063.

**Modelos:**
- `ProsusAI/finbert` (HuggingFace) — BERT base finance-tuned, ampliamente citado.
- `yiyanghkust/finbert-tone` (HuggingFace) — DistilBERT-based, alternativa más liviana, **recomendado**.
- `ahmedrachid/FinancialBERT-Sentiment-Analysis` — alternativa con preprocessing más cuidado.

**Software:**
- `transformers` (HuggingFace) — librería Python para cargar y correr modelos.
- `torch` (PyTorch) — backend.

---

*Half-Kelly Validation Analysis armado por Cowork el 2026-05-25 como research preparatorio para futuro #FEAT-007. NO sustituye validación con data real al momento de implementación. Item #FEAT-007 sigue AFUERA del scope activo — este doc queda como base de contexto.*
