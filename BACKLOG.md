# BACKLOG — Afterlife Capital / Sentinel

> **Fuente única de verdad consolidada.** Reemplaza a `NEXT_ITERATION.md` y `TECHDEBT.md` (obsoletos). Cualquier nuevo item entra acá primero.

**Mantenedores:** Roman (decisiones) · Cowork (Roma — coordinación) · Code (ejecución del bot).

**Última actualización:** 2026-05-25 (post-T-Q + T-R parcial; sprint maratónico 23-25 may cerrado en su mayor parte).

---

## Convenciones

**Tipos:** `BUG-CRIT` / `BUG-FUNC` / `BUG-COSM` / `TECH-BLOCK` / `TECH-DRIFT` / `FEAT-CORE` / `FEAT-NICE` / `ARCH` / `EXP` / `OPS` / `DOC`.

**Prioridades:** `P0` bloqueante / `P1` próxima iteración / `P2` backlog cercano / `P3` futuro.

**Status:** `TODO` · `WIP` · `BLOCKED` · `DONE` (mover a `Archivo DONE`) · `WONTFIX` · `DIFERIDO`.

---

## Bloques activos / Pipeline

| ID bloque | Cubre items | Status | LOG entry |
|---|---|---|---|
| **T-N** Robustez de Desarrollo | #FASE2-NEW-1 + #FASE2-NEW-2 + #FASE2-NEW-4 (audit) + ruff fix | ✅ DONE local | `[04:35]` + `[05:30]` + ruff fix `f56f174` |
| **T-O** Robustez The Ear + Observabilidad | #TD-5 + #TD-6 + #OP-2 + #ME-3 | ✅ DONE local | `[04:40]` + `[06:30]` + sesión fresca completa |
| **T-P** Cobertura ≥95% módulos críticos | #FASE2-NEW-4 completo (9/9 módulos a **100%**) | ✅ DONE local | `[06:45]` + DONE 9/9 |
| **T-Q** UPDATE rename S-2 | #OPS-008 | ✅ DONE (drift: ya estaba aplicado, idempotente) | LOG sesión fresca |
| **T-R** TECHDEBT cleanup | Bloque F | ✅ DONE local (9/9 sub-commits, ahead 35) | LOG sesión fresca + DECISIONES + DONE |
| **Bloque G Cowork** | #FASE2-NEW-5 + #TD-26 research (DONE) · #DOC-005 + #BUG-002 (diferidos por falta DB) | ⚠️ PARCIAL — 2/4 items DONE en outputs/ | sin LOG entry separada |

**Pipeline próximo (Roman decide orden post-T-R):**
- **Bloque C — Compliance + Slippage:** #ME-1 + #CR-1 + #CR-2 + #CR-3 + #ME-4 (4-5 sesiones).
- **Bloque D — Patrón Broker:** #ARCH-001 (2-3 sesiones).
- **Bloque E — Plugins externos:** #HE-2 + #HE-3 + #HE-4 + #HE-5 + Equity Research (4-6 sesiones).
- **Bloque I — Mejoras menores:** Nota matutina + Directrices diseño emails (1-2 sesiones).
- **Bloque J — Futuro P3:** Leverage + risk budgeting + Reactivar S-10 + Trailing stops + Riskfolio-Lib (post-Fase 5).

**Afuera (NO se trabaja, 14 items):** #OPS-005 LLC + #OPS-006 Auditoría IAs + #FEAT-011 SMS/Telegram + #OPS-007 OAuth Meridian + #FEAT-007 FinBERT/distilFinBERT + #FEAT-012/013 Dashboard v2 + Paper-Live paralelo + #TM-1/4/5 + Multimercado + La Forja + Batching Universe Selector.

---

## Tabla resumen — items activos

| ID | Título | Tipo | Prio | Status |
|---|---|---|---|---|
| **#OPS-009** | Restart api.py martes con 4 flags | OPS | P0 | TODO (Roman) |
| **#OPS-010** | Email viewers reapertura 2º período | OPS | P1 | TODO (Roman) |
| **#OPS-011** | Testing manual dashboard al levantar | OPS | P1 | TODO (Roman) |
| **#OPS-012** | Restart main.py pre-lunes 9:30 ET (activar heartbeat) | OPS | P0 | TODO (Roman) |
| **T-R sub-3** | historian: is_warmup + DB_POOL + #TD-23 (incluye migración SQL) | TECH-BLOCK | P2 | BLOCKED por decisión Roman |
| **T-R sub-4** | config: property + load_dotenv guard (dataclasses WONTFIX) | TECH-DRIFT | P2 | BLOCKED por decisión Roman |
| **T-R sub-5** | correlation_guard: #TD-3 + #TD-4 (cambian contrato) | BUG-FUNC | P1 | BLOCKED por decisión Roman |
| **T-R sub-7** | sentinels: #TD-24 + Wilder smoothing (diferido post-período-2) | TECH-DRIFT | P2 | BLOCKED por decisión Roman |
| **T-R sub-8** | cross-cutting: TimedRotatingFileHandler + #TD-12 TIMESTAMPTZ (grande) + dashboard | TECH-BLOCK | P2 | BLOCKED por decisión Roman |
| **T-R sub-9** | regime + cosméticos: #TD-22 + off-by-one + #TECH-001 + #TD-25 | TECH-DRIFT | P3 | BLOCKED por decisión Roman |
| #ME-1 | Slippage tracking + ajuste paper→live | TECH-BLOCK | P0 | TODO |
| #CR-1 | Reportes fiscales (K-1) | OPS | P0 | TODO |
| #CR-3 | Fees realistas simulados | TECH-BLOCK | P0 | TODO |
| #TD-26 | Validación matemática Half-Kelly (research DONE, falta auditoría externa) | TECH-BLOCK | P0 | ⚠️ PARCIAL (research Cowork en `outputs/half_kelly_validation_analysis.md`) |
| #ARCH-001 | Refactor patrón Broker | ARCH | P2 | TODO |
| #TECH-001 | Bug git index recurrente | TECH-BLOCK | — | ✅ WONTFIX (0 recurrencias post-Defender exclusion en ~15 commits del sprint) |
| #ME-4 | Costo Claude API per Sentinel | TECH-BLOCK | P2 | TODO |
| #CR-2 | Splits y dividendos | TECH-BLOCK | P2 | TODO |
| #HE-2 | Investment Thesis Tracking | FEAT-CORE | P2 | TODO |
| #HE-3 | Alpaca MCP conversacional | FEAT-NICE | P2 | TODO |
| #HE-4 | Backtesting framework | FEAT-CORE | P2 | TODO |
| #HE-5 | Wealth Management plugin | FEAT-NICE | P2 | TODO |
| #TD-13 | API versionado `/api/v1/` (breaking frontend) | TECH-DRIFT | P2 | DIFERIDO (coordinar Design) |
| #DOC-005 | Revisión manual titulares The Ear período 1 | DOC | P1 | DIFERIDO (Cowork, falta acceso DB) |
| #BUG-002 | 17 signals huérfanas 27-abr investigación | BUG-FUNC | P1 | DIFERIDO (Cowork, falta acceso DB) |

---

## P0 — Crítico (gate Fase 5 live)

- **#ME-1 Slippage tracking** — `trades.slippage` existe pero no se usa en métricas. Sin esto Sharpe paper > Sharpe live siempre.
- **#CR-1 Reportes fiscales (wash sales + K-1)** — para fase live con dinero real distribuido entre socios.
- **#CR-3 Fees realistas simulados** — SEC + FINRA TAF + exchange fees para que Sharpe paper sea representativo del live.
- **#TD-26 Validación Half-Kelly** — research Cowork hecho (`outputs/half_kelly_validation_analysis.md`). Falta auditoría externa formal pre-Fase 5.
- **#FASE2-NEW-5 Gate pre-live checklist** — DONE en `outputs/gate_pre_live_checklist.md` (160 líneas, 64 checkboxes).
- **#OPS-009 Restart api.py martes** — Roman manual.
- **#OPS-012 Restart main.py pre-lunes 9:30 ET** — activar heartbeat (precondición #OP-2 cumplida).

---

## P1 — Importante (2º período o pre-Fase 5)

- **T-R sub-5 correlation_guard #TD-3 + #TD-4** — cambia contrato (BLOCKED por decisión Roman).
- **#DOC-005 Revisión titulares The Ear período 1** — DIFERIDO Cowork (falta DB).
- **#BUG-002 17 signals huérfanas 27-abr** — DIFERIDO (falta DB).
- **#OPS-010 Email viewers reapertura** — Roman manual.
- **#OPS-011 Testing manual dashboard al arrancar** — Roman manual (caveat T-M).

---

## P2 — Robustez técnica (no bloquea fase live inicial)

- **#ARCH-001 Patrón Broker** (abstracción Alpaca).
- **#TECH-001 Bug git index recurrente** (verificar si Defender exclusion lo mitigó completamente).
- **T-R sub-3 historian** (BLOCKED por decisión migración SQL).
- **T-R sub-4 config** (BLOCKED).
- **T-R sub-7 sentinels** (BLOCKED — Wilder diferido).
- **T-R sub-8 cross-cutting** (BLOCKED — TIMESTAMPTZ migración grande + dashboard Design).
- **#ME-4 Costo Claude API per Sentinel.**
- **#CR-2 Splits/dividendos.**
- **#HE-2/3/4/5** plugins externos.
- **#TD-13 `/api/v1` prefix** — DIFERIDO (breaking, coordinar Design).
- **Nota matutina** estructurada (complemento The Ear).
- **Directrices diseño emails.**

---

## P3 — Futuro (post-Fase 5)

- Leverage escalonado (1.25x condicionado).
- Risk budgeting jerárquico intra-Sentinel.
- Reactivar S-10 RegimeClassifier.
- #TM-3 Trailing stops por software.
- #HE-6 Riskfolio-Lib.
- #TD-1 FIFO multi-ticker (bug menor re-caracterizado).
- T-R sub-9 cosméticos (#TD-25 dataclass + #TD-22 dead code + off-by-one).

---

## Archivo DONE — Sprint 23-25 may (cierres recientes)

### Sprint 23-24 may (pushed a `origin/main=0242eb2`):
- **#H-4 Decimal completo** — `a022de0` + `917cad8` + `0ed87e4` + `3672a82` (4 módulos).
- **#H-5b** cache pop SELL filled — `6a427c5`.
- **#H-6/#H-6b** auto-reconcile CANCELLED/PENDING_NEW — sprint 23-may.
- **#GR-1/2/3/4** SL/TP bracket + ATR sizing + DD limits + cap 85% — sprint 23-24 may + `d73568f`.
- **#FEAT-008** Lista negra Universe Selector — `7f089a0`.
- **#FEAT-009** Trigger idle_timeout — sprint 23-may.
- **#OP-1** Backup automático DB — `scripts/backup_db.ps1` + README.
- **Hardening XSS sentinel-data.js** + **#TD-17** localStorage whitelist — sprint 23-may.
- **§-markers** historian/api/email_service — sprint 23-may.
- **#HE-1** QuantStats — `d57ffd7`.
- **#FASE2-NEW-6** validate-workspace.ps1 — `b04e752` + `fb90702`.
- **T-A/B/C** Hardening XSS parcial sentinel-app.js + gitignore + clean-git-locks — `ac55d40`.
- **BUENAS_PRACTICAS v2.5→v2.7** refuerzo §14.0.
- **EXP-001/#BUG-001** Sharpe sin anualizar B.2 — `67164a5`.
- **EXP-002** PF+RTD decay Opción C — `de4f029` + migración 014.
- **EXP-003** CorrelationGuard persistencia — `2bf79ec` + migración 013.

### Sprint 24-25 may (LOCAL ahead 32+ sobre `origin/main=0242eb2`):
- **EXP-005/T-K** Modo Observador Fractional — `09dd71b` + `ad33843` + migración 015.
- **#FASE2-NEW-3/T-L** marcadores § main + sentinels + universe_selector — `0242eb2` (pusheado).
- **#FEAT-010/T-M** Hardening XSS sentinel-app.js completo — `fddcbbe` (LOCAL).
- **EXP-004** Fractional real path Alpaca — **WONTFIX** (Alpaca/IBKR no soportan).
- **#OPS-004** Excluir repo de Windows Defender — Roman manual 24-may.
- **T-N Robustez Dev** — `734ada4` + `d57f5d6` + `2c19c2e` + `1ce3302` + `f56f174` (ruff fix) + `7080b8f` (doc).
- **T-O Robustez The Ear** — `13038c2` + `37ec6dd` + `93067d6` + `ce3480d` (#TD-5 + #TD-6 + #OP-2 + #ME-3).
- **T-P Cobertura ≥95%** — `e5aa079` + `316ee4d` + `371a044` + 5 commits adicionales (9/9 módulos a **100%**, gate CI ≥95% activo, suite 99→431).
- **T-Q rename S-2** — psql idempotente (ya estaba aplicado).
- **T-R parcial 3/9** — `f271742` sub-1 api + `86c197e` sub-2 dispatcher + `2f4fc0b` sub-6 main. 6 sub-commits pendientes con decisiones Roman.

### Trabajo Cowork DONE (en `outputs/`, sin commit al repo):
- **#FASE2-NEW-5** Gate pre-live checklist — `outputs/gate_pre_live_checklist.md` (160 líneas, 64 checkboxes).
- **#TD-26 research** Half-Kelly validation analysis — `outputs/half_kelly_validation_analysis.md` (209 líneas).
- **4 docs regenerados** previos: EXPERIMENTS, INCIDENT_PLAYBOOK, RATIONALE, FASE4_PLAN.

---

## Pendiente Cowork (mantenimiento)

- **Commit Cowork** con BACKLOG + NEXT_ITERATION/TECHDEBT obsoletos + LOG + BUENAS_PRACTICAS v2.7 + 6 docs en `outputs/` → pausado por modelo NO-git de Roman.
- **Mover 6 docs `outputs/` al repo `docs/`** → mismo motivo, pausado.

---

*BACKLOG consolidado por Cowork 2026-05-25 post-T-R parcial. Sprint maratónico 23-25 may cerrado en su mayor parte: bot quedó con 431 tests, cobertura 99.83%, CI verde local, 9 módulos críticos a 100%, observabilidad activa (heartbeat configurado), shadow fractional listo para período 2. Quedan 6 sub-commits de T-R con decisiones Roman + items P0/P1 de Compliance/Slippage + bloques futuros C/D/E.*
