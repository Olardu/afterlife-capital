# Intervención manual 2026-05-16: cierre de short QQQ accidental + análisis de pérdida del 15-may

**Fecha:** 16 de mayo de 2026 (sábado, mercado cerrado)
**Tipo:** corrección de bug + análisis read-only del período de observación
**Permitido bajo:** `OBSERVATION_PERIOD.md` sección PERMITIDO punto 1 (bug fix crítico — pérdida de dinero por error técnico) + punto 3 (observabilidad read-only)
**Ejecutor pendiente:** Roman, manual vía Alpaca Dashboard (lunes 18-may apertura)
**Bug raíz:** #H-5b — cache `dispatcher.open_positions` desactualizado post-SELL → SELLs concurrentes sobre posición ya cerrada en Alpaca → short acumulado

---

## 1. Resumen ejecutivo

El viernes 15-may-2026 la cuenta paper de Alpaca perdió **-$84.64 (-0.08%)** sobre un equity de $100,172. La pérdida principal vino de un trade de AMD con pérdida realizada de **-$19.81**, complementada con pérdidas menores en NVDA, TSLA y QQQ. Adicionalmente, el bug #H-5b se manifestó de nuevo y generó dos SELL accidentales sobre QQQ que dejaron una **posición short QQQ -2 shares** que NO fue decisión del bot — son shorts heredados del cache desactualizado, mismo patrón que el SPY del 11-may.

Estado actual de la cuenta:
- Equity: $100,087.20
- Cash: $99,883.07
- Posiciones abiertas: AAPL +1, NVDA +1, SPY +1, TLT +1, XLP +1, XLU +1, XLV +1, **QQQ -2 (accidental)**
- Long market value: $1,621.99 / Short market value: -$1,417.86
- Position market value: $3,039.85 (utilización ~3% del equity, sizing trivial qty=1 plano)

---

## 2. P&L del 15-may por símbolo (realizado)

Reconstruido a partir de `/v2/account/activities/FILL` con matching FIFO contra entries previos del 12-14 may:

| Símbolo | P&L 15-may | Detalle |
|---|---:|---|
| **AMD** | **-$19.81** | Entry 14-may 10:45 @ $449.26 (S-4 MACD+Volume), exit 15-may 15:30 @ $429.45. El peor trade del día por sí solo aporta 23% de la pérdida diaria. |
| **NVDA** | **-$7.13** | Múltiples idas y vueltas con entry pesado del 14-may @ $235.61 y exits del 15-may en $227-228. |
| **TSLA** | -$6.74 | Entry 13-may @ $437.12, exit 15-may 09:32 @ $430.38 (apertura). |
| **QQQ** | -$6.36 | Primer SELL del viernes cierra long del 13-may con pérdida. Los dos SELL subsiguientes son shorts accidentales (bug #H-5b). |
| Resto (XLU, IWM, GLD, XLP, TLT, SPY) | +$2.17 | Compensaciones menores. |
| **Total realizado** | **-$37.87** | |
| **+ Mark-to-market sobre posiciones aún abiertas al cierre** | -$46.77 | Diferencia con el P&L total Alpaca |
| **TOTAL día 15-may** | **-$84.64** | Coincide con `portfolio/history` |

---

## 3. Bug #H-5b: shorts accidentales en QQQ

### Evidencia en logs

Múltiples advertencias en `sentinel-v0.5/logs/sentinel.log` del 15-may:

```
2026-05-15 09:45:04,864 [WARNING] sentinel.dispatcher — Posiciones fantasma (local pero no en Alpaca): {'IWM', 'TSLA'}
2026-05-15 10:00:04,459 [WARNING] sentinel.dispatcher — Posiciones fantasma (local pero no en Alpaca): {'SPY'}
```

Patrón idéntico al del SPY del 11-may: el cache `dispatcher.open_positions` registra una posición que ya cerró en Alpaca, los Sentinels siguen emitiendo SELL contra ese estado fantasma, y Alpaca abre short porque la posición está a 0.

### Trades específicos que generaron el short QQQ

Tres SELL sobre QQQ el 15-may:
- 09:45:09 SELL 1 @ $707.31 — `side=sell` (cierra long del 13-may a $713.67) ✓ legítimo
- 09:45:14 SELL 1 @ $707.28 — `side=sell_short` ✗ short accidental #1
- 10:30:07 SELL 1 @ $710.85 — `side=sell_short` ✗ short accidental #2

Resultado: **QQQ short -2 shares @ avg $708.48** en Alpaca. Unrealized PnL al sábado: -$0.90 (QQQ en $708.93, posición casi flat porque el subyacente apenas se movió post-fill).

---

## 4. Plan de intervención manual (lunes 18-may apertura)

Replicando el procedimiento exacto del 11-may documentado en `backups/2026-05-11/manual_intervention_spy_short_cleanup.md`. El bot se queda corriendo normal — Roman solo cierra la posición desde Alpaca y Roma se encarga de la reconciliación de registros post-fill.

### 4.1 Acción que ejecuta Roman

**Cuándo:** lunes 18-may, justo a/después de la apertura (09:30 ET).
**Dónde:** https://app.alpaca.markets/paper/dashboard/overview → Positions → QQQ → Close position.
**Parámetros:**
- Symbol: QQQ
- Side: BUY
- Quantity: 2
- Type: Market
- Time in Force: Day
- Position intent: `buy_to_close` (cierra short, no abre long)

**Riesgo de race condition — más alto que el 11-may:**
- El 11-may con SPY parking_brake estaba activo, sin emisiones del dispatcher en el opening.
- Hoy parking_brake=False desde 16-may 00:03 (`can_trade=True`). Si el dispatcher emite un SELL adicional de QQQ entre la apertura y el fill manual (segundos), el cache fantasma engrosaría el short a -3.
- **Mitigación:** Roman envía la orden BUY 2 QQQ con prioridad cuando vea la cuenta abierta. Si quiere blindar, puede mandar la orden el domingo 17-may noche (after-hours, queue para apertura) — Alpaca la procesa al opening cross antes que cualquier ciclo del dispatcher de las 09:30.

### 4.2 Reconciliación post-fill (Roma se encarga vía Alpaca API)

Una vez que Roman avise que ejecutó la orden, sigo el mismo checklist que el 11-may con SPY:

1. **Verificación de cierre limpio** (igual sección 6 del archivo del 11-may):
   - `GET /v2/positions/QQQ` → debe devolver 404 "position does not exist" ✓
   - `GET /v2/orders?status=closed` → confirma `order_id`, `filled_avg_price`, `filled_at`
   - `GET /v2/account` → snapshot post-fill (cash, equity, short_market_value=0, long_market_value, buying_power)
   - `GET /v2/account/activities/FILL?after=<hora del fill>` → confirma el activity con `side=buy`, `qty=2`, `type=fill`
   - Confirmar que `sentinel.log` NO contiene "Orden enviada: QQQ BUY qty=2" — eso prueba que fue intervención externa, no operación del bot.

2. **Cálculo de realized P&L del cierre:**
   - Entry avg del short: $708.48 (de las dos `sell_short` del 15-may 09:45:14 @ $707.28 y 10:30:07 @ $710.85)
   - Exit price: el fill del lunes
   - Realized P&L = (entry - exit) × 2 sh
   - Anotar en sección 7 de este archivo.

3. **Actualización de registros (.md):**
   - **Este archivo:** completar sección 7 (que voy a crear) con los números reales del fill + cambiar sección 8 de ⏳ a ✅.
   - **`CHANGELOG.md`:** convertir el bloque `[Unreleased] — 2026-05-16` de "pendiente" a fill confirmado con cifras, igual que el `[Unreleased] — 2026-05-11` del SPY.
   - **`OBSERVATION_PERIOD.md`:** la sección "Intervención manual 2026-05-16" pasa de "Plan de cierre" a "Fill confirmado" con timestamps y precio.

4. **DB Postgres:** **NO se inserta nada manualmente.** Mismo criterio del 11-may: el trade de Alpaca queda registrado solo en Alpaca y en el archivo de intervención. La tabla `trades` del Postgres solo contiene operaciones que pasaron por el dispatcher del bot — la intervención manual es externa por definición. Esto preserva la limpieza del análisis del 27-may (la auditoría sabe que los trades de la DB son del bot, las intervenciones manuales están en `backups/`).

5. **Marca de datos para el balance del 27-may** (ya cubierta en sección 3):
   - Excluir del análisis de performance del Sentinel responsable: los `sell_short` de QQQ del 15-may 09:45:14 en adelante.
   - Pre-intervención (hasta el fill del lunes): QQQ short -2 sh, ruido de bug.
   - Post-intervención: QQQ vuelve a 0 sh, hasta que algún Sentinel abra legítimamente.

### 4.3 Lo que NO se hace

- NO `sentinel-stop.bat` / `sentinel-start.bat` — el bot queda corriendo, mismo approach que el 11-may.
- NO se modifica el cache `dispatcher.open_positions` — se autocorrige en el próximo ciclo de 15 min cuando lea Alpaca y vea QQQ=0.
- NO se ajustan thresholds, prompts, lógica de agentes — sigue siendo período de observación.
- NO se inserta el trade del cierre en la tabla `trades` de Postgres (preserva limpieza para auditoría del 27-may).

### Marca de datos

- Trades en QQQ entre 2026-05-15 09:45:14 y 2026-05-16 (cierre pendiente): contaminados por bug. Excluir del análisis de performance del Sentinel responsable al cierre del 27-may.
- Posición QQQ post-cierre manual: limpia (0 shares).
- **Riesgo residual:** mismo que con SPY del 11-may — si #H-5b reaparece antes del fix post-27-may en otros símbolos, repetir intervención y documentar.

---

## 5. Análisis adicional del 15-may

### AMD — el trade más caro

- **Sentinel emisor:** S-4 MACD+Volume (`sentinels/__init__.py`)
- **Log de la señal:**
  ```
  2026-05-14 10:45:03 sentinel.sentinels — S-4 MACD+Volume | AMD | BUY @ 448.0500
  (MACD=-0.4683 sig=-0.7391 vol=24123 avg=14555)
  ```
- **Anomalía:** AMD no figuraba como ticker históricamente activo de S-4 (apareció en `sentinel_tickers` desde el 28-abr en S-4 y S-9 pero nunca había emitido señal). Es la PRIMERA operación efectiva de AMD del Sentinel.
- **Warm-up status:** AMD estaba con `0/2 trades` para evaluación de scores parciales. Sin métricas previas, el sizing cayó al piso de 5% (qty=1 plano por el sizing trivial del 11-may).
- **Outcome:** entry a $449.26 (compra market con slippage de +$1.21 sobre la señal), exit a $429.45 → -$19.81. AMD cayó **-4.41%** en el día.

### NVDA — sobre-tradeo

NVDA tuvo 4 trades el 15-may (2 BUY + 2 SELL) más una venta de la posición acumulada del 14-may. El sizing trivial qty=1 implica que el bot está "navegando" el ruido de NVDA sin capturar movimientos grandes. Patrón a vigilar.

### TSLA — exit en apertura

TSLA SELL @ market a las 09:32 (~2 min después de la apertura) sobre el entry del 13-may @ $437.12. Salida en gap-down de apertura del 15-may a $430.38 → -$6.74. Comportamiento técnicamente correcto (ORB-like trigger) pero perdedor en este caso.

---

## 6. Corrección al diagnóstico anterior (importante para auditoría)

En sesión Cowork del 16-may inicialmente reporté que **el bot no había estado operando del 12-may al 16-may** y que las pérdidas eran solo mark-to-market sobre posiciones huérfanas. **Eso fue incorrecto.**

Causa raíz del error: el sandbox de Cowork tenía un snapshot stale del filesystem que mostraba `sentinel.log` truncado en el 12-may 20:04. Las herramientas `Read`/`Grep` (que sí leen el archivo actualizado) revelaron las 22,082 líneas reales con actividad continua del bot del 25-abr al 16-may, incluyendo todos los trades del 13-15 may.

**Lección para BUENAS_PRACTICAS_V2 / PROTOCOL_SESSION:** cuando un análisis dependa de `logs/*.log` o cualquier archivo escrito en tiempo real, **siempre cross-check** entre el bash del sandbox y las file-tools (Read/Grep) para detectar staleness. Si discrepan, confiar en las file-tools o en una llamada directa a la API (en este caso Alpaca).

---

## 7. Referencias cruzadas

- **CHANGELOG.md** — agregar bloque `[Unreleased] — 2026-05-16` con resumen.
- **OBSERVATION_PERIOD.md** — agregar sección "Intervención manual 2026-05-16: cierre de short QQQ accidental por bug #H-5b" en la lista de intervenciones registradas.
- **TECHDEBT.md** / **NEXT_ITERATION.md** — el fix definitivo de #H-5b sigue pendiente para post-27-may. Mientras tanto, considerar agregar guardrails read-only de detección automática (alerta cuando aparece "Posiciones fantasma" en log) para no depender de revisión manual.
- **`backups/2026-05-11/manual_intervention_spy_short_cleanup.md`** — precedente. Mismo bug, mismo procedimiento.

---

## 7. Ejecución del cierre — PENDIENTE (a completar tras el fill del lunes)

*Esta sección se rellena cuando Roman ejecute la orden y Roma verifique vía Alpaca API. Mismo formato que la sección "Ejecución real" del archivo del 11-may.*

### 7.1 Orden enviada (Roman) — CONFIRMADO via Alpaca API 2026-05-16

- **Submitted at:** 2026-05-17T21:17:05.659031529Z (= 17:17 ET, after-hours del sábado)
- **Symbol:** QQQ
- **Side:** BUY
- **Quantity:** 2
- **Type:** Market
- **Order ID:** `47b0c814-8677-4bd3-9178-a4c570ae9e15`
- **Client Order ID:** `9be6fd38-375b-40e4-9497-ddcd61c1d156`
- **Position intent:** `buy_to_close` ✓
- **Time in Force:** day
- **Estado al envío:** `accepted` (queued para opening cross)
- **Expires at:** 2026-05-18T20:00:00Z (lunes 18-may 16:00 ET, fin del día de trading)
- **Ejecución esperada:** lunes 18-may 09:30:00 ET (opening cross) — Alpaca resubmits automáticamente al inicio de RTH

### 7.2 Ejecución real (verificada vía Alpaca API 2026-05-18 09:35 ET)

- **Submitted at (UTC / ET):** 2026-05-18T08:00:20.121289781Z / 2026-05-18 04:00:20 ET (re-submission automática del re-routing al opening cross; envío original del usuario fue 2026-05-17T21:17:05 UTC = 17:17 ET del sábado)
- **Filled at (UTC / ET):** 2026-05-18T13:30:41.297050442Z / **2026-05-18 09:30:41 ET** (41 segundos post-apertura)
- **Filled qty:** **2** / 2 ✅
- **Filled avg price:** **$711.31**
- **Status final:** `filled` ✅
- **Fees:** $0 (paper trading)

### 7.3 Estado de la cuenta post-fill

- Posición QQQ: **404 "position does not exist"** ✅ — short cerrado limpiamente
- Cash: **$99,199.61** (pre-fill: $99,883.07; delta = -$683.46 = ajuste del settlement del short más el cierre del long mark-to-market — coherente con paper account dynamics)
- Equity: **$100,081.85** (pre-fill: $100,087.20; delta intradía = -$5.35)
- Short market value: **$0** ✅
- Long market value: **$882.24** (las posiciones long del bot abrieron el lunes con marcas distintas; ver 7.5)
- Buying power: $396,700.96 (regt: $199,281.46)
- balance_asof: 2026-05-15

### 7.4 Realized P&L del cierre

- Entry avg (short open): $708.48 (avg de los dos sell_short del 15-may 09:45:14 @ $707.28 y 10:30:07 @ $710.85)
- Exit price: **$711.31**
- Realized P&L: **(708.48 − 711.31) × 2 = −$5.66** (pérdida — el opening cross del lunes salió ~+0.40% sobre el avg del short, así que el bug costó esos ~$5.66 adicionales sobre el #H-5b del 15-may)
- Costo total acumulado del bug #H-5b en QQQ: P&L del 15-may en QQQ (−$6.36) + cierre del 18-may (−$5.66) = **−$12.02** sobre el equity de ~$100K (~−0.012%, ruido del período de observación pero documentado para análisis del 27-may).

### 7.5 Race condition con el bot

- **NO orden enviada por el bot:** `Grep` sobre `sentinel.log` con patrón `^2026-05-18.*Orden enviada.*QQQ BUY qty=2` → **0 matches**. Confirma intervención externa, no operación del bot. ✅
- **Race condition DETECTADA pero MITIGADA por el dispatcher:**
  - 09:30:34 — S-8 RSI Divergence emite señal **BUY QQQ @ $712.14** (post bullish div price 708.5650→706.9200 RSI 28.23→31.79). El log dice: `[INFO] sentinel.sentinels — S-8 RSI Divergence | QQQ | BUY @ 712.1400`.
  - 09:30:36 — Dispatcher WARNING: `Posiciones no rastreadas (Alpaca pero no local): {'SPY', 'QQQ', 'XLU', 'XLV', 'TLT', 'AAPL', 'XLP', 'NVDA'}` — el cache local sigue desincronizado del estado real de Alpaca (efecto colateral del bug #H-5b en el path de arranque de la sesión).
  - 09:30:41 — Fill manual del BUY 2 QQQ @ $711.31 (cierre del short).
  - 09:30:43 — Dispatcher: `[INFO] sentinel.dispatcher — Señal BUY QQQ omitida — ya hay posición abierta este cycle.` La protección anti-duplicado funcionó: el dispatcher detectó que "ya había" una posición abierta en QQQ este ciclo (el fill recién acababa de ocurrir) y descartó la señal de S-8. **Sin esta protección, el bot habría enviado un BUY 1 QQQ adicional y la cuenta habría quedado long +1 después del cierre manual.**
- **Conclusión sobre #H-5b:**
  - El bug del cache `dispatcher.open_positions` desactualizado **sigue presente** (mensaje "Posiciones no rastreadas" en el ciclo de apertura).
  - La protección dispatcher de "señal omitida — ya hay posición abierta" funcionó como red de seguridad y previno una operación errónea.
  - **Recomendación post-27-may:** el fix definitivo de #H-5b debe abordar el sync del cache al arranque y post-fill, pero la guardrail actual mitiga buena parte del riesgo de ejecución duplicada. Documentar en NEXT_ITERATION.md como hallazgo.

---

## 8. Estado de verificación

| Item | Status |
|---|---|
| Análisis P&L del 15-may por símbolo | ✅ Completado (Alpaca API /v2/account/activities/FILL) |
| Identificación de trades fantasma en log | ✅ Completado (sentinel.log grep) |
| Confirmación del Sentinel responsable de AMD | ✅ S-4 MACD+Volume |
| Confirmación posición QQQ short -2 | ✅ Alpaca /v2/positions |
| Documento de incidente (este archivo) | ✅ Creado |
| Actualización CHANGELOG.md | ✅ Bloque `[Unreleased] — 2026-05-16` agregado (a actualizar con cifras post-fill) |
| Actualización OBSERVATION_PERIOD.md | ✅ Sección "Intervención manual 2026-05-16" agregada (a actualizar con cifras post-fill) |
| Cierre manual del short QQQ en Alpaca | ✅ Completado (Roman, sábado 16-may 17:17 ET; fill lunes 18-may 09:30:41 ET @ $711.31) |
| Verificación post-fill vía Alpaca API | ✅ Completado (Roma, lunes 18-may 09:35 ET, scheduled task `qqq-short-fill-verification`) |
| Sección 7 completada con números reales | ✅ Completado |
| CHANGELOG.md actualizado con cifras finales | ✅ Completado |
| OBSERVATION_PERIOD.md actualizado con fill confirmado | ✅ Completado |
