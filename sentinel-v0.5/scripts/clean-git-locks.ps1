<#
.SYNOPSIS
    Detecta y elimina .git/index.lock huerfano del repo.

.DESCRIPTION
    Bug recurrente: procesos git que crashean (o el sandbox de Cowork
    que no puede limpiar) dejan .git/index.lock huerfano, bloqueando
    add/commit/push. Este script lo detecta, verifica que no haya
    procesos git activos en el repo, y elimina el lock con prompt.

    Cierra el patron observado en BUENAS_PRACTICAS_V2 sec 15.1 (casos
    reales que motivan automatizacion).

    Uso:
      .\scripts\clean-git-locks.ps1            # con prompt
      .\scripts\clean-git-locks.ps1 -Force     # sin prompt

.EXAMPLE
    PS> cd "C:\Users\roman\Nueva Ruta\afterlife-capital"
    PS> .\sentinel-v0.5\scripts\clean-git-locks.ps1
#>

param(
    [switch]$Force
)

# Localizar repo root (subir directorios buscando .git)
$repoRoot = $PWD.Path
while ($repoRoot -and -not (Test-Path (Join-Path $repoRoot ".git"))) {
    $repoRoot = Split-Path $repoRoot -Parent
}
if (-not $repoRoot) {
    Write-Error "No se encontro repo git en $PWD ni ancestros."
    exit 1
}

$lockPath = Join-Path $repoRoot ".git\index.lock"

if (-not (Test-Path $lockPath)) {
    Write-Host "OK: .git/index.lock no existe. Nada que limpiar." -ForegroundColor Green
    exit 0
}

# Hay lock. Verificar si hay proceso git activo.
$gitProcs = Get-Process git -ErrorAction SilentlyContinue
$lockInfo = Get-Item $lockPath
$ageMin = [math]::Round(((Get-Date) - $lockInfo.LastWriteTime).TotalMinutes, 1)

Write-Host ""
Write-Host "===== git index.lock detectado =====" -ForegroundColor Yellow
Write-Host "Path:      $lockPath"
Write-Host "Tamano:    $($lockInfo.Length) bytes"
Write-Host "Antiguedad: $ageMin minutos"
Write-Host "Procesos git activos: $($gitProcs.Count)"

if ($gitProcs.Count -gt 0) {
    Write-Host ""
    Write-Host "ALERTA: hay procesos git corriendo. El lock puede NO ser huerfano." -ForegroundColor Red
    $gitProcs | Format-Table Id, ProcessName, StartTime
    Write-Host "NO eliminar el lock sin confirmar que esos procesos terminaron."
    exit 2
}

if (-not $Force) {
    $confirm = Read-Host "Eliminar el lock huerfano? (s/N)"
    if ($confirm -ne 's' -and $confirm -ne 'S') {
        Write-Host "Cancelado por usuario."
        exit 0
    }
}

Remove-Item $lockPath -Force
if ($?) {
    Write-Host "OK: .git/index.lock eliminado." -ForegroundColor Green
    Write-Host "Ahora podes correr 'git status' / 'git add' normalmente."
} else {
    Write-Error "Fallo al eliminar el lock. Verificar permisos."
    exit 1
}
