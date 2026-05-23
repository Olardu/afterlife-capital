# Deploy steps — Excepción 1 ampliada (2026-05-08)

Lo que hice yo (offline, sin tocar producción) y lo que necesita que ejecutes vos.

## Ya hecho

1. **Backups** de archivos a modificar en `backups/2026-05-08/`:
   - `dispatcher.py.pre-fix2`
   - `historian.py.pre-fix2`
2. **Fix 1 aplicado** en `sentinel-v0.5/dispatcher.py` líneas 153-163: conversión explícita `float()` e `int()` en `allocate_capital()`.
3. **Fix 2 aplicado** en `sentinel-v0.5/historian.py` líneas 585-619: `get_sentinel_scores()` ahora hace `JOIN sentinel_tickers ON is_active = TRUE`.
4. **Validación de sintaxis** con `ast.parse()`: ambos archivos OK, CRLF preservado.
5. **Simulación** ejecutada confirmando comportamiento esperado: Mantis pasa de 5% (piso) a 25% (techo), qty NVDA pasa de 1 a ~200 shares.
6. **SQL listo**: `validation_queries_2026-05-08.sql` y `cleanup_mantis.sql`.
7. **Documentación**: `OBSERVATION_PERIOD.md` ampliada, `CHANGELOG.md` actualizado, `CLAUDE.md` con nuevo estado.

## Lo que necesitás ejecutar vos (10 minutos)

### Paso 1 — Validar Sharpes reales (opcional pero recomendado)

pgAdmin ya está abierto y conectado al servidor PostgreSQL 18. Solo te pide el password.

1. En pgAdmin, hace doble click en `PostgreSQL 18` → ingresá tu password de postgres → OK.
2. Navega: `Databases → sentinel → tools → Query Tool` (botón en la barra superior, ícono de rayo).
3. Abrí el archivo: `Open File` → `backups/2026-05-08/validation_queries_2026-05-08.sql`.
4. Ejecutá (F5).
5. Pegame el output de los Bloques 2, 3 y 7 si querés que valide la lista de tickers a limpiar antes de seguir.

Si saltás este paso y vas directo a Paso 2, el `cleanup_mantis.sql` también incluye verificación pre y post.

### Paso 2 — Ejecutar limpieza Mantis

1. En pgAdmin Query Tool, abrí: `backups/2026-05-08/cleanup_mantis.sql`.
2. Ejecutá (F5).
3. Verificá el output del último SELECT: solo `NVDA`, `XLU`, `TLT` deberían aparecer como `is_active = TRUE` para Mantis.

### Paso 3 — Reiniciar el bot

Tenés `sentinel-stop.bat` y `sentinel-start.bat` en `Descargas/`. La secuencia:

1. Doble click en `sentinel-stop.bat` (o detené `main.py` como lo hagas normalmente).
2. Esperá ~5 segundos a que el proceso termine.
3. Doble click en `sentinel-start.bat`.
4. Verificá en la ventana que arranca (o en `sentinel-v0.5/logs/sentinel.log`):
   - Línea con `=== Sentinel v0.5 — Iniciando sistema ===`.
   - Después del primer ciclo de 15 min: `Sharpe agregado por sentinel: {...}` y `Capital asignado: {...}` (sin errores `decimal.Decimal`).

### Paso 4 — Verificar el siguiente ciclo

Hoy mercado cerrado. El bot va a correr ciclos administrativos cada 15 min con `can_trade=False`. Aún así, los logs deben mostrar:

- ✅ `Sharpe agregado por sentinel: {'4d60c408...': 39.96, ...}` — sin TypeError.
- ✅ `Capital asignado: {'4d60c408...': '25.0%', ...}` — Mantis al techo.
- ✅ `Universe Selection ciclo: evaluated=N rotations=0` — el bucle se detuvo.
- ❌ Si seguís viendo `Error calculando allocation` o rotaciones de Mantis sobre TSLA/SPY, abrime un chat y revisamos.

### Paso 5 — Verificación con mercado abierto (lunes 2026-05-11)

A las 09:30 ET el lunes:
- Mantis debería emitir señales solo sobre NVDA, XLU, TLT.
- Las órdenes deberían tener qty calculada según 25% del equity (típicamente 100-250 shares según precio).
- `qty=1` ya NO debería ser el patrón dominante.

Si todo OK lunes a media mañana, la Excepción 1 ampliada queda cerrada como bug fix exitoso.

## Rollback (si algo sale mal)

```powershell
cd "C:\Users\roman\Nueva Ruta\afterlife-capital"
copy backups\2026-05-08\dispatcher.py.pre-fix2 sentinel-v0.5\dispatcher.py
copy backups\2026-05-08\historian.py.pre-fix2 sentinel-v0.5\historian.py
```

Y reiniciar el bot. La limpieza de `sentinel_tickers` no se rolbackea automáticamente — si querés, hay que `UPDATE sentinel_tickers SET is_active = TRUE WHERE sentinel_id = '4d60c408-...'` para revertir, pero recordá que eso te devuelve los 18 tickers nuevos.

## Archivos generados en `backups/2026-05-08/`

- `dispatcher.py.pre-fix2` — backup pre-cambio
- `historian.py.pre-fix2` — backup pre-cambio
- `test_fixes_simulation.py` — script de simulación de los 4 escenarios
- `validation_queries_2026-05-08.sql` — queries read-only para diagnóstico
- `cleanup_mantis.sql` — UPDATEs de limpieza (este es el que ejecutás)
- `DEPLOY_STEPS.md` — este archivo
