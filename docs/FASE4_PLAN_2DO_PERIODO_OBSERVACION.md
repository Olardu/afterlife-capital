# FASE 4 — Plan del 2º Período de Observación

> **Inicio:** martes 2026-05-26 pre-apertura del mercado.
> **Duración prevista:** 30 días (hasta ~25 de junio).
> **Objetivo:** validar el comportamiento del bot post-fixes del sprint 24-may con sizing real (no qty=1 trivial como en el 1er período).

**Mantenedor:** Cowork (Roma) escribe + actualiza. Roman valida criterio. Code reporta evidencia.

**Archivo regenerado el:** 2026-05-25 (versión anterior perdida).

---

## Contexto

El 1er período de observación (28-abr → 23-may, 26 días reales) cerró anticipadamente con resultado neto +0.094% absoluto. La conclusión del balance: **el período NO probó las protecciones del bot** porque (a) mercado tranquilo, (b) sizing trivial qty=1 todo el período por falta de allocation, (c) The Ear nunca actuó, (d) bugs encontrados retroactivamente (Sharpe, CorrelationGuard no persistente, decay solo por WR+Sharpe).

Sprint del 24-may corrigió 3 bugs / agregó 1 lógica nueva:
- BUG-001 Sharpe sin anualizar (B.2) — `67164a5`
- EXP-003 CorrelationGuard persistencia — `2bf79ec`
- EXP-002 PF+RTD en decay (Opción C) — `de4f029`
- EXP-005 Modo Observador Fractional — en curso, T-K

El 2º período sirve para evaluar empíricamente si esos cambios funcionan en producción + capturar la evidencia del costo de operar sin fractional.

---

## Hipótesis del período

1. **Half-Kelly con Sharpe corregido (B.2) produce allocations balanceadas.** En el 1er período, el Sharpe bugueado concentraba 64% de la torta en S-3 Bollinger (8 trades). Post-fix, las allocations se distribuyen de forma más coherente con la calidad real de cada Sentinel.

2. **CorrelationGuard reduce/descarta señales con frecuencia detectable.** En el 1er período no había forma de medir. Ahora con persistencia, esperamos ≥10% de señales con alguna acción del guard (reducidas o descartadas).

3. **Decay con PF+RTD identifica Sentinels rentables que el viejo criterio mataba.** Y mata Sentinels que el viejo criterio rescataba indebidamente. Las 23 rotaciones del 1er período fueron TODAS por `decay_confirmed` con el criterio viejo — esperamos ver diferencias.

4. **El bot opera estable con sizing real.** Sin crashes, sin posiciones huérfanas, sin desincronizaciones cache vs Alpaca durante todo el período. Bracket orders server-side cuidan las posiciones cuando hay caídas técnicas del bot.

5. **The Ear actúa al menos 1 vez** en el período si hay catalizadores macro (FOMC junio típicamente, CPI, NFP, earnings season). Esperamos ver al menos un veto real para tener evidencia de cómo se comporta el bot ante un evento.

---

## Configuración del período (flags y parámetros)

**Flags activados (vía `.env` + restart `api.py`):**

```
DAILY_REPORT_ENABLED=true
ATR_SIZING_ENABLED=true
PORTFOLIO_DD_LIMITS_ENABLED=true
SHADOW_FRACTIONAL_ENABLED=true   # nuevo, EXP-005
```

**Parámetros congelados (NO se tocan durante el período, lección AQR/Knight):**

| Parámetro | Valor | Cambio vs período 1 |
|---|---|---|
| KELLY_FRACTION | 0.5 | sin cambio |
| MAX_CAPITAL_PER_SENTINEL | 25.0% | sin cambio |
| MIN_CAPITAL_PER_SENTINEL | 5.0% | sin cambio |
| CORRELATION_THRESHOLD | 0.75 | sin cambio |
| SHARPE_MINIMUM | 0.05 | recalibrado per B.2 (era 0.5) |
| PROFIT_FACTOR_MINIMUM | 1.3 | nuevo |
| RTD_MINIMUM | 1.0 | nuevo |
| WARMUP_TRADES_MINIMUM | 10 | sin cambio |
| RISK_SCORE_VETO_THRESHOLD | 0.7 | sin cambio |
| PARKING_BRAKE_TIME | 15:45 ET | sin cambio |

**Lo que está PERMITIDO modificar durante el período** (igual al 1er período, ver `OBSERVATION_PERIOD.md`):
- Bug fixes críticos (bot crashea, pierde plata, datos corruptos, seguridad).
- Documentación.
- Observabilidad read-only (queries SQL, exports, dashboards sin lógica).

**Lo que está PROHIBIDO modificar:**
- Cualquier threshold de la tabla de arriba.
- Lógica de Sentinels, Universe Selector, The Ear, CorrelationGuard, Historian.
- Path de ejecución (`dispatcher.execute_order`, `_submit_order_sync`).
- Comportamiento del bot que cambie cómo se generan/persisten datos.

**Si surge necesidad de cambio durante el período** → registrarlo como excepción documentada en LOG con justificación + marca temporal exacta, para que el análisis post-período pueda dividir los datos en sub-períodos.

---

## Métricas a observar

### Mensual / al cierre del período

- **Equity curve diaria:** persistida en `daily_equity_snapshots` (tabla cableada en #GR-3).
- **Sharpe del portfolio:** anualizado vs SPY benchmark (via QuantStats).
- **Sortino, Max DD, Volatility, Win rate, Profit factor:** mismas métricas que el balance del 1er período para comparación directa.
- **Drawdown maxes:** intra-día y sobre la curva acumulada.

### Por Sentinel

- **Sharpe per-trade (con B.2):** verificar que queda en rango [-3, +3]. Si algún Sentinel produce |Sharpe| > 5 → revisar EXP-001.
- **PF y RTD persistidos:** validar que los criterios de decay funcionan en producción (EXP-002).
- **Allocations dinámicas:** ¿cómo se distribuyen entre los 9? ¿algún Sentinel monopoliza?
- **Trades por Sentinel:** comparar volumen vs período 1 (S-2 Mantis tuvo 188 trades, ¿se mantiene?).
- **Tickers operados:** Universe Selector ¿rotó? ¿qué nuevos tickers introdujo?

### CorrelationGuard (EXP-003)

- **% señales evaluadas con guard:** debería ser >0% (en período 1 era 0 porque no se persistía).
- **Distribución por status:** intacta / reducida_leve / reducida_media / reducida_fuerte / descartada.
- **Correlación promedio:** ¿es estable? ¿hay días con correlación generalizada alta?
- **Tickers más "reducidos":** ¿cuáles son los que más activan el guard?

### Shadow Fractional (EXP-005)

- **Total registros en `signals_shadow_fractional`:** target ≥100.
- **Distribución por status:** `matched` / `fractional_would_increase` / `signal_lost_to_int_floor` / `other`.
- **Suma `dollar_diff` agregado:** cuántos dólares no se desplegaron por el floor a int.
- **% por ticker:** ¿qué tickers son los más afectados? (esperado: tickers caros — NVDA, MSFT, GOOG, MGM si los hay).
- **% por Sentinel:** ¿qué Sentinels sufren más el problema?
- **Decisión post-período:** con esta evidencia, prioridad real de #FEAT-001 (fractional con mitigaciones).

### The Ear

- **# eventos macro registrados:** durante el período.
- **# vetos disparados:** durante el período (esperado: al menos 1).
- **Falsos positivos identificados:** titulares irrelevantes que pasaron el filtro.
- **Falsos negativos:** eventos reales que el bot operó como si no existieran.

### Health del sistema

- **# crashes / restarts:** debería ser 0.
- **# incidentes git/index:** debería ser 0 (post-Defender exclusion del 24-may).
- **# alertas del heartbeat externo:** N/A todavía (#FEAT-004 pendiente).
- **Latencia del cycle:** tiempo promedio de procesar todas las señales del cycle.

---

## Criterios GO / NO-GO al cierre del período

**GO (avanzar a Fase 5 live):**
- Equity preservada (PnL ≥ -2% del capital paper inicial).
- 0 crashes / restarts no planificados.
- Métricas Sharpe/Sortino/PF razonables (Sharpe portfolio > 0.5 anualizado, PF > 1.2, Max DD < 5%).
- CorrelationGuard funcionando (≥10% señales con alguna acción del guard).
- Decay PF+RTD identifica al menos 1 rotación distinta del criterio viejo (validación EXP-002).
- Shadow Fractional con evidencia suficiente para decidir #FEAT-001.

**NO-GO (extender período / iterar antes de Fase 5):**
- PnL < -2% (necesita análisis de causa raíz).
- 1+ crash sin causa identificada y resuelta.
- Métricas inconsistentes con la hipótesis (ej: Sharpe negativo, Max DD > 10%).
- The Ear veto durante días enteros sin evento macro real (falso positivo).
- Universe Selector recomienda exóticos no en blacklist (ya identificados 7 en período 1).

---

## Riesgos identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Evento macro fuerte (FOMC, CPI sorpresa) | Alta | Medio | The Ear + bracket SL/TP server-side. Si flash crash: bracket protege. |
| Bug en lógica nueva post-fix (B.2 / Opción C) | Media | Medio | Detección automática vía suite 99/99 + cross-check semanal del balance. |
| Posición huérfana por desincronización cache/Alpaca | Media | Alto | #H-5/#H-6b cubren, pero monitorear. Reconciliación manual si necesario. |
| Caída de Cloudflare (dashboard inaccesible) | Baja | Bajo | Bot sigue operando local. Acceder por localhost. |
| Caída de Alpaca con posiciones abiertas | Baja | Bajo | Bracket SL/TP server-side siguen activos durante el outage. |
| `.git/index.lock` recurrente | Muy baja | Bajo | Defender exclusion aplicada. `clean-git-locks.ps1` como recovery. |
| Bot en loop infinito por bug | Baja | Alto | Stop-Process + investigar logs. Healthchecks externo cuando #FEAT-004. |
| Shadow Fractional rompe flow ejecutable | Muy baja | Alto | try/except amplio en el código del shadow. Flag SHADOW_FRACTIONAL_ENABLED para apagar rápido. |

---

## Cadencia de revisión durante el período

**Diaria (automática):**
- Daily report email a viewers (`DAILY_REPORT_ENABLED=true`).
- Snapshot equity en `daily_equity_snapshots`.

**Semanal (Roman + Cowork):**
- Revisar 5-10 entries del LOG de la semana, identificar patrones inusuales.
- Spot-check de queries de balance §3-§6 sobre data parcial.
- Verificar tabla `signals_shadow_fractional` esté llenándose.

**Al cierre del período (~25 junio):**
- Balance completo análogo al del 1er período.
- Análisis de cada experimento (EXP-001 a EXP-005) con criterios pre-registrados.
- Decisión GO / NO-GO documentada.
- Si GO: arrancar Fase 5 con plan de live conservador.
- Si NO-GO: identificar causas + iterar + 3er período.

---

## Pendientes operacionales antes del martes 26-may

- [x] Defender exclusion del repo (Roman, 24-may).
- [ ] UPDATE rename S-2 en pgAdmin (`#OPS-002`).
- [ ] Code completa T-K (EXP-005) + Cowork valida + push (`#EXP-005`).
- [ ] Migración 015 aplicada a DB local (autorización Roman, patrón 011/013/014).
- [ ] Restart `api.py` pre-apertura con 4 flags (`#OPS-001`).
- [ ] Email a viewers reapertura (`#OPS-003`).

---

*FASE4_PLAN regenerado por Cowork el 2026-05-25. Reemplaza versión perdida. Cuando arranque el período, este archivo se mueve a `sentinel-v0.5/docs/` o equivalente y se referencia desde `OBSERVATION_PERIOD.md`.*
