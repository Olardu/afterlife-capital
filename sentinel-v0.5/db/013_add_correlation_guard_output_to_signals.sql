-- Migration 013: persistir el output de CorrelationGuard en signals table.
-- Hoy CorrelationGuard opera en runtime (dispatcher.process_signal invoca
-- evaluate_signal) pero su output (avg_correlation, qty original vs ajustada,
-- factor de reducción) solo queda en logs. Sin persistencia no auditamos.
--
-- Cierra TECHDEBT-NEW-2 + EXP-003. Habilita la sección §6 del balance.
--
-- NO aplicar autónomo: requiere autorización explícita de Roman en el LOG
-- (mismo patrón que la migración 011 de daily_equity_snapshots).

BEGIN;

ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS avg_correlation_at_decision NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS original_qty                NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS adjusted_qty                NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS reduction_factor            NUMERIC(5,4);

COMMENT ON COLUMN signals.avg_correlation_at_decision IS
    'Promedio de correlación de la nueva señal vs posiciones existentes al momento de evaluación. NULL si CorrelationGuard no se invocó (caso edge).';
COMMENT ON COLUMN signals.original_qty IS
    'Cantidad propuesta por el Sentinel ANTES de CorrelationGuard.';
COMMENT ON COLUMN signals.adjusted_qty IS
    'Cantidad final DESPUÉS de CorrelationGuard. Igual a original_qty si la señal pasó intacta. 0 si fue descartada.';
COMMENT ON COLUMN signals.reduction_factor IS
    'Factor aplicado: 1.0 = pasó intacta, < 1.0 = reducida proporcionalmente, 0.0 = descartada por correlación alta.';

COMMIT;
