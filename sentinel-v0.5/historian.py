# historian.py
# Agente de memoria y feedback loop de Sentinel v0.5.
# Gestiona toda la persistencia en PostgreSQL: trades, signals, performance scores
# y eventos macro. Expone el feedback loop de decay al Dispatcher.
# Usa asyncpg para operaciones no bloqueantes dentro del grafo LangGraph.

import json
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


# Email del owner del sistema — protegido contra eliminación desde el panel
# admin. Coincide con el UPDATE idempotente de connect() y con la cuenta
# Google que tiene acceso ADMIN garantizado.
_OWNER_EMAIL = "***REMOVED-EMAIL***"


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
