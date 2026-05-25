# Análisis cualitativo del período 1 (28-abr → 23-may 2026)

> **Propósito:** extraer lecciones cualitativas de los datos del 1er período de observación que SÍ se pueden usar — sin pretender hacer ajuste estadístico de parámetros (la data tiene baja calidad por sizing trivial qty=1). Insumo para entender comportamiento del bot pre-martes y para definir qué monitorear con prioridad durante el período de validación post-arranque.

**Mantenedor:** Cowork (Roma).
**Fecha:** 2026-05-25.
**Fuente:** CSVs en `backups/2026-05-24/balance_data/` generados por `run_balance_queries.py` durante el sprint 24-may.
**Caveats:**
- Sharpe per-Sentinel pre-fix B.2 → valores absurdos (93.9, -120.4) descartados del análisis cuantitativo.
- Sizing trivial qty=1 todo el período → distorsiona allocations reales.
- CorrelationGuard NO persistía descartes → q6_1 vacío.
- Período corto (26 días) + sample chico (S-9 con 4 trades).

---

## §1 — Resumen ejecutivo (3 hallazgos accionables)

1. **Pending rate crítico en 4 sentinels** (S-1, S-4, S-5, S-6 con >65% de órdenes que nunca se llenaron). Sus limit prices son demasiado estrictos vs movimiento real del mercado. **Investigar antes de martes** o queremos un patrón sistemático de cancelaciones en período 2.

2. **Concentración masiva en SPY** — 7 de 9 sentinels operan SPY como uno de sus 3 tickers. CorrelationGuard NO se podía verificar en período 1 (sin persistencia), pero en período 2 va a tener trabajo. Threshold 0.75 a validar empíricamente.

3. **S-2 RSI Fast Reversion monopolizó actividad** (188 trades = 55% del total). Los otros 8 sentinels combinados suman 155 trades. **Desbalance fuerte** — algunos sentinels casi no operaron (S-9 con 4 trades). Implica que la mayoría de los componentes del bot quedaron sub-validados.

---

## §2 — Volumen operacional por Sentinel

| Sentinel | Total | Fills | Cancelled | Pending | % Pending | Slippage avg |
|---|---|---|---|---|---|---|
| **S-2 RSI Fast Reversion** | 188 | 130 | 58 | 0 | 0% | +0.0009 |
| S-5 ORB | 38 | 13 | 0 | **25** | **66%** ⚠️ | -0.0034 |
| S-7 VWAP Reversion | 35 | 32 | 3 | 0 | 0% | -0.0584 |
| S-3 Bollinger Bounce | 23 | 17 | 6 | 0 | 0% | -0.0039 |
| S-6 EMA Triple | 19 | 6 | 0 | **13** | **68%** ⚠️ | -0.0263 |
| S-8 RSI Divergence | 15 | 9 | 6 | 0 | 0% | +0.0410 |
| S-1 SMA Crossover | 11 | 1 | 0 | **10** | **91%** ⚠️ | -0.0100 |
| S-4 MACD+Volume | 10 | 2 | 0 | **8** | **80%** ⚠️ | -0.0360 |
| S-9 Bollinger Squeeze | 4 | 4 | 0 | 0 | 0% | +0.0350 |

**Hallazgo crítico: 4 Sentinels con pending rate >65%.** Son los que usan limit orders: S-1 (sma_crossover), S-4 (macd_volume), S-5 (orb_breakout), S-6 (ema_triple). Sus precios límite quedan fuera del rango que el mercado alcanza en los 60s de espera antes de cancelar.

**Implicación:** durante el período 2 con sizing real, estos sentinels van a seguir generando muchas señales que nunca se llenan. Eso significa:
- Capital reservado pero no desplegado.
- Calidad de evaluación per-Sentinel comprometida (10 fills no son suficientes para validar decay).
- Posible parámetro a revisar post-período: cuánto tiempo se espera por el limit, o usar limit prices más laxos.

---

## §3 — Concentración de tickers

| Ticker | Aparece en N Sentinels | Sentinels |
|---|---|---|
| **SPY** | 7 | S-1, S-3, S-5, S-6, S-7, S-8, S-9 |
| **QQQ** | 5 | S-1, S-5, S-7, S-8 (+casi-S-2 via rotaciones) |
| **NVDA** | 4 | S-2, S-4, S-6, S-9 |
| AAPL | 1 | S-5 |
| AMD | 2 | S-4, S-9 |
| GLD | 1 | S-7 |
| IWM | 1 | S-1 |
| MSFT | 1 | S-8 |
| TLT | 1 | S-2 |
| TSLA | 2 | S-4, S-6 |
| XLP | 1 | S-3 |
| XLU | 1 | S-2 |
| XLV | 1 | S-3 |

**Implicación:** si la mayoría de los Sentinels emite señal sobre SPY en un mismo cycle, el CorrelationGuard tiene que reducir mucho el sizing. En período 1 esto no se medía. En período 2 vamos a tener tracking — esperá que el guard sea activo, no decorativo.

**Acción para monitoreo:** durante shakedown post-martes, revisar diariamente `q6_1_correlation_guard_summary.csv` (ahora con persistencia). Si el guard descarta >30% de señales, el threshold 0.75 está MUY estricto. Si <5%, está MUY laxo.

---

## §4 — Performance (Sharpe bugueado, pre-B.2)

| Sentinel | Ticker | Trades | Win Rate | Sharpe (BUGUEADO) |
|---|---|---|---|---|
| S-3 Bollinger | SPY | 2 | 100% | 93.90 |
| S-3 Bollinger | XLP | 4 | 75% | 86.66 |
| S-7 VWAP | GLD | 7 | 86% | 50.00 |
| S-3 Bollinger | XLV | 2 | 50% | 47.63 |
| S-2 RSI | NVDA | 22 | 59% | 24.78 |
| S-7 VWAP | QQQ | 5 | 60% | 18.38 |
| S-2 RSI | XLU | 9 | 67% | -1.40 |
| S-7 VWAP | SPY | 3 | 67% | -19.49 |
| S-2 RSI | TLT | 8 | 38% | -40.44 |
| S-5 ORB | AAPL | 2 | 0% | -82.28 |
| S-5 ORB | QQQ | 3 | 0% | -93.24 |
| S-8 RSI Div | MSFT | 2 | 0% | -120.39 |

**Lecturas válidas pese al bug:**
- **Win rates SÍ son confiables** (cálculo simple, no afectado por bug Sharpe).
- S-5 ORB y S-8 RSI Divergence operaron muy mal: 0% win rate en sus 2-3 trades evaluables. Probable: estrategias no funcionaron en este régimen de mercado, O sample muy chico.
- S-7 VWAP en GLD con 86% win rate y 7 trades: el mejor desempeño aparente del período. Vale la pena monitorear en período 2.
- S-2 RSI en NVDA con 59% win rate y 22 trades: razonable, distribución estadísticamente significativa.

**Post fix B.2** (en período 2 con datos reales), los Sharpe per-trade van a quedar en rango razonable y van a ser comparables entre Sentinels. **Eso es el dato que faltó.**

---

## §5 — Universe Selector y productos exóticos

### Rotaciones del período: 23 totales, TODAS en S-2

- 0 rotaciones preanticipadas (`warning_status`).
- 23 rotaciones urgentes (`decay_confirmed`).
- 0 descartadas por recovery.
- Costo total Claude API: **$0.68** (~$0.03 por call promedio).
- **1 solo Sentinel afectado: S-2.**

**Implicación:** los otros 8 Sentinels nunca rotaron porque NUNCA alcanzaron `WARMUP_TRADES_MINIMUM = 10` con suficiente data para evaluar decay. S-1 con 11 trades llegó al threshold pero solo 1 fill (90% pending), entonces la base estadística era todavía pésima.

### 7 productos exóticos ejecutados (todos en S-2)

| Ticker | Veces propuesto | Tipo | Ejecutada |
|---|---|---|---|
| **SOXS** | 2 | Leveraged inverse semis | ✅ |
| **DBA** | 1 | Agriculture commodity | ✅ |
| **BITI** | 1 | Inverse Bitcoin | ✅ |
| **USO** | 1 | Oil futures (contango) | ✅ |
| **UVXY** | 1 | Leveraged volatility | ✅ |
| **VIXY** | 1 | Volatility | ✅ |
| **SQQQ** | 1 | Leveraged inverse QQQ | ✅ |

**Problema histórico:** S-2 es `rsi_short` (mean reversion). Productos leveraged inverse y volatility ETFs tienen decay diario sostenido — son **incompatibles con mean reversion**. El Universe Selector los propuso porque le pareció lógico (BITI inverso de Bitcoin para "shortear" si RSI sobre-compra), pero el decay del producto domina cualquier oportunidad de mean reversion.

**Fix:** lista negra (`_BLACKLIST` en `universe_selector.py`) implementada en commit `7f089a0`. En período 2 NO van a aparecer estos productos.

**Acción para monitoreo período 2:** verificar que `rotation_decisions` NO tenga ningún ticker de la lista negra. Si aparece, hay bug en el filtro.

---

## §6 — The Ear (filtro macro)

| Métrica | Valor del período |
|---|---|
| Eventos macro totales | 2,724 |
| Circuit breakers activados | 0 |
| Risk score promedio | 0.0265 |
| **Risk score MÁXIMO** | **0.3200** |
| Eventos alto riesgo (≥0.5) | 0 |

**Lectura:**
- **El componente NO fue probado.** El threshold de veto es 0.7 y el máximo observado fue 0.32 — quedó muy lejos.
- **2,724 eventos en 26 días = ~105 eventos por día.** Volumen alto, scoring conservador.
- Mercado fue tranquilo (sin FOMC sorpresa, sin NFP shock, sin geopolítica fuerte).

**Implicaciones:**
1. No sabemos si el threshold 0.7 es correcto en un mercado real. Mantenerlo conservador parece OK pero quedó sin validar.
2. **FinBERT (T-U) viene a cambiar esto** — score nuevo con distribución probable distinta, va a requerir recalibración con data real durante shakedown.
3. **q5_3_titulares_matched.csv está VACÍO** — ningún titular alcanzó risk_score>0.5 individualmente. Es decir, el scoring keyword nunca dió "matches fuertes".

**Acción para monitoreo período 2:** monitorear distribución de risk_score diaria (keyword + FinBERT cuando entre). Si FinBERT post-arranque tampoco supera el threshold en condiciones normales, hay que recalibrar con data real (proceso documentado en `outputs/TAREA_T-U_distilfinbert.md` Sub-6).

---

## §7 — CorrelationGuard (sin data del período 1)

`q6_1_correlation_guard_summary.csv` tiene 0 filas. Razón: la persistencia se implementó en EXP-003 (commit `2bf79ec`) DESPUÉS del cierre del período. Antes el guard operaba en runtime pero no persistía decisiones.

**Esperado en período 2:** con persistencia activa + concentración fuerte en SPY (7/9 sentinels), el guard va a tener trabajo real. Threshold 0.75 a evaluar empíricamente.

---

## §8 — Lecciones para período 2 (acciones concretas pre-martes)

1. **Monitorear daily pending rate** de S-1/S-4/S-5/S-6. Si siguen >50% en período 2, agendar revisión de cómo se calculan los limit prices (post-período, no durante).

2. **Monitorear daily output de CorrelationGuard.** Ahora que persiste, ver cuántas señales pasa/reduce/descarta. Calibración del threshold 0.75 si los números no son razonables.

3. **Verificar lista negra Universe Selector activa.** Ningún ticker leveraged/inverse debería volver a aparecer en `rotation_decisions`. Si aparece, hay regresión.

4. **Monitorear S-2 vs el resto.** Si S-2 sigue siendo 55% de la actividad, hay desbalance estructural. Pero NO se ajusta durante el período — se observa y decide post-cierre.

5. **Monitorear distribución FinBERT score** (post-arranque T-U). Recalibrar threshold de veto con data real durante shakedown.

6. **Monitorear Sharpe per-trade** (post fix B.2). Verificar que ningún Sentinel produce |Sharpe| >5. Si aparece, hay anomalía a investigar.

---

## §9 — Lo que NO se puede sacar de estos datos

Por honestidad metodológica, dejar claro lo que NO sirve este análisis:

- **Ajustar parámetros cuantitativos** (KELLY_FRACTION, MAX_CAPITAL, CORRELATION_THRESHOLD, RSI/Bollinger períodos). Sizing trivial + bugs descartan este uso.
- **Decidir scope de Sentinels** (mantener vs eliminar). Sample chico + bugs invalidan la decisión.
- **Validar performance per-Sentinel**. Sharpe bugueado, no comparable.
- **Calibrar threshold de The Ear**. Nunca actuó.
- **Validar threshold CorrelationGuard**. Cero datos persistidos.

Estos análisis se hacen **post-período 2** con datos de calidad: sizing real (Half-Kelly + ATR), bugs fixeados, tracking completo (slippage, CorrelationGuard, tax lots, etc.).

---

## §10 — Caveats sobre #BUG-002 (17 signals huérfanas del 27-abr)

Pendiente de investigación. El balance no contempló este caso. Si en período 2 vuelve a aparecer (signals que no llegan al dispatcher), agregar logging detallado para identificar el bug.

---

*Análisis cualitativo del período 1 armado por Cowork el 2026-05-25 como insumo pre-arranque del período de validación post-martes. NO sustituye análisis cuantitativo formal — eso se hace post-período 2 con datos de calidad.*
