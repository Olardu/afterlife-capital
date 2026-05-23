-- =============================================================================
-- LIMPIEZA MANTIS — 2026-05-08 (Excepción 1 ampliada)
-- =============================================================================
-- Mantis (S-2 rsi_short, sentinel_id=4d60c408-51f7-482c-8879-987e78769e32)
-- acumuló 18 tickers nuevos como subproducto del bucle de Universe Selector.
-- Plan: dejar 3 tickers activos compatibles con rsi_short (mean reversion +
-- diversificación factorial Bridgewater All Weather):
--
--   NVDA  → estrella histórica (Sharpe 39.96 según Excepción 1)   — Ambiente 2
--   XLU   → utilities defensivo, mean reversion clásica           — Ambiente 3
--   TLT   → bonos largos, mean reversion por movimiento de tasas  — Ambiente 4
--
-- Resto: marcado is_active=FALSE. NO se borran filas (preservamos historial
-- auditable de qué propuso Claude bajo el bug). Tampoco se borra
-- performance_scores ni rotation_decisions.
--
-- Estimación segura — VERIFICAR primero con BLOQUE 1 del archivo
-- validation_queries_2026-05-08.sql antes de ejecutar.
-- =============================================================================

\timing on

-- -----------------------------------------------------------------------------
-- Paso 0 — VERIFICACIÓN PRE-LIMPIEZA (read-only)
-- -----------------------------------------------------------------------------
-- Mostrar el estado actual de Mantis. Si NVDA, XLU o TLT NO están en la lista,
-- el plan necesita ajuste — avisar antes de ejecutar el UPDATE.

\echo '=== Estado actual de Mantis (sentinel_id=4d60c408-...) ==='

SELECT
    ticker,
    is_active,
    assigned_at AT TIME ZONE 'America/New_York' AS assigned_at_et
FROM sentinel_tickers
WHERE sentinel_id = '4d60c408-51f7-482c-8879-987e78769e32'
ORDER BY is_active DESC, ticker;

-- -----------------------------------------------------------------------------
-- Paso 1 — Asegurar NVDA, XLU, TLT activos (UPSERT)
-- -----------------------------------------------------------------------------
-- Si XLU y TLT NO existen en sentinel_tickers para Mantis (porque Claude nunca
-- los propuso aunque están en la lista de finalistas), los creamos como
-- activos. NVDA debería existir; el ON CONFLICT lo deja en TRUE igual.

\echo '=== UPSERT: NVDA, XLU, TLT activos en Mantis ==='

INSERT INTO sentinel_tickers (sentinel_id, ticker, is_active, assigned_at)
VALUES
    ('4d60c408-51f7-482c-8879-987e78769e32', 'NVDA', TRUE, NOW()),
    ('4d60c408-51f7-482c-8879-987e78769e32', 'XLU',  TRUE, NOW()),
    ('4d60c408-51f7-482c-8879-987e78769e32', 'TLT',  TRUE, NOW())
ON CONFLICT (sentinel_id, ticker) DO UPDATE
    SET is_active   = TRUE,
        assigned_at = NOW();

-- -----------------------------------------------------------------------------
-- Paso 2 — Marcar el resto como inactive
-- -----------------------------------------------------------------------------
-- Cualquier ticker de Mantis que NO sea NVDA/XLU/TLT queda is_active=FALSE.
-- Esto incluye TSLA y SPY (zombies originales) y los 18 nuevos del bucle.

\echo '=== UPDATE: resto de tickers de Mantis a is_active=FALSE ==='

UPDATE sentinel_tickers
SET is_active = FALSE
WHERE sentinel_id = '4d60c408-51f7-482c-8879-987e78769e32'
  AND ticker NOT IN ('NVDA', 'XLU', 'TLT')
  AND is_active = TRUE;

-- -----------------------------------------------------------------------------
-- Paso 3 — Limpiar pending_candidates de Mantis (si los hay)
-- -----------------------------------------------------------------------------
-- Por si hay candidatos en watchlist apuntando a Mantis. No deberían existir
-- porque las rotaciones de hoy usaron `decay_confirmed` directo, pero por
-- prudencia.

\echo '=== UPDATE: pending_candidates de Mantis a status=discarded ==='

UPDATE pending_candidates
SET status = 'discarded',
    discarded_at = NOW(),
    discarded_reason = 'cleanup_mantis_2026-05-08_post_loop_fix'
WHERE sentinel_id = '4d60c408-51f7-482c-8879-987e78769e32'
  AND status = 'watching';

-- -----------------------------------------------------------------------------
-- Paso 4 — VERIFICACIÓN POST-LIMPIEZA
-- -----------------------------------------------------------------------------

\echo '=== Estado final de Mantis ==='

SELECT
    ticker,
    is_active,
    assigned_at AT TIME ZONE 'America/New_York' AS assigned_at_et
FROM sentinel_tickers
WHERE sentinel_id = '4d60c408-51f7-482c-8879-987e78769e32'
ORDER BY is_active DESC, ticker;

\echo ''
\echo '=== Verificación: get_sentinel_scores con JOIN (post Fix 2) ==='
\echo 'Esta query simula lo que verá el Dispatcher después del reinicio.'
\echo 'Solo NVDA, XLU, TLT deberían aparecer para Mantis.'

SELECT
    s.name                AS sentinel,
    ps.ticker,
    ROUND(ps.sharpe_ratio::numeric, 2) AS sharpe,
    ROUND((ps.win_rate * 100)::numeric, 1) AS win_rate_pct,
    ps.total_trades
FROM performance_scores ps
JOIN sentinels s ON ps.sentinel_id = s.sentinel_id
JOIN sentinel_tickers st
  ON st.sentinel_id = ps.sentinel_id AND st.ticker = ps.ticker
WHERE s.sentinel_id = '4d60c408-51f7-482c-8879-987e78769e32'
  AND st.is_active = TRUE
ORDER BY ps.sharpe_ratio DESC;

\echo ''
\echo '=== Listo. Ahora reiniciar main.py para que Fix 1 + Fix 2 entren en efecto. ==='
