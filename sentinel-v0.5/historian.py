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
    ) -> UUID:
        """
        Inserta un trade en la tabla trades.

        signal_id puede ser None para trades manuales sin señal previa.

        Returns:
            trade_id del registro insertado.
        """
        sql = """
            INSERT INTO trades
                (signal_id, sentinel_id, owner_id, ticker, side, qty,
                 filled_price, slippage, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING trade_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql,
                    signal_id, sentinel_id, owner_id,
                    ticker, side, qty, filled_price, slippage, status,
                )
            trade_id = row["trade_id"]
            logger.info(f"Trade registrado: {trade_id} | {ticker} {side} qty={qty} status={status}")
            return trade_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error al registrar trade ({ticker} {side}): {e}")
            raise

    async def update_trade_status(
        self,
        trade_id: UUID,
        status: str,
        filled_price: Optional[float] = None,
        slippage: Optional[float] = None,
    ):
        """
        Actualiza el status de un trade PENDING → FILLED o CANCELLED.

        Si status es FILLED y no se provee slippage, lo calcula como:
            filled_price - price_at_signal (del signal original asociado).
        Si el trade no tiene signal_id asociado, slippage queda en None.
        """
        try:
            async with self.pool.acquire() as conn:
                if status == "FILLED" and filled_price is not None and slippage is None:
                    row = await conn.fetchrow(
                        """
                        SELECT s.price_at_signal
                        FROM trades t
                        LEFT JOIN signals s ON t.signal_id = s.signal_id
                        WHERE t.trade_id = $1
                        """,
                        trade_id,
                    )
                    if row and row["price_at_signal"] is not None:
                        slippage = filled_price - float(row["price_at_signal"])

                await conn.execute(
                    """
                    UPDATE trades
                    SET status = $1, filled_price = $2, slippage = $3
                    WHERE trade_id = $4
                    """,
                    status, filled_price, slippage, trade_id,
                )
            logger.info(
                f"Trade {trade_id} → {status} | filled={filled_price} slippage={slippage}"
            )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al actualizar trade {trade_id}: {e}")
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
            sharpe_ratio = mean_r / std_r if std_r > 0 else 0.0

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
