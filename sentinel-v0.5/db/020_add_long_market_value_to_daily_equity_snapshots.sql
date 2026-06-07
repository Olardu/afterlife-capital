-- Migración 020 — columna long_market_value en daily_equity_snapshots (BUG 2,
-- #BUG-CG-EXPOSURE). Alerta de sobre-exposición SOSTENIDA (solo notificación, cero
-- ventas automáticas): si long_market_value / equity_close supera el umbral
-- (config.EXPOSURE_ALERT_THRESHOLD, 95%) durante EXPOSURE_ALERT_DAYS días hábiles
-- consecutivos, /api/status expone una alerta para el dashboard. Decisión Roman/Deep:
-- no vender en dips (lockea pérdidas); el cap que bloquea compras + el guard
-- anti-margen ya cubren el riesgo real. Esta columna solo habilita el AVISO.
-- Idempotente (ADD COLUMN IF NOT EXISTS); nullable → filas viejas no cuentan para
-- la alerta. Aplicar con psql ON_ERROR_STOP=1.

BEGIN;

ALTER TABLE daily_equity_snapshots
    ADD COLUMN IF NOT EXISTS long_market_value NUMERIC(20, 4);   -- valor de mercado en longs al snapshot

COMMENT ON COLUMN daily_equity_snapshots.long_market_value IS
    'Valor de mercado en posiciones long al momento del snapshot diario. Alimenta la alerta de sobre-exposicion sostenida (#BUG-CG-EXPOSURE). NULL = no registrado (filas pre-migracion / fetch fallido) -> no cuenta para la alerta.';

COMMIT;
