# Scheduled Task — Verificación fill QQQ short el lunes 18-may

**Cómo crear el task en Cowork:**

1. Abrir menú de Cowork → Scheduled Tasks (o equivalente)
2. Crear nuevo task con estos parámetros:

```
Task ID:    qqq-short-fill-verification
Description: Verificar fill del cierre manual del short QQQ el lunes 18-may post-apertura y actualizar registros.
Fire at:    2026-05-18T09:35:00-04:00
            (= lunes 18-may 09:35 ET, 5 min después de la apertura)
Notify on completion: TRUE
```

3. En el campo "Prompt" pegar todo el bloque que está a continuación (entre las líneas `--- BEGIN PROMPT ---` y `--- END PROMPT ---`):

--- BEGIN PROMPT ---

Tarea automatizada: verificar el fill de una orden manual de cierre de short QQQ en Alpaca paper y actualizar los registros del proyecto Afterlife Capital / Sentinel v0.5.

# CONTEXTO

Roman (Afterlife Capital) envió el sábado 16-may-2026 a las 17:17 ET una orden manual desde Alpaca Dashboard para cerrar una posición short QQQ -2 shares accidental causada por el bug #H-5b (cache `dispatcher.open_positions` desactualizado tras SELLs concurrentes). La orden queda `accepted` hasta el opening cross del lunes 18-may 09:30:00 ET. Este task se dispara a las 09:35 ET para verificar que el fill ocurrió y completar la documentación.

Esto replica el patrón del 11-may-2026 con SPY documentado en `C:\Users\roman\Nueva Ruta\afterlife-capital\backups\2026-05-11\manual_intervention_spy_short_cleanup.md`.

# DATOS DE LA ORDEN

- Order ID: `47b0c814-8677-4bd3-9178-a4c570ae9e15`
- Client Order ID: `9be6fd38-375b-40e4-9497-ddcd61c1d156`
- Symbol: QQQ
- Side: BUY
- Qty: 2
- Type: market
- Position intent: buy_to_close
- TIF: day
- Submitted at: 2026-05-17T21:17:05 UTC

# ESTADO PRE-FILL (verificado sábado 16-may)

- QQQ short: -2 sh @ avg $708.48 (de dos sell_short del 15-may: 09:45:14 @ $707.28 y 10:30:07 @ $710.85)
- Equity: $100,087.20
- Cash: $99,883.07
- Long market value: $1,621.99
- Short market value: -$1,417.86

# CREDENCIALES ALPACA

Las credenciales paper de Alpaca están en `C:\Users\roman\Nueva Ruta\afterlife-capital\sentinel-v0.5\.env`:
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`

Lee el archivo con la herramienta Read y extrae los valores. No los publiques en respuestas al usuario.

# PASOS A EJECUTAR

## Paso 1: Verificación vía Alpaca API

Usar `mcp__workspace__bash` con las credenciales del .env. Llamar:

1. `GET /v2/orders/47b0c814-8677-4bd3-9178-a4c570ae9e15` — debe devolver status="filled", filled_qty="2", filled_avg_price, filled_at.
2. `GET /v2/positions/QQQ` — debe devolver HTTP 404 "position does not exist" (significa que el short se cerró).
3. `GET /v2/account` — captura snapshot: equity, cash, long_market_value, short_market_value (debe ser 0), buying_power, balance_asof.
4. `GET /v2/account/activities/FILL?after=2026-05-18T09:30:00Z&until=2026-05-18T10:00:00Z` — confirma activity con symbol=QQQ, side=buy, qty=2, type=fill.

## Paso 2: Cálculo de realized P&L del cierre

```
Entry avg (short open) = $708.48
Exit price = filled_avg_price (del paso 1)
Realized P&L = (708.48 - exit_price) × 2
```

Si exit < 708.48 → ganancia. Si exit > 708.48 → pérdida.

## Paso 3: Confirmar intervención externa (no del bot)

Usar `Grep` sobre `C:\Users\roman\Nueva Ruta\afterlife-capital\sentinel-v0.5\logs\sentinel.log` con patrón:
- `^2026-05-18.*Orden enviada.*QQQ BUY qty=2`

Resultado esperado: 0 matches. Eso prueba que el fill fue intervención externa, no del bot.

También verificar entre 09:30:00 y el fill que no haya emisiones de QQQ por el dispatcher (race condition):
- `^2026-05-18 09:[34][0-9].*sentinel\.dispatcher.*QQQ`

Anotar cualquier coincidencia para evaluar race.

## Paso 4: Actualizar archivos de documentación

Tres archivos a editar (todos son .md, no toca DB ni código operacional):

### 4a. `C:\Users\roman\Nueva Ruta\afterlife-capital\backups\2026-05-16\manual_intervention_qqq_short_cleanup.md`

Completar secciones 7.2 a 7.5 con los datos reales del paso 1 y 2. Cambiar la sección 8 — los items pendientes ⏳ pasan a ✅.

- 7.2 Ejecución real (timestamps UTC y ET, filled_qty, filled_avg_price, status, fees=$0)
- 7.3 Estado de la cuenta post-fill
- 7.4 Realized P&L del cierre
- 7.5 Race condition con el bot (resultados del paso 3)

### 4b. `C:\Users\roman\Nueva Ruta\afterlife-capital\CHANGELOG.md`

En el bloque `## [Unreleased] — 2026-05-16 — Intervención manual pendiente: short QQQ accidental por bug #H-5b reaparición`, agregar al final una sección `### Fill confirmado (2026-05-18)` con:
- Hora del fill (UTC y ET)
- Filled avg price
- Realized P&L del cierre
- Cash, equity, posición QQQ post-fill
- Confirmación de intervención externa

Cambiar el título del bloque a `## [Unreleased] — 2026-05-16 — Intervención manual: short QQQ accidental por bug #H-5b reaparición — FILL CONFIRMADO 2026-05-18`.

### 4c. `C:\Users\roman\Nueva Ruta\afterlife-capital\OBSERVATION_PERIOD.md`

En la sección `### Intervención manual 2026-05-16: cierre de short QQQ accidental por bug #H-5b (reaparición)`, agregar después del "Plan de cierre" un bloque `**Fill confirmado (verificado vía Alpaca API 2026-05-18):**` con:
- Submitted at (sábado), Filled at (lunes)
- Filled avg price
- Realized P&L
- Posición QQQ: 0 shares ✅
- Cash, Equity, Short market value
- Estado: evento CERRADO limpiamente.

## Paso 5: Reportar al usuario

Mensaje resumen en español, conciso, con:
- ✅ Confirmación de fill o ⚠️ si algo no se ejecutó como esperado
- Filled price + realized P&L
- Estado actual de la cuenta (equity, cash)
- Si hubo race condition o no
- Archivos actualizados con links computer://

Formato del link: `[Archivo](computer://C:\ruta\completa\al\archivo)`

# REGLAS OPERACIONALES (no negociables)

- Solo lectura sobre la DB Postgres. No ejecutar UPDATE/INSERT/DELETE. Si necesitas escribir algo, proponer SQL y pedir que Roman lo ejecute.
- No enviar órdenes a Alpaca. Solo lecturas GET.
- No tocar `.env`, credenciales, ni configuración runtime.
- No reiniciar el bot (`sentinel-stop.bat` / `sentinel-start.bat`).
- Edición de archivos .md está permitida sin pedir permiso adicional.
- Si encuentras algo inesperado (orden no se ejecutó, fill parcial, posición sigue abierta, error de API), reportar al usuario y NO intentar corregir autónomamente.

# REFERENCIAS

- Documento de intervención: `C:\Users\roman\Nueva Ruta\afterlife-capital\backups\2026-05-16\manual_intervention_qqq_short_cleanup.md`
- Precedente del 11-may: `C:\Users\roman\Nueva Ruta\afterlife-capital\backups\2026-05-11\manual_intervention_spy_short_cleanup.md`
- CLAUDE.md del bot: `C:\Users\roman\Nueva Ruta\afterlife-capital\sentinel-v0.5\CLAUDE.md`
- Reglas del período de observación: `C:\Users\roman\Nueva Ruta\afterlife-capital\OBSERVATION_PERIOD.md`

--- END PROMPT ---

## Nota importante

Los scheduled tasks corren solo cuando la app de Cowork está abierta. Si la app está cerrada al disparo, el task se ejecuta al próximo launch. Para garantizar que el task corra el lunes a las 09:35 ET, mejor abrir Cowork antes de esa hora.

Alternativa más simple si el scheduled task da problemas:
- El lunes a partir de las 09:30 ET, abrir nueva sesión de Cowork con el mensaje: "verifica el fill del QQQ del cierre manual del sábado, order_id 47b0c814-8677-4bd3-9178-a4c570ae9e15"
- Yo entro a verificar todo igual, manualmente, sin necesidad del task automatizado.
