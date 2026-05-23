# Backups del 2 de Mayo 2026 - Auditoria del Sistema

## Para restaurar: copiar el archivo .original sobre el actual

## Archivos respaldados

| Archivo | Ubicacion original | Contenido |
|---|---|---|
| api.py.original | sentinel-v0.5/api.py | API antes de: imports Alpaca, filtro fecha, endpoint /api/account/equity |
| sentinel-data.js.original | dashboard/sentinel-data.js | Antes de: fetchAndRenderKPIs, renderFallbackKPIs, synthEquityHist real |
| sentinel-app.js.original | dashboard/sentinel-app.js | Antes de: mini-curvas reales, Win/Sharpe "--" cuando sin datos |
| index.html.current | dashboard/index.html | Version con cache-bust ?v=20260502c (no hay original pre-cache-bust) |

## Cambios realizados (en orden)

### Ronda 1 - Correcciones de la auditoria
1. **api.py**: Importo ALPACA_API_KEY/SECRET_KEY desde config
2. **api.py**: Agrego OBSERVATION_START = 2026-04-28 y filtro en /api/trades
3. **api.py**: Nuevo endpoint /api/account/equity (read-only desde Alpaca)
4. **sentinel-data.js**: renderEmptyKPIs() reemplazado por fetchAndRenderKPIs()
5. **sentinel-data.js**: renderFallbackKPIs() para cuando el endpoint falla

### Ronda 2 - Dashboard solo datos reales (Alpaca como fuente de verdad)
6. **sentinel-app.js**: Mini-curvas de Sentinels ahora usan trades FILLED reales (antes: Math.sin fake)
7. **sentinel-app.js**: Win% y Sharpe muestran "--" cuando no hay datos (antes: "0%" y "0.00")
8. **sentinel-data.js**: synthEquityHist() ahora usa trades FILLED con precio real (antes: linea plana fake)
9. **sentinel-data.js**: Fix doble $$ en KPIs (removido '$' prefix, HTML ya lo trae)
10. **index.html**: Cache-bust ?v=20260502c en script tags

### Ronda 3 - Detalle por Sentinel: vigilancia vs operacion + fixes UI
11. **sentinel-app.js**: Tickers sin trades muestran "VIGILANDO" en vez de senal (antes: BUY/SELL/—)
12. **sentinel-app.js**: P&L muestra "LONG N"/"SHORT N" para posiciones abiertas sin round-trip
13. **sentinel-app.js**: Alineacion centrada para valores "—" y "LONG/SHORT" en tablas de detalle
14. **sentinel-data.js**: Fix signo duplicado en PnL KPI ("+$+46.48" → "+46.48")
15. **sentinel-data.js**: eqCapital/eqPnl ahora incluyen "$" prefix
16. **sentinel-data.js**: HORA en ultimos trades cambiado de HH:MM:SS a MM-DD HH:MM
17. **index.html**: Removido "+$" hardcoded antes de span osPnl
18. **index.html**: Cache-bust → ?v=20260502e

| sentinel-app.js.pre-ronda3 | dashboard/sentinel-app.js | Antes de Ronda 3 (post-Ronda 2) |

### Script auxiliar (no requiere backup)
- **sentinel-v0.5/reconcile_pending_trades.py**: Reconcilio 22 trades PENDING_NEW con Alpaca (todos FILLED)

### Nuevo: CHANGELOG-UI.md
- **dashboard/CHANGELOG-UI.md**: Registro de TODOS los cambios de interfaz para sincronizar con Claude Design


### Adopción de posiciones huérfanas
19. **adopt_orphan_positions.py**: Registró BUY retroactivo de MSFT ($424.60) → Neo/S-8
20. **adopt_orphan_positions.py**: Registró BUY retroactivo de XLP ($82.75) → Oracle/S-3
- Justificación: posiciones abiertas en Alpaca sin registro en DB (compras previas al período de observación). Se registran para mantener flujo de datos limpio y evitar ruido durante la observación.
- trade_ids: d4a3b87f-c366-4db1-890a-77bb3b83ae6a (MSFT), b7f78c3e-d8d2-41b8-89b7-3377cfe9aad0 (XLP)


### Ronda 6 — Conectar Frente C (frontend-only)
| sentinel-data.js.pre-ronda6 | dashboard/sentinel-data.js | Antes de: uptime real, agents i18n |
| sentinel-i18n.js.pre-ronda6 | dashboard/sentinel-i18n.js | Antes de: agents_active_label, foot_demo live |
| index.html.pre-ronda6 | dashboard/index.html | Antes de: footUptime id, cache-bust r6fix3 |

21. **sentinel-data.js**: fetchAndRenderBuild() ahora también extrae uptime_hours
22. **sentinel-data.js**: Removido footUptime _DASH de KPI functions (evita overwrite)
23. **sentinel-data.js**: agents_active_label usa i18n
24. **sentinel-i18n.js**: foot_demo → "Sistema en vivo" (4 idiomas)
25. **index.html**: footUptime con id, cache-bust → r6fix3

## Como restaurar todo a estado pre-auditoria
```
copy backups\2026-05-02\api.py.original sentinel-v0.5\api.py
copy backups\2026-05-02\sentinel-data.js.original dashboard\sentinel-data.js
copy backups\2026-05-02\sentinel-app.js.original dashboard\sentinel-app.js
```
Luego reiniciar la API.
