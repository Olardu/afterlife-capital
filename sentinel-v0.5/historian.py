# historian.py
# Agente de memoria y feedback loop de Sentinel v0.5.
# Gestiona toda la persistencia en PostgreSQL: trades, signals, performance scores
# y eventos macro. Expone el feedback loop de decay al Dispatcher.
# Usa asyncpg para operaciones no bloqueantes dentro del grafo LangGraph.

import logging
import math
from typing import Optional
from uuid import UUID

import asyncpg

from config import (
    PERFORMANCE_DECAY_THRESHOLD,
    SHARPE_MINIMUM,
    WARMUP_TRADES_REQUIRED,
)

logger = logging.getLogger("sentinel.historian")


# Annualization factor para Sharpe sobre barras de 15 minutos.
# Equity market: 252 días hábiles × 26 barras/día (6.5h × 4 barras/hora) = 6552
# bars/year. El factor escala el Sharpe per-period a Sharpe anual estándar,
# que es la escala asumida por SHARPE_MINIMUM = 0.5 en config.py.
# Sin esto, el threshold se aplicaba contra Sharpe per-period y rechazaba
# estrategias razonables como decay (#TECHDEBT promovido).
_BARS_PER_TRADING_DAY = 26
_TRADING_DAYS_PER_YEAR = 252
_SHARPE_ANNUALIZATION_FACTOR = math.sqrt(_TRADING_DAYS_PER_YEAR * _BARS_PER_TRADING_DAY)


class Historian:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Inicializa el pool de conexiones asyncpg (min 2, max 10 conexiones).

        Timeouts:
            command_timeout=10  → cada query individual aborta a los 10s.
            timeout=5           → acquire connection del pool aborta a los 5s.
        Sin estos, una query colgada drena el pool y el sistema queda sin
        servicio en silencio (#H-3a).
        """
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=10,
                timeout=5,
            )
            logger.info("Pool PostgreSQL inicializado.")
        except Exception as e:
            logger.error(f"Error al conectar con PostgreSQL: {e}")
            raise

        # Asegurar que la tabla system_state existe (idempotente).
        # Es el canal IPC entre api.py y main.py para el kill switch (#H-7).
        # La migración 004 también crea esta tabla — este DDL es la red de
        # seguridad para entornos donde la migración no se aplicó manualmente.
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            for flag in ("halt_requested", "system_halted", "resume_requested"):
                await conn.execute(
                    """
                    INSERT INTO system_state (key, value) VALUES ($1, 'false')
                    ON CONFLICT (key) DO NOTHING
                    """,
                    flag,
                )

            # Asegurar email + role=ADMIN del owner (#H-1). La columna `email`
            # ya existe en schema.sql desde la creación de la DB (multi-tenant
            # base). Este UPDATE solo corre cuando el email persistido no
            # coincide con el del admin OAuth — idempotente.
            await conn.execute(
                """
                UPDATE users
                SET email = '***REMOVED-EMAIL***',
                    role  = 'ADMIN'
                WHERE username = 'roman'
                  AND (email IS DISTINCT FROM '***REMOVED-EMAIL***'
                       OR role IS DISTINCT FROM 'ADMIN')
                """
            )

    async def close(self):
        """Cierra el pool de conexiones limpiamente."""
        if self.pool:
            await self.pool.close()
            logger.info("Pool PostgreSQL cerrado.")

    async def record_signal(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str,
        signal_type: str,
        price_at_signal: float,
    ) -> UUID:
        """
        Inserta una señal en la tabla signals.

        Returns:
            signal_id del registro insertado.
        """
        sql = """
            INSERT INTO signals (sentinel_id, owner_id, ticker, signal_type, price_at_signal)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING signal_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, sentinel_id, owner_id, ticker, signal_type, price_at_signal)
            signal_id = row["signal_id"]
            logger.info(f"Signal registrado: {signal_id} | {ticker} {signal_type} @ {price_at_signal}")
            return signal_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error al registrar signal ({ticker} {signal_type}): {e}")
            raise

    async def record_trade(
        self,
        signal_id: Optional[UUID],
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str,
        side: str,
        qty: float,
        filled_price: Optional[float],
        slippage: Optional[float],
        status: str,
        order_id: Optional[str] = None,
    ) -> UUID:
        """
        Inserta un trade en la tabla trades.

        signal_id puede ser None para trades manuales sin señal previa.
        order_id (str) es el identificador retornado por Alpaca al submit;
        se persiste para que el background task de limit orders pueda
        reconciliar el trade vía update_trade_status(order_id=...). (#H-6)

        Returns:
            trade_id del registro insertado.
        """
        sql = """
            INSERT INTO trades
                (signal_id, sentinel_id, owner_id, ticker, side, qty,
                 filled_price, slippage, status, order_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING trade_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql,
                    signal_id, sentinel_id, owner_id,
                    ticker, side, qty, filled_price, slippage, status, order_id,
                )
            trade_id = row["trade_id"]
            logger.info(f"Trade registrado: {trade_id} | {ticker} {side} qty={qty} status={status}")
            return trade_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error al registrar trade ({ticker} {side}): {e}")
            raise

    async def update_trade_status(
        self,
        *,
        trade_id: Optional[UUID] = None,
        order_id: Optional[str] = None,
        status: str,
        filled_price: Optional[float] = None,
        slippage: Optional[float] = None,
    ):
        """
        Actualiza el status de un trade PENDING → FILLED o CANCELLED.

        Identificación: pasar trade_id (UUID de la tabla) O order_id (string
        de Alpaca, persistido en la columna trades.order_id desde la migración
        003). Exactamente uno de los dos. (#H-6)

        Si status es FILLED y no se provee slippage, lo calcula como:
            filled_price - price_at_signal (del signal original asociado).
        Si el trade no tiene signal_id asociado, slippage queda en None.
        """
        if trade_id is None and order_id is None:
            raise ValueError("Debe proveerse trade_id u order_id")
        if trade_id is not None and order_id is not None:
            raise ValueError("Debe proveerse SOLO uno: trade_id O order_id, no ambos")

        # Identificador a usar en el WHERE (solo uno está poblado por las
        # validaciones de arriba). El nombre de columna se interpola en el SQL
        # — es seguro porque el valor está hardcoded acá, no viene de input.
        if trade_id is not None:
            where_col: str = "trade_id"
            where_value: object = trade_id
            id_label = f"trade_id={trade_id}"
        else:
            where_col = "order_id"
            where_value = order_id
            id_label = f"order_id={order_id}"

        try:
            async with self.pool.acquire() as conn:
                if status == "FILLED" and filled_price is not None and slippage is None:
                    row = await conn.fetchrow(
                        f"""
                        SELECT s.price_at_signal
                        FROM trades t
                        LEFT JOIN signals s ON t.signal_id = s.signal_id
                        WHERE t.{where_col} = $1
                        """,
                        where_value,
                    )
                    if row and row["price_at_signal"] is not None:
                        slippage = filled_price - float(row["price_at_signal"])

                await conn.execute(
                    f"""
                    UPDATE trades
                    SET status = $1, filled_price = $2, slippage = $3
                    WHERE {where_col} = $4
                    """,
                    status, filled_price, slippage, where_value,
                )
            logger.info(
                f"Trade {id_label} → {status} | filled={filled_price} slippage={slippage}"
            )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al actualizar trade {id_label}: {e}")
            raise

    async def calculate_performance(self, sentinel_id: UUID, ticker: str) -> dict:
        """
        Calcula métricas de performance para el par (sentinel_id, ticker)
        sobre trades FILLED, pareando ciclos BUY→SELL en orden FIFO.

        Un ciclo ganador: SELL.filled_price > BUY.filled_price.
        Sharpe = mean(returns) / std(returns) sobre los retornos de cada ciclo.
        Requiere al menos 2 ciclos para calcular std; con 1 retorna sharpe=0.

        Returns:
            dict con win_rate, sharpe_ratio y total_trades.
        """
        sql = """
            SELECT side, filled_price, created_at
            FROM trades
            WHERE sentinel_id = $1
              AND ticker = $2
              AND status = 'FILLED'
              AND filled_price IS NOT NULL
            ORDER BY created_at ASC
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, sentinel_id, ticker)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener trades para performance ({sentinel_id}, {ticker}): {e}")
            raise

        # LIMITACIÓN v0.5: el pareo FIFO asume ciclos BUY→SELL alternados.
        # Si un Sentinel emite dos BUYs sin SELL intermedio, el segundo BUY
        # se despareja. Aceptable porque los Sentinels heredan la protección
        # last_signal del v0.0 que previene señales duplicadas consecutivas.
        buys  = [r for r in rows if r["side"] == "BUY"]
        sells = [r for r in rows if r["side"] == "SELL"]
        pairs = list(zip(buys, sells))
        total_trades = len(pairs)

        if total_trades == 0:
            return {"win_rate": 0.0, "sharpe_ratio": 0.0, "total_trades": 0}

        returns = [
            (float(sell["filled_price"]) - float(buy["filled_price"])) / float(buy["filled_price"])
            for buy, sell in pairs
        ]
        win_rate = sum(1 for r in returns if r > 0) / total_trades

        if total_trades < 2:
            sharpe_ratio = 0.0
        else:
            mean_r   = sum(returns) / total_trades
            variance = sum((r - mean_r) ** 2 for r in returns) / (total_trades - 1)
            std_r    = math.sqrt(variance) if variance > 0 else 0.0
            # Annualizar: per-period × sqrt(periods/year). Asume returns iid
            # — aproximación estándar, suficiente para gating de decay.
            sharpe_ratio = (mean_r / std_r) * _SHARPE_ANNUALIZATION_FACTOR if std_r > 0 else 0.0

        logger.debug(
            f"Performance ({sentinel_id}, {ticker}): "
            f"win_rate={win_rate:.4f} sharpe={sharpe_ratio:.4f} trades={total_trades}"
        )
        return {"win_rate": win_rate, "sharpe_ratio": sharpe_ratio, "total_trades": total_trades}

    async def evaluate_decay(self, sentinel_id: UUID, ticker: str) -> bool:
        """
        Evalúa si el par (sentinel_id, ticker) está en performance decay.

        Warm-Up Protocol: si total_trades < WARMUP_TRADES_REQUIRED retorna False
        sin insertar nada — no hay historia suficiente para juzgar rotación.

        Decay se marca TRUE si:
            win_rate < PERFORMANCE_DECAY_THRESHOLD  O  sharpe_ratio < SHARPE_MINIMUM

        Inserta o actualiza el registro en performance_scores.
        Requiere UNIQUE (sentinel_id, ticker) en esa tabla para el upsert.

        Returns:
            True si hay decay, False si no.
        """
        metrics      = await self.calculate_performance(sentinel_id, ticker)
        total_trades = metrics["total_trades"]

        if total_trades < WARMUP_TRADES_REQUIRED:
            logger.info(
                f"Warm-Up activo ({sentinel_id}, {ticker}): "
                f"{total_trades}/{WARMUP_TRADES_REQUIRED} trades. Decay no evaluado."
            )
            return False

        win_rate     = metrics["win_rate"]
        sharpe_ratio = metrics["sharpe_ratio"]
        decay        = win_rate < PERFORMANCE_DECAY_THRESHOLD or sharpe_ratio < SHARPE_MINIMUM

        upsert_sql = """
            INSERT INTO performance_scores
                (sentinel_id, ticker, sharpe_ratio, win_rate, total_trades, performance_decay)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (sentinel_id, ticker) DO UPDATE SET
                sharpe_ratio      = EXCLUDED.sharpe_ratio,
                win_rate          = EXCLUDED.win_rate,
                total_trades      = EXCLUDED.total_trades,
                performance_decay = EXCLUDED.performance_decay,
                calculated_at     = NOW()
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    upsert_sql,
                    sentinel_id, ticker, sharpe_ratio, win_rate, total_trades, decay,
                )
            logger.info(
                f"Decay evaluado ({sentinel_id}, {ticker}): "
                f"decay={decay} | win_rate={win_rate:.4f} sharpe={sharpe_ratio:.4f}"
            )
            return decay
        except asyncpg.PostgresError as e:
            logger.error(f"Error al registrar performance_scores ({sentinel_id}, {ticker}): {e}")
            raise

    async def get_active_sentinels(self, owner_id: UUID) -> list[dict]:
        """
        Retorna los Sentinels activos del owner con sus tickers asignados.
        Usado por main.py al inicializar y por el Dispatcher en run_cycle
        para evaluar decay sobre la fuente de verdad (DB).

        Returns:
            Lista de {sentinel_id, name, strategy_type, tickers: list[str]}.
            tickers contiene solo los tickers activos (sentinel_tickers.is_active = TRUE).
            Sentinels sin tickers asignados retornan tickers=[].
        """
        sql = """
            SELECT
                s.sentinel_id,
                s.name,
                s.strategy_type,
                COALESCE(
                    array_agg(st.ticker ORDER BY st.ticker)
                        FILTER (WHERE st.ticker IS NOT NULL AND st.is_active = TRUE),
                    ARRAY[]::VARCHAR[]
                ) AS tickers
            FROM sentinels s
            LEFT JOIN sentinel_tickers st ON s.sentinel_id = st.sentinel_id
            WHERE s.owner_id = $1 AND s.is_active = TRUE
            GROUP BY s.sentinel_id, s.name, s.strategy_type
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, owner_id)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener sentinels activos (owner={owner_id}): {e}")
            raise

    async def get_sentinel_tickers(self, sentinel_id: UUID) -> list[str]:
        """
        Retorna los tickers activos asignados a un Sentinel.
        Útil para refrescar la lista de tickers de un Sentinel ya instanciado
        sin recargar todos los Sentinels del owner.

        Returns:
            Lista de strings con los tickers activos.
        """
        sql = """
            SELECT ticker
            FROM sentinel_tickers
            WHERE sentinel_id = $1 AND is_active = TRUE
            ORDER BY ticker
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, sentinel_id)
            return [r["ticker"] for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener tickers del sentinel {sentinel_id}: {e}")
            raise

    async def get_sentinel_scores(self, owner_id: UUID) -> list[dict]:
        """
        Retorna performance_scores de todos los Sentinels del owner,
        ordenados por sharpe_ratio DESC. El Dispatcher usa este ranking
        para distribuir capital con Half-Kelly.

        Sentinels sin score aún no aparecen en el resultado.
        """
        sql = """
            SELECT
                ps.score_id,
                ps.sentinel_id,
                s.name          AS sentinel_name,
                ps.ticker,
                ps.sharpe_ratio,
                ps.win_rate,
                ps.total_trades,
                ps.performance_decay,
                ps.calculated_at
            FROM performance_scores ps
            JOIN sentinels s ON ps.sentinel_id = s.sentinel_id
            WHERE s.owner_id = $1
            ORDER BY ps.sharpe_ratio DESC NULLS LAST
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, owner_id)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener sentinel scores (owner={owner_id}): {e}")
            raise

    async def get_trade_history(
        self,
        sentinel_id: UUID,
        ticker: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Retorna historial de trades para un Sentinel ordenado por created_at DESC.
        Filtra por ticker si se provee.
        """
        try:
            async with self.pool.acquire() as conn:
                if ticker:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM trades
                        WHERE sentinel_id = $1 AND ticker = $2
                        ORDER BY created_at DESC
                        LIMIT $3
                        """,
                        sentinel_id, ticker, limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM trades
                        WHERE sentinel_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2
                        """,
                        sentinel_id, limit,
                    )
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener historial ({sentinel_id}, ticker={ticker}): {e}")
            raise

    async def record_macro_event(
        self,
        risk_score: float,
        vix_level: Optional[float],
        spy_change_15min: Optional[float],
        circuit_breaker_triggered: bool,
    ) -> UUID:
        """
        Inserta un registro de estado macro en macro_events.
        Llamado por The Ear cada 15 minutos y al activar el Circuit Breaker.

        Returns:
            event_id del registro insertado.
        """
        sql = """
            INSERT INTO macro_events
                (risk_score, vix_level, spy_change_15min, circuit_breaker_triggered)
            VALUES ($1, $2, $3, $4)
            RETURNING event_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql, risk_score, vix_level, spy_change_15min, circuit_breaker_triggered
                )
            event_id = row["event_id"]
            logger.info(
                f"Macro event: {event_id} | "
                f"risk={risk_score} vix={vix_level} "
                f"spy_15m={spy_change_15min} circuit_breaker={circuit_breaker_triggered}"
            )
            return event_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error al registrar macro event: {e}")
            raise

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Busca un usuario por email. Usado por el callback OAuth para validar
        que el email autenticado por Google está registrado como ADMIN o
        VIEWER en la DB antes de emitir cookie de sesión (#H-1).

        Returns:
            dict {user_id, username, email, role} o None si no existe.
        """
        sql = """
            SELECT user_id, username, email, role
            FROM users
            WHERE email = $1
            LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, email)
            return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logger.error(f"Error al buscar usuario por email ({email}): {e}")
            raise

    async def get_system_flag(self, key: str) -> Optional[str]:
        """
        Lee un flag de system_state. Retorna el value o None si la key no existe.

        Usado por el kill switch poller en main.py para detectar pedidos de
        halt remoto vía API (#H-7).
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT value FROM system_state WHERE key = $1",
                    key,
                )
            return row["value"] if row else None
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer system_state[{key}]: {e}")
            raise

    async def set_system_flag(self, key: str, value: str) -> None:
        """
        Upsert de un flag en system_state. Actualiza updated_at automáticamente.

        Usado por api.py (endpoints halt/resume) y por el poller de main.py
        (para resetear el flag tras consumir el evento) (#H-7).
        """
        sql = """
            INSERT INTO system_state (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET
                value      = EXCLUDED.value,
                updated_at = NOW()
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, key, value)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al escribir system_state[{key}]={value}: {e}")
            raise
