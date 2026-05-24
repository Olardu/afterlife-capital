-- Migración 011: tabla daily_equity_snapshots — fuente persistente de equity
-- histórico para los drawdown limits del portafolio (#GR-3).
-- Fecha: 2026-05-24
-- Razón: el límite de drawdown acumulado ("-15% vs peak histórico → pausa
--        indefinida") necesita un peak que NUNCA se pierda. Alpaca
--        portfolio_history tiene retención limitada (~2 años) y se descarta
--        al cambiar de cuenta (paper → live en julio). Una tabla propia
--        sobrevive reinicios y migraciones de cuenta, y es la source of truth.
-- Granularidad: 1 fila por día hábil por owner, con equity al open, al close,
--        y el peak running hasta esa fecha. Suficiente para los 3 niveles
--        (daily/weekly/cumulative).
-- Estado: idempotente (IF NOT EXISTS). historian.connect() la ejecuta al
--         próximo restart; también aplicable manual con psql.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 011_create_daily_equity_snapshots.sql

CREATE TABLE IF NOT EXISTS daily_equity_snapshots (
    snapshot_id   UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id      UUID           NOT NULL REFERENCES users(user_id),
    snapshot_date DATE           NOT NULL,
    equity_open   NUMERIC(20, 4) NOT NULL,
    equity_close  NUMERIC(20, 4) NOT NULL,
    peak_to_date  NUMERIC(20, 4) NOT NULL,
    created_at    TIMESTAMP      NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP      NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_equity_snapshots_owner_date
    ON daily_equity_snapshots (owner_id, snapshot_date DESC);
