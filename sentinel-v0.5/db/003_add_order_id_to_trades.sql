-- Migración 003: agregar columna order_id a tabla trades
-- Fecha: 2026-04-25
-- Razón: el order_id de Alpaca es metadata legítima del trade y se necesita
--        para reconciliar limit orders ejecutadas en background (#H-6).
--        Sin esta columna, el background task no puede actualizar el trade
--        en DB porque no hay forma de mapear order_id → trade_id.
-- Estado: APLICADA MANUALMENTE por Roman el 2026-04-25.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 003_add_order_id_to_trades.sql

ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_id TEXT;
CREATE INDEX IF NOT EXISTS idx_trades_order_id ON trades(order_id) WHERE order_id IS NOT NULL;
