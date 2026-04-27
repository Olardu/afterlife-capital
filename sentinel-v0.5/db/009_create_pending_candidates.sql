-- Migración 009: tabla pending_candidates — Watchlist Anticipada
-- Fecha: 2026-04-27
-- Razón: cuando un Sentinel cruza el WARNING_THRESHOLD (pre-decay), el
--        Universe Selector pide un candidato a Claude PERO no lo activa
--        todavía. Se queda en watchlist 7 días por default. Si la
--        performance se recupera el candidato se descarta. Si cruza el
--        DECAY_THRESHOLD el candidato se activa automáticamente
--        (#UNIVERSE-SELECTION).
-- Estado: aplicar manualmente con psql; historian.connect() es la red de
--         seguridad.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 009_create_pending_candidates.sql

CREATE TABLE IF NOT EXISTS pending_candidates (
    candidate_id     UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    sentinel_id      UUID      NOT NULL REFERENCES sentinels(sentinel_id),
    proposed_ticker  TEXT      NOT NULL,
    proposed_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMP NOT NULL,
    decision_id      UUID      REFERENCES rotation_decisions(decision_id),
    -- 'watching' | 'activated' | 'expired' | 'discarded'
    status           TEXT      NOT NULL DEFAULT 'watching'
);

-- Solo un candidato 'watching' por Sentinel a la vez (índice parcial UNIQUE
-- — equivalente al "UNIQUE WHERE status='watching'" del prompt original
-- pero usando la sintaxis correcta de PostgreSQL).
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_candidates_one_active
    ON pending_candidates(sentinel_id)
    WHERE status = 'watching';

CREATE INDEX IF NOT EXISTS idx_pending_candidates_status     ON pending_candidates(status);
CREATE INDEX IF NOT EXISTS idx_pending_candidates_expires_at ON pending_candidates(expires_at);
CREATE INDEX IF NOT EXISTS idx_pending_candidates_sentinel   ON pending_candidates(sentinel_id);
