# historian.py
# Agente de memoria y feedback loop de Sentinel v0.5.
# Gestiona toda la persistencia en PostgreSQL: trades, signals, performance scores
# y eventos macro. Expone el feedback loop de decay al Dispatcher.
# Usa asyncpg para operaciones no bloqueantes dentro del grafo LangGraph.

import json
import logging
import math
from datetime import datetime
from decimal import Decimal
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


# Email del owner del sistema — protegido contra eliminación desde el panel
# admin. Coincide con el UPDATE idempotente de connect() y con la cuenta
# Google que tiene acceso ADMIN garantizado.
_OWNER_EMAIL = "***REMOVED-EMAIL***"


# =============================================================================
# Índice de secciones (§) — buscables con "§ N":
#   § 1  — Imports y configuración (arriba de este bloque)
#   § 2  — Conexión y schema (__init__, connect, close)
#   § 3  — Signals y trades (record_signal/trade, update_trade_status)
#   § 4  — Performance y decay (calculate_performance, evaluate_decay)
#   § 5  — Sentinels y tickers (get_active_sentinels, get_sentinel_tickers)
#   § 6  — Helpers VIX / idle / drawdown (get_avg_vix, get_last_trade_timestamp, get_ticker_added_at)
#   § 7  — Scores e historia de trades (get_sentinel_scores, get_trade_history)
#   § 8  — Macro events (record_macro_event)
#   § 9  — Usuarios (get_user_by_email, list_users, add_user, remove_user)
#   § 10 — System flags (get_system_flag, set_system_flag)
#   § 11 — API keys (list/get/upsert/delete)
#   § 12 — Warning status (get_sentinels_with_warning, update_warning_status)
#   § 13 — Universe Selector: candidatos y rotaciones (pending_candidates, rotation_decisions, failed_tickers)
#   § 14 — Macro context (get_recent_macro_events, get_recent_macro_context)
# =============================================================================


class Historian:
    # ═══════════════════════════ § 2 — Conexión y schema ═══════════════════════════
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

            # Asegurar que trades.status soporta status largos de Alpaca (#FIX-005).
            # El primer día de paper trading reveló que "PENDING_NEW" (11 chars)
            # rompe el VARCHAR(10) original. Ampliamos a VARCHAR(32) y relajamos
            # el CHECK constraint que solo admitía FILLED|CANCELLED|PENDING.
            # Idempotente: solo amplía si está corto, solo dropea si existe.
            await conn.execute("""
                DO $$
                BEGIN
                    IF (SELECT character_maximum_length
                          FROM information_schema.columns
                         WHERE table_name = 'trades'
                           AND column_name = 'status') < 32 THEN
                        ALTER TABLE trades ALTER COLUMN status TYPE VARCHAR(32);
                    END IF;
                END $$;
            """)
            await conn.execute(
                "ALTER TABLE trades DROP CONSTRAINT IF EXISTS trades_status_check"
            )

            # Asegurar que macro_events tiene la columna news_titles (#FIX-007).
            # The Ear ahora persiste los TOP 5 titulares que más contribuyeron
            # al risk_score para auditoría posterior. Idempotente.
            await conn.execute(
                "ALTER TABLE macro_events "
                "ADD COLUMN IF NOT EXISTS news_titles JSONB NOT NULL DEFAULT '[]'::jsonb"
            )

            # Asegurar que la tabla api_keys existe (#FIX-008). El panel admin
            # gestiona credenciales encriptadas con Fernet — el bot sigue
            # leyendo desde .env hasta que la sincronización automática esté
            # validada. Idempotente.
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
                    service_name    TEXT         NOT NULL UNIQUE,
                    encrypted_value TEXT         NOT NULL,
                    description     TEXT,
                    last_rotated_at TIMESTAMP    NOT NULL DEFAULT NOW(),
                    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
                    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_keys_service_name "
                "ON api_keys(service_name)"
            )

            # =================================================================
            # UNIVERSE SELECTION (#UNIVERSE-SELECTION) — migraciones 008-010.
            # Tres recursos relacionados:
            #   - rotation_decisions: log inmutable de cada decisión de Claude.
            #   - pending_candidates: Watchlist Anticipada por Sentinel.
            #   - performance_scores.warning_status: pre-decay marker.
            # Todos idempotentes; el orden importa porque pending_candidates
            # tiene FK a rotation_decisions.
            # =================================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rotation_decisions (
                    decision_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
                    sentinel_id          UUID         NOT NULL REFERENCES sentinels(sentinel_id),
                    owner_id             UUID         NOT NULL REFERENCES users(user_id),
                    triggered_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
                    trigger_reason       TEXT         NOT NULL,
                    old_ticker           TEXT         NOT NULL,
                    old_win_rate         DOUBLE PRECISION,
                    old_sharpe_ratio     DOUBLE PRECISION,
                    old_total_trades     INTEGER,
                    new_ticker           TEXT,
                    candidates_proposed  JSONB        NOT NULL DEFAULT '[]'::jsonb,
                    claude_reasoning     TEXT,
                    claude_confidence    DOUBLE PRECISION,
                    claude_model         TEXT,
                    claude_input_tokens  INTEGER,
                    claude_output_tokens INTEGER,
                    claude_cost_usd      DOUBLE PRECISION,
                    status               TEXT         NOT NULL DEFAULT 'pending',
                    executed_at          TIMESTAMP,
                    rolled_back_at       TIMESTAMP,
                    rolled_back_by       TEXT,
                    new_ticker_trades_after_30d  INTEGER,
                    new_ticker_winrate_after_30d DOUBLE PRECISION,
                    new_ticker_sharpe_after_30d  DOUBLE PRECISION,
                    notes                TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rotation_decisions_sentinel "
                "ON rotation_decisions(sentinel_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rotation_decisions_status "
                "ON rotation_decisions(status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rotation_decisions_triggered "
                "ON rotation_decisions(triggered_at DESC)"
            )

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_candidates (
                    candidate_id     UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
                    sentinel_id      UUID      NOT NULL REFERENCES sentinels(sentinel_id),
                    proposed_ticker  TEXT      NOT NULL,
                    proposed_at      TIMESTAMP NOT NULL DEFAULT NOW(),
                    expires_at       TIMESTAMP NOT NULL,
                    decision_id      UUID      REFERENCES rotation_decisions(decision_id),
                    status           TEXT      NOT NULL DEFAULT 'watching'
                )
            """)
            # Solo un candidato 'watching' por Sentinel — índice parcial UNIQUE.
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_candidates_one_active "
                "ON pending_candidates(sentinel_id) WHERE status = 'watching'"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_candidates_status "
                "ON pending_candidates(status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_candidates_expires_at "
                "ON pending_candidates(expires_at)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_candidates_sentinel "
                "ON pending_candidates(sentinel_id)"
            )

            await conn.execute(
                "ALTER TABLE performance_scores "
                "ADD COLUMN IF NOT EXISTS warning_status BOOLEAN NOT NULL DEFAULT FALSE"
            )
            await conn.execute(
                "ALTER TABLE performance_scores "
                "ADD COLUMN IF NOT EXISTS warning_detected_at TIMESTAMP"
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

    # ═══════════════════════════ § 3 — Signals y trades ═══════════════════════════
    async def record_signal(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str,
        signal_type: str,
        price_at_signal: Decimal,
    ) -> UUID:
        """
        Inserta una señal en la tabla signals.

        Returns:
            signal_id del registro insertado.
        """
        # Precio monetario → Decimal en todo el pipeline (#H-4). Conversión defensiva
        # (acepta callers que aún pasen float durante la migración gradual).
        price_at_signal = Decimal(str(price_at_signal))

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
        qty: Decimal,
        filled_price: Optional[Decimal],
        slippage: Optional[Decimal],
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
        # qty/precios monetarios → Decimal (#H-4). Conversión defensiva (callers float ok).
        qty = Decimal(str(qty))
        filled_price = Decimal(str(filled_price)) if filled_price is not None else None
        slippage = Decimal(str(slippage)) if slippage is not None else None

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
        filled_price: Optional[Decimal] = None,
        slippage: Optional[Decimal] = None,
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
        # Precios monetarios → Decimal (#H-4). Conversión defensiva (callers float ok).
        filled_price = Decimal(str(filled_price)) if filled_price is not None else None
        slippage = Decimal(str(slippage)) if slippage is not None else None

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
                        # asyncpg devuelve Decimal para columnas NUMERIC → resta exacta (#H-4)
                        slippage = filled_price - row["price_at_signal"]

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

    # ═══════════════════════════ § 4 — Performance y decay ═══════════════════════════
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

        # Cálculo en Decimal (precios monetarios, #H-4) y conversión a float al final:
        # `returns` es un ratio adimensional usado en sharpe → float OK (§8.6).
        returns = [
            float((sell["filled_price"] - buy["filled_price"]) / buy["filled_price"])
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

    # Mínimo de round trips para escribir scores parciales (sin evaluar decay).
    # Con 2+ trades hay suficientes datos para un Sharpe y win_rate indicativos
    # que alimentan al Dispatcher y Dashboard, aunque no sean definitivos.
    _PARTIAL_SCORE_MIN_TRADES = 2

    async def evaluate_decay(self, sentinel_id: UUID, ticker: str) -> bool:
        """
        Evalúa si el par (sentinel_id, ticker) está en performance decay.

        Scores Parciales: si total_trades >= _PARTIAL_SCORE_MIN_TRADES pero
        < WARMUP_TRADES_REQUIRED, se escriben scores a performance_scores con
        performance_decay = False (no se juzga rotación aún). Esto permite que
        Dispatcher y Dashboard tengan datos antes de alcanzar warmup completo.

        Warm-Up Protocol: solo con total_trades >= WARMUP_TRADES_REQUIRED se
        evalúa decay real (win_rate y sharpe vs thresholds).

        Decay se marca TRUE si:
            win_rate < PERFORMANCE_DECAY_THRESHOLD  O  sharpe_ratio < SHARPE_MINIMUM

        Inserta o actualiza el registro en performance_scores.
        Requiere UNIQUE (sentinel_id, ticker) en esa tabla para el upsert.

        Returns:
            True si hay decay, False si no.
        """
        metrics      = await self.calculate_performance(sentinel_id, ticker)
        total_trades = metrics["total_trades"]

        if total_trades < self._PARTIAL_SCORE_MIN_TRADES:
            logger.info(
                f"Warm-Up activo ({sentinel_id}, {ticker}): "
                f"{total_trades}/{self._PARTIAL_SCORE_MIN_TRADES} trades. "
                f"Sin datos suficientes para scores parciales."
            )
            return False

        win_rate     = metrics["win_rate"]
        sharpe_ratio = metrics["sharpe_ratio"]

        # Solo evaluar decay si alcanzó warmup completo
        if total_trades >= WARMUP_TRADES_REQUIRED:
            decay = win_rate < PERFORMANCE_DECAY_THRESHOLD or sharpe_ratio < SHARPE_MINIMUM
        else:
            # Scores parciales: escribir métricas pero no juzgar decay
            decay = False
            logger.info(
                f"Scores parciales ({sentinel_id}, {ticker}): "
                f"{total_trades}/{WARMUP_TRADES_REQUIRED} trades. "
                f"Escribiendo scores sin evaluar decay."
            )

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

    # ═══════════════════════════ § 5 — Sentinels y tickers ═══════════════════════════
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

    # -- Helpers del trigger idle_timeout (#UNIVERSE-IDLE) --------------------

    # ═══════════════════════════ § 6 — Helpers VIX / idle / drawdown ═══════════════════════════
    async def get_avg_vix(self, days: int) -> Optional[float]:
        """
        Promedio de macro_events.vix_level en los últimos `days` días. Usado por
        el guard de mercado plano de idle_timeout. Retorna None si no hay datos
        de VIX en la ventana (o ante error de DB — fail-safe sin crashear).
        """
        sql = """
            SELECT AVG(vix_level)::float8
            FROM macro_events
            WHERE created_at >= NOW() - make_interval(days => $1)
              AND vix_level IS NOT NULL
        """
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(sql, days)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al calcular VIX promedio ({days}d): {e}")
            return None

    async def get_last_trade_timestamp(
        self, sentinel_id: UUID, ticker: str,
    ) -> Optional[datetime]:
        """
        created_at del último trade FILLED de (sentinel_id, ticker), o None si
        ese ticker nunca tuvo un trade FILLED. Mide inactividad para
        idle_timeout. Timestamp naive en hora local del server.
        """
        sql = """
            SELECT MAX(created_at)
            FROM trades
            WHERE sentinel_id = $1 AND ticker = $2 AND status = 'FILLED'
        """
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(sql, sentinel_id, ticker)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener último trade ({sentinel_id}/{ticker}): {e}")
            return None

    async def get_ticker_added_at(
        self, sentinel_id: UUID, ticker: str,
    ) -> Optional[datetime]:
        """
        assigned_at del ticker activo en sentinel_tickers, o None si no está
        asignado/activo. idle_timeout lo usa para no rotar tickers recién
        agregados que aún no tuvieron tiempo de operar.
        """
        sql = """
            SELECT assigned_at
            FROM sentinel_tickers
            WHERE sentinel_id = $1 AND ticker = $2 AND is_active = TRUE
        """
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(sql, sentinel_id, ticker)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al obtener assigned_at ({sentinel_id}/{ticker}): {e}")
            return None

    # ═══════════════════════════ § 7 — Scores e historia de trades ═══════════════════════════
    async def get_sentinel_scores(self, owner_id: UUID) -> list[dict]:
        """
        Retorna performance_scores de todos los Sentinels del owner,
        ordenados por sharpe_ratio DESC. El Dispatcher usa este ranking
        para distribuir capital con Sharpe-weighted Half-Kelly.

        Filtra por sentinel_tickers.is_active = TRUE: scores de tickers ya
        rotados (zombies) se ignoran. Sin este filtro, evaluate_decay deja
        de actualizar scores zombies pero sus filas viejas siguen en DB,
        haciendo que el Universe Selector vuelva a verlos como "en decay"
        cada ciclo y dispare rotaciones repetidas (bug observado en Mantis
        el 2026-05-08: 23 rotaciones en 6h sobre TSLA y SPY ya rotados).

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
            JOIN sentinel_tickers st
              ON st.sentinel_id = ps.sentinel_id AND st.ticker = ps.ticker
            WHERE s.owner_id = $1 AND st.is_active = TRUE
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

    # ═══════════════════════════ § 8 — Macro events ═══════════════════════════
    async def record_macro_event(
        self,
        risk_score: float,
        vix_level: Optional[float],
        spy_change_15min: Optional[float],
        circuit_breaker_triggered: bool,
        news_titles: Optional[list[dict]] = None,
    ) -> UUID:
        """
        Inserta un registro de estado macro en macro_events.
        Llamado por The Ear cada 15 minutos y al activar el Circuit Breaker.

        news_titles: lista de dicts con los titulares que más contribuyeron
        al risk_score actual (#FIX-007). Cada dict tiene la forma
        {title, source, published_at, matched_keywords}. Si None, se persiste
        []. Sirve para auditar por qué se redujo el trading en un momento dado.

        Returns:
            event_id del registro insertado.
        """
        # Serialización JSON para JSONB. asyncpg acepta string JSON o dict;
        # forzamos string para ser explícitos sobre el contenido persistido.
        titles_json = json.dumps(news_titles or [], ensure_ascii=False)

        sql = """
            INSERT INTO macro_events
                (risk_score, vix_level, spy_change_15min,
                 circuit_breaker_triggered, news_titles)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING event_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql, risk_score, vix_level, spy_change_15min,
                    circuit_breaker_triggered, titles_json,
                )
            event_id = row["event_id"]
            logger.info(
                f"Macro event: {event_id} | "
                f"risk={risk_score} vix={vix_level} "
                f"spy_15m={spy_change_15min} circuit_breaker={circuit_breaker_triggered} "
                f"titles={len(news_titles or [])}"
            )
            return event_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error al registrar macro event: {e}")
            raise

    # ═══════════════════════════ § 9 — Usuarios ═══════════════════════════
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

    async def list_users(self) -> list[dict]:
        """
        Lista todos los usuarios para el panel admin. Ordenados por created_at
        ascendente (el owner aparece primero).
        """
        sql = """
            SELECT user_id, username, email, role, created_at
            FROM users
            ORDER BY created_at ASC
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar usuarios: {e}")
            raise

    async def add_user(self, email: str, role: str = "VIEWER") -> dict:
        """
        Inserta un usuario nuevo. El username se deriva del local part del
        email; si colisiona con uno existente (UNIQUE) le agregamos un sufijo
        numérico. Retorna el dict del registro creado.

        Raises:
            ValueError si el email ya existe o el role es inválido.
        """
        if role not in ("ADMIN", "VIEWER"):
            raise ValueError(f"role inválido: {role!r}")
        email = email.strip().lower()
        if not email or "@" not in email:
            raise ValueError(f"email inválido: {email!r}")

        # Generar username único a partir del local part del email.
        base = email.split("@", 1)[0][:50] or "user"
        username = base
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    suffix = 1
                    while await conn.fetchval(
                        "SELECT 1 FROM users WHERE username = $1", username,
                    ):
                        suffix += 1
                        candidate = f"{base[:46]}_{suffix}"
                        username = candidate

                    try:
                        row = await conn.fetchrow(
                            """
                            INSERT INTO users (username, email, role)
                            VALUES ($1, $2, $3)
                            RETURNING user_id, username, email, role, created_at
                            """,
                            username, email, role,
                        )
                    except asyncpg.UniqueViolationError as e:
                        # Email duplicado (la unicidad de username ya la cubrimos arriba)
                        raise ValueError("email_exists") from e
            logger.info(f"Usuario creado: {email} ({role}) | username={username}")
            return dict(row)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al crear usuario ({email}, {role}): {e}")
            raise

    async def remove_user(self, user_id: str) -> bool:
        """
        Elimina un usuario. Retorna True si la fila fue eliminada, False si
        no existía. NO permite eliminar al owner del sistema (***REMOVED-EMAIL***).

        Raises:
            ValueError("cannot_remove_owner") si se intenta eliminar al owner.
        """
        try:
            uid = UUID(user_id) if not isinstance(user_id, UUID) else user_id
        except (ValueError, AttributeError):
            raise ValueError(f"user_id inválido: {user_id!r}")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT email FROM users WHERE user_id = $1", uid,
                )
                if row is None:
                    return False
                if (row["email"] or "").lower() == _OWNER_EMAIL:
                    raise ValueError("cannot_remove_owner")
                result = await conn.execute(
                    "DELETE FROM users WHERE user_id = $1", uid,
                )
            # asyncpg devuelve "DELETE n" — extraemos n
            deleted = result.startswith("DELETE ") and result.split()[-1] != "0"
            if deleted:
                logger.info(f"Usuario eliminado: user_id={uid} email={row['email']}")
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error al eliminar usuario {user_id}: {e}")
            raise

    # ═══════════════════════════ § 10 — System flags ═══════════════════════════
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

    # =========================================================================
    # API KEYS (#FIX-008) — gestión de credenciales encriptadas para panel admin
    # Las keys se persisten encriptadas con Fernet (crypto_utils.encrypt). El
    # listado público devuelve valores enmascarados; reveal requiere ADMIN
    # explícito. El bot sigue leyendo desde .env — la sincronización
    # automática es trabajo de una sesión futura.
    # =========================================================================

    # ═══════════════════════════ § 11 — API keys ═══════════════════════════
    async def list_api_keys(self) -> list[dict]:
        """
        Lista las API keys gestionadas con su valor enmascarado
        (primeros 4 + **** + últimos 4 chars del valor desencriptado).
        NO devuelve el valor en claro.

        Returns:
            list de {key_id, service_name, masked_value, description,
                     last_rotated_at, created_at, updated_at}.
        """
        # Imports locales: crypto_utils requiere MASTER_ENCRYPTION_KEY al evaluar
        # _get_fernet(); importarlo arriba haría que cualquier módulo que
        # importe historian.py revente al startup si .env no tiene la key.
        from crypto_utils import decrypt, mask

        sql = """
            SELECT key_id, service_name, encrypted_value, description,
                   last_rotated_at, created_at, updated_at
            FROM api_keys
            ORDER BY service_name ASC
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql)
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar api_keys: {e}")
            raise

        result: list[dict] = []
        for r in rows:
            try:
                plaintext = decrypt(r["encrypted_value"])
                masked    = mask(plaintext)
            except Exception as e:
                # Si una key no se puede desencriptar (master key cambió,
                # ciphertext corrupto), no rompemos el listado entero —
                # marcamos esa fila como UNAVAILABLE para que el admin
                # pueda al menos verla y rotarla.
                logger.warning(
                    f"No pudo desencriptarse api_keys.service_name={r['service_name']}: {e}"
                )
                masked = "<UNAVAILABLE>"
            result.append({
                "key_id":          str(r["key_id"]),
                "service_name":    r["service_name"],
                "masked_value":    masked,
                "description":     r["description"] or "",
                "last_rotated_at": r["last_rotated_at"],
                "created_at":      r["created_at"],
                "updated_at":      r["updated_at"],
            })
        return result

    async def get_api_key_value(self, service_name: str) -> Optional[str]:
        """
        Devuelve el valor desencriptado de una API key. SOLO debe usarse desde
        endpoints ADMIN-only con logging explícito (#FIX-008).

        Returns:
            string en claro, o None si no existe.

        Raises:
            cryptography.fernet.InvalidToken si el ciphertext está corrupto.
        """
        from crypto_utils import decrypt

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT encrypted_value FROM api_keys WHERE service_name = $1",
                    service_name,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer api_keys[{service_name}]: {e}")
            raise
        if row is None:
            return None
        return decrypt(row["encrypted_value"])

    async def get_api_key_by_id(self, key_id: UUID) -> Optional[str]:
        """Variante de get_api_key_value() que busca por key_id (UUID)."""
        from crypto_utils import decrypt

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT service_name, encrypted_value FROM api_keys WHERE key_id = $1",
                    key_id,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer api_keys por id ({key_id}): {e}")
            raise
        if row is None:
            return None
        return decrypt(row["encrypted_value"])

    async def upsert_api_key(
        self,
        service_name: str,
        value: str,
        description: str = "",
    ) -> dict:
        """
        Inserta o actualiza una API key. El valor se encripta antes de
        persistir. Si el service_name ya existe, actualiza encrypted_value,
        description y last_rotated_at = NOW().

        Returns:
            dict {key_id, service_name, masked_value, description,
                  last_rotated_at, created_at, updated_at}.
        """
        from crypto_utils import encrypt, mask

        if not service_name or not service_name.strip():
            raise ValueError("service_name vacío")
        if not value or not value.strip():
            raise ValueError("value vacío")

        service_name = service_name.strip()
        encrypted    = encrypt(value)

        sql = """
            INSERT INTO api_keys (service_name, encrypted_value, description, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (service_name) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                description     = EXCLUDED.description,
                last_rotated_at = NOW(),
                updated_at      = NOW()
            RETURNING key_id, service_name, encrypted_value, description,
                      last_rotated_at, created_at, updated_at
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, service_name, encrypted, description or "")
        except asyncpg.PostgresError as e:
            logger.error(f"Error al upsertar api_key ({service_name}): {e}")
            raise

        logger.info(f"API key upsert: {service_name} (len={len(value)})")
        return {
            "key_id":          str(row["key_id"]),
            "service_name":    row["service_name"],
            "masked_value":    mask(value),
            "description":     row["description"] or "",
            "last_rotated_at": row["last_rotated_at"],
            "created_at":      row["created_at"],
            "updated_at":      row["updated_at"],
        }

    async def delete_api_key(self, key_id: UUID) -> bool:
        """
        Elimina una API key por UUID. Retorna True si se borró, False si
        no existía.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM api_keys WHERE key_id = $1", key_id,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al eliminar api_key {key_id}: {e}")
            raise
        deleted = result.startswith("DELETE ") and result.split()[-1] != "0"
        if deleted:
            logger.info(f"API key eliminada: key_id={key_id}")
        return deleted

    # =========================================================================
    # UNIVERSE SELECTION (#UNIVERSE-SELECTION) — métodos para el módulo
    # universe_selector.py: detección de warning, persistencia de decisiones,
    # gestión de candidatos, ejecución y rollback de rotaciones.
    # =========================================================================

    # ═══════════════════════════ § 12 — Warning status ═══════════════════════════
    async def get_sentinels_with_warning(self, owner_id: UUID) -> list[dict]:
        """
        Retorna las filas de performance_scores que cruzaron el WARNING
        threshold sin haber cruzado aún el DECAY. Cada item es una unidad
        (sentinel_id, ticker) — un Sentinel con varios tickers puede aparecer
        varias veces.

        Returns:
            list de dicts con sentinel_id, name, strategy_type, ticker,
            win_rate, sharpe_ratio, total_trades, performance_decay,
            warning_status, warning_detected_at.
        """
        sql = """
            SELECT s.sentinel_id, s.name, s.strategy_type,
                   ps.ticker, ps.win_rate, ps.sharpe_ratio, ps.total_trades,
                   ps.performance_decay, ps.warning_status, ps.warning_detected_at
            FROM performance_scores ps
            JOIN sentinels s ON s.sentinel_id = ps.sentinel_id
            WHERE s.owner_id = $1
              AND s.is_active = TRUE
              AND ps.warning_status = TRUE
            ORDER BY ps.warning_detected_at DESC NULLS LAST
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, owner_id)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar sentinels con warning: {e}")
            raise

    async def update_warning_status(
        self,
        sentinel_id: UUID,
        ticker: str,
        win_rate: float,
        sharpe_ratio: float,
        warning_threshold_winrate: float,
        warning_threshold_sharpe: float,
    ) -> bool:
        """
        Marca/desmarca warning_status en performance_scores según los
        umbrales pasados. warning_detected_at se setea cuando entra en
        warning (NULL cuando sale).

        Returns:
            True si la fila ahora está en warning, False si no.
        """
        in_warning = (
            (win_rate is not None and win_rate < warning_threshold_winrate)
            or (sharpe_ratio is not None and sharpe_ratio < warning_threshold_sharpe)
        )
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE performance_scores
                    SET warning_status      = $3,
                        warning_detected_at = CASE
                            WHEN $3 = TRUE AND warning_status = FALSE THEN NOW()
                            WHEN $3 = FALSE THEN NULL
                            ELSE warning_detected_at
                        END
                    WHERE sentinel_id = $1 AND ticker = $2
                    """,
                    sentinel_id, ticker, in_warning,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al actualizar warning_status ({sentinel_id}, {ticker}): {e}")
            raise
        return in_warning

    # ═══════════════════════════ § 13 — Universe Selector: candidatos y rotaciones ═══════════════════════════
    async def get_pending_candidate(self, sentinel_id: UUID) -> Optional[dict]:
        """
        Retorna el candidato pendiente activo (status='watching') del
        Sentinel, o None si no hay. Solo puede haber uno por el índice
        UNIQUE parcial.
        """
        sql = """
            SELECT pc.candidate_id, pc.sentinel_id, pc.proposed_ticker,
                   pc.proposed_at, pc.expires_at, pc.decision_id, pc.status
            FROM pending_candidates pc
            WHERE pc.sentinel_id = $1 AND pc.status = 'watching'
            LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, sentinel_id)
            return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer pending_candidate ({sentinel_id}): {e}")
            raise

    async def get_idle_pending_candidate(self, sentinel_id: UUID) -> Optional[dict]:
        """
        Retorna el pending_candidate 'watching' del Sentinel cuyo
        rotation_decision asociado fue disparado por idle_timeout, o None.
        (pending_candidates no guarda trigger_reason — se obtiene por JOIN con
        rotation_decisions.) Incluye old_ticker de la decisión para verificar
        que el ticker a reemplazar sigue idle antes de ejecutar la rotación.

        Returns dict {candidate_id, proposed_ticker, proposed_at, decision_id,
        old_ticker} o None.
        """
        sql = """
            SELECT pc.candidate_id, pc.proposed_ticker, pc.proposed_at,
                   pc.decision_id, rd.old_ticker
            FROM pending_candidates pc
            JOIN rotation_decisions rd ON rd.decision_id = pc.decision_id
            WHERE pc.sentinel_id = $1
              AND pc.status = 'watching'
              AND rd.trigger_reason = 'idle_timeout'
            LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, sentinel_id)
            return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer idle pending_candidate ({sentinel_id}): {e}")
            raise

    async def save_pending_candidate(
        self,
        sentinel_id: UUID,
        proposed_ticker: str,
        decision_id: UUID,
        ttl_days: int = 7,
    ) -> UUID:
        """
        Guarda un candidato en watchlist. Falla si ya hay otro en watching
        para el mismo sentinel (índice UNIQUE parcial) — el caller debe
        descartar el anterior primero.
        """
        sql = """
            INSERT INTO pending_candidates
                (sentinel_id, proposed_ticker, expires_at, decision_id, status)
            VALUES ($1, $2, NOW() + ($3 || ' days')::interval, $4, 'watching')
            RETURNING candidate_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql, sentinel_id, proposed_ticker, str(ttl_days), decision_id,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al guardar pending_candidate ({sentinel_id}, {proposed_ticker}): {e}")
            raise
        cid = row["candidate_id"]
        logger.info(
            f"Pending candidate creado: sentinel={sentinel_id} "
            f"ticker={proposed_ticker} expires_in={ttl_days}d candidate_id={cid}"
        )
        return cid

    async def discard_pending_candidate(self, candidate_id: UUID, reason: str = "") -> bool:
        """Marca el candidato como 'discarded'. Returns True si actualizó algo."""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE pending_candidates SET status = 'discarded' "
                    "WHERE candidate_id = $1 AND status = 'watching'",
                    candidate_id,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al descartar pending_candidate {candidate_id}: {e}")
            raise
        ok = result.startswith("UPDATE ") and result.split()[-1] != "0"
        if ok:
            logger.info(f"Pending candidate descartado: {candidate_id} | reason={reason!r}")
        return ok

    async def expire_old_pending_candidates(self) -> int:
        """
        Marca como 'expired' todos los pending_candidates con expires_at <= NOW()
        y status='watching'. Llamar periódicamente desde universe_selector.
        Retorna el conteo actualizado.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE pending_candidates SET status = 'expired' "
                    "WHERE status = 'watching' AND expires_at <= NOW()"
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al expirar pending_candidates: {e}")
            raise
        count = int(result.split()[-1]) if result.startswith("UPDATE ") else 0
        if count:
            logger.info(f"Pending candidates expirados: {count}")
        return count

    async def save_rotation_decision(
        self,
        *,
        sentinel_id: UUID,
        owner_id: UUID,
        trigger_reason: str,
        old_ticker: str,
        old_win_rate: Optional[float],
        old_sharpe_ratio: Optional[float],
        old_total_trades: Optional[int],
        new_ticker: Optional[str],
        candidates_proposed: list,
        claude_reasoning: Optional[str],
        claude_confidence: Optional[float],
        claude_model: Optional[str],
        claude_input_tokens: int,
        claude_output_tokens: int,
        claude_cost_usd: Decimal,
        status: str = "pending",
        notes: Optional[str] = None,
    ) -> UUID:
        """Persiste una rotation_decision. Retorna decision_id."""
        # Costo USD monetario → Decimal (#H-4). Conversión defensiva.
        claude_cost_usd = Decimal(str(claude_cost_usd))

        sql = """
            INSERT INTO rotation_decisions
                (sentinel_id, owner_id, trigger_reason,
                 old_ticker, old_win_rate, old_sharpe_ratio, old_total_trades,
                 new_ticker, candidates_proposed, claude_reasoning,
                 claude_confidence, claude_model,
                 claude_input_tokens, claude_output_tokens, claude_cost_usd,
                 status, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12,
                    $13, $14, $15, $16, $17)
            RETURNING decision_id
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql,
                    sentinel_id, owner_id, trigger_reason,
                    old_ticker, old_win_rate, old_sharpe_ratio, old_total_trades,
                    new_ticker, json.dumps(candidates_proposed or []),
                    claude_reasoning, claude_confidence, claude_model,
                    claude_input_tokens, claude_output_tokens, claude_cost_usd,
                    status, notes,
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al persistir rotation_decision ({sentinel_id}): {e}")
            raise
        did = row["decision_id"]
        logger.info(
            f"Rotation decision creada: {did} | sentinel={sentinel_id} "
            f"old={old_ticker} new={new_ticker} cost=${claude_cost_usd:.4f} "
            f"status={status}"
        )
        return did

    async def execute_rotation_in_db(
        self,
        decision_id: UUID,
    ) -> bool:
        """
        Ejecuta atomicamente la rotación: marca el ticker viejo inactive,
        inserta/activa el nuevo en sentinel_tickers, y marca la decisión
        como 'executed'. Todo en una sola transacción.

        Returns:
            True si la rotación se aplicó, False si la decisión no estaba
            en estado 'pending' o el sentinel/ticker no se encontraron.
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    decision = await conn.fetchrow(
                        "SELECT sentinel_id, old_ticker, new_ticker, status "
                        "FROM rotation_decisions WHERE decision_id = $1 FOR UPDATE",
                        decision_id,
                    )
                    if decision is None:
                        logger.warning(f"execute_rotation: decision {decision_id} no existe")
                        return False
                    if decision["status"] != "pending":
                        logger.warning(
                            f"execute_rotation: decision {decision_id} ya está en "
                            f"status={decision['status']!r}, skip"
                        )
                        return False
                    if not decision["new_ticker"]:
                        logger.warning(f"execute_rotation: decision {decision_id} sin new_ticker")
                        await conn.execute(
                            "UPDATE rotation_decisions "
                            "SET status = 'failed', notes = 'no new_ticker provided' "
                            "WHERE decision_id = $1",
                            decision_id,
                        )
                        return False

                    sid    = decision["sentinel_id"]
                    old    = decision["old_ticker"]
                    new    = decision["new_ticker"]

                    await conn.execute(
                        "UPDATE sentinel_tickers SET is_active = FALSE "
                        "WHERE sentinel_id = $1 AND ticker = $2",
                        sid, old,
                    )
                    # ON CONFLICT DO UPDATE — si el nuevo ticker ya existió antes
                    # (rotación de ida y vuelta), simplemente lo reactivamos.
                    await conn.execute(
                        """
                        INSERT INTO sentinel_tickers (sentinel_id, ticker, is_active)
                        VALUES ($1, $2, TRUE)
                        ON CONFLICT (sentinel_id, ticker) DO UPDATE
                            SET is_active = TRUE,
                                assigned_at = NOW()
                        """,
                        sid, new,
                    )
                    await conn.execute(
                        "UPDATE rotation_decisions "
                        "SET status = 'executed', executed_at = NOW() "
                        "WHERE decision_id = $1",
                        decision_id,
                    )
                    # Activar el pending_candidate asociado si existe.
                    await conn.execute(
                        "UPDATE pending_candidates "
                        "SET status = 'activated' "
                        "WHERE decision_id = $1 AND status = 'watching'",
                        decision_id,
                    )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al ejecutar rotation_in_db {decision_id}: {e}")
            raise
        logger.info(f"Rotation ejecutada: decision_id={decision_id} | {old} → {new} | sentinel={sid}")
        return True

    async def rollback_rotation_in_db(
        self,
        decision_id: UUID,
        admin_email: str,
    ) -> bool:
        """
        Deshace una rotación previamente ejecutada. Solo aplicable si
        status='executed'. Restaura el ticker viejo y desactiva el nuevo.
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    decision = await conn.fetchrow(
                        "SELECT sentinel_id, old_ticker, new_ticker, status "
                        "FROM rotation_decisions WHERE decision_id = $1 FOR UPDATE",
                        decision_id,
                    )
                    if decision is None:
                        logger.warning(f"rollback: decision {decision_id} no existe")
                        return False
                    if decision["status"] != "executed":
                        logger.warning(
                            f"rollback: decision {decision_id} no está en "
                            f"status='executed' (actual={decision['status']!r})"
                        )
                        return False

                    sid = decision["sentinel_id"]
                    old = decision["old_ticker"]
                    new = decision["new_ticker"]

                    await conn.execute(
                        "UPDATE sentinel_tickers SET is_active = FALSE "
                        "WHERE sentinel_id = $1 AND ticker = $2",
                        sid, new,
                    )
                    await conn.execute(
                        """
                        INSERT INTO sentinel_tickers (sentinel_id, ticker, is_active)
                        VALUES ($1, $2, TRUE)
                        ON CONFLICT (sentinel_id, ticker) DO UPDATE
                            SET is_active = TRUE,
                                assigned_at = NOW()
                        """,
                        sid, old,
                    )
                    await conn.execute(
                        "UPDATE rotation_decisions "
                        "SET status = 'rolled_back', "
                        "    rolled_back_at = NOW(), "
                        "    rolled_back_by = $2 "
                        "WHERE decision_id = $1",
                        decision_id, admin_email,
                    )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al rollback {decision_id}: {e}")
            raise
        logger.warning(
            f"ROLLBACK ejecutado por {admin_email}: decision_id={decision_id} "
            f"| restaurado {new} → {old} | sentinel={sid}"
        )
        return True

    async def discard_rotation_decision(self, decision_id: UUID, reason: str = "") -> bool:
        """Marca como 'discarded' una decisión que estaba pending."""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE rotation_decisions "
                    "SET status = 'discarded', notes = COALESCE(notes, '') || $2 "
                    "WHERE decision_id = $1 AND status = 'pending'",
                    decision_id, f" | discarded: {reason}" if reason else " | discarded",
                )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al discard rotation_decision {decision_id}: {e}")
            raise
        ok = result.startswith("UPDATE ") and result.split()[-1] != "0"
        return ok

    async def get_recent_rotations(
        self,
        owner_id: UUID,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> list[dict]:
        """
        Lista paginada de rotaciones recientes para el owner. Si status se
        provee, filtra (e.g. 'executed' para mostrar en dashboard).
        """
        params: list = [owner_id]
        where = "WHERE rd.owner_id = $1"
        if status:
            params.append(status)
            where += f" AND rd.status = ${len(params)}"
        params.append(limit)
        sql = f"""
            SELECT rd.decision_id, rd.sentinel_id, s.name AS sentinel_name,
                   rd.triggered_at, rd.trigger_reason,
                   rd.old_ticker, rd.new_ticker,
                   rd.old_win_rate, rd.old_sharpe_ratio, rd.old_total_trades,
                   rd.claude_confidence, rd.claude_model, rd.claude_cost_usd,
                   rd.status, rd.executed_at, rd.rolled_back_at, rd.rolled_back_by,
                   rd.candidates_proposed, rd.claude_reasoning, rd.notes
            FROM rotation_decisions rd
            JOIN sentinels s ON s.sentinel_id = rd.sentinel_id
            {where}
            ORDER BY rd.triggered_at DESC
            LIMIT ${len(params)}
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar rotaciones: {e}")
            raise

    async def get_rotation_decision(self, decision_id: UUID) -> Optional[dict]:
        """Detalle completo de una decisión por ID."""
        sql = """
            SELECT rd.*, s.name AS sentinel_name
            FROM rotation_decisions rd
            JOIN sentinels s ON s.sentinel_id = rd.sentinel_id
            WHERE rd.decision_id = $1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, decision_id)
            return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer rotation_decision {decision_id}: {e}")
            raise

    async def get_active_pending_candidates(self, owner_id: UUID) -> list[dict]:
        """
        Lista candidatos en watching (no expirados) para el owner.

        Incluye trigger_reason via LEFT JOIN con rotation_decisions para que
        el Universe Selector pueda usarlo en el prompt de coordinación
        ("MORPHEUS reclamó GLD por pre_decay_warning"). Backwards-compatible:
        el endpoint admin /api/admin/candidates ignora trigger_reason si no
        lo usa.
        """
        sql = """
            SELECT pc.candidate_id, pc.sentinel_id, s.name AS sentinel_name,
                   pc.proposed_ticker, pc.proposed_at, pc.expires_at,
                   pc.decision_id, pc.status,
                   rd.trigger_reason
            FROM pending_candidates pc
            JOIN sentinels s ON s.sentinel_id = pc.sentinel_id
            LEFT JOIN rotation_decisions rd ON rd.decision_id = pc.decision_id
            WHERE s.owner_id = $1
              AND pc.status = 'watching'
              AND pc.expires_at > NOW()
            ORDER BY pc.proposed_at DESC
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, owner_id)
            return [dict(r) for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar pending_candidates: {e}")
            raise

    async def get_failed_tickers_for_sentinel(self, sentinel_id: UUID) -> list[str]:
        """
        Tickers que ya tuvo este Sentinel y rotaron por decay (status='executed'
        o 'rolled_back'). Útil como contexto para el prompt — Claude evita
        proponer tickers que ya fallaron.
        """
        sql = """
            SELECT DISTINCT old_ticker
            FROM rotation_decisions
            WHERE sentinel_id = $1
              AND status IN ('executed', 'rolled_back')
              AND old_ticker IS NOT NULL
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, sentinel_id)
            return [r["old_ticker"] for r in rows]
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar failed_tickers de {sentinel_id}: {e}")
            raise

    # ═══════════════════════════ § 14 — Macro context ═══════════════════════════
    async def get_recent_macro_events(self, limit: int = 10) -> list[dict]:
        """
        Lista los últimos N macro_events ordenados DESC por created_at,
        incluyendo titulares matched (#FIX-010). Defensivo si la columna
        news_titles aún no existe en DB (FIX-007 pendiente de aplicar):
        retorna lista vacía para news_titles en ese caso.

        Returns:
            list de dicts con event_id, created_at, risk_score, vix_level,
            spy_change_15min, circuit_breaker_triggered, news_titles (list).
        """
        try:
            async with self.pool.acquire() as conn:
                col_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='macro_events' AND column_name='news_titles')"
                )
                if col_exists:
                    rows = await conn.fetch(
                        """
                        SELECT event_id, risk_score, vix_level, spy_change_15min,
                               circuit_breaker_triggered, news_titles, created_at
                        FROM macro_events
                        ORDER BY created_at DESC
                        LIMIT $1
                        """,
                        limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT event_id, risk_score, vix_level, spy_change_15min,
                               circuit_breaker_triggered, created_at
                        FROM macro_events
                        ORDER BY created_at DESC
                        LIMIT $1
                        """,
                        limit,
                    )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al listar macro_events: {e}")
            raise

        result: list[dict] = []
        for r in rows:
            d = dict(r)
            raw = d.get("news_titles")
            # asyncpg devuelve JSONB como str (sin codec custom) o como list
            # según versión. Normalizamos a list[dict].
            if isinstance(raw, str):
                try:
                    d["news_titles"] = json.loads(raw)
                except (ValueError, TypeError):
                    d["news_titles"] = []
            elif isinstance(raw, list):
                d["news_titles"] = raw
            else:
                d["news_titles"] = []
            result.append(d)
        return result

    async def get_recent_macro_context(self, hours: int = 6) -> dict:
        """
        Snapshot del contexto macro reciente para enviar a Claude:
        último risk_score, circuit_breaker actual, vix/spy delta promedio,
        y top 5 titulares relevantes.
        """
        sql = """
            SELECT risk_score, vix_level, spy_change_15min,
                   circuit_breaker_triggered, news_titles, created_at
            FROM macro_events
            WHERE created_at >= NOW() - ($1 || ' hours')::interval
            ORDER BY created_at DESC
            LIMIT 30
        """
        try:
            async with self.pool.acquire() as conn:
                # news_titles puede no existir si la migración 006 aún no se aplicó.
                col_exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'macro_events' AND column_name = 'news_titles')"
                )
                if col_exists:
                    rows = await conn.fetch(sql, str(hours))
                else:
                    rows = await conn.fetch(
                        """
                        SELECT risk_score, vix_level, spy_change_15min,
                               circuit_breaker_triggered, created_at
                        FROM macro_events
                        WHERE created_at >= NOW() - ($1 || ' hours')::interval
                        ORDER BY created_at DESC LIMIT 30
                        """,
                        str(hours),
                    )
        except asyncpg.PostgresError as e:
            logger.error(f"Error al leer macro_context: {e}")
            raise

        if not rows:
            return {
                "risk_score": 0.0, "circuit_breaker": False,
                "vix_delta": None, "spy_delta": None, "recent_titles": [],
            }

        latest = rows[0]
        # Promedio de cambios de los últimos eventos
        vix_vals = [float(r["vix_level"]) for r in rows if r["vix_level"] is not None]
        spy_vals = [float(r["spy_change_15min"]) for r in rows if r["spy_change_15min"] is not None]

        # Top titulares — agrupar de los últimos eventos hasta 5 únicos
        seen = set()
        titles: list[dict] = []
        for r in rows:
            raw = r.get("news_titles") if isinstance(r, dict) else None
            if raw is None and "news_titles" in r.keys():
                raw = r["news_titles"]
            if not raw:
                continue
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    continue
            if not isinstance(raw, list):
                continue
            for entry in raw:
                title = (entry.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                titles.append(entry)
                if len(titles) >= 5:
                    break
            if len(titles) >= 5:
                break

        return {
            "risk_score":      float(latest["risk_score"]) if latest["risk_score"] is not None else 0.0,
            "circuit_breaker": bool(latest["circuit_breaker_triggered"]),
            "vix_delta":       (sum(vix_vals) / len(vix_vals)) if vix_vals else None,
            "spy_delta":       (sum(spy_vals) / len(spy_vals)) if spy_vals else None,
            "recent_titles":   titles,
        }
