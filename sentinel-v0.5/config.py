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
SECRET_KEY   = os.environ.get("SECRET_KEY")   # sesiones FastAPI / Google OAuth

_CRITICAL_CREDENTIALS = {
    "ALPACA_API_KEY":    ALPACA_API_KEY,
    "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY,
    "DATABASE_URL":      DATABASE_URL,
    "NEWS_API_KEY":      NEWS_API_KEY,
    "SECRET_KEY":        SECRET_KEY,
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
