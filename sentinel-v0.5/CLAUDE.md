# Sentinel v0.5

Sistema de trading algorítmico multi-agente. 9 estrategias autónomas (Sentinels) coordinadas por un Dispatcher, con protecciones macro, gestión de capital Half-Kelly y persistencia en PostgreSQL. Operación en paper trading hasta validar.

## Stack

- Python 3.14, asyncio
- PostgreSQL 18 nativo en Windows (servicio `postgresql-x64-18`)
- alpaca-py con feed IEX (paper)
- aiohttp + NewsAPI (macro)
- scikit-learn (RandomForest, S-10 desactivado)
- pandas (cálculos manuales de indicadores, sin ta-lib)
- LangGraph: planeado, todavía no implementado (loop manual en `main.py`)

## Componentes

| Archivo | Rol |
|---|---|
| `main.py` | Entry point, initialize() + main_loop() alineado a 15 min ET |
| `config.py` | Constantes y validación de credenciales |
| `historian.py` | Pool asyncpg, signals/trades, performance decay |
| `dispatcher.py` | Orquestador: kill-switch, sizing Half-Kelly, ejecución Alpaca |
| `the_ear.py` | NewsAPI cada 15min, VIXY/SPY change, Circuit Breaker, Parking Brake |
| `correlation_guard.py` | Pearson manual sobre rolling 60 velas, umbral 0.75 |
| `regime_classifier.py` | S-10 RandomForest BULL/NEUTRAL/BEAR — **DESACTIVADO** |
| `sentinels/__init__.py` | BaseSentinel + 9 estrategias |
| `api.py` | FastAPI backend (REST + SSE) en puerto 8080. Sirve dashboard estático. |
| `db/schema.sql` | 7 tablas con multi-tenant `owner_id` |
| `db/003_add_order_id_to_trades.sql` | Migración aplicada 2026-04-25: columna order_id en trades. |
| `db/004_create_system_state.sql` | Migración 2026-04-26: tabla system_state (canal IPC api↔main para kill switch). |
| `email_service.py` | Cliente async de Resend para welcome/removal emails (templates Design). |

## 9 Sentinels operativos

| # | Tipo | Lógica |
|---|---|---|
| S-1 | sma_crossover | Cruce SMA(10)/SMA(50) |
| S-2 | rsi_short | RSI(2): <15 BUY / >85 SELL |
| S-3 | bollinger_bounce | Cierre fuera de BB(20, 2σ) |
| S-4 | macd_volume | MACD(12,26,9) + volumen >1.5×SMA(20) |
| S-5 | orb_breakout | Opening Range Breakout 9:30 ET |
| S-6 | ema_triple | EMA 8>21>55 alineadas |
| S-7 | vwap_reversion | Cierre fuera de VWAP±2σ intraday |
| S-8 | rsi_divergence | Divergencia RSI(14) en swings (k=3) |
| S-9 | bollinger_squeeze | BBW percentil 10 + breakout |

S-10 (RegimeClassifier) está implementado pero desactivado con early returns documentados — accuracy 0.3849 sobre 3 clases es casi random. Reactivar cuando haya 50-100 trades reales y features adicionales (RSI, MACD, breadth, yield curve).

## Arrancar

```powershell
cd sentinel-v0.5
venv\Scripts\activate
python main.py
```

Requiere PostgreSQL servicio activo y `.env` con credenciales.

## Estado actual (2026-04-26 — bot lanzado en paper trading)

✅ **Operativo y corriendo**:
- API + Cloudflare Tunnel + main.py corriendo en 3 ventanas, esperando 9:30 ET 2026-04-27 (lunes).
- DB con 9 Sentinels (5% allocation cada uno, 45% total). 27 tickers en `sentinel_tickers`.
- Auth Google OAuth con roles ADMIN/VIEWER. Único ADMIN: `***REMOVED-EMAIL***`. Único VIEWER: `goorale@gmail.com`.
- Kill switch operacional: botón DETENER/INICIAR del dashboard dispara halt/resume vía DB flag, poller cada 5s en `main.py` ejecuta `activate_kill_switch`/`deactivate_kill_switch`.
- Panel admin en `/admin` (ADMIN-only): CRUD de usuarios con welcome/removal email automático vía Resend desde `noreply@afterlifecapital.co` (dominio verificado).

### Hardening post-auditoría (sesiones 1–4 — 2026-04-25 / 2026-04-26)

**Sesiones 1–2.5** (2026-04-25):
- `#H-2` Race TheEar → `asyncio.Lock`.
- `#H-3` Timeouts asyncpg + `asyncio.wait_for` en los 11 call sites Alpaca.
- `#H-5` open_positions desync → refactor `list[dict]` → `dict[str, dict]`.
- `#H-6` Limit orders en background con `_check_later` + migración 003 (`order_id`).
- `_is_limit_strategy` set explícito; `approved = status == "FILLED"`; `done_callback` en ear_task.

**Sesión 3** (2026-04-26 — kill switch + Sharpe):
- `#H-7` kill switch operacional: tabla `system_state` (migración 004) como canal IPC entre `api.py` y `main.py`. Endpoints `POST /api/system/halt`, `POST /api/system/resume`, `GET /api/system/state`. Poller en `main.py` cada 5s. Frontend toggle DETENER/INICIAR.
- Sharpe annualization (#TECHDEBT promovido): factor `sqrt(252×26) ≈ 80.94` aplicado en `historian.calculate_performance`.

**Sesión 4** (2026-04-26 — auth + admin panel + integración Design):
- `#H-1` Google OAuth: rutas `/auth/login,callback,logout,me` con Authlib + SessionMiddleware (cookie firmada itsdangerous, HttpOnly, Secure, SameSite=Lax, 24h). Middleware `auth_middleware` con matriz de gating (público / sesión / role=ADMIN).
- Roles ADMIN/VIEWER aplicados en endpoints. VIEWER no ve botón DETENER ni link ADMIN; `/admin` redirige silently a `/`.
- Panel admin (`/admin`): handoff Design integrado (`admin.html` + `admin-app.js`) con adapter `user_id → id` para mantener API.
- Email service Resend con templates HTML del handoff Design (welcome bilingüe ES/EN con bloque permisos ADMIN, revoked bilingüe ES/EN). Envío async con httpx.

### Issues 🟠 ALTOS — estado al 2026-04-26
- ✅ #H-1 (auth API)
- ✅ #H-2 (race TheEar)
- ✅ #H-3 (timeouts)
- ✅ #H-5 (open_positions)
- ✅ #H-6 (limit orders)
- ✅ #H-7 (kill switch)
- ⏳ **#H-4 — float→Decimal en cálculos financieros**. Único 🟠 pendiente. Probable sesión 5.

### Branches
- `main` — actualizada hoy con `adb84a3` (merge --no-ff feature/admin-panel + handoffs Design).
- `feature/design-handoff-integration` — mergeada en main vía `f5e6384` (v2.3).
- `feature/admin-panel` — mergeada en main vía `adb84a3` (v2.4 efectiva).
- `backup/pre-redesign-2026-04-25` — snapshot inmutable.

## Decisiones clave

- **Sin Docker**: PostgreSQL 18 nativo en Windows (Docker Desktop fallaba en setup inicial).
- **Refactor BaseSentinel**: `fetch_bars`, `_fetch_bars_sync`, `run` centralizados. Cada Sentinel solo define `__init__` + `analyze`.
- **`feed=DataFeed.IEX` obligatorio**: la cuenta paper sin SIP da 403 al pedir datos recientes. Aplicado en los 4 sitios que hacen StockBarsRequest.
- **S-10 desactivado**: ahorra 30-60s de arranque (no descarga 25 años de SPY ni entrena RF). `get_regime()` retorna `"NEUTRAL"` fijo. Reactivar editando los early returns en `regime_classifier.py`.
- **RSI con SMA, no Wilder**: cálculo simplificado en `_rsi()`. Diferencia marginal vs Wilder smoothing — mejorar después si hace falta.
- **Logs**: `logs/sentinel.log` con RotatingFileHandler (5MB, 3 backups).

## Próximos pasos

1. **Lunes 2026-04-27 9:30 ET** — primera corrida real (bot ya corriendo, esperando apertura). Roman vuelve del trabajo y revisa logs + dashboard.
2. **Sesión 5** (cuando Roman tenga energía): `#H-4` float→Decimal en cálculos financieros (último 🟠 ALTO pendiente). También dashboard hardening: XSS innerHTML, race SSE, defensa Chart.js.
3. Implementar nodo LangGraph real en `main.py` (actualmente loop manual con `asyncio.gather`).
4. Mejorar `_rsi()` a Wilder smoothing (S-2, S-8).
5. Reactivar S-10 cuando criterios estén (50–100 trades + features adicionales).
6. Deploy a Raspberry Pi 5.

## Bugs conocidos

- Ninguno bloqueante al cierre 2026-04-26.
- ORB y VWAP retornan `price=0.0` cuando no hay barras del día actual ET (sábado/domingo o pre-market). El `run()` filtra por `qty=0.0` así que no afecta el pipeline, pero es estéticamente raro en logs.
- `record_trade` falla si la migración 003 no se aplicó (no validamos schema al startup). Aplicada manualmente en local.
- `update_trade_status` no warns si 0 rows afectados (ej. order_id no existe en DB).
- `record_trade` se hace en el mismo try que `record_signal`; si `record_signal` falla, la orden ya está en Alpaca pero sin fila DB.
- Reconciliación post-restart de limit orders: si el sistema cae con tasks `_check_later` en vuelo, mueren con el proceso. La orden Alpaca queda activa pero sin tracking. TODO en `dispatcher.execute_order`.
- `system_halted` flag persiste entre reinicios pero el Dispatcher arranca con `kill_switch_active=False` in-memory. Discrepancia hasta que el poller reaccione a un nuevo `halt_requested` o `resume_requested`.
- `OWNER_EMAIL` hardcodeado en dos lugares (`historian._OWNER_EMAIL` y `admin-app.js`). Si cambia el admin Google, hay que editar ambos.

## Seguridad

- Multi-tenant: todo dato lleva `owner_id`. Owner actual: `roman` / `***REMOVED-EMAIL***` (UUID `***REMOVED-UUID***`).
- `.env`, `client_secret_*.json`, `.claude/` excluidos de git y de Drive sync.
- NEWS_API_KEY enviado en header `X-Api-Key` (nunca en URL params).
- Kill switch: `dispatcher.activate_kill_switch("CONFIRMAR")` requiere passphrase exacta. Disparable desde `/api/system/halt` (ADMIN-only) o desde el botón DETENER del dashboard.
- Auth: Google OAuth con cookie firmada itsdangerous (HttpOnly, Secure, SameSite=Lax, max-age 24h). Solo emails registrados en `users` reciben sesión válida.
- Resend: dominio verificado `afterlifecapital.co`. Emails desde `noreply@afterlifecapital.co` con `X-Entity-Ref-ID` para tracking.
