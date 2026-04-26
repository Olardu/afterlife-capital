# api.py
# Backend FastAPI de Sentinel v0.5. Sirve datos reales al dashboard
# (afterlife-capital/dashboard/index.html) vía endpoints REST y SSE.
#
# Multi-tenant: todas las queries filtran por owner_id (cargado al startup
# desde users.username == OWNER_USERNAME). En v0.5 hay un solo owner ('roman').
#
# Las queries van directas a historian.pool — historian.py mantiene su API
# limpia para uso interno del sistema (Dispatcher, run_cycle).
#
# Arrancar: venv\Scripts\python.exe api.py  (puerto 8080)

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import logging
import math
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import os

import uvicorn
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.sessions import SessionMiddleware

from config import (
    DATABASE_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    LOG_LEVEL,
    OAUTH_REDIRECT_URI,
    OWNER_USERNAME,
    PARKING_BRAKE_TIME,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
    TIMEZONE,
)
from historian import Historian


# =============================================================================
# LOGGING — configuración propia (api.py se arranca standalone)
# =============================================================================

def _setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt   = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_h = RotatingFileHandler(
        filename    = "logs/api.log",
        maxBytes    = 5 * 1024 * 1024,
        backupCount = 3,
        encoding    = "utf-8",
    )
    file_h.setFormatter(fmt)

    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_h)


_setup_logging()
logger = logging.getLogger("sentinel.api")


# =============================================================================
# ESTADO GLOBAL
# =============================================================================

historian = Historian(database_url=DATABASE_URL)
_owner_id: Optional[UUID] = None

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _owner_id
    await historian.connect()
    async with historian.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM users WHERE username = $1",
            OWNER_USERNAME,
        )
    if row is None:
        raise RuntimeError(
            f"Usuario '{OWNER_USERNAME}' no existe en users. "
            "Crearlo o ajustar OWNER_USERNAME en .env antes de arrancar la API."
        )
    _owner_id = row["user_id"]
    logger.info(f"API lista | owner_id={_owner_id} | dashboard_dir={DASHBOARD_DIR}")
    yield
    await historian.close()
    logger.info("API cerrada limpiamente.")


# =============================================================================
# APP
# =============================================================================

app = FastAPI(title="SENTINEL v0.5 API", lifespan=lifespan)


# =============================================================================
# OAUTH — Google
# =============================================================================

oauth = OAuth()
oauth.register(
    name                       = "google",
    client_id                  = GOOGLE_CLIENT_ID,
    client_secret              = GOOGLE_CLIENT_SECRET,
    server_metadata_url        = "https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs              = {"scope": "openid email profile"},
)


def _get_session_user(request: Request) -> Optional[dict]:
    """Lee el usuario autenticado de la sesión firmada. None si no hay login."""
    return request.session.get("user")


# Rutas públicas: /auth/* (login flow) + assets estáticos del dashboard.
# El resto requiere sesión. /auth/me responde 401 desde su handler para
# evitar duplicar la lógica acá.
_PUBLIC_PATHS = {
    "/auth/login", "/auth/callback", "/auth/logout",
    "/sentinel-data.js", "/sentinel-app.js", "/sentinel-i18n.js",
    "/favicon.ico",
}
_PUBLIC_PREFIXES = ("/assets/",)

# Endpoints que requieren role=ADMIN. Cambios futuros: agregar acá.
_ADMIN_PATHS = {"/api/system/halt", "/api/system/resume"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Gate de autenticación + autorización por rutas (#H-1).

    - /auth/*, assets, favicon: público.
    - / (dashboard): redirect 302 a /auth/login si no hay sesión.
    - /api/*: 401 si no hay sesión. /api/system/{halt,resume} además 403 si role != ADMIN.
    - Cualquier otra ruta: pasa (StaticFiles atrás del mount root maneja errores).
    """
    path   = request.url.path
    method = request.method

    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    user = _get_session_user(request)

    if path == "/":
        if user is None:
            return RedirectResponse(url="/auth/login", status_code=302)
        return await call_next(request)

    if path.startswith("/api/"):
        if user is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if method == "POST" and path in _ADMIN_PATHS and user.get("role") != "ADMIN":
            return JSONResponse(
                {"error":   "forbidden",
                 "message": "Solo administradores pueden controlar el sistema"},
                status_code=403,
            )
        return await call_next(request)

    return await call_next(request)


# Orden de registro de middlewares — IMPORTANTE.
# Starlette envuelve outside-in: el último `add_middleware` queda más afuera
# (procesa primero en inbound). El decorator @app.middleware("http") de
# auth_middleware se registró antes de estos add_middleware, así que queda
# más adentro que ambos. Resultado del stack inbound:
#   SessionMiddleware → CORSMiddleware → auth_middleware → handler
# Esto garantiza que auth_middleware ya tiene request.session poblada.
#
# `https_only` es configurable via SESSION_HTTPS_ONLY (default true). Sobre
# HTTP localhost la cookie no se setea — por eso el smoke test OAuth real
# se hace contra el dominio público (ver INSTRUCCIONES OPERATIVAS).
_HTTPS_ONLY = os.environ.get("SESSION_HTTPS_ONLY", "true").lower() != "false"

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = False,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key      = SESSION_SECRET,
    session_cookie  = SESSION_COOKIE_NAME,
    max_age         = SESSION_MAX_AGE_SECONDS,
    same_site       = "lax",
    https_only      = _HTTPS_ONLY,
)


_LOGIN_DENIED_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Acceso denegado · Sentinel</title>
<style>
  body { background:#030610; color:#eaeefb; font-family:system-ui,-apple-system,sans-serif;
         display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }
  .card { border:1px solid rgba(0,245,255,0.2); padding:32px 40px; border-radius:8px;
          background:rgba(10,18,32,0.8); max-width:420px; }
  h1 { color:#ff2060; margin:0 0 12px; font-size:18px; letter-spacing:2px; }
  p { color:#aab2c8; line-height:1.5; margin:0 0 20px; }
  a { color:#00f5ff; text-decoration:none; border:1px solid #00f5ff; padding:8px 16px;
      display:inline-block; border-radius:4px; }
  a:hover { background:rgba(0,245,255,0.1); }
  code { color:#00ff88; }
</style></head>
<body><div class="card">
  <h1>+ ACCESO DENEGADO</h1>
  <p>El email <code>{email}</code> no está registrado en este sistema.
     Contactá al administrador para que te dé acceso.</p>
  <a href="/auth/login">Volver al login</a>
</div></body></html>
"""


# =============================================================================
# HELPERS
# =============================================================================

def _to_json(value):
    """Convierte tipos asyncpg/stdlib a tipos JSON-serializables."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    return value


def _row(row) -> dict:
    """asyncpg.Record → dict serializable."""
    return {k: _to_json(v) for k, v in dict(row).items()}


def _is_parking_brake_active() -> bool:
    """True si la hora ET >= PARKING_BRAKE_TIME (no se persiste en macro_events)."""
    now_et = datetime.now(tz=ZoneInfo(TIMEZONE))
    h, m = map(int, PARKING_BRAKE_TIME.split(":"))
    return (now_et.hour, now_et.minute) >= (h, m)


_RANGE_DAYS = {"today": None, "last_week": 7, "last_month": 30, "all": None}

def _range_to_since(range_str: str) -> Optional[datetime]:
    """Traduce range a timestamp UTC naive (para columnas TIMESTAMP sin TZ)."""
    now = datetime.utcnow()
    if range_str == "today":
        return datetime(now.year, now.month, now.day)
    if range_str == "last_week":
        return now - timedelta(days=7)
    if range_str == "last_month":
        return now - timedelta(days=30)
    return None  # 'all' o cualquier otro


def _http_500(operation: str, exc: Exception):
    logger.exception(f"Error en {operation}")
    raise HTTPException(status_code=500, detail=f"{operation}: {exc!s}")


# =============================================================================
# AUTH — Google OAuth (#H-1)
# Flujo: /auth/login redirige a Google → Google retorna a /auth/callback con
# código → intercambiamos por token → leemos email del userinfo → buscamos
# en users → guardamos {email, role, user_id} en la sesión firmada. /auth/logout
# limpia la sesión.
# =============================================================================

@app.get("/auth/login")
async def auth_login(request: Request):
    return await oauth.google.authorize_redirect(request, OAUTH_REDIRECT_URI)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        logger.warning(f"OAuth error en callback: {e.error} — {e.description}")
        return RedirectResponse(url="/auth/login", status_code=302)

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower().strip()
    if not email or not userinfo.get("email_verified"):
        logger.warning(f"Email ausente o no verificado en token: {userinfo!r}")
        return HTMLResponse(_LOGIN_DENIED_HTML.format(email=email or "—"), status_code=403)

    user = await historian.get_user_by_email(email)
    if user is None:
        logger.warning(f"Login rechazado — email no registrado: {email}")
        return HTMLResponse(_LOGIN_DENIED_HTML.format(email=email), status_code=403)

    request.session["user"] = {
        "email":   user["email"],
        "role":    user["role"],
        "user_id": str(user["user_id"]),
    }
    logger.info(f"Login OK | email={email} role={user['role']}")
    return RedirectResponse(url="/", status_code=302)


@app.get("/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=302)


@app.get("/auth/me")
async def auth_me(request: Request):
    """Endpoint utility para que el frontend sepa quién está logueado."""
    user = _get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


# =============================================================================
# ENDPOINTS REST
# =============================================================================

@app.get("/api/status")
async def api_status():
    try:
        async with historian.pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*)::int FROM sentinels
                        WHERE owner_id = $1 AND is_active = TRUE) AS sentinels_active,
                    (SELECT COUNT(*)::int FROM sentinels
                        WHERE owner_id = $1) AS sentinels_total,
                    (SELECT COUNT(*)::int FROM sentinel_tickers st
                        JOIN sentinels s ON st.sentinel_id = s.sentinel_id
                        WHERE s.owner_id = $1 AND st.is_active = TRUE) AS tickers_total,
                    (SELECT risk_score FROM macro_events
                        ORDER BY created_at DESC LIMIT 1) AS risk_score,
                    (SELECT circuit_breaker_triggered FROM macro_events
                        ORDER BY created_at DESC LIMIT 1) AS circuit_breaker
                """,
                _owner_id,
            )
        return {
            "system":           "ONLINE",
            "sentinels_active": stats["sentinels_active"],
            "sentinels_total":  stats["sentinels_total"],
            "regime":           "NEUTRAL",   # S-10 desactivado, régimen fijo
            "tickers_total":    stats["tickers_total"],
            "refresh_interval": "15MIN",
            "risk_score":       float(stats["risk_score"]) if stats["risk_score"] is not None else 0.0,
            "circuit_breaker":  bool(stats["circuit_breaker"]) if stats["circuit_breaker"] is not None else False,
            "parking_brake":    _is_parking_brake_active(),
        }
    except Exception as e:
        _http_500("/api/status", e)


@app.get("/api/sentinels")
async def api_sentinels():
    """
    Sentinels con sus tickers, último signal y métricas de performance.
    pnl es placeholder 0.0 — calcular FIFO BUY/SELL cuando haya trades reales.
    """
    sql = """
        WITH last_signals AS (
            SELECT DISTINCT ON (sentinel_id, ticker)
                sentinel_id, ticker, signal_type, created_at AS signal_at
            FROM signals
            WHERE owner_id = $1
            ORDER BY sentinel_id, ticker, created_at DESC
        )
        SELECT
            s.sentinel_id,
            s.name,
            s.strategy_type,
            s.capital_allocation,
            st.ticker,
            ls.signal_type,
            ls.signal_at,
            ps.win_rate,
            ps.sharpe_ratio,
            ps.total_trades,
            ps.performance_decay
        FROM sentinels s
        JOIN sentinel_tickers st
          ON st.sentinel_id = s.sentinel_id
         AND st.is_active = TRUE
        LEFT JOIN last_signals ls
          ON ls.sentinel_id = s.sentinel_id
         AND ls.ticker = st.ticker
        LEFT JOIN performance_scores ps
          ON ps.sentinel_id = s.sentinel_id
         AND ps.ticker = st.ticker
        WHERE s.owner_id = $1 AND s.is_active = TRUE
        ORDER BY s.name, st.ticker
    """
    try:
        async with historian.pool.acquire() as conn:
            rows = await conn.fetch(sql, _owner_id)
    except Exception as e:
        _http_500("/api/sentinels", e)

    grouped: dict = {}
    for r in rows:
        sid = str(r["sentinel_id"])
        if sid not in grouped:
            grouped[sid] = {
                "sentinel_id":    sid,
                "name":           r["name"],
                "strategy_type":  r["strategy_type"],
                "allocation_pct": float(r["capital_allocation"]),
                "decay_status":   False,
                "total_trades":   0,
                "tickers":        [],
            }
        grouped[sid]["tickers"].append({
            "ticker":         r["ticker"],
            "last_signal":    r["signal_type"],
            "last_signal_at": r["signal_at"].isoformat() if r["signal_at"] else None,
            "pnl":            0.0,   # TODO: calcular FIFO cuando haya trades reales
            "win_rate":       float(r["win_rate"]) if r["win_rate"] is not None else 0.0,
            "sharpe_ratio":   float(r["sharpe_ratio"]) if r["sharpe_ratio"] is not None else 0.0,
        })
        if r["performance_decay"]:
            grouped[sid]["decay_status"] = True
        if r["total_trades"]:
            grouped[sid]["total_trades"] += int(r["total_trades"])

    return list(grouped.values())


@app.get("/api/trades")
async def api_trades(
    limit:    int           = Query(50, ge=1, le=500),
    sentinel: Optional[str] = Query(None, description="sentinel_id (UUID)"),
    ticker:   Optional[str] = Query(None),
):
    where     = ["t.owner_id = $1"]
    params: list = [_owner_id]

    if sentinel:
        try:
            sid = UUID(sentinel)
        except ValueError:
            raise HTTPException(status_code=400, detail="sentinel debe ser UUID válido")
        params.append(sid)
        where.append(f"t.sentinel_id = ${len(params)}")

    if ticker:
        params.append(ticker.upper())
        where.append(f"t.ticker = ${len(params)}")

    params.append(limit)
    sql = f"""
        SELECT
            t.trade_id,
            s.name AS sentinel_name,
            t.ticker,
            t.side,
            t.qty,
            t.filled_price,
            t.slippage,
            t.status,
            t.created_at
        FROM trades t
        JOIN sentinels s ON t.sentinel_id = s.sentinel_id
        WHERE {' AND '.join(where)}
        ORDER BY t.created_at DESC
        LIMIT ${len(params)}
    """
    try:
        async with historian.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_row(r) for r in rows]
    except Exception as e:
        _http_500("/api/trades", e)


@app.get("/api/macro")
async def api_macro():
    sql = """
        SELECT risk_score, vix_level, spy_change_15min,
               circuit_breaker_triggered, created_at
        FROM macro_events
        ORDER BY created_at DESC
        LIMIT 20
    """
    try:
        async with historian.pool.acquire() as conn:
            rows = await conn.fetch(sql)
    except Exception as e:
        _http_500("/api/macro", e)

    events = [_row(r) for r in rows]
    latest = events[0] if events else {}
    return {
        "current_risk_score": float(latest.get("risk_score") or 0.0),
        "circuit_breaker":    bool(latest.get("circuit_breaker_triggered") or False),
        "parking_brake":      _is_parking_brake_active(),
        "recent_events":      events,
    }


@app.get("/api/performance")
async def api_performance():
    sql = """
        SELECT
            s.name AS sentinel_name,
            ps.ticker,
            ps.win_rate,
            ps.sharpe_ratio,
            ps.total_trades,
            ps.performance_decay,
            ps.calculated_at
        FROM performance_scores ps
        JOIN sentinels s ON ps.sentinel_id = s.sentinel_id
        WHERE s.owner_id = $1
        ORDER BY ps.sharpe_ratio DESC NULLS LAST
    """
    try:
        async with historian.pool.acquire() as conn:
            rows = await conn.fetch(sql, _owner_id)
        return [_row(r) for r in rows]
    except Exception as e:
        _http_500("/api/performance", e)


@app.get("/api/report")
async def api_report(range: str = Query("today", regex="^(today|last_week|last_month|all)$")):
    """
    Reporte completo. Combina datos reales (cuando existen) con placeholders
    en secciones que aún no están instrumentadas (correlation_guard, dispatcher).
    """
    since = _range_to_since(range)

    try:
        async with historian.pool.acquire() as conn:
            # Trades en rango
            if since:
                trades = await conn.fetch(
                    """
                    SELECT t.trade_id, s.name AS sentinel_name, t.ticker, t.side,
                           t.qty, t.filled_price, t.slippage, t.status, t.created_at
                    FROM trades t
                    JOIN sentinels s ON t.sentinel_id = s.sentinel_id
                    WHERE t.owner_id = $1 AND t.created_at >= $2
                    ORDER BY t.created_at DESC
                    """,
                    _owner_id, since,
                )
            else:
                trades = await conn.fetch(
                    """
                    SELECT t.trade_id, s.name AS sentinel_name, t.ticker, t.side,
                           t.qty, t.filled_price, t.slippage, t.status, t.created_at
                    FROM trades t
                    JOIN sentinels s ON t.sentinel_id = s.sentinel_id
                    WHERE t.owner_id = $1
                    ORDER BY t.created_at DESC
                    """,
                    _owner_id,
                )

            # Macro events count
            if since:
                macro_count = await conn.fetchval(
                    "SELECT COUNT(*)::int FROM macro_events WHERE created_at >= $1",
                    since,
                )
            else:
                macro_count = await conn.fetchval(
                    "SELECT COUNT(*)::int FROM macro_events"
                )

            # Macro events recientes
            macro_recent = await conn.fetch(
                """
                SELECT risk_score, vix_level, spy_change_15min,
                       circuit_breaker_triggered, created_at
                FROM macro_events
                ORDER BY created_at DESC
                LIMIT 20
                """
            )
    except Exception as e:
        _http_500("/api/report", e)

    # Strategy performance: reusar la lógica de /api/sentinels
    strategy_performance = await api_sentinels()

    return {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "range":        range,
            "owner":        OWNER_USERNAME,
            "system":       "Sentinel v0.5",
        },
        "system_health": {
            "uptime_seconds":    None,   # TODO: trackear desde startup
            "total_trades":      len(trades),
            "macro_events":      int(macro_count or 0),
            "errors_last_hour":  None,   # TODO: hook al logging handler
        },
        "strategy_performance": strategy_performance,
        "macro_context": {
            "events_total":     int(macro_count or 0),
            "recent_events":    [_row(r) for r in macro_recent],
            "parking_brake":    _is_parking_brake_active(),
        },
        "correlation_guard": {
            "threshold":              0.75,
            "rolling_window_candles": 60,
            "evaluations_in_range":   None,    # TODO: persistir evaluaciones
        },
        "dispatcher": {
            "kelly_fraction":         0.5,
            "max_capital_per_sentinel_pct": 25.0,
            "min_capital_per_sentinel_pct": 5.0,
            "regime":                 "NEUTRAL",
            "kill_switch_active":     False,   # TODO: leer de estado runtime
        },
        "trades": [_row(t) for t in trades],
    }


# =============================================================================
# KILL SWITCH — endpoints de control remoto (#H-7)
# api.py y main.py corren en procesos separados; system_state actúa como
# canal IPC. main.py pollea cada 5s tres flags:
#   - halt_requested: la API setea "true" cuando el admin pide halt.
#                     El poller lo consume, dispara activate_kill_switch
#                     y resetea a "false".
#   - system_halted:  el poller lo setea "true" después de halt y "false"
#                     después de resume. Es la fuente de verdad del estado
#                     visible para la API y el dashboard (toggle del botón).
#   - resume_requested: la API setea "true" cuando el admin pide resume.
#                       El poller lo consume y dispara deactivate_kill_switch.
# Auth: GET state requiere sesión; POST halt/resume requieren role=ADMIN.
# =============================================================================

@app.get("/api/system/state")
async def api_system_state():
    try:
        halt_flag   = await historian.get_system_flag("halt_requested")
        halted_flag = await historian.get_system_flag("system_halted")
        return {
            "halt_requested": halt_flag   == "true",
            "system_halted":  halted_flag == "true",
        }
    except Exception as e:
        _http_500("/api/system/state", e)


@app.post("/api/system/halt")
async def api_system_halt():
    try:
        halted = await historian.get_system_flag("system_halted")
        if halted == "true":
            return {"status": "already_halted"}
        await historian.set_system_flag("halt_requested", "true")
        logger.warning("HALT solicitado vía API")
        return {
            "status":  "halt_requested",
            "message": "Kill switch se activará en máximo 5 segundos",
        }
    except Exception as e:
        _http_500("/api/system/halt", e)


@app.post("/api/system/resume")
async def api_system_resume():
    try:
        halted = await historian.get_system_flag("system_halted")
        if halted != "true":
            return {"status": "already_running"}
        await historian.set_system_flag("resume_requested", "true")
        logger.warning("RESUME solicitado vía API")
        return {
            "status":  "resume_requested",
            "message": "Sistema se reactivará en máximo 5 segundos",
        }
    except Exception as e:
        _http_500("/api/system/resume", e)


# =============================================================================
# SSE — push periódico de actualización al dashboard
# =============================================================================

_SSE_INTERVAL_SECONDS = 900   # 15 minutos


async def _build_sse_payload() -> dict:
    """Snapshot compacto: status + sentinels resumido + últimos trades."""
    status   = await api_status()
    trades   = await api_trades(limit=10, sentinel=None, ticker=None)

    async with historian.pool.acquire() as conn:
        sentinels = await conn.fetch(
            """
            SELECT s.sentinel_id, s.name, s.strategy_type,
                   array_agg(st.ticker ORDER BY st.ticker)
                       FILTER (WHERE st.is_active = TRUE) AS tickers
            FROM sentinels s
            LEFT JOIN sentinel_tickers st ON st.sentinel_id = s.sentinel_id
            WHERE s.owner_id = $1 AND s.is_active = TRUE
            GROUP BY s.sentinel_id, s.name, s.strategy_type
            ORDER BY s.name
            """,
            _owner_id,
        )

    return {
        "ts":        datetime.utcnow().isoformat() + "Z",
        "status":    status,
        "sentinels": [_row(s) for s in sentinels],
        "trades":    trades,
    }


@app.get("/api/sse")
async def api_sse():
    async def event_generator():
        # Primer payload inmediato — sin esperar 15min para la primera actualización
        try:
            initial = await _build_sse_payload()
            yield {"event": "update", "data": json.dumps(initial)}
        except Exception as e:
            logger.error(f"SSE initial payload failed: {e}")

        while True:
            await asyncio.sleep(_SSE_INTERVAL_SECONDS)
            try:
                payload = await _build_sse_payload()
                yield {"event": "update", "data": json.dumps(payload)}
            except Exception as e:
                logger.error(f"SSE payload failed: {e}")
                # No matar el stream — esperar al próximo ciclo
                yield {"event": "error", "data": json.dumps({"error": str(e)})}

    # ping=15s mantiene la conexión viva entre updates de 15min
    return EventSourceResponse(event_generator(), ping=15)


# =============================================================================
# DASHBOARD ESTÁTICO
# El mount en "/" debe ser el ÚLTIMO add — los routes /api/* tienen
# precedencia porque se registran antes.
# =============================================================================

if DASHBOARD_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(DASHBOARD_DIR), html=True),
        name="dashboard",
    )
    logger.info(f"Dashboard servido desde {DASHBOARD_DIR}")
else:
    logger.warning(f"Dashboard no encontrado en {DASHBOARD_DIR} — solo API disponible.")

    @app.get("/")
    async def root():
        return JSONResponse({
            "service": "SENTINEL v0.5 API",
            "dashboard": "not_found",
            "expected_path": str(DASHBOARD_DIR),
        })


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8080, reload=False)
