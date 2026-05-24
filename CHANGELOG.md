# Changelog

All notable changes to Afterlife Capital — Sentinel v0.5 are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 2026-05-24 — Validación post-edit (v2.5 manual) + incidente Code + #GR-3 cableo real

### Added

- **`BUENAS_PRACTICAS_V2.md` v2.5** (commit `1261e8c`, autor Cowork): nuevo §14.0
  "Verificación técnica post-edit (gate OBLIGATORIO antes de DONE)" al inicio
  del checklist §14. 6 reglas duras: `py_compile`/`node --check`, `pytest`
  con número esperado, `git diff --stat` coherente vs prometido, `grep`
  verificación para `.md` post-Edit/Write, NUNCA reportar DONE si checklist
  falla (`[BLOQ]` en su lugar), preferir `Edit` sobre `Write` para
  incrementales + dividir `Write` masivos. Subsecciones §14.1 a 14.7
  renumeradas (antes negritas sueltas, ahora headers numerados). Incluye
  precedente literal del incidente Code 24-may como evidencia histórica.
- **`db/011_create_daily_equity_snapshots.sql`** (commit `d73568f`):
  migración nueva, tabla `daily_equity_snapshots` con `UNIQUE(owner_id, snapshot_date)`,
  `equity_open/close`, `peak_to_date` running via `GREATEST` en `ON CONFLICT`.
  **Aplicada a la DB** por Code con autorización Cowork (scope acotado).
  DDL idempotente también en `historian.connect()` como red de seguridad.
- **`historian.record_daily_equity_snapshot`** + `has_equity_snapshot_today` +
  `get_drawdown_equities` (day_open / week_ago 5 días hábiles / peak MAX).
- **`main._daily_equity_snapshot_poller`**: corre 1×/día post-close ET (≥16:05),
  idempotente, cancelación limpia en shutdown. #GR-3 ahora funcional end-to-end.
- **`tests/test_daily_equity_snapshots.py`**: 4 casos TDD. Suite 73 → **77/77**.
- **`teamwork/archive/LOG_v01.md`** (commit `13f2052`): rotación del LOG v01
  (828 líneas, ~71 KB) según protocolo. LOG v02 nuevo con header de 5 líneas
  resumiendo v01 + lecciones del incidente.
- **Memoria Cowork `feedback_post_edit_validation_obligatoria.md`**: regla
  durable de validación post-edit (origina la sección §14.0 del manual).

### Changed

- **`sentinel-v0.5/CLAUDE.md`** (commit `13f2052`): contexto Fase 2 in-progress
  con commits H-4/H-5b/H-6b/GR-* pusheados al cierre v01 del LOG.
- **`NEXT_ITERATION.md`** (commit `13f2052`): items #FASE2-NEW-1 a 5 derivados
  de la sesión 23-may (enforcement pre-commit, requirements pin `==`,
  marcadores § en archivos >500 LOC, cobertura paths críticos, gate pre-live).
- **`dispatcher._get_drawdown_equities`** (commit `d73568f`): reemplaza stub
  fail-safe → current de Alpaca en vivo + refs a la tabla nueva.

### Fixed

- **Índice git corrupto + `.git/index.lock` huérfano** (incidente 24-may
  madrugada): bug recurrente — 3er incidente del mismo patrón (previos
  13-may y 24-may madrugada). Reparado manualmente por Roman vía
  `Remove-Item .git\index.lock + index + git reset HEAD`. Sandbox Cowork
  NO puede limpiar el lock (`Operation not permitted`).
- **4 archivos del bot truncados post-`d73568f`** (`historian.py`/`main.py`/
  `email_service.py`/`config.py` con `SyntaxError`): Code completó limpio
  el commit `d73568f` (cableo #GR-3) y reportó "acabó". Post-commit intentó
  más edits y el tool `Write`/`Edit` truncó silenciosamente al escribir
  (`historian.py` cortado en `except asyncpg.Pos`). Code NO corrió
  `py_compile`/`pytest` y reportó DONE. Detección por Cowork al inspeccionar
  working tree post-rescate del índice. **Rescue:** backup catalogado de los
  corruptos en `backups/2026-05-24/corrupted_pre_revert/` (8 archivos + LOG
  uncommitted), restauración de los 6 .py desde HEAD vía `git show + cp`
  (bypass del índice corrupto). Suite vuelve a 77/77.

### Decisions

- **Permiso Code para ejecutar DB con scope acotado**: aplicado por primera
  vez en migración 011 (autorización Cowork sesión anterior). Aplica solo a
  DB (NO a Alpaca — sigue manual via dashboard por fiscal/legal). Documentado
  en memoria `feedback_no_autonomous_db_or_account_changes.md`.

### Notes

- **`d73568f` + `13f2052` + `1261e8c` pusheados** a `github.com/Olardu/afterlife-capital`
  (`origin/main` = `1261e8c` al cierre de esta entrada).
- **Pendiente para martes 26-may pre-apertura:** restart `api.py` (toma fix
  #H-5b + scheduler off + nuevo poller EOD), decisión sobre activar flags
  `ATR_SIZING_ENABLED` y `PORTFOLIO_DD_LIMITS_ENABLED` (hoy `False` default),
  `UPDATE sentinels SET name='S-2 RSI Fast Reversion'` (rename Mantis).

---

## Post-mortem T1 — 17 signals huérfanas del 2026-04-27

**Síntoma:** 17 signals registradas en tabla `signals` el 27-abr nunca llegaron
al dispatcher; quedaron sin trade asociado. Detectado en auditoría del 23-may.

**Causa raíz:** bug VARCHAR(10) en columna `ticker` de `signals` previo al
**FIX-005** (commit pre-28-abr). Tickers con símbolo >10 caracteres (típico en
ETFs leveraged / tickers extendidos del Universe Selector) truncaban
silenciosamente al INSERT, generando mismatch con la lookup posterior del
dispatcher por `signals.ticker`. Sin match → signal huérfana, sin trade.

**Resolución:** **FIX-005** (migración `005_fix_trades_status_length.sql` +
extensión ticker a VARCHAR(50), 28-abr). El bug no reaparece desde entonces
(verificado: 0 signals huérfanas en período 28-abr → 23-may).

**Lecciones aplicadas:**

- **`BUENAS_PRACTICAS_V2 §8.6`** (paths críticos): tests TDD pre-live para
  cualquier path financiero. Una validación de length de ticker antes del
  INSERT habría cazado el bug.
- **`BUENAS_PRACTICAS_V2 §15`** (Automatización): pre-commit con linters
  detectaría `VARCHAR(10)` como sospechoso en migraciones nuevas (regla
  configurable: longitud mínima para campos identificadores de mercado).
- **`BUENAS_PRACTICAS_V2 §14.0`** (post-edit, nuevo): `pytest` post-edit
  habría detectado la query del dispatcher fallando con tickers truncados.

**Acción residual:** las 17 signals huérfanas del 27-abr **permanecen en DB
como artefacto histórico**. Sin valor para reconstruir trades (faltan los
dispatches asociados). **NO eliminar** — sirven como evidencia del bug para
auditorías futuras y como ejemplo de "fail silent" en sistemas time-sensitive.

---

## [Unreleased] — 2026-05-23 (tarde) — Migración al protocolo teamwork/LOG.md

### Added

- **`teamwork/LOG.md`** — canal bidireccional Cowork ↔ Code, cronológico, append-only,
  compacto (entradas tipo `[YYYY-MM-DD HH:MM AUTOR TAG] mensaje 1-5 líneas`).
  Reemplaza el protocolo handoff/report en raíz (que llegó a ~250 líneas por
  handoff y consumía muchos tokens). Roman lee/intercede cuando quiere.

### Changed

- **`HANDOFF_TO_CODE.md` y `REPORT_FROM_CODE.md` en raíz** vaciados a placeholders
  con puntero a `teamwork/LOG.md`. Mantenidos como compatibilidad para no
  confundir a quien busque el flujo viejo.

### Deprecated

- **Protocolo handoff/report en raíz.** Histórico de los 5 ciclos del 2026-05-23
  archivado en `backups/2026-05-23/handoffs/`. Para tareas grandes con
  especificación tipo handoff (criterios de aceptación, restricciones múltiples)
  se sigue usando un archivo en `backups/YYYY-MM-DD/handoffs/HANDOFF_##.md`
  referenciado desde el LOG.
- **`BUENAS_PRACTICAS.md` v1** (último update 6-may) — superado desde el 13-may
  por `BUENAS_PRACTICAS_V2.md` v2.x. Code lo manda a papelera de Windows en
  HANDOFF de migración (rescatable desde Explorer si hace falta).

### Decisions

- **NO mover** `BUENAS_PRACTICAS_V2.md` ni `PROTOCOL_SESSION.md` fuera del repo.
  Razón: `sentinel-v0.5/CLAUDE.md` + otras docs los referencian con paths
  relativos; moverlos rompería referencias. Hoy son "manuales universales que
  físicamente viven en afterlife-capital/". Cuando aparezca un segundo proyecto
  activo que también los use, reevaluamos.
- **Patrón forward para deletes:** mandar a papelera de Windows vía PowerShell,
  no `rm` permanente. Roman objetó el delete permanente como "feo".

### Notes

- Próxima entrada del LOG (post `PUSH-OK`) arranca Fase 1: snapshot del bot al
  23-may + instalar QuantStats (`#HE-1`) + reporte balance.
- Objetivo del fin de semana: v0.6 corriendo el martes (decidido por Roman).

---

## [Unreleased] — 2026-05-23 — Cierre anticipado del período de observación

### Closed

- **Período de observación protegida** (28-abr → 27-may planeado).
  Cerrado anticipadamente el **23-may** (26 días efectivos en lugar de 30).
- **Motivo (textual de Roman):** "La plataforma nunca funcionó como se tenía
  planeado, no todas las estrategias funcionaron, no se invirtió todo el
  capital que se disponía para eso, hubo errores que no se tuvieron
  presentes. Para evitar seguir acumulando datos incompletos, pero igual
  valiosos, y para aprovechar mi fin de semana largo, decidí mejor terminar
  acá y no esperar los 4 días que faltan."

### Caveats del período

Datos NO miden la versión final del diseño. Tres sub-períodos distintos:

- 28-abr → 07-may: dispatcher con allocation roto, fallback 5% plano.
- 08-may → 11-may: bugs descubiertos por Excepción 1 (TypeError + bucle Mantis).
- 12-may → 23-may: allocation OK pero sizing trivial (qty=1, utilización ~3-5%
  del equity), bug #H-5b reapareció 2 veces (SPY 11-may, QQQ 15-may).

### Restricciones LEVANTADAS

A partir del 23-may, todas las reglas "❌ NO PERMITIDO" de OBSERVATION_PERIOD.md
dejan de aplicar. El plan post-observación (6 fases) entra en vigor según
NEXT_ITERATION.md y memoria `project_sentinel_post_observation_plan.md`.

### Próximos pasos inmediatos

- HANDOFF #2 = TBD (pendiente decisión de Roman tras este cierre).
- Snapshot del estado del bot al 23-may vía Alpaca API.
- Code debe actualizar `sentinel-v0.5/CLAUDE.md` que aún dice "período hasta 27/05".
- Fase 1 del plan: balance del período con QuantStats + métricas por Sentinel.

### Notes

- **Esto NO es transición a live.** El bot sigue en paper durante Fases 1-4.
  Live conservador previsto para julio 2026 tras segundo período de observación.
- **El cierre NO reinicia el contador** porque ya cerró el período entero.
  Los datos del período son lo que son — el balance los analiza, los
  caveats los contextualizan.

---

## [Unreleased] — 2026-05-23 — Inicio del experimento Cowork↔Code (protocolo handoff/report)

### Added

- **`HANDOFF_TO_CODE.md`** en la raíz del proyecto. Canal Cowork → Code. Un solo
  handoff activo a la vez; cuando se cierra, Cowork lo archiva en
  `backups/YYYY-MM-DD/handoffs/` antes de escribir el siguiente.
- **`REPORT_FROM_CODE.md`** en la raíz del proyecto. Canal Code → Cowork. Code
  sobrescribe al completar un handoff con archivos tocados, validaciones, hash
  de commit local, hallazgos y pendientes para Cowork/Roman.

### Protocolo

- **División por tipo de trabajo:** Cowork piensa (planning, lectura, `.md`,
  prueba via Chrome). Code ejecuta (código fuente, scripts, commits, push,
  Drive sync).
- **Archivos que Code NO toca:** `CHANGELOG.md`, `TECHDEBT.md`,
  `NEXT_ITERATION.md`, `OBSERVATION_PERIOD.md`, `BUENAS_PRACTICAS_V2.md`,
  `PROTOCOL_SESSION.md`, `dashboard/CHANGELOG-UI.md`, memorias persistentes.
  Si necesita cambios, los propone en el REPORT.
- **Archivos que Code mantiene:** `sentinel-v0.5/CLAUDE.md`, su
  `CLAUDE.md` global, su `MEMORY.md` global.
- **Compartidos (coordinar via handoff):** `API_REFERENCE.md`, `PROJECT_MAP.md`.
- **Push remoto:** requiere HANDOFF tipo `PUSH_APROBADO` de Cowork con el
  hash exacto. Sin ese handoff, Code commitea localmente pero no pushea.
- **DB y cuenta Alpaca:** ninguna de las dos instancias modifica
  autónomamente. Roman ejecuta.
- **Memoria separada:** Cowork y Code NO comparten `MEMORY.md`. El HANDOFF
  es el único canal — Cowork debe escribir explícitamente el contexto que
  Code necesita.

### HANDOFF #1 — COMPLETADO 2026-05-23

- **Tarea:** añadir sección "División Cowork↔Code" al `CLAUDE.md` global de Code.
- **Resultado:** sección pegada al final del archivo, byte-a-byte idéntica
  al bloque del handoff (MD5 `2543ec63bd0084d9d85b7ad463be5ed8` validado
  por Cowork de forma independiente desde el repo).
- **Path real del CLAUDE.md global:** `C:\Users\roman\Nueva Ruta\CLAUDE.md`
  (no `C:\Users\roman\.claude\CLAUDE.md` como había sugerido el handoff).
  **Para próximos handoffs usar el path real.**
- **Backup pre-edit:** `backups/2026-05-23/CLAUDE.md.bak` (43 líneas,
  MD5 `74a425972eebaecc2b0f7fdeb34d8ed7`).
- **Archivos del handoff archivados:** `backups/2026-05-23/handoffs/HANDOFF_01.md`
  y `backups/2026-05-23/handoffs/REPORT_01.md`. `HANDOFF_TO_CODE.md` y
  `REPORT_FROM_CODE.md` en raíz volvieron a su estado de placeholder.
- **Sin push, sin DB, sin Alpaca** (el archivo editado vive fuera del repo Sentinel).
- **Estado del flujo:** protocolo Cowork↔Code validado en su primer ciclo.

### Observaciones del primer ciclo

- Cowork pidió path probable + permitió a Code "localizar y reportar".
  Code lo encontró por sí mismo y documentó la corrección. **Patrón a
  preservar:** Cowork sugiere paths probables pero deja margen, Code valida
  y reporta el real.
- Code reportó deuda de commits en el repo (varios `.md` modificados sin
  commitear, mayoría introducidos por Cowork hoy). **A resolver en próximo
  HANDOFF:** decidir si Cowork pide a Code que commitee los `.md` que
  mantiene Cowork, o si se acumulan y se commitean en bloque al cierre.

### Notes

- Experimento planeado originalmente para 2026-05-16 (ver memoria
  `project_saturday_audit_2026-05-16.md`) y diferido por la intervención
  del short QQQ. Se retoma hoy.
- Si HANDOFF #1 resulta bien, próximo handoff (#2) será actualizar
  `API_REFERENCE.md` con los endpoints añadidos desde el 5-may (Capital
  card de Excepción 1.2 entre otros) — cumple la regla #0 de
  `ENDPOINTS_BACKLOG.md` que requiere mantener API_REFERENCE al día.
- Si el flujo se valida con 2-3 ciclos exitosos, se formaliza como nueva
  sección §11.x en `BUENAS_PRACTICAS_V2.md` ("Coordinación entre instancias
  de IA").

---

## [Unreleased] — 2026-05-16 — Intervención manual: short QQQ accidental por bug #H-5b reaparición — FILL CONFIRMADO 2026-05-18

### Discovered

- **P&L del 15-may: -$84.64 (-0.08%)**, la mayor pérdida diaria de la semana. Detalle reconstruido vía Alpaca API (`/v2/account/activities/FILL`):
  - AMD -$19.81 (entry 14-may @ $449.26 por S-4 MACD+Volume, exit 15-may @ $429.45 con caída de -4.41% en el día).
  - NVDA -$7.13, TSLA -$6.74, QQQ -$6.36 (este último incluye el primer SELL legítimo del long del 13-may).
  - Resto +$2.17. Realizado total: -$37.87. Mark-to-market sobre posiciones aún abiertas al cierre: -$46.77.
- **Bug #H-5b reapareció en QQQ.** Logs `sentinel.dispatcher — Posiciones fantasma (local pero no en Alpaca)` el 15-may en {'IWM', 'TSLA', 'SPY'} confirmaron el patrón. Resultado: dos órdenes `sell_short` sobre QQQ (09:45:14 y 10:30:07) sin decisión del bot. **Posición actual QQQ -2 shares @ avg $708.48** que debe cerrarse manualmente (mismo patrón que SPY del 11-may).

### Manual Intervention (pendiente)

- Cierre manual del short QQQ -2 sh vía Alpaca Dashboard, lunes 18-may pre-apertura (con bot detenido para evitar race con el opening cross). Procedimiento completo en `backups/2026-05-16/manual_intervention_qqq_short_cleanup.md`. Mismo proceso que con SPY del 12-may.

### Documentation

- Nuevo archivo `backups/2026-05-16/manual_intervention_qqq_short_cleanup.md` con:
  - Análisis P&L del 15-may por símbolo.
  - Trazabilidad de los SELL fantasma de QQQ.
  - Plan de cierre manual.
  - Marca de datos para el balance del 27-may (excluir trades QQQ del 15-may 09:45:14 en adelante del análisis de performance del Sentinel responsable).
- `OBSERVATION_PERIOD.md` — agregar sección "Intervención manual 2026-05-16" en bloque de intervenciones registradas (mismo formato que 2026-05-11).

### Notes — lección sobre sandbox staleness

- Diagnóstico inicial en la sesión Cowork del 16-may concluyó erróneamente que el bot no había estado operando del 12-may al 16-may. Causa: el bash del sandbox veía un snapshot stale de `sentinel.log` (cortado el 12-may 20:04). Las herramientas Read/Grep que sí leen el archivo real revelaron 22,082 líneas con actividad continua del bot. **Corrección documentada en `backups/2026-05-16/manual_intervention_qqq_short_cleanup.md` sección 6.**
- Implicación para futuras sesiones: cuando un análisis dependa de archivos escritos en tiempo real, cross-check con file-tools (Read/Grep) o con una llamada directa a la API antes de afirmar el estado del sistema. Anotar en `BUENAS_PRACTICAS_V2.md` cuando se haga la próxima revisión.

### Fill confirmado (2026-05-18)

- **Orden:** BUY 2 QQQ market, day. Order ID `47b0c814-8677-4bd3-9178-a4c570ae9e15`. Position intent `buy_to_close`.
- **Envío de Roman:** sábado 16-may 17:17 ET (after-hours, queued para opening cross).
- **Fill:** **lunes 18-may 09:30:41 ET** (13:30:41 UTC), 41 segundos post-apertura.
- **Filled avg price:** **$711.31**.
- **Realized P&L del cierre:** (708.48 − 711.31) × 2 = **−$5.66**. Costo total del bug #H-5b en QQQ (15-may + cierre 18-may): **−$12.02**.
- **Estado post-fill (Alpaca API):** posición QQQ = 0 (404 "position does not exist") ✅, equity $100,081.85, cash $99,199.61, short market value $0, long market value $882.24.
- **Race condition detectada y mitigada:**
  - 09:30:34 — S-8 RSI Divergence emitió señal BUY QQQ @ $712.14 (post bullish div).
  - 09:30:36 — Dispatcher WARNING: `Posiciones no rastreadas (Alpaca pero no local): {'SPY','QQQ','XLU','XLV','TLT','AAPL','XLP','NVDA'}` — cache desync persistente (#H-5b).
  - 09:30:41 — Fill manual del BUY 2 @ $711.31.
  - 09:30:43 — Dispatcher: `Señal BUY QQQ omitida — ya hay posición abierta este cycle`. La guardrail anti-duplicado **previno** que el bot enviara un BUY 1 adicional sobre la posición recién cerrada.
- **Confirmación de intervención externa:** Grep sobre `sentinel.log` con `^2026-05-18.*Orden enviada.*QQQ BUY qty=2` → 0 matches. El fill no provino del dispatcher.
- **Conclusión técnica:** #H-5b sigue presente en el cache `dispatcher.open_positions` pero la guardrail "señal omitida — ya hay posición abierta" funcionó como red de seguridad. Documentar para fix definitivo post-27-may.
- **Estado del evento:** **CERRADO LIMPIAMENTE**. Sección 7 de `backups/2026-05-16/manual_intervention_qqq_short_cleanup.md` completada.

---

## [Unreleased] — 2026-05-13 — Excepción 1.2: Capital card en el dashboard

### Added

- **Nuevo endpoint `GET /api/account/capital`** (sentinel-v0.5/api.py). Read-only,
  formato `{ data, meta }` cumpliendo BUENAS_PRACTICAS_V2.md sección 6.2,
  responsabilidad única (capital total, capital invertido, day_pnl absoluto y
  porcentual sobre invertido y sobre equity).
- **Tarjeta "Capital card"** en dashboard/index.html debajo de la curva de
  Equity: 3 líneas con `Capital total`, `Invertido (% del equity)`, y
  `PnL s/ invertido ($ y %)`.
- **`loadCapitalMetrics()`** en dashboard/sentinel-data.js: fetch +
  parsing del formato `{ data, meta }` + render con fallback a `—` en error.
  Llamado desde `reloadFromAPI()`.
- **i18n keys** `cap_total`, `cap_invested`, `cap_pnl_invested` en ES, EN, JA, TH.

### Changed

- Cache-bust de sentinel-data.js y sentinel-i18n.js a `?v=20260513a`.

### Notes

- Registrado como **Excepción 1.2** en `OBSERVATION_PERIOD.md`. Cosmética
  del dashboard + endpoint read-only — permitido durante observación
  (PERMITIDO puntos 3 y 4).
- El endpoint viejo `/api/account/equity` queda intacto. Refactorizar a
  formato `{ data, meta }` queda como deuda técnica para Fase 2 post-27-may.
- **Activación:** requiere `sentinel-stop.bat` → 10s → `sentinel-start.bat`
  para que api.py cargue el endpoint nuevo. Refrescar dashboard con Ctrl+F5
  si el navegador cachea agresivamente.
- Backups en `backups/2026-05-13/`.

---

## [Unreleased] — 2026-05-11 — Intervención manual + hallazgo de sizing

### Manual Intervention

- **Cierre manual de short SPY accidental** (consecuencia de bug #H-5b cache desactualizado).
  Roman compró 4 shares SPY a market vía Alpaca Dashboard para netear posición a 0.
  Documentado en `backups/2026-05-11/manual_intervention_spy_short_cleanup.md` con
  trazabilidad completa para el balance del 27-may. Posición SPY (-4) → 0.
  **Fill confirmado 2026-05-12 09:31:32 ET** a $736.685 (4 sh). Cash post-fill:
  **$98,155.16** (de $101,157.69 pre-intervención). Equity: $100,168.01. Realized
  P&L del cierre: ~+$4.53 (gap-down al opening favoreció). Race condition con bot
  NO se materializó (parking_brake=True activo, sin emisiones del Dispatcher en el
  opening). Evento cerrado limpiamente.

### Discovered (NO se fixea durante observación)

- **Sizing del Dispatcher es trivial, no Half-Kelly real.** Post-fix de Excepción 1.1,
  los logs muestran `Capital asignado` operando correctamente (Mantis 23-24%, otro
  Sentinel 25%, resto al piso). Pero las órdenes siguen saliendo con qty=1 porque
  los 9 Sentinels emiten `qty=1.0` hardcoded y el Dispatcher hace `min(qty, max_qty)`.
  Utilización real del equity: 4.9% (vs 58-65% esperado con Half-Kelly real).
  Documentado en `OBSERVATION_PERIOD.md` como hallazgo del período. Fix encaja con
  #GR-2 (position sizing por ATR) del bloque post-27-may.

### Notes

- El período de observación actual (28-abr → 27-may) mide "qty=1 plano con allocation
  Sharpe-weighted no consumida", no "Half-Kelly real". Considerar al hacer balance.
- Bug #H-5b sigue activo: shorts accidentales pueden volver a aparecer hasta el
  fix post-27-may. Si reaparecen, repetir intervención manual.

---

## [Unreleased] — 2026-05-08 — Excepción 1 ampliada (dos bugs heredados)

### Fixed

- **Dispatcher: TypeError float += Decimal** — `dispatcher.allocate_capital()`
  mezclaba acumuladores `float` con `score["sharpe_ratio"]` que asyncpg devuelve
  como `decimal.Decimal`. Resultado: 21 errores hoy, `cycle_allocation = {}`
  cada ciclo, todos los Sentinels caen al fallback `MIN_CAPITAL_PER_SENTINEL=5%`.
  Fix: conversión explícita `float()` e `int()` al leer scores
  (`dispatcher.py` líneas 153-163). Cierra ticket histórico **#H-4**
  (último 🟠 ALTO pendiente del backlog) en este punto.

- **Universe Selector: bucle de rotación zombie** — `historian.get_sentinel_scores()`
  devolvía scores de tickers ya rotados (`is_active=FALSE`) porque no hacía
  JOIN con `sentinel_tickers`. El Universe Selector seguía viéndolos como
  "en decay" cada ciclo y disparaba rotaciones nuevas sobre el mismo old_ticker.
  Mantis (S-2) ejecutó **23 rotaciones en 6 horas** sobre TSLA y SPY ya rotados,
  costo ~$0.65 USD a Claude, acumulando 18 tickers nuevos. Fix: agregar
  `JOIN sentinel_tickers st ON ... WHERE st.is_active = TRUE` a
  `get_sentinel_scores()` (`historian.py` líneas 585-619). Filtra zombies sin
  destruir datos históricos.

### Changed

- **Limpieza de Mantis (DB)**: `sentinel_tickers` actualizado para mantener
  solo `NVDA` (estrella histórica), `XLU` (utilities, mean reversion para
  rsi_short, Ambiente 3 All Weather) y `TLT` (bonos largos, Ambiente 4)
  como `is_active=TRUE`. Los 18 tickers nuevos del bucle + TSLA + SPY pasan
  a `is_active=FALSE` sin borrar registros (preservamos auditoría).
- **Docstring de `allocate_capital`** y `get_sentinel_scores`: actualizadas
  para reflejar que el algoritmo es **Sharpe-weighted Half-Kelly** (no solo
  "Half-Kelly"), por precisión conceptual.

### Documentation

- `OBSERVATION_PERIOD.md`: ampliación de Excepción 1 documentando los dos
  bugs y la limpieza de Mantis. Marca de datos pre/post excepción-1.1.
  Contador del período NO se reinicia (mismo criterio que Excepción 1).
- `backups/2026-05-08/`: backups de archivos modificados, script de simulación
  (`test_fixes_simulation.py`) que reproduce el TypeError y verifica el fix,
  queries SQL de validación y limpieza, `DEPLOY_STEPS.md` con instrucciones.

### Deferred

- **Trigger `idle_timeout` para Universe Selector** — propuesta de rotar
  tickers sin actividad en X días. Cae en "cambiar lógica de agente" según
  `OBSERVATION_PERIOD.md`, queda para post-2026-05-27. Anotado en
  `NEXT_ITERATION.md`.

### Validation

- Simulación con datos sintéticos representativos
  (`backups/2026-05-08/test_fixes_simulation.py`):
  - Escenario A (estado actual) reproduce el TypeError exacto de logs.
  - Escenario D (ambos fixes) produce allocation Half-Kelly correcta:
    Mantis recibe 25% techo, qty NVDA pasa de 1 share (fallback bug) a
    ~208 shares (allocation real con NVDA $120).
- Sintaxis Python validada con `ast.parse()` en ambos archivos modificados.
- CRLF preservado (1682 CRLF, 0 LF puro en historian; 751 CRLF, 0 LF puro
  en dispatcher).

## [Unreleased] — 2026-04-25

### Changed
- **Dashboard reemplazado por integración del handoff oficial de Claude
  Design** sobre branch `feature/design-handoff-integration`.
  - HTML/CSS pixel-perfect del prototipo (`Sentinel Dashboard v2.html`).
  - Lógica de render (`sentinel-app.js`) tal cual del handoff.
  - i18n en 4 idiomas (`sentinel-i18n.js`) tal cual del handoff.
  - `sentinel-data.js` reescrito custom para conectar a `/api/*` con SSE,
    reemplazando el mock + tick loop original.

### Added
- `dashboard/sentinel-i18n.js`, `dashboard/sentinel-app.js` — copiados del handoff oficial.
- `dashboard/sentinel-data.js` — orquestador de fetch + SSE; mantiene contenido
  editorial fijo (citas Matrix/Cyberpunk, AGENTS, AGENT_ICONS) hardcoded
  porque no son datos de API.
- `dashboard/assets/favicon.svg` y `favicon-mono-cyan.svg`.
- `dashboard/HANDOFF_INTEGRATION.md` — tabla de mapeo handoff↔API + endpoints
  consumidos + limitaciones declaradas.
- `dashboard/README.md` — stack, estructura, cómo modificar cada sección,
  cómo agregar Sentinel/idioma, variables CSS, limitaciones.
- `CHANGELOG.md` — este archivo.
- `MERGE_REPORT.md` — reporte final de merge propuesto.

### Removed
- `design-handoff-temp/` — copia local del bundle del handoff. Borrada tras
  copiar archivos a `dashboard/`. (Era untracked, no afecta historia git.)

### Notes técnicas
- El tick loop mock del handoff (`setTimeout(tick, 2500)` en `sentinel-app.js`)
  se neutraliza interceptando `setTimeout` antes de que `app.js` cargue:
  `sentinel-data.js` reemplaza temporalmente `window.setTimeout` y descarta
  llamadas con `fn.name === 'tick'`. Los datos reales llegan solo por SSE.
- Persistencia de `lang`/`view`/`theme` en `localStorage` agregada por
  `sentinel-data.js` vía event delegation (sin tocar `sentinel-app.js`).
- Datos derivados o sintéticos (equity history, news titles, logs) están
  marcados con TODO en `HANDOFF_INTEGRATION.md` para futuras extensiones de
  la API.

### No tocado
- `sentinel-v0.5/api.py` — instrucción explícita.
- `dashboard/index1.html`, `dashboard/index2.html` — untracked, respetados.

---

## [0.5.0] — 2026-04-25 (anterior, en main)

### Added
- Backend FastAPI completo (`sentinel-v0.5/api.py`) con endpoints REST
  `/api/status`, `/api/sentinels`, `/api/trades`, `/api/macro`,
  `/api/performance`, `/api/report`, SSE en `/api/sse`, dashboard estático en `/`.
- Migración multi-ticker: tabla `sentinel_tickers` (relación N:M), refactor
  de `BaseSentinel` para operar múltiples tickers en paralelo, estado
  `last_signal` y opening ranges por ticker.
- 9 Sentinels operativos en DB con 3 tickers cada uno.
- Dashboard standalone HTML/CSS/JS vanilla con Chart.js CDN, 4 idiomas,
  toggle Cyberpunk/Sobrio (sustituido en este Unreleased por el handoff oficial).
- 9 estrategias implementadas: SMA Crossover, RSI Short, Bollinger Bounce,
  MACD+Volume, ORB, EMA Triple, VWAP Reversion, RSI Divergence, Bollinger Squeeze.

### Disabled
- `S-10 RegimeClassifier` desactivado (accuracy 0.3849 sobre 3 clases).

### Fixed
- `feed=DataFeed.IEX` faltante en 4 archivos (causaba 403 SIP en cuenta paper).

### Security
- `meridian/.claude/.credentials.json` purgado del Drive.
- `sync-drive.ps1` con `--delete-excluded` y patrones recursivos `**/`.

---

## [0.1.0] — 2026-04-22

### Added
- Landing page Afterlife Capital v2.
- Favicon SVG.
- Sentinel panel link.
- i18n ES/JA/TH sincronizado con estado v0.1.
