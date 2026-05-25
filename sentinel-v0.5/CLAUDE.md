# Sentinel v0.5

Sistema de trading algorítmico multi-agente. 9 estrategias autónomas (Sentinels) coordinadas por un Dispatcher, con protecciones macro, gestión de capital Half-Kelly y persistencia en PostgreSQL. Operación en paper trading hasta validar.

## Estado al 2026-05-24 — T-P EN CURSO (6/9 módulos a 100%). 19 commits LOCALES, `origin/main`=`0242eb2`, HEAD `fbb6d64`, suite 278/278

**T-P (cobertura ≥95% módulos críticos) — parcial.** Modelo NO-push vigente. Cobertura por módulo:
- ✅ **market_clock 0%→100%** (`76db0e0`, 18 tests) · ✅ **claude_client 18%→100%** (`4949540`, 15) · ✅ **the_ear 29%→100%** (`84f97e5`, 25).
- ✅ **main.py 16%→100%** (`d680084`, 47 tests, `test_main_coverage.py`) · ✅ **correlation_guard 44%→100%** (`e850432`, 16, `test_correlation_guard_coverage.py`) · ✅ **universe_selector 43%→100%** (`fbb6d64`, 45, `test_universe_selector_coverage.py`).
- ⏳ Pendientes (orden post-reinicio decidido con Roman): **(1) historian (27%, 712 stmts — el más grande, mock asyncpg) PRIMERO con budget fresco → (2) dispatcher (44%, 498 stmts, mock Alpaca) → (3) gate CI `--cov-fail-under=95` AL FINAL** (recién con historian+dispatcher ≥95%) + actualizar `docs/coverage_audit_2026-05-25.md`.
- Patrón: bloques `if __name__=="__main__"` ejecutables → `# pragma: no cover`. Loops infinitos: `asyncio.sleep` mockeado con centinela. Suite 115→278.

## Estado al 2026-05-24 — T-O COMPLETA. 11 commits LOCALES (modelo NO-push), `origin/main`=`0242eb2`, suite 115/115

Sesión T-K→T-O con Cowork. **Modelo desde LOG 04:45: commits LOCALES, sin push** hasta un bundle ordenado por Roman. 10 commits locales sobre `origin/main`=`0242eb2` (HEAD `ce3480d`).

- **T-K EXP-005 Modo Observador Fractional** (`09dd71b`+`ad33843`): tabla `signals_shadow_fractional` (**migración 015 aplicada a DB**), flag `SHADOW_FRACTIONAL_ENABLED` (default ON), bloque shadow al final de `process_signal` (calcula qué operaría fractional vs `floor()` real, INSERT aislado, NO afecta la ejecución), `historian.record_shadow_fractional`. T-J (fractional real) ARCHIVADO: Alpaca no acepta notional+bracket.
- **T-L**: marcadores § + índice interno en `main.py`, `sentinels/__init__.py`, `universe_selector.py` (los otros 4 archivos >500 LOC ya los tenían).
- **T-M**: hardening XSS en `dashboard/sentinel-app.js` (escapeHtml en `s.id`/`s.name`/`s.quoteSrc`).
- **T-N**: `.pre-commit-config.yaml` + `.github/workflows/ci.yml` + `ruff.toml` (lint de correctness F+E9, **NO black** por la alineación manual de `=`) + `docs/coverage_audit_2026-05-25.md` (cobertura total **36%**) + `CONTRIBUTING.md`.
- **T-O COMPLETA** (4 sub-objetivos):
  - #TD-5 (`37ec6dd`): `the_ear` `pct_change`→`None`; el circuit breaker distingue sin-datos de 0% real.
  - #TD-6 (`37ec6dd`): flag `news_disabled` expuesto en `evaluate()`; follow-up: `the_ear_news_disabled` en `/api/status` (commit #ME-3).
  - #OP-2 (`93067d6`): heartbeat externo healthchecks.io. `config.HEARTBEAT_URL` (flag-gated, default off) + `main._send_heartbeat()` async no-bloqueante al final de cada ciclo (`import aiohttp`). Fallo de red → warning, no rompe el bot. `tests/test_heartbeat.py` (3). Nota README.
  - #ME-3 (`ce3480d`): `historian.get_signals_breakdown_today()` → `{filled, cancelled, pending, no_trade}` de las señales de HOY (conteo en `_bucket_signal_rows`, función pura). `/api/status` expone `signals_breakdown_today`. `scripts/queries_signals_breakdown.sql`. `tests/test_signals_breakdown.py` (6).
  - Suite **115/115** (era 106). the_ear 16%→29%.

**Pendiente:** **T-P — cobertura ≥95% módulos críticos** (EN COLA, BLOQUEADA hasta `[COWORK VALIDACIÓN T-O + OK avanzar a T-P]` en `teamwork/LOG.md`). **Migraciones DB aplicadas: 013, 014, 015.**

**Precondición Roman #OP-2:** crear check en healthchecks.io + `HEARTBEAT_URL=https://hc-ping.com/<UUID>` en `.env` + restart `main.py` (sin la URL el ping no hace nada). **Martes 26-may** restart `api.py` con env: `SHADOW_FRACTIONAL_ENABLED=true` + `ATR_SIZING_ENABLED=true` + `PORTFOLIO_DD_LIMITS_ENABLED=true` + `DAILY_REPORT_ENABLED=true`.

## Stack

- Python 3.14, asyncio
- PostgreSQL 18 nativo en Windows (servicio `postgresql-x64-18`)
- alpaca-py con feed IEX (paper)
- aiohttp + NewsAPI (macro)
- scikit-learn (RandomForest, S-10 desactivado)
- pandas (cálculos manuales de indicadores, sin ta-lib)
- LangGraph: planeado, todavía no implementado (loop manual en `main.py`)

## Componentes

| Archivo | Rol |
|---|---|
| `main.py` | Entry point, initialize() + main_loop() alineado a 15 min ET |
| `config.py` | Constantes y validación de credenciales |
| `historian.py` | Pool asyncpg, signals/trades, performance decay |
| `dispatcher.py` | Orquestador: kill-switch, sizing Half-Kelly, ejecución Alpaca |
| `the_ear.py` | NewsAPI cada 15min, VIXY/SPY change, Circuit Breaker, Parking Brake |
| `correlation_guard.py` | Pearson manual sobre rolling 60 velas, umbral 0.75 |
| `regime_classifier.py` | S-10 RandomForest BULL/NEUTRAL/BEAR — **DESACTIVADO** |
| `sentinels/__init__.py` | BaseSentinel + 9 estrategias |
| `api.py` | FastAPI backend (REST + SSE) en puerto 8080. Sirve dashboard estático. |
| `db/schema.sql` | 7 tablas con multi-tenant `owner_id` |
| `db/003_add_order_id_to_trades.sql` | Migración aplicada 2026-04-25: columna order_id en trades. |
| `db/004_create_system_state.sql` | Migración 2026-04-26: tabla system_state (canal IPC api↔main para kill switch). |
| `db/005_fix_trades_status_length.sql` | Migración 2026-04-27: trades.status VARCHAR(10)→(32), drop CHECK constraint para soportar status de Alpaca como PENDING_NEW. |
| `db/006_add_news_titles_to_macro_events.sql` | Migración 2026-04-27: columna news_titles JSONB en macro_events para titulares matched de The Ear. |
| `db/007_create_api_keys_table.sql` | Migración 2026-04-27: tabla api_keys con encrypted_value para gestión visual desde panel admin. |
| `db/008_create_rotation_decisions.sql` | Migración 2026-04-27: log inmutable de decisiones de Universe Selection. |
| `db/009_create_pending_candidates.sql` | Migración 2026-04-27: Watchlist Anticipada con UNIQUE parcial por sentinel. |
| `db/010_add_warning_threshold_to_performance_scores.sql` | Migración 2026-04-27: warning_status + warning_detected_at. |
| `email_service.py` | Cliente async de Resend para welcome/removal emails (templates Design) + template de rotación. |
| `crypto_utils.py` | Fernet helpers (encrypt/decrypt/mask) para api_keys encriptadas. |
| `claude_client.py` | Wrapper async sobre anthropic.AsyncAnthropic con timeout, cost tracking, JSON schema. |
| `universe_selector.py` | Lógica de rotación automática con Claude Sonnet 4.6 (warning/decay → propuesta → rotación). |
| `market_clock.py` | Estado mercado NYSE (OPEN/CLOSED/PRE_MARKET/AFTER_HOURS) + holidays 2026-2027. |

## 9 Sentinels operativos

| # | Tipo | Lógica |
|---|---|---|
| S-1 | sma_crossover | Cruce SMA(10)/SMA(50) |
| S-2 | rsi_short | RSI(2): <15 BUY / >85 SELL |
| S-3 | bollinger_bounce | Cierre fuera de BB(20, 2σ) |
| S-4 | macd_volume | MACD(12,26,9) + volumen >1.5×SMA(20) |
| S-5 | orb_breakout | Opening Range Breakout 9:30 ET |
| S-6 | ema_triple | EMA 8>21>55 alineadas |
| S-7 | vwap_reversion | Cierre fuera de VWAP±2σ intraday |
| S-8 | rsi_divergence | Divergencia RSI(14) en swings (k=3) |
| S-9 | bollinger_squeeze | BBW percentil 10 + breakout |

S-10 (RegimeClassifier) está implementado pero desactivado con early returns documentados — accuracy 0.3849 sobre 3 clases es casi random. Reactivar cuando haya 50-100 trades reales y features adicionales (RSI, MACD, breadth, yield curve).

## Arrancar

```powershell
cd sentinel-v0.5
venv\Scripts\activate
python main.py
```

Requiere PostgreSQL servicio activo y `.env` con credenciales.

## Estado al 2026-05-24 noche — Fase 2/3 robustez (`origin/main` `de4f029`, suite 95/95)

Sesión de robustez post-incidente del Write truncado. Cambios de código relevantes (todos pusheados):

- **Sharpe bug corregido (#TECHDEBT-NEW-1, `67164a5`):** `historian.calculate_performance` ya NO anualiza con `sqrt(252×26)≈80.94`. El Sharpe es **per-trade puro** (`mean/std`). Los valores de `performance_scores.sharpe_ratio` previos al fix (93.9, -120.4) eran artefacto del bug y distorsionaban `dispatcher.allocate_capital`. `SHARPE_MINIMUM` recalibrado 0.5→0.05 en `config.py`. `_SHARPE_ANNUALIZATION_FACTOR` queda definido pero DEPRECADO en el cálculo.
- **CorrelationGuard persistido (#TECHDEBT-NEW-2 / EXP-003, `2bf79ec`):** migración **013** agrega `avg_correlation_at_decision`, `original_qty`, `adjusted_qty`, `reduction_factor` a `signals`. `record_signal` acepta los 4 (default None, backward compat). `dispatcher.process_signal` persiste el output del guard, **incluidas las señales descartadas** por correlación (antes el `return` pre-`record_signal` las perdía).
- **Decay multifactor (#FASE2-NEW-5 / EXP-002, `de4f029`):** `calculate_performance` retorna `profit_factor` + `return_to_drawdown_ratio` (`inf` en edge cases gross_loss=0 / max_dd=0). `evaluate_decay` usa lógica combinada Opción C. Migración **014** agrega ambas columnas a `performance_scores`. Nuevos thresholds `PROFIT_FACTOR_MINIMUM=1.3`, `RTD_MINIMUM=1.0`. (OBS: el `rescued_by_pf_rtd` de la Opción C es matemáticamente redundante — pendiente de revisión por Cowork.)
- **Dashboard XSS hardening (`ac55d40`):** `escapeHtml()` en `dashboard/sentinel-app.js` (5 sitios con datos API/DB) + fix raíz en `tickerSpan` (`dashboard/sentinel-data.js`).

**Migraciones DB local:** 013 + 014 APLICADAS. **Suite: 95/95** (era 77 al inicio del día).

**Scripts ops nuevos en `scripts/`:** `validate-workspace.ps1` (gate anti-truncado — correr antes de cada commit), `clean-git-locks.ps1` (recovery de `.git/index.lock` huérfano), `run_balance_queries.py` + `generate_quantstats_report.py` (balance del período de observación). Migraciones `db/013` + `db/014`.

**Bug `.git/index.lock` recurrente:** resuelto con Windows Defender exclusion del repo (era el escaneo real-time sobre `.git/`).

**Pendiente:** **T-J Fractional trading** (`qty`→`notional`, refactor del dispatcher). Operacional Roman: `UPDATE sentinels SET name='S-2 RSI Fast Reversion' WHERE strategy_type='rsi_short'` en pgAdmin; restart `api.py` martes 26-may con flags `ATR_SIZING_ENABLED` + `PORTFOLIO_DD_LIMITS_ENABLED` ON.

## Estado al 2026-05-23 — Cierre anticipado del período de observación

### Fase 2 en curso (sesión nocturna 23-may, camino a v0.6 martes 26-may)

Coordinación vía `teamwork/LOG.md` (protocolo Cowork↔Code). Avanzado y **pusheado** a `origin/main`: `6a427c5` #H-5b (cache pop tras SELL) + quantstats · `a022de0` #H-4 Decimal correlation_guard · `917cad8` #H-4 Decimal historian · `5fa7125` §-markers dispatcher · `0ed87e4` #H-4 Decimal dispatcher · `3672a82` #H-6b auto-reconcile (poller 5 min en main.py) + #H-4 reconciler. **#H-4 y #H-6b cerrados.** Suite TDD **27/27** en `tests/`.

**Local sin pushear (espera PUSH-OK Cowork):** `5417066` (rename S-2 display→"RSI Fast Reversion", `requirements.txt` `==`, `requirements-dev.txt`).

Pendientes: DB `UPDATE sentinels SET name='S-2 RSI Fast Reversion' WHERE strategy_type='rsi_short'` (Roman) · 56 PENDING_NEW backlog (auto-limpia al arrancar main.py) · siguen lista negra Universe Selector + #GR-4 + #GR-1/#GR-2.

Convención: TDD test-first, backup pre-edit, Decimal en montos (§8.6), commit local + PUSH-OK.

### Sesión del 2026-05-23 (Roma + Code, HANDOFF #2)

El período de observación protegida (28-abr → 27-may) se **cerró anticipadamente el 2026-05-23**, 4 días antes de lo previsto. Decisión de Roman, documentada en `OBSERVATION_PERIOD.md` (sección "Cierre del período"). Motivo: durante las 4 semanas el sistema nunca operó en su forma de diseño (Dispatcher roto hasta 07-may, sizing trivial `qty=1` todo el período, bug #H-5b reaparecido 2 veces). Acumular más días sub-óptimos no aporta señal. El balance del período se lee como **versión sub-óptima del diseño**, no como evaluación del diseño final.

**El bot sigue en paper trading.** El cierre NO implica transición a live (live conservador previsto para julio 2026, post-Fase 4).

#### Restricciones del período — LEVANTADAS a partir del 23-may

Todas las reglas de la sección "❌ NO PERMITIDO" de `OBSERVATION_PERIOD.md` dejan de aplicar. Ahora SÍ se puede tocar SYSTEM_PROMPT del Universe Selector, thresholds, prompts, parámetros de estrategias, agregar/remover Sentinels, lógica de agentes, timeouts, reactivar S-10, e implementar features bloqueadas — **pero no de forma indiscriminada**: todo cambio sigue el plan de 6 fases (abajo). Fase 1 debe completarse antes de Fases 2-3.

#### Reporte diario — DESACTIVADO

El scheduler del reporte diario (16:30 ET L-V, `_daily_report_loop` en `api.py`) quedó **desactivado** vía flag `DAILY_REPORT_ENABLED` (definido en `config.py`, default `True`; puesto en `false` en `.env`). El arranque del scheduler en el lifespan de `api.py` ahora chequea el flag antes de crear la task. Email de cierre enviado a los 5 viewers el 23-may avisando la pausa.

- **Reactivar para el 2do período de observación (junio):** poner `DAILY_REPORT_ENABLED=true` en `.env` (o quitar la línea — el default es `True`) y reiniciar `api.py`.
- **Requiere restart de `api.py`** para tomar efecto (el proceso vivo mantiene el loop anterior hasta reiniciar).
- El endpoint manual `/api/report/daily/send-now` sigue activo para tests.
- La lógica del reporte NO se borró — solo se desactivó el disparo automático.

#### Plan post-observación activo — 6 fases (detalle en `NEXT_ITERATION.md`)

1. **Fase 1 — Análisis del período (días 1-3).** Métricas por Sentinel (win rate, Sharpe, profit factor, drawdown, slippage), equity curve, evaluación de Universe Selector / The Ear / CorrelationGuard. Recomendado QuantStats (#HE-1).
2. **Fase 2 — Auditoría de código (días 4-7).** Aplicar `BUENAS_PRACTICAS_V2` al codebase, cerrar #H-4 (float→Decimal restante) y #H-5b (cache `open_positions`), hardening dashboard, tests core, code review externo opcional.
3. **Fase 3 — Features bloqueadas (días 8-14).** Por prioridad: rename S-2, fix #H-5b, lista negra de leveraged/decay en prompt del Universe Selector, fractional trading (`qty`→`notional`), módulo `simulated_costs`, trigger `idle_timeout`, reactivar S-10, plugin Equity Research.
4. **Fase 4 — Segundo período de observación (30 días, junio).** Código limpio, sigue en paper, sin leverage. Validar mejora consistente vs abril-mayo.
5. **Fase 5 — Live conservador (julio 2026, condicionado).** Capital pequeño ($500-2K), solo bots long-cash, fractional, sin leverage, paper experimental en paralelo.
6. **Fase 6 — Hipótesis exploratorias (post-julio, condicionado).** Leverage escalonado 1.25x, shorts intencionales, multimercado, La Forja.

#### Eventos del período (resumen, detalle en `OBSERVATION_PERIOD.md`)

- Excepción 1 (07-may): scores parciales + agregación Dispatcher.
- Excepción 1.1 (08-may): Decimal/float + JOIN zombies + cleanup Mantis.
- Excepción 1.2 (13-may): Capital card dashboard (endpoint read-only).
- Intervención manual SPY (11-may) y QQQ (16-may): cierres de short accidental por #H-5b. Costo acumulado #H-5b: ~−$12 en QQQ, +$4.53 en SPY.
- Hallazgo 11-may: sizing trivial `qty=1` → diferido a #GR-2.

Contador del período nunca reiniciado (todas fueron correcciones de bug, no cambios de hipótesis).

---

## Estado al 2026-05-08 — Excepción 1 ampliada: dos bugs heredados

### Sesión del 2026-05-08 (Roma + Roman)

Primer día de mercado post-Excepción 1. Aparecieron dos bugs que la Excepción 1 expuso:

1. **Dispatcher: TypeError float += Decimal** en `allocate_capital()`. Mezcla de tipos al sumar `weighted_sharpe_sum` (float) con `score["sharpe_ratio"]` (Decimal de asyncpg). 21 errores en logs el 08-may. Resultado: `cycle_allocation = {}` cada ciclo → todos los Sentinels al fallback `MIN_CAPITAL_PER_SENTINEL = 5%` plano → órdenes con `qty=1`.

2. **Universe Selector: bucle de rotación zombie**. `historian.get_sentinel_scores()` no hacía JOIN con `sentinel_tickers`, devolvía scores de tickers ya rotados (`is_active=FALSE`). Mantis (S-2) ejecutó 23 rotaciones en 6h sobre TSLA y SPY zombies, costo ~$0.65 USD, acumulando 18 tickers nuevos.

**Fixes aplicados** (registrados como ampliación de Excepción 1, contador NO reinicia):

- `dispatcher.py` L153-163: conversión explícita `float()` e `int()` al leer scores. Cierra **#H-4** (último 🟠 ALTO pendiente).
- `historian.py` L585-619: `get_sentinel_scores()` con `JOIN sentinel_tickers ON is_active=TRUE`.
- DB: limpieza de Mantis a `NVDA + XLU + TLT` activos (resto inactive, sin borrar). Cubre Ambientes 2 (NVDA tech), 3 (XLU defensivo) y 4 (TLT bonos largos) del marco All Weather, todos compatibles con rsi_short (mean reversion).

**Validación:** simulación en `backups/2026-05-08/test_fixes_simulation.py` reproduce el TypeError y demuestra que ambos fixes producen allocation Sharpe-weighted Half-Kelly correcta (Mantis al 25% techo, qty NVDA pasa de 1 a ~200 shares).

**Pendiente para Roman al volver:** ejecutar `cleanup_mantis.sql` en pgAdmin y reiniciar `main.py`. Pasos en `backups/2026-05-08/DEPLOY_STEPS.md`. Mercado cerrado, ventana de deploy óptima.

**Deferido:** Trigger `idle_timeout` propuesto para Universe Selector — cae en "cambiar lógica de agente", se difiere a post-2026-05-27. Anotado en `NEXT_ITERATION.md`.

---

## Estado al 2026-04-28 — segunda jornada paper + Frente A/A.5 dashboard honesto

### Sesión del 2026-04-28 (Roman + Code) — todo READ-ONLY o cosmética dashboard

**Período de observación protegida vigente** (28-abr → 27-may). Default no-tocar; lo de hoy entra en "observabilidad read-only" + "cosmética dashboard". Cero cambios a thresholds, prompts, agentes, schema o datos de DB.

#### 1. Inventario read-only de DB (`backups/sentinel_2026-04-28_pre_inventory.dump` 49 KB + `inventory_2026-04-28.txt` 53 KB)

12 tablas auditadas (no 11 — apareció `sentinel_tickers` con 27 filas que la lista del prompt original no incluía). Hallazgos:

- **Timestamps en DB están en EDT** (hora local del server), no UTC. Para distinguir "handoff vs día real" el cutoff conceptual es `2026-04-28 09:30:00` (apertura mercado), no `13:30 UTC` como se asumía.
- **`signals`**: 36 filas. 17 del 27-abr (TSLA/NVDA/MSFT/GLD/SPY/QQQ/XLP), 19 del 28-abr.
- **`trades`**: 19 filas, **TODAS del 28-abr** (las 17 signals del 27 nunca llegaron al dispatcher). Status: 8 FILLED / 6 PENDING_NEW / 5 CANCELLED. Tickers: TSLA, NVDA, SPY, QQQ, AAPL, GLD, MSFT.
- **`performance_scores` VACÍA** → los win_rate/sharpe ficticios del dashboard NO venían de DB.
- **`macro_events`**: ~275 (drift, The Ear sigue ingresando cada 7-15 min).
- **`migration_log` y `api_keys` vacías** (esperado).
- **`rotation_decisions` y `pending_candidates` vacías** (Universe Selection no disparó porque performance_scores está vacía → nadie cruzó warning/decay threshold).
- **AMD aparece sólo en `sentinel_tickers`** (asignado a S-4 y S-9), nunca emitió signal ni trade. Refuta hipótesis inicial: los datos AMD/+$115 del dashboard NO eran seed de DB.

#### 2. Auditoría dashboard (`audit_dashboard_2026-04-28.md` 28 KB, 364 líneas)

Mapeo completo: 28 endpoints backend, 12 fetch frontend, 38 elementos del dashboard (16 reales / 7 parciales / 15 sintéticos). Veredicto: **Escenario B (parcial)**. La causa raíz NO era una sola función — eran 3 mecanismos mezclados:
- Markup literal en `index.html` sin `id` (11 piezas).
- Funciones sintéticas en `sentinel-app.js` (handoff Design): `renderSentGrid` mini-charts, `renderDetail` tickers operados, `renderHistorian` columnas trades/slip/decay, `buildReport` cliente, `tick` (interceptado).
- Constantes hardcoded en `sentinel-data.js`: `STATE.balance = 100000`, `synthEquityHist()`, `AGENTS[]` con `active` fijo.

Los 11 casos especiales del prompt resueltos uno por uno con archivo:línea exacto.

#### 3. Frente A — markup honesto + renderers reales

Backup: `backups/dashboard_2026-04-28_pre_fix_a.tar.gz` (28 KB).

Cambios:
- **`index.html`** +10/-10: 11 IDs nuevos sobre markup literal (`#agentsActiveCount`, `#osPnlPct`, `#osOpenPos`, `#osSigApproved`, `#osSigRejected`, `#eqMaxDD`, `#cgAvgCorr`, `#cgReduced`, `#cgDiscarded`, `#footUptime`, `#footBuild`).
- **`sentinel-data.js`** +118/-1: `STATE.balance = null` (era 100000), nueva sección "Frente A" con `renderAgentsActiveCount`, `renderCircuitBreakerToggle`, `renderParkingBrakeToggle`, `renderEmptyKPIs`, `fetchAndRenderBuild`. Llamadas en `loadStatus()` (toggles + count) y al final de `reloadFromAPI()` (`renderEmptyKPIs` sobrescribe).
- **`sentinel-app.js`** +53/-20: `renderHeader` y `renderEquity` envueltos en `if (STATE.balance != null)` para no romper con null. `renderHistorian` ahora lee `s._api.total_trades` y `s._api.decay_status` reales (slip queda "—"). `downloadReport` async pegando contra `/api/report` real (mapeo `last_hour` → `today` para evitar 422). `buildReport()` original conservada por si algo la usa.

Política central: **mostrar "—" en lugar de inventar**. KPIs sin endpoint (BALANCE, P&L, POSICIONES, signals procesadas, max DD, correlation guard, uptime) muestran em-dash hasta que Frente B agregue endpoints. Cuando exista `/api/account/equity`, se reemplazan los `_setText(id, _DASH)` en `renderEmptyKPIs()` por la lectura del campo correspondiente.

#### 4. Frente A.5 — neutralizar columnas sintéticas en `renderDetail` + corregir etiqueta engañosa

Backup: `backups/dashboard_2026-04-28_pre_fix_a5.tar.gz` (16 KB).

Cambios:
- **`sentinel-app.js`** +46/-9: solo el bloque `tickerRows` dentro de `renderDetail`. Iteración cambia de `s.tickers` (strings) a `s._api.tickers` (objects). Las 4 fórmulas `charCodeAt` del bundle eliminadas — ahora usa `last_signal`, `pnl`, `win_rate`, `sharpe_ratio` reales con regla "0 → '—'" porque el backend mapea NULL → 0.0 (api.py L493-495). Sharpe negativo SÍ se muestra.
- **`sentinel-i18n.js`** +4/-4: `dt_tickers` cambiado de "TICKERS OPERADOS" → "TICKERS ASIGNADOS" en es/en/ja/th. Los tickers que se muestran son del universo asignado (`sentinel_tickers`), no los efectivamente operados — el nombre nuevo no miente. `dt_recent` ("ÚLTIMOS 5 TRADES") intacto porque esa tabla SÍ son trades reales.

#### 5. Anomalías documentadas pendientes de acción

- **`***REMOVED-EMAIL***` sigue en `users`** (creado 2026-04-28 11:15:31). Roman dijo que fue eliminado hoy por incidente de seguridad — la eliminación NO se ejecutó en DB. Próxima sesión: ejecutar el DELETE vía panel admin o script controlado.
- **17 signals huérfanas del 27-abr** que nunca llegaron al dispatcher. Verificable revisando logs de ese día (fuera de scope hoy).

## Próximos pasos

### Frente B — endpoints faltantes (PARA POST-OBSERVATION o como excepción documentable)

✅ **Operativo y corriendo**:
- API + Cloudflare Tunnel + main.py corriendo. Primer ciclo real con mercado abierto fue lunes 2026-04-27.
- DB con 9 Sentinels (5% allocation cada uno, 45% total). 27 tickers en `sentinel_tickers`.
- Auth Google OAuth con roles ADMIN/VIEWER. Único ADMIN: `***REMOVED-EMAIL***`. Único VIEWER: `goorale@gmail.com`.
- Kill switch operacional: botón DETENER/INICIAR del dashboard dispara halt/resume vía DB flag, poller cada 5s en `main.py` ejecuta `activate_kill_switch`/`deactivate_kill_switch`.
- Panel admin en `/admin` (ADMIN-only): CRUD de usuarios con welcome/removal email automático vía Resend desde `noreply@afterlifecapital.co` (dominio verificado).
- Universe Selection automática habilitada con Claude Sonnet 4.6.

### Bloque 1 (2026-04-27 — fixes del primer día) — mergeado a main

- `#FIX-005` trades.status VARCHAR(10)→VARCHAR(32) + drop CHECK constraint. PENDING_NEW de Alpaca ya no rompe el INSERT.
- `#FIX-006` `/api/report` con datos reales del Historian (uptime, signals_received, news_that_moved_decisions, etc.). El `buildReport()` cliente-side de sentinel-app.js sigue siendo demo y queda en TECHDEBT — el endpoint real es la fuente de verdad.
- `#FIX-007` The Ear persiste top 5 titulares en `macro_events.news_titles` (JSONB).
- `#FIX-008` Panel admin con gestión de API keys encriptadas (Fernet). El bot SIGUE leyendo desde .env — la sincronización automática es trabajo futuro. Requiere `MASTER_ENCRYPTION_KEY` en .env.

### Bloque 2 (2026-04-27 — Universe Selection) — mergeado a main

Sistema completo de rotación automática (Modo A — sin aprobación manual):
- `claude_client.py` — wrapper async con timeout (30s), cost tracking ($/M tokens), JSON schema. Cap por call $0.20.
- `universe_selector.py` — `evaluate_all_sentinels()` corre cada ciclo de 15min:
  - Pre-decay (warning): pide candidato y queda en watchlist 7 días.
  - Decay confirmado: ejecuta candidato pendiente o pide urgente.
  - Recuperación: descarta candidato pendiente.
- 3 tablas nuevas: `rotation_decisions` (log auditable con costo USD), `pending_candidates` (Watchlist con UNIQUE parcial), `performance_scores.warning_status`.
- 5 endpoints admin: `GET /api/admin/rotations[?status=]`, `GET /admin/rotations/{id}`, `POST /admin/rotations/{id}/rollback`, `GET /admin/candidates`, `GET /api/rotations/recent` (público VIEWER).
- Email automático al admin en cada rotación (template cyberpunk).
- Banner discreto de rotaciones recientes (24h) en dashboard.
- Sección de rotaciones + candidatos en panel admin con modal de detalle (razonamiento Claude, costo, candidatos alternativos) y rollback con confirm + email logueado.
- Test real al deploy: $0.0142 por call, 1169 in / 710 out tokens. Costo mensual estimado: ~$3.80 normal, ~$68 pico (cap mensual de $10 ya configurado en console.anthropic.com).

### Bloque 3 (2026-04-27 — The Ear + visibilidad) — mergeado a main

- `#FIX-009` Substring bug en keyword matching: `keyword in text` → `re.compile(\b{kw}\b)` con IGNORECASE. Elimina falsos positivos como "war" en "warnings". Trade-off documentado: word-boundary no matchea plurales (tariffs ≠ tariff, surges ≠ surge) — aceptamos precisión sobre recall.
- `#FIX-010` Endpoint `GET /api/macro_events?limit=N` (VIEWER+ADMIN) + frontend que reemplaza el placeholder genérico "Macro update — risk X · VIX Y · SPY Z" por el primer titular real de news_titles[]. Fallback al formato genérico si el evento no tiene titulares.
- `#FIX-011` Endpoint `GET /api/market-status` (público) + indicador en header con MERCADO ABIERTO/CERRADO/PRE-MERCADO/POST-MERCADO + countdown adaptativo (1h 42m / 17h 14m / 2d 5h). Estados con colores semánticos (verde/rojo/amarillo/magenta). `market_clock.py` con holidays NYSE 2026-2027 hardcoded.

### Hardening post-auditoría (sesiones 1–4 — 2026-04-25 / 2026-04-26)

**Sesiones 1–2.5** (2026-04-25):
- `#H-2` Race TheEar → `asyncio.Lock`.
- `#H-3` Timeouts asyncpg + `asyncio.wait_for` en los 11 call sites Alpaca.
- `#H-5` open_positions desync → refactor `list[dict]` → `dict[str, dict]`.
- `#H-6` Limit orders en background con `_check_later` + migración 003 (`order_id`).
- `_is_limit_strategy` set explícito; `approved = status == "FILLED"`; `done_callback` en ear_task.

**Sesión 3** (2026-04-26 — kill switch + Sharpe):
- `#H-7` kill switch operacional: tabla `system_state` (migración 004) como canal IPC entre `api.py` y `main.py`. Endpoints `POST /api/system/halt`, `POST /api/system/resume`, `GET /api/system/state`. Poller en `main.py` cada 5s. Frontend toggle DETENER/INICIAR.
- Sharpe annualization (#TECHDEBT promovido): factor `sqrt(252×26) ≈ 80.94` aplicado en `historian.calculate_performance`.

**Sesión 4** (2026-04-26 — auth + admin panel + integración Design):
- `#H-1` Google OAuth: rutas `/auth/login,callback,logout,me` con Authlib + SessionMiddleware (cookie firmada itsdangerous, HttpOnly, Secure, SameSite=Lax, 24h). Middleware `auth_middleware` con matriz de gating (público / sesión / role=ADMIN).
- Roles ADMIN/VIEWER aplicados en endpoints. VIEWER no ve botón DETENER ni link ADMIN; `/admin` redirige silently a `/`.
- Panel admin (`/admin`): handoff Design integrado (`admin.html` + `admin-app.js`) con adapter `user_id → id` para mantener API.
- Email service Resend con templates HTML del handoff Design (welcome bilingüe ES/EN con bloque permisos ADMIN, revoked bilingüe ES/EN). Envío async con httpx.

**Sesión 4.1** (2026-04-26 tarde — fixes UX dashboard + landing):
- `dashboard/sentinel-data.js`: logo `.brand` del header ahora es clickeable, abre `https://www.afterlifecapital.co` en nueva pestaña con `noopener,noreferrer`. Accesible por teclado (Enter/Space) con `role=link` y `tabindex=0`. Sin tocar `index.html`. Commit `0723a93`.
- `index.html` (raíz, landing Vercel): link CTA actualizado de `bot-cambio-ruta-production.up.railway.app/` a `sentinel.afterlifecapital.co/`. Commit final `77f6740` tras incidente: el primer intento (`33156b7`) consumió el `\` que escapaba la quote `\"` del atributo `href` dentro del `<script type="__bundler/template">` JSON-string, rompiendo el render. Revertido (`64f246b`) y reaplicado con regex que respeta el escape. JSON validado con `ConvertFrom-Json` antes del push.

### Issues 🟠 ALTOS — estado al 2026-04-27
- ✅ #H-1 (auth API)
- ✅ #H-2 (race TheEar)
- ✅ #H-3 (timeouts)
- ✅ #H-5 (open_positions)
- ✅ #H-6 (limit orders)
- ✅ #H-7 (kill switch)
- ⏳ **#H-4 — float→Decimal en cálculos financieros**. Único 🟠 pendiente.

### Issues #FIX-* (Bloques 1-3) — todos cerrados al 2026-04-27
- ✅ #FIX-005 trades.status VARCHAR + CHECK
- ✅ #FIX-006 /api/report con datos reales
- ✅ #FIX-007 news_titles persistidos por The Ear
- ✅ #FIX-008 panel admin con API keys encriptadas
- ✅ #FIX-009 substring bug en The Ear
- ✅ #FIX-010 /api/macro_events + render real
- ✅ #FIX-011 /api/market-status + indicador header

### Universe Selection (#UNIVERSE-SELECTION) — operativo al 2026-04-27
- Modo A (automático) habilitado. Email al admin por cada rotación.
- Cap mensual $10 en console.anthropic.com.
- Cap por call $0.20 (test real: $0.0142).

### Branches
- `main` — todos los bloques mergeados, último commit `9403e69` (DESIGN_CHANGES.md fixes 10-11).
- `feature/the-ear-improvements` — Bloque 3 (mergeado).
- `feature/universe-selection` — Bloque 2 (mergeado).
- `feature/day1-fixes` — Bloque 1 (mergeado).
- `backup/pre-redesign-2026-04-25` — snapshot inmutable previo.

## Decisiones clave

- **Sin Docker**: PostgreSQL 18 nativo en Windows (Docker Desktop fallaba en setup inicial).
- **Refactor BaseSentinel**: `fetch_bars`, `_fetch_bars_sync`, `run` centralizados. Cada Sentinel solo define `__init__` + `analyze`.
- **`feed=DataFeed.IEX` obligatorio**: la cuenta paper sin SIP da 403 al pedir datos recientes. Aplicado en los 4 sitios que hacen StockBarsRequest.
- **S-10 desactivado**: ahorra 30-60s de arranque (no descarga 25 años de SPY ni entrena RF). `get_regime()` retorna `"NEUTRAL"` fijo. Reactivar editando los early returns en `regime_classifier.py`.
- **RSI con SMA, no Wilder**: cálculo simplificado en `_rsi()`. Diferencia marginal vs Wilder smoothing — mejorar después si hace falta.
- **Logs**: `logs/sentinel.log` con RotatingFileHandler (5MB, 3 backups).

### Backlog operativo (post-observation)

1. **#H-4** float→Decimal en cálculos financieros (último 🟠 ALTO pendiente).
2. Dashboard hardening: XSS innerHTML, race SSE, defensa Chart.js.
3. Implementar nodo LangGraph real en `main.py` (actualmente loop manual con `asyncio.gather`).
4. Mejorar `_rsi()` a Wilder smoothing (S-2, S-8).
5. Reactivar S-10 cuando criterios estén (50–100 trades + features adicionales).
6. Universe Selection — agregar plurales/conjugaciones a `_NEGATIVE_KEYWORDS`/`_POSITIVE_KEYWORDS` o cambiar pattern a `\b{kw}s?\b` si word-boundary estricto pierde mucha señal.
7. ✅ Botón "DESCARGAR REPORTE JSON" — migrado a `/api/report` real (Frente A 2026-04-28). TECHDEBT.md L132 cerrado.
8. Sincronización automática `.env` ↔ tabla api_keys (hoy es solo gestión visual).
9. Deploy a Raspberry Pi 5.

### Frente B propuesto (cuando OWNER lo autorice como excepción o post-2026-05-27)

Endpoints **read-only nuevos** que rellenan los "—" del dashboard sin cambiar lógica del bot. Cada uno reemplaza un `_setText(id, _DASH)` en `renderEmptyKPIs()` por la lectura del campo correspondiente:

- `/api/account/equity` → llamar Alpaca `get_account()` y devolver `{balance, equity, cash, day_pnl, day_pnl_pct, positions_count}`. Reemplaza: `#osBalance`, `#osPnl`, `#osPnlPct`, `#osOpenPos`, `#eqCapital`, `#eqPnl`.
- `/api/equity/series?range=today` → curva real desde Alpaca portfolio history. Reemplaza: `#eqChart` (renderEquity hoy usa `synthEquityHist`) + permite calcular `#eqMaxDD` real.
- Persistir `signals.approved` + `signals.rejection_reason` (TODO en api.py L911-913) → exponer en `/api/signals/summary` para `#osSigProc`, `#osSigApproved`, `#osSigRejected`.
- Persistir `signals.correlation_action` + `signals.correlation_used` (TODO api.py L897-901) → `/api/correlation/summary` para `#cgAvgCorr`, `#cgReduced`, `#cgDiscarded`.
- Endpoint liviano `/api/version` con `{system_version, uptime_hours}` (hoy hay que pegarle a `/api/report` completo solo para sacar el build) → `#footUptime`, `#footBuild`.

Nota importante: estos endpoints técnicamente "exponen datos que ya existen" (no modifican lógica), pero agregar columnas nuevas a `signals` toca schema. Si Roman autoriza durante observación, **registrar como Excepción en `OBSERVATION_PERIOD.md` y resetear el contador de 30 días**. Más conservador: anotar en `NEXT_ITERATION.md` y aplicar después del 2026-05-27.

### Acciones operativas pendientes (no son features)

- **Eliminar `***REMOVED-EMAIL***` de `users`** — eliminación falló hoy 2026-04-28, sigue en DB con `created_at = 2026-04-28 11:15:31`. Ejecutar via panel admin (`DELETE /api/admin/users/{user_id}`) o script controlado.
- Investigar por qué las **17 signals del 27-abr nunca llegaron al dispatcher** (logs de ese día — `logs/sentinel.log`).
- Roman pendiente: rotar credenciales OAuth de Claude Code en meridian (incidente 25-abr, tokens viejos siguen vivos).

## Bugs conocidos

- Ninguno bloqueante al cierre 2026-04-28.
- ORB y VWAP retornan `price=0.0` cuando no hay barras del día actual ET (sábado/domingo o pre-market). El `run()` filtra por `qty=0.0` así que no afecta el pipeline, pero es estéticamente raro en logs.
- `update_trade_status` no warns si 0 rows afectados (ej. order_id no existe en DB).
- `record_trade` se hace en el mismo try que `record_signal`; si `record_signal` falla, la orden ya está en Alpaca pero sin fila DB.
- Reconciliación post-restart de limit orders: si el sistema cae con tasks `_check_later` en vuelo, mueren con el proceso. La orden Alpaca queda activa pero sin tracking. TODO en `dispatcher.execute_order`.
- `system_halted` flag persiste entre reinicios pero el Dispatcher arranca con `kill_switch_active=False` in-memory. Discrepancia hasta que el poller reaccione a un nuevo `halt_requested` o `resume_requested`.
- `OWNER_EMAIL` hardcodeado en dos lugares (`historian._OWNER_EMAIL` y `admin-app.js`). Si cambia el admin Google, hay que editar ambos.
- Word-boundary regex de The Ear (#FIX-009) no matchea plurales/conjugaciones — trade-off intencional vs falsos positivos del bug original. Si una nota relevante usa "tariffs" en lugar de "tariff", la perdemos.
- Holidays NYSE en `market_clock.py` hardcodeados 2026-2027. Hay que actualizar manualmente en noviembre 2027 cuando NYSE publique 2028.
- Indicador de mercado puede no aparecer si el handoff borra `.hdr-stats` después de los 3s del retry de `ensureNode()`. No observado en producción aún.
- Titulares de NewsAPI llegan en inglés y se muestran tal cual en los 4 idiomas (es/en/ja/th) — no hay traducción automática.
- Cache miss del system prompt de Universe Selection: el SYSTEM_PROMPT (~400 tokens) está debajo del mínimo cacheable de Sonnet 4.6 (2048). Cada call paga full price input. Si querés activar caching, engrosar el prompt o aceptar la limitación.

## Seguridad

- Multi-tenant: todo dato lleva `owner_id`. Owner actual: `roman` / `***REMOVED-EMAIL***` (UUID `***REMOVED-UUID***`).
- `.env`, `client_secret_*.json`, `.claude/` excluidos de git y de Drive sync.
- NEWS_API_KEY enviado en header `X-Api-Key` (nunca en URL params).
- Kill switch: `dispatcher.activate_kill_switch("CONFIRMAR")` requiere passphrase exacta. Disparable desde `/api/system/halt` (ADMIN-only) o desde el botón DETENER del dashboard.
- Auth: Google OAuth con cookie firmada itsdangerous (HttpOnly, Secure, SameSite=Lax, max-age 24h). Solo emails registrados en `users` reciben sesión válida.
- Resend: dominio verificado `afterlifecapital.co`. Emails desde `noreply@afterlifecapital.co` con `X-Entity-Ref-ID` para tracking.
