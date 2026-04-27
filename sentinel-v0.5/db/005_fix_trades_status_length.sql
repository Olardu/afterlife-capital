-- Migración 005: ampliar trades.status de VARCHAR(10) a VARCHAR(32) y relajar CHECK
-- Fecha: 2026-04-27
-- Razón: el primer día de paper trading reveló que Alpaca devuelve status
--        intermedios como "PENDING_NEW" (11 chars), "ACCEPTED", "PARTIALLY_FILLED"
--        (16 chars), "DONE_FOR_DAY" (12 chars), etc. Con VARCHAR(10) y el CHECK
--        constraint anterior (FILLED|CANCELLED|PENDING) los INSERT fallaban con
--        "el valor es demasiado largo para el tipo character varying(10)" y los
--        trades se enviaban a Alpaca pero no quedaban registrados en DB.
--        Ejemplo concreto: BUY de TSLA del 2026-04-27 09:30 y 14:30 ET. (#FIX-005)
-- Estado: PENDIENTE — aplicar manualmente con psql cuando el bot esté apagado.
--         Mientras tanto, historian.connect() aplica el mismo cambio idempotente
--         en cada arranque (ver bloque DO $$ con information_schema check).
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 005_fix_trades_status_length.sql

ALTER TABLE trades ALTER COLUMN status TYPE VARCHAR(32);

-- El CHECK constraint original solo aceptaba ('FILLED', 'CANCELLED', 'PENDING').
-- Alpaca usa un vocabulario más amplio (ver
-- https://docs.alpaca.markets/docs/orders-at-alpaca#order-lifecycle).
-- Lo dropeamos para no rechazar valores legítimos. La lógica del Dispatcher
-- ya solo acciona sobre status conocidos (approved si == "FILLED"); el resto
-- queda persistido como historial sin afectar el pipeline.
ALTER TABLE trades DROP CONSTRAINT IF EXISTS trades_status_check;
