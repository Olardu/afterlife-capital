# main.py
# Entry point de Sentinel v0.5.
# Inicializa todos los agentes, construye el grafo LangGraph y orquesta
# el ciclo principal de trading en paper mode con Alpaca IEX.
#
# ORDEN CRÍTICO: load_dotenv() corre ANTES de cualquier import de config.
#
# Índice de secciones (§) — buscables con "§ N":
#   § 1 — Logging
#   § 2 — Helpers de horario
#   § 3 — Inicialización
#   § 4 — Ciclo principal
#   § 5 — Entry point (pollers de background + main)

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp

from config import (
    BASE_TICKER,
    DATABASE_URL,
    DEEPSEEK_API_KEY,
    HEARTBEAT_URL,
    LOG_LEVEL,
    MARKET_CLOSE,
    MARKET_OPEN,
    MIN_CAPITAL_PER_SENTINEL,
    OWNER_USERNAME,
    TIMEZONE,
    UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS,
    UNIVERSE_SELECTION_ENABLED,
    validate_config,
)
from correlation_guard import CorrelationGuard
from dispatcher import Dispatcher
from historian import Historian
from reconcile_pending_trades import reconcile_pending
from regime_classifier import RegimeClassifier
from sentinels import SENTINEL_REGISTRY, SentinelSMACrossover
from the_ear import TheEar


# =============================================================================
# § 1 — LOGGING
# =============================================================================

def _setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado — evita handlers duplicados en re-imports o tests

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt   = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    # Path absoluto basado en la ubicación del módulo (no en el CWD del proceso),
    # para que el log no se fragmente si se arranca desde otra carpeta.
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # #TD-8: rotación DIARIA (TimedRotatingFileHandler) en vez de por tamaño — el bot
    # corre 24/7 y el tope de 5MB se llenaba rápido. Rota a medianoche, conserva ~1 semana.
    file_handler = TimedRotatingFileHandler(
        filename    = str(log_dir / "sentinel.log"),
        when        = "midnight",
        backupCount = 7,
        encoding    = "utf-8",
    )
    file_handler.setFormatter(fmt)

    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)


_setup_logging()
logger = logging.getLogger("sentinel.main")


# =============================================================================
# § 2 — HELPERS DE HORARIO
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


async def _send_heartbeat() -> None:
    """
    Ping no-bloqueante a healthchecks.io (#OP-2): señala "el loop completó un
    ciclo más". Si el bot se cae, healthchecks.io deja de recibir pings y alerta.

    Flag-gated por HEARTBEAT_URL: vacío = no hace nada. Cualquier fallo de red se
    loggea como warning y NO interrumpe el ciclo de trading (best-effort puro).
    """
    if not HEARTBEAT_URL:
        return
    try:
        async with aiohttp.ClientSession() as session:
            await asyncio.wait_for(session.get(HEARTBEAT_URL), timeout=5)
    except Exception as e:
        logger.warning(f"Heartbeat ping falló (no afecta el bot): {e}")


# =============================================================================
# § 3 — INICIALIZACIÓN
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
    # Swap FinBERT→DeepSeek: si hay DEEPSEEK_API_KEY, construir el DeepSeekClient
    # e inyectarlo en The Ear (DIP). The Ear lo usa para interpretar las noticias
    # de Alpaca News y devolver risk_score. Sin key → cliente None y The Ear queda
    # "sordo" a noticias (risk_score = last_risk_score, fallback seguro).
    deepseek_client = None
    if DEEPSEEK_API_KEY:
        from deepseek_client import DeepSeekClient
        deepseek_client = DeepSeekClient()
        logger.info(f"The Ear con DeepSeek habilitado (modelo {deepseek_client.model}).")
    else:
        logger.warning("DEEPSEEK_API_KEY ausente — The Ear sin interpretación de "
                       "noticias (risk_score se sostiene en el último conocido).")
    the_ear           = TheEar(historian=historian, deepseek_client=deepseek_client)
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
        tickers = list(row.get("tickers") or [])
        if not tickers:
            logger.warning(f"Sentinel {row['name']} sin tickers asignados — omitido.")
            continue
        sentinel = cls(
            sentinel_id = row["sentinel_id"],
            owner_id    = owner_id,
            tickers     = tickers,
        )
        sentinels.append(sentinel)
        logger.info(f"Sentinel cargado desde DB: {sentinel.name} ({', '.join(tickers)})")

    # Fallback: S-1 SMA Crossover por defecto si la DB está vacía
    if not sentinels:
        logger.warning(
            "Sin Sentinels activos en DB. Creando e insertando S-1 SMA Crossover por defecto."
        )
        fallback_id = uuid.uuid4()
        try:
            async with historian.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO sentinels
                            (sentinel_id, owner_id, name, strategy_type, capital_allocation)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        fallback_id,
                        owner_id,
                        "S-1 SMA Crossover",
                        "sma_crossover",
                        MIN_CAPITAL_PER_SENTINEL,
                    )
                    await conn.execute(
                        """
                        INSERT INTO sentinel_tickers (sentinel_id, ticker)
                        VALUES ($1, $2)
                        """,
                        fallback_id,
                        BASE_TICKER,
                    )
            logger.info(f"S-1 SMA Crossover insertado en DB con sentinel_id={fallback_id} (ticker={BASE_TICKER}).")
        except Exception as e:
            logger.error(f"Error al insertar S-1 en DB: {e}. El Sentinel operará sin registro persistente.")

        sentinels.append(SentinelSMACrossover(
            sentinel_id = fallback_id,
            owner_id    = owner_id,
            tickers     = [BASE_TICKER],
        ))

    # 7. Universe Selector (#UNIVERSE-SELECTION) — opcional, behind feature flag.
    # Si UNIVERSE_SELECTION_ENABLED=false (o ANTHROPIC_API_KEY ausente), seteamos
    # universe_selector=None y main_loop lo skipea. No bloquea el bot.
    universe_selector = None
    if UNIVERSE_SELECTION_ENABLED:
        try:
            from claude_client     import ClaudeClient
            from universe_selector import UniverseSelector
            from email_service     import send_rotation_email

            claude_client = ClaudeClient()

            async with historian.pool.acquire() as conn:
                owner_email = await conn.fetchval(
                    "SELECT email FROM users WHERE user_id = $1", owner_id,
                )

            async def _email_sender(decision: dict) -> bool:
                if not owner_email:
                    return False
                return await send_rotation_email(
                    to_email=owner_email,
                    decision=decision,
                )

            universe_selector = UniverseSelector(
                historian      = historian,
                claude_client  = claude_client,
                owner_id       = owner_id,
                email_sender   = _email_sender,
            )
            logger.info("Universe Selector habilitado (Claude API configurada).")
        except RuntimeError as e:
            # ANTHROPIC_API_KEY no configurada — feature degrada limpio.
            logger.warning(f"Universe Selector no inicializado: {e}")
            universe_selector = None
        except Exception as e:
            logger.error(f"Error al inicializar Universe Selector: {e}")
            universe_selector = None
    else:
        logger.info("Universe Selector deshabilitado (UNIVERSE_SELECTION_ENABLED=false).")

    logger.info(f"Sistema listo — {len(sentinels)} Sentinel(s) activo(s).")
    return {
        "historian":         historian,
        "regime_classifier": regime_classifier,
        "the_ear":           the_ear,
        "correlation_guard": correlation_guard,
        "dispatcher":        dispatcher,
        "sentinels":         sentinels,
        "owner_id":          owner_id,
        "universe_selector": universe_selector,
    }


# =============================================================================
# § 4 — CICLO PRINCIPAL
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
    universe_selector      = system.get("universe_selector")

    logger.info("Main loop iniciado. Esperando horario de mercado...")

    while True:
        if not _is_market_open():
            now = datetime.now(tz=ZoneInfo(TIMEZONE))
            logger.debug(f"Fuera de horario de mercado ({now.strftime('%H:%M')} ET). Durmiendo 60s.")
            await asyncio.sleep(60)
            continue

        logger.info("--- Nuevo ciclo de 15 minutos ---")

        # 1. Ejecutar todos los Sentinels en paralelo. Cada s.run() retorna
        # ahora una lista de señales (multi-ticker: 0 a N por Sentinel).
        try:
            signals_raw = await asyncio.gather(
                *[s.run() for s in sentinels],
                return_exceptions=True,
            )
        except Exception as e:
            logger.error(f"Error en asyncio.gather de Sentinels: {e}")
            signals_raw = []

        # 2. Aplanar (lista de listas → lista) y filtrar excepciones
        pending_signals = []
        for i, result in enumerate(signals_raw):
            if isinstance(result, Exception):
                logger.error(f"Sentinel {sentinels[i].name} lanzó excepción: {result}")
                continue
            if result:
                pending_signals.extend(result)

        logger.info(f"{len(pending_signals)} señal(es) generada(s) por los Sentinels.")

        # 3. Pasar señales al Dispatcher
        try:
            await dispatcher.run_cycle(pending_signals=pending_signals)
        except Exception as e:
            logger.error(f"Error en Dispatcher.run_cycle: {e}")

        # 3.5. Universe Selection (#UNIVERSE-SELECTION) — rotación automática
        # de tickers degradados. Aislado con timeout y try/except amplio:
        # un error o rate-limit de Claude NO debe interrumpir el bot.
        if universe_selector is not None:
            try:
                await asyncio.wait_for(
                    universe_selector.evaluate_all_sentinels(),
                    timeout=UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Universe Selection timeout "
                    f"({UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS}s) — skip este ciclo"
                )
            except Exception as e:
                logger.exception(f"Error en Universe Selection (no fatal): {e}")

        # 3.6. Heartbeat externo (#OP-2) — best-effort, no bloquea ni rompe el
        # ciclo. Señala a healthchecks.io que el loop sigue vivo.
        await _send_heartbeat()

        # 4. Dormir hasta el próximo múltiplo de 15 minutos
        wait = _seconds_to_next_candle()
        logger.debug(f"Próximo ciclo en {wait:.0f}s.")
        await asyncio.sleep(wait)


# =============================================================================
# § 5 — ENTRY POINT (pollers de background + main)
# =============================================================================

def _ear_task_done(task: asyncio.Task):
    """
    Callback para detectar fallas silenciosas del task de The Ear polling.
    Sin esto, una excepción no capturada en start_polling muere en silencio
    y el sistema sigue corriendo sin macro context. (#TECHDEBT promovido)
    """
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("ear_task cancelado limpiamente.")
        return
    if exc is not None:
        logger.critical(f"ear_task murió inesperadamente: {exc!r}", exc_info=exc)
    else:
        logger.warning("ear_task terminó sin excepción pero sin estar cancelado.")


_KILL_SWITCH_POLL_INTERVAL = 5  # segundos


async def _kill_switch_poller(historian: Historian, dispatcher: Dispatcher):
    """
    Pollea system_state cada 5s y maneja dos transiciones (#H-7):

    1. halt_requested=true  → activate_kill_switch + system_halted=true.
    2. system_halted=true & resume_requested=true → deactivate_kill_switch.

    El flag system_halted es la fuente de verdad del estado actual del
    sistema (vista por la API y el dashboard); halt_requested y
    resume_requested son los disparadores transitorios escritos por la API.

    Resiliencia: errores transitorios de DB se loggean y se reintenta en
    el próximo tick. El task solo muere por cancelación explícita.
    """
    logger.info("Kill switch poller iniciado (intervalo 5s).")
    while True:
        try:
            halt_flag = await historian.get_system_flag("halt_requested")
            if halt_flag == "true":
                logger.critical("Kill switch activado por solicitud remota vía API")
                await dispatcher.activate_kill_switch("CONFIRMAR")
                await historian.set_system_flag("halt_requested", "false")
                await historian.set_system_flag("system_halted",  "true")

            halted      = await historian.get_system_flag("system_halted")
            resume_flag = await historian.get_system_flag("resume_requested")
            if halted == "true" and resume_flag == "true":
                logger.critical("Sistema reactivado por solicitud remota vía API")
                await dispatcher.deactivate_kill_switch("CONFIRMAR")
                await historian.set_system_flag("resume_requested", "false")
                await historian.set_system_flag("system_halted",    "false")
        except Exception as e:
            logger.warning(f"Error en kill_switch_poller: {e}")
        await asyncio.sleep(_KILL_SWITCH_POLL_INTERVAL)


def _ks_task_done(task: asyncio.Task):
    """Callback para detectar fallas silenciosas del kill switch poller."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("kill_switch_poller cancelado limpiamente.")
        return
    if exc is not None:
        logger.critical(f"kill_switch_poller murió: {exc!r}", exc_info=exc)
    else:
        logger.warning("kill_switch_poller terminó sin excepción pero sin estar cancelado.")


_RECONCILE_POLL_INTERVAL = 300  # segundos (5 min)


async def _reconciliation_poller(historian: Historian, interval_sec: int = _RECONCILE_POLL_INTERVAL):
    """
    Cada `interval_sec` segundos reconcilia trades PENDING_NEW > 5 min con Alpaca.
    Cierra #H-6b: trades que quedaban huérfanos por status no actualizado.

    Resiliencia: errores transitorios se loggean y se reintenta en el próximo tick.
    El task solo muere por cancelación explícita.
    """
    logger.info(f"Reconciliation poller iniciado (cada {interval_sec}s).")
    while True:
        await asyncio.sleep(interval_sec)
        try:
            stats = await reconcile_pending(
                historian.pool, apply=True, max_age_minutes=5, verbose=False,
            )
            if stats["updates_applied"] > 0:
                logger.info(
                    f"Reconciliation: {stats['updates_applied']} trades actualizados "
                    f"({stats['filled']} FILLED, {stats['cancelled']} CANCELLED)."
                )
            else:
                logger.debug("Reconciliation: 0 actualizaciones (nada pendiente).")
        except asyncio.CancelledError:
            logger.info("Reconciliation poller cancelado.")
            raise
        except Exception as e:
            logger.error(f"Reconciliation falló: {e}", exc_info=True)


def _reconcile_task_done(task: asyncio.Task):
    """Callback para detectar fallas silenciosas del reconciliation poller."""
    if task.cancelled():
        logger.info("reconciliation_poller cancelado limpiamente.")
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"reconciliation_poller terminó con excepción: {exc!r}", exc_info=exc)


_EQUITY_SNAPSHOT_POLL_INTERVAL = 1800  # segundos (30 min)


async def _daily_equity_snapshot_poller(
    historian: Historian,
    dispatcher: Dispatcher,
    owner_id: uuid.UUID,
    interval_sec: int = _EQUITY_SNAPSHOT_POLL_INTERVAL,
):
    """
    Registra el snapshot EOD de equity una vez por día hábil, tras las 16:05 ET
    (cierre de mercado + margen para los EOD updates de Alpaca). Es la fuente
    persistente para los drawdown limits del portafolio (#GR-3): peak histórico
    que sobrevive reinicios y migración paper→live.

    Chequea cada `interval_sec`; si ya pasó 16:05 ET y no hay snapshot de hoy, lo
    registra (idempotente). Resiliente: errores se loggean y se reintenta.
    """
    logger.info(
        f"Daily equity snapshot poller iniciado (cada {interval_sec}s, EOD 16:05 ET)."
    )
    while True:
        await asyncio.sleep(interval_sec)
        try:
            now_et = datetime.now(tz=ZoneInfo(TIMEZONE))
            if (now_et.hour, now_et.minute) < (16, 5):
                continue  # mercado aún no cerró / EOD no listo
            if await historian.has_equity_snapshot_today(owner_id):
                continue  # ya registrado hoy
            equity = await asyncio.wait_for(
                asyncio.to_thread(dispatcher._get_account_equity), timeout=15.0,
            )
            await historian.record_daily_equity_snapshot(owner_id, equity)
            logger.info(f"Daily equity snapshot EOD registrado: equity={equity}")
        except asyncio.CancelledError:
            logger.info("Daily equity snapshot poller cancelado.")
            raise
        except Exception as e:
            logger.error(f"Daily equity snapshot falló: {e}", exc_info=True)


def _equity_snapshot_task_done(task: asyncio.Task):
    """Callback para detectar fallas silenciosas del equity snapshot poller."""
    if task.cancelled():
        logger.info("daily_equity_snapshot_poller cancelado limpiamente.")
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            f"daily_equity_snapshot_poller terminó con excepción: {exc!r}", exc_info=exc
        )


async def main():
    """Inicializa el sistema, arranca The Ear en background y entra al main loop."""
    system = await initialize()

    # The Ear corre su propio polling loop en paralelo (NewsAPI cada 15 min)
    ear_task = asyncio.create_task(
        system["the_ear"].start_polling(),
        name="the_ear_polling",
    )
    ear_task.add_done_callback(_ear_task_done)
    logger.info("The Ear polling iniciado en background.")

    # Kill switch poller — IPC con api.py vía system_state (#H-7)
    kill_switch_task = asyncio.create_task(
        _kill_switch_poller(system["historian"], system["dispatcher"]),
        name="kill_switch_poller",
    )
    kill_switch_task.add_done_callback(_ks_task_done)

    # Reconciliation poller — auto-reconcilia PENDING_NEW cada 5 min (#H-6b)
    reconcile_task = asyncio.create_task(
        _reconciliation_poller(system["historian"]),
        name="reconciliation_poller",
    )
    reconcile_task.add_done_callback(_reconcile_task_done)
    logger.info("Reconciliation poller iniciado en background.")

    # Daily equity snapshot poller — fuente persistente de drawdown EOD (#GR-3)
    equity_snapshot_task = asyncio.create_task(
        _daily_equity_snapshot_poller(
            system["historian"], system["dispatcher"], system["owner_id"],
        ),
        name="daily_equity_snapshot_poller",
    )
    equity_snapshot_task.add_done_callback(_equity_snapshot_task_done)
    logger.info("Daily equity snapshot poller iniciado en background.")

    try:
        await main_loop(system)
    finally:
        ear_task.cancel()
        try:
            await ear_task
        except asyncio.CancelledError:
            pass

        kill_switch_task.cancel()
        try:
            await kill_switch_task
        except asyncio.CancelledError:
            pass

        reconcile_task.cancel()
        try:
            await reconcile_task
        except asyncio.CancelledError:
            pass

        equity_snapshot_task.cancel()
        try:
            await equity_snapshot_task
        except asyncio.CancelledError:
            pass

        await system["historian"].close()
        logger.info("=== Sentinel v0.5 — Sistema cerrado limpiamente ===")


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt recibido — cerrando Sentinel.")
    except Exception as e:
        logger.critical(f"Error fatal en Sentinel: {e}", exc_info=True)
        raise
