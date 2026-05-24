# Backups de la base de datos Sentinel (#OP-1)

Backups automáticos de PostgreSQL con rotación. Los `.dump.gz` de esta carpeta
**no se versionan** (gitignored: `**/*.dump.gz`) — solo este README va a git.

## Script

`sentinel-v0.5/scripts/backup_db.ps1` — ejecuta `pg_dump` (formato custom) →
`backups/db/YYYYMMDD_HHMMSS.dump.gz` y rota:

- **7 daily** — los 7 más recientes.
- **4 weekly** — backups de domingo.
- **12 monthly** — backups del día 1 del mes.

Un backup se conserva si entra en cualquiera de las tres categorías.

## Uso manual

```powershell
# La contraseña NUNCA está en el script (repo público). Setearla antes:
$env:PGPASSWORD = '<password de postgres>'

# Backup real:
& "C:\Users\roman\Nueva Ruta\afterlife-capital\sentinel-v0.5\scripts\backup_db.ps1"

# Smoke test (no ejecuta pg_dump ni borra nada, solo muestra qué haría):
& "...\backup_db.ps1" -DryRun
```

Parámetros opcionales: `-PgDump`, `-DbName`, `-DbUser`, `-DbHost`, `-DbPort`,
`-BackupDir`, `-KeepDaily`, `-KeepWeekly`, `-KeepMonthly`.

## Programar el cron (Windows Task Scheduler) — lo hace Roman

El script **no** se auto-programa. Para correrlo a diario (ej. 02:00):

1. Abrir **Task Scheduler** → *Create Task*.
2. **General:** nombre `Sentinel DB Backup`; *Run whether user is logged on or not*.
3. **Triggers:** *Daily* a las 02:00.
4. **Actions:** *Start a program*
   - Program/script: `powershell.exe`
   - Argumentos:
     `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\roman\Nueva Ruta\afterlife-capital\sentinel-v0.5\scripts\backup_db.ps1"`
5. **Importante (contraseña):** el script lee `$env:PGPASSWORD`. Para una tarea
   desatendida, definir `PGPASSWORD` como variable de entorno **del sistema**
   (Panel de Control → Variables de entorno) o usar un `.pgpass` de PostgreSQL.
   No poner la contraseña en los argumentos de la tarea.

## Restore

```powershell
# 1. Descomprimir el .dump.gz elegido:
$gz  = "C:\...\backups\db\20260524_020000.dump.gz"
$out = $gz -replace '\.gz$',''
$in  = [System.IO.File]::OpenRead($gz)
$ou  = [System.IO.File]::Create($out)
$dz  = New-Object System.IO.Compression.GzipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
$dz.CopyTo($ou); $dz.Close(); $ou.Close(); $in.Close()

# 2. Restore con pg_restore (CUIDADO: --clean dropea objetos existentes).
$env:PGPASSWORD = '<password>'
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" `
    -h localhost -p 5432 -U postgres -d sentinel --clean --if-exists $out
```

> **Antes de un restore en producción:** confirmar que el bot (`main.py`) y la
> API (`api.py`) están detenidos para evitar escrituras concurrentes.

## Verificación de integridad

```powershell
# Listar el contenido de un dump sin restaurarlo:
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --list $out
```
