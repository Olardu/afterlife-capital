-- Migration 014: profit_factor + return_to_drawdown_ratio en performance_scores.
-- Soporta el decay multifactor (EXP-002 / Rec 6 investigación): win_rate y sharpe
-- por sí solos dan falsos positivos (WR 38% + payoff 2.0 es rentable pero se mata)
-- y falsos negativos (WR 65% + payoff 0.4 pierde y no se detecta). PF (>1.3) y RTD
-- (>1.0) son las métricas más informativas. Cierra #FASE2-NEW-5.
--
-- NO aplicar autónomo sin OK de Roman (autorización heredada del LOG 2026-05-24 20:45,
-- mismo patrón/scope que las migraciones 011 y 013).

BEGIN;

ALTER TABLE performance_scores
    ADD COLUMN IF NOT EXISTS profit_factor            NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS return_to_drawdown_ratio NUMERIC(10,4);

COMMENT ON COLUMN performance_scores.profit_factor IS
    'Gross profit / abs(gross loss) sobre returns por trade. NULL si no es finito (gross_loss=0).';
COMMENT ON COLUMN performance_scores.return_to_drawdown_ratio IS
    'Total return / max drawdown sobre la serie acumulada de returns. NULL si no es finito (max_dd=0).';

COMMIT;
