<#
.SYNOPSIS
    Valida que el working tree no tenga archivos truncados antes de commit/push.

.DESCRIPTION
    Capa preventiva automatizada para detectar el bug del Write/Edit
    silenciosamente truncado (3 incidentes en 24h el 24-may, ver
    BUENAS_PRACTICAS_V2 §14.0.7).

    Recorre `git status --porcelain` y para cada archivo M, A, ??:
      - .py  → python -m py_compile, abort si error
      - .js  → node --check, abort si error
      - .md / .json / .yaml / .yml → verifica final del archivo
        (no terminar a media palabra, último byte = newline o cierre razonable)
      - otros → check que no esté vacío

    Reporta errores y warnings con sugerencias de recovery.
    Exit code 0 si OK; con -Strict exit 1 si hay errors o warnings.

.PARAMETER Strict
    Si se pasa, exit code != 0 ante warnings (no solo errors).
    Útil en pre-commit hooks o CI.

.EXAMPLE
    PS> cd "C:\Users\roman\Nueva Ruta\afterlife-capital"
    PS> .\sentinel-v0.5\scripts\validate-workspace.ps1

.NOTES
    Creado 2026-05-24 tras 3 incidentes del bug Write truncado.
    Ver BUENAS_PRACTICAS_V2.md §14.0 (gate técnico post-edit).
#>

param(
    [switch]$Strict
)

# Localizar repo root (sube buscando .git)
$repoRoot = $PWD.Path
while ($repoRoot -and -not (Test-Path (Join-Path $repoRoot ".git"))) {
    $repoRoot = Split-Path $repoRoot -Parent
}
if (-not $repoRoot) {
    Write-Error "No se encontro repo git en $PWD ni ancestros."
    exit 1
}
Set-Location $repoRoot

# Obtener archivos del git status (porcelain = stable formato)
$statusOutput = git status --porcelain
$errors   = @()
$warnings = @()
$checked  = 0

foreach ($line in $statusOutput) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }

    $status = $line.Substring(0, 2)
    $file   = $line.Substring(3).Trim('"')

    # Procesar M (modified), A (added), ?? (untracked); saltar D (deleted)
    if ($status -notmatch '^( M|M |MM|A |\?\?)$') { continue }

    # FIX 2026-05-24 (Cowork): path absoluto OBLIGATORIO. PowerShell hace Set-Location
    # arriba pero metodos .NET ([System.IO.File], [System.IO.Path]) y cmdlets como
    # Get-Item usan el CWD del proceso .NET (que NO es el de PowerShell). Sin
    # absolute path, ReadAllBytes/Get-Item fallan con 'No se puede encontrar'
    # cuando el script se invoca desde fuera del repo root.
    $absPath = Join-Path $repoRoot $file
    if (-not (Test-Path $absPath -PathType Leaf)) { continue }

    $checked++
    $ext = [System.IO.Path]::GetExtension($file).ToLower()

    switch ($ext) {
        '.py' {
            $null = python -m py_compile $absPath 2>&1
            if ($LASTEXITCODE -ne 0) {
                $errors += "[.py] $file - py_compile FAIL"
            }
        }
        '.js' {
            $null = node --check $absPath 2>&1
            if ($LASTEXITCODE -ne 0) {
                $errors += "[.js] $file - node --check FAIL"
            }
        }
        { $_ -in '.md', '.json', '.yaml', '.yml' } {
            $bytes = [System.IO.File]::ReadAllBytes($absPath)
            if ($bytes.Length -eq 0) {
                $warnings += "[$ext] $file - archivo vacio"
                continue
            }
            $lastByte = $bytes[$bytes.Length - 1]
            # \n (10) o \r (13) son sanos
            if ($lastByte -eq 10 -or $lastByte -eq 13) { continue }

            # Si no termina en newline, check si ultima linea termina en char de cierre razonable
            $lastLine = (Get-Content $absPath -Tail 1 -ErrorAction SilentlyContinue)
            if ($lastLine -match '[.,?!:})>\"''*`\]_\-]$') { continue }

            $warnings += "[$ext] $file - posible truncado: ultima linea no termina en newline ni cierre razonable (ultimo byte=$lastByte)"
        }
        default {
            if ((Get-Item $absPath).Length -eq 0) {
                $warnings += "[$ext] $file - archivo vacio"
            }
        }
    }
}

# Reporte
Write-Host ""
Write-Host "===== validate-workspace.ps1 =====" -ForegroundColor Cyan
Write-Host "Repo:                 $repoRoot"
Write-Host "Archivos chequeados:  $checked"
$errColor  = if ($errors.Count -gt 0) { 'Red' } else { 'Green' }
$warnColor = if ($warnings.Count -gt 0) { 'Yellow' } else { 'Green' }
Write-Host "Errores:              $($errors.Count)" -ForegroundColor $errColor
Write-Host "Warnings:             $($warnings.Count)" -ForegroundColor $warnColor

if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "ERRORES:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Sugerencia: 'git checkout HEAD -- <archivo>' para revertir, o restaurar desde backup en backups/YYYY-MM-DD/."
}

if ($warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "WARNINGS (posibles truncados, revisar manualmente):" -ForegroundColor Yellow
    $warnings | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
}

if ($errors.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host ""
    Write-Host "OK: working tree limpio. Listo para commit/push." -ForegroundColor Green
}

if ($Strict -and ($errors.Count -gt 0 -or $warnings.Count -gt 0)) {
    exit 1
}
exit 0
