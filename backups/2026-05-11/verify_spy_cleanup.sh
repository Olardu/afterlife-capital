#!/bin/bash
# Script de verificación post-cierre de short SPY (intervención manual 2026-05-11)
# Correr DESPUÉS de ejecutar la orden BUY 4 SPY en Alpaca Dashboard.
# Verifica que la posición quedó en 0 y registra evidencia para el archivo de auditoría.

cd "$(dirname "$0")/../../sentinel-v0.5" || exit 1

KEY=$(grep '^ALPACA_API_KEY=' .env | cut -d'=' -f2-)
SECRET=$(grep '^ALPACA_SECRET_KEY=' .env | cut -d'=' -f2-)
BASE="https://paper-api.alpaca.markets"

echo "=== Verificación post-intervención $(date) ==="
echo ""

echo "--- 1. Posición SPY (debe NO existir o tener qty=0) ---"
SPY_RESPONSE=$(curl -s -H "APCA-API-KEY-ID: $KEY" -H "APCA-API-SECRET-KEY: $SECRET" "$BASE/v2/positions/SPY")
if echo "$SPY_RESPONSE" | grep -q "position does not exist"; then
    echo "✅ Posición SPY ya no existe — short cerrado correctamente."
else
    echo "⚠ Posición SPY aún existe:"
    echo "$SPY_RESPONSE" | python3 -m json.tool
fi
echo ""

echo "--- 2. Último BUY de SPY (debe ser orden manual de 4 shares) ---"
curl -s -H "APCA-API-KEY-ID: $KEY" -H "APCA-API-SECRET-KEY: $SECRET" \
    "$BASE/v2/orders?status=closed&symbols=SPY&limit=5&direction=desc" \
    | python3 -c "
import json, sys
orders = json.loads(sys.stdin.read())
for o in orders[:3]:
    print(f'  {o.get(\"submitted_at\", \"?\")[:19]} | {o[\"side\"]:5} qty={o[\"qty\"]:>4} filled={o.get(\"filled_avg_price\", \"-\")} status={o[\"status\"]}')
"
echo ""

echo "--- 3. Estado actual de la cuenta ---"
curl -s -H "APCA-API-KEY-ID: $KEY" -H "APCA-API-SECRET-KEY: $SECRET" "$BASE/v2/account" \
    | python3 -c "
import json, sys
a = json.loads(sys.stdin.read())
print(f'  equity:        \${a[\"equity\"]}')
print(f'  cash:          \${a[\"cash\"]}')
print(f'  long_market:   \${a[\"long_market_value\"]}')
print(f'  short_market:  \${a[\"short_market_value\"]}')
print(f'  position_value: \${a[\"position_market_value\"]}')
"
echo ""

echo "--- 4. Confirmar que el bot NO emitió la orden (sentinel.log no menciona SPY BUY qty=4) ---"
if grep -q "SPY BUY qty=4" logs/sentinel.log 2>/dev/null; then
    echo "⚠ ATENCIÓN: el log del bot contiene una orden SPY BUY qty=4 — verificar si fue el bot o intervención manual."
else
    echo "✅ El bot no emitió SPY BUY qty=4 — confirma que la orden fue intervención manual externa."
fi

echo ""
echo "=== Fin verificación ==="
