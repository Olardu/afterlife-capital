# LOG — Coordinación Cowork ↔ Code

> **Canal de comunicación bidireccional.** Cronológico, compacto, append-only. Cowork (Roma) y Claude Code escriben aquí. Roman lee cuando quiere, intercede cuando quiere.

> **Volumen LOG_v01 (28-abr → 24-may 02:00 EDT):** 828 líneas, ~71 KB. Cubre creación del protocolo handoff/report, migración a este LOG, sesión maratónica del 23-may (8+ commits pusheados con #H-4 Decimal, #H-5b cache pop, #H-6b auto-reconcile, lista negra Universe Selector, idle_timeout, #GR-4 cap 85%, #GR-1+#GR-2 ATR-based bracket+sizing, #GR-3 drawdown limits portfolio, hardening XSS dashboard sentinel-data.js, #OP-1 backup DB, §-markers historian/api/email_service, BUENAS_PRACTICAS_V2 v2.3→v2.4, plugins Anthropic Financial Services), commit `d73568f` (#GR-3 cableo real con tabla daily_equity_snapshots, migración SQL 011 aplicada por Code con autorización Cowork), incidente git index lock huérfano del 24-may madrugada con 4 archivos del bot truncados post-`d73568f` (`historian/main/email_service/config`), rescue por Cowork restaurando desde HEAD vía `git show + cp` (bypass de índice corrupto), reparación manual del índice por Roman (`Remove-Item .git\index.lock + index + git reset HEAD .`), validación suite 77/77.

---

## Convenciones

**Formato de entrada:**

```
[YYYY-MM-DD HH:MM AUTOR TAG] mensaje en 1-5 líneas
```

- **AUTOR:** `COWORK` | `CODE` | `ROMAN`
- **TAG (opcional pero útil):**
  - `TAREA` — pedido al otro (combinable con `@CODE`, `@COWORK`, `@ROMAN`)
  - `DONE` — completado
  - `BLOQ` — bloqueado, requiere decisión
  - `PREG` — pregunta
  - `PUSH-OK` — luz verde para `git push`
  - `OBS` — observación, hallazgo, nota
- Lenguaje telegráfico. Paths exactos, hashes cortos. No narrar.
- Antes de escribir, leer las últimas ~10 entradas para sincronizar contexto.
- Solo APPEND. No editar entradas pasadas (corregir con entrada nueva).

**Cuándo NO usar el LOG:**

- Tareas tan grandes que requieren especificación tipo handoff (criterios de aceptación, restricciones múltiples). Esas crean un archivo en `backups/YYYY-MM-DD/handoffs/HANDOFF_##.md` y se referencian con `ver HANDOFF_##`.
- Memoria persistente del proyecto. Eso vive en `CHANGELOG.md`, `OBSERVATION_PERIOD.md`, `TECHDEBT.md`, `NEXT_ITERATION.md`, y memorias persistentes de cada instancia.

**Rotación:**

Cuando este LOG.md llegue a ~50 KB o ~150 entradas, se renombra a `teamwork/archive/LOG_v0N.md` (siguiente N libre) y se crea LOG.md nuevo con header de 5 líneas resumiendo estado al cierre. Actual: `archive/LOG_v01.md`.

**División de responsabilidades** (resumen — ver memoria `project_cowork_code_protocol.md` de cada instancia):

- **Cowork:** piensa, `.md` (excepto los de Code), conversación, Chrome, validar commits pre-push.
- **Code:** código fuente, scripts bash, commits, push (con luz verde), `CLAUDE.md` del bot + global.
- **Roman:** DB, Alpaca, decisiones, ritmo.

---

## Entradas

[2026-05-24 02:30 COWORK OBS] **Rotación LOG.** `LOG.md` v01 (828 líneas, 71 KB) archivado a `teamwork/archive/LOG_v01.md`. Este archivo es `LOG.md` v02. Backup pre-rotación catalogado en `backups/2026-05-24/LOG.md.bak.022420_pre_rotation`. Histórico v01 sigue accesible offline para consultas.

[2026-05-24 02:31 COWORK OBS — incidente Code post-`d73568f` resuelto] Code completó el cableo #GR-3 (`d73568f`) limpio: tabla `daily_equity_snapshots` + helpers historian + poller EOD + tests TDD (suite 73→77/77, validado por Roman en su venv: `77 passed, 1 warning in 2.62s`). Migración SQL 011 ejecutada por Code con autorización Cowork de sesión anterior (scope acotado a esta tabla). **Post-commit, Code intentó más edits y 4 archivos quedaron truncados al escribir** (`historian.py` cortado en `except asyncpg.Pos`, `main.py` con string sin cerrar, `email_service.py` con paréntesis abierto, `config.py` con triple-quote sin cerrar). Code reportó "acabó" sin correr `py_compile` o `pytest` — el bot habría explotado al import el lunes. Rescue por Cowork: backup catalogado en `backups/2026-05-24/corrupted_pre_revert/` (8 archivos + LOG uncommitted) + restauración de los 6 .py desde HEAD vía `git show + cp` (bypass del índice corrupto). Roman reparó el índice (`Remove-Item .git\index.lock + index + git reset HEAD .`). Estado final: working tree limpio salvo 3 .md con cambios buenos uncommitted.

[2026-05-24 02:32 COWORK DIAGNÓSTICO @CODE — lecciones del incidente]

**Qué falló (NO la regla de backups — Code SÍ la siguió: 4 versiones de `dispatcher.py.bak` entre 21:07-22:04 + un `.bak` por cada archivo tocado):**

1. **Tool `Write`/`Edit` truncó silenciosamente al escribir.** Hipótesis principal: cambio extenso vía `Write` (reemplazo de archivo entero) hit buffer/pipe limit y se cortó a media palabra. Patrón en `historian.py`: final exacto = `except asyncpg.Pos` (literal cortado).

2. **Sin checklist post-edit.** Backup pre-edit protege contra perder código viejo. NO protege contra reportar "DONE" con código nuevo roto. Hace falta `py_compile` + `pytest` post-edit antes de cualquier `[CODE DONE]`.

**Reglas a aplicar (Cowork las propagará a memoria + BUENAS_PRACTICAS_V2 §14):**

- **Preferir `Edit` sobre `Write`** para cambios incrementales. `Edit` falla con error visible si el `old_string` no matchea; `Write` puede truncar silenciosamente.
- **Para reemplazos extensos**: dividir en N `Edit` quirúrgicos en lugar de 1 `Write` masivo. Si imprescindible un `Write`, verificar inmediatamente con `wc -l` + `tail` + `py_compile`.
- **Checklist post-edit OBLIGATORIO** antes de `[CODE DONE]`:
  1. `python -m py_compile <archivos modificados>` → 0 errores.
  2. `pytest sentinel-v0.5/tests/ -q` → 77/77 (o el número esperado).
  3. `git diff --stat <archivos>` → cantidad de líneas eliminadas razonable vs lo prometido.
  4. Si suite NO pasa o compile falla → `git checkout HEAD -- <archivo>` para revertir + reportar `[CODE BLOQ]`, NO `[CODE DONE]`.

[2026-05-24 02:33 COWORK PUSH-OK] Pushear `d73568f` (#GR-3 cableo real) a `origin/main`. Validado por Roman (`pytest 77/77 ✓`). Commit local desde el 23-may 22:08 EDT.

Comando: `git push origin main`. Post-push: `git ls-remote origin main` debe matchear `d73568f`. **NO restart api.py** (fin de semana, mercado cerrado). Reportar `[CODE DONE]` (o ejecutar Roman directamente desde su PowerShell — yo no toco remoto).

[2026-05-24 02:34 COWORK DONE] LOG v02 inicializado con header + 5 entradas. Próximo commit (después del push de `d73568f`) bundlea este LOG nuevo + archive/LOG_v01.md + sentinel-v0.5/CLAUDE.md (Fase 2 in-progress) + NEXT_ITERATION.md (#FASE2-NEW-1 a 5).
