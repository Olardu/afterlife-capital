#!/usr/bin/env bash
# check_secrets.sh — Guard anti-fuga (#15). Escanea lo STAGED por credenciales/PII
# antes de permitir un commit. Nace del incidente del 31-may (secretos+PII en repo
# público). Diseño: patrones de FORMA (no valores reales — el guard no debe contener
# secretos) + patrones extra opcionales desde .secrets-patterns.local (gitignored),
# donde Roman puede poner los valores exactos (IP server, tunnel-id, UUID) sin
# commitearlos. Uso: lo invoca .git/hooks/pre-commit; también corre en CI.
# Salida: 0 = limpio; 1 = hallazgo (aborta el commit).
set -uo pipefail

# Patrones de FORMA de credenciales (regex ERE). NO contienen valores reales.
PATTERNS=(
  'sk-ant-api03-[A-Za-z0-9_-]{20,}'          # Anthropic API key
  'GOCSPX-[A-Za-z0-9_-]{10,}'                # Google OAuth client secret
  're_[A-Za-z0-9_]{20,}'                     # Resend API key
  '\bPK[A-Z0-9]{16,}\b'                      # Alpaca key ID
  'AKIA[0-9A-Z]{16}'                         # AWS access key id
  'ghp_[A-Za-z0-9]{30,}'                     # GitHub PAT
  'xox[baprs]-[A-Za-z0-9-]{10,}'             # Slack token
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'       # private key block
  '(password|passwd|PGPASSWORD|secret|api[_-]?key|token)[[:space:]]*[=:][[:space:]]*["'"'"'][^"'"'"']{6,}'  # asignación de credencial
  '[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo)\.[A-Za-z]{2,}'  # email personal (PII)
)

# Patrones extra locales (valores exactos: IP/tunnel/UUID) — NO versionados.
EXTRA_FILE="$(git rev-parse --show-toplevel 2>/dev/null)/.secrets-patterns.local"
EXTRA=()
if [ -f "$EXTRA_FILE" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    EXTRA+=("$line")
  done < "$EXTRA_FILE"
fi

# Modo de escaneo:
#   (sin args)            -> staged (pre-commit hook): git diff --cached
#   --range <base> <head> -> CI: git diff <base> <head> (solo lo nuevo del push/PR)
# En ambos casos se escanean SOLO las líneas AGREGADAS (+), no el árbol entero, para
# no romper por contenido viejo legítimo y bloquear únicamente nuevas introducciones.
if [ "${1:-}" = "--range" ]; then
  DIFF_SPEC=("${2:?--range requiere BASE}" "${3:?--range requiere HEAD}")
else
  DIFF_SPEC=(--cached)
fi

# Archivos cambiados (added/copied/modified), excluyendo binarios y el propio guard.
mapfile -t FILES < <(git diff "${DIFF_SPEC[@]}" --name-only --diff-filter=ACM | grep -vE '\.(png|jpg|jpeg|gif|ico|pdf|zip|gz|dump)$' | grep -vE 'scripts/check_secrets\.sh$')

hits=0
mask() { sed -E 's/(.{4}).*(.{3})/\1***\2/'; }

scan_one() {
  local pat="$1" label="$2"
  for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue
    # Solo las líneas AGREGADAS en el stage (+), no el archivo entero.
    while IFS= read -r match; do
      [ -z "$match" ] && continue
      echo "  [$label] $f : $(printf '%s' "$match" | mask)"
      hits=$((hits+1))
    done < <(git diff "${DIFF_SPEC[@]}" -U0 -- "$f" | grep '^+' | grep -vE '^\+\+\+' | grep -oE "$pat" 2>/dev/null)
  done
}

for p in "${PATTERNS[@]}"; do scan_one "$p" "forma"; done
for p in "${EXTRA[@]}";    do scan_one "$p" "local"; done

if [ "$hits" -gt 0 ]; then
  echo ""
  echo "✖ check_secrets: $hits hallazgo(s) de credencial/PII en lo staged (enmascarado arriba)."
  echo "  Quitá el secreto del cambio (o usá un placeholder) y re-stageá. Para un falso positivo"
  echo "  puntual, commiteá con --no-verify SOLO si estás 100% seguro de que no es un secreto."
  exit 1
fi
echo "✓ check_secrets: limpio (${#FILES[@]} archivo(s) escaneados)."
exit 0
