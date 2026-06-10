# config.py
# Configuración central de Sentinel v0.5.
# Todas las credenciales se leen desde variables de entorno — nunca hardcodeadas.
# Importar este módulo y llamar validate_config() al iniciar el sistema.

import os
from decimal import Decimal

from dotenv import load_dotenv

# Guard idempotente (#TD): aunque el entrypoint (main.py/api.py) llama load_dotenv()
# antes de importar config, lo repetimos acá para que config sea robusto si se importa
# desde contextos que no lo hicieron (scripts, tests). Corre ANTES de leer las vars de
# abajo, así las constantes module-level reflejan el .env. load_dotenv NO sobrescribe
# vars ya presentes en el entorno → llamarlo dos veces es inocuo.
load_dotenv()

# =============================================================================
# CREDENCIALES — leídas desde entorno
# Definir en .env o en el entorno del proceso antes de arrancar.
# =============================================================================

ALPACA_API_KEY    = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_BASE_URL   = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

DATABASE_URL = os.environ.get("DATABASE_URL")
# Tamaño del pool de conexiones asyncpg (#TD: antes hardcoded en historian.connect()).
DB_POOL_MIN  = int(os.environ.get("DB_POOL_MIN", "2"))
DB_POOL_MAX  = int(os.environ.get("DB_POOL_MAX", "10"))
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")   # DEPRECADO: The Ear migró a Alpaca News + DeepSeek (swap FinBERT→DeepSeek). Ya no es crítica.
SECRET_KEY   = os.environ.get("SECRET_KEY")   # legacy — uso histórico, no tocar

# Google OAuth — credenciales del proyecto "Afterlife Capital".
# Authorized redirect URI debe coincidir con OAUTH_REDIRECT_URI abajo.
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
SESSION_SECRET       = os.environ.get("SESSION_SECRET")   # firma cookies de sesión
OAUTH_REDIRECT_URI   = os.environ.get(
    "OAUTH_REDIRECT_URI",
    "https://sentinel.afterlifecapital.co/auth/callback",
)
SESSION_COOKIE_NAME    = "sentinel_session"
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60   # 24 horas

# Resend — emails transaccionales (welcome / removal del panel admin).
# Dominio verificado: afterlifecapital.co. Sender: noreply@afterlifecapital.co.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

# Email del owner del sistema (cuenta ADMIN protegida + reply-to de los emails
# de cierre). Es PII → vive SOLO en el .env, nunca hardcodeado en el código
# (§7.1). Si no está configurado, la protección/UPDATE del owner se omiten de
# forma segura (no se pisa el email persistido).
OWNER_EMAIL = os.environ.get("OWNER_EMAIL")

# Anthropic API — usada por el Universe Selector para proponer candidatos
# de rotación cuando un Sentinel se acerca al decay (#UNIVERSE-SELECTION).
# El bot llama a Claude Sonnet 4.6 con contexto de mercado + noticias macro.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL   = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# DeepSeek API — usada por The Ear para interpretar noticias de mercado y
# devolver un risk_score 0-1 (swap FinBERT→DeepSeek). API OpenAI-compatible.
# Si falta la key, The Ear degrada con gracia (fallback a last_risk_score) — NO
# es credencial crítica para el arranque (a diferencia de las de _CRITICAL).
# Modelo default = v4-flash (barato, suficiente para clasificar densidad
# risk-off; ~$1-2/mes con título+resumen). Cambiable a v4-pro vía .env.
DEEPSEEK_API_KEY        = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL       = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL          = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_TIMEOUT_SECONDS = float(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "20"))
# #BUG-DEEPSEEK-TRUNC: presupuesto de salida para el risk assessment. El default
# del cliente (512) truncaba el JSON con rationale ~9×/día (08/09-jun) → The Ear
# caía a last_risk_score en ~1/3 de los ciclos RTH.
DEEPSEEK_MAX_TOKENS     = int(os.environ.get("DEEPSEEK_MAX_TOKENS", "2048"))

# Nombres de las credenciales críticas. validate_config() las lee FRESH desde
# os.environ en cada llamada (#TD: antes era un dict que capturaba los VALORES al
# import → no reflejaba un os.environ.update posterior, ej. rotación de keys desde el
# panel admin o setup en tests). Guardamos solo los nombres; los valores se resuelven
# al validar.
_CRITICAL_CREDENTIAL_NAMES = (
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "DATABASE_URL",
    # NEWS_API_KEY removida de críticas: The Ear migró a Alpaca News (mismas keys
    # de Alpaca) + DeepSeek. NewsAPI quedó deprecada. DEEPSEEK_API_KEY tampoco es
    # crítica: si falta, The Ear cae a last_risk_score (degradación con gracia).
    "SECRET_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "SESSION_SECRET",
    "RESEND_API_KEY",
    "ANTHROPIC_API_KEY",
)

# =============================================================================
# DISPATCHER
# Controla la distribución de capital entre los 10 Sentinels.
# Half-Kelly reduce el tamaño teórico a la mitad para limitar drawdown.
# =============================================================================

MAX_CAPITAL_PER_SENTINEL = 25.0   # % máximo asignable a un solo Sentinel
MIN_CAPITAL_PER_SENTINEL = 5.0    # % mínimo — por debajo de esto el Sentinel se pausa
KELLY_FRACTION           = 0.5    # Half-Kelly
MAX_ALLOCATION_TOTAL     = 85     # % del equity. La suma de allocations por Sentinel no
                                  # excede esto: garantiza 15% en cash para fees, slippage,
                                  # gaps de apertura y oportunidades asimétricas. #GR-4.

# --- #GR-2 — Position sizing por ATR (risk parity). FLAG-GATED, default OFF. ---
# Con ATR_SIZING_ENABLED=False el bot mantiene el comportamiento viejo (qty del
# Sentinel, sin TP/SL). Roman lo activa en .env (ATR_SIZING_ENABLED=true) + restart
# cuando decida — fallback inmediato volviendo a false. Sin esto, el bot del lunes
# empezaría a operar con sizing ~30× mayor sin validación gradual.
ATR_SIZING_ENABLED         = os.environ.get("ATR_SIZING_ENABLED", "false").lower() == "true"
RISK_PER_TRADE             = Decimal("0.01")   # % del equity arriesgado por trade (1%)
ATR_WINDOW                 = 14                 # ventana Wilder estándar
ATR_STOP_MULTIPLIER        = Decimal("2.0")     # distancia entry→stop = 2× ATR
RR_RATIO_TAKE_PROFIT       = Decimal("2.0")     # take-profit a 2× el riesgo (R/R 2:1)
MAX_POSITION_PCT_OF_EQUITY = Decimal("0.15")    # cap por posición individual (15%)
MIN_POSITION_USD           = Decimal("25")      # piso $ para que los fees no dominen

# --- T-X (#FEAT-011): multipliers ATR per-Sentinel (Opción B) ---
# SL = entry − sl_mult × ATR (riesgo absoluto)
# TP = entry + sl_mult × ATR × rr_ratio (recompensa)
# Cada par se justifica por la naturaleza del Sentinel (trend largo vs mean-rev
# rápida vs intradía vs reversal) — ver docs/TAREA_T-X_tpsl_per_sentinel.md §1.
# Los defaults globales de arriba (ATR_STOP_MULTIPLIER/RR_RATIO_TAKE_PROFIT)
# quedan como fallback si el strategy_type no está en el dict.
ATR_PER_SENTINEL = {
    "sma_crossover":     {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("3.0")},   # trend largo
    "rsi_short":         {"sl_mult": Decimal("1.5"), "rr_ratio": Decimal("1.0")},   # mean-rev rápida (RSI2)
    "bollinger_bounce":  {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("1.5")},   # mean-rev mediana
    "macd_volume":       {"sl_mult": Decimal("2.5"), "rr_ratio": Decimal("2.5")},   # trend confirmado por vol
    "orb_breakout":      {"sl_mult": Decimal("1.0"), "rr_ratio": Decimal("2.0")},   # intradía momentum
    "ema_triple":        {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("3.0")},   # trend smoother
    "vwap_reversion":    {"sl_mult": Decimal("1.0"), "rr_ratio": Decimal("1.0")},   # intradía mean-rev
    "rsi_divergence":    {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("2.0")},   # reversal (baseline)
    "bollinger_squeeze": {"sl_mult": Decimal("1.5"), "rr_ratio": Decimal("3.0")},   # volatility breakout
}


def get_atr_multipliers_for_strategy(strategy_type: str) -> dict:
    """
    Devuelve {'sl_mult', 'rr_ratio'} (Decimal) para el strategy_type del Sentinel.
    Fallback a los defaults globales (ATR_STOP_MULTIPLIER / RR_RATIO_TAKE_PROFIT)
    si el strategy_type no está en ATR_PER_SENTINEL (incluye "" o "unknown").
    """
    override = ATR_PER_SENTINEL.get(strategy_type)
    if override is not None:
        return override
    return {"sl_mult": ATR_STOP_MULTIPLIER, "rr_ratio": RR_RATIO_TAKE_PROFIT}


# --- #GR-3 — Drawdown limits del portafolio. FLAG-GATED, default OFF. ---
# Con PORTFOLIO_DD_LIMITS_ENABLED=False el dispatcher no evalúa drawdown (igual
# patrón que ATR_SIZING). Roman lo activa en .env cuando decida.
PORTFOLIO_DD_LIMITS_ENABLED = os.environ.get("PORTFOLIO_DD_LIMITS_ENABLED", "false").lower() == "true"
MAX_DAILY_DRAWDOWN_PCT      = Decimal("0.05")   # 5% intradía vs equity al open → pausa entradas hasta el cierre
MAX_WEEKLY_DRAWDOWN_PCT     = Decimal("0.10")   # 10% en 5 días hábiles → kill switch
MAX_CUMULATIVE_DRAWDOWN_PCT = Decimal("0.15")   # 15% vs peak histórico → pausa indefinida (intervención manual)

# --- BUG 2 (#BUG-CG-EXPOSURE, diseño Deep) — Alerta de sobre-exposición sostenida. ---
# SOLO NOTIFICACIÓN, CERO ventas automáticas (decisión Roman/Deep: vender en un dip
# lockea pérdidas; el cap que bloquea compras + el guard anti-margen ya cubren). Si la
# exposición (long_market_value / equity) supera EXPOSURE_ALERT_THRESHOLD durante
# EXPOSURE_ALERT_DAYS días hábiles seguidos, /api/status expone una alerta para el
# dashboard ("bot al 96% hace 5 días"). Default ON: es read-only, no toca el trading.
EXPOSURE_ALERT_ENABLED   = os.environ.get("EXPOSURE_ALERT_ENABLED", "true").lower() == "true"
EXPOSURE_ALERT_THRESHOLD = Decimal("0.95")      # >95% del equity desplegado en longs
EXPOSURE_ALERT_DAYS      = 5                     # días hábiles consecutivos sostenidos

# --- EXP-005 — Modo Observador Fractional. FLAG-GATED, default ON. ---
# El bot opera IDÉNTICO (qty entera, floor en execute_order); con
# SHADOW_FRACTIONAL_ENABLED=true el dispatcher persiste en signals_shadow_fractional
# qué HUBIERA operado con fractional (notional), solo para análisis post-período.
# NO altera ninguna orden enviada a Alpaca. Fallback: =false en .env + restart.
SHADOW_FRACTIONAL_ENABLED  = os.environ.get("SHADOW_FRACTIONAL_ENABLED", "true").lower() == "true"

# --- #HE-2 — Investment Thesis Tracking. FLAG-GATED, default OFF. ---
# Con THESIS_TRACKING_ENABLED=False el Universe Selector opera idéntico (no crea
# ni transiciona tesis, no inyecta el feedback histórico al prompt). Con =true,
# cada rotación nace como una tesis (IDEA → ENTRY_READY → ... → CLOSED) y el
# historial de tesis cerradas se incluye en el system prompt como contexto
# (feedback loop, #ME-2). NO altera las órdenes que manda el bot; solo registra
# metadata y enriquece el prompt. Roman lo activa en .env (5º flag del restart
# del martes) — fallback inmediato volviendo a false. Ver investment_thesis.py.
THESIS_TRACKING_ENABLED    = os.environ.get("THESIS_TRACKING_ENABLED", "false").lower() == "true"
# Cuántas tesis cerradas recientes se incluyen en el prompt del Universe Selector.
THESIS_FEEDBACK_LIMIT      = int(os.environ.get("THESIS_FEEDBACK_LIMIT", "20"))

# --- #FEAT-007 — The Ear sentiment FinBERT. FLAG-GATED, default OFF. ---
# Con THE_EAR_SENTIMENT_ENABLED=False The Ear usa solo keyword matching (legacy,
# idéntico). Con =true y un SentimentAnalyzer inyectado, corre en "hybrid mode":
# el risk_score [0,1] lo sigue dando el keyword (semántica intacta para decay/
# dashboard/veto), y FinBERT agrega (a) un veto extra si el sentiment promedio
# cae por debajo del umbral y (b) persistencia del score FinBERT para calibrar.
# Roman lo activa en .env + restart. Si el modelo no carga → fallback a keyword.
THE_EAR_SENTIMENT_ENABLED  = os.environ.get("THE_EAR_SENTIMENT_ENABLED", "false").lower() == "true"
# Umbral de veto FinBERT: sentiment promedio [-1,1] por debajo de este valor
# bloquea el trading (can_trade=False). Default conservador; se recalibra con
# data real (ver docs/finbert_recalibration_plan.md).
THE_EAR_FINBERT_VETO_THRESHOLD = float(os.environ.get("THE_EAR_FINBERT_VETO_THRESHOLD", "-0.6"))

# --- #FEAT-014 — Cooldown post-loss en mean reversion. FLAG-GATED, default OFF. ---
# Con COOLDOWN_POST_LOSS_ENABLED=true, el dispatcher bloquea un BUY si hubo un
# cierre con pérdida (disposal gain<0, motor FIFO de #CR-1) en ese ticker dentro de
# los últimos COOLDOWN_POST_LOSS_DAYS días. Ataca el ~27% de wash sales que generaba
# la re-entrada rápida del bot (#CR-1). Default OFF para arranque seguro; Roman lo
# activa en .env tras validar. La ventana IRS de wash sale es 30d; 7d evita la
# re-entrada inmediata sin ser tan restrictivo.
COOLDOWN_POST_LOSS_ENABLED = os.environ.get("COOLDOWN_POST_LOSS_ENABLED", "false").lower() == "true"
COOLDOWN_POST_LOSS_DAYS    = int(os.environ.get("COOLDOWN_POST_LOSS_DAYS", "7"))

# --- Wilder RSI smoothing. FLAG-GATED, default OFF. ---
# Con WILDER_RSI_ENABLED=true, _rsi() usa el smoothing de Wilder (RMA, EWMA con
# alpha=1/period — estándar de la industria, Wilder 1978) en lugar del SMA-smoothing
# actual. Cambia las señales de los Sentinels que usan RSI (S-2 RSI Fast Reversion,
# S-8 RSI Divergence). Default OFF para que Roman lo active por separado y compare.
WILDER_RSI_ENABLED = os.environ.get("WILDER_RSI_ENABLED", "false").lower() == "true"

# =============================================================================
# CORRELATION GUARD
# Corre antes de cada orden. Si la correlación rolling entre la señal entrante
# y posiciones abiertas supera el umbral, reduce o descarta la posición.
# =============================================================================

CORRELATION_THRESHOLD      = 0.75   # umbral de correlación para reducir posición
CORRELATION_ROLLING_WINDOW = 60     # número de velas para el cálculo rolling
MIN_POSITION_SIZE          = 1      # unidades mínimas — si sizing cae por debajo, descarta señal

# =============================================================================
# THE EAR
# Monitoreo macro continuo. Circuit Breaker pausa todas las operaciones
# si el mercado mueve más allá de los umbrales definidos.
# Parking Brake cierra posiciones abiertas antes del cierre del mercado.
# =============================================================================

NEWS_FETCH_INTERVAL_SECONDS    = 900    # polling de noticias cada 15 minutos (Alpaca News)
VIX_CIRCUIT_BREAKER_THRESHOLD  = 30    # % de cambio en VIX que activa el corte
SPY_CIRCUIT_BREAKER_THRESHOLD  = -2    # % de caída de SPY en 15 min que activa el corte
PARKING_BRAKE_TIME             = "15:45"  # hora límite para nuevas órdenes (HH:MM ET)
RISK_SCORE_VETO_THRESHOLD      = 0.7     # risk_score sobre este valor bloquea operaciones (= umbral de ENTRADA al veto)

# --- Veto de noticias SUAVIZADO (swap FinBERT→DeepSeek, LOCKED por Roman). ---
# El veto por risk_score deja de ser instantáneo (1 ciclo) para evitar que un
# titular alarmista AISLADO frene la jornada entera. Histéresis con 2 umbrales:
#   - ENTRAR al veto (can_trade=False): risk_score >= ENTER en CONSECUTIVE ciclos seguidos.
#   - SALIR del veto: risk_score < EXIT (banda muerta ENTER..EXIT evita flapping en el borde).
# The Ear es stateful (cuenta ciclos consecutivos ≥ENTER + estado del veto, in-memory;
# en restart arranca SIN veto = seguro). NO toca el Circuit Breaker (freno rápido por
# precio VIXY/SPY), que sigue intacto → suavizar el veto de noticias NO deja expuesto
# a crashes súbitos (esos los corta el circuit breaker).
RISK_VETO_ENTER_THRESHOLD   = float(os.environ.get("RISK_VETO_ENTER_THRESHOLD", str(RISK_SCORE_VETO_THRESHOLD)))  # 0.70
RISK_VETO_EXIT_THRESHOLD    = float(os.environ.get("RISK_VETO_EXIT_THRESHOLD", "0.60"))
RISK_VETO_CONSECUTIVE_CYCLES = int(os.environ.get("RISK_VETO_CONSECUTIVE_CYCLES", "2"))
# Tope de artículos por batch enviado a DeepSeek (acota tokens/costo; los más recientes).
NEWS_BATCH_MAX_ARTICLES     = int(os.environ.get("NEWS_BATCH_MAX_ARTICLES", "40"))
# Cuántos titulares top-riesgo se persisten en macro_events.news_titles (= top_n actual).
NEWS_TOP_TITLES             = int(os.environ.get("NEWS_TOP_TITLES", "5"))

# =============================================================================
# HISTORIAN
# Calcula performance por (Sentinel, ticker). Si una combinación cae bajo
# los umbrales, se marca performance_decay = TRUE y el Dispatcher rota el activo.
# WARMUP evita rotar activos con muy poca historia estadística.
# =============================================================================

PERFORMANCE_DECAY_THRESHOLD = 0.4    # win_rate mínimo antes de marcar decay
SHARPE_MINIMUM              = 0.05   # Sharpe per-trade mínimo (B.2: recalibrado de 0.5 anualizado; equiv. exacto 0.5/80.94≈0.006, a 0.05 conservador)
WARMUP_TRADES_REQUIRED      = 10     # trades mínimos antes de evaluar decay
PROFIT_FACTOR_MINIMUM       = 1.3    # gross_profit/abs(gross_loss) para "rescatar" del decay (EXP-002 / Rec 6)
RTD_MINIMUM                 = 1.0    # return-to-drawdown mínimo para "rescatar" del decay (EXP-002 / Rec 6)

# Aliases explícitos para Universe Selector (#UNIVERSE-SELECTION). Mantienen
# coherencia entre el Historian (que usa los nombres genéricos) y el selector
# (que también necesita warning thresholds anticipados).
DECAY_THRESHOLD_WIN_RATE   = PERFORMANCE_DECAY_THRESHOLD
DECAY_THRESHOLD_SHARPE     = SHARPE_MINIMUM

# Warning thresholds — disparan request anticipado de candidato a Claude
# antes de cruzar el umbral de decay. Si la performance se recupera el
# candidato se descarta (status='discarded').
WARNING_THRESHOLD_WIN_RATE = 0.45
WARNING_THRESHOLD_SHARPE   = 0.65

# =============================================================================
# UNIVERSE SELECTION (#UNIVERSE-SELECTION)
# Rotación automática de tickers usando Claude. Toggle global por si hay
# que pausar el módulo entero sin bajar el bot.
# =============================================================================

UNIVERSE_SELECTION_ENABLED                = os.environ.get(
    "UNIVERSE_SELECTION_ENABLED", "true"
).lower() == "true"
UNIVERSE_SELECTION_TIMEOUT_SECONDS        = float(os.environ.get(
    "UNIVERSE_SELECTION_TIMEOUT_SECONDS", "60"   # default 60s — subido tras test de latencia con system prompt nuevo (All Weather + AQR)
))
UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD  = float(os.environ.get(
    "UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD", "0.20"
))
UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS  = float(os.environ.get(
    "UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS", "180"  # default 180s — ratio 3:1 vs per-call 60s
))
UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS     = int(os.environ.get(
    "UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS", "7"
))

# =============================================================================
# DAILY REPORT (#DAILY-REPORT)
# Reporte diario por email a las 16:30 ET (L-V). Toggle global para pausar el
# envío automático sin tocar la lógica del reporte ni bajar la API.
# Desactivado el 2026-05-23 con el cierre anticipado del período de observación
# (HANDOFF #2). Reactivar para el segundo período de observación (junio):
# poner DAILY_REPORT_ENABLED=true en .env (o quitar la línea — default es True).
# El endpoint manual /api/report/daily/send-now sigue activo aunque esto sea False.
# =============================================================================

DAILY_REPORT_ENABLED = os.environ.get("DAILY_REPORT_ENABLED", "true").lower() == "true"

# =============================================================================
# OBSERVABILIDAD / OPS (#OP-2)
# Heartbeat externo (healthchecks.io). main.py pinga esta URL al final de cada
# ciclo del loop principal; si el bot se cae, healthchecks.io alerta por email.
# Flag-gated: vacío = deshabilitado (no se hace ningún ping). Roman crea el check
# en https://healthchecks.io/ y pega la URL de ping (https://hc-ping.com/<UUID>)
# en .env como HEARTBEAT_URL. Ver README sección "Heartbeat / monitoreo".
# =============================================================================

HEARTBEAT_URL = os.environ.get("HEARTBEAT_URL", "")

# =============================================================================
# REGIME CLASSIFIER (S-10)
# Meta-agente que clasifica cada sesión antes de que el mercado abra.
# Entrenado sobre 25 años de datos SPY con Random Forest.
# =============================================================================

REGIME_LABELS        = ["BULL", "NEUTRAL", "BEAR"]
SPY_HISTORICAL_YEARS = 25

# =============================================================================
# SISTEMA GENERAL
# Parámetros compartidos por todos los módulos.
# =============================================================================

BASE_TICKER    = "SPY"
CANDLE_INTERVAL = "15Min"
# Parámetros de descarga de barras de los Sentinels (#TD-24: antes hardcoded en
# sentinels/__init__.py). BARS_LOOKBACK = velas de 15min a analizar; FETCH_DAYS = días
# calendario a pedir (margen para cubrir fines de semana → ~120-150 barras hábiles).
BARS_LOOKBACK  = 150
FETCH_DAYS     = 10
MARKET_OPEN    = "09:30"
MARKET_CLOSE   = "16:00"
TIMEZONE       = "America/New_York"
LOG_LEVEL      = "INFO"
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "roman")


# =============================================================================
# VALIDACIÓN
# =============================================================================

def validate_config() -> bool:
    """
    Verifica que todas las credenciales críticas estén presentes.
    Llamar al inicio del sistema antes de instanciar cualquier agente.
    Lanza ValueError detallando qué variable falta.
    """
    missing = [name for name in _CRITICAL_CREDENTIAL_NAMES if not os.environ.get(name)]

    if missing:
        raise ValueError(
            f"Sentinel no puede iniciar. Variables de entorno faltantes: {', '.join(missing)}. "
            "Definirlas en el entorno del proceso o en un archivo .env antes de arrancar."
        )

    return True

# NOTA: config.py ahora llama load_dotenv() al import (guard idempotente, arriba),
# así que es robusto aunque el caller no lo haya hecho. El entrypoint (main.py/api.py)
# igual lo llama primero — es redundante pero inocuo. Ver main.py para el orden.
