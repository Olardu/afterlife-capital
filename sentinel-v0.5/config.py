# config.py
# Configuración central de Sentinel v0.5.
# Todas las credenciales se leen desde variables de entorno — nunca hardcodeadas.
# Importar este módulo y llamar validate_config() al iniciar el sistema.

import os

# =============================================================================
# CREDENCIALES — leídas desde entorno
# Definir en .env o en el entorno del proceso antes de arrancar.
# =============================================================================

ALPACA_API_KEY    = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_BASE_URL   = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

DATABASE_URL = os.environ.get("DATABASE_URL")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
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

# Anthropic API — usada por el Universe Selector para proponer candidatos
# de rotación cuando un Sentinel se acerca al decay (#UNIVERSE-SELECTION).
# El bot llama a Claude Sonnet 4.6 con contexto de mercado + noticias macro.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL   = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

_CRITICAL_CREDENTIALS = {
    "ALPACA_API_KEY":       ALPACA_API_KEY,
    "ALPACA_SECRET_KEY":    ALPACA_SECRET_KEY,
    "DATABASE_URL":         DATABASE_URL,
    "NEWS_API_KEY":         NEWS_API_KEY,
    "SECRET_KEY":           SECRET_KEY,
    "GOOGLE_CLIENT_ID":     GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
    "SESSION_SECRET":       SESSION_SECRET,
    "RESEND_API_KEY":       RESEND_API_KEY,
    "ANTHROPIC_API_KEY":    ANTHROPIC_API_KEY,
}

# =============================================================================
# DISPATCHER
# Controla la distribución de capital entre los 10 Sentinels.
# Half-Kelly reduce el tamaño teórico a la mitad para limitar drawdown.
# =============================================================================

MAX_CAPITAL_PER_SENTINEL = 25.0   # % máximo asignable a un solo Sentinel
MIN_CAPITAL_PER_SENTINEL = 5.0    # % mínimo — por debajo de esto el Sentinel se pausa
KELLY_FRACTION           = 0.5    # Half-Kelly

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

NEWS_FETCH_INTERVAL_SECONDS    = 900    # polling NewsAPI cada 15 minutos
VIX_CIRCUIT_BREAKER_THRESHOLD  = 30    # % de cambio en VIX que activa el corte
SPY_CIRCUIT_BREAKER_THRESHOLD  = -2    # % de caída de SPY en 15 min que activa el corte
PARKING_BRAKE_TIME             = "15:45"  # hora límite para nuevas órdenes (HH:MM ET)
RISK_SCORE_VETO_THRESHOLD      = 0.7     # risk_score sobre este valor bloquea operaciones

# =============================================================================
# HISTORIAN
# Calcula performance por (Sentinel, ticker). Si una combinación cae bajo
# los umbrales, se marca performance_decay = TRUE y el Dispatcher rota el activo.
# WARMUP evita rotar activos con muy poca historia estadística.
# =============================================================================

PERFORMANCE_DECAY_THRESHOLD = 0.4    # win_rate mínimo antes de marcar decay
SHARPE_MINIMUM              = 0.5    # Sharpe ratio mínimo aceptable
WARMUP_TRADES_REQUIRED      = 10     # trades mínimos antes de evaluar decay

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
    missing = [name for name, value in _CRITICAL_CREDENTIALS.items() if not value]

    if missing:
        raise ValueError(
            f"Sentinel no puede iniciar. Variables de entorno faltantes: {', '.join(missing)}. "
            "Definirlas en el entorno del proceso o en un archivo .env antes de arrancar."
        )

    return True

# ADVERTENCIA: load_dotenv() debe ejecutarse ANTES de importar
# este módulo. Ver main.py para el orden correcto de inicialización.
