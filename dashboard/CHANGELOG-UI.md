# CHANGELOG-UI — Sentinel Dashboard

> **Propósito**: Este archivo registra TODOS los cambios que afectan la interfaz del dashboard.
> Debe enviarse a Claude Design antes de hacer modificaciones visuales para que esté al tanto
> del estado actual. Cada entrada incluye qué se cambió, por qué, y en qué archivo.

---

## 2026-05-13 — Capital card debajo de la curva de Equity

### Problema

El bloque "// CURVA DE EQUITY" muestra `Capital`, `PnL día`, y `Max DD` calculados sobre el **equity total** (~$100K paper). Pero el sistema solo despliega ~1.6% del equity (hallazgo del sizing trivial documentado el 11-may). Resultado: el operador ve "PnL día -0.015%" cuando en realidad el sistema ganó/perdió ~1% sobre el capital efectivamente invertido. La métrica visible engaña sobre la performance real.

### Solución

Tarjeta nueva justo debajo de la curva, dentro del mismo `panel-body` de SECCIÓN 3 EQUITY. Reusa el patrón visual existente (`<div class="eq-meta">`) con una clase modificadora `cap-meta` para futura diferenciación CSS si Design quisiera ajustar (hoy hereda el estilo de `.eq-meta` sin override).

**Estructura HTML añadida** (versión final tras ajuste por feedback de Roman):

```html
<div class="eq-meta cap-meta">
  <span data-i18n="cap_invested">Invertido</span><b id="capInvested">—</b>
  <span data-i18n="cap_pnl_invested">PnL s/ invertido</span><b class="green" id="capDayPnl">—</b>
</div>
```

**Nota sobre la versión inicial:** la primera iteración incluía una tercera columna `Capital total` (con ID `capTotal` y key `cap_total`), pero quedaba redundante con `Capital` del bloque viejo arriba (mismo valor). Roman pidió eliminarla. El bloque viejo arriba sigue mostrando `Capital` (= equity total); el bloque nuevo abajo solo muestra `Invertido` y `PnL s/ invertido` para complementar sin duplicar.

La key i18n `cap_total` queda en `sentinel-i18n.js` para uso futuro si se necesita en otro contexto (no se borra para evitar churn).

**index.html**

- Insertado debajo del `<div class="eq-meta">` original (línea ~661). Mismo nivel jerárquico, dos bloques `.eq-meta` consecutivos dentro del mismo `panel-body`.
- Cache-bust actualizado: `sentinel-data.js?v=20260513a` y `sentinel-i18n.js?v=20260513a`.

**sentinel-data.js**

- Nueva función `loadCapitalMetrics()` que consume el endpoint nuevo `/api/account/capital`. Formato de respuesta: `{ data: { equity, invested, day_pnl, day_pnl_pct_of_invested, ... }, meta: { source, as_of, definitions } }`.
- Helpers nuevos: `_formatUSD(n)` y `_formatPct(n, includeSign)` para presentación consistente.
- Color del PnL: clase `green` si `day_pnl >= 0`, clase `red` si negativo (reusa convención del handoff existente — verificar que `.red` exista o agregar fallback en CSS).
- Fallback a `—` en error (no datos, HTTP no-200, network).
- Llamado desde `reloadFromAPI()` en cada ciclo.

**sentinel-i18n.js**

Tres keys nuevas en cada uno de los 4 idiomas:

| Key | ES | EN | JA | TH |
|---|---|---|---|---|
| `cap_total` | Capital total | Total capital | 総資本 | ทุนทั้งหมด |
| `cap_invested` | Invertido | Invested | 投資中 | ลงทุนแล้ว |
| `cap_pnl_invested` | PnL s/ invertido | PnL on invested | 投資損益 | PnL ต่อทุนลงทุน |

### Para Design

Si querés ajustar la diferenciación visual entre el bloque viejo (`Capital`, `PnL día`, `Max DD` sobre equity) y el nuevo (`Capital total`, `Invertido`, `PnL s/ invertido`), tenés la clase `.cap-meta` disponible como modificador (hoy sin estilos propios). Sugerencia: un border-top suave o un label de sección entre los dos bloques podría ayudar a separar conceptualmente "equity total" vs "capital invertido". No es bloqueante — la versión actual funciona reusando `.eq-meta`.

Formato actual de los valores (lo que verá Design al revisar):

- `Capital total`: `$100,151.24`
- `Invertido`: `$1,594.79 (1.59%)` — el % es sobre equity total
- `PnL s/ invertido`: `-$15.25 (-0.96%)` — el % es sobre capital invertido, NO sobre equity

### Conexión con redesign de dashboard

Esta es una mejora puntual de visibilidad, NO el redesign completo en 4 vistas que está planeado para post-27-may (ver `project_sentinel_dashboard.md` en memoria persistente). Cuando llegue ese redesign, esta tarjeta encaja naturalmente en la Vista 2 (Performance).

---

## 2026-05-04 — Unificación de tooltips

### Problema
Los tooltips de estatus (FILLED, CANCELLED, etc.) y posiciones abiertas (LONG/SHORT) usaban el atributo `title` nativo del navegador, que se ve como un rectángulo amarillo con delay inconsistente. Los tooltips de tickers (QQQ → Invesco QQQ Trust) usaban un div flotante posicionado por JS que se ve mucho mejor.

### Solución
Unificación de TODOS los tooltips al sistema de div flotante `#tickerTooltip`.

**sentinel-app.js**
- Estatus en tabla "Últimos 5 trades" (renderDetail): `title="${statusInfo().tip}"` → `<span class="tip-trigger" data-tip="${statusInfo().tip}">` 
- Estatus en tabla "Operaciones" (renderOps): mismo cambio
- Posición abierta en tabla tickers: `title="${t('pos_long_tip')}"` → `<span class="tip-trigger" data-tip="...">`
- Ya no se genera ningún atributo `title` dinámico

**sentinel-data.js**
- `initTickerTooltip()` ahora usa selector universal `[data-tip]` en lugar de `.ticker-sym[data-tip]`
- Funciona para cualquier elemento con `data-tip`, no solo tickers
- Comentario actualizado: "Universal tooltip"

**index.html**
- `.tbl .st-ok/.st-cancel/.st-warn/.st-wait`: removido `cursor: help` (ahora lo hereda del span interno)
- Removido `.tbl [title] { cursor: help; }` (ya no se usa `title`)
- Nuevo: `.tip-trigger { cursor: help; border-bottom: 1px dotted currentColor; }` — estilo visual unificado
- Cache-bust: `?v=20260503d` → `?v=20260504a`

### Notas para Claude Design
- Clase `.tip-trigger`: aplica `cursor: help` y `border-bottom: 1px dotted currentColor` al texto con tooltip
- Clase `.ticker-sym`: mantiene su estilo propio (cyan, dotted cyan underline) — no usa `.tip-trigger`
- Ambos tipos comparten el mismo div `#tickerTooltip` y el mismo listener JS
- Los textos de tooltip están en i18n (4 idiomas: es/en/ja/th) vía claves `_tip`
- Touch/móvil: tap muestra, segundo tap o tap fuera oculta

---

## 2026-05-02 — Auditoría + Rediseño "Solo datos de Alpaca"

### Ronda 1 — Conexión con datos reales

**sentinel-data.js**
- `renderEmptyKPIs()` reemplazado por `fetchAndRenderKPIs()` que llama a `/api/account/equity`
- `renderFallbackKPIs()` nuevo: muestra "—" cuando el endpoint falla
- KPIs ahora muestran datos reales de Alpaca: Balance, P&L, Posiciones abiertas

**Impacto visual**: La sección "ESTADO DE OPERACIÓN" pasó de mostrar "—" en todo a mostrar
valores reales ($100,046.48, +$46.48, 8 posiciones). Los campos sin endpoint aún muestran "—".

---

### Ronda 2 — Eliminar datos falsos/sintéticos

**sentinel-app.js**
- Mini-curvas de cada Sentinel: antes usaban `Math.sin()` (curvas fake). Ahora usan trades
  FILLED reales. Si un Sentinel no tiene ≥2 trades, muestra línea plana gris.
- Colores de curva: verde si tendencia positiva, rojo si negativa, gris transparente si sin datos.
- Win% y Sharpe: antes mostraban "0%" y "0.00". Ahora muestran "--" cuando no hay
  `performance_scores` (warm-up protocol: requiere 10 trades mínimo por par sentinel/ticker).

**sentinel-data.js**
- `synthEquityHist()`: antes generaba línea plana fake. Ahora calcula curva de equity desde
  trades FILLED con precio real (PnL acumulado simulado desde $100K).
- Fix doble `$$` en KPIs: HTML ya tenía `$` prefix, JS también lo agregaba. Removido del JS.

**Impacto visual**: Sección "9 SENTINELS" — 5 Sentinels con curvas reales (Mantis, Silverhand,
Smasher, Trinity, Netrunner), 4 con líneas grises planas (Morpheus, Oracle, Neo, Rogue).
Curva de Equity muestra variación real. Win/Sharpe muestran "--" en todas las cards.

---

### Ronda 3 — Detalle por Sentinel: vigilancia vs operación

**sentinel-app.js**
- Tabla "TICKERS ASIGNADOS" en detalle de cada Sentinel:
  - Tickers SIN trades FILLED → señal muestra "👁 VIGILANDO" (antes: BUY/SELL/—)
  - Tickers CON trades pero sin round-trip → P&L muestra "LONG N" o "SHORT N" (posición abierta)
  - Tickers CON round-trip completo (buy+sell) → P&L calculado desde trades reales
- Alineación: "LONG/SHORT", "—" en P&L/WIN/SHARPE centrados (`text-align: center`)

**sentinel-data.js**
- P&L KPIs: corregido signo duplicado ("+$+46.48" → "+$46.48"). Ahora usa `sign + '$' + abs()`
- Equity labels (eqCapital, eqPnl): agregado "$" prefix que se perdía al reemplazar textContent
- Columna HORA en últimos trades: formato cambiado de `HH:MM:SS` a `MM-DD HH:MM`

**index.html**
- Removido `+$` hardcoded antes de `<span id="osPnl">` (causaba signo duplicado)
- Cache-bust actualizado a `?v=20260502e`

**Impacto visual**: La tabla de detalle ahora distingue claramente entre tickers en modo
vigilancia (badge amarillo "VIGILANDO") y tickers con operación real. Los trades muestran
fecha además de hora. Valores "—" centrados en sus columnas.

---

## Archivos del dashboard

| Archivo | Función |
|---------|---------|
| `index.html` | Estructura HTML, CSS, layout completo |
| `sentinel-app.js` | Lógica de UI: cards, grids, detalle accordion, mini-curvas, flujo de operaciones |
| `sentinel-data.js` | Conexión con API: fetch datos, SSE, KPIs, equity curve, mapeo de datos |
| `sentinel-i18n.js` | Traducciones i18n: ES, EN, JA, TH. Señales, status, tooltips, agentes |

### Ronda 4 — Internacionalización de status + tooltips descriptivos

**sentinel-i18n.js** (ES, EN, JA, TH)
- Nuevas claves para status de trades: `st_filled` ("Ejecutada"), `st_cancelled` ("Cancelada"),
  `st_partial` ("Parcial"), `st_expired` ("Expirada"), `st_rejected` ("Rechazada"),
  `st_pending` ("Enviada"), `st_new` ("Recibida"), `st_accepted` ("Aceptada"),
  `st_suspended` ("Suspendida"), `st_unknown` ("Desconocido").
- Cada status tiene clave `_tip` con descripción para tooltip (ej: `st_filled_tip`).
- Nuevas claves para posiciones: `pos_long` ("Abierta (compra)"), `pos_short` ("Abierta (venta)")
  con tooltips explicativos.
- `sig_watching` ("VIGILANDO" / "WATCHING" / "監視中" / "เฝ้าดู")

**sentinel-app.js**
- Nueva función `statusInfo(rawStatus)`: mapea status Alpaca → {text, tip, cls} usando i18n.
  Soporta: FILLED, PARTIALLY_FILLED, CANCELLED, EXPIRED, REJECTED, PENDING_NEW, NEW,
  ACCEPTED, SUSPENDED.
- Celdas de status en tablas de trades ahora muestran tooltip al hover/touch con `title=""`.
- Posiciones abiertas (antes "LONG 1") ahora: "1 Abierta (compra)" con tooltip.
- "VIGILANDO" ahora usa `t('sig_watching')` para i18n.

**index.html**
- Nuevas clases CSS: `.st-ok` (verde), `.st-cancel` (rojo), `.st-warn` (amarillo),
  `.st-wait` (cyan). Todas con `cursor: help` para indicar tooltip.
- Tablas de detalle usan `table-layout: fixed` con `<colgroup>` para anchos consistentes.
- Cache-bust → `?v=20260502g`

**Impacto visual**: Los status técnicos de Alpaca (FILLED, CANCELLED) ahora se muestran en el
idioma del usuario con colores semánticos (verde=ok, rojo=cancelada, amarillo=advertencia,
cyan=en espera). Al pasar el mouse o tocar en móvil, aparece una descripción del significado.
Las posiciones abiertas se leen en lenguaje natural ("1 Abierta (compra)") en lugar de
jerga financiera ("LONG 1").

---


### Ronda 5 — Fix alineación Historian + Flujo (CSS por ID)

**index.html**
- Nueva regla CSS: `.tbl td.c { text-align: center; }` — clase utilitaria para centrar celdas.
- Nueva regla CSS por ID: `#histBody td:not(:first-child)` y `#flowBody td:nth-child(n+4)` →
  `text-align: center`. Esto fuerza el centrado en las tablas Historian y Flujo independientemente
  de qué versión del JS tenga el browser en cache.
- Causa raíz: Cloudflare servía la versión anterior de sentinel-app.js (con `class="r"`) a pesar
  del cache-bust `?v=20260502g`. El CSS por ID resuelve la alineación sin depender del JS.
- Cache-bust → `?v=20260502h`

**Impacto visual**: Las columnas WIN, SHARPE, TRADES, SLIP, DECAY en Historian y WIN, SHARPE,
ALLOC en Flujo de Sentinels ahora se muestran centradas correctamente. SENTINEL queda alineado
a la izquierda. La tabla Operaciones Ejecutadas ya estaba correcta (CANT y STATUS centradas,
PRECIO alineado a la derecha).

---


### Ronda 6 — Conectar datos reales a elementos pendientes del Frente C

**sentinel-data.js**
- `fetchAndRenderBuild()`: ahora también extrae `system_health.uptime_hours` de `/api/report`
  y lo muestra en `#footUptime`. Formato: "<1h" si menos de 1 hora, "Nh" redondeado si más.
- Removido `_setText('footUptime', _DASH)` de `fetchAndRenderKPIs()` y `renderFallbackKPIs()`
  para que no sobreescriban el valor real que pone `fetchAndRenderBuild()`.
- `renderAgentsActiveCount()`: ahora usa `t('agents_active_label')` para i18n en vez de
  string hardcoded en español.

**sentinel-i18n.js** (ES, EN, JA, TH)
- Nueva clave `agents_active_label` por idioma ("agentes activos" / "agents active" / etc.)
- `foot_demo` cambiado de "Datos de demostración" → "Sistema en vivo" (y equivalentes i18n).

**index.html**
- Uptime `<b>168h</b>` → `<b id="footUptime">—</b>` (ahora tiene id para ser actualizado por JS).
- Cache-bust → `?v=r6fix3`

**Ya funcionaban de sesiones anteriores (confirmado):**
- Circuit Breaker / Parking Brake toggles (sentinel-data.js L234-236, L1044-1066)
- Build version via `/api/report` (sentinel-data.js L1146-1157)
- `downloadReport()` usa `/api/report` real (sentinel-app.js L481-503)
- Agentes activos count dinámico (sentinel-data.js L1036-1042)

**Impacto visual**: Footer ahora muestra "Sistema en vivo" con Uptime real y Build real.
Los toggles Circuit Breaker y Parking Brake reflejan estado real del backend. El conteo
de agentes activos se calcula dinámicamente.

**Pendiente (requiere cambios de backend — documentado para revisión futura):**
- SEÑALES PROCESADAS: `dispatcher.signals_approved/rejected` devuelven `null` en `/api/report`
- CORRELATION GUARD: `correlation_guard.signals_reduced/discarded/avg_correlation` devuelven `null`
- MAX DD: no existe endpoint ni cálculo de drawdown máximo
- REGIME CLASSIFIER S-10: no existe como sentinel en DB (agente desactivado)

---

## 2026-05-03 — Curva de Equity estilo Robinhood

### Contexto
La curva de equity original era una línea SVG simple sin interactividad, sin punto de equilibrio,
y sin selector de período. Se rediseñó para comportarse como las curvas de Robinhood/Alpaca:
breakeven visible, color dinámico verde/rojo, selector de período, y hover interactivo.

### Nuevo endpoint backend (api.py)
- `GET /api/account/portfolio-history?period=<4H|8H|1D|1W|1M|1A>` — Read-only contra Alpaca
  `get_portfolio_history()`. No modifica lógica del bot ni datos en DB. Pura observabilidad.
- Retorna: `timestamps[]`, `equity[]`, `profit_loss[]`, `profit_loss_pct[]`, `base_value`, `period`
- Para 4H/8H: recorta las últimas N barras del período 1D de Alpaca (48 y 32 barras respectivamente)
- Granularidad automática: 4H/1D→5Min, 8H→15Min, 1W→1H, 1M/1A→1D

### index.html — Cambios estructurales

**CSS nuevo:**
- `.eq-period-bar` — Contenedor flex para botones de período
- `.eq-period-btn` — Botones estilo pill con bordes fusionados (border-radius solo en extremos).
  Estado `.active`: fondo cyan, color negro. Hover: texto y borde cyan.
- `.eq-hover-info` — Overlay absoluto (top-left del chart) que muestra valor y cambio al hover.
  Contiene `.eq-hover-value` (18px, bold) y `.eq-hover-change` (12px). Transición opacity 0.15s.
- `.eq-chart-wrap` — Wrapper con `position: relative` para anclar el hover overlay.
- `.eq-chart` ahora tiene `cursor: crosshair`.

**HTML modificado (sección CURVA DE EQUITY):**
- Antes: `<span class="meta" data-i18n="equity_24h">últimas 24h</span>` (texto fijo)
- Ahora: `<span class="meta" id="eqPeriodLabel">1D</span>` (dinámico según selección)
- Nuevo: Barra de 6 botones `<button class="eq-period-btn">` con `data-period`: 4H, 8H, 1D, 1W, 1M, 1Y
- Nuevo: `<div class="eq-chart-wrap">` envuelve el SVG + hover overlay
- Nuevo: `<div class="eq-hover-info" id="eqHoverInfo">` con `eqHoverValue` y `eqHoverChange`
- PnL label: cambiado de "PnL día" a "PnL" (ya no es fijo al día)

**Cache-bust:** `?v=r6fix3` → `?v=20260503a` en ambos script tags

### sentinel-app.js — Cambios funcionales

**`renderEquity()` — Reescrita completamente:**
- Antes: línea SVG simple, color basado en primer vs último punto, sin breakeven.
- Ahora:
  - **Breakeven line**: línea horizontal punteada (`stroke-dasharray: 6 4`) en el Y correspondiente
    a `STATE.equityBaseValue` (primer valor del período). Color `var(--dim)`, opacidad 0.5.
  - **Color dinámico**: verde (`var(--green)`) si último valor ≥ base, rojo (`var(--red)`) si menor.
    Aplica tanto a la línea como al gradiente del área.
  - **Área fill**: gradiente vertical desde el color de tendencia (opacity 0.25→0) pero el área
    se dibuja desde la línea de breakeven, no desde el fondo del chart. Esto hace que cuando
    está en ganancia, el fill verde está entre la línea y el breakeven (arriba); en pérdida,
    el fill rojo está entre la línea y el breakeven (abajo).
  - **Y-scale**: incluye el base value en el cálculo de min/max para que la línea de breakeven
    siempre sea visible. Padding: 20px top, 10px bottom.
  - **Grid**: 3 líneas horizontales sutiles al 25%, 50%, 75%.
  - **Stroke**: `stroke-linejoin: round`, `stroke-linecap: round`, width 2px.
  - **Empty state**: si `data.length < 2`, muestra texto "Sin datos para este período" centrado.

**`_setupEquityHover()` — Nueva función:**
- Evento `mousemove` sobre rect transparente que cubre el SVG.
- Calcula el índice más cercano al cursor.
- Muestra:
  - Línea vertical punteada (`eqHoverLine`) que sigue al cursor.
  - Punto circular (`eqHoverDot`, radio 4px) sobre la curva en el punto correspondiente.
  - Overlay `eqHoverInfo` (top-left): valor del equity en grande, y debajo: fecha/hora + cambio
    vs base en $ y %. Los colores del hover siguen la tendencia (verde/rojo).
- `mouseleave`: oculta todos los elementos de hover.

**Period selector (IIFE `initEquityPeriodSelector`):**
- Escucha click en `.eq-period-btn`. Al click: toggle clase `.active`, actualiza label,
  llama a `fetchPortfolioHistory(period)`.
- Al cargar la página (con 1.5s delay): fetch inicial con período "1D", marca 1D como activo.

### sentinel-data.js — Cambios de estado y fetch

**STATE — Nuevos campos:**
- `equityTimestamps: []` — Array de timestamps (epoch seconds) del período actual
- `equityBaseValue: 100000` — Valor base (breakeven) del período seleccionado
- `equityPeriod: '1D'` — Período activo
- `equityLoading: false` — Flag para evitar fetch concurrentes

**`fetchPortfolioHistory(period)` — Nueva función:**
- Llama a `/api/account/portfolio-history?period=X` (mapea '1Y'→'1A' para Alpaca)
- Pobla `STATE.equityHist`, `STATE.equityTimestamps`, `STATE.equityBaseValue`
- Actualiza KPIs (eqCapital, eqPnl) con el último punto del período
- Fallback a `synthEquityHist(STATE.trades)` si el endpoint falla
- Llama a `renderEquity()` al terminar

### Impacto visual

La sección "CURVA DE EQUITY" pasa de ser una línea estática sin contexto a un chart interactivo:
- 6 botones de período en la parte superior (estilo pill, misma estética que los controles existentes)
- Línea de breakeven punteada siempre visible
- Curva verde cuando hay ganancia vs el inicio del período, roja cuando hay pérdida
- Al pasar el mouse: línea vertical + punto + overlay con valor exacto, fecha/hora, y cambio en $ y %
- El área bajo/sobre la curva se rellena con gradiente sutil desde la línea de breakeven

### Archivos modificados
| Archivo | Tipo de cambio |
|---------|---------------|
| `index.html` | CSS (nuevas clases), HTML (selector período, hover overlay), cache-bust |
| `sentinel-app.js` | `renderEquity()` reescrita, nuevo `_setupEquityHover()`, nuevo period selector |
| `sentinel-data.js` | Nuevos campos STATE, nueva `fetchPortfolioHistory()` |
| `api.py` | Nuevo endpoint `/api/account/portfolio-history` (read-only Alpaca) |

---

### Adición — Tooltips de nombres completos en tickers

**sentinel-data.js**
- Nuevo diccionario `TICKER_NAMES`: ~80 tickers con nombre completo (ETFs índice, sectoriales,
  commodities, mega-caps tech, financieros, leveraged, cripto-adyacentes, internacionales).
- Nueva función `tickerSpan(sym)`: recibe un símbolo (ej: "QQQ") y devuelve HTML
  `<span class="ticker-sym" data-tip="Invesco QQQ Trust (Nasdaq-100)" tabindex="0">QQQ</span>`.
  Si el ticker no está en el diccionario, devuelve el span sin tooltip.

**sentinel-app.js** — 3 reemplazos:
1. Tabla "TICKERS ASIGNADOS" en detalle de Sentinel: `${sym}` → `${tickerSpan(sym)}`
2. Tabla "ÚLTIMOS TRADES" en detalle de Sentinel: `${tr.ticker}` → `${tickerSpan(tr.ticker)}`
3. Tabla "OPERACIONES EJECUTADAS" principal: `${tr.ticker}` → `${tickerSpan(tr.ticker)}`

**index.html** — CSS y HTML nuevo:
- `.ticker-sym`: `cursor: help`, color cyan, borde inferior punteado sutil
  (`border-bottom: 1px dotted rgba(0,245,255,0.3)`). Sin `position: relative` (ya no usa
  pseudo-elemento).
- `#tickerTooltip`: div flotante con `position: fixed`, `z-index: 9999`. Fondo `var(--bg-2)`,
  borde `1px solid var(--cyan)`, border-radius 4px, font-size 11px, `white-space: nowrap`,
  `box-shadow: 0 2px 12px rgba(0,0,0,0.4)`. Transición opacity 0.15s. Clase `.visible` lo
  muestra.
- Nuevo `<div id="tickerTooltip"></div>` antes de los script tags.
- Nota: se descartó el enfoque CSS puro (`::after` + `tabindex`) porque el overflow de las
  celdas de tabla cortaba el tooltip. El div fijo con posicionamiento JS no tiene ese problema.

**sentinel-data.js** — Tooltip JS:
- `tickerSpan()` ya no usa `tabindex="0"`.
- Nuevo IIFE `initTickerTooltip()`: event delegation con `mouseover`/`mouseout` en document.
  Posiciona el div `#tickerTooltip` con `getBoundingClientRect()` centrado arriba del elemento.
  Ajuste automático si se sale del viewport. Touch: `touchstart` con toggle (tap muestra,
  segundo tap o tap fuera oculta). `passive: false` para `preventDefault`.

**Impacto visual**: Cada símbolo de ticker en el dashboard (tablas de tickers asignados, trades
por Sentinel, y operaciones ejecutadas) ahora muestra un subrayado punteado sutil. Al pasar
el mouse o tocar en pantalla táctil, aparece un tooltip con el nombre completo del instrumento
(ej: "QQQ" → "Invesco QQQ Trust (Nasdaq-100)"). Los tickers no reconocidos se muestran sin
tooltip. El diccionario cubre ~80 tickers incluyendo todos los actualmente en uso por el sistema.

---

## Notas para Claude Design

- El dashboard usa CSS variables definidas en `index.html` (`:root`): `--green`, `--red`, `--cyan`, `--dim`, `--yellow`, etc.
- Las tablas usan clase `.tbl` con columnas de ancho automático. Headers son 9px uppercase.
- Los badges de señal usan clases `.sig-buy` (verde), `.sig-sell` (rojo), `.sig-hold` (amarillo con borde).
- Los status de trades usan clases `.st-ok` (verde), `.st-cancel` (rojo), `.st-warn` (amarillo), `.st-wait` (cyan).
- Tooltips via atributo `title=""` en celdas con `cursor: help`. Funciona en hover (desktop) y long-press (móvil).
- Las tablas de detalle usan `.tbl-fixed` (`table-layout: fixed`) con `<colgroup>` para anchos fijos por porcentaje.
- La fuente principal es monoespaciada (`--code` / `--mono`), display es `--display`.
- Responsive: hay media query `@media (max-width: 900px)` que ajusta padding en tablas.
- Cache-bust: los script tags tienen `?v=YYYYMMDD[letter]` para forzar recarga tras cambios.
- La curva de equity usa SVG con hover interactivo (no canvas). El hover overlay es un div absolutamente posicionado dentro de `.eq-chart-wrap`.
- El selector de período usa botones `.eq-period-btn` con estilo pill (bordes fusionados). El botón activo usa `.active` con fondo cyan.
- Los tickers usan `.ticker-sym` con tooltip CSS puro (pseudo-elemento `::after` con `data-tip`). Se activan con `:hover` y `:focus` (touch). El diccionario `TICKER_NAMES` en sentinel-data.js tiene ~80 entradas.
- El breakeven es una línea punteada SVG (stroke-dasharray) posicionada en el Y del primer valor del período.
- Los colores de la curva son dinámicos: `var(--green)` o `var(--red)` según si el último valor está por encima o debajo del breakeven.
