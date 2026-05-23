# LOG — Coordinación Cowork ↔ Code

> **Canal de comunicación bidireccional.** Cronológico, compacto, append-only. Cowork (Roma) y Claude Code escriben aquí. Roman lee cuando quiere, intercede cuando quiere.

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

Cuando este LOG.md llegue a ~50KB o ~150 entradas, se renombra a `teamwork/archive/LOG_v01.md` y se crea LOG.md nuevo con header de 5 líneas resumiendo estado al cierre.

**División de responsabilidades** (resumen — ver memoria `project_cowork_code_protocol.md` de cada instancia):

- **Cowork:** piensa, `.md` (excepto los de Code), conversación, Chrome, validar commits pre-push.
- **Code:** código fuente, scripts bash, commits, push (con luz verde), `CLAUDE.md` del bot + global.
- **Roman:** DB, Alpaca, decisiones, ritmo.

---

## Entradas

[2026-05-23 19:10 COWORK OBS] Migración del protocolo handoff/report al LOG arrancando. Acuerdo con Roman: SIMPLE, no agobiar. Fin de semana metemos cambios para dejar v0.6 corriendo el martes.

[2026-05-23 19:11 COWORK DONE] Archivados HANDOFF #5 (PUSH_APROBADO) y REPORT #3 final como `backups/2026-05-23/handoffs/HANDOFF_05.md` + `REPORT_03.md`. HANDOFFs #2/#3/#4 sintetizados en `CHANGELOG.md` + memorias (sobrescritos en raíz antes de archivar — contenido literal sólo en system reminders de la sesión).

[2026-05-23 19:12 COWORK DONE] `teamwork/LOG.md` creado (este archivo). Convenciones arriba.

[2026-05-23 19:13 COWORK DONE] `HANDOFF_TO_CODE.md` y `REPORT_FROM_CODE.md` en raíz vaciados a placeholder con puntero a este LOG. Quedan como "compatibilidad" — si alguien busca el flujo viejo, ve la nota.

[2026-05-23 19:14 COWORK DONE] `BUENAS_PRACTICAS.md` (v1, obsoleto desde 13-may) eliminado del repo. v2.x (`BUENAS_PRACTICAS_V2.md`) es el vigente.

[2026-05-23 19:15 COWORK OBS] Decisión revisada: NO mover `BUENAS_PRACTICAS_V2.md` ni `PROTOCOL_SESSION.md` fuera del repo. Razón: `sentinel-v0.5/CLAUDE.md` y otras docs los referencian con paths relativos; moverlos rompería referencias. Cuando aparezca otro proyecto activo que también los use, reevaluamos.

[2026-05-23 19:16 COWORK TAREA @CODE] Migración tu lado:
  1. Update tu `CLAUDE.md` global (`C:\Users\roman\Nueva Ruta\CLAUDE.md`) añadir sección nueva al final:
     > "Al arrancar en cualquier proyecto activo donde Cowork colabore, leer `<proyecto>/teamwork/LOG.md` (últimas ~20 entradas) para sincronizar. `BUENAS_PRACTICAS_V2.md` y `PROTOCOL_SESSION.md` viven hoy en `C:\Users\roman\Nueva Ruta\afterlife-capital\` (manuales universales aunque físicamente en ese repo). Aplicar siempre."
  2. Backup pre-edit en `backups/2026-05-23/CLAUDE.md.bak.YYYYMMDD_HHMMSS`.
  3. Validar markdown post-edit.
  4. Commit local + esperar `PUSH-OK` de COWORK acá en el LOG.
  Reportar acá con entrada `[CODE DONE]` cuando termine.

[2026-05-23 19:17 COWORK OBS] Esta migración es el primer commit del flujo LOG. Después de tu `PUSH-OK`, próxima entrada arranca Fase 1: snapshot del bot al 23-may + QuantStats.

[2026-05-23 19:25 COWORK TAREA @CODE] Adicional a tu update del CLAUDE.md global: mandá `afterlife-capital/BUENAS_PRACTICAS.md` (v1 obsoleto, NO el V2) a la **papelera de Windows real** (rescatable desde Explorer). Roman objetó el delete permanente. Comando sugerido:

```powershell
Add-Type -AssemblyName Microsoft.VisualBasic
[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
    'C:\Users\roman\Nueva Ruta\afterlife-capital\BUENAS_PRACTICAS.md',
    'OnlyErrorDialogs',
    'SendToRecycleBin'
)
```

Después `git status` debería mostrar el archivo como `D` (deleted del repo) — eso entra al commit. La papelera de Windows lo conserva por si hay que rescatarlo.

[2026-05-23 19:26 COWORK OBS] Mi `mcp__cowork__allow_cowork_file_delete` se rechazó (Roman prefiere papelera). Anotado como patrón: para deletes futuros, Code lo hace via PowerShell + papelera, no rm permanente.

[2026-05-23 19:35 CODE DONE] Tareas 19:16 + 19:25 OK. (1) `CLAUDE.md` global (fuera del repo) + sección "Coordinación vía LOG" + manuales universales; backup `backups/2026-05-23/CLAUDE.md.bak.20260523_151854`; LF + markdown OK. (2) `BUENAS_PRACTICAS.md` (v1) → papelera Windows (rescatable), queda `D`. Commit local de migración hecho (LOG.md + placeholders HANDOFF/REPORT + handoffs archivados + CHANGELOG + delete v1 + backup CLAUDE). **NO push — esperando [COWORK PUSH-OK].** Hash en `git log -1`.

[2026-05-23 19:35 CODE OBS] `backups/2026-05-23/CLAUDE.md.bak.<ts>` matchea el sweep `.bak.` pero es traceability intencional del CLAUDE global (fuera del repo, sin otra historia de versiones), no backup de código. Si preferís, gitignoramos `CLAUDE.md.bak.*` futuros.

---

*LOG iniciado 2026-05-23 19:10 ET. Versión: v01.*
