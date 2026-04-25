-- =============================================================================
-- SENTINEL v0.5 — Esquema PostgreSQL
-- Arquitectura multi-tenant. Todo registro lleva owner_id para aislar datos
-- por usuario. Diseñado para paper trading con Alpaca IEX.
-- =============================================================================

-- Extensión necesaria para gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- =============================================================================
-- TABLA: users
-- Base del modelo multi-tenant. Cada entidad del sistema referencia esta tabla.
-- ADMIN puede operar; VIEWER solo puede consultar el dashboard.
-- =============================================================================
CREATE TABLE users (
    user_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username  VARCHAR(50)  UNIQUE NOT NULL,
    email     VARCHAR(100) UNIQUE NOT NULL,
    role      VARCHAR(10)  NOT NULL CHECK (role IN ('ADMIN', 'VIEWER')),
    created_at TIMESTAMP   NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- TABLA: sentinels
-- Registro de los 10 agentes de estrategia. Cada Sentinel pertenece a un usuario
-- (owner_id), opera sobre un ticker base y tiene una asignación de capital
-- entre 5% y 25% del portafolio total (regla Dispatcher).
-- =============================================================================
CREATE TABLE sentinels (
    sentinel_id         UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            UUID          NOT NULL REFERENCES users(user_id),
    name                VARCHAR(50)   NOT NULL,
    strategy_type       VARCHAR(50)   NOT NULL,
    ticker              VARCHAR(10)   NOT NULL,
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    capital_allocation  DECIMAL(5,2)  NOT NULL CHECK (capital_allocation BETWEEN 5 AND 25),
    created_at          TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sentinels_owner_id   ON sentinels(owner_id);
CREATE INDEX idx_sentinels_ticker     ON sentinels(ticker);
CREATE INDEX idx_sentinels_created_at ON sentinels(created_at);


-- =============================================================================
-- TABLA: signals
-- Señales generadas por cada Sentinel antes de ser enviadas al Dispatcher.
-- El Dispatcher decide si ejecutar según régimen, correlación y capital disponible.
-- =============================================================================
CREATE TABLE signals (
    signal_id       UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    sentinel_id     UUID          NOT NULL REFERENCES sentinels(sentinel_id),
    owner_id        UUID          NOT NULL REFERENCES users(user_id),
    ticker          VARCHAR(10)   NOT NULL,
    signal_type     VARCHAR(10)   NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
    price_at_signal DECIMAL(10,4) NOT NULL,
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_sentinel_id ON signals(sentinel_id);
CREATE INDEX idx_signals_owner_id    ON signals(owner_id);
CREATE INDEX idx_signals_ticker      ON signals(ticker);
CREATE INDEX idx_signals_created_at  ON signals(created_at);


-- =============================================================================
-- TABLA: trades
-- Ejecuciones reales enviadas a Alpaca (paper trading con feed IEX).
-- Registra slippage para retroalimentar al Historian y al Dispatcher.
-- status PENDING → FILLED o CANCELLED una vez que Alpaca confirma.
-- =============================================================================
CREATE TABLE trades (
    trade_id      UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id     UUID          REFERENCES signals(signal_id),
    sentinel_id   UUID          NOT NULL REFERENCES sentinels(sentinel_id),
    owner_id      UUID          NOT NULL REFERENCES users(user_id),
    ticker        VARCHAR(10)   NOT NULL,
    side          VARCHAR(5)    NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty           DECIMAL(10,4) NOT NULL,
    filled_price  DECIMAL(10,4),
    slippage      DECIMAL(10,4),
    status        VARCHAR(10)   NOT NULL CHECK (status IN ('FILLED', 'CANCELLED', 'PENDING')),
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_sentinel_id ON trades(sentinel_id);
CREATE INDEX idx_trades_owner_id    ON trades(owner_id);
CREATE INDEX idx_trades_ticker      ON trades(ticker);
CREATE INDEX idx_trades_created_at  ON trades(created_at);


-- =============================================================================
-- TABLA: performance_scores
-- Calculado por el Historian. Score por (sentinel_id, ticker).
-- performance_decay = TRUE activa rotación de ticker en ese Sentinel.
-- sharpe_ratio y win_rate son la base del sizing Half-Kelly en el Dispatcher.
-- =============================================================================
CREATE TABLE performance_scores (
    score_id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    sentinel_id       UUID          NOT NULL REFERENCES sentinels(sentinel_id),
    ticker            VARCHAR(10)   NOT NULL,
    sharpe_ratio      DECIMAL(8,4),
    win_rate          DECIMAL(5,4),
    total_trades      INT           NOT NULL DEFAULT 0,
    performance_decay BOOLEAN       NOT NULL DEFAULT FALSE,
    calculated_at     TIMESTAMP     NOT NULL DEFAULT NOW(),
    UNIQUE (sentinel_id, ticker)
);

CREATE INDEX idx_performance_sentinel_id    ON performance_scores(sentinel_id);
CREATE INDEX idx_performance_ticker         ON performance_scores(ticker);
CREATE INDEX idx_performance_calculated_at  ON performance_scores(calculated_at);


-- =============================================================================
-- TABLA: macro_events
-- Registros de The Ear. Captura el estado macro cada 15 minutos.
-- circuit_breaker_triggered = TRUE pausa todas las operaciones del sistema.
-- Parking Brake se activa a las 15:45 — se registra aquí también.
-- =============================================================================
CREATE TABLE macro_events (
    event_id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_score                DECIMAL(3,2) NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
    vix_level                 DECIMAL(8,4),
    spy_change_15min          DECIMAL(8,4),
    circuit_breaker_triggered BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at                TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_macro_events_created_at ON macro_events(created_at);


-- =============================================================================
-- TABLA: migration_log
-- Auditoría de migraciones retroactivas. Registra cuántos registros fueron
-- actualizados con owner_id por cada ejecución del script de migración.
-- =============================================================================
CREATE TABLE migration_log (
    log_id            UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id          UUID      NOT NULL REFERENCES users(user_id),
    records_migrated  INT       NOT NULL DEFAULT 0,
    migrated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_migration_log_owner_id     ON migration_log(owner_id);
CREATE INDEX idx_migration_log_migrated_at  ON migration_log(migrated_at);


-- Migración retroactiva en db/migrate_retroactive.sql — ejecutar por separado.
