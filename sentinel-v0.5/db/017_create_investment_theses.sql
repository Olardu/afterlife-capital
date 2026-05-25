-- Migración 017: tabla investment_theses — Investment Thesis Tracking (#HE-2).
-- Fecha: 2026-05-25
-- Razón: tracking estructurado de las tesis de inversión del bot. Cada propuesta
--        del Universe Selector (rotación) nace como una "tesis" que avanza por
--        una state machine (IDEA → ENTRY_READY → ACTIVE → CLOSED). Al cerrar se
--        evalúa con MAE/MFE (Maximum Adverse / Favorable Excursion) + outcome,
--        y el conjunto de tesis cerradas alimenta el system prompt del Universe
--        Selector como contexto histórico (feedback loop, #ME-2). Permite medir
--        la calidad de las decisiones del modelo en el tiempo, más allá del
--        win_rate crudo (cuánto sufrió la posición antes de funcionar, etc).
-- Estado: aplicar manualmente con psql cuando el bot esté apagado.
--         historian.connect() también ejecuta este DDL idempotente.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 017_create_investment_theses.sql

CREATE TABLE IF NOT EXISTS investment_theses (
    thesis_id            UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    sentinel_id          UUID           NOT NULL REFERENCES sentinels(sentinel_id),
    owner_id             UUID           NOT NULL REFERENCES users(user_id),
    -- Rotación que originó la tesis (NULL si se creó por otra vía). El reasoning
    -- de Claude vive en rotation_decisions.claude_reasoning + acá una copia.
    decision_id          UUID           REFERENCES rotation_decisions(decision_id),

    ticker               TEXT           NOT NULL,
    -- 'LONG' | 'SHORT' (S-2 y S-8 operan en corto).
    direction            TEXT           NOT NULL DEFAULT 'LONG'
                                        CHECK (direction IN ('LONG', 'SHORT')),
    -- State machine. Ver investment_thesis.VALID_TRANSITIONS.
    state                TEXT           NOT NULL DEFAULT 'IDEA'
                                        CHECK (state IN ('IDEA', 'ENTRY_READY', 'ACTIVE', 'CLOSED')),

    -- Targets de la tesis (al proponerla).
    entry_price_target   NUMERIC(20, 4),
    exit_target          NUMERIC(20, 4),
    stop_loss            NUMERIC(20, 4),
    rationale_text       TEXT,
    claude_reasoning     TEXT,

    -- Realización (se completan al pasar a ACTIVE / CLOSED).
    entry_price          NUMERIC(20, 4),   -- fill real al entrar
    exit_price           NUMERIC(20, 4),   -- precio real al cerrar
    -- 'win' | 'loss' | 'breakeven' (al cerrar).
    outcome              TEXT,
    gain                 NUMERIC(20, 4),   -- por acción, en precio
    gain_pct             NUMERIC(12, 4),
    -- MAE/MFE durante el holding (magnitud >= 0, en precio y en %).
    mae                  NUMERIC(20, 4),
    mfe                  NUMERIC(20, 4),
    mae_pct              NUMERIC(12, 4),
    mfe_pct              NUMERIC(12, 4),
    holding_days         INTEGER,

    created_at           TIMESTAMP      NOT NULL DEFAULT NOW(),
    entry_at             TIMESTAMP,
    closed_at            TIMESTAMP,
    notes                TEXT
);

CREATE INDEX IF NOT EXISTS idx_investment_theses_sentinel ON investment_theses(sentinel_id);
CREATE INDEX IF NOT EXISTS idx_investment_theses_state    ON investment_theses(state);
CREATE INDEX IF NOT EXISTS idx_investment_theses_owner    ON investment_theses(owner_id);
CREATE INDEX IF NOT EXISTS idx_investment_theses_decision ON investment_theses(decision_id);
CREATE INDEX IF NOT EXISTS idx_investment_theses_created  ON investment_theses(created_at DESC);
