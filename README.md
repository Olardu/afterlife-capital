# Afterlife Capital — Sentinel v0.5

Sistema de trading algorítmico multi-agente con 9 estrategias autónomas
operando en paralelo sobre múltiples tickers, con dashboard web en vivo.
Paper trading vía Alpaca IEX hasta validación. Multi-tenant.

## Estructura del repo

```
afterlife-capital/
├── index.html                  Landing page (Afterlife Capital site)
├── dashboard/
│   ├── index.html              Dashboard SPA (vanilla JS + Chart.js)
│   ├── README.md               Documentación del dashboard
│   └── REDESIGN_PLAN.md        Plan del redesign visual 2026-04-25
├── sentinel-v0.5/
│   ├── api.py                  Backend FastAPI (REST + SSE)
│   ├── main.py                 Loop principal de trading
│   ├── dispatcher.py           Orquestador (Half-Kelly, kill-switch)
│   ├── historian.py            Persistencia PostgreSQL (asyncpg)
│   ├── the_ear.py              Macro context (NewsAPI, VIX/SPY)
│   ├── correlation_guard.py    Pearson rolling 60 velas
│   ├── regime_classifier.py    S-10 (desactivado temporalmente)
│   ├── sentinels/__init__.py   BaseSentinel + 9 estrategias concretas
│   ├── db/schema.sql           7 tablas con multi-tenant owner_id
│   ├── CLAUDE.md               Estado del proyecto
│   └── requirements.txt        Dependencias Python
├── AUDIT.md                    Issues de seguridad/bugs encontrados
└── CHANGELOG.md                Historial de cambios (Keep a Changelog)
```

## Dashboard

Dashboard web en `dashboard/index.html`. Servido por `api.py` en la raíz `/`.

Features:
- Header sticky con indicadores en vivo
- Gauge SVG del risk score de The Ear
- Accordion expandible por Sentinel (cita + descripción + tickers)
- Mini equity charts por Sentinel
- Terminal logs estilo macOS
- 4 idiomas (ES/EN/JA/TH)
- Toggle Cyberpunk/Sobrio
- Conexión a API real con auto-refresh vía SSE cada 15min

Documentación detallada: [`dashboard/README.md`](dashboard/README.md).

## Cómo arrancar

```powershell
cd sentinel-v0.5
venv\Scripts\python.exe api.py
```

API + dashboard en `http://localhost:8080/`.

Requisitos:
- PostgreSQL 18 (servicio `postgresql-x64-18` en Windows)
- `.env` con credenciales (Alpaca paper + NewsAPI). Copiar `.env.example`.
- Python 3.14+ con venv y `pip install -r requirements.txt`.

## Estado actual (2026-04-25)

- **9 Sentinels** activos en DB con 3 tickers c/u (27 registros en `sentinel_tickers`)
- **API operativa**: REST + SSE + dashboard servido
- **Dashboard rediseñado** en branch `feature/dashboard-redesign` (pendiente merge)
- **0 trades reales** todavía — primera corrida en mercado abierto pendiente
- **S-10 RegimeClassifier** desactivado (accuracy insuficiente, TODO en código)

Ver [`CHANGELOG.md`](CHANGELOG.md) para historial detallado y
[`AUDIT.md`](AUDIT.md) para issues abiertos.

## Branches

- `main` — versión de producción (con dashboard pre-redesign)
- `feature/dashboard-redesign` — redesign visual en curso
- `backup/pre-redesign-2026-04-25` — snapshot inmutable previo al redesign
