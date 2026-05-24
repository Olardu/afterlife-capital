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
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import os

# Capturado al import. Sirve para system_health.uptime_hours del /api/report.
APP_START_TIME = time.time()

import uvicorn
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.sessions import SessionMiddleware

from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    DAILY_REPORT_ENABLED,
    DATABASE_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    LOG_LEVEL,
    NEWS_API_KEY,
    OAUTH_REDIRECT_URI,
    OWNER_USERNAME,
    PARKING_BRAKE_TIME,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
    TIMEZONE,
)

# Fecha inicio del periodo de observacion (trades antes de esto son contaminacion)
OBSERVATION_START = datetime(2026, 4, 28)
from email_service import send_daily_report, send_removal_email, send_welcome_email
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

    # Arrancar scheduler del reporte diario (#DAILY-REPORT)
    # Desactivado el 2026-05-23 vía DAILY_REPORT_ENABLED=false (cierre anticipado
    # del período de observación, HANDOFF #2). Reactivar para el 2do período (junio).
    global _daily_report_task
    if DAILY_REPORT_ENABLED:
        _daily_report_task = asyncio.create_task(_daily_report_loop())
        logger.info("Daily report scheduler arrancado.")
    else:
        logger.info(
            "Daily report scheduler NO arrancado (DAILY_REPORT_ENABLED=false). "
            "Reactivar poniendo DAILY_REPORT_ENABLED=true en .env."
        )

    yield

    # Cancelar scheduler al cerrar
    if _daily_report_task and not _daily_report_task.done():
        _daily_report_task.cancel()
        try:
            await _daily_report_task
        except asyncio.CancelledError:
            pass
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
    # Info de mercado pública (#FIX-011) — el indicador del header lo
    # consume antes de que el usuario inicie sesión también.
    "/api/market-status",
}
_PUBLIC_PREFIXES = ("/assets/",)

# Endpoints/paths que requieren role=ADMIN.
# - _ADMIN_PATHS: paths exactos POST-only (kill switch).
# - _ADMIN_PREFIXES: prefijos donde TODO método (GET/POST/DELETE) requiere ADMIN
#                   (panel admin de usuarios).
_ADMIN_PATHS    = {"/api/system/halt", "/api/system/resume"}
_ADMIN_PREFIXES = ("/api/admin/",)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Gate de autenticación + autorización por rutas (#H-1).

    - /auth/*, assets, favicon: público.
    - / (dashboard): redirect 302 a /auth/login si no hay sesión.
    - /admin (panel admin HTML): redirect a login sin sesión, 403 si VIEWER.
    - /api/*: 401 si no hay sesión.
        · /api/system/{halt,resume} POST: 403 si role != ADMIN.
        · /api/admin/* (cualquier método): 403 si role != ADMIN.
    - Cualquier otra ruta: pasa (StaticFiles atrás del mount root maneja errores).
    """
    path   = request.url.path
    method = request.method

    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    user = _get_session_user(request)

    if path == "/admin":
        if user is None:
            return RedirectResponse(url="/auth/login", status_code=302)
        if user.get("role") != "ADMIN":
            # VIEWER no debería siquiera saber que /admin existe — silent
            # redirect al dashboard en lugar de 403 explícito.
            return RedirectResponse(url="/", status_code=302)
        return await call_next(request)

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
        if any(path.startswith(p) for p in _ADMIN_PREFIXES) and user.get("role") != "ADMIN":
            return JSONResponse(
                {"error":   "forbidden",
                 "message": "Solo administradores pueden gestionar usuarios"},
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

# =============================================================================
# Índice de secciones (§) — buscables con "§ N":
#   § 1 — Imports y configuración (arriba de este bloque)
#   § 2 — Auth Google OAuth (/auth/*)
#   § 3 — Endpoints core (status, sentinels, trades, macro, market-status, performance)
#   § 4 — Cuenta Alpaca (equity, capital, portfolio-history)
#   § 5 — Reporte (/api/report, daily, send-now)
#   § 6 — Control operativo / Kill switch (system/state, halt, resume)
#   § 7 — Administración (panel, users, api-keys, rotations, candidates)
#   § 8 — SSE streaming + frontend estático
# =============================================================================

# ═══════════════════════════ § 2 — Auth Google OAuth ═══════════════════════════
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

# ═══════════════════════════ § 3 — Endpoints core ═══════════════════════════
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
        # #ME-3: desglose de señales de hoy por destino (filled/cancelled/
        # pending/no_trade). Adquiere su propia conexión → fuera del with previo.
        signals_breakdown = await historian.get_signals_breakdown_today(_owner_id)
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
            # #ME-3 — tracking de trades fallidos por categoría (señales de hoy).
            "signals_breakdown_today": signals_breakdown,
            # #TD-6 follow-up — visible si NEWS_API_KEY falta (The Ear queda ciego
            # a noticias). True = sin key configurada.
            "the_ear_news_disabled":   not bool(NEWS_API_KEY),
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
            "total_trades":   int(r["total_trades"]) if r["total_trades"] is not None else 0,
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
    where     = ["t.owner_id = $1", "t.created_at >= $2"]
    params: list = [_owner_id, OBSERVATION_START]

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


@app.get("/api/market-status")
async def api_market_status():
    """
    Estado del mercado NYSE + tiempo hasta próximo cambio (#FIX-011).
    Pública (no requiere auth — info de mercado, no propietaria).
    Retorna: is_open, status (OPEN|CLOSED|PRE_MARKET|AFTER_HOURS),
    next_open, next_close, current_time_et.
    """
    try:
        from market_clock import get_market_status
        return get_market_status()
    except Exception as e:
        _http_500("/api/market-status", e)


@app.get("/api/macro_events")
async def api_macro_events(limit: int = Query(10, ge=1, le=100)):
    """
    Últimos N macro_events con titulares matched (#FIX-010). Sirve al
    dashboard para reemplazar el placeholder genérico
    "Macro update — risk X · VIX Y · SPY Z" por los titulares específicos
    que movieron las decisiones (FIX-007 los persiste, este endpoint los
    expone). Requiere sesión válida (auth_middleware) — sin restricción
    de role (VIEWER + ADMIN).

    Response: list de eventos con news_titles ya parseados (list[dict]).
    """
    try:
        events = await historian.get_recent_macro_events(limit=limit)
    except Exception as e:
        _http_500("/api/macro_events", e)

    parking = _is_parking_brake_active()
    return [
        {
            "event_id":        str(e["event_id"]) if e.get("event_id") else None,
            "created_at":      e["created_at"].isoformat() if e.get("created_at") else None,
            "risk_score":      float(e["risk_score"]) if e.get("risk_score") is not None else 0.0,
            "vix_change":      float(e["vix_level"]) if e.get("vix_level") is not None else None,
            "spy_change":      float(e["spy_change_15min"]) if e.get("spy_change_15min") is not None else None,
            "regime":          "NEUTRAL",   # S-10 desactivado — régimen fijo
            "circuit_breaker": bool(e.get("circuit_breaker_triggered") or False),
            "parking_brake":   parking,     # estado actual; aplicado a todos los rows del set (no se persiste por evento)
            "news_titles":     e.get("news_titles") or [],
        }
        for e in events
    ]


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


# ═══════════════════════════ § 4 — Cuenta Alpaca ═══════════════════════════
@app.get("/api/account/equity")
async def api_account_equity():
    """
    Endpoint read-only que consulta la cuenta Alpaca para obtener
    balance, equity, posiciones abiertas y PnL no realizado.
    Alimenta los KPIs del dashboard (Frente B).
    """
    try:
        from alpaca.trading.client import TradingClient

        client  = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = await asyncio.to_thread(client.get_account)
        positions = await asyncio.to_thread(client.get_all_positions)

        # Calcular PnL no realizado total
        unrealized_pl = sum(
            float(p.unrealized_pl) for p in positions if p.unrealized_pl
        )

        return {
            "equity":            float(account.equity),
            "cash":              float(account.cash),
            "portfolio_value":   float(account.portfolio_value) if account.portfolio_value else float(account.equity),
            "buying_power":      float(account.buying_power),
            "positions_count":   len(positions),
            "unrealized_pl":     round(unrealized_pl, 2),
            "positions": [
                {
                    "ticker":        p.symbol,
                    "qty":           float(p.qty),
                    "market_value":  float(p.market_value) if p.market_value else 0,
                    "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else 0,
                    "avg_entry":     float(p.avg_entry_price) if p.avg_entry_price else 0,
                    "current_price": float(p.current_price) if p.current_price else 0,
                }
                for p in positions
            ],
        }
    except Exception as e:
        logger.error(f"/api/account/equity error: {e}")
        _http_500("/api/account/equity", e)



@app.get("/api/account/capital")
async def api_account_capital():
    """
    Endpoint read-only con responsabilidad única: métricas de capital total vs
    capital efectivamente invertido y rentabilidad del día sobre el capital
    deployado (no sobre el equity total, que diluye con el cash dormido).

    Cumple el formato estándar { data, meta } definido en BUENAS_PRACTICAS_V2.md
    sección 6.2. Introducido como Excepción 1.2 del período de observación
    (2026-05-13) — cosmética/observabilidad sin tocar lógica del bot.
    """
    try:
        from alpaca.trading.client import TradingClient

        client  = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = await asyncio.to_thread(client.get_account)

        equity      = float(account.equity)
        last_equity = float(account.last_equity) if account.last_equity else equity
        long_mv     = float(account.long_market_value) if account.long_market_value else 0.0
        short_mv    = float(account.short_market_value) if account.short_market_value else 0.0
        invested    = abs(long_mv) + abs(short_mv)
        day_pnl     = equity - last_equity

        invested_pct_of_equity   = (invested / equity * 100) if equity > 0 else 0.0
        day_pnl_pct_of_equity    = (day_pnl / last_equity * 100) if last_equity > 0 else 0.0
        day_pnl_pct_of_invested  = (day_pnl / invested * 100) if invested > 0 else 0.0

        return {
            "data": {
                "equity":                  round(equity, 2),
                "last_equity":             round(last_equity, 2),
                "long_market_value":       round(long_mv, 2),
                "short_market_value":      round(short_mv, 2),
                "invested":                round(invested, 2),
                "invested_pct_of_equity":  round(invested_pct_of_equity, 2),
                "day_pnl":                 round(day_pnl, 2),
                "day_pnl_pct_of_equity":   round(day_pnl_pct_of_equity, 4),
                "day_pnl_pct_of_invested": round(day_pnl_pct_of_invested, 4),
            },
            "meta": {
                "source":      "alpaca",
                "as_of":       datetime.now(ZoneInfo("UTC")).isoformat(),
                "definitions": {
                    "invested":                "abs(long_market_value) + abs(short_market_value) — capital efectivamente expuesto al mercado",
                    "day_pnl_pct_of_invested": "rentabilidad del día sobre el capital REALMENTE invertido (no sobre el equity total)",
                },
            },
        }
    except Exception as e:
        logger.error(f"/api/account/capital error: {e}")
        _http_500("/api/account/capital", e)


@app.get("/api/account/portfolio-history")
async def api_portfolio_history(period: str = Query("1D", regex="^(4H|8H|1D|1W|1M|1A)$")):
    """
    Endpoint read-only que consulta Alpaca portfolio history via REST API.
    Alimenta la curva de equity del dashboard con datos temporales reales.
    No modifica datos ni lógica del bot — pura observabilidad.

    Períodos: 4H, 8H, 1D, 1W, 1M, 1A
    Granularidad automática según período (Alpaca default).
    """
    import httpx

    try:
        # Mapear períodos cortos a parámetros Alpaca REST API
        period_map = {
            "4H":  {"period": "1D",  "timeframe": "5Min"},
            "8H":  {"period": "1D",  "timeframe": "15Min"},
            "1D":  {"period": "1D",  "timeframe": "5Min"},
            "1W":  {"period": "1W",  "timeframe": "1H"},
            "1M":  {"period": "1M",  "timeframe": "1D"},
            "1A":  {"period": "1A",  "timeframe": "1D"},
        }
        params = period_map.get(period, {"period": "1D", "timeframe": "5Min"})

        # Alpaca Paper Trading REST API
        base_url = "https://paper-api.alpaca.markets"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        }
        query_params = {
            "period": params["period"],
            "timeframe": params["timeframe"],
            "extended_hours": "true",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base_url}/v2/account/portfolio/history",
                headers=headers,
                params=query_params,
            )
            resp.raise_for_status()
            data = resp.json()

        timestamps = data.get("timestamp", [])
        equity_vals = data.get("equity", [])
        pnl_vals = data.get("profit_loss", [])
        pnl_pct_vals = data.get("profit_loss_pct", [])

        # Filtrar nulls (Alpaca puede devolver null en barras sin actividad)
        clean = [
            (t, e, p, pp)
            for t, e, p, pp in zip(timestamps, equity_vals, pnl_vals, pnl_pct_vals)
            if e is not None
        ]
        if clean:
            timestamps, equity_vals, pnl_vals, pnl_pct_vals = map(list, zip(*clean))
        else:
            timestamps, equity_vals, pnl_vals, pnl_pct_vals = [], [], [], []

        # --- Filtro de valores stale (paper trading artifact) ---
        # Si un valor de equity se repite idéntico 3+ barras seguidas en
        # timeframes sub-diarios, es un dato stale de Alpaca paper (no hay
        # repricing real fuera de mercado). Interpolamos linealmente entre
        # el último valor real antes del bloque y el primero después.
        if params["timeframe"] != "1D" and len(equity_vals) > 4:
            i = 0
            while i < len(equity_vals):
                # Buscar inicio de bloque stale
                j = i + 1
                while j < len(equity_vals) and equity_vals[j] == equity_vals[i]:
                    j += 1
                run_len = j - i
                if run_len >= 3:
                    # Bloque stale detectado: interpolar
                    before = equity_vals[i - 1] if i > 0 else equity_vals[i]
                    after  = equity_vals[j] if j < len(equity_vals) else equity_vals[j - 1]
                    for k in range(i, j):
                        t = (k - i + 1) / (run_len + 1)
                        equity_vals[k] = round(before + (after - before) * t, 2)
                    i = j
                else:
                    i += 1

        # Para 4H/8H: recortar al número de barras correspondiente
        if period == "4H":
            n = 48   # 4h × 12 barras/hora (5min)
            timestamps = timestamps[-n:]
            equity_vals = equity_vals[-n:]
            pnl_vals = pnl_vals[-n:]
            pnl_pct_vals = pnl_pct_vals[-n:]
        elif period == "8H":
            n = 32   # 8h × 4 barras/hora (15min)
            timestamps = timestamps[-n:]
            equity_vals = equity_vals[-n:]
            pnl_vals = pnl_vals[-n:]
            pnl_pct_vals = pnl_pct_vals[-n:]

        # base_value: primer equity del rango (punto de equilibrio)
        base_value = equity_vals[0] if equity_vals else 100000

        return {
            "timestamps":   timestamps,
            "equity":       equity_vals,
            "profit_loss":  pnl_vals,
            "profit_loss_pct": pnl_pct_vals,
            "base_value":   base_value,
            "period":       period,
        }
    except Exception as e:
        logger.error(f"/api/account/portfolio-history error: {e}")
        _http_500("/api/account/portfolio-history", e)


# ═══════════════════════════ § 5 — Reporte ═══════════════════════════
@app.get("/api/report")
async def api_report(range: str = Query("today", regex="^(today|last_week|last_month|all)$")):
    """
    Reporte JSON exhaustivo (#FIX-006).

    Todos los campos derivan de queries reales al Historian. Para cada campo
    cuya tabla/columna aún no existe en el modelo de datos se devuelve null
    (o {}) con un comentario `TODO: persistir X` al lado en código —
    explícitamente NO inventamos datos de relleno.

    El generador cliente-side `buildReport()` en `dashboard/sentinel-app.js`
    sigue produciendo datos demo y no se puede modificar (handoff Design,
    fuera del scope de este branch). Este endpoint es la fuente de verdad
    para integraciones que consumen `/api/report` directamente.
    """
    since = _range_to_since(range)

    try:
        async with historian.pool.acquire() as conn:
            # ============ TRADES en rango ============
            if since:
                trades_rows = await conn.fetch(
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
                trades_rows = await conn.fetch(
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

            # ============ MACRO ============
            macro_filter = "WHERE created_at >= $1" if since else ""
            macro_args   = [since] if since else []

            macro_count = await conn.fetchval(
                f"SELECT COUNT(*)::int FROM macro_events {macro_filter}",
                *macro_args,
            )
            risk_score_avg = await conn.fetchval(
                f"SELECT AVG(risk_score)::float FROM macro_events {macro_filter}",
                *macro_args,
            )
            circuit_breaker_activations = await conn.fetchval(
                f"""
                SELECT COUNT(*)::int FROM macro_events
                {macro_filter}{' AND' if since else 'WHERE'} circuit_breaker_triggered = TRUE
                """,
                *macro_args,
            )

            # macro_events.news_titles (FIX 3) puede no existir en la DB hasta
            # el próximo restart del bot/API que aplica el DDL idempotente.
            # Detectamos la columna antes de seleccionarla para no romper.
            news_titles_col_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'macro_events' AND column_name = 'news_titles'
                )
                """
            )
            if news_titles_col_exists:
                news_filter = "WHERE created_at >= $1" if since else ""
                news_rows = await conn.fetch(
                    f"""
                    SELECT created_at, risk_score, circuit_breaker_triggered, news_titles
                    FROM macro_events
                    {news_filter}
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    *macro_args,
                )
            else:
                news_rows = []

            # ============ STRATEGY PERFORMANCE — agregados por sentinel ============
            # Combina sentinels + tickers + performance_scores (decay/sharpe/win_rate)
            # con slippage_avg calculado desde trades en rango (para reflejar el
            # comportamiento operativo del período pedido).
            strat_rows = await conn.fetch(
                """
                SELECT
                    s.sentinel_id,
                    s.name,
                    s.strategy_type,
                    s.capital_allocation,
                    COALESCE(
                        array_agg(DISTINCT st.ticker ORDER BY st.ticker)
                            FILTER (WHERE st.ticker IS NOT NULL AND st.is_active = TRUE),
                        ARRAY[]::VARCHAR[]
                    ) AS tickers,
                    COALESCE(SUM(ps.total_trades), 0)::int       AS total_trades_score,
                    AVG(ps.win_rate)::float                       AS win_rate_avg,
                    AVG(ps.sharpe_ratio)::float                   AS sharpe_avg,
                    BOOL_OR(ps.performance_decay)                 AS decay_status
                FROM sentinels s
                LEFT JOIN sentinel_tickers st
                    ON st.sentinel_id = s.sentinel_id
                LEFT JOIN performance_scores ps
                    ON ps.sentinel_id = s.sentinel_id
                WHERE s.owner_id = $1 AND s.is_active = TRUE
                GROUP BY s.sentinel_id, s.name, s.strategy_type, s.capital_allocation
                ORDER BY s.name
                """,
                _owner_id,
            )

            # slippage_avg + total_trades reales del período por sentinel
            if since:
                trade_aggs = await conn.fetch(
                    """
                    SELECT sentinel_id,
                           AVG(slippage)::float AS slippage_avg,
                           COUNT(*)::int       AS trades_in_range
                    FROM trades
                    WHERE owner_id = $1 AND created_at >= $2
                    GROUP BY sentinel_id
                    """,
                    _owner_id, since,
                )
            else:
                trade_aggs = await conn.fetch(
                    """
                    SELECT sentinel_id,
                           AVG(slippage)::float AS slippage_avg,
                           COUNT(*)::int       AS trades_in_range
                    FROM trades
                    WHERE owner_id = $1
                    GROUP BY sentinel_id
                    """,
                    _owner_id,
                )
            slip_by_sid = {
                str(r["sentinel_id"]): {
                    "slippage_avg":    r["slippage_avg"],
                    "trades_in_range": r["trades_in_range"],
                }
                for r in trade_aggs
            }

            # ============ DISPATCHER — signals recibidos en rango ============
            if since:
                signals_received = await conn.fetchval(
                    "SELECT COUNT(*)::int FROM signals WHERE owner_id = $1 AND created_at >= $2",
                    _owner_id, since,
                )
            else:
                signals_received = await conn.fetchval(
                    "SELECT COUNT(*)::int FROM signals WHERE owner_id = $1",
                    _owner_id,
                )

            # ============ KILL SWITCH actual ============
            kill_switch_flag = await conn.fetchval(
                "SELECT value FROM system_state WHERE key = 'system_halted'"
            )
    except Exception as e:
        _http_500("/api/report", e)

    strategy_performance = []
    for r in strat_rows:
        sid = str(r["sentinel_id"])
        agg = slip_by_sid.get(sid, {})
        strategy_performance.append({
            "sentinel":       r["name"],
            "strategy":       r["strategy_type"],
            "tickers":        list(r["tickers"]) if r["tickers"] else [],
            "win_rate":       float(r["win_rate_avg"]) if r["win_rate_avg"] is not None else 0.0,
            "sharpe_ratio":   float(r["sharpe_avg"])   if r["sharpe_avg"]   is not None else 0.0,
            "total_trades":   int(r["total_trades_score"] or 0),
            "trades_in_range": int(agg.get("trades_in_range") or 0),
            "slippage_avg":   float(agg["slippage_avg"]) if agg.get("slippage_avg") is not None else None,
            "decay_status":   bool(r["decay_status"]) if r["decay_status"] is not None else False,
            "allocation_pct": float(r["capital_allocation"]),
        })

    news_that_moved_decisions = []
    for r in news_rows:
        raw_titles = r["news_titles"]
        # asyncpg devuelve JSONB como str (sin codec); parseamos defensivo
        if isinstance(raw_titles, str):
            try:
                titles = json.loads(raw_titles)
            except Exception:
                titles = []
        elif isinstance(raw_titles, list):
            titles = raw_titles
        else:
            titles = []
        news_that_moved_decisions.append({
            "timestamp":  r["created_at"].isoformat() if r["created_at"] else None,
            "risk_score": float(r["risk_score"]) if r["risk_score"] is not None else 0.0,
            "impact":     "circuit_breaker" if r["circuit_breaker_triggered"] else (
                          "risk_elevated"   if (r["risk_score"] or 0) > 0.5 else "neutral"),
            "titles":     titles,
        })

    uptime_hours = (time.time() - APP_START_TIME) / 3600.0

    return {
        "metadata": {
            "generated_at":   datetime.utcnow().isoformat() + "Z",
            "range":          range,
            "owner":          OWNER_USERNAME,
            "system_version": "SENTINEL v0.5",
        },
        "system_health": {
            "uptime_hours":                round(uptime_hours, 2),
            "total_trades":                len(trades_rows),
            "macro_events":                int(macro_count or 0),
            "circuit_breaker_activations": int(circuit_breaker_activations or 0),
            # TODO: persistir errores por módulo (tabla logs o handler dedicado)
            "errors_by_module":            {},
            # TODO: trackear reconnects de Alpaca/postgres/NewsAPI a métrica
            "reconnections":               {},
            # TODO: persistir activaciones de parking brake (hoy solo se calcula
            # en runtime con _is_parking_brake_active(), no se guarda en DB)
            "parking_brake_activations":   None,
        },
        "strategy_performance": strategy_performance,
        "macro_context": {
            "events_total":              int(macro_count or 0),
            "risk_score_avg":            float(risk_score_avg) if risk_score_avg is not None else 0.0,
            # TODO: persistir régimen del classifier (S-10) por evento macro
            "regime_distribution":       None,
            "parking_brake_now":         _is_parking_brake_active(),
            "news_that_moved_decisions": news_that_moved_decisions,
        },
        "correlation_guard": {
            "threshold":              0.75,
            "rolling_window_candles": 60,
            # TODO: persistir signals.correlation_action y signals.correlation_used
            # para poder reportar reduced/discarded/avg_correlation reales
            "signals_reduced":        None,
            "signals_discarded":      None,
            "avg_correlation":        None,
        },
        "dispatcher": {
            "kelly_fraction":               0.5,
            "max_capital_per_sentinel_pct": 25.0,
            "min_capital_per_sentinel_pct": 5.0,
            "regime":                       "NEUTRAL",
            "kill_switch_active":           (kill_switch_flag == "true"),
            "signals_received":             int(signals_received or 0),
            # TODO: persistir signals.approved + signals.rejection_reason
            "signals_approved":             None,
            "signals_rejected":             None,
            "rejection_reasons":            None,
        },
        "trades": [_row(t) for t in trades_rows],
    }


# =============================================================================
# DAILY REPORT — endpoint + data collector + scheduler (#DAILY-REPORT)
# Consolida todos los datos del día en un solo dict que alimenta:
#   1. GET /api/report/daily — JSON para integraciones
#   2. send_daily_report()   — email al cierre del mercado (16:30 ET)
# Read-only: no modifica lógica del bot ni datos en DB.
# =============================================================================

OBSERVATION_END = datetime(2026, 5, 27)

async def collect_daily_report_data(
    conn, owner_id, report_date: Optional[date] = None
) -> dict:
    """
    Recopila todos los datos necesarios para el reporte diario.
    Si report_date es None, usa la fecha actual en ET.
    Retorna dict listo para _render_daily_report_html() y para JSON response.
    """
    tz_et = ZoneInfo("America/New_York")
    if report_date is None:
        report_date = datetime.now(tz=tz_et).date()

    day_start = datetime(report_date.year, report_date.month, report_date.day)
    day_end   = day_start + timedelta(days=1)

    # Trades del dia
    trades_rows = await conn.fetch(
        """
        SELECT t.trade_id, s.name AS sentinel_name, t.ticker, t.side,
               t.qty, t.filled_price, t.slippage, t.status, t.created_at
        FROM trades t
        JOIN sentinels s ON t.sentinel_id = s.sentinel_id
        WHERE t.owner_id = $1 AND t.created_at >= $2 AND t.created_at < $3
        ORDER BY t.created_at ASC
        """,
        owner_id, day_start, day_end,
    )

    filled    = [r for r in trades_rows if (r["status"] or "").upper() == "FILLED"]
    cancelled = [r for r in trades_rows if (r["status"] or "").upper() == "CANCELLED"]

    # P&L por sentinel — solo round trips completos (BUY+SELL mismo ticker mismo dia)
    from collections import defaultdict
    _st_trades = defaultdict(list)   # (sentinel, ticker) -> [(side, px*qty, timestamp)]
    for t in filled:
        key = (t["sentinel_name"], t["ticker"])
        px  = float(t["filled_price"] or 0)
        qty = float(t["qty"] or 0)
        _st_trades[key].append(((t["side"] or "").upper(), px * qty))

    pnl_by_sentinel: dict = {}
    for (sentinel, ticker), ops in _st_trades.items():
        buys  = [v for side, v in ops if side == "BUY"]
        sells = [v for side, v in ops if side == "SELL"]
        matched = min(len(buys), len(sells))
        if matched > 0:
            realized = sum(sells[:matched]) - sum(buys[:matched])
            pnl_by_sentinel.setdefault(sentinel, 0.0)
            pnl_by_sentinel[sentinel] += realized

    pnl_sentinel_list = sorted(
        [{"name": k, "pnl": round(v, 2)} for k, v in pnl_by_sentinel.items()],
        key=lambda x: x["pnl"],
        reverse=True,
    )

    # Equity y posiciones (Alpaca)
    equity = 0.0
    cash = 0.0
    last_equity = 0.0
    positions_list = []
    positions_count = 0
    unrealized_pl = 0.0

    try:
        from alpaca.trading.client import TradingClient
        client  = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = await asyncio.to_thread(client.get_account)
        positions = await asyncio.to_thread(client.get_all_positions)

        equity = float(account.equity)
        cash   = float(account.cash)
        last_equity = float(account.last_equity) if account.last_equity else equity
        positions_count = len(positions)
        unrealized_pl = sum(float(p.unrealized_pl or 0) for p in positions)

        positions_list = [
            {
                "ticker":        p.symbol,
                "qty":           float(p.qty),
                "market_value":  float(p.market_value or 0),
                "unrealized_pl": float(p.unrealized_pl or 0),
                "avg_entry":     float(p.avg_entry_price or 0),
                "current_price": float(p.current_price or 0),
            }
            for p in positions
        ]
    except Exception as e:
        logger.warning(f"Daily report: Alpaca data unavailable: {e}")

    realized_pl = sum(pnl_by_sentinel.values())
    # P&L diario real = equity actual - equity cierre dia anterior (Alpaca)
    total_pnl   = equity - last_equity if last_equity > 0 else (realized_pl + unrealized_pl)
    pnl_pct     = (total_pnl / last_equity * 100) if last_equity > 0 else 0.0

    # Macro events (The Ear)
    news_col_exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'macro_events' AND column_name = 'news_titles'
        )
        """
    )
    if news_col_exists:
        ear_rows = await conn.fetch(
            """
            SELECT created_at, risk_score, circuit_breaker_triggered, news_titles
            FROM macro_events
            WHERE created_at >= $1 AND created_at < $2
            ORDER BY created_at ASC
            """,
            day_start, day_end,
        )
    else:
        ear_rows = await conn.fetch(
            """
            SELECT created_at, risk_score, circuit_breaker_triggered
            FROM macro_events
            WHERE created_at >= $1 AND created_at < $2
            ORDER BY created_at ASC
            """,
            day_start, day_end,
        )

    ear_events = []
    latest_risk = 0.0
    for r in ear_rows:
        risk = float(r["risk_score"] or 0)
        latest_risk = risk
        titles = []
        if news_col_exists:
            raw = r.get("news_titles")
            if isinstance(raw, str):
                try:
                    titles = json.loads(raw)
                except Exception:
                    titles = []
            elif isinstance(raw, list):
                titles = raw
        ear_events.append({
            "timestamp":  r["created_at"],
            "risk_score": risk,
            "impact":     "circuit_breaker" if r["circuit_breaker_triggered"] else (
                          "risk_elevated" if risk > 0.5 else "neutral"),
            "titles":     titles,
        })

    # Rotaciones del dia
    rotations_rows = await conn.fetch(
        """
        SELECT rd.decision_id, s.name AS sentinel_name, rd.old_ticker, rd.new_ticker,
               rd.trigger_reason, rd.claude_confidence, rd.status
        FROM rotation_decisions rd
        JOIN sentinels s ON rd.sentinel_id = s.sentinel_id
        WHERE rd.triggered_at >= $1 AND rd.triggered_at < $2
              AND rd.status = 'executed'
        ORDER BY rd.triggered_at ASC
        """,
        day_start, day_end,
    )
    rotations = [dict(r) for r in rotations_rows]

    return {
        "date":             str(report_date),
        "equity":           round(equity, 2),
        "cash":             round(cash, 2),
        "pnl":              round(total_pnl, 2),
        "pnl_pct":          round(pnl_pct, 3),
        "positions_count":  positions_count,
        "filled_count":     len(filled),
        "cancelled_count":  len(cancelled),
        "pending_count":    len([r for r in trades_rows if (r["status"] or "").upper() == "PENDING_NEW"]),
        "risk_score":       round(latest_risk, 2),
        "trades":           [_row(t) for t in trades_rows],
        "pnl_by_sentinel":  pnl_sentinel_list,
        "positions":        positions_list,
        "ear_events":       ear_events,
        "rotations":        rotations,
    }


@app.get("/api/report/daily")
async def api_report_daily(
    dt: Optional[str] = Query(None, description="Fecha YYYY-MM-DD (default: hoy ET)")
):
    """
    Reporte diario consolidado (#DAILY-REPORT). Read-only.
    Alimenta el email de cierre de mercado y sirve como API para integraciones.
    """
    try:
        report_date = date.fromisoformat(dt) if dt else None
    except ValueError:
        raise HTTPException(400, f"Fecha invalida: {dt}. Usar formato YYYY-MM-DD.")

    try:
        async with historian.pool.acquire() as conn:
            data = await collect_daily_report_data(conn, _owner_id, report_date)
    except Exception as e:
        _http_500("/api/report/daily", e)

    return data


@app.post("/api/report/daily/send-now")
async def api_report_daily_send_now(
    dt: Optional[str] = Query(None, description="Fecha YYYY-MM-DD (default: hoy ET)")
):
    """
    Disparo manual del reporte diario por email.
    Envia a todos los usuarios activos. Util para pruebas o reenvios.
    """
    try:
        report_date = date.fromisoformat(dt) if dt else None
    except ValueError:
        raise HTTPException(400, f"Fecha invalida: {dt}. Usar formato YYYY-MM-DD.")

    try:
        async with historian.pool.acquire() as conn:
            data = await collect_daily_report_data(conn, _owner_id, report_date)
            users = await conn.fetch(
                "SELECT email FROM users WHERE email IS NOT NULL"
            )

        sent = 0
        failed = []
        for user in users:
            email = user["email"]
            if email:
                ok = await send_daily_report(to_email=email, data=data)
                if ok:
                    sent += 1
                else:
                    failed.append(email)

        logger.info(f"Daily report manual: enviado a {sent}/{len(users)} usuarios.")
        return {
            "status": "ok",
            "sent": sent,
            "total_users": len(users),
            "failed": failed,
            "report_date": data.get("report_date", "hoy"),
        }
    except Exception as e:
        _http_500("/api/report/daily/send-now", e)


# ---------------------------------------------------------------------------
# Scheduler: envio automatico del reporte diario a las 16:30 ET (L-V)
# ---------------------------------------------------------------------------

_daily_report_task: Optional[asyncio.Task] = None


async def _daily_report_loop():
    """
    Loop que espera hasta las 16:30 ET de lunes a viernes y dispara
    el envio del reporte diario a todos los usuarios registrados.
    """
    tz_et = ZoneInfo("America/New_York")
    TARGET_HOUR, TARGET_MIN = 16, 30

    while True:
        try:
            now = datetime.now(tz=tz_et)

            # Auto-stop: no enviar despues del periodo de observacion
            if now.date() > OBSERVATION_END.date():
                logger.info(
                    "Daily report scheduler: periodo de observacion finalizado "
                    f"({OBSERVATION_END.date()}). Scheduler detenido."
                )
                break

            target_today = now.replace(
                hour=TARGET_HOUR, minute=TARGET_MIN, second=0, microsecond=0
            )

            if now >= target_today or now.weekday() >= 5:
                days_ahead = 1
                candidate = now + timedelta(days=days_ahead)
                while candidate.weekday() >= 5:
                    days_ahead += 1
                    candidate = now + timedelta(days=days_ahead)
                target = candidate.replace(
                    hour=TARGET_HOUR, minute=TARGET_MIN, second=0, microsecond=0
                )
            else:
                target = target_today

            wait_seconds = (target - now).total_seconds()
            logger.info(
                f"Daily report scheduler: proximo envio en {wait_seconds/3600:.1f}h "
                f"({target.strftime('%Y-%m-%d %H:%M')} ET)"
            )
            await asyncio.sleep(wait_seconds)

            logger.info("Daily report scheduler: generando reporte...")
            try:
                async with historian.pool.acquire() as conn:
                    data = await collect_daily_report_data(conn, _owner_id)

                    users = await conn.fetch(
                        "SELECT email FROM users WHERE email IS NOT NULL"
                    )

                sent = 0
                for user in users:
                    email = user["email"]
                    if email:
                        ok = await send_daily_report(to_email=email, data=data)
                        if ok:
                            sent += 1
                logger.info(f"Daily report enviado a {sent}/{len(users)} usuarios.")
            except Exception as e:
                logger.error(f"Daily report scheduler error: {e}")

            await asyncio.sleep(61)

        except asyncio.CancelledError:
            logger.info("Daily report scheduler cancelado.")
            break
        except Exception as e:
            logger.error(f"Daily report loop error inesperado: {e}")
            await asyncio.sleep(300)


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

# ═══════════════════════════ § 6 — Control operativo / Kill switch ═══════════════════════════
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
# ADMIN — panel de gestión de usuarios
# Todos los paths bajo /api/admin/* y la ruta /admin requieren role=ADMIN
# (gating en auth_middleware). Los emails de welcome/removal se envían en
# background — fire-and-forget, no bloquea la respuesta si Resend falla.
# =============================================================================

# ═══════════════════════════ § 7 — Administración ═══════════════════════════
@app.get("/admin")
async def admin_page():
    admin_file = DASHBOARD_DIR / "admin.html"
    if not admin_file.is_file():
        raise HTTPException(status_code=404, detail="admin.html no encontrado")
    return FileResponse(str(admin_file))


@app.get("/api/admin/users")
async def admin_list_users():
    try:
        users = await historian.list_users()
        return [_to_json(u) for u in users]
    except Exception as e:
        _http_500("/api/admin/users GET", e)


@app.post("/api/admin/users")
async def admin_add_user(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    email = (payload.get("email") or "").strip().lower()
    role  = payload.get("role") or "VIEWER"
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="invalid_email")
    if role not in ("ADMIN", "VIEWER"):
        raise HTTPException(status_code=400, detail="invalid_role")

    try:
        user = await historian.add_user(email, role)
    except ValueError as e:
        if str(e) == "email_exists":
            return JSONResponse({"error": "email_exists"}, status_code=409)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _http_500("/api/admin/users POST", e)

    background_tasks.add_task(send_welcome_email, email, role)
    logger.info(f"Admin agregó usuario: {email} ({role})")
    return {"status": "created", "user": _to_json(user)}


@app.delete("/api/admin/users/{user_id}")
async def admin_remove_user(user_id: str, background_tasks: BackgroundTasks):
    try:
        try:
            uid = UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_user_id")

        async with historian.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT email FROM users WHERE user_id = $1", uid,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="not_found")
        email = row["email"]

        try:
            await historian.remove_user(uid)
        except ValueError as e:
            if str(e) == "cannot_remove_owner":
                return JSONResponse({"error": "cannot_remove_owner"}, status_code=403)
            raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        _http_500("/api/admin/users DELETE", e)

    background_tasks.add_task(send_removal_email, email)
    logger.info(f"Admin eliminó usuario: {email}")
    return {"status": "removed"}


# =============================================================================
# ADMIN — gestión de API keys (#FIX-008)
# Las keys se persisten encriptadas con Fernet (crypto_utils). El bot SIGUE
# leyendo desde .env en producción — esta tabla es gestión visual + futura
# migración. /reveal devuelve el plaintext y se loggea con WARN explícito.
# =============================================================================

def _serialize_api_key(entry: dict) -> dict:
    """asyncpg datetime → ISO. UUID ya viene como str desde Historian."""
    out = dict(entry)
    for k in ("last_rotated_at", "created_at", "updated_at"):
        if k in out and out[k] is not None and not isinstance(out[k], str):
            out[k] = out[k].isoformat()
    return out


@app.get("/api/admin/api-keys")
async def admin_list_api_keys():
    try:
        keys = await historian.list_api_keys()
        return [_serialize_api_key(k) for k in keys]
    except RuntimeError as e:
        # MASTER_ENCRYPTION_KEY no configurada — error de operación, no del cliente
        logger.error(f"crypto error en /api/admin/api-keys GET: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        _http_500("/api/admin/api-keys GET", e)


@app.post("/api/admin/api-keys")
async def admin_upsert_api_key(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    service_name = (payload.get("service_name") or "").strip()
    value        = payload.get("value") or ""
    description  = (payload.get("description") or "").strip()

    if not service_name:
        raise HTTPException(status_code=400, detail="service_name_required")
    if not value:
        raise HTTPException(status_code=400, detail="value_required")

    try:
        entry = await historian.upsert_api_key(service_name, value, description)
    except RuntimeError as e:
        logger.error(f"crypto error en /api/admin/api-keys POST: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _http_500("/api/admin/api-keys POST", e)

    user = _get_session_user(request) or {}
    logger.info(f"API key upsert por {user.get('email', '?')} | service={service_name}")
    return {"status": "saved", "key": _serialize_api_key(entry)}


@app.post("/api/admin/api-keys/{key_id}/reveal")
async def admin_reveal_api_key(key_id: str, request: Request):
    try:
        kid = UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_key_id")

    try:
        # Recuperamos service_name + plaintext en una sola lectura. Usamos
        # get_api_key_by_id para no exponer service_name como input al cliente.
        async with historian.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT service_name FROM api_keys WHERE key_id = $1", kid,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="not_found")

        plaintext = await historian.get_api_key_by_id(kid)
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"crypto error en reveal: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        _http_500("/api/admin/api-keys reveal", e)

    user = _get_session_user(request) or {}
    logger.warning(
        f"API key REVELADA: service={row['service_name']} | admin={user.get('email', '?')}"
    )
    return {"value": plaintext}


@app.delete("/api/admin/api-keys/{key_id}")
async def admin_delete_api_key(key_id: str, request: Request):
    try:
        kid = UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_key_id")

    try:
        async with historian.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT service_name FROM api_keys WHERE key_id = $1", kid,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="not_found")

        deleted = await historian.delete_api_key(kid)
    except HTTPException:
        raise
    except Exception as e:
        _http_500("/api/admin/api-keys DELETE", e)

    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")

    user = _get_session_user(request) or {}
    logger.info(f"API key eliminada: service={row['service_name']} | admin={user.get('email', '?')}")
    return {"status": "removed"}


# =============================================================================
# UNIVERSE SELECTION — rotaciones y candidatos pendientes
# (#UNIVERSE-SELECTION). /api/admin/* es ADMIN-only por gating del middleware.
# /api/rotations/recent es VIEWER-friendly para mostrar el banner del dashboard.
# =============================================================================

def _serialize_rotation(row: dict) -> dict:
    """rotation_decisions row → JSON-friendly dict."""
    out = _to_json(dict(row))
    # candidates_proposed puede venir como str (JSONB serializado) o list
    raw = out.get("candidates_proposed")
    if isinstance(raw, str):
        try:
            out["candidates_proposed"] = json.loads(raw)
        except Exception:
            out["candidates_proposed"] = []
    return out


@app.get("/api/admin/rotations")
async def admin_list_rotations(
    limit:  int           = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None, description="pending|executed|rolled_back|failed|discarded"),
):
    if status and status not in {"pending", "executed", "rolled_back", "failed", "discarded"}:
        raise HTTPException(status_code=400, detail="invalid_status")
    try:
        rows = await historian.get_recent_rotations(_owner_id, limit=limit, status=status)
        return [_serialize_rotation(r) for r in rows]
    except Exception as e:
        _http_500("/api/admin/rotations GET", e)


@app.get("/api/admin/rotations/{decision_id}")
async def admin_get_rotation(decision_id: str):
    try:
        did = UUID(decision_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_decision_id")
    try:
        row = await historian.get_rotation_decision(did)
    except Exception as e:
        _http_500("/api/admin/rotations detail", e)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _serialize_rotation(row)


@app.post("/api/admin/rotations/{decision_id}/rollback")
async def admin_rollback_rotation(decision_id: str, request: Request):
    try:
        did = UUID(decision_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_decision_id")

    user = _get_session_user(request) or {}
    admin_email = user.get("email") or "unknown@admin"

    try:
        ok = await historian.rollback_rotation_in_db(did, admin_email)
    except Exception as e:
        _http_500("/api/admin/rotations rollback", e)

    if not ok:
        raise HTTPException(
            status_code=409,
            detail="rotation_not_rollbackable",
        )
    logger.warning(f"ROLLBACK admin: decision_id={did} | admin={admin_email}")
    return {"status": "rolled_back", "decision_id": str(did), "by": admin_email}


@app.get("/api/admin/candidates")
async def admin_list_candidates():
    try:
        rows = await historian.get_active_pending_candidates(_owner_id)
        return [_to_json(r) for r in rows]
    except Exception as e:
        _http_500("/api/admin/candidates GET", e)


@app.get("/api/rotations/recent")
async def api_rotations_recent(limit: int = Query(5, ge=1, le=20)):
    """
    Endpoint público (VIEWER + ADMIN) — últimas rotaciones executed para
    mostrar el banner del dashboard. Solo expone old/new/sentinel/timestamp,
    sin razonamiento ni costos.
    """
    try:
        rows = await historian.get_recent_rotations(
            _owner_id, limit=limit, status="executed",
        )
    except Exception as e:
        _http_500("/api/rotations/recent", e)
    return [
        {
            "decision_id":    str(r["decision_id"]),
            "sentinel_name":  r.get("sentinel_name"),
            "old_ticker":     r.get("old_ticker"),
            "new_ticker":     r.get("new_ticker"),
            "executed_at":    r["executed_at"].isoformat() if r.get("executed_at") else None,
            "trigger_reason": r.get("trigger_reason"),
        }
        for r in rows
    ]


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


# ═══════════════════════════ § 8 — SSE streaming + frontend estático ═══════════════════════════
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
