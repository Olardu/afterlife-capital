# Changelog

All notable changes to Afterlife Capital — Sentinel v0.5 are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Dashboard redesign visual** sobre branch `feature/dashboard-redesign`:
  - Header sticky con indicadores de status fijos al scrollear (`feat(dashboard): header sticky con indicadores fijos`).
  - Gauge SVG circular animado para el risk score de The Ear con color por umbral verde/amarillo/rojo (`feat(dashboard): gauge SVG del risk score`).
  - Accordion expandible por Sentinel — click en card expande inline con cita, descripción y tabla de tickers; sólo una abierta a la vez (`feat(dashboard): accordion expandible por sentinel`).
  - Mini equity charts por Sentinel card (Chart.js mini line) con fallback de placeholder visual cuando aún no hay trades (`feat(dashboard): mini-charts de equity por sentinel`).
  - Terminal de logs estilo macOS (3 dots rojo/amarillo/verde, título "sentinel.log") con highlighting por nivel INFO/WARN/ERROR (`feat(dashboard): terminal logs estilo macOS`).
- `dashboard/REDESIGN_PLAN.md` con tabla de features faltantes, complejidades y plan de implementación.
- `AUDIT.md` (raíz) con 6 issues de severidad Media identificados en el dashboard final y la API.
- `dashboard/README.md` con documentación del dashboard, stack, secciones y guías de modificación.
- `CHANGELOG.md` (este archivo) — formato Keep a Changelog.

### Changed
- Reemplazada la sección scroll-to-detail por accordion inline; eliminada `<section id="sentinel-detail-section">` que ya no se usa.
- Reemplazado `<details><summary>` simple de logs por componente `.terminal` con header tipo macOS.

### Security
- Audit en `AUDIT.md` cubre: XSS por innerHTML sin escape (Media), API sin autenticación (Media en localhost / Alta si se expone a internet), curva de equity placeholder con slippage como proxy (Media), bug menor de filtro en mini-charts (Media), race condition potencial en SSE (Media), defensa ausente si Chart.js no carga (Media). No se aplicaron correcciones — solo reporte.

### Backup / Safety
- Branch inmutable `backup/pre-redesign-2026-04-25` creada antes de cualquier cambio visual.
- `dashboard/index.pre-redesign.html` snapshot del dashboard previo persistido en `main` para diff rápido.

---

## [0.5.0] - 2026-04-25

### Added
- Backend FastAPI completo (`sentinel-v0.5/api.py`) con endpoints REST `/api/status`, `/api/sentinels`, `/api/trades`, `/api/macro`, `/api/performance`, `/api/report`, SSE en `/api/sse`, y servicio del dashboard estático en `/`.
- Migración multi-ticker: nueva tabla `sentinel_tickers` (relación N:M), refactor de `BaseSentinel` para operar múltiples tickers en paralelo con `asyncio.gather`, estado `last_signal` y opening ranges por ticker.
- 9 Sentinels operativos en DB con 3 tickers cada uno (45% del capital total asignado).
- Dashboard standalone HTML/CSS/JS vanilla con Chart.js CDN, 4 idiomas (ES/EN/JA/TH), toggle Cyberpunk/Sobrio, conexión a `/api/*` y SSE.
- 9 estrategias implementadas: SMA Crossover (S-1), RSI Short (S-2), Bollinger Bounce (S-3), MACD+Volume (S-4), ORB (S-5), EMA Triple (S-6), VWAP Reversion (S-7), RSI Divergence (S-8), Bollinger Squeeze (S-9). Helper `_rsi`, `_ema`, `_find_swings` reutilizables.
- Fix responsive: tablas con `overflow-x: auto` para mobile.

### Changed
- Renames Cyberpunk-style: MORPHEUS, MANTIS, ORACLE, SILVERHAND, SMASHER, TRINITY, NETRUNNER, NEO, ROGUE.
- Refactor `BaseSentinel` — `fetch_bars`, `_fetch_bars_sync`, `run` movidos a la clase base. Cada Sentinel concreto sólo define `__init__` + `analyze`.

### Disabled
- `S-10 RegimeClassifier` desactivado temporalmente con TODO documentado: accuracy 0.3849 sobre 3 clases es casi random. Reactivar cuando haya 50-100 trades reales y features adicionales (RSI, MACD, breadth, yield curve).

### Fixed
- Bug crítico: `feed=DataFeed.IEX` faltante en 4 archivos (regime_classifier, correlation_guard, the_ear, sentinels/__init__) que causaba 403 SIP en cuenta paper.

### Security
- `meridian/.claude/.credentials.json` purgado del Drive (estuvo expuesto durante varios días).
- `sync-drive.ps1` reescrito con `--delete-excluded` y patrones recursivos `**/`.
- `.gitignore` raíz expandido con `**/.env`, `**/venv/`, `**/__pycache__/`, secretos OAuth, etc.

---

## [0.1.0] - 2026-04-22

### Added
- Landing page Afterlife Capital v2 (Claude Design redesign).
- Favicon SVG integrado.
- Link al Sentinel panel.
- Sincronización i18n ES/JA/TH con estado real v0.1.
