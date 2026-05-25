# Plan de recalibración del umbral FinBERT — The Ear (#FEAT-007 / T-U)

> Cómo calibrar `THE_EAR_FINBERT_VETO_THRESHOLD` con data real una vez que el bot
> opera con FinBERT activo. Hasta calibrar, el bot corre en **hybrid mode**: el
> keyword matching sigue decidiendo el `risk_score`, FinBERT observa y agrega un
> veto extra conservador.

**Autor:** Claude Code. **Fecha:** 2026-05-25.

---

## Cómo funciona hoy (v1, hybrid mode)

- **Flag:** `THE_EAR_SENTIMENT_ENABLED` (default `false`). Roman lo activa en `.env`
  + restart de `main.py`.
- **Modelo:** `ProsusAI/finbert` (CPU, lazy load). Si no carga → fallback a keyword,
  sin romper el bot.
- **Qué decide qué:**
  - `risk_score` ∈ [0,1] lo da el **keyword matching** (sin cambios). Mantiene
    intacta la semántica que consumen el decay, el dashboard y el veto
    `risk_score > RISK_SCORE_VETO_THRESHOLD` (0.7).
  - FinBERT calcula el **sentiment promedio** ∈ [-1,1] de los titulares y agrega un
    **veto extra**: si `finbert_score < THE_EAR_FINBERT_VETO_THRESHOLD` (default
    **-0.6**) → `can_trade = False`.
- **Persistencia (hybrid):** cada `macro_event` guarda `risk_score` (keyword),
  `sentiment_score_finbert` (siempre que el modelo dé score) y `sentiment_method`
  (`keyword` | `hybrid`). Esto permite comparar ambos métodos sobre la misma data.

> **Por qué hybrid y no FinBERT puro de entrada:** el umbral correcto se desconoce
> hasta ver la distribución real de scores sobre el flujo de noticias del bot.
> Darle a FinBERT el control del `risk_score` antes de calibrar arriesga vetar de
> más o de menos. El valor `finbert` de `sentiment_method` queda reservado para esa
> fase futura (FinBERT como fuente primaria), post-calibración.

---

## Calendario de recalibración

| Días | Acción |
|---|---|
| **1-3** post-arranque | Persistir ambos scores (hybrid). **NO** ajustar el umbral. Observar la distribución de `sentiment_score_finbert`. |
| **Día 4** | Analizar la distribución observada. Calibrar `THE_EAR_FINBERT_VETO_THRESHOLD` para que el veto FinBERT dispare en una proporción razonable de ciclos: **>1% y <5%**. (Un umbral que veta el 0% es inútil; uno que veta el 30% paraliza el bot.) |
| **Día 7** | Revisar correspondencia entre los vetos FinBERT y el movimiento real del mercado ese día (¿el veto anticipó caídas reales o fueron falsos positivos?). |
| **Días 10-30** | El bot opera con el umbral calibrado. Si la correspondencia se sostiene, se mantiene. |

### Consulta para observar la distribución (días 1-3)

```sql
-- Distribución del score FinBERT desde que se activó hybrid mode.
SELECT
    count(*)                                   AS eventos,
    count(sentiment_score_finbert)             AS con_finbert,
    round(avg(sentiment_score_finbert), 4)     AS media,
    round(min(sentiment_score_finbert), 4)     AS minimo,
    round(percentile_cont(0.05) WITHIN GROUP (ORDER BY sentiment_score_finbert), 4) AS p05,
    round(percentile_cont(0.25) WITHIN GROUP (ORDER BY sentiment_score_finbert), 4) AS p25,
    round(percentile_cont(0.50) WITHIN GROUP (ORDER BY sentiment_score_finbert), 4) AS mediana
FROM macro_events
WHERE sentiment_method = 'hybrid'
  AND created_at >= NOW() - INTERVAL '3 days';
```

El percentil p05 es un buen punto de partida para el umbral: vetaría ~5% de los
ciclos más bajistas. Ajustar dentro de la banda 1-5% según lo observado.

```sql
-- ¿Cuántos ciclos habría vetado un umbral candidato (ej. -0.6)?
SELECT
    count(*) FILTER (WHERE sentiment_score_finbert < -0.6) AS vetados,
    count(*)                                                AS total,
    round(100.0 * count(*) FILTER (WHERE sentiment_score_finbert < -0.6) / count(*), 2) AS pct_vetado
FROM macro_events
WHERE sentiment_method = 'hybrid'
  AND sentiment_score_finbert IS NOT NULL;
```

---

## Cómo ajustar el umbral

1. Editar `.env`: `THE_EAR_FINBERT_VETO_THRESHOLD=-0.55` (o el valor calibrado).
2. Restart de `main.py`. No requiere migración ni cambio de código.

## Notas / caveats del modelo

- `ProsusAI/finbert` tiene sesgos conocidos: titulares con "Fed", "jobs report" o
  "rate" tienden a `negative` aunque el contexto sea alcista (los lee como riesgo
  de inflación/hawkish). Por eso el umbral inicial es conservador (-0.6) y la
  decisión primaria sigue en el keyword durante la calibración.
- El score es el **promedio** de los titulares del ciclo; pocos titulares muy
  bajistas pueden mover el promedio. Considerar, en una iteración futura, ponderar
  por confianza o usar la mediana si el promedio resulta ruidoso.
- Drift de versiones respecto a la spec original (forzado por Python 3.14):
  `torch 2.9.1+cpu` / `transformers 5.9.0` / modelo `ProsusAI/finbert` (en lugar de
  `yiyanghkust/finbert-tone`, que no carga su clasificador en transformers 5.x).
