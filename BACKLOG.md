# BACKLOG — Afterlife Capital / Sentinel

> **Fuente única de verdad consolidada.** Reemplaza a `NEXT_ITERATION.md` y `TECHDEBT.md` (obsoletos). Cualquier nuevo item entra acá primero.

**Mantenedores:** Roman (decisiones) · Cowork (Roma — coordinación) · Code (ejecución del bot).

**Última actualización:** 2026-05-25 noche (post-T-S pusheado en `31f0304` + T-T DONE local en `78823da` + 3 specs movidas a `docs/` + T-U lista para Code arrancar).

---

## Convenciones

**Tipos:** `BUG-CRIT` / `BUG-FUNC` / `BUG-COSM` / `TECH-BLOCK` / `TECH-DRIFT` / `FEAT-CORE` / `FEAT-NICE` / `ARCH` / `EXP` / `OPS` / `DOC`.

**Prioridades:** `P0` bloqueante / `P1` próxima iteración / `P2` backlog cercano / `P3` futuro.

**Status:** `TODO` · `WIP` · `BLOCKED` · `DONE` (mover a `Archivo DONE`) · `WONTFIX` · `DIFERIDO`.

---

## Bloques activos / Pipeline

| ID bloque | Cubre items | Status | LOG entry |
|---|---|---|---|
| **T-N** Robustez de Desarrollo | #FASE2-NEW-1 + #FASE2-NEW-2 + #FASE2-NEW-4 audit + ruff fix | ✅ DONE pusheado en `7727511` | `[04:35]` + `[05:30]` |
| **T-O** Robustez The Ear + Observabilidad | #TD-5 + #TD-6 + #OP-2 + #ME-3 | ✅ DONE pusheado en `7727511` | `[04:40]` + `[06:30]` |
| **T-P** Cobertura ≥95% módulos críticos | 9/9 módulos a **100%**, gate CI ≥95% | ✅ DONE pusheado en `7727511` | `[06:45]` |
| **T-Q** UPDATE rename S-2 | #OPS-008 idempotente | ✅ DONE (ya estaba aplicado) | LOG sesión fresca |
| **T-R** TECHDEBT cleanup Bloque F | 9/9 sub-commits cerrados | ✅ DONE pusheado en `7727511` | LOG decisiones + DONE |
| **T-S** Compliance + Slippage Bloque C | #ME-1 + #ME-4 + #CR-3 + #CR-1 + #CR-2 (5/5) | ✅ DONE pusheado en `31f0304` | LOG `[T-S]` |
| **T-T** Plugins externos Bloque E (Code) | #HE-2 IDEA insert + #HE-4 fees + Sub-3 Equity Research framework por prompt | ✅ DONE local en `78823da` (ahead 10). Sub-3b (datos reales 10-K/EDGAR) → backlog P3. #HE-2b (transición ENTRY_READY→ACTIVE + MAE/MFE backfill) → próximo finde | LOG `[T-T cierre]` |
| **T-U** distilFinBERT (#FEAT-007) | Reemplazo The Ear keyword matching, modo hybrid (ProsusAI/finbert, no yiyanghkust por incompat transformers 5.x) | ✅ DONE local en `78823da→e934338` (ahead 16). 6 commits + migración 018. Suite 610→636. Plan calibración en `docs/finbert_recalibration_plan.md` | LOG `[T-U cierre]` |
| **T-V** 3 cambios comportamiento bot | #FEAT-014 cooldown + #TECH-003 FIFO + Wilder RSI | ✅ DONE local 3/3 (`571f30c` + `b1bf88b` + `a5db770`). Suite 636→658. Cooldown/Wilder flag-gated default OFF | LOG `[T-V cierre]` |
| **#TECH-004** Fix tests dispatcher heredan .env | Fixture autouse parchea `config.ATR_SIZING_ENABLED` | ✅ DONE local en `c6ea32d`. Suite 636/636 verde con .env actual (ATR=true) | LOG `[#TECH-004]` |
| **Bloque G Cowork** | #FASE2-NEW-5 + #TD-26 research + análisis cualitativo P1 + research FinBERT (DONE) · #DOC-005 (diferido por falta DB) · **#BUG-002 CERRADO** como artefacto histórico | ✅ 5/6 items DONE | varias entradas |

**Pipeline próximo (Roman decide orden — sprint finde 31-may/1-2 jun):**
- **Bloque D — Patrón Broker:** #ARCH-001 (1-2 sesiones realistas).
- **Bloque I — Mejoras menores:** Nota matutina + Directrices diseño emails (1 sesión).
- **#TECH-002** Limpieza HTMLs viejos dashboard (15 min).
- **#HE-2b** Transición ENTRY_READY→ACTIVE + MAE/MFE backfill (post-#HE-2 IDEA insert).
- **#FEAT-EquityResearch-real (Sub-3b)** Parsing 10-K/EDGAR + DCF real (vs framework por prompt actual).
- **Signals.rejection_reason** (drift T-V: cooldown/duplicate descartes solo observables por logs).
- **#TECH-005** ✅ DONE local en `20e21b0` (26-may noche). max_tokens 2000→8000 + error tipificado `truncated_max_tokens` + 2 tests. Sin retry automático (KISS, evita duplicar costo API). Si recurre con 8000, agregar retry.
- **#TECH-006** ✅ DONE local en `f80e231` (26-may noche). Bug REAL confirmado: query de failed_tickers estaba incompleta. Fix con UNION old+new. Validado DB: S-2 antes {SPY,TSLA}, ahora incluye GLD + 17 más. Drift importante: NO estaba conectado con #TECH-005 (eran 2 bugs independientes).
- **#TECH-007** Backtest framework #HE-4 — adapter intradía NO reproduce S-5 ORB / S-7 VWAP / S-9 Squeeze (0 trades en backtest, 3/8/3 trades reales). `backtest/adapters.py` no maneja contexto de sesión intradía. P2, sprint próximo finde.
- **#FEAT-008** Backtest LLM-driven con Claude API (C2 diferido del incidente 26-may). Validación cualitativa del SYSTEM_PROMPT mediante replay programático con T=0 + 2-3x repeticiones. Code en este incidente ya razonó como Universe sobre 2 semanas; queda el replay programático cuando haya tokens. P3.
- **#FEAT-009** Revisar thresholds warmup/decay del trigger Universe Selector — el umbral `sharpe<0.65` puede gatillar rotaciones contraproducentes en tickers con win rate alto pero cola gorda (NVDA) o baja volatilidad (utilities). Ponderar win rate o ajustar umbral. P2, sprint post-período 2 con data real.
- **#FEAT-010** ✅ DONE local en `1206183` (26-may noche). Regla "categoría-fallida > cobertura" agregada al SYSTEM_PROMPT + 1 test.
- **T-X #FEAT-011** ✅ DONE local en `7a839c9` (26-may noche). TP/SL ATR multipliers per-Sentinel (Opción B). Dict `ATR_PER_SENTINEL` + helper `get_atr_multipliers_for_strategy` + wire dispatcher.process_signal. 23 tests TDD nuevos. Spec en `docs/TAREA_T-X_tpsl_per_sentinel.md` con justificación técnica por Sentinel. Suite 685, config 96% / dispatcher 100%.
- **#TECH-008** Backtest framework #HE-4 con TP/SL brackets — el framework actual NO incluye los brackets de ATR_SIZING en la simulación. Sharpes/win rates históricos del período 1 (qty=1 sin brackets) no son comparables con período 2 post-T-X. Ampliar `backtest/` para simular brackets, re-medir métricas per-Sentinel. P2, sprint post-período 2 con data real ATR.
- **Análisis P&L real período 1** — Code extraer de la DB: equity inicio/cierre, P&L global + por Sentinel, win rate global + por Sentinel sobre 28-abr → 23-may. Comparar con backtest mecánico para validar el orden de magnitud del framework #HE-4. P1, próxima sesión Code (rápido, 15 min).
- **Bloque J — Futuro P3:** Leverage + risk budgeting + Reactivar S-10 + Trailing stops + Riskfolio-Lib (post-Fase 5).

**Afuera (NO se trabaja, 11 items):** #OPS-005 LLC + #OPS-006 Auditoría IAs + #FEAT-011 SMS/Telegram + #OPS-007 OAuth Meridian + Paper-Live paralelo + #TM-1/4/5 + Multimercado + La Forja + Batching Universe Selector.

**Sacados de AFUERA recientemente (decisión Roman 2026-05-25):**
- `#FEAT-007 distilFinBERT` → P0 ACTIVO en T-U (martes 26-may).
- `#FEAT-012 + #FEAT-013 Dashboard rework v2` → P1 ACTIVO para sprint próximo fin de semana (~31 may / 1-2 jun).

---

## Plan próximo fin de semana (~31 may / 1-2 jun)

**Sprint propuesto** (~9 macro bloques al ritmo actual):

| Prioridad | Bloque | Riesgo período |
|---|---|---|
| 1 | **Dashboard rework v2** completo (#FEAT-012 + #FEAT-013 + #TD-13 `/api/v1` + #TD-18-21) | ❌ Frontend, no afecta lógica del bot |
| 2 | #ARCH-001 Patrón Broker (abstracción Alpaca) | ❌ Refactor estructural |
| 3 | #TECH-002 Limpieza HTMLs viejos dashboard | ❌ Cosmético (15 min) |
| 4 | Bloque I Mejoras menores (nota matutina + diseño emails) | ❌ Notificaciones |
| 5 | #FEAT-014 Cooldown post-loss mean reversion | ✅ Cambia veto bot |
| 6 | #TECH-003 Migrar `calculate_performance` a FIFO (cierra #TD-1) | ✅ Cambia cálculo decay |
| 7 | Wilder RSI smoothing (anteriormente diferido T-R sub-7) | ✅ Cambia señales |
| 8 | TIMESTAMPTZ migración (anteriormente diferido T-R sub-8) | ❌ Estructural DB |
| 9 | **gstack evaluation** (Garry Tan toolkit 28 slash commands) | ❌ Meta-tooling, evaluación. Para Claude Code, no Cowork |

**Caveats de timing:**
- Items 5/6/7 cambian comportamiento del bot. Si el período formal de observación ya arrancó esa semana, mejor esperar al cierre.
- Si el bot sigue en fase de "validación + ajustes" post-martes (sin período formal), entran como parte de los ajustes.
- Dashboard rework es el más grande del bloque (~30-50% del sprint, depende de complejidad LLC multi-rol).

---

## Tabla resumen — items activos

| ID | Título | Tipo | Prio | Status |
|---|---|---|---|---|
| #OPS-009 | Ejecutar script flags T-V/T-U (3 nuevas) + sentinel-start.bat | OPS | P0 | TODO (Roman, esta noche o mañana temprano) |
| #OPS-010 | Email viewers reapertura 2º período | OPS | P1 | TODO (Roman, martes) |
| #OPS-011 | Testing manual dashboard cuando vuelva del trabajo | OPS | P1 | TODO (Roman, martes noche) |
| #TD-26 | Validación Half-Kelly (research DONE, falta auditoría externa) | TECH-BLOCK | P0 | ⚠️ PARCIAL — research DONE, falta IA independiente |
| #ARCH-001 | Refactor patrón Broker (abstracción Alpaca para portabilidad IBKR) | ARCH | P2 | TODO finde |
| #TECH-002 | Limpieza HTMLs viejos dashboard | TECH-DRIFT | P3 | 🔄 EN CURSO (cleanup hoy) |
| #HE-2b | Transición ENTRY_READY→ACTIVE + MAE/MFE backfill desde price stream | FEAT-NICE | P2 | TODO finde |
| #FEAT-EquityResearch-real | Sub-3b: parsing 10-K/EDGAR + DCF computado (vs framework por prompt actual) | FEAT-NICE | P3 | TODO post-Fase 5 |
| Signals.rejection_reason | Persistir razón de descarte (cooldown/duplicate hoy solo en logs) | TECH-DRIFT | P2 | TODO finde |
| #HE-3 | Alpaca MCP conversacional (Roman instala desde Cowork app) | FEAT-NICE | P2 | TODO Roman |
| #HE-5 | Wealth Management plugin (Roman instala) | FEAT-NICE | P2 | TODO Roman |
| #TD-13 | API versionado `/api/v1/` (breaking frontend) | TECH-DRIFT | P2 | DIFERIDO (coordinar Design en sprint finde) |
| #DOC-005 | Revisión manual titulares The Ear período 1 | DOC | P1 | DIFERIDO (re-evaluar con data hybrid mode post-arranque) |
| TIMESTAMPTZ migración | Estructural DB (T-R sub-8 diferido) | TECH-DRIFT | P2 | TODO finde |
| gstack evaluation | Toolkit Garry Tan/YC (28 slash commands) — evaluar si suma | ARCH | P3 | TODO finde |
| **Hallazgos análisis P1 a monitorear** | Pending rate >65% S-1/S-4/S-5/S-6 + concentración SPY (7/9) + S-2 monopolio (55%) + distribución FinBERT post-arranque | OBS | P1 | Monitoreo período 2 |

---

## P0 — Crítico (gate Fase 5 live)

- **#OPS-009** Ejecutar script flags T-V/T-U (3 nuevas) + arrancar sentinel-start.bat (Roman, esta noche o mañana temprano).
- **#TD-26 Validación Half-Kelly** — research Cowork DONE (`docs/half_kelly_validation_analysis.md`). Falta auditoría externa formal pre-Fase 5 (IAs independientes).

---

## P1 — Importante (2º período o pre-Fase 5)

- **#OPS-010 Email viewers** — Roman manual martes anunciando reapertura 2º período.
- **#OPS-011 Testing manual dashboard** — Roman martes noche al volver del trabajo.
- **#DOC-005 Revisión titulares The Ear período 1** — DIFERIDO Cowork. Re-evaluar post-arranque con datos hybrid mode FinBERT.
- **Hallazgos análisis P1 a monitorear post-arranque:**
  - **Pending rate** en S-1/S-4/S-5/S-6 (>65% en período 1, limit prices estrictos).
  - **CorrelationGuard activity** (ahora persiste — esperar >10% señales con acción).
  - **S-2 monopolio** (55% de la actividad en período 1 — observar si se mantiene).
  - **Distribución FinBERT score** post-arranque para recalibrar threshold (plan en `docs/finbert_recalibration_plan.md`).
  - **Sharpe per-trade post-B.2** — verificar ningún Sentinel produce |Sharpe|>5.
  - **Cooldown post-loss activity** — esperar reducción del 27% wash sales observado en período 1.

---

## P2 — Robustez técnica (no bloquea fase live inicial)

- **#ARCH-001 Patrón Broker** (abstracción Alpaca, sprint finde).
- **#HE-2b** Transición ENTRY_READY→ACTIVE + MAE/MFE backfill (sprint finde).
- **Signals.rejection_reason** persistir razón de descarte (drift T-V, sprint finde).
- **#HE-3 Alpaca MCP** + **#HE-5 Wealth Management** — Roman instala desde Cowork app.
- **#TD-13** `/api/v1` prefix — DIFERIDO (breaking, coordinar Design en sprint finde).
- **TIMESTAMPTZ migración** (diferido T-R sub-8) — estructural DB, sprint finde.
- **dashboard #TD-18-21** — post-Dashboard rework v2.
- **Nota matutina** + **directrices diseño emails** (Bloque I sprint finde).

---

## P3 — Futuro (post-Fase 5)

- **#FEAT-EquityResearch-real (Sub-3b)** Parsing 10-K/EDGAR + DCF computado con datos reales (vs framework por prompt actual).
- **#FEAT-007b** Alternativa a FinBERT vía Claude Haiku API (~$3/mes). Mejor calidad de sentiment, cero infraestructura, sin PyTorch ni 840MB cache, ya conectado vía ANTHROPIC_API_KEY. Implementar como `SentimentAnalyzerClaude` con mismo interface (`score`/`batch_score`) — fallback automático a keyword si API falla. Plan B sin costo: VADER (pure Python <1MB). Evaluar después de T-W migración Hetzner — si FinBERT funciona OK en Linux, no urgente; si falla, este es el camino.
- **gstack evaluation** — Toolkit Garry Tan/YC (28 slash commands). Re-evaluar si suma en sprint finde.
- Leverage escalonado (1.25x condicionado).
- Risk budgeting jerárquico intra-Sentinel.
- Reactivar S-10 RegimeClassifier.
- #TM-3 Trailing stops por software.
- #HE-6 Riskfolio-Lib.
- #TD-25 Position dataclass (cosmético).

---

## Archivo DONE — Sprint 23-25 may (cierres recientes)

### Sprint 23-24 may (pushed a `origin/main`):
- **#H-4 Decimal completo** — `a022de0` + `917cad8` + `0ed87e4` + `3672a82` (4 módulos).
- **#H-5b** cache pop SELL filled — `6a427c5`.
- **#H-6/#H-6b** auto-reconcile CANCELLED/PENDING_NEW — sprint 23-may.
- **#GR-1/2/3/4** SL/TP bracket + ATR sizing + DD limits + cap 85% — sprint 23-24 may + `d73568f`.
- **#FEAT-008** Lista negra Universe Selector — `7f089a0`.
- **#FEAT-009** Trigger idle_timeout — sprint 23-may.
- **#OP-1** Backup automático DB — script + README.
- **Hardening XSS sentinel-data.js** + **#TD-17** — sprint 23-may.
- **§-markers** historian/api/email_service — sprint 23-may.
- **#HE-1 QuantStats** — `d57ffd7`.
- **#FASE2-NEW-6 validate-workspace.ps1** — `b04e752` + `fb90702`.
- **T-A/B/C** Hardening XSS parcial + gitignore + clean-git-locks — `ac55d40`.
- **BUENAS_PRACTICAS v2.5→v2.7** refuerzo §14.0.
- **EXP-001/#BUG-001** Sharpe sin anualizar B.2 — `67164a5`.
- **EXP-002** PF+RTD decay — `de4f029` + migración 014.
- **EXP-003** CorrelationGuard persistencia — `2bf79ec` + migración 013.

### Sprint 24-25 may (pusheados en `7727511`):
- **EXP-005/T-K** Modo Observador Fractional — `09dd71b` + `ad33843` + migración 015.
- **#FASE2-NEW-3/T-L** Marcadores § + índice — `0242eb2`.
- **#FEAT-010/T-M** Hardening XSS completo `sentinel-app.js` — `fddcbbe`.
- **EXP-004** Fractional real path Alpaca — **WONTFIX** (Alpaca/IBKR no soportan).
- **#OPS-004** Defender exclusion — Roman manual 24-may.
- **T-N Robustez Dev** — `734ada4` + `d57f5d6` + `2c19c2e` + `1ce3302` + `f56f174` (ruff fix) + `7080b8f`.
- **T-O Robustez The Ear + Observabilidad** — `13038c2` + `37ec6dd` + `93067d6` + `ce3480d`.
- **T-P Cobertura ≥95%** — 9/9 módulos a **100%**, suite 99→431, gate CI ≥95%.
- **T-Q rename S-2** — psql idempotente.
- **T-R TECHDEBT cleanup Bloque F** — 9 commits (`f271742` + `86c197e` + `2f4fc0b` + `82b6f45` + `15bd719` + `57a5b8f` + `1782da2` + `513a8f9` + `157f363`).
- **#TECH-001 → WONTFIX** (0 recurrencias .git/index post-Defender exclusion).
- Commit Cowork bundle 1 — `7727511`.

### Sprint 25 may (pusheados en `31f0304`):
- **T-S Bloque C Compliance + Slippage** — 5/5 cerrado (#ME-1 + #ME-4 + #CR-3 + #CR-1 + #CR-2). 14 commits Code + commit Cowork. Suite 489/489. 3 módulos nuevos al 100% (`simulated_costs`, `tax_lots`, `corporate_actions`). Cero migraciones SQL (on-the-fly).
- #TD-1 con caveat: motor FIFO en `tax_lots.py`. `calculate_performance` sigue zip ingenuo → seguimiento en #TECH-003.

### Sprint 25 may noche (pusheados en `d168559`, bundle push 2):
- **T-T Plugins externos Bloque E** — `78823da` cierre 3/3. Sub-1 #HE-2 (módulo `investment_thesis.py` 100% + insert IDEA en historian + migración 017 aplicada). Sub-2 #HE-4 (no aplica — fees ya cubiertos en T-S #CR-3). Sub-3 Equity Research framework integrado al `SYSTEM_PROMPT` de Universe Selector. Flag operacional `THESIS_TRACKING_ENABLED=true`.
- **T-U distilFinBERT (#FEAT-007)** — 6 commits `1005c83` → `e934338` cierre 6/6. Módulo `sentiment_analyzer.py` (ProsusAI/finbert, no yiyanghkust por incompat transformers 5.x) + migración 018 + integración The Ear hybrid mode + flag `THE_EAR_SENTIMENT_ENABLED` + plan calibración en `docs/finbert_recalibration_plan.md`. Suite 610→636. torch 2.9.1+cpu + transformers 5.9.0 instalados en venv del bot.
- **#TECH-004 fix tests dispatcher** — `c6ea32d`. Fixture autouse parchea `config.ATR_SIZING_ENABLED=False` para que tests sean independientes del .env. Suite 636/636 verde con .env actual (ATR=true).
- **T-V 3 cambios comportamiento** — 3 commits cierre 3/3:
  - `571f30c` Sub-2 #TECH-003 FIFO: `calculate_performance` usa `tax_lots.match_fifo` (cierra #TD-1). Sin flag (fix de bug). Parity-check 0/25 diff zip vs FIFO sobre DB real.
  - `b1bf88b` Sub-1 #FEAT-014 Cooldown post-loss: bloquea BUY si cierre con pérdida ±7d. Flag `COOLDOWN_POST_LOSS_ENABLED` default OFF.
  - `a5db770` Sub-3 Wilder RSI: smoothing correcto cuando flag `WILDER_RSI_ENABLED` activo (default OFF).
- **#BUG-002 CERRADO** — investigación read-only Code: 17 signals huérfanas TODAS del 27-abr, primer trade DB = 28-abr → artefacto histórico Dispatcher pre-fixes (Excepción 1 conocida). No es bug.
- Specs T-U / T-V / análisis cualitativo P1 / research FinBERT consolidadas en `docs/` (Roman Copy-Item).
- `.gitignore` ampliación defensiva (`backups/`, `**/backups/`, `**/.env.backup*`, `inventory_*`, `/investigacion_*.md`).
- Bundle push 2: `31f0304` → `d168559` (+21 commits, 20 Code + 1 Cowork).

### Trabajo Cowork DONE (en `docs/` listo para push):
- **#FASE2-NEW-5** Gate pre-live checklist — `docs/gate_pre_live_checklist.md`.
- **#TD-26 research** Half-Kelly validation — `docs/half_kelly_validation_analysis.md`.
- **Research FinBERT** — `docs/finbert_arquitectura_analysis.md`.
- **EXPERIMENTS + INCIDENT_PLAYBOOK + RATIONALE + FASE4_PLAN** — `docs/` (4 docs regenerados).
- **Spec TAREA T-U distilFinBERT** — `docs/TAREA_T-U_distilfinbert.md` (288 líneas).
- **Spec TAREA T-V cambios comportamiento** — `docs/TAREA_T-V_cambios_comportamiento.md` (~285 líneas).
- **Análisis cualitativo período 1** — `docs/analisis_cualitativo_periodo_1.md` (200 líneas).

---

## Pendiente Cowork (mantenimiento)

- **Commit Cowork** con BACKLOG actualizado + 2 docs outputs nuevos (T-U spec + análisis P1) cuando convenga (junto a próximo bundle o standalone).

---

*BACKLOG actualizado 2026-05-25 noche (post turno completo T-T + T-U + T-V + #TECH-004 + #BUG-002). T-S pusheado en `31f0304`. Resto local en HEAD `a5db770`, ahead 20. Bundle push 2 en curso. #FEAT-007 distilFinBERT integrado en hybrid mode. #BUG-002 cerrado como artefacto histórico (no es bug — primer día Dispatcher pre-fixes). #TECH-004 fix tests dispatcher cerrado. Estimaciones de ritmo: lo que originalmente proyecté en meses se está cerrando en días — recalibrar estimaciones futuras dividiendo por 2-3.*
