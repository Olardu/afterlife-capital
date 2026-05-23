# HANDOFF_TO_CODE.md

> **Canal de comunicación Cowork → Code.** Solo vive un handoff activo a la vez. Cuando se cierre (REPORT_FROM_CODE.md con estado COMPLETADO_LOCAL/PUSHEADO), Cowork lo archiva en `backups/YYYY-MM-DD/handoffs/` antes de escribir el siguiente. Si este archivo solo contiene la cabecera, no hay handoff pendiente.

---

# HANDOFF #1 — 2026-05-23

**De:** Cowork (Roma)
**Para:** Claude Code
**Estado:** PENDIENTE
**Tipo:** TAREA

## Objetivo

Configurar el protocolo Cowork↔Code en el `CLAUDE.md` global de Code añadiendo una sección nueva con las reglas de división de responsabilidades. Este es el primer experimento del flujo y a la vez la configuración fundacional: sin esto, Code no sabe qué archivos puede o no puede tocar cuando Cowork está activo.

## Contexto necesario (leer antes de actuar)

- Este archivo (`HANDOFF_TO_CODE.md`) — protocolo completo del flujo en la cabecera.
- `afterlife-capital/PROTOCOL_SESSION.md` — protocolo universal de inicio de sesión (referencia, no editar).
- `afterlife-capital/BUENAS_PRACTICAS_V2.md` §10.1, §10.2, §10.3 — reglas de backups, commits y line endings (referencia).
- Tu propio `CLAUDE.md` global (probable path: `C:\Users\roman\.claude\CLAUDE.md`) — el archivo que vas a editar. Si no está ahí, localizarlo con `where.exe` o `Get-ChildItem` desde PowerShell.

## Archivos a modificar

- `C:\Users\roman\.claude\CLAUDE.md` (o donde sea que esté tu archivo de instrucciones permanentes globales) — añadir una sección nueva al final con el contenido que va en la sección "Contenido exacto a pegar" más abajo.

## Restricciones

- [ ] Backup pre-edit del archivo en `backups/2026-05-23/CLAUDE.md.bak` dentro del repo `afterlife-capital` (aunque el archivo viva fuera del repo, el backup queda acá para trazabilidad).
- [ ] Validar markdown post-edit: archivo se abre sin errores, encabezados bien anidados, listas bien formadas.
- [ ] **NO pushear nada.** Este archivo no está en el repo de Sentinel. No requiere commit ni push.
- [ ] **NO modificar** otras secciones del archivo. Solo añadir la nueva al final.
- [ ] Conservar line endings originales del archivo (CRLF o LF — usar el mismo que ya tiene).

## Criterios de aceptación

- La sección nueva aparece al final del `CLAUDE.md` global, separada del contenido previo por `---`.
- El texto pegado coincide exactamente con el de "Contenido exacto a pegar" (verificable con diff o md5 sobre la sección).
- Backup catalogado existe en `backups/2026-05-23/`.
- El resto del archivo queda intacto (verificable comparando el resto del contenido contra el backup).

## Qué reportar en `REPORT_FROM_CODE.md`

- Path exacto donde estaba tu CLAUDE.md global.
- Ruta del backup creado.
- Listado de secciones del archivo antes y después (para confirmar que solo se añadió la nueva).
- Resultado de la validación de markdown.
- Cualquier hallazgo inesperado (ej. el archivo ya tenía una sección similar, conflicto con instrucciones previas, etc.).
- Confirmación explícita: "NO se pushó nada, NO se tocó DB ni Alpaca".

---

## Contenido exacto a pegar

> Pegar TODO el bloque siguiente al final del `CLAUDE.md` global, precedido por una línea `---` separadora. NO modificar el contenido — si algo te parece incorrecto, reportarlo en lugar de cambiarlo.

```markdown
---

## División Cowork↔Code (añadida 2026-05-23)

**Contexto:** Cowork (Roma — instancia de Claude en Cowork desktop) y Claude Code colaboran en proyectos donde ambos tienen acceso al filesystem pero memoria persistente separada. El protocolo handoff/report es el único canal de comunicación entre los dos.

### Reglas (proyecto Sentinel / afterlife-capital)

**1. División por tipo de trabajo:**

- **Cowork** piensa, escribe `.md` de proyecto, lee logs/DB/Alpaca, prueba via Claude in Chrome, conversa con Roman.
- **Code** edita código fuente (`.py`, `.js`, `.html`, `.css`), corre scripts bash, ejecuta tests, hace commits locales, pushea a GitHub **solo con luz verde de Cowork**, ejecuta `sync-drive.ps1` al cerrar sesión.

**2. Archivos que Code NO toca** (los mantiene Cowork):

- `CHANGELOG.md`, `TECHDEBT.md`, `NEXT_ITERATION.md`, `OBSERVATION_PERIOD.md` (raíz del proyecto)
- `BUENAS_PRACTICAS_V2.md`, `PROTOCOL_SESSION.md` (manuales universales)
- `dashboard/CHANGELOG-UI.md`
- Memorias persistentes de Cowork (otro filesystem, no accesibles a Code de todas formas)

Si Code identifica que uno de estos archivos requiere cambio, lo propone en el REPORT, no lo edita.

**3. Archivos que Code SIGUE manteniendo** (regla preexistente):

- `CLAUDE.md` del proyecto activo (ej. `sentinel-v0.5/CLAUDE.md`)
- Este `CLAUDE.md` global (instrucciones permanentes)
- Su propia `MEMORY.md` en `C:\Users\roman\.claude\projects\...\memory\MEMORY.md`

**4. Archivos compartidos** (cualquiera puede editar, coordinar via handoff):

- `API_REFERENCE.md`
- `PROJECT_MAP.md`

**5. Protocolo handoff/report:**

- Cowork escribe `HANDOFF_TO_CODE.md` (raíz del proyecto) con objetivo + contexto + restricciones + criterios de aceptación + qué reportar.
- Code lee, ejecuta, escribe `REPORT_FROM_CODE.md` con archivos tocados + paths de backups + validaciones + hash del commit local + hallazgos + acciones pendientes para Cowork/Roman.
- **Solo un handoff vivo a la vez.** Cuando se cierra, Cowork archiva ambos archivos en `backups/YYYY-MM-DD/handoffs/` antes de escribir el siguiente.
- **Push remoto requiere HANDOFF tipo `PUSH_APROBADO` de Cowork** con el hash exacto a pushear. Sin ese handoff, Code commitea localmente pero NO pushea, esperando validación de Cowork.

**6. DB y cuenta Alpaca:** ninguna de las dos instancias modifica autónomamente. Proponen SQL/comandos en el HANDOFF (Cowork) o REPORT (Code), Roman ejecuta.

**7. Memoria separada (CRÍTICO):** Cowork y Code **NO comparten** `MEMORY.md`. Cada uno tiene la suya en filesystems distintos. Si Cowork descubre algo importante (ej. un bug, una restricción nueva, contexto reciente del bot), debe escribirlo explícitamente en el HANDOFF — no asumir que Code lo sabrá leyendo memoria.

### Cuándo se aplica

Todo trabajo en proyectos donde Cowork está activo. Hoy: `afterlife-capital`. Otros proyectos sin Cowork siguen el flujo normal de Code sin restricciones adicionales.

### Cómo iniciar trabajo cuando Cowork está activo

1. Al recibir instrucción de trabajar en `afterlife-capital`, leer `HANDOFF_TO_CODE.md` en la raíz del proyecto.
2. Si hay un handoff PENDIENTE, ejecutar siguiendo las reglas de arriba.
3. Si no hay handoff o está COMPLETADO/ARCHIVADO, esperar instrucción explícita de Roman.
```

---

## Notas finales

- Este HANDOFF #1 es a la vez **prueba del protocolo y configuración del mismo**. Si todo sale bien, en próximas sesiones Code ya arrancará sabiendo las reglas.
- El próximo handoff probable (HANDOFF #2) será actualizar `API_REFERENCE.md` con los endpoints añadidos desde 5-may (Capital card, etc.) — primera tarea "real" del flujo.
- Si encontrás cualquier cosa inesperada o el path del CLAUDE.md global no coincide con el sugerido, parar y reportar antes de seguir.
