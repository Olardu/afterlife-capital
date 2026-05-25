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
| **#FEAT-007** | **distilFinBERT integration al The Ear (T-U)** | **FEAT-CORE** | **P0** | **⏳ TODO — spec lista, DEADLINE martes** |
| #OPS-009 | Restart api.py martes con 4 flags (incluido `THE_EAR_SENTIMENT_ENABLED=true`) | OPS | P0 | TODO (Roman) |
| #OPS-010 | Email viewers reapertura 2º período | OPS | P1 | TODO (Roman) |
| #OPS-011 | Testing manual dashboard al levantar | OPS | P1 | TODO (Roman) |
| #OPS-012 | Restart main.py pre-lunes 9:30 ET (activar heartbeat) | OPS | P0 | TODO (Roman) |
| #TD-26 | Validación Half-Kelly (research DONE, falta auditoría externa) | TECH-BLOCK | P0 | ⚠️ PARCIAL |
| #ARCH-001 | Refactor patrón Broker | ARCH | P2 | TODO |
| #FEAT-014 | Cooldown post-loss mean reversion (evita 27% wash sales de #CR-1) | FEAT-CORE | P1 | TODO |
| #TECH-003 | Migrar `calculate_performance` a motor FIFO de tax_lots (cierra #TD-1) | TECH-BLOCK | P2 | TODO |
| #TECH-002 | Limpieza HTMLs viejos dashboard (15 min) | TECH-DRIFT | P3 | TODO |
| #HE-2 / #HE-4 / Equity Research framework | T-T cerrado en `78823da` (DONE local, no push) | FEAT-CORE | P2 | ✅ DONE local |
| #HE-2b | Transición ENTRY_READY→ACTIVE + MAE/MFE backfill desde price stream | FEAT-NICE | P2 | TODO próximo finde |
| #FEAT-EquityResearch-real | Sub-3b: parsing 10-K/EDGAR + DCF computado + comparables ratios reales (vs framework por prompt actual) | FEAT-NICE | P3 | TODO post-Fase 5 |
| #HE-3 | Alpaca MCP conversacional (Roman instala) | FEAT-NICE | P2 | TODO Roman |
| #HE-5 | Wealth Management plugin (Roman instala) | FEAT-NICE | P2 | TODO Roman |
| #TD-13 | API versionado `/api/v1/` (breaking frontend) | TECH-DRIFT | P2 | DIFERIDO (coordinar Design) |
| #DOC-005 | Revisión manual titulares The Ear período 1 | DOC | P1 | DIFERIDO (Cowork, falta DB) |
| #BUG-002 | 17 signals huérfanas 27-abr (referida en análisis P1 §10) | BUG-FUNC | P1 | DIFERIDO (Cowork, falta DB) |
| **Hallazgos análisis P1** | Pending rate >65% en S-1/S-4/S-5/S-6 + concentración SPY (7/9) + S-2 monopolio (55%) | OBS | P1 | Monitoreo período 2 |

---

## P0 — Crítico (gate Fase 5 live)

- **#FEAT-007 distilFinBERT integration** — T-U planeada, spec lista, entra al martes con el bot. Decisión Roman 2026-05-25.
- **#TD-26 Validación Half-Kelly** — research Cowork DONE (`docs/half_kelly_validation_analysis.md`). Falta auditoría externa formal pre-Fase 5.
- **#FASE2-NEW-5 Gate pre-live checklist** — DONE en `docs/gate_pre_live_checklist.md` (160 líneas, 64 checkboxes).
- **#OPS-009** Restart `api.py` martes con `THE_EAR_SENTIMENT_ENABLED=true` + 3 flags previos.
- **#OPS-012** Restart `main.py` pre-lunes 9:30 ET (heartbeat).

---

## P1 — Importante (2º período o pre-Fase 5)

- **#FEAT-014 Cooldown post-loss** — insumo crítico: 27% disposals wash sales en #CR-1. Sin cooldown, bot re-entra rápido y difiere pérdidas masivamente con sizing real.
- **#DOC-005 Revisión titulares The Ear período 1** — DIFERIDO Cowork (falta DB). Re-evaluar post-arranque con datos hybrid mode.
- **#BUG-002 17 signals huérfanas** — DIFERIDO (falta DB). Nota: análisis cualitativo §10 marca acción si reaparece en período 2 (logging detallado).
- **#OPS-010 Email viewers** — Roman manual martes.
- **#OPS-011 Testing manual dashboard** — Roman martes.
- **Hallazgos análisis P1 a monitorear post-arranque:**
  - **Pending rate** en S-1/S-4/S-5/S-6 (>65% en período 1, sus limit prices son demasiado estrictos).
  - **CorrelationGuard activity** (ahora persiste — esperar >10% señales con acción).
  - **S-2 monopolio** (55% de la actividad en período 1 — observar si se mantiene).
  - **Distribución FinBERT score** post-arranque para recalibrar threshold.
  - **Sharpe per-trade post-B.2** — verificar ningún Sentinel produce |Sharpe|>5.

---

## P2 — Robustez técnica (no bloquea fase live inicial)

- **#ARCH-001 Patrón Broker** (abstracción Alpaca).
- **#TECH-003** Migrar `calculate_performance` a motor FIFO de `tax_lots.py` (cierra #TD-1 completamente).
- **#HE-2 / #HE-4 / Equity Research integration** — en curso en T-T.
- **#HE-3 Alpaca MCP** + **#HE-5 Wealth Management** — Roman instala desde Cowork app.
- **#TD-13** `/api/v1` prefix — DIFERIDO (breaking, coordinar Design).
- **Diferidos T-R** (Wilder smoothing RSI, TIMESTAMPTZ migración grande, dashboard #TD-18-21, dataclasses config) — post-período-2.
- **Nota matutina** estructurada (complemento The Ear).
- **Directrices diseño emails.**

---

## P3 — Futuro (post-Fase 5)

- Leverage escalonado (1.25x condicionado).
- Risk budgeting jerárquico intra-Sentinel.
- Reactivar S-10 RegimeClassifier.
- #TM-3 Trailing stops por software.
- #HE-6 Riskfolio-Lib.
- #TD-1 FIFO multi-ticker (cubierto por #TECH-003 indirectamente).
- #TD-25 Position dataclass (cosmético).
- **#TECH-002 Limpieza HTMLs viejos** dashboard (mejora stats GitHub).

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

### Sprint 25 may noche (DONE local, NO-push, ahead 10 sobre `31f0304`):
- **T-T Plugins externos Bloque E** — `78823da` cierre 3/3. Sub-1 #HE-2 (módulo `investment_thesis.py` 100% + insert IDEA en historian + migración 017 aplicada). Sub-2 #HE-4 (no aplica — fees ya cubiertos en T-S #CR-3). Sub-3 Equity Research framework integrado al `SYSTEM_PROMPT` de Universe Selector (no es invocación de skill — es framework pasado por prompt para que Claude lo aplique con su conocimiento intrínseco). Flag operacional martes: agregar `THESIS_TRACKING_ENABLED=true`.
- Specs T-U / T-V / análisis cualitativo P1 movidas de `outputs/` a `docs/` (Roman ejecutó Copy-Item).

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
