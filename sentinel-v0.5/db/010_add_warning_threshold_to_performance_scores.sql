-- Migración 010: agregar warning_status a performance_scores
-- Fecha: 2026-04-27
-- Razón: el Universe Selector necesita un canal explícito para marcar que
--        un Sentinel está en zona de "warning" (pre-decay) sin reusar la
--        flag performance_decay (que sigue siendo binaria — sin/con decay).
--        warning_status permite trackear la transición y, si la performance
--        se recupera antes de cruzar el decay threshold, descartar el
--        candidato pendiente sin haberlo activado (#UNIVERSE-SELECTION).
-- Estado: idempotente — re-aplicar es seguro. historian.connect() también
--         ejecuta este DDL.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 010_add_warning_threshold_to_performance_scores.sql

ALTER TABLE performance_scores
    ADD COLUMN IF NOT EXISTS warning_status      BOOLEAN   NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS warning_detected_at TIMESTAMP;
