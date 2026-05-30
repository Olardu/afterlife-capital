-- Migración 019 — columna risk_rationale en macro_events (swap FinBERT→DeepSeek).
-- The Ear pasa de FinBERT local a DeepSeek API para interpretar las noticias de
-- mercado (Alpaca News / Benzinga) y devolver un risk_score 0-1. DeepSeek también
-- devuelve una breve explicación (rationale) de por qué; se persiste 1 por ciclo
-- para auditar las decisiones del veto de noticias. Los titulares top siguen en
-- news_titles (JSONB). sentiment_method pasa a valer 'deepseek'.
-- Idempotente (ADD COLUMN IF NOT EXISTS). Aplicar con psql ON_ERROR_STOP=1.

BEGIN;

ALTER TABLE macro_events
    ADD COLUMN IF NOT EXISTS risk_rationale TEXT;   -- explicación breve de DeepSeek (<= 200-300 chars)

COMMENT ON COLUMN macro_events.risk_rationale IS
    'Explicacion breve de DeepSeek sobre por que el risk_score de este ciclo (swap FinBERT->DeepSeek). NULL si no hubo noticias nuevas o DeepSeek no estaba disponible.';

COMMIT;
