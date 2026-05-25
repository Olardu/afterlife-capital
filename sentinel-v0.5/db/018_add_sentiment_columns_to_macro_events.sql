-- Migración 018 — columnas de sentiment FinBERT en macro_events (#FEAT-007 / T-U).
-- The Ear puede complementar el keyword matching con sentiment finance-tuned
-- (modelo ProsusAI/finbert). En "hybrid mode" se persisten AMBOS scores para
-- comparar keyword vs FinBERT durante la calibración del umbral de veto.
-- Idempotente (ADD COLUMN IF NOT EXISTS). Aplicar con psql ON_ERROR_STOP=1.

BEGIN;

ALTER TABLE macro_events
    ADD COLUMN IF NOT EXISTS sentiment_score_finbert NUMERIC(6,4),  -- [-1, 1]
    ADD COLUMN IF NOT EXISTS sentiment_method        VARCHAR(20);   -- 'keyword' | 'finbert' | 'hybrid'

COMMENT ON COLUMN macro_events.sentiment_score_finbert IS
    'Sentiment score [-1,1] del modelo FinBERT sobre los titulares. NULL si el modelo no estaba disponible.';
COMMENT ON COLUMN macro_events.sentiment_method IS
    'Metodo del risk_score que decidio: keyword (legacy) | finbert (FinBERT activo) | hybrid (ambos persistidos).';

COMMIT;
