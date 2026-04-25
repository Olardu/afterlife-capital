# Dashboard — Sentinel v0.5

UI web del sistema de trading multi-agente Sentinel v0.5.

## Qué hace

Lee datos en vivo del backend FastAPI (`/api/*`) y los presenta en una sola
página HTML standalone. Sin frameworks pesados, sin build step. Refresco
automático vía Server-Sent Events cada 15 minutos.

## Stack

- **HTML / CSS / JS vanilla** — sin React, Vue, Svelte, Astro.
- **Chart.js 4.4** vía CDN (`cdn.jsdelivr.net`) — para curva de equity y
  mini-charts por Sentinel.
- **Google Fonts** — Orbitron (titulares) + Share Tech Mono (datos).
- **Server-Sent Events** vía `EventSource` — push de updates desde
  `/api/sse` cada 15 minutos.

## Estructura del archivo `index.html`

El archivo es standalone. Secciones aproximadas (ver `index.html` para líneas
exactas):

| Sección | Contenido |
|---------|-----------|
| `<style>` cabecera | CSS vars + tema cyberpunk/sobrio |
| `header.topbar` (sticky) | Logo, status pills, controles (idioma, vista, tema, descarga) |
| `<main>` agentes | 5 cards: Dispatcher, CorrelationGuard, The Ear (gauge SVG), Historian, S-10 |
| `<main>` resumen | Mini cards con métricas clave |
| `<main>` noticias | Macro events recientes |
| `<main>` equity | Chart.js global con PnL acumulado (placeholder) |
| `<main>` sentinels | 9 cards expandibles con accordion inline + mini-chart |
| `<main>` trades | Tabla de operaciones ejecutadas |
| `<main>` flujo | Tabla un row por (sentinel × ticker) |
| `<main>` terminal | Logs estilo macOS con colores por nivel |
| `<footer>` | Identificador + timestamp última actualización |

JS organizado en bloques con comentarios `RENDER —`, `DATA —`, `UI HANDLERS —`.

## Cómo modificar cada feature

### Cambiar paleta cyberpunk vs sobrio

Editar las CSS vars en `:root` (cyberpunk) y `[data-theme="sobrio"]` al inicio
del `<style>`. Variables principales: `--primary`, `--accent`, `--good`,
`--bad`, `--warn`, `--text`, `--bg`, `--bg-2`, `--card-bg`, `--card-bd`.

### Cambiar el gauge del risk score

Función `renderGauge(pct)` — devuelve SVG. Los thresholds de color están
hardcoded: `>70 → bad`, `>40 → warn`, default → good. Cambiar ahí si querés
otro umbral.

### Modificar el accordion de Sentinels

- Markup interno: `renderSentinelDetail(s)` — devuelve el `<div class="sent-detail">`.
- Toggle handler: `toggleSentinelCard(card)` — expande la clickeada y cierra
  cualquier otra.
- CSS: `.sent-card.expanded` ocupa `grid-column: 1 / -1` (full width).

### Cambiar mini-charts de Sentinels

Función `renderMiniCharts()`. Si no hay trades → muestra placeholder vacío.
Si hay → Chart.js mini line. La fuente del cálculo de `acc` (PnL aproximado
con slippage) está documentada como placeholder hasta que el backend
implemente FIFO real.

### Modificar el terminal logs

- Markup: sección `<div class="terminal">` antes del `</main>`.
- Render: `renderLogs()` — itera `STATE.macro.recent_events` y aplica clase
  `log-info`/`log-warn`/`log-error` según `circuit_breaker_triggered` y
  `risk_score`.
- Toggle: `setupUI()` registra click en `#terminal-header` que toggea
  `.collapsed`.

## Cómo agregar un nuevo Sentinel

1. **Backend** — el nuevo Sentinel ya debe estar en la DB y registrado en
   `SENTINEL_REGISTRY` de `sentinel-v0.5/sentinels/__init__.py`.
2. **Dashboard** — agregar entrada al objeto `SENTINEL_DISPLAY` con su
   `strategy_type` como key:
   ```js
   nuevo_strategy_type: {
     name: "NEWNAME",
     subtitle: "Nombre Estrategia — Categoría",
     quote: { es: "...", en: "...", ja: "...", th: "..." },
     desc:  { es: "...", en: "...", ja: "...", th: "..." },
   }
   ```
3. La API ya devuelve los Sentinels con sus tickers — el dashboard los
   renderiza automáticamente.

## Cómo agregar un nuevo idioma

1. Agregar entrada al objeto `I18N` con código de idioma como key.
2. Copiar todas las claves de `I18N.es` y traducir.
3. Agregar `<option value="xx">XX</option>` al `<select id="lang">` en el HTML.
4. En `SENTINEL_DISPLAY`, agregar la traducción de `quote` y `desc` para cada
   Sentinel bajo la nueva clave. Si una clave falta, el fallback es `es`.

## Variables CSS y temas

| Variable | Cyberpunk | Sobrio |
|----------|-----------|--------|
| `--bg` | `#030610` (negro) | `#161616` |
| `--primary` | `#00f5ff` (cyan) | `#6ea8fe` (azul) |
| `--accent` | `#ff00ff` (magenta) | `#b39bd6` (violeta apagado) |
| `--good` | `#00ff88` | `#6cc78c` |
| `--bad` | `#ff4466` | `#d57380` |
| `--warn` | `#ffcc00` | `#d8b15c` |
| `--shadow` | glow cyan | none |

El tema se controla por `<html data-theme="cyberpunk|sobrio">` y se persiste
solo en memoria (no localStorage por ahora).

## Endpoints consumidos

Todos a través de `fetchJSON()` con manejo de error que retorna `null`:

| Endpoint | Cuándo |
|----------|--------|
| `/api/status` | Al cargar y en cada update SSE |
| `/api/sentinels` | Al cargar y en cada update SSE |
| `/api/trades?limit=100` | Al cargar y en cada update SSE |
| `/api/macro` | Al cargar y en cada update SSE |
| `/api/performance` | Al cargar y en cada update SSE |
| `/api/sse` | Conexión persistente que dispara reload completo en cada `event: update` |
| `/api/report?range=...` | On-demand por click en el botón "Reporte" |

## Toggles disponibles

- **Idioma** (`<select id="lang">`) — cambia todos los strings UI.
- **Vista Simple/Completa** (`<button id="toggle-view">`) — `data-view="simple"`
  oculta secciones marcadas con `data-detailed` (noticias, equity, sentinel
  detail, trades, flujo, logs).
- **Tema Cyberpunk/Sobrio** (`<button id="toggle-theme">`) — alterna las CSS vars.

## Limitaciones conocidas

Ver `AUDIT.md` en la raíz del repo para issues de seguridad/bugs detectados.
Resumen rápido:

- Equity es placeholder con slippage hasta que haya FIFO real en backend.
- innerHTML sin escape (data viene de DB controlada — defensa en
  profundidad pendiente).
- API sin autenticación (OK localhost — agregar antes de exponer al exterior).
