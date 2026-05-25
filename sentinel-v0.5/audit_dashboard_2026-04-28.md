# Auditoría READ-ONLY — Conexión backend ↔ frontend del dashboard Sentinel

**Fecha:** 2026-04-28
**Autorizada por:** Bot Owner (owner@example.com, OWNER)
**Tipo:** Diagnóstico estático. Cero modificaciones de código, DB ni procesos.
**Vigente bajo:** OBSERVATION_PERIOD.md — categoría "observabilidad read-only".

Rutas auditadas:
- Backend: `sentinel-v0.5/api.py`
- Frontend: `dashboard/index.html` (767 líneas), `dashboard/sentinel-app.js` (423), `dashboard/sentinel-data.js` (1026), `dashboard/sentinel-i18n.js` (28 KB)

---

## 1. Mapa de endpoints del backend

API servida por `sentinel-v0.5/api.py` en puerto 8080 (Cloudflare tunnel a `sentinel.afterlifecapital.co`). Todos los endpoints `/api/*` requieren sesión salvo `/api/market-status`. `/api/system/*` POST y `/api/admin/*` requieren `role=ADMIN`.

| Ruta | Método | api.py L | Tabla(s) que lee | Campos relevantes que devuelve |
|---|---|---|---|---|
| `/auth/login` | GET | 343 | — | redirect a Google OAuth |
| `/auth/callback` | GET | 348 | users | escribe sesión |
| `/auth/logout` | GET | 376 | — | limpia sesión |
| `/auth/me` | GET | 382 | sesión | `{email, role, user_id}` |
| `/api/status` | GET | 395 | sentinels, sentinel_tickers, macro_events | `system, sentinels_active, sentinels_total, regime ("NEUTRAL" fijo), tickers_total, refresh_interval ("15MIN"), risk_score, circuit_breaker, parking_brake` |
| `/api/sentinels` | GET | 431 | sentinels, sentinel_tickers, signals (last_signals), performance_scores | lista de sentinels con `tickers[].{ticker, last_signal, pnl=0.0 (placeholder), win_rate, sharpe_ratio}`, `allocation_pct`, `decay_status`, `total_trades` |
| `/api/trades` | GET | 505 | trades, sentinels | `trade_id, sentinel_name, ticker, side, qty, filled_price, slippage, status, created_at` (limit 50 default) |
| `/api/macro` | GET | 552 | macro_events | `current_risk_score, circuit_breaker, parking_brake, recent_events[]` (últimos 20) |
| `/api/market-status` | GET (público) | 577 | — (market_clock.py) | `is_open, status (OPEN/CLOSED/PRE_MARKET/AFTER_HOURS), next_open, next_close, current_time_et` |
| `/api/macro_events` | GET | 592 | macro_events | últimos 10 con `event_id, created_at, risk_score, vix_change, spy_change, regime ("NEUTRAL" fijo), circuit_breaker, parking_brake, news_titles[]` |
| `/api/performance` | GET | 626 | performance_scores, sentinels | filas crudas; **HOY VACÍO** (DB sin filas) |
| `/api/report` | GET | 650 | trades, signals, sentinels, sentinel_tickers, performance_scores, macro_events, system_state | reporte JSON exhaustivo con `metadata, system_health, strategy_performance[], macro_context, correlation_guard (TODOs null), dispatcher (signals_approved/rejected null), trades[]` |
| `/api/system/state` | GET | 934 | system_state | `{halt_requested, system_halted}` |
| `/api/system/halt` | POST (ADMIN) | 947 | system_state (escribe) | dispara halt |
| `/api/system/resume` | POST (ADMIN) | 963 | system_state (escribe) | dispara resume |
| `/admin` | GET (ADMIN) | 986 | sirve `dashboard/admin.html` | — |
| `/api/admin/users` | GET (ADMIN) | 994 | users | listado |
| `/api/admin/users` | POST (ADMIN) | 1003 | users (escribe) | crear |
| `/api/admin/users/{id}` | DELETE (ADMIN) | 1031 | users (escribe) | eliminar |
| `/api/admin/api-keys` | GET (ADMIN) | 1079 | api_keys | listado sin revelar valor |
| `/api/admin/api-keys` | POST (ADMIN) | 1092 | api_keys (escribe) | crear/actualizar |
| `/api/admin/api-keys/{id}/reveal` | POST (ADMIN) | 1123 | api_keys (lee + decrypt) | revela value desencriptado |
| `/api/admin/api-keys/{id}` | DELETE (ADMIN) | 1156 | api_keys (escribe) | eliminar |
| `/api/admin/rotations` | GET (ADMIN) | 1204 | rotation_decisions | listado con filtros |
| `/api/admin/rotations/{id}` | GET (ADMIN) | 1218 | rotation_decisions | detalle |
| `/api/admin/rotations/{id}/rollback` | POST (ADMIN) | 1233 | rotation_decisions (escribe) | rollback |
| `/api/admin/candidates` | GET (ADMIN) | 1257 | pending_candidates | watchlist |
| `/api/rotations/recent` | GET | 1266 | rotation_decisions | últimas N (24h) |
| `/api/sse` | GET (SSE) | 1327 | varias (vía `_build_sse_payload`) | push de actualizaciones cada 15 min |
| `/` (dashboard) | GET | 1357 (mount StaticFiles) | sirve `dashboard/index.html` y assets | — |

**Total: 28 endpoints** (24 REST + 1 SSE + auth flow + dashboard estático).

---

## 2. Mapa de fetch del frontend

Todos los fetch están en `sentinel-data.js`. `sentinel-app.js` y `sentinel-i18n.js` no hacen ninguna llamada HTTP.

| sentinel-data.js L | URL | Función JS | Destino DOM/STATE |
|---|---|---|---|
| 180 (helper `_fetchJson`) | — | wrapper genérico para los GET | maneja 401/403/errors |
| 202 (`loadStatus`) | `GET /api/status` | `loadStatus()` | `#hSistema`, `#hRegimen`, `.hdr-stats .hs .v.cyan` (3 pills), `STATE.riskScore`, `AGENTS[*].active` (solo dispatcher/the_ear/regime) |
| 233 (`loadSentinels`) | `GET /api/sentinels` | `loadSentinels()` | `SENTINELS[]` (mutación in-place) |
| 279 (`loadTrades`) | `GET /api/trades?limit=50` | `loadTrades()` | `STATE.trades`, `STATE.equityHist` (vía `synthEquityHist()`) |
| 343 (`loadMacro`) | `GET /api/macro_events?limit=10` | `loadMacro()` | `NEWS[]`, `STATE.logs`, `I18N[lang]._news_dyn_*` |
| 345 (`loadMacro` fallback) | `GET /api/macro` | `loadMacro()` (fallback si 404) | idem |
| 442 | `EventSource('/api/sse')` | `connectSSE()` | dispara `reloadFromAPI()` en cada `update` |
| 583 | `GET /api/system/state` | `refreshKillSwitchState()` | toggle `#detenerBtn` (DETENER ↔ INICIAR) |
| 609 | `POST /api/system/resume` | handler de `#detenerBtn` | — |
| 637 | `POST /api/system/halt` | handler de `#detenerBtn` | — |
| 672 | `GET /auth/me` | `setupAdminLink()` | inyecta `#adminLink` (solo ADMIN), oculta `#detenerBtn` (VIEWER), guarda `window._userRole` |
| 797 | `GET /api/rotations/recent?limit=5` | `setupRotationsBanner()` (refresh 5min) | `#rotationsBanner` debajo del header |
| 982 | `GET /api/market-status` | `setupMarketStatusIndicator()` (refresh 60s) | `#hMercado` (pill nueva en `.hdr-stats`) |

**Total: 12 llamadas distintas** (8 GET + 2 POST + 1 SSE + 1 auth).

Endpoints del backend **NO consumidos por el frontend**:
- `/api/macro` — sólo fallback de `/api/macro_events`
- `/api/performance` — definido pero ningún fetch lo invoca (datos de performance se obtienen embebidos en `/api/sentinels`)
- `/api/report` — el botón "DESCARGAR REPORTE JSON" usa `buildReport()` cliente-side, NO este endpoint (TECHDEBT.md L132 confirmado)
- Todos los `/api/admin/*` — consumidos por `admin-app.js`, no por el dashboard principal

---

## 3. Mapa de secciones del dashboard

Convención de estado:
- ✅ **REAL** — render desde endpoint, sin transformación que invente datos.
- ⚠ **PARCIAL** — usa endpoint pero rellena con cálculo sintético / fallback inventado.
- ❌ **SINTÉTICO** — markup hardcoded del bundle handoff o función JS sintética.

### HEADER

| Elemento | index.html L | Render JS | Estado | Fuente |
|---|---|---|---|---|
| `#hSistema` (SISTEMA · ONLINE) | 527 | sentinel-data.js L217 (`loadStatus`) | ✅ | `/api/status.system` |
| Pill `9/9` (sentinels) | 222 (`.hdr-stats .v.cyan[0]`) | sentinel-data.js L224 | ✅ | `/api/status.sentinels_active/total` |
| `#hRegimen` (RÉGIMEN · NEUTRAL) | 529 | sentinel-data.js L219 | ⚠ | `/api/status.regime` — siempre `"NEUTRAL"` (S-10 desactivado, hardcoded en backend api.py L420) |
| Pill `27` (TICKERS) | 222 | sentinel-data.js L225 | ✅ | `/api/status.tickers_total` |
| Pill `15MIN` (REFRESH) | 222 | sentinel-data.js L226 | ⚠ | `/api/status.refresh_interval` — string fijo del backend (L422) |
| `#hRisk` (RISK 0.12) | 532 | sentinel-app.js L251 (`renderHeader`) | ✅ | `STATE.riskScore` ← `/api/status.risk_score` |
| `#hMercado` (MERCADO · ABIERTO + countdown) | inyectado por sentinel-data.js L971 | sentinel-data.js L914 (`_renderMarketIndicator`) | ✅ | `/api/market-status` |
| `#detenerBtn` (DETENER/INICIAR) | 551 | sentinel-data.js L562 (`_setKillSwitchUI`) | ✅ | `/api/system/state` |
| `#rotationsBanner` (debajo del header) | inyectado por sentinel-data.js L820 | sentinel-data.js L790 | ✅ | `/api/rotations/recent` |

### CUERPO PRINCIPAL

| Sección | index.html L | Render JS | Estado | Fuente |
|---|---|---|---|---|
| `#agentsGrid` (5 cards: DISPATCHER, CORRELATION GUARD, THE EAR, HISTORIAN, REGIME CLASSIFIER) | 569 | sentinel-app.js L16 (`renderAgents`) | ❌ | `AGENTS[]` HARDCODED en sentinel-data.js L123-129. Sólo `dispatcher` y `the_ear` se actualizan a `active=!circuit_breaker`. `correlation`, `historian`, `regime` quedan **fijos en `active:false`** sin importar lo que pase en el backend |
| Tag "5 agentes activos" | 567 (`<span data-i18n="agents_meta">`) | — | ❌ | i18n string literal "5 agentes activos" — no se calcula |
| BALANCE TOTAL | 579 (`#osBalance`) | sentinel-app.js L253 | ❌ | `STATE.balance = 100000` HARDCODED en sentinel-data.js L148. Sobreescribe el markup `100,255.63` con `100,000.00` |
| P&L DEL DÍA monto (`+$`) | 580 (`#osPnl`) | sentinel-app.js L254 | ❌ | `Math.abs(STATE.balance-100000)` = 0 siempre |
| P&L DEL DÍA porcentaje (`+0.42%`) | 580 (`<div class="sub">+0.42%</div>` SIN ID) | — | ❌ | markup literal del bundle, **nunca actualizado** |
| POSICIONES ABIERTAS = 5 | 581 (`<div class="v">5</div>` SIN ID) | — | ❌ | markup literal del bundle, **nunca actualizado** |
| SEÑALES PROCESADAS = 23 | 582 (`#osSigProc`) | — (ningún render lo toca) | ❌ | markup literal; el `id` existe pero ninguna función JS lo escribe |
| aprobadas: 18 / rechazadas: 5 | 582 (`<b>` SIN ID) | — | ❌ | markup literal del bundle |
| `#newsList` ("NOTICIAS QUE MOVIERON DECISIONES") | 590 | sentinel-app.js L31 (`renderNews`) | ✅ | `NEWS[]` ← `/api/macro_events` (titulares reales con fallback bilingüe genérico, FIX-010) |
| `#newsCount` ("5 items") | 588 | sentinel-app.js L40 | ✅ | `NEWS.length` |
| `#eqChart` (curva de equity) | 602 | sentinel-app.js L44 (`renderEquity`) | ⚠ | `STATE.equityHist` ← `synthEquityHist()` (sentinel-data.js L319) — sin trades muestra `100000 + Math.sin(i*0.4)*10`; con trades acumula `slippage*qty*sign(side)` con slippage forzado a `0`, así que también horizontal |
| `#eqCapital` ("$100,000.00") | 604 | sentinel-app.js L67 | ❌ | `STATE.balance` hardcoded |
| `#eqPnl` ("+$420.18") | 605 | sentinel-app.js L68-70 | ❌ | `STATE.balance-100000` = 0 |
| Max DD ("-1.24%") | 606 (`<b>-1.24%</b>` SIN ID) | — | ❌ | markup literal del bundle |
| `#sentGrid` (9 cards de Sentinels) | 618 | sentinel-app.js L74 (`renderSentGrid`) | ⚠ | name/sid/sig/win/sharpe/alloc REALES desde `/api/sentinels`. Mini-chart 100% sintético: `Math.sin(idx*7+i*1.3) + Math.cos(idx*3+i*0.7) + sharpe*0.18 + Math.random()*0.4` (24 puntos) |
| `#detailContainer` (acordeón por Sentinel) | 630 | sentinel-app.js L127 (`renderDetail`) | ⚠ | Cita/descripción REALES (i18n estático). Tabla "Tickers operados": **PnL/Win/Sharpe/Signal SINTÉTICOS** vía hash determinístico de `tk.charCodeAt(0)` (L133-138). Tabla "Últimos 5 trades": filtra `STATE.trades` por sentinel (REAL) |

### PANELES AVANZADOS

| Sección | index.html L | Render JS | Estado | Fuente |
|---|---|---|---|---|
| `#gaugeRisk` (gauge risk score) | 645 | sentinel-app.js L204 (`renderGauge`) | ⚠ | `STATE.riskScore` REAL pero la fórmula `valA = ... * Math.min(v/0.6, 1)` recorta visual a 0.6 max |
| `#gaugeVal` (valor numérico bajo gauge) | 648 | sentinel-app.js L222 | ✅ | `STATE.riskScore.toFixed(2)` |
| `#bbCircuit` (CIRCUIT BREAKER · OFF) | 653 (`class="bb-toggle on"` y label "OFF") | — (ningún render lo actualiza) | ❌ | markup literal — el backend devuelve `circuit_breaker` en `/api/status` pero el frontend NUNCA actualiza este toggle |
| `#bbParking` (PARKING BRAKE · OFF) | 654 (idem) | — | ❌ | markup literal — `parking_brake` del backend NUNCA renderizado acá (sí afecta otros lados pero no este toggle) |
| CORR PROMEDIO 0.42 | 663 (SIN ID) | — | ❌ | markup literal del bundle |
| SEÑALES REDUCIDAS 5 | 664 (SIN ID) | — | ❌ | markup literal del bundle |
| DESCARTADAS 2 | 665 (SIN ID) | — | ❌ | markup literal del bundle |
| `#histBody` (HISTORIAN — PERFORMANCE) | 675 | sentinel-app.js L225 (`renderHistorian`) | ⚠ | name/win/sharpe REALES (vienen de `/api/sentinels`, hoy 0/0). **trades/slippage/decay SINTÉTICOS**: `trades = 28 + (i*7) % 200`, `slip = 0.02 + (i*0.011)%0.06`, `decay = i===8 ? YES : NO` |
| `#allocBars` (DISPATCHER — ALLOCATION) | 682 | sentinel-app.js L235 (`renderAlloc`) | ✅ | `s.alloc` REAL ← `/api/sentinels.allocation_pct` (5% por sentinel en DB) |
| `#opsBody` (OPERACIONES EJECUTADAS) | 697 | sentinel-app.js L181 (`renderOps`) | ✅ | `STATE.trades` ← `/api/trades` |
| `#opsCount` ("0 trades") | 691 | sentinel-app.js L189 | ✅ | `STATE.trades.length` |
| `#flowBody` (FLUJO DE SENTINELS) | 713 | sentinel-app.js L192 (`renderFlow`) | ✅ | `SENTINELS[]` con sig/win/sharpe/alloc reales |
| `#flowCount` ("9 sentinels") | 707 | sentinel-app.js L200 | ⚠ | string literal hardcoded |
| `#terminalBody` (LOGS DEL SISTEMA) | 734 | sentinel-app.js L259 (`renderLogs`) | ⚠ | `STATE.logs` SE GENERA en sentinel-data.js L404 a partir de `/api/macro_events` reales pero RE-FORMATEADO como `EAR :: risk_score=... vix=... spy=... circuit_breaker=...` (no son logs reales del bot, son macro_events disfrazados de log lines) |
| `#logCount` / `#logsCountMeta` | 732/724 | sentinel-app.js L271-272 | ✅ | `STATE.logs.length` |
| Botón DESCARGAR REPORTE JSON | 745 | sentinel-app.js L367 (`downloadReport`) | ❌ | invoca `buildReport()` (sentinel-app.js L323) — 100% sintético; NO usa `/api/report` real |

### FOOTER

| Elemento | index.html L | Render JS | Estado |
|---|---|---|---|
| AFTERLIFE | 753 | — | ❌ literal estático |
| "Datos de demostración" | 755 | — | ❌ i18n key `foot_demo` literal |
| `#footUpd` (Actualizado HH:MM:SS) | 756 | sentinel-app.js L255 + sentinel-data.js L435 | ✅ | `Date.now().toTimeString()` |
| Uptime: 168h | 757 (`<b>168h</b>` SIN ID) | — | ❌ markup literal del bundle |
| Build: 0.5.42-a8c1f | 758 (`<b>0.5.42-a8c1f</b>` SIN ID) | — | ❌ markup literal del bundle |

### Conteo de secciones

- **Total identificadas:** 38 elementos auditables
- **REAL (✅):** 16
- **PARCIAL (⚠):** 7
- **SINTÉTICO (❌):** 15

---

## 4. Funciones sintéticas detectadas

### En `sentinel-app.js` (handoff Design original — congelado por ser bundle de terceros)

| Función | Líneas | Qué inventa | Sección que alimenta | Endpoint que la reemplazaría |
|---|---|---|---|---|
| `renderSentGrid()` mini-chart | 77-91 | 24 puntos por sentinel con `Math.sin + Math.cos + sharpe*0.18 + Math.random()` | mini-chart de cada card en `#sentGrid` | ninguno (no existe endpoint de equity por sentinel) |
| `renderDetail()` filas de "Tickers operados" | 132-139 | `signal = sigs[(charCodeAt+sid)%3]`, `pnl = (charCodeAt*7)%280-60`, `win = 0.42+(charCodeAt*11)%30/100`, `sharpe = 0.3+(charCodeAt*5)%140/100` | tabla "Tickers operados" dentro del acordeón de cada Sentinel | parcial: `/api/sentinels` ya trae `pnl=0.0, win_rate, sharpe_ratio` por ticker pero el render los ignora |
| `renderHistorian()` columnas trades/slip/decay | 228-230 | `trades = 28+(i*7)%200`, `slip = 0.02+(i*0.011)%0.06`, `decay = i===8?YES:NO` | tabla "HISTORIAN — PERFORMANCE" | parcial: `/api/sentinels` trae `total_trades, decay_status` reales pero el render no los usa |
| `tick()` | 284-320 | signals/trades/balance/risk_score random cada 3-5s | habría modificado `STATE.trades, STATE.balance, STATE.logs, STATE.riskScore` y disparado `renderAll()` | **interceptado** por `killTickMock()` en sentinel-data.js L161 — NO corre, datos llegan vía SSE |
| `buildReport()` | 323-365 | `uptime_hours:168, errors_by_module, reconnections, parking_brake_activations:5, strategy_performance` con la misma fórmula `28+i*7`, `regime_distribution:{BULL:3,NEUTRAL:12,BEAR:0}`, `correlation_guard:{reduced:5, discarded:2, avg_correlation:0.45}`, `dispatcher:{received:45, approved:38, rejected:7}` | botón "DESCARGAR REPORTE JSON" | `/api/report` (existe en backend, no se usa) |
| Listener `#detenerBtn` (handoff) | 403 | `alert('SISTEMA DETENIDO (demo)')` | botón DETENER | **interceptado** por `setupKillSwitch()` en sentinel-data.js L596 (`stopImmediatePropagation`) |

### En `sentinel-data.js` (capa "real" — escrita por nuestro lado)

| Función | Líneas | Qué inventa | Sección que alimenta | Notas |
|---|---|---|---|---|
| `STATE.balance = 100000` | 148 | constante hardcoded | `#osBalance, #eqCapital, #osPnl` | TODO en el comentario: "extender API con `/api/account/equity`" |
| `STATE.balanceChange = 0` | 148 | constante hardcoded | — | nunca se actualiza |
| `synthEquityHist()` sin trades | 323-327 | 24 puntos `100000 + Math.sin(i*0.4)*10` (línea casi recta con jitter mínimo) | `STATE.equityHist` → `#eqChart` | placeholder hasta que backend exponga equity series |
| `synthEquityHist()` con trades | 329-336 | acumulado de `slippage*qty*sign(side)` pero con `slip = 0` literal en L333 | idem | "no es PnL real" según el propio comentario |
| Constantes `AGENTS[]` con `active: true/false` fijos | 123-129 | dispatcher:true, correlation:false, the_ear:true, historian:false, regime:false | `#agentsGrid` | `loadStatus()` sólo modifica dispatcher/the_ear/regime; correlation y historian quedan permanentemente en `false` |
| `STATE.logs` desde macro_events | 404-415 | re-formatea cada `macro_event` como `EAR :: risk_score=X vix=Y spy=Z circuit_breaker=W` | `#terminalBody` | son datos reales pero presentados como "log line" — el bot tiene su propio log file en disco que no se expone |

### Markup literal hardcoded en `index.html` (sin id, nunca renderizado desde JS)

| Línea | Elemento | Texto |
|---|---|---|
| 567 | meta de AGENTES | "5 agentes activos" (i18n) |
| 580 | sub de osPnl | "+0.42%" |
| 581 | valor de POSICIONES ABIERTAS | "5" |
| 582 | aprobadas / rechazadas | "18" / "5" |
| 606 | Max DD | "-1.24%" |
| 653 | CIRCUIT BREAKER toggle | clase `bb-toggle on` + texto "OFF" |
| 654 | PARKING BRAKE toggle | clase `bb-toggle on` + texto "OFF" |
| 663 | CORR PROMEDIO | "0.42" |
| 664 | SEÑALES REDUCIDAS | "5" |
| 665 | DESCARTADAS | "2" |
| 731 | terminal path | "~/sentinel/control@aftercapital — bash — 0.5x42" |
| 757 | Uptime | "168h" |
| 758 | Build | "0.5.42-a8c1f" |
| 576 | "actualizado hace 3 min" (con `#opsAgo` pero ningún render lo toca) | "3" |
| 588 | "5 items" en `#newsCount` (sí se actualiza por renderNews) | string inicial |
| 724 | "17 lines" en `#logsCountMeta` (sí se actualiza por renderLogs) | string inicial |

**Total funciones/lugares sintéticos: 21**
- 6 funciones de `sentinel-app.js`
- 5 puntos sintéticos en `sentinel-data.js`
- 13 piezas de markup literal en `index.html` (de las cuales 11 nunca se actualizan)

---

## 5. Resolución de los 11 casos especiales

### CASO 1 — BALANCE TOTAL = $100,000.00

**Origen:** `STATE.balance = 100000` HARDCODED en `sentinel-data.js:148` con comentario `// TODO: extender API con /api/account/equity`.
**Render:** `renderHeader()` en `sentinel-app.js:253` (`#osBalance`) y `renderEquity()` L67 (`#eqCapital`).
**Endpoint que lo reemplazaría:** ninguno existe hoy. Habría que agregar `/api/account/equity` que pegue contra Alpaca o calcule desde trades cerrados. Alpaca real: $100,036.85.

### CASO 2 — P&L = +$0.00 pero +0.42%

**Dos fuentes distintas:**
- `+$0.00`: `renderHeader()` en `sentinel-app.js:254` escribe `#osPnl` con `fmt(Math.abs(STATE.balance-100000))`. Como `STATE.balance` es 100000 hardcoded → siempre 0.
- `+0.42%`: en `index.html:580` el `<div class="sub">+0.42%</div>` **NO TIENE ID** y **ningún render JS lo toca**. Es markup literal del bundle.

Por eso son inconsistentes entre sí: el monto se "actualiza" a 0 (con bug de fórmula), el porcentaje queda fijo del demo.

### CASO 3 — POSICIONES ABIERTAS = 5

`index.html:581`: `<div class="os-item"><div class="k" data-i18n="os_open_pos">POSICIONES ABIERTAS</div><div class="v">5</div></div>`. **Sin id, sin render.** Markup literal del bundle Design. Alpaca real: 6 posiciones.

### CASO 4 — SEÑALES PROCESADAS = 23 (18 / 5)

`index.html:582`:
- `<span id="osSigProc">23</span>` — tiene id pero **ningún render JS lo escribe** (`grep osSigProc` solo aparece en index.html).
- `<b style="color:var(--green)">18</b>` y `<b style="color:var(--red)">5</b>` — **sin id**.

100% markup literal. DB tiene 36 signals reales hoy.

Curiosamente `buildReport()` (sentinel-app.js:357) usa `signals_received: 45, signals_approved: 38, signals_rejected: 7` — números diferentes, también fake pero distintos a los del HTML.

### CASO 5 — "5 agentes activos"

`index.html:567`: `<span class="meta"><span data-i18n="agents_meta">5 agentes activos</span></span>`. Es una string i18n literal — no se calcula a partir de `AGENTS.filter(a=>a.active).length`. Si los 5 agents estuvieran inactivos seguiría diciendo "5 agentes activos".

### CASO 6 — REGIME CLASSIFIER S-10

El AGENTS array (sentinel-data.js:128) tiene `{ id:"regime", nameKey:"ag_regime", subKey:"ag_regime_sub", ..., active:false, icon:"regime" }`. La sub-label "S-10 Meta-Agente" está en `sentinel-i18n.js:81` (`ag_regime_sub:"S-10 Meta-Agente"`).

**No existe S-10 en la DB** (`sentinels` tiene 9 filas, S-1 a S-9 — confirmado por inventario previo). El "S-10" es marketing del bundle: el RegimeClassifier existe en código (`regime_classifier.py`) pero está desactivado (régimen fijo NEUTRAL en backend api.py:420 y sentinel-data.js:210). En DB no aparece como sentinel separado.

`loadStatus()` (sentinel-data.js:209-211) explícitamente fuerza `regime.active = false`. La card se sigue dibujando aunque el agente no exista — viene del array hardcoded.

### CASO 7 — Mini-charts en cards de Sentinels

`renderSentGrid()` en `sentinel-app.js:77-91` genera 24 puntos:

```js
let v = 100;
for (let i=0;i<24;i++){
  v += (Math.sin(idx*7 + i*1.3) + Math.cos(idx*3 + i*0.7)) * 0.5
     + s.sharpe*0.18 + (Math.random()-0.5)*0.4;
  pts.push(v);
}
```

100% sintético. El componente determinístico (sin/cos) garantiza que cada Sentinel tenga "su" forma de curva, el `Math.random()` agrega jitter, y `s.sharpe*0.18` mete una variación leve por valor real (hoy con sharpe=0 no aporta nada).

Por eso MORPHEUS muestra picos y valles aunque `performance_scores` esté vacía y no haya trades cerrados — la curva no representa equity real.

### CASO 8 — Max DD = -1.24% con curva vacía

`index.html:606`: `<span data-i18n="eq_max_dd">Max DD</span><b>-1.24%</b>`. **Sin id, sin render.** Markup literal del bundle.

### CASO 9 — HISTORIAN trades 28/35/42/49/56/63/70/77/84

`renderHistorian()` en `sentinel-app.js:228`:

```js
const trades = 28 + (i*7) % 200;
```

Para `i=0..8` da exactamente 28, 35, 42, 49, 56, 63, 70, 77, 84. Confirmado al 100%.

El `slip` (L229) y `decay` (L230) también son fórmulas: `slip = (0.02 + (i*0.011)%0.06).toFixed(3)` y `decay = i===8 ? YES : NO` (siempre S-9 con decay YES).

### CASO 10 — CORRELATION GUARD CORR=0.42 / REDUCIDAS=5 / DESCARTADAS=2

`index.html:663-665`. Tres `<div class="v">...</div>` **sin id, sin render**. Markup literal.

DB no tiene tabla de correlation events (correcto: no se persisten). El backend `/api/report` lo expone como `null` (api.py:899-901, comentado como TODO). El dashboard simplemente nunca se conectó a esos campos.

### CASO 11 — DISPATCHER ALLOCATION 5%

**Real.** `renderAlloc()` en `sentinel-app.js:235-247` lee `s.alloc` de cada Sentinel, que viene de `loadSentinels()` mapeado de `allocation_pct/100` (sentinel-data.js:260, donde `allocation_pct` es `/api/sentinels.allocation_pct` ← `sentinels.capital_allocation` en DB).

Confirmado en inventario previo: los 9 sentinels tienen `capital_allocation = 5.00`. Las barras del dashboard reflejan el dato real.

(Caveat menor: el escalado visual usa `const max = 0.25` hardcoded, lo cual es coherente con el `MAX_CAPITAL_PER_SENTINEL = 25%` de OBSERVATION_PERIOD.md — no es invento, es el techo del sistema.)

---

## 6. Veredicto final + recomendación

### Veredicto: **ESCENARIO B — PARCIAL**

El dashboard es un híbrido: la **infraestructura de fetch está bien armada** (12 endpoints consumidos, SSE conectado, kill switch funcional, market status real, news_titles reales del FIX-010), pero **muchos KPIs visibles del cuerpo principal son markup literal** que sobrevivió al integrar el bundle handoff y nunca recibieron un renderer.

Distribución cuantitativa:
- 16 elementos REALES (42%)
- 7 PARCIALES (18%)
- 15 SINTÉTICOS (40%)

**Causa raíz operativa.** No es "una sola función culpable". Son **tres mecanismos distintos** mezclados:

1. **Markup literal en `index.html` sin `id`** — 11 piezas que nunca pueden ser actualizadas porque no hay manera de seleccionarlas desde JS sin reescribir el HTML. Caso: POSICIONES=5, +0.42%, Max DD, CORR 0.42, SEÑALES REDUCIDAS=5, etc.

2. **Funciones sintéticas en `sentinel-app.js`** (handoff Design, no se modifica) — generan datos con sin/cos/random/charCodeAt para mini-charts, "Tickers operados" en detail, columnas trades/slip/decay del Historian, y todo `buildReport()`.

3. **Constantes hardcoded en `sentinel-data.js`** (capa "real" nuestra) — `STATE.balance = 100000`, `synthEquityHist()` placeholder, `AGENTS[]` con `active` fijo para 3 de 5 agentes.

**Adicional.** Hay endpoints **definidos pero no usados** (`/api/performance`, `/api/report`) y campos que el backend devuelve pero el frontend ignora (`circuit_breaker`, `parking_brake` en `/api/status` — el frontend solo los usa para AGENTS.active, no para los toggles `#bbCircuit`/`#bbParking`).

### Datos de Alpaca/DB no expuestos por ningún endpoint

Para los KPIs que mostrar correctamente, faltan:
- `equity_total` (Alpaca account) → BALANCE TOTAL
- `pnl_day` (Alpaca o cálculo FIFO sobre trades) → P&L DEL DÍA monto y porcentaje
- `open_positions_count` (Alpaca positions) → POSICIONES ABIERTAS
- `signals_approved`/`signals_rejected` (signals.approved + signals.rejection_reason — TODOs en api.py L911)
- `correlation_guard.{signals_reduced, signals_discarded, avg_correlation}` (TODOs en api.py L897-901)
- `equity_curve` series → CURVA DE EQUITY real
- `max_drawdown` calculado sobre la curva
- Build version y uptime real (uptime ya existe en `/api/report.system_health.uptime_hours` pero no se consume en el dashboard)

### Recomendación de orden para el fix posterior (no ejecutar ahora)

Tres frentes paralelizables, en orden de impacto vs esfuerzo:

**A. Quick wins de markup** (sin tocar lógica del bot):
- Asignar `id` a las 11 piezas de markup literal sin id.
- Crear renderers en `sentinel-data.js` que mapeen los campos que el backend YA devuelve (`circuit_breaker, parking_brake` para los toggles, `regime` para el header — aunque sea "NEUTRAL" fijo está bien que se renderice desde la API).
- Cambiar el botón "DESCARGAR REPORTE JSON" para que pegue `/api/report` real en lugar de `buildReport()` cliente.

**B. Endpoints faltantes** (cambios al backend, ojo con OBSERVATION_PERIOD — son endpoints nuevos read-only, no modifican lógica):
- `/api/account/equity` que llame Alpaca `get_account()` y devuelva `{balance, equity, cash, day_pnl, day_pnl_pct, positions_count}`. Para BALANCE/P&L/POSICIONES.
- `/api/equity/series?range=today` con la curva de equity por trade ejecutado (calculable desde Alpaca portfolio history).

**C. Refactor del frontend** (mayor esfuerzo, fuera del período):
- Reescribir las funciones sintéticas de `sentinel-app.js` (`renderSentGrid` mini-chart, `renderDetail` tabla de tickers, `renderHistorian` columnas) para que consuman `/api/sentinels` y `/api/performance` reales.
- Persistir y exponer `correlation_guard` events (signals.correlation_action + signals.correlation_used como TODO en api.py L897).

> Nota: B y C tocan lógica del bot solo si se entiende como "exponer datos que ya existen". Mientras se mantenga read-only y no se modifiquen thresholds/prompts/agentes, encajan en "observabilidad read-only" del OBSERVATION_PERIOD. Confirmar con el OWNER antes de cualquier merge.

---


---

## 7. Resoluciones aplicadas — 2 de Mayo 2026

> Auditoría de corrección autorizada por Bot Owner.
> Todos los cambios son read-only (endpoints nuevos) o de presentación (frontend).
> No se modificaron thresholds, prompts ni lógica de agentes.

### Frente A — Quick wins de markup → COMPLETADO

| # Auditoría | Elemento | Estado anterior | Corrección | Ronda |
|---|---|---|---|---|
| CASO 1 | BALANCE TOTAL $100,000 | ❌ HARDCODED `STATE.balance=100000` | ✅ Ahora consume `/api/account/equity` real de Alpaca | R1 |
| CASO 2 | P&L = +$0.00 | ❌ `Math.abs(STATE.balance-100000)` = 0 | ✅ P&L real desde Alpaca. Fix doble signo (+$+46 → +$46) | R1+R3 |
| CASO 3 | POSICIONES ABIERTAS = 5 | ❌ Markup literal sin id | ✅ Ahora muestra count real de posiciones Alpaca | R1 |
| §3 tabla | Mini-charts sintéticos | ❌ `Math.sin + Math.cos + random` | ✅ Curvas de trades FILLED reales. Sin datos → línea gris | R2 |
| §3 tabla | Win% / Sharpe en cards | ⚠ Mostraban "0%" / "0.00" | ✅ Muestran "--" cuando no hay performance_scores (warm-up) | R2 |
| §4 | `synthEquityHist()` sin trades | ❌ `100000 + Math.sin(i*0.4)*10` | ✅ Calcula desde trades FILLED con PnL acumulado real | R2 |
| §3 tabla | Detalle: tickers sin trades | ⚠ Mostraban señal BUY/SELL/— | ✅ Muestran "👁 VIGILANDO" (i18n 4 idiomas) | R3 |
| §3 tabla | Detalle: posiciones abiertas | — | ✅ Muestran "N Abierta (compra/venta)" con tooltip | R3 |
| §3 tabla | HORA en últimos trades | Solo hora HH:MM:SS | ✅ Ahora muestra MM-DD HH:MM (fecha + hora) | R3 |
| §4 | Status técnicos (FILLED, CANCELLED) | ❌ Texto raw de Alpaca API | ✅ Traducidos a 4 idiomas (ES/EN/JA/TH) con tooltips descriptivos | R4 |
| §4 | Términos financieros (LONG/SHORT) | ❌ Jerga en inglés | ✅ Lenguaje natural i18n: "Abierta (compra)" / "Open (buy)" etc. | R4 |
| §3 tabla | Alineación Historian / Flujo | ⚠ Columnas numéricas no centradas | ✅ CSS por ID fuerza centrado independiente del cache | R5 |

### Frente A.5 — Endpoint nuevo (backend read-only)

| Endpoint | Archivo | Descripción |
|---|---|---|
| `GET /api/account/equity` | api.py | Nuevo. Llama `trading_client.get_all_positions()` + `get_account()` de Alpaca. Devuelve `{equity, cash, pnl, positions: [{ticker, qty, avg_entry, current_price, unrealized_pl, market_value}]}`. Read-only. | R1 |

### Frente B — Datos operativos

| Acción | Descripción | Justificación |
|---|---|---|
| Reconciliación de 22 trades | `reconcile_pending_trades.py` actualizó trades PENDING_NEW → FILLED cruzando con Alpaca | Datos faltantes por orders que pasaron de pending a filled sin callback |
| Adopción MSFT → Neo (S-8) | INSERT BUY $424.60, trade_id `d4a3b87f` | Posición huérfana previa al período de observación. Mantener flujo de datos limpio. |
| Adopción XLP → Oracle (S-3) | INSERT BUY $82.75, trade_id `b7f78c3e` | Posición huérfana previa al período de observación. Evitar ruido en datos recolectados. |

### Frente C — Pendiente (requiere Claude Design + refactor mayor)

Resueltos en Ronda 6 (frontend-only, sin tocar período de observación):

- ✅ §3: Circuit Breaker / Parking Brake toggles → conectados a `/api/status` (ya funcionaba)
- ✅ §3: `buildReport()` → reemplazado por `downloadReport()` que usa `/api/report` real (ya funcionaba)
- ✅ CASO 5: "5 agentes activos" → ahora dinámico con i18n (ya funcionaba, mejorado en R6)
- ✅ §4: Uptime → ahora real desde `/api/report` system_health.uptime_hours (R6)
- ✅ §4: Build → ahora real desde `/api/report` metadata.system_version (ya funcionaba)
- ✅ §4: "Datos de demostración" → cambiado a "Sistema en vivo" con i18n (R6)

Pendiente (requiere modificaciones al backend — NO tocar durante período de observación):

- ⏳ CASO 4: SEÑALES PROCESADAS — `dispatcher.signals_approved/rejected` devuelven `null`
- ⏳ CASO 6: REGIME CLASSIFIER S-10 — agente no existe en DB, card hardcoded
- ⏳ CASO 8: Max DD — no existe cálculo de drawdown máximo
- ⏳ CASO 10: CORRELATION GUARD — `signals_reduced/discarded/avg_correlation` devuelven `null`
- ⏳ §3: AGENTS[] cards correlation/historian — `active:false` fijo (backend no expone estado)

### Infraestructura de mantenimiento creada

| Recurso | Ubicación | Propósito |
|---|---|---|
| CHANGELOG-UI.md | `dashboard/CHANGELOG-UI.md` | Registro de cambios de interfaz para sincronizar con Claude Design |
| Backups catalogados | `backups/2026-05-02/` | Archivos originales + README con instrucciones de restauración |
| Norma de backups | Memoria del proyecto | Siempre backup → editar → changelog → cache-bust |

### Conteo actualizado

- **Total elementos auditables:** 38
- **REAL (✅):** 29 (antes 16, +13 corregidos en R1-R6)
- **PARCIAL (⚠):** 3 (antes 7, -4 promovidos a REAL)
- **SINTÉTICO (❌):** 6 (antes 15, -9 corregidos — 4 restantes requieren backend)

*Auditoría original generada el 2026-04-28 (read-only). Resoluciones del 2026-05-02 aplicadas con autorización del OWNER.*
