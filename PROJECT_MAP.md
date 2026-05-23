# PROJECT_MAP.md — Afterlife Capital

**Actualizado:** 2026-05-05
**Versión:** Sentinel v0.5
**Estado:** Fase 0 — Observación protegida (→ 2026-05-27)

---

## Estructura del repositorio

```
afterlife-capital/
├── sentinel-v0.5/          # Backend del bot de trading
│   ├── main.py             # Entry point del bot — orquesta el ciclo principal
│   ├── api.py              # FastAPI — dashboard API + scheduler de reportes
│   ├── historian.py         # ORM/DAL — PostgreSQL, schema, queries
│   ├── dispatcher.py        # Asignación de capital + ejecución de órdenes
│   ├── the_ear.py           # Análisis macro — NewsAPI + riesgo + circuit breaker
│   ├── correlation_guard.py # Filtro de correlación entre Sentinels
│   ├── universe_selector.py # Rotación de tickers via Claude API
│   ├── regime_classifier.py # S-10 — clasificador de régimen (desactivado)
│   ├── market_clock.py      # Horarios NYSE, festivos, estado del mercado
│   ├── config.py            # Constantes y thresholds del sistema
│   ├── email_service.py     # Templates y envío de emails (Resend API)
│   ├── claude_client.py     # Cliente para Claude API (Anthropic)
│   ├── crypto_utils.py      # Encriptación de API keys (Fernet)
│   ├── adopt_orphan_positions.py  # Reconcilia posiciones huérfanas de Alpaca
│   ├── reconcile_pending_trades.py # Sincroniza trades pendientes
│   ├── restart_api.py       # Script helper para reiniciar api.py
│   ├── run_adopt.py         # Script helper para ejecutar adopt_orphan
│   ├── .env                 # Variables de entorno (NO en git)
│   ├── CLAUDE.md            # Instrucciones para Claude Code (NO modificar)
│   ├── venv/                # Entorno virtual Python 3.14
│   ├── logs/                # Logs del sistema
│   └── db/                  # Migraciones SQL
│
├── dashboard/               # Frontend SPA del dashboard
│   ├── index.html           # Dashboard principal — monolito HTML
│   ├── admin.html           # Panel de administración
│   ├── sentinel-app.js      # Lógica del dashboard (fetch, render, SSE)
│   ├── sentinel-data.js     # Transformación de datos para gráficos
│   ├── sentinel-i18n.js     # Internacionalización (ES/EN/FR/PT)
│   ├── admin-app.js         # Lógica del panel admin
│   ├── CHANGELOG-UI.md      # Registro de cambios visuales (para Claude Design)
│   └── assets/              # Favicons SVG
│
├── API_REFERENCE.md         # Documentación completa de la API
├── ENDPOINTS_BACKLOG.md     # Plan de endpoints futuros con prioridades
├── OBSERVATION_PERIOD.md    # Reglas del período de observación
├── PROJECT_MAP.md           # Este archivo
├── CHANGELOG.md             # Historial general de cambios
├── AUDIT_FULL.md            # Auditoría de sistema (2026-05-02)
├── TECHDEBT.md              # Deuda técnica documentada
├── DESIGN_CHANGES.md        # Cambios de diseño visual
│
├── backups/                 # Backups catalogados por fecha
│   ├── 2026-05-02/
│   └── 2026-05-03/
│
├── templetes-correo/        # Diseños de templates de email
├── panel-admin/             # Diseños del panel admin
└── index1.html              # Landing page (desplegada en Vercel)
```

---

## Módulos del bot — qué hace cada uno

### main.py (~480 líneas)
**Rol:** Cerebro operativo. Orquesta el ciclo de trading cada 15 minutos.
**Flujo:** Inicializa Sentinels → genera señales (asyncio.gather) → pasa al Dispatcher → registra resultados.
**Depende de:** config, historian, dispatcher, the_ear, correlation_guard, market_clock, regime_classifier
**Funciones clave:** `run_cycle()`, `main()`, las 9 estrategias de Sentinels (S-1 a S-9)

### api.py (~1860 líneas)
**Rol:** API REST + dashboard + scheduler de reportes diarios.
**Framework:** FastAPI con Uvicorn en puerto 8080.
**Depende de:** historian, email_service, config, crypto_utils
**Secciones principales:**
- Autenticación (Google OAuth)
- Endpoints core (/api/status, /api/sentinels, /api/trades, /api/macro)
- Cuenta Alpaca (/api/account/equity, /api/account/portfolio-history)
- Admin (usuarios, API keys, rotaciones)
- Kill switch (/api/system/halt, /api/system/resume)
- Reporte diario (/api/report/daily, /api/report/daily/send-now)
- Scheduler automático 16:30 ET L-V
- SSE streaming (/api/sse)
- Dashboard estático (mount en /)

### historian.py (~1650 líneas)
**Rol:** Capa de datos. Todo lo que toca PostgreSQL pasa por aquí.
**Conexión:** asyncpg pool al PostgreSQL local.
**Schema:** Tablas — users, sentinels, sentinel_tickers, trades, signals, macro_events, rotation_decisions, system_state, api_keys
**Funciones clave:** `init_db()`, `record_trade()`, `record_signal()`, `get_sentinels()`, `record_rotation_decision()`, `list_users()`

### dispatcher.py (~717 líneas)
**Rol:** Decide cuánto capital asignar y ejecuta órdenes en Alpaca.
**Algoritmo:** Sharpe-weighted Half-Kelly (5%-25% por Sentinel).
**Depende de:** config, historian, alpaca SDK
**Funciones clave:** `allocate_capital()`, `apply_regime_adjustment()`, `process_signal()`, `run_cycle()`

### the_ear.py (~445 líneas)
**Rol:** Centinela macro. Escucha noticias y calcula riesgo sistémico.
**Fuente:** NewsAPI — filtra por keywords de riesgo.
**Threshold:** risk > 0.7 → circuit breaker (veta trades).
**Depende de:** config, historian
**Funciones clave:** `evaluate()`, `_calculate_risk_score()`, `_check_circuit_breaker()`

### correlation_guard.py (~276 líneas)
**Rol:** Evita que múltiples Sentinels operen activos correlacionados.
**Acción:** Reduce qty o descarta señales cuando la correlación es alta.
**Depende de:** config, scipy (para cálculos estadísticos)

### universe_selector.py (~717 líneas)
**Rol:** Rota tickers de bajo rendimiento usando Claude API.
**Trigger:** Sentinel con win rate bajo o performance degradada.
**Depende de:** claude_client, historian, config

### config.py (~178 líneas)
**Rol:** Constantes centralizadas del sistema.
**Contenido:** Thresholds (Kelly fraction, capital min/max, risk threshold), intervals, timezone, holidays NYSE.

### email_service.py (~1432 líneas)
**Rol:** Templates HTML y envío de emails vía Resend API.
**Templates:** Welcome, revoked access, rotation notification, daily report.
**Estilo:** Tema claro/sobrio, Courier New, compatible Outlook/Gmail/Apple Mail.

### market_clock.py (~145 líneas)
**Rol:** Sabe si el mercado está abierto, próxima apertura, festivos NYSE.

### crypto_utils.py (~76 líneas)
**Rol:** Encriptación/desencriptación de API keys con Fernet.

---

## Flujo de datos principal

```
NewsAPI → the_ear.py (riesgo)
                ↓
main.py → 9 Sentinels generan señales
                ↓
correlation_guard.py (filtra correlación)
                ↓
dispatcher.py (asigna capital + ejecuta en Alpaca)
                ↓
historian.py (registra en PostgreSQL)
                ↓
api.py (sirve datos al dashboard + emails)
```

---

## Base de datos (PostgreSQL 18)

**Tablas principales:** users, sentinels, sentinel_tickers, trades, signals, macro_events, rotation_decisions, system_state, api_keys

**Conexión:** Definida en .env como DATABASE_URL, pool manejado por asyncpg en historian.py.

---

## Infraestructura

- **Runtime:** Python 3.14, Windows local (máquina de Roman)
- **DB:** PostgreSQL 18 (servicio Windows nativo)
- **API:** FastAPI + Uvicorn en puerto 8080
- **Tunnel:** Cloudflare Tunnel → sentinel.afterlifecapital.co
- **Landing:** Vercel → afterlifecapital.co
- **Emails:** Resend API
- **Broker:** Alpaca (paper trading)
- **IA:** Claude API (Anthropic) para Universe Selector

---

## Documentos de referencia

| Documento | Qué contiene |
|-----------|-------------|
| API_REFERENCE.md | Todos los endpoints con params, responses, auth |
| ENDPOINTS_BACKLOG.md | Endpoints futuros priorizados por fase |
| OBSERVATION_PERIOD.md | Qué se puede y no se puede cambiar hasta el 27 mayo |
| CHANGELOG-UI.md | Cambios visuales del dashboard (para Claude Design) |
| TECHDEBT.md | Deuda técnica pendiente |

---

## Convenciones

- **Backups:** `archivo.py.bak.YYYYMMDD_HHMMSS` antes de cada edición
- **Cache-bust:** Query param `?v=YYYYMMDD` en script tags del dashboard
- **Line endings:** Dashboard usa CRLF, backend usa LF
- **Idioma código:** Variables/funciones en inglés, comentarios en español, UI bilingüe ES/EN
- **CLAUDE.md:** NO modificar — mantenido por Claude Code
