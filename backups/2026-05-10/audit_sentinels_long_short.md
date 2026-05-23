# Auditoría de los 9 Sentinels — long-only / long-cash / long-short

**Fecha:** 2026-05-10
**Propósito:** Preparación para habilitar fractional trading en fase live (post-27-may). Determinar si cada Sentinel toma posiciones short, y qué hay que modificar (si algo) cuando se introduzca fractional.
**Alcance:** Solo análisis del código actual de `sentinel-v0.5/sentinels/__init__.py` y `dispatcher.py`. NO toca producción.

---

## Hallazgo central — dos niveles de "long-short"

Distinguir entre:

1. **Intención de diseño** del Sentinel: qué señal emite el `analyze()` ante condiciones bajistas (BEAR signal).
2. **Comportamiento efectivo** del sistema: qué hace el Dispatcher con esa señal.

Los 9 Sentinels son **long-short en intención de diseño** (`analyze()` emite SELL en condiciones bajistas con simetría sobre BUY). Pero el **Dispatcher restringe el sistema a long-cash de facto**: en `dispatcher.process_signal` líneas ~355-358:

```python
if side == "SELL":
    if ticker not in self.open_positions:
        logger.info(f"Señal SELL para {ticker} rechazada — sin posición abierta.")
        return {**base_result, "reason": "no_open_position"}
```

Resultado: las señales SELL solo se ejecutan **si hay una posición long previa que cerrar**. Ningún Sentinel puede abrir short hoy. **El sistema actual ya es long-cash de facto, independiente de la intención de cada Sentinel.**

Esto simplifica la decisión para fractional: no hay que modificar la lógica de los Sentinels. Solo hay que hacer explícito el comportamiento y documentarlo.

---

## Tabla por Sentinel

| # | Codename / Strategy | BUY signal | SELL signal | Intención diseño | Comportamiento actual | Acción para fractional |
|---|---|---|---|---|---|---|
| S-1 | SMA Crossover (`sma_crossover`) | Golden cross (SMA10 cruza arriba SMA50) | Death cross (SMA10 cruza abajo SMA50) | Long-short | Long-cash | Ninguna |
| S-2 | RSI Short (`rsi_short`) | RSI(2) < 15 | RSI(2) > 85 | Long-short | Long-cash | Ninguna |
| S-3 | Bollinger Bounce (`bollinger_bounce`) | Cierre < banda inferior | Cierre > banda superior | Long-short | Long-cash | Ninguna |
| S-4 | MACD+Volume (`macd_volume`) | Cross-up con vol > 1.5×SMA20 | Cross-down con vol > 1.5×SMA20 | Long-short | Long-cash | Ninguna |
| S-5 | ORB Breakout (`orb_breakout`) | Cierre > opening range high con vol confirmado | Cierre < opening range low con vol confirmado | Long-short | Long-cash | Ninguna |
| S-6 | EMA Triple (`ema_triple`) | EMA8 > EMA21 > EMA55 | EMA8 < EMA21 < EMA55 | Long-short | Long-cash | Ninguna |
| S-7 | VWAP Reversion (`vwap_reversion`) | Precio < VWAP - 2σ | Precio > VWAP + 2σ | Long-short | Long-cash | Ninguna |
| S-8 | RSI Divergence (`rsi_divergence`) | Bullish divergence (precio low, RSI no) | Bearish divergence (precio high, RSI no) | Long-short | Long-cash | Ninguna |
| S-9 | Bollinger Squeeze (`bollinger_squeeze`) | Squeeze + breakout arriba | Squeeze + breakout abajo | Long-short | Long-cash | Ninguna |

**No hay ningún Sentinel que requiera modificación para fractional.** Todos pueden operar fractional desde el primer día porque ninguno abre short con el dispatcher actual.

---

## Caveats operativos importantes

### 1. Asimetría de mercado (consecuencia del long-cash de facto)

Como el sistema solo opera del lado alcista, en bear markets queda paralizado a nivel de posiciones nuevas. Específicamente:

- **Bear market sostenido**: muchos Sentinels emiten SELL, el dispatcher los rechaza, no se abren posiciones nuevas. El sistema queda en cash hasta que aparezcan señales BUY.
- **Bull market**: el sistema opera normalmente.
- **Mercado lateral**: las mean-reversion (S-2, S-3, S-7) y reversal (S-8) generan rotación de longs sin tomar shorts.

Esto es una decisión de diseño implícita, no documentada en el código. Vale anotarla porque afecta cómo se interpreta el Sharpe agregado.

### 2. "RSI Short" no significa short selling

El nombre `S-2 RSI Short` puede confundir. "Short" se refiere al **período corto** del RSI (2 barras), no a dirección short. La estrategia es mean reversion long-cash idéntica a las demás. Vale aclararlo en el dashboard o renombrar a algo como `RSI Fast Reversion` post-observación.

### 3. SELL como cierre solo opera por ticker

`dispatcher.process_signal` busca `ticker in self.open_positions`. Si dos Sentinels distintos tienen posición en NVDA (uno larga del S-2, otro larga del S-6) — el dispatcher solo trackea una posición por ticker (`self.open_positions: dict[str, dict]`). Una SELL de cualquier Sentinel cierra la posición compartida en NVDA. Eso puede generar comportamientos donde un Sentinel "cierra la posición de otro".

**Implicación para fractional + observación**: con capital pequeño y fractional, este efecto se va a ver más seguido porque más Sentinels van a tener posiciones a la vez en activos compartidos. Anotarlo para revisar post-27-may si genera ruido.

### 4. Restricción de duplicate BUY entre Sentinels

Líneas 352-354 del dispatcher:

```python
if side == "BUY" and ticker in self.open_positions:
    logger.info(f"Señal BUY {ticker} omitida — ya hay posición abierta este cycle.")
    return {**base_result, "reason": "duplicate_ticker_buy"}
```

Si NVDA ya está en `open_positions` de un Sentinel, otro Sentinel emitiendo BUY en NVDA queda bloqueado. Esto es protección anti-doble-compra del mismo ticker. Con fractional, esta protección sigue siendo deseable (no comprar 2× en el mismo ticker en el mismo ciclo), pero conviene revisar si la lógica también bloquea casos legítimos (Sentinel A vende NVDA, Sentinel B emite BUY en el mismo ciclo — debería poder ejecutarse).

---

## Recomendaciones para post-27-may

### Implementación de fractional (sin cambios a Sentinels)

1. **Modificar contrato del Dispatcher** de `qty=int` a `notional=float`. Ningún Sentinel necesita cambios.
2. **Agregar filtros en Universe Selection**: `fractionable=TRUE`, `marginable=TRUE`. El Universe Selector llama a Claude — el prompt necesita incluir el filtro en el criterio de selección.
3. **Cap mínimo por bot ~$25-50**: si `capital_total / 9 < $25`, dispatcher concentra en menos bots (los de mejor Sharpe) o salta el ciclo. Esto requiere modificación de `allocate_capital`.

### Documentación previa (puede hacerse durante observación)

1. **Renombrar S-2 RSI Short → RSI Fast Reversion** en el dashboard (cambio cosmético, está permitido durante observación).
2. **Agregar nota en `CLAUDE.md`** documentando que el sistema actual es long-cash de facto, no long-short como sugiere la simetría de las señales BUY/SELL en cada Sentinel.
3. **Documentar la asimetría de mercado** como "expected behavior" en `RATIONALE.md` (cuando se cree).

### Decisión deferida (post-fractional, cuando capital crezca)

Si en algún punto Roman decide habilitar shorts (whole shares, no fractional):
- Sería una **modificación al Dispatcher**: relajar la condición de `no_open_position`.
- Cada Sentinel necesitaría una decisión: ¿la SELL en BEAR signal abre short, o solo cierra long si existe?
- Probablemente requiere `easy_to_borrow=TRUE` filter en Universe Selection.
- Bots con peor Sharpe deberían no shortear (Half-Kelly con leverage negativo sobre Sharpe bajo amplifica pérdida).
- Esto NO es para 2026. Es decisión de v2.x o posterior.

---

## Verificación contra Alpaca Assets API (ejecutada 2026-05-10)

Hecha vía `GET /v2/assets/{symbol}` con paper credentials desde el sandbox. 27 tickers verificados (los originales de los 9 Sentinels + los 18 que rotó Mantis bajo el bug del bucle).

### Resultados consolidados

**Fractional:** ✅ 27/27 con `fractionable=TRUE`. **Cero modificación necesaria a nivel de assets cuando se implemente fractional.**

**Marginable:** ✅ 27/27 con `marginable=TRUE`. Cuando se active leverage, todos los assets actuales lo soportan sin restricciones.

**Shortable + Easy-to-borrow:** ❌ **5 tickers NO son shortable ni easy-to-borrow**:

| Ticker | Tipo | Razón |
|---|---|---|
| BITI | 1x inverse Bitcoin | Producto leveraged inverse — bloqueado para short |
| SQQQ | 3x inverse QQQ | Leveraged inverse, decay diario brutal |
| UVXY | 2x VIX futures | Leveraged volatility, no shortable |
| VIXY | 1x VIX short-term | Volatility ETF, restricted |
| USO | Oil futures fund | Restricted por estructura de futuros |

Los 5 son exactamente los que Roma identificó conceptualmente como "no aptos para rsi_short" en la conversación de fractional. El Universe Selector los propuso bajo el bug del bucle de Mantis (todos ya `is_active=FALSE` post-cleanup). Confirma que **filtrar `shortable=TRUE` y/o lista negra de leveraged products en el prompt del Universe Selector** es necesario para evitar que vuelvan a ser propuestos.

### Datos adicionales de la cuenta paper (`GET /v2/account`)

- `portfolio_value = $100,146.23` / `equity = $100,146.23`
- `cash = $99,548.56`
- `multiplier = "4"` (4x intraday — la cuenta tiene PDT designation activa)
- `pattern_day_trader = true` (relevante: hasta el 4-jun 2026 cuando FINRA retire la regla)
- `shorting_enabled = true` (a nivel de cuenta, los shorts están permitidos)
- `daytrade_count = 23`
- `long_market_value = $2,068.47`
- `short_market_value = -$1,470.80` ⚠️ **hay posiciones short activas**

### Posiciones reales actuales (`GET /v2/positions`)

| Side | Ticker | Qty | Avg entry | Unrealized PnL |
|---|---|---|---|---|
| LONG | AAPL | 1 | $278.74 | +$12.26 |
| LONG | GLD | 1 | $431.12 | -$1.44 |
| LONG | IWM | 1 | $284.97 | -$2.33 |
| LONG | MSFT | 1 | $412.87 | -$0.80 |
| **SHORT** | **SPY** | **-2** | **$737.04** | **+$3.55** |
| LONG | TSLA | 1 | $426.23 | -$0.98 |
| LONG | XLP | 1 | $83.86 | +$0.23 |
| LONG | XLV | 1 | $144.87 | -$1.32 |

**El SHORT SPY de 2 shares contradice la conclusión inicial de la auditoría.** El sistema actual SÍ está abriendo shorts, no es long-cash puro como sugería el filtro `if ticker not in self.open_positions` del Dispatcher.

---

## NUEVO BUG DESCUBIERTO — `#H-5b` Cache desactualizado en open_positions tras SELL

### Síntoma

SPY está short en -2 shares en Alpaca paper, a pesar de que el Dispatcher tiene lógica explícita para rechazar SELL sin posición previa. Los dos `SPY VENTA qty=1` del 2026-05-08 (13:15 y 14:15 ET) que vimos en logs llevaron la posición de +1 long a -1 (primera SELL cerró la long) y de -1 a -2 (segunda SELL profundizó el short).

### Causa raíz

En `dispatcher.process_signal` (líneas 401-408 de la versión actual):

```python
# Actualizar posiciones locales si se ejecutó
if order_result.get("status") == "FILLED":
    self.open_positions[ticker] = {
        "ticker":      ticker,
        "qty":         final_qty,
        "side":        side,
        "sentinel_id": sentinel_id,
    }
```

La actualización solo agrega/sobrescribe la entry. **Nunca se ELIMINA la entry tras un SELL exitoso.** Resultado: dentro del mismo cycle, después de una SELL que cierra una posición:

1. `sync_positions_from_alpaca()` al inicio del cycle: `open_positions = {SPY: long 1}`.
2. Sentinel A emite SELL en SPY → check `ticker not in self.open_positions` falla (SPY está en el dict) → SELL ejecuta → Alpaca posición = 0 → pero `self.open_positions` queda con `{SPY: long 1}` cacheado.
3. Sentinel B (o el mismo en otro ciclo intermedio sin sync) emite SELL en SPY → check vuelve a fallar → SELL ejecuta → Alpaca posición = -1.
4. Repetir → -2.

Esto es exactamente lo que pasó el 8-may. La discrepancia se detecta en el `sync_positions_from_alpaca()` del siguiente cycle (línea 90: "Posiciones fantasma (local pero no en Alpaca)") pero ya es tarde — los shorts están abiertos.

### Severidad

**ALTA pero no inmediata.** El sistema accidentalmente toma posiciones short, lo cual:
- Funciona porque la cuenta tiene `shorting_enabled=true` y `multiplier=4`. Pero no es la intención de diseño.
- Pierde el guard que se pensaba tener para fase live con capital pequeño.
- Para los 5 tickers NO shortable (BITI, SQQQ, UVXY, VIXY, USO), la SELL fallaría con error de Alpaca cuando se intente shortear — generaría órdenes rechazadas en logs pero no posición.

### Fix propuesto (NO implementar durante observación)

En `process_signal`, después de `if order_result.get("status") == "FILLED"`:

```python
if side == "BUY":
    self.open_positions[ticker] = {
        "ticker": ticker, "qty": final_qty,
        "side": "BUY", "sentinel_id": sentinel_id,
    }
elif side == "SELL":
    # SELL cierra posición — eliminar entry del cache
    self.open_positions.pop(ticker, None)
```

Adicionalmente, considerar si la condición `if ticker not in self.open_positions` debería relajarse para permitir shorts intencionales (cuando se decida soportar short-selling diseñado) o si reforzarse para detectar cantidades.

**Status:** documentado, NO implementado. Cae en regla 4 de `OBSERVATION_PERIOD.md`. Programar para bloque post-27-may.

### Acción correctiva manual (sugerencia para Roman)

Cuando vuelvas a arrancar el bot el lunes, vale cerrar manualmente el short de SPY desde el panel admin o desde Alpaca directamente (compra 2 shares de SPY a market) para limpiar la posición y empezar el período de observación post-fix con posiciones consistentes con el diseño long-cash esperado.

---

## Recomendaciones actualizadas

### Cambios en el prompt del Universe Selector (post-27-may)

Filtrar explícitamente del universo permitido:

- `tradable=TRUE` (ya implícito)
- `fractionable=TRUE` (cuando se active fractional)
- `marginable=TRUE` (cuando se active leverage)
- `shortable=TRUE` (siempre — los 5 leveraged inverse del bug no deberían volver a ser propuestos)
- Lista negra explícita por nombre de leveraged inverse ETFs (`BITI, SQQQ, SOXS, UVXY, VIXY, SQQQ, TQQQ, UPRO, SPXU, TZA, FAZ` etc.). El prompt actual menciona "NUNCA propongas penny stocks" pero no menciona leveraged products como categoría.

### Validación de la auditoría

La conclusión central se mantiene: **los 9 Sentinels en su lógica de análisis NO discriminan entre "cerrar long" y "abrir short"** — emiten SELL en condiciones bajistas con simetría sobre BUY. El sistema actual estaba pensado para long-cash, pero el cache bug del Dispatcher permite que accidentalmente termine en short. Una vez fixeado #H-5b, el sistema vuelve a ser long-cash de facto y fractional puede proceder sin modificar Sentinels.

---

*Auditoría hecha el 2026-05-10. No toca código de producción. Sirve como referencia para el bloque de infraestructura post-27-may.*
