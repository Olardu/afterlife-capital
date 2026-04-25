# main.py
# Entry point de Sentinel v0.5.
# Inicializa todos los agentes, construye el grafo LangGraph y orquesta
# el ciclo principal de trading en paper mode con Alpaca IEX.
#
# ORDEN CRÍTICO: load_dotenv() corre ANTES de cualquier import de config.

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

from config import (
    BASE_TICKER,
    CANDLE_INTERVAL,
    DATABASE_URL,
    LOG_LEVEL,
    MARKET_CLOSE,
    MARKET_OPEN,
    MIN_CAPITAL_PER_SENTINEL,
    OWNER_USERNAME,
    TIMEZONE,
    validate_config,
)
from correlation_guard import CorrelationGuard
from dispatcher import Dispatcher
from historian import Historian
from regime_classifier import RegimeClassifier
from sentinels import SENTINEL_REGISTRY, SentinelSMACrossover
from the_ear import TheEar


# =============================================================================
# LOGGING
# =============================================================================

def _setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado — evita handlers duplicados en re-imports o tests

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt   = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        filename    = "logs/sentinel.log",
        maxBytes    = 5 * 1024 * 1024,  # 5 MB
        backupCount = 3,
        encoding    = "utf-8",
    )
    file_handler.setFormatter(fmt)

    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)


_setup_logging()
logger = logging.getLogger("sentinel.main")


# =============================================================================
# HELPERS DE HORARIO
# =============================================================================

def _is_market_open() -> bool:
    """Retorna True si el mercado está abierto ahora mismo en ET (lun-vie)."""
    now = datetime.now(tz=ZoneInfo(TIMEZONE))
    if now.weekday() >= 5:   # sábado=5, domingo=6
        return False
    open_h,  open_m  = map(int, MARKET_OPEN.split(":"))
    close_h, close_m = map(int, MARKET_CLOSE.split(":"))
    current = (now.hour, now.minute)
    return (open_h, open_m) <= current < (close_h, close_m)


def _seconds_to_next_candle() -> float:
    """Segundos hasta el próximo múltiplo de 15 minutos (alineado al reloj)."""
    now  = datetime.now(tz=ZoneInfo(TIMEZONE))
    wait = (15 - now.minute % 15) * 60 - now.second
    return max(float(wait), 1.0)


# =============================================================================
# INICIALIZACIÓN
# =============================================================================

async def _get_owner_id(historian: Historian) -> uuid.UUID:
    """Obtiene el user_id del owner desde la DB usando OWNER_USERNAME de config."""
    async with historian.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM users WHERE username = $1 LIMIT 1",
            OWNER_USERNAME,
        )
    if row is None:
        raise RuntimeError(
            f"Usuario '{OWNER_USERNAME}' no encontrado en la tabla users. "
            "Crear el usuario o ajustar OWNER_USERNAME en .env antes de arrancar."
        )
    return row["user_id"]


async def initialize() -> dict:
    """
    Inicializa todos los componentes del sistema en el orden correcto.

    Orden crítico:
        1. validate_config()           — credenciales presentes
        2. Historian.connect()         — pool PostgreSQL
        3. RegimeClassifier.initialize() — descarga 25 años SPY y entrena RF
        4. Instanciar TheEar, CorrelationGuard
        5. Instanciar Dispatcher con owner_id
        6. Instanciar Sentinels desde DB (o S-1 SMA Crossover como default)

    Returns:
        dict con todas las instancias del sistema.
    """
    logger.info("=== Sentinel v0.5 — Iniciando sistema ===")

    # 1. Validar credenciales
    validate_config()
    logger.info("Credenciales validadas.")

    # 2. Historian — pool de conexiones PostgreSQL
    historian = Historian(database_url=DATABASE_URL)
    await historian.connect()
    logger.info("Historian conectado a PostgreSQL.")

    # 3. RegimeClassifier — entrena el modelo (puede tardar 30-60s)
    regime_classifier = RegimeClassifier()
    await regime_classifier.initialize()

    # 4. TheEar y CorrelationGuard
    the_ear           = TheEar(historian=historian)
    correlation_guard = CorrelationGuard()

    # 5. Dispatcher — requiere owner_id desde DB
    owner_id   = await _get_owner_id(historian)
    dispatcher = Dispatcher(
        historian         = historian,
        the_ear           = the_ear,
        correlation_guard = correlation_guard,
        regime_classifier = regime_classifier,
        owner_id          = owner_id,
    )
    logger.info(f"Dispatcher inicializado para owner_id={owner_id}.")

    # 6. Instanciar Sentinels
    sentinels: list = []
    try:
        active = await historian.get_active_sentinels(owner_id)
    except Exception as e:
        logger.error(f"Error al obtener Sentinels desde DB: {e}")
        active = []

    for row in active:
        strategy_type = row.get("strategy_type", "")
        cls = SENTINEL_REGISTRY.get(strategy_type)
        if cls is None:
            logger.warning(
                f"strategy_type '{strategy_type}' no registrado en SENTINEL_REGISTRY. "
                f"Sentinel {row['name']} omitido."
            )
            continue
        sentinel = cls(
            sentinel_id = row["sentinel_id"],
            owner_id    = owner_id,
            ticker      = row["ticker"],
        )
        sentinels.append(sentinel)
        logger.info(f"Sentinel cargado desde DB: {sentinel.name} ({sentinel.ticker})")

    # Fallback: S-1 SMA Crossover por defecto si la DB está vacía
    if not sentinels:
        logger.warning(
            "Sin Sentinels activos en DB. Creando e insertando S-1 SMA Crossover por defecto."
        )
        fallback_id = uuid.uuid4()
        try:
            async with historian.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO sentinels
                        (sentinel_id, owner_id, name, strategy_type, ticker, capital_allocation)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    fallback_id,
                    owner_id,
                    "S-1 SMA Crossover",
                    "sma_crossover",
                    BASE_TICKER,
                    MIN_CAPITAL_PER_SENTINEL,
                )
            logger.info(f"S-1 SMA Crossover insertado en DB con sentinel_id={fallback_id}.")
        except Exception as e:
            logger.error(f"Error al insertar S-1 en DB: {e}. El Sentinel operará sin registro persistente.")

        sentinels.append(SentinelSMACrossover(
            sentinel_id = fallback_id,
            owner_id    = owner_id,
        ))

    logger.info(f"Sistema listo — {len(sentinels)} Sentinel(s) activo(s).")
    return {
        "historian":         historian,
        "regime_classifier": regime_classifier,
        "the_ear":           the_ear,
        "correlation_guard": correlation_guard,
        "dispatcher":        dispatcher,
        "sentinels":         sentinels,
        "owner_id":          owner_id,
    }


# =============================================================================
# CICLO PRINCIPAL
# =============================================================================

async def main_loop(system: dict):
    """
    Loop principal de trading. Se ejecuta en ciclos de 15 minutos alineados
    al reloj (09:30, 09:45, 10:00, ...) mientras el mercado está abierto.

    En cada ciclo:
        1. Ejecuta todos los Sentinels en paralelo con asyncio.gather
        2. Filtra señales (descarta None)
        3. Pasa señales al Dispatcher.run_cycle(pending_signals)
        4. Duerme hasta el próximo múltiplo de 15 minutos

    Fuera de horario: loggea y duerme 60s antes de volver a verificar.
    """
    dispatcher: Dispatcher = system["dispatcher"]
    sentinels: list        = system["sentinels"]

    logger.info("Main loop iniciado. Esperando horario de mercado...")

    while True:
        if not _is_market_open():
            now = datetime.now(tz=ZoneInfo(TIMEZONE))
            logger.debug(f"Fuera de horario de mercado ({now.strftime('%H:%M')} ET). Durmiendo 60s.")
            await asyncio.sleep(60)
            continue

        logger.info("--- Nuevo ciclo de 15 minutos ---")

        # 1. Ejecutar todos los Sentinels en paralelo
        try:
            signals_raw = await asyncio.gather(
                *[s.run() for s in sentinels],
                return_exceptions=True,
            )
        except Exception as e:
            logger.error(f"Error en asyncio.gather de Sentinels: {e}")
            signals_raw = []

        # 2. Filtrar None y excepciones
        pending_signals = []
        for i, result in enumerate(signals_raw):
            if isinstance(result, Exception):
                logger.error(f"Sentinel[{i}] lanzó excepción: {result}")
            elif result is not None:
                pending_signals.append(result)

        logger.info(f"{len(pending_signals)} señal(es) generada(s) por los Sentinels.")

        # 3. Pasar señales al Dispatcher
        try:
            await dispatcher.run_cycle(pending_signals=pending_signals)
        except Exception as e:
            logger.error(f"Error en Dispatcher.run_cycle: {e}")

        # 4. Dormir hasta el próximo múltiplo de 15 minutos
        wait = _seconds_to_next_candle()
        logger.debug(f"Próximo ciclo en {wait:.0f}s.")
        await asyncio.sleep(wait)


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """Inicializa el sistema, arranca The Ear en background y entra al main loop."""
    system = await initialize()

    # The Ear corre su propio polling loop en paralelo (NewsAPI cada 15 min)
    ear_task = asyncio.create_task(
        system["the_ear"].start_polling(),
        name="the_ear_polling",
    )
    logger.info("The Ear polling iniciado en background.")

    try:
        await main_loop(system)
    finally:
        ear_task.cancel()
        try:
            await ear_task
        except asyncio.CancelledError:
            pass

        await system["historian"].close()
        logger.info("=== Sentinel v0.5 — Sistema cerrado limpiamente ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt recibido — cerrando Sentinel.")
    except Exception as e:
        logger.critical(f"Error fatal en Sentinel: {e}", exc_info=True)
        raise
