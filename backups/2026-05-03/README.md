# Backup 2026-05-03 — Curva de Equity Rediseño

## Archivos respaldados

| Archivo | Descripción |
|---------|-------------|
| sentinel-app.js.original | Rendering logic del dashboard (incluye renderEquity()) |
| sentinel-data.js.original | State & data fetchers (incluye synthEquityHist()) |
| index.html.original | SPA principal del dashboard (sección equity) |
| api.py.original | FastAPI backend (antes de agregar portfolio-history) |

## Cambios realizados

- Nuevo endpoint GET `/api/account/portfolio-history` en api.py (read-only, Alpaca)
- Curva de equity rediseñada: breakeven line, color verde/rojo dinámico, selector de período (4H, 8H, 1D, 1W, 1M, 1Y)
- HTML actualizado: selector de período reemplaza texto fijo "últimas 24h"
- Cache-bust actualizado en script tags

## Restauración

```bash
cp backups/2026-05-03/sentinel-app.js.original dashboard/sentinel-app.js
cp backups/2026-05-03/sentinel-data.js.original dashboard/sentinel-data.js
cp backups/2026-05-03/index.html.original dashboard/index.html
cp backups/2026-05-03/api.py.original sentinel-v0.5/api.py
```
