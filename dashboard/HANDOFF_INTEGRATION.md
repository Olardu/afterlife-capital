# Handoff ↔ API real — mapeo de datos

Branch: `feature/design-handoff-integration`
Fecha: 2026-04-25

Este documento mapea las variables/campos que `sentinel-app.js` (handoff oficial)
consume contra los endpoints reales de `sentinel-v0.5/api.py`.

`sentinel-app.js` no se modifica (se copia tal cual del handoff). El trabajo
se concentra en `sentinel-data.js` reescrito para poblar las globales con
datos de la API en lugar del mock original.

---

## Globales que `sentinel-app.js` consume

`SENTINELS`, `AGENTS`, `AGENT_ICONS`, `NEWS`, `STATE`, `PRICES`, `I18N`.

`I18N` viene de `sentinel-i18n.js` (no se toca).
`SENTINELS`/`AGENTS`/`AGENT_ICONS`/`NEWS`/`STATE`/`PRICES` los provee el nuevo `sentinel-data.js`.

---

## Tabla de mapeo

| Global handoff | Campo handoff | Endpoint API | Campo respuesta | Notas |
|---|---|---|---|---|
| `SENTINELS[i]` | `id` | derivado | índice → `S-1`..`S-9` | API usa UUID. Mapeo por orden de strategy_type |
| `SENTINELS[i]` | `name` | hardcoded en map | — | `MORPHEUS`, `MANTIS`, etc. — derivado de `strategy_type` |
| `SENTINELS[i]` | `stratKey` | mapping local | strategy_type → stratKey | `sma_crossover` → `sma_xover`, `bollinger_bounce` → `bb_bounce`, etc. |
| `SENTINELS[i]` | `tickers` | `/api/sentinels` | `tickers[].ticker` | array de strings |
| `SENTINELS[i]` | `sig` | `/api/sentinels` | `tickers[0].last_signal` | el handoff espera UN sig por sentinel, la API tiene uno por ticker. Tomamos el primero ≠ HOLD si existe, sino el primero |
| `SENTINELS[i]` | `win` | `/api/sentinels` | promedio de `tickers[].win_rate` | API tiene win por ticker |
| `SENTINELS[i]` | `sharpe` | `/api/sentinels` | promedio de `tickers[].sharpe_ratio` | idem |
| `SENTINELS[i]` | `alloc` | `/api/sentinels` | `allocation_pct / 100` | API devuelve 5.0 → handoff espera 0.05 |
| `SENTINELS[i]` | `quote*` | hardcoded en sentinel-data.js | — | citas en ES/EN/JA/TH copiadas tal cual del handoff original |
| `AGENTS` | (5 agentes) | hardcoded | — | Dispatcher, CorrelationGuard, The Ear, Historian, RegimeClassifier — copiados tal cual del handoff |
| `AGENTS[i].active` | bool | `/api/status` | derivado | `dispatcher.active = !circuit_breaker`, `the_ear.active = !circuit_breaker`, `regime.active = false` (S-10 desactivado), otros por defecto del handoff |
| `AGENT_ICONS` | SVG strings | hardcoded | — | copiados tal cual del handoff |
| `NEWS[i]` | `ts` | `/api/macro` | `recent_events[i].created_at` (HH:MM) | formateado |
| `NEWS[i]` | `titleKey` | `/api/macro` | derivado | clave i18n no aplica con datos dinámicos — uso `title` directo en string compuesto con risk_score |
| `NEWS[i]` | `impact` | `/api/macro` | derivado | `circuit_breaker_triggered=true → 'cb'`, `risk_score>0.5 → 'risk'`, sino `'neutral'` |
| `STATE.lang` | string | localStorage | — | persistencia local |
| `STATE.view` | string | localStorage | — | idem |
| `STATE.theme` | string | localStorage | — | idem |
| `STATE.balance` | number | **no API** | — | placeholder hasta que `/api/account/equity` exista (TODO en backend) |
| `STATE.balanceChange` | number | **no API** | — | placeholder, calcular cuando haya `balance` real |
| `STATE.riskScore` | number | `/api/status` | `risk_score` | float 0-1 |
| `STATE.trades` | array | `/api/trades?limit=50` | array | mapeo: `id← derivado de hash trade_id`, `sent ← derivado, sentName ← sentinel_name, ticker, side, qty, px ← filled_price, status, ts ← created_at HH:MM:SS` |
| `STATE.logs` | array | `/api/macro` | derivado de `recent_events` | sintetizar líneas log a partir de macro events |
| `STATE.equityHist` | number[] | **no API** | — | placeholder: derivado de cumulative slippage * qty * sign(side) sobre trades. Comentado como TODO. |
| `STATE.nextId` | number | derivado | — | `trades.length` o último id+1 |
| `PRICES` | object ticker→price | **no API** | — | placeholder: usado solo por el tick mock; con SSE real el render se refresca con datos de `/api/sentinels` |

---

## Endpoints consumidos vs handoff

| `sentinel-app.js` consume | Endpoint API real | Estado |
|---|---|---|
| `SENTINELS` con sig, win, sharpe, alloc, tickers | `/api/sentinels` | ✅ matchea (con mapeo) |
| `STATE.riskScore`, sentinels active count, regime | `/api/status` | ✅ matchea |
| `STATE.trades` | `/api/trades?limit=50` | ✅ matchea (con mapeo) |
| `NEWS` con título y impact | `/api/macro` recent_events | ⚠️ degradado (no hay título real, derivado de risk_score) |
| Performance por sentinel | `/api/performance` | ✅ matchea (no se usa directo, ya está en `/api/sentinels`) |
| Tick loop (signal + log + trade nuevo) | `/api/sse` | ✅ reemplaza setInterval con EventSource |
| Balance de cuenta, P&L del día, posiciones abiertas | **no existe en API** | ❌ placeholder. Mostrar `—` hasta que se agregue endpoint `/api/account/equity` |
| Equity history series | **no existe en API** | ⚠️ placeholder construido sintéticamente desde trades |

---

## Mapeo `strategy_type` → `stratKey` del handoff

```
sma_crossover     → sma_xover
rsi_short         → rsi_short
bollinger_bounce  → bb_bounce
macd_volume       → macd_vol
orb_breakout      → or_breakout
ema_triple        → ema_triple
vwap_reversion    → vwap_revert
rsi_divergence    → rsi_diverg
bollinger_squeeze → bb_squeeze
```

El handoff usa estas keys para resolver i18n (`desc_sma_xover`, etc.).

---

## SSE — reemplazo del tick loop

`sentinel-app.js` original llama `setTimeout(tick, 2500)` en el boot. El nuevo
`sentinel-data.js` reemplaza eso conectándose a `/api/sse`:

```js
const sse = new EventSource('/api/sse');
sse.addEventListener('update', e => {
  const payload = JSON.parse(e.data);
  // refrescar SENTINELS, STATE.trades, STATE.riskScore desde la API
  reloadFromAPI().then(() => renderAll());
});
```

`reloadFromAPI()` hace `Promise.all([fetch /api/status, /api/sentinels, /api/trades, /api/macro])`
y popula las globales. Después dispara `renderAll()` (función de
`sentinel-app.js`) para refrescar la UI.

El boot (`setTimeout(tick, 2500)` y `applyI18n()`) se sobrecarga: en el nuevo
sistema el boot de `sentinel-data.js` hace el primer `reloadFromAPI()` y
luego abre el SSE. `applyI18n()` se llama después.

---

## Limitaciones declaradas

Lo siguiente queda como placeholder porque la API actual no lo provee (y
**no se puede tocar `api.py`**):

1. **Balance total y P&L del día** — el handoff muestra `$100,255.63` y
   `+$425.80`. Sin endpoint `/api/account/equity` o similar, mostramos `—`.
2. **Posiciones abiertas count** — el handoff muestra `5`. Sin endpoint, `—`.
3. **Señales procesadas / aprobadas / rechazadas** — el handoff muestra `23 (18/5)`.
   Sin endpoint, `—`.
4. **Equity history series real** — el handoff muestra una curva de 24h.
   Construyo placeholder sintético desde trades.
5. **News titles reales** — el handoff muestra titulares ("Fed cuts rates...").
   La API de macro_events solo tiene risk_score numérico. Sintetizamos un
   string descriptivo: `Macro update — risk={x.xx} VIX{y.y%} SPY{z.z%}`.
6. **Logs reales del sistema** — el handoff muestra logs de tipo bash. La
   API solo expone macro_events. Sintetizamos log lines a partir de eso.

Estas limitaciones se documentan en `dashboard/README.md` y `CHANGELOG.md`
con comentarios `TODO: extender API`.
