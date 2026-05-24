-- 015_add_signals_shadow_fractional.sql
-- EXP-005 — Modo Observador Fractional (T-K).
-- Tabla NUEVA y AISLADA. NO modifica ninguna tabla existente ni el flow ejecutable.
-- Por cada señal real, el dispatcher persiste aquí qué HUBIERA operado con
-- fractional (notional) vs lo que realmente ejecutó (qty entera, floor) — para
-- cuantificar post-período el costo real de operar sin fractional.
-- Decisión Roman↔Cowork 24-may noche (ver teamwork/LOG.md 00:30 + 00:35).
-- Idempotente: CREATE TABLE IF NOT EXISTS + índices IF NOT EXISTS.

BEGIN;

CREATE TABLE IF NOT EXISTS signals_shadow_fractional (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id                   UUID REFERENCES signals(id) ON DELETE CASCADE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ticker                      VARCHAR(20) NOT NULL,
    sentinel_id                 UUID NOT NULL,
    price_at_signal             NUMERIC(14,4) NOT NULL,
    equity_at_decision          NUMERIC(14,2) NOT NULL,
    allocation_pct              NUMERIC(7,4) NOT NULL,
    max_dollar_value            NUMERIC(14,2) NOT NULL,
    qty_real_executed           NUMERIC(14,4) NOT NULL,
    qty_fractional_would        NUMERIC(14,6) NOT NULL,
    notional_real               NUMERIC(14,2) NOT NULL,
    notional_fractional_would   NUMERIC(14,2) NOT NULL,
    dollar_diff                 NUMERIC(14,2) NOT NULL,
    status                      VARCHAR(50) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_frac_signal_id  ON signals_shadow_fractional(signal_id);
CREATE INDEX IF NOT EXISTS idx_shadow_frac_created_at ON signals_shadow_fractional(created_at);
CREATE INDEX IF NOT EXISTS idx_shadow_frac_status     ON signals_shadow_fractional(status);

COMMENT ON TABLE signals_shadow_fractional IS
    'EXP-005: modo observador fractional. Cada signal real persiste aquí en paralelo qué hubiera operado con fractional. NO afecta el flow ejecutable. Inicio 2do período observación.';
COMMENT ON COLUMN signals_shadow_fractional.qty_real_executed IS
    'qty efectivamente enviada a Alpaca = floor(qty_fractional_would) (execute_order hace int(floor(qty))).';
COMMENT ON COLUMN signals_shadow_fractional.qty_fractional_would IS
    'qty que se ejecutaría con fractional = final_qty pre-floor (allocation + reducción CorrelationGuard ya aplicadas).';
COMMENT ON COLUMN signals_shadow_fractional.dollar_diff IS
    'notional_fractional_would - notional_real = capital sin desplegar por el floor a entero.';
COMMENT ON COLUMN signals_shadow_fractional.status IS
    'matched (dollar_diff < $1) | fractional_would_increase (qty_frac > qty_real, diff significativa) | signal_lost_to_int_floor (qty_real=0 por floor pero qty_frac>0) | other';

COMMIT;
