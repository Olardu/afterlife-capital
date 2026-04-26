# Changelog

All notable changes to Afterlife Capital — Sentinel v0.5 are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 2026-04-25

### Changed
- **Dashboard reemplazado por integración del handoff oficial de Claude
  Design** sobre branch `feature/design-handoff-integration`.
  - HTML/CSS pixel-perfect del prototipo (`Sentinel Dashboard v2.html`).
  - Lógica de render (`sentinel-app.js`) tal cual del handoff.
  - i18n en 4 idiomas (`sentinel-i18n.js`) tal cual del handoff.
  - `sentinel-data.js` reescrito custom para conectar a `/api/*` con SSE,
    reemplazando el mock + tick loop original.

### Added
- `dashboard/sentinel-i18n.js`, `dashboard/sentinel-app.js` — copiados del handoff oficial.
- `dashboard/sentinel-data.js` — orquestador de fetch + SSE; mantiene contenido
  editorial fijo (citas Matrix/Cyberpunk, AGENTS, AGENT_ICONS) hardcoded
  porque no son datos de API.
- `dashboard/assets/favicon.svg` y `favicon-mono-cyan.svg`.
- `dashboard/HANDOFF_INTEGRATION.md` — tabla de mapeo handoff↔API + endpoints
  consumidos + limitaciones declaradas.
- `dashboard/README.md` — stack, estructura, cómo modificar cada sección,
  cómo agregar Sentinel/idioma, variables CSS, limitaciones.
- `CHANGELOG.md` — este archivo.
- `MERGE_REPORT.md` — reporte final de merge propuesto.

### Removed
- `design-handoff-temp/` — copia local del bundle del handoff. Borrada tras
  copiar archivos a `dashboard/`. (Era untracked, no afecta historia git.)

### Notes técnicas
- El tick loop mock del handoff (`setTimeout(tick, 2500)` en `sentinel-app.js`)
  se neutraliza interceptando `setTimeout` antes de que `app.js` cargue:
  `sentinel-data.js` reemplaza temporalmente `window.setTimeout` y descarta
  llamadas con `fn.name === 'tick'`. Los datos reales llegan solo por SSE.
- Persistencia de `lang`/`view`/`theme` en `localStorage` agregada por
  `sentinel-data.js` vía event delegation (sin tocar `sentinel-app.js`).
- Datos derivados o sintéticos (equity history, news titles, logs) están
  marcados con TODO en `HANDOFF_INTEGRATION.md` para futuras extensiones de
  la API.

### No tocado
- `sentinel-v0.5/api.py` — instrucción explícita.
- `dashboard/index1.html`, `dashboard/index2.html` — untracked, respetados.

---

## [0.5.0] — 2026-04-25 (anterior, en main)

### Added
- Backend FastAPI completo (`sentinel-v0.5/api.py`) con endpoints REST
  `/api/status`, `/api/sentinels`, `/api/trades`, `/api/macro`,
  `/api/performance`, `/api/report`, SSE en `/api/sse`, dashboard estático en `/`.
- Migración multi-ticker: tabla `sentinel_tickers` (relación N:M), refactor
  de `BaseSentinel` para operar múltiples tickers en paralelo, estado
  `last_signal` y opening ranges por ticker.
- 9 Sentinels operativos en DB con 3 tickers cada uno.
- Dashboard standalone HTML/CSS/JS vanilla con Chart.js CDN, 4 idiomas,
  toggle Cyberpunk/Sobrio (sustituido en este Unreleased por el handoff oficial).
- 9 estrategias implementadas: SMA Crossover, RSI Short, Bollinger Bounce,
  MACD+Volume, ORB, EMA Triple, VWAP Reversion, RSI Divergence, Bollinger Squeeze.

### Disabled
- `S-10 RegimeClassifier` desactivado (accuracy 0.3849 sobre 3 clases).

### Fixed
- `feed=DataFeed.IEX` faltante en 4 archivos (causaba 403 SIP en cuenta paper).

### Security
- `meridian/.claude/.credentials.json` purgado del Drive.
- `sync-drive.ps1` con `--delete-excluded` y patrones recursivos `**/`.

---

## [0.1.0] — 2026-04-22

### Added
- Landing page Afterlife Capital v2.
- Favicon SVG.
- Sentinel panel link.
- i18n ES/JA/TH sincronizado con estado v0.1.
