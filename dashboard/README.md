# Dashboard — Sentinel v0.5

UI del sistema de trading multi-agente. Es el handoff oficial de **Claude
Design** (HTML/CSS pixel-perfect del prototipo) conectado a la API real
(`/api/*`) por un `sentinel-data.js` propio que reemplaza el mock original
y enchufa SSE para refresco en vivo.

## Stack

- HTML / CSS / JS vanilla — sin frameworks.
- 3 archivos JS externos cargados en este orden (no cambiar):
  1. `sentinel-i18n.js` — diccionario ES / EN / JA / TH (≈100 keys). Tal cual del handoff.
  2. `sentinel-data.js` — globales pobladas con datos de la API + SSE listener. **Custom**, no del handoff.
  3. `sentinel-app.js` — render, accordion, theme/lang/view toggles, download de reporte. Tal cual del handoff.
- Google Fonts: Orbitron, Share Tech Mono, JetBrains Mono.
- Sin Chart.js: el gauge de risk score, la curva de equity y los mini-charts
  por sentinel se dibujan con SVG inline en `sentinel-app.js`.

## Estructura del directorio

```
dashboard/
├── index.html                   ← markup + CSS (handoff Design v2)
├── sentinel-i18n.js             ← traducciones (handoff)
├── sentinel-data.js             ← globales + fetch API + SSE (custom)
├── sentinel-app.js              ← lógica render (handoff)
├── HANDOFF_INTEGRATION.md       ← mapeo handoff ↔ API
├── README.md                    ← este archivo
└── assets/
    ├── favicon.svg              ← split cyan/magenta (Afterlife)
    └── favicon-mono-cyan.svg    ← mono cyan (Sentinel sub-brand)
```

## Endpoints consumidos

`sentinel-data.js` orquesta `reloadFromAPI()` y SSE:

| Endpoint | Cuándo | Pobla |
|----------|--------|-------|
| `GET /api/status` | boot + cada update SSE | `STATE.riskScore`, agentes activos, header pills |
| `GET /api/sentinels` | boot + cada update SSE | `SENTINELS[]` con id, name, sig, win, sharpe, alloc, tickers |
| `GET /api/trades?limit=50` | boot + cada update SSE | `STATE.trades` |
| `GET /api/macro` | boot + cada update SSE | `NEWS`, `STATE.logs` |
| `GET /api/sse` | conexión persistente | dispara `reloadFromAPI()` en cada `event: update` |
| `GET /api/report?range=...` | on-demand desde el botón "DESCARGAR REPORTE JSON" | descarga JSON |

## Cómo modificar cada sección

### Header sticky (logo + status pills + controles)

- Markup: `<header class="header-fixed">` en `index.html`.
- Status pills (SISTEMA / SENTINELS / RÉGIMEN / TICKERS / REFRESH / RISK)
  se actualizan desde `loadStatus()` en `sentinel-data.js`.
- El botón **STOP** está cableado a `alert('SISTEMA DETENIDO (demo)')` en
  `sentinel-app.js`. No hay endpoint `POST /api/system/halt` aún.

### Agentes (5 cards)

- Markup: `<div class="agents-grid" id="agentsGrid">`.
- Render: `renderAgents()` en `sentinel-app.js` itera `AGENTS[]`.
- `AGENTS` es contenido fijo del diseño en `sentinel-data.js`. El campo
  `active` se actualiza con `data.circuit_breaker` de `/api/status`.
- Iconos: `AGENT_ICONS` en `sentinel-data.js` (SVG strings).

### KPIs operativos

- Balance / P&L / Posiciones abiertas / Señales procesadas. **Placeholder**:
  no existe endpoint `/api/account/equity`. Los valores estáticos del HTML
  (`$100,255.63`, `+$425.80`, etc.) se mantienen hasta que el backend exponga
  estos datos.

### Noticias macro

- `NEWS` se popula desde `/api/macro` `recent_events`. La API no devuelve
  títulos legibles — `sentinel-data.js` sintetiza un string `Macro update —
  risk X.XX VIX Y% SPY Z%` y lo inyecta como key dinámica en `I18N`.

### Curva de equity

- SVG en `<svg id="eqChart">`. Render: `renderEquity()`.
- Datos: `STATE.equityHist` (array de números). Hoy es **placeholder**
  sintético construido desde `STATE.trades`. Cuando exista
  `GET /api/equity?range=...`, reemplazar la función `synthEquityHist()` en
  `sentinel-data.js`.

### 9 Sentinel cards + accordion detalle

- Grid: `<div class="sent-grid" id="sentGrid">`.
- Detalle: `<div id="detailContainer">` con `.detail-block` por sentinel.
- Click en card → smooth scroll al detalle + abrir accordion.
- Citas (Matrix / Cyberpunk 2077): hardcoded en `QUOTES` dentro de
  `sentinel-data.js`. **No vienen de la API** — son contenido editorial.

### Paneles avanzados (vista COMPLETA)

- 4 paneles: gauge The Ear, KPIs Correlation Guard, tabla Historian, barras
  Dispatcher allocation. Render en `sentinel-app.js` (`renderGauge`,
  `renderHistorian`, `renderAlloc`).
- Visibles solo en `body[data-view="full"]`. SIMPLE los oculta vía CSS.

### Logs colapsable + descarga

- Click en `.logs-head` → toggle `.logs-section.open`.
- `STATE.logs` se sintetiza desde `/api/macro` events.
- Botón DESCARGAR genera JSON con `buildReport(range)` (en `sentinel-app.js`).
  El JSON tiene formato propio del handoff — coexiste con el endpoint
  `/api/report?range=` del backend (que no se usa hoy desde el dashboard).

## Cómo agregar un nuevo Sentinel

1. **Backend** — el Sentinel debe estar en la DB (`sentinels` + `sentinel_tickers`)
   y registrado en `SENTINEL_REGISTRY` de `sentinel-v0.5/sentinels/__init__.py`.
2. **Dashboard** — en `sentinel-data.js`:
   - Agregar entry en `STRATEGY_KEY_MAP`: `nuevo_strategy_type → strat_key`.
   - Agregar entry en `CYBERPUNK_NAME`: `nuevo_strategy_type → "NEWNAME"`.
   - Agregar entry en `SID_BY_STRATEGY`: `nuevo_strategy_type → "S-10"`.
   - Agregar entry en `QUOTES` con `quote`, `quoteSrc`, `quoteEn/Ja/Th`.
3. **i18n** — en `sentinel-i18n.js`, agregar `desc_<strat_key>` con la
   descripción de la estrategia traducida en los 4 idiomas.
4. La API ya devolverá el Sentinel automáticamente — no hay que tocar nada
   más.

## Cómo agregar un nuevo idioma

1. En `sentinel-i18n.js`: copiar el bloque `es:` con todas las keys y
   traducir.
2. En `index.html`: agregar `<button data-lang="xx">XX</button>` dentro de
   `#langToggle`.
3. En `sentinel-data.js` `loadMacro()`: agregar la key `xx` en el bloque que
   sintetiza títulos de news dinámicos (búscalo por `_news_dyn_`).
4. En `sentinel-data.js` constants `QUOTES`: agregar `quoteXx` por sentinel.

## Variables CSS y temas

Definidos en `index.html` `<style>` raíz.

| Token | Cyber (default) | Sober |
|-------|-----------------|-------|
| `--bg` | `#030610` | `#f5f6f8` |
| `--panel` | `#07091a` | `#ffffff` |
| `--cyan` | `#00f5ff` | `#1d6fb8` |
| `--magenta` | `#ff00d4` | `#8a2db5` |
| `--green` | `#00ff88` | `#1d8a52` |
| `--red` | `#ff2060` | `#c4334a` |
| `--text` | `#d8e6f5` | `#1a2030` |

El theme se controla con `<body data-theme="cyber|sober">`. Persistido en
`localStorage('sentinel.theme')` por `sentinel-data.js`.

## Persistencia local

`sentinel-data.js` agrega listeners delegados que guardan en
`localStorage`:

- `sentinel.lang` — ES / EN / JA / TH
- `sentinel.view` — full / simple
- `sentinel.theme` — cyber / sober

Al boot, los lee y sincroniza el `dataset` del body + el botón activo del
toggle correspondiente.

## Tick mock neutralizado

El `sentinel-app.js` original termina con `setTimeout(tick, 2500)` que
arranca un loop de mutaciones aleatorias (signals fake, prices random walk,
trades inventados). En modo conectado a la API esto contamina los datos
reales.

`sentinel-data.js` intercepta `setTimeout` antes de que `sentinel-app.js`
cargue, y filtra la llamada con `fn.name === 'tick'` y `delay === 2500` (la
firma específica del boot del handoff). El tick nunca arranca; las
actualizaciones llegan sólo por SSE.

## Limitaciones conocidas

Ver `HANDOFF_INTEGRATION.md` para detalle. Resumen:

1. **Balance / P&L / Posiciones abiertas / Señales procesadas** — el HTML
   muestra valores hardcoded (`$100,255.63`, `+$425.80`, `5`, `23`).
   Requieren endpoint `/api/account/equity` o equivalente. **TODO: extender
   API.**
2. **News titles reales** — la API solo expone risk_score/VIX/SPY. Se
   sintetizan strings descriptivos como placeholder.
3. **Equity history series** — la API no expone serie histórica de equity.
   Se sintetiza desde trades como placeholder visual.
4. **Logs reales del sistema** — solo se muestran los macro events. Sin
   endpoint para tail del log de `sentinel.log` aún.
5. **Botón STOP** — alert demo. Requiere `POST /api/system/halt` con
   confirmación. **TODO: extender API.**
6. **`renderDetail` calcula PnL/win/sharpe por ticker con un hash sintético**
   (línea ~136 de `sentinel-app.js`). En el handoff es decorativo. Para
   datos reales hay que reemplazar esa función o exponer `/api/sentinels/:id`
   con detalle por ticker.

## Cómo arrancar

```powershell
cd sentinel-v0.5
venv\Scripts\python.exe api.py
```

Servido en `http://localhost:8080/` — el dashboard está en `/` y la API en
`/api/*`. El dashboard hace fetch a su mismo origen, así que no requiere
config adicional.
