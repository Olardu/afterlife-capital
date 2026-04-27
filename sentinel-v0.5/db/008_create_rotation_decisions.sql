-- Migración 008: tabla rotation_decisions — auditoría de Universe Selection
-- Fecha: 2026-04-27
-- Razón: cuando un Sentinel se acerca al decay, el Universe Selector pide a
--        Claude un candidato de reemplazo. Cada decisión debe quedar
--        completamente loggeada (input del Sentinel, candidatos propuestos,
--        razonamiento, costo en tokens y USD, ejecución, rollback) para
--        auditar las elecciones del modelo y poder validarlas
--        estadísticamente con el tiempo (#UNIVERSE-SELECTION).
-- Estado: aplicar manualmente con psql cuando el bot esté apagado.
--         historian.connect() también ejecuta este DDL idempotente.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 008_create_rotation_decisions.sql

CREATE TABLE IF NOT EXISTS rotation_decisions (
    decision_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    sentinel_id          UUID         NOT NULL REFERENCES sentinels(sentinel_id),
    owner_id             UUID         NOT NULL REFERENCES users(user_id),
    triggered_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    -- 'pre_decay_warning' | 'decay_confirmed' | 'manual'
    trigger_reason       TEXT         NOT NULL,

    -- Estado del Sentinel al momento de la decisión
    old_ticker           TEXT         NOT NULL,
    old_win_rate         DOUBLE PRECISION,
    old_sharpe_ratio     DOUBLE PRECISION,
    old_total_trades     INTEGER,

    -- Decisión de Claude
    new_ticker           TEXT,
    candidates_proposed  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    claude_reasoning     TEXT,
    claude_confidence    DOUBLE PRECISION,
    claude_model         TEXT,
    claude_input_tokens  INTEGER,
    claude_output_tokens INTEGER,
    claude_cost_usd      DOUBLE PRECISION,

    -- Estado de la rotación
    -- 'pending' | 'executed' | 'rolled_back' | 'failed' | 'discarded'
    status               TEXT         NOT NULL DEFAULT 'pending',
    executed_at          TIMESTAMP,
    rolled_back_at       TIMESTAMP,
    rolled_back_by       TEXT,

    -- Tracking de resultado post-rotación (se actualiza periódicamente)
    new_ticker_trades_after_30d  INTEGER,
    new_ticker_winrate_after_30d DOUBLE PRECISION,
    new_ticker_sharpe_after_30d  DOUBLE PRECISION,

    notes                TEXT
);

CREATE INDEX IF NOT EXISTS idx_rotation_decisions_sentinel  ON rotation_decisions(sentinel_id);
CREATE INDEX IF NOT EXISTS idx_rotation_decisions_status    ON rotation_decisions(status);
CREATE INDEX IF NOT EXISTS idx_rotation_decisions_triggered ON rotation_decisions(triggered_at DESC);
