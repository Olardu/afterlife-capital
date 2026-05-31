#!/usr/bin/env bash
# backup_db.sh — Backup automático de la DB de producción ALC en ALC-P (Hetzner).
# Parte 1: pg_dump -Fc local + rotación 14d. Parte 2 (off-site R2): se activa SOLA
# cuando exista el remote rclone 'r2' (sin re-editar este script). pg_dump es
# READ-ONLY. Lo dispara alc-db-backup.timer (diario 01:00 UTC).
set -euo pipefail

APP=/home/sentinel/afterlife-capital/sentinel-v0.5
cd "$APP"

# DATABASE_URL (peer-socket) del .env, CRLF-safe.
DB_URL=$(grep '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '\r')
DEST="$APP/backups/auto"
LOG="$APP/logs/db_backup.log"
mkdir -p "$DEST" "$APP/logs"
TS=$(date -u +%Y%m%d_%H%M%S)
DUMP="$DEST/sentinel_${TS}.dump"

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$LOG"; }

log "pg_dump -> $DUMP"
pg_dump -Fc "$DB_URL" -f "$DUMP"
log "dump OK ($(stat -c%s "$DUMP") bytes)"

# Rotación local: borrar dumps de más de 14 días (backup diario => ~14 copias).
find "$DEST" -name 'sentinel_*.dump' -mtime +14 -delete
log "rotacion local: $(ls "$DEST"/sentinel_*.dump 2>/dev/null | wc -l) dump(s) restantes"

# Parte 2 (off-site Cloudflare R2): solo si el remote 'r2' está configurado.
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q '^r2:'; then
    if rclone copy "$DUMP" r2:alc-db-backups/ 2>>"$LOG"; then
        log "R2 upload OK -> r2:alc-db-backups/$(basename "$DUMP")"
        rclone delete --min-age 30d r2:alc-db-backups/ 2>>"$LOG" || log "WARN: retención R2 falló"
    else
        log "WARN: R2 upload falló (revisar rclone/creds)"
    fi
else
    log "R2 no configurado aún (Parte 2 pendiente) — solo backup local"
fi
log "backup completo"
