# Plan de redesign visual del dashboard

Fecha: 2026-04-25
Branch: `feature/dashboard-redesign`

## Contexto

`dashboard/index.html` actual (1186 líneas, 48 KB) está conectado a la API real
(`/api/status`, `/api/sentinels`, `/api/trades`, `/api/macro`, `/api/performance`,
`/api/sse`) pero perdió features visuales del diseño original generado en
Claude Design.

`dashboard/index1.html` (230 KB, bundle minificado de Claude Design con datos
mock) sirve **solo como referencia visual**. No se puede extraer estructura
del bundle minificado de forma directa: el contenido visual está en JSX dentro
de un único `<script>` JS bundleado en una sola línea — la búsqueda con grep
solo confirma presencia pero no permite reconstruir la estructura.

Las 5 features a recuperar las dictó el usuario explícitamente y se documentan
abajo. Decisiones técnicas (selector CSS, animaciones, estructura DOM) son
propias — no copiadas del bundle.

## Estado actual (auditoría visual de `dashboard/index.html`)

| Sección                  | Implementación actual | Línea aprox |
|--------------------------|-----------------------|-------------|
| Header `.topbar`         | `<header>` estático, scrollea con la página | 305 |
| Risk score               | Pill texto en topbar + card en summary | 332 / 696 |
| Sentinel cards           | Click → scroll a sección `#sentinel-detail-section` | 813 |
| Mini equity por sentinel | No existe — un solo Chart.js global en sección dedicada | n/a |
| Logs                     | `<details><summary>` simple sin estilo terminal | 365 |

## Features faltantes vs diseño original

| # | Feature | Descripción visual | Complejidad | Riesgo | Orden |
|---|---------|--------------------|-------------|--------|-------|
| 2.1 | Header sticky | El `header.topbar` queda pegado al top al scrollear, con backdrop-filter blur | S | Bajo — solo CSS | 1 |
| 2.2 | Gauge SVG circular | Reemplaza la card de The Ear: arco SVG con `stroke-dasharray` animado, color según umbral (verde/amarillo/rojo). Acompaña al texto con número grande % | M | Bajo — SVG aislado | 2 |
| 2.3 | Accordion por Sentinel | Reemplaza scroll-to-detail. Click en card expande inline mostrando cita + descripción + tabla de tickers. Se cierra con segundo click | M | Medio — toca markup y handlers existentes | 3 |
| 2.4 | Mini-charts equity | Cada `.sent-card` muestra un mini canvas Chart.js (línea ~80px alto, sin labels, color cyan) con equity placeholder | M | Medio — instanciar 9 Chart.js, cuidar destroy en re-render | 4 |
| 2.5 | Terminal logs estilo macOS | Header de la sección logs con 3 dots (rojo/amarillo/verde simulando close/min/max), título "sentinel.log", body fuente mono con colores por nivel (INFO cyan, WARN amarillo, ERROR rojo) | S | Bajo — solo CSS + render lines | 5 |

## Convenciones de implementación

- **Vanilla JS** — no agregar React/Vue/etc.
- **CSS vars existentes** — reutilizar `--primary`, `--accent`, `--good`, `--bad`,
  `--warn`. No introducir nuevas paletas.
- **Tema sobrio** — todas las features deben funcionar en `data-theme="sobrio"`
  (animaciones desactivadas o atenuadas, colores muted).
- **i18n** — cualquier string nuevo se agrega a las 4 entradas de `I18N`.
- **Empty states** — toda feature data-driven debe manejar arrays vacíos sin
  romperse y sin mostrar gráficos rotos.

## Estrategia de seguridad

- Cada feature 2.X es 1 commit en `feature/dashboard-redesign`.
- Si una feature rompe algo crítico que no se arregla en 15 minutos, se salta
  y se documenta en este archivo en la sección "Saltos" abajo.
- Toda la implementación se prueba arrancando la API local y haciendo `curl /`
  + verificación de ausencia de errores en la respuesta servida (hacer fetch
  desde el navegador real está fuera del scope del agente; se confía en el
  parse del HTML y las verificaciones del `data-i18n-key` y los IDs).

## Saltos

(Vacío al iniciar — se llena durante la implementación si alguna feature
queda pendiente).
