# HANDOFF_TO_CODE.md

> **Canal de comunicación Cowork → Code.** Solo vive un handoff activo a la vez. Cuando se cierre (REPORT_FROM_CODE.md con estado COMPLETADO_LOCAL/PUSHEADO), Cowork lo archiva en `backups/YYYY-MM-DD/handoffs/` antes de escribir el siguiente.

---

# HANDOFF #4 — 2026-05-23 — REHACER_COMMITS (no es PUSH_APROBADO)

**De:** Cowork (Roma)
**Para:** Claude Code
**Estado:** PENDIENTE
**Tipo:** REHACER_COMMITS — bloqueo de seguridad pre-push
**Continuación de:** REPORT #3 (3 commits locales)

## Por qué NO PUSH_APROBADO

Validé los 3 commits locales. Buen trabajo con el lock huérfano, line-endings y el rescate del `.env.bak`. **Pero el commit `5ba6fb4` incluye 120 archivos / 71K líneas y muchos no deberían ir a un repo público:**

- `sentinel-v0.5/backups/sentinel_2026-04-28_pre_inventory.dump` — DB dump nativo PostgreSQL.
- `sentinel-v0.5/inventory_2026-04-28.txt` (565 líneas) — inventario de DB con PII (emails de viewers, UUIDs, posiblemente datos de trades).
- `sentinel-v0.5/backups/inventory_*.sql` + `inventory_*.txt` (4 archivos) — queries con output de datos.
- `code-outputs/` (16 archivos, hasta 2700 líneas) — logs completos de sesiones de Claude Code.
- ~17 backups in-place (`dashboard/*.bak.*`, `dashboard/*.backup_*`, `dashboard/*.pre-redesign.html`, `sentinel-v0.5/*.bak.*`, `sentinel-v0.5/*.backup_*`) — copias enteras de api.py, email_service.py, historian.py, dispatcher.py, sentinel-app.js, sentinel-data.js.
- `panel-admin/panel-admin.zip` y `templetes-correo/templetes-correo.zip` (binarios sin auditar).
- En `backups/`: archivos `*.original`, `*.pre-ronda*`, `*.pre-fix*`, `*.pre-equity-card`, `*.with-cap-total` (copias enteras de archivos del proyecto).

**Confirmé que el repo es público** vía `curl -I https://github.com/Olardu/afterlife-capital` → HTTP 200 sin redirect a login.

Roman decidió: **rehacer commits limpios** antes de pushear.

## Receta — comandos exactos

### Paso 1 — Reset al base previo (preserva cambios en working tree)

```powershell
git reset --mixed 1183fa0
git status --short
# Esperado: todos los archivos quedan modificados/untracked, sin nada en staging.
```

### Paso 2 — Ampliar `.gitignore` y agregar `.gitattributes`

Sobrescribir `.gitignore` con este contenido completo (preserva lo existente + agrega los patrones nuevos):

```gitignore
# === Secretos y credenciales ===
client_secret_*.json
**/.env
**/.env.local
**/.env.production
**/.env.staging
**/.env.bak*
**/*.env.bak*

# === Entornos Python ===
**/venv/
**/.venv/
**/__pycache__/
**/*.pyc
**/*.pyo

# === Logs y bases de datos ===
**/logs/*.log
**/*.log
**/*.db
**/*.dump

# === Backups in-place: copias de archivos editados (NO van a git) ===
dashboard/*.bak
dashboard/*.bak.*
dashboard/*.backup_*
dashboard/*.pre-*.html
dashboard/*.pre-*.js
dashboard/*.pre-*.py
sentinel-v0.5/*.bak
sentinel-v0.5/*.bak.*
sentinel-v0.5/*.backup_*
sentinel-v0.5/*.pre-*.py
sentinel-v0.5/*.pre-*.js

# === Backups con código completo / dumps / inventarios (subcarpetas) ===
backups/**/*.original
backups/**/*.pre-ronda*
backups/**/*.pre-fix*
backups/**/*.pre-equity-card
backups/**/*.with-cap-total
backups/**/*.tar.gz
backups/**/api.py.*
backups/**/email_service.py.*
backups/**/historian.py.*
backups/**/dispatcher.py.*
backups/**/sentinel-app.js.*
backups/**/sentinel-data.js.*
backups/**/sentinel-i18n.js.*
backups/**/index.html.*
sentinel-v0.5/backups/*.tar.gz
sentinel-v0.5/backups/*.dump
sentinel-v0.5/backups/inventory_*
sentinel-v0.5/inventory_*.txt

# === Code outputs (logs de sesiones de Claude Code) ===
code-outputs/

# === Handoffs Design archivados (binarios sin auditar) ===
panel-admin/panel-admin.zip
templetes-correo/templetes-correo.zip
```

Y verificar que `.gitattributes` (creado en commit anterior) sigue presente con su contenido original.

### Paso 3 — Borrar del disco los archivos sensibles (opcional pero recomendado)

Antes de stagear, eliminar los archivos del disco para evitar que vuelvan a entrar accidentalmente. Si Roman prefiere conservarlos para auditoría local, saltar este paso (el `.gitignore` los protege igual).

```powershell
# Backups in-place dashboard
Remove-Item dashboard/sentinel-app.js.backup_2026-05-02, dashboard/sentinel-app.js.bak.20260507_equity_fix, dashboard/sentinel-data.js.backup_2026-05-02, dashboard/sentinel-data.js.bak.20260507_equity_fix, dashboard/sentinel-data.js.bak.20260507_sharpe_fix, dashboard/index.pre-redesign.html -ErrorAction SilentlyContinue

# Backups in-place sentinel-v0.5
Remove-Item sentinel-v0.5/api.py.backup_2026-05-02, sentinel-v0.5/api.py.bak.20260504, sentinel-v0.5/api.py.bak.20260505_013315, sentinel-v0.5/api.py.bak.20260507_report_fix, sentinel-v0.5/api.py.bak.pre_fix_rotation_query, sentinel-v0.5/dispatcher.py.bak.20260507_aggregation_fix, sentinel-v0.5/email_service.py.bak.20260504, sentinel-v0.5/email_service.py.bak.20260505_013315, sentinel-v0.5/email_service.py.bak.20260507_report_fix, sentinel-v0.5/email_service.py.bak.pre_fix_titles, sentinel-v0.5/historian.py.bak.20260507_scores_parciales -ErrorAction SilentlyContinue

# Inventario y dump DB
Remove-Item sentinel-v0.5/inventory_2026-04-28.txt -ErrorAction SilentlyContinue
# (El .dump y los .sql del inventario quedan en sentinel-v0.5/backups/, ya excluidos por .gitignore. Si Roman quiere borrarlos también, ejecutar Remove-Item sobre ellos.)

# Logs de output  
Remove-Item -Recurse code-outputs -ErrorAction SilentlyContinue
```

**Si Roman dice "mejor mantenerlos en disco para auditoría local"** — saltar este paso entero. El `.gitignore` igual los excluye de futuros commits.

### Paso 4 — Verificar staging limpio

```powershell
git status --short | Select-String -Pattern "(inventory|\.dump|\.bak\.|\.backup_|\.original|\.pre-(ronda|fix|equity-card)|code-outputs|\.tar\.gz|panel-admin\.zip|templetes-correo\.zip)"
# Esperado: SIN MATCHES.
```

Si hay matches, los archivos están en disco pero `.gitignore` los debería ignorar — verificá que `git status --short` los muestre como `??` (untracked) y no como `M` (modified). Si aparecen como `M`, hay que hacer `git rm --cached <archivo>` antes de seguir.

### Paso 5 — Commit 1 (Code): config de repo

```powershell
git add .gitignore .gitattributes
git commit -m "chore: line-endings (gitattributes) + .gitignore ampliado (backups, code-outputs, inventarios, dumps)" -m "" -m "Convención de line-endings: LF canónico en repo (* text=auto + *.sh eol=lf + binarios marcados)." -m "" -m ".gitignore ampliado para excluir:" -m "- Backups in-place (dashboard/*.bak.*, dashboard/*.backup_*, idem sentinel-v0.5/)" -m "- Copias de código en backups/ (*.original, *.pre-ronda*, *.pre-fix*, etc.)" -m "- DB dumps y inventarios (sentinel-v0.5/backups/*.dump, **/inventory_*.txt)" -m "- code-outputs/ (logs de sesiones Claude Code)" -m "- ZIPs binarios de handoffs Design archivados" -m "" -m "Decidido tras review pre-push (HANDOFF #4 del 2026-05-23) por riesgo de exposición en repo público."
```

### Paso 6 — Commit 2 (Cowork docs): solo los .md de Cowork del 2026-05-23

```powershell
git add CHANGELOG.md OBSERVATION_PERIOD.md HANDOFF_TO_CODE.md REPORT_FROM_CODE.md backups/2026-05-23/handoffs/HANDOFF_01.md backups/2026-05-23/handoffs/REPORT_01.md backups/2026-05-23/CLAUDE.md.bak

git commit --author="Cowork (Roma) <cowork@afterlifecapital.local>" -m "docs(cowork): cierre período observación + protocolo Cowork↔Code" -m "" -m "Sesión 2026-05-23. Cowork mantenedora de .md de docs no-bot:" -m "- CHANGELOG.md: cierre HANDOFF #1, cierre anticipado período observación, inicio protocolo Cowork↔Code" -m "- OBSERVATION_PERIOD.md: sección 'Cierre del período' (motivo textual de Roman + caveats + restricciones levantadas)" -m "- HANDOFF_TO_CODE.md + REPORT_FROM_CODE.md: archivos del protocolo handoff/report (deprecados al finalizar este ciclo a favor de teamwork/LOG.md)" -m "- backups/2026-05-23/handoffs/: HANDOFF_01 + REPORT_01 archivados (protocolo handoff/report ciclo 1)" -m "- backups/2026-05-23/CLAUDE.md.bak: backup pre-edit del CLAUDE.md global de Code"
```

### Paso 7 — Commit 3 (Code): todo el resto (consolidación backlog mayo + HANDOFF #2)

```powershell
git add -A
git status --short
# Verificar: solo cambios de código + docs no-Cowork. Sin sensibles (ver Paso 4).
git commit -m "chore: consolidación backlog mayo + cierre período observación (HANDOFF #2)" -m "" -m "Working tree acumuló cambios sin commitear desde 28-abr (último commit base: 1183fa0)." -m "Causa raíz identificada: .git/index.lock huérfano del 13-may bloqueó commits 10 días." -m "Este commit consolida todo el estado al cierre del 2026-05-23, excluidos los archivos sensibles cubiertos por .gitignore ampliado." -m "" -m "Trabajo previo incluido:" -m "- Excepción 1 (07-may): scores parciales + agregación dispatcher (historian, dispatcher, api)" -m "- Excepción 1.1 (08-may): TypeError float+=Decimal + JOIN sentinel_tickers + cleanup Mantis" -m "- Excepción 1.2 (13-may): Capital card endpoint /api/account/capital + tarjeta dashboard" -m "- Universe Selector improvements del período" -m "- Cambios dashboard, panel admin, assets, índices i18n" -m "- Updates de docs (TECHDEBT, DESIGN_CHANGES, MERGE_REPORT, AUDIT_FULL, dashboard/HANDOFF_INTEGRATION)" -m "- Migraciones db (003-010) ya aplicadas a producción" -m "- Updates utility modules (claude_client, crypto_utils, market_clock, regime_classifier, correlation_guard, main, adopt_orphan, reconcile_pending, restart_api, run_adopt)" -m "- Documentos backups/ aprobados (manual_intervention SPY/QQQ, audit sentinels, DEPLOY_STEPS, BUENAS_PRACTICAS_V2.pre-v2.2, scheduled task verifications)" -m "- Landing pages index.html / index1.html" -m "" -m "Trabajo de HANDOFF #2 (sesión 2026-05-23):" -m "- Email cierre período enviado a 5 viewers vía Resend (period_close en email_service.py)" -m "- Scheduler reporte diario desactivado vía flag DAILY_REPORT_ENABLED en config.py + guard en api.py" -m "- sentinel-v0.5/CLAUDE.md actualizado con cierre del período + plan 6 fases" -m "" -m "Excluidos por .gitignore ampliado:" -m "- DB dump + inventarios (sentinel-v0.5/inventory_*.txt + sentinel-v0.5/backups/inventory_* + sentinel-v0.5/backups/*.dump)" -m "- 17 backups in-place de código (dashboard/*.bak.*, *.backup_*, *.pre-redesign.html; sentinel-v0.5/*.bak.*, *.backup_*)" -m "- code-outputs/ (16 logs de sesión Claude Code)" -m "- 2 ZIPs binarios de handoffs Design" -m "- Copias de código en backups/ (.original, .pre-ronda*, .pre-fix*, .pre-equity-card, .with-cap-total)" -m "" -m "Compromiso forward: no acumular backlog sin commitear (regla del protocolo Cowork↔Code)."
```

### Paso 8 — Validación final

```powershell
git log --oneline -5
# Esperado: 3 commits nuevos + 1183fa0 + ...

git log -1 --format="%an <%ae>" HEAD~1
# Esperado: Cowork (Roma) <cowork@afterlifecapital.local>

git log -1 --format="%an <%ae>" HEAD
# Esperado: Roman Olarte <***REMOVED-EMAIL***> (o tu identidad git)

git log -1 --format="%an <%ae>" HEAD~2
# Esperado: Roman Olarte (el commit de gitignore/gitattributes)

git diff --stat HEAD~2 HEAD~1
# Esperado: solo .md de Cowork (+backups/2026-05-23/...)

git diff --stat HEAD~1 HEAD | head -20
# Esperado: código real, SIN ningún archivo sensible

# Verificación final de sensibles en los nuevos commits:
git log HEAD~3..HEAD --name-only --pretty=format: | sort -u | grep -E "(inventory_|\.dump$|\.bak\.|\.backup_|\.original$|\.pre-(ronda|fix|equity-card)|code-outputs|\.tar\.gz$|panel-admin\.zip$|templetes-correo\.zip$)"
# Esperado: SIN MATCHES.

git status
# Esperado: clean (excepto archivos nuevos no-trackeados que el .gitignore ya excluye).
```

## Restricciones

- [ ] **NO pushear todavía.** Esperar HANDOFF #5 PUSH_APROBADO de Cowork.
- [ ] **NO modificar contenido** de archivos del proyecto. Solo cambios son `.gitignore` (Paso 2) y posiblemente borrar archivos del disco (Paso 3, opcional).
- [ ] Si en Paso 4 (verificar staging) aparecen archivos sensibles, **parar y reportar**. Lo más probable es que `.gitignore` tenga un patrón mal escrito — Cowork lo corrige.
- [ ] Si en Paso 8 la verificación final muestra MATCHES de sensibles, **parar y reportar**. NO seguir.
- [ ] Conservar el commit `677eb6b` (normalización line-endings) que ya hiciste? **NO** — `git reset --mixed 1183fa0` lo deshace. La nueva versión del Paso 5 combina `.gitattributes` + `.gitignore` en un solo commit más completo. Tirar `677eb6b` está bien.

## Qué reportar en `REPORT_FROM_CODE.md`

- Outputs exactos de cada validación de Paso 8.
- Si decidiste borrar archivos del disco (Paso 3) o no.
- Listado de archivos en cada commit (`git show <hash> --name-only --pretty=format:`).
- Confirmaciones obligatorias estándar.
- Si encontraste algún archivo sensible adicional que mi inventario no listó, reportarlo (puede haber `.bak` o `.tmp` que se me hayan escapado).

## Notas finales

- Esta es la última iteración del protocolo handoff/report. Después del PUSH exitoso (HANDOFF #5), migramos a `teamwork/LOG.md`.
- También en esa migración: mover `BUENAS_PRACTICAS_V2.md` + `PROTOCOL_SESSION.md` de `afterlife-capital/` a `C:\Users\roman\Nueva Ruta\` (manuales universales), borrar `BUENAS_PRACTICAS.md` v1, actualizar `CLAUDE.md` global de Code con paths universales.
