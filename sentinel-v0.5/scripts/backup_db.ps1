<#
.SYNOPSIS
    Backup automático de la base de datos Sentinel (PostgreSQL) con rotación. #OP-1.

.DESCRIPTION
    Ejecuta pg_dump (formato custom comprimido) de la DB Sentinel a
    <repo>/backups/db/YYYYMMDD_HHMMSS.dump.gz y aplica una política de rotación:
        - 7 daily  : los 7 backups diarios más recientes.
        - 4 weekly : backups de domingo, los 4 más recientes.
        - 12 monthly: backups del día 1 del mes, los 12 más recientes.
    Un backup puede contar para varias categorías; se conserva si entra en
    cualquiera. El resto se elimina.

    NUNCA hardcodea credenciales (repo público). Lee la contraseña de
    $env:PGPASSWORD. Si no está seteada, aborta con instrucción.

.PARAMETER DryRun
    No ejecuta pg_dump ni borra nada: solo muestra qué haría. Para smoke test.

.EXAMPLE
    $env:PGPASSWORD = '***'; .\backup_db.ps1
    $env:PGPASSWORD = '***'; .\backup_db.ps1 -DryRun

.NOTES
    El cron NO se programa acá — Roman lo agenda en Windows Task Scheduler
    (ver backups/db/README.md). Restore: también en el README.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$PgDump   = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe",
    [string]$DbName   = "sentinel",
    [string]$DbUser   = "postgres",
    [string]$DbHost   = "localhost",
    [int]   $DbPort   = 5432,
    [string]$BackupDir,
    [int]   $KeepDaily   = 7,
    [int]   $KeepWeekly  = 4,
    [int]   $KeepMonthly = 12
)

$ErrorActionPreference = "Stop"

# Directorio de backups: <repo>/backups/db (scripts/ vive en sentinel-v0.5/scripts).
if (-not $BackupDir) {
    $repoRoot  = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $BackupDir = Join-Path $repoRoot "backups\db"
}
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
}

$stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $BackupDir "$stamp.dump.gz"

function Write-Log($level, $msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] [$level] $msg"
}

# --- 1. Validaciones previas ---------------------------------------------------
if (-not $env:PGPASSWORD) {
    Write-Log "ERROR" "PGPASSWORD no está seteada en el entorno. Abortando (no se hardcodea la contraseña)."
    exit 1
}
if (-not (Test-Path $PgDump)) {
    Write-Log "ERROR" "pg_dump no encontrado en '$PgDump'. Pasá -PgDump con la ruta correcta."
    exit 1
}

# --- 2. Backup -----------------------------------------------------------------
if ($DryRun) {
    Write-Log "INFO" "[DRY-RUN] pg_dump -Fc $DbName@${DbHost}:$DbPort -> $outFile (gzip)"
} else {
    Write-Log "INFO" "Iniciando pg_dump de '$DbName' -> $outFile"
    try {
        # -Fc = formato custom (ya comprimido); lo recomprimimos a .gz para uniformidad
        # del pipeline de rotación y portabilidad. pg_dump escribe a stdout (-f -).
        & $PgDump -h $DbHost -p $DbPort -U $DbUser -d $DbName -Fc 2>$null |
            Set-Content -Path "$outFile.tmp" -Encoding Byte
        if ($LASTEXITCODE -ne 0) { throw "pg_dump devolvió código $LASTEXITCODE" }

        # Comprimir el .tmp a .gz
        $in  = [System.IO.File]::OpenRead("$outFile.tmp")
        $out = [System.IO.File]::Create($outFile)
        $gz  = New-Object System.IO.Compression.GzipStream($out, [System.IO.Compression.CompressionMode]::Compress)
        $in.CopyTo($gz); $gz.Close(); $out.Close(); $in.Close()
        Remove-Item "$outFile.tmp" -Force

        $sizeKb = [math]::Round((Get-Item $outFile).Length / 1KB, 1)
        Write-Log "INFO" "Backup OK: $outFile ($sizeKb KB)"
    } catch {
        Write-Log "ERROR" "Backup falló: $_"
        if (Test-Path "$outFile.tmp") { Remove-Item "$outFile.tmp" -Force }
        exit 1
    }
}

# --- 3. Rotación ---------------------------------------------------------------
$all = Get-ChildItem -Path $BackupDir -Filter "*.dump.gz" -ErrorAction SilentlyContinue |
       Sort-Object Name -Descending

# Parsear fecha del nombre YYYYMMDD_HHMMSS.dump.gz
function Get-BackupDate($file) {
    if ($file.Name -match '^(\d{8})_\d{6}\.dump\.gz$') {
        return [datetime]::ParseExact($Matches[1], 'yyyyMMdd', $null)
    }
    return $null
}

$keep = [System.Collections.Generic.HashSet[string]]::new()

# Daily: los N más recientes (cualquier día).
$all | Select-Object -First $KeepDaily | ForEach-Object { [void]$keep.Add($_.Name) }

# Weekly: domingos, los N más recientes.
$all | Where-Object { $d = Get-BackupDate $_; $d -and $d.DayOfWeek -eq 'Sunday' } |
    Select-Object -First $KeepWeekly | ForEach-Object { [void]$keep.Add($_.Name) }

# Monthly: día 1, los N más recientes.
$all | Where-Object { $d = Get-BackupDate $_; $d -and $d.Day -eq 1 } |
    Select-Object -First $KeepMonthly | ForEach-Object { [void]$keep.Add($_.Name) }

$toDelete = $all | Where-Object { -not $keep.Contains($_.Name) }
foreach ($f in $toDelete) {
    if ($DryRun) {
        Write-Log "INFO" "[DRY-RUN] eliminaría $($f.Name)"
    } else {
        Remove-Item $f.FullName -Force
        Write-Log "INFO" "Rotación: eliminado $($f.Name)"
    }
}

Write-Log "INFO" ("Rotación completa. Conservados: {0} | eliminados: {1}{2}" -f `
    $keep.Count, $toDelete.Count, $(if ($DryRun) { ' (dry-run)' } else { '' }))
