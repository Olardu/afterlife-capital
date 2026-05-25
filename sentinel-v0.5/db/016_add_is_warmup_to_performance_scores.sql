-- Migración 016 (#TD — T-R Bloque F) — 2026-05-24
-- Agrega is_warmup a performance_scores: marca filas de scores PARCIALES
-- (2 ≤ total_trades < WARMUP_TRADES_REQUIRED) para que el dashboard distinga
-- "en warmup" de "sin datos". Lo persiste historian.evaluate_decay.
-- Idempotente (mismo patrón que 011/013/014/015). También se aplica como red de
-- seguridad en historian.connect() vía ADD COLUMN IF NOT EXISTS.

ALTER TABLE performance_scores
    ADD COLUMN IF NOT EXISTS is_warmup BOOLEAN NOT NULL DEFAULT FALSE;
