# Intervención manual — Cierre de posición short SPY accidental

**Fecha:** 2026-05-11
**Ejecutor:** Roman Olarte (manual, vía Alpaca Dashboard)
**Naturaleza:** Corrección de bug, NO operación del bot
**Período de observación protegida:** activo (27-abr → 27-may)

---

## Contexto del bug que originó la posición

**Bug:** `#H-5b` — Cache desactualizado en `dispatcher.open_positions` tras SELL exitoso.

**Causa raíz documentada en:** `backups/2026-05-08/audit_sentinels_long_short.md`.

**Resumen:** `dispatcher.process_signal` solo actualiza `self.open_positions` en BUY filled, nunca elimina entries tras SELL filled. Dentro del mismo cycle, después de una SELL que cierra una posición long, el cache queda desactualizado. Un segundo SELL en el mismo ticker pasa el check `if ticker not in self.open_positions` (que mira al cache obsoleto) y termina abriendo short en Alpaca.

**Evidencia operativa:**

- 2026-05-08: descubierto inicialmente con SPY short -2 shares.
- 2026-05-11: posición empeoró a SPY short -4 shares (2 SELLs adicionales generaron shorts).

**Fix del bug:** anotado en `NEXT_ITERATION.md` como item #H-5b, para implementar post-27-may. NO se implementa durante observación por regla 4 de `OBSERVATION_PERIOD.md`. El fix es de 2 líneas (`self.open_positions.pop(ticker, None)` en SELL filled).

---

## Estado pre-intervención (verificado contra Alpaca API)

Posición SPY a las 22:20 ET del 2026-05-11:

```json
{
  "symbol": "SPY",
  "qty": "-4",
  "side": "short",
  "avg_entry_price": "737.818",
  "current_price": "738.15",
  "market_value": "-2952.6",
  "cost_basis": "-2951.272",
  "unrealized_pl": "-1.328",
  "unrealized_plpc": "-0.00045"
}
```

Estado de la cuenta:

```
account_number: PA36P9MDPXCD
equity: $100,161.34
cash: $101,157.69
buying_power: $393,933.50
shorting_enabled: true
```

---

## Justificación de la intervención

**Por qué se cierra ahora y no se espera al fin del período de observación:**

1. La posición crece sin control hasta que se fixee #H-5b. Cada día con SELLs concurrentes en SPY agrega más shares al short. De -2 a -4 en 3 días → probable que llegue a -8 a -16 al cierre del período.
2. El short distorsiona las métricas del período de observación: el portfolio agregado tiene exposición direccional NO intencional al lado bajista del S&P 500.
3. Es una posición que el sistema NUNCA debió abrir. No representa una decisión del bot, representa un bug del Dispatcher.
4. Cerrarla manualmente y documentarlo es más limpio que dejarla crecer y luego intentar segregar el ruido en el análisis del 27-may.

**Por qué califica como excepción permitida del período de observación:**

`OBSERVATION_PERIOD.md` sección "PERMITIDO" punto 1: "Bug fixes críticos. Definición: pierde dinero por error técnico (ej: orden duplicada, persistencia rota)."

El short de SPY es exactamente eso: pérdida potencial (si el mercado sube, el short pierde) por error técnico (cache obsoleto, no decisión del bot). La corrección manual no modifica lógica ni thresholds, solo deshace el efecto del bug.

---

## Acción ejecutada

**Orden enviada:** 2026-05-11 22:27:34 ET (Roman vía Alpaca Dashboard).

**Parámetros:**
- Symbol: SPY
- Side: BUY
- Quantity: 4
- Type: Market
- Time in Force: Day
- Order ID: `6d9e9533-d2f5-4299-9dd8-abf456f2506e`
- Position intent: `buy_to_close`

**Estado al momento del envío:** `accepted` — mercado cerrado al momento del envío (after-hours), orden queued para ejecutar en el opening del próximo día de trading.

### Ejecución real (verificada vía Alpaca API 2026-05-12 09:45 ET)

- **Submitted at:** 2026-05-12T08:00:25 UTC (= 04:00:25 ET, resubmisión automática de Alpaca para sesión RTH)
- **Filled at:** 2026-05-12T13:31:32 UTC (= **09:31:32 ET**, ~90 segundos después del opening cross)
- **Filled qty:** 4 / 4
- **Filled avg price:** **$736.685**
- **Status final:** `filled`
- **Fees:** $0 (paper trading)

**Estado de la cuenta post-fill (snapshot 2026-05-12 09:45 ET):**
- Posición SPY: **NO existe** (`GET /v2/positions/SPY` → HTTP 404 "position does not exist") ✅
- Cash: **$98,155.16** (de $101,157.69 pre-intervención → delta -$3,002.53; coste de 4 sh × $736.685 = $2,946.74 + ~$56 de pequeños movimientos del día)
- Equity: **$100,168.01** (vs $100,161.34 pre-intervención → +$6.67)
- Short market value: **$0** ✅
- Long market value: $2,012.85
- Buying power: $394,063.86

**Realized P&L del short:** entry avg $737.818 vs exit $736.685 = **+$1.133/share × 4 = ~+$4.53 ganancia realizada** (gap-down en el opening cross favoreció el cierre).

**Race condition con el bot — NO se materializó:**
- `sentinel.log` confirma que el bot tiene la última entrada el 2026-05-11 22:18:37 ET con `parking_brake=True` activo (no emite trades). El bot **no estaba operando hoy 12-may** durante el opening, por lo que el bug #H-5b no tuvo oportunidad de emitir un SELL adicional sobre SPY antes del fill.
- Confirmado: la orden BUY 4 SPY del 11-may fue intervención externa (no aparece en logs del bot como "Orden enviada SPY BUY qty=4").

**Resultado:** posición SPY netada limpiamente a 0. **Evento cerrado.**

---

## Trazabilidad para el balance del 27-may

**Para el análisis de performance del período de observación, considerar:**

1. **Esta intervención fue manual, no del bot.** Cualquier trade en SPY con timestamp del 2026-05-11 cuyo origen NO sea una `signal` previa del bot debe excluirse del análisis de performance de los Sentinels.

2. **Trades históricos en SPY del 2026-05-08 al 2026-05-11 son ruido de bug.** Los SELLs que generaron el short están en `trades` pero NO se generaron por decisión técnica del Sentinel emitir SELL — se generaron porque el dispatcher dejó pasar SELLs sobre posiciones que ya estaban cerradas en Alpaca. Marcar estos en el análisis.

3. **La intervención no resetea el bug.** Hasta que se implemente el fix de #H-5b post-27-may, **shorts accidentales pueden volver a ocurrir**. Si reaparecen, repetir esta intervención y documentar similarmente.

4. **Marca de datos del período de observación:**
   - Pre-intervención (2026-05-08 al 2026-05-11 22:20 ET): contiene ruido de short SPY accidental.
   - Post-intervención (2026-05-11 22:20+ ET): cuenta sin posición SPY, hasta que el bot abra una nueva legítimamente.
   - Si el bug se vuelve a manifestar (probable, no está fixeado), se anota como nueva intervención.

---

## Verificación post-intervención

Después de ejecutar la orden, Roma (Claude) verificará vía Alpaca API que:

- Posición SPY no aparece en `GET /v2/positions` (qty = 0).
- Trade aparece en `GET /v2/orders?status=closed` con side=buy, qty=4, status=filled.
- Cash actualizado en `GET /v2/account` (reducido en ~$2,953).
- El log del bot (`sentinel.log`) NO contiene línea de "Orden enviada SPY BUY qty=4" — confirma que fue intervención externa, no operación del bot.

Una vez verificado, se actualiza este documento con timestamp y precio de fill reales.

---

## Posiciones esperadas POST-intervención

Una vez cerrado el short:

| Side | Ticker | Qty | Nota |
|---|---|---|---|
| LONG | GLD | 1 | Posición legítima del bot |
| LONG | IWM | 1 | Posición legítima del bot |
| LONG | MSFT | 1 | Posición legítima del bot |
| LONG | NVDA | 1 | Posición legítima del bot |
| LONG | TLT | 1 | Posición legítima del bot (Mantis post-cleanup) |
| LONG | TSLA | 1 | Posición legítima del bot |
| LONG | XLP | 1 | Posición legítima del bot |

Notar: SPY queda eliminado, XLU no aparece (Mantis aún no entró en XLU). Si XLU aparece después, es porque Mantis lo operó legítimamente.

---

*Documento creado el 2026-05-11. Actualizar tras ejecución manual con timestamps y precios reales.*
