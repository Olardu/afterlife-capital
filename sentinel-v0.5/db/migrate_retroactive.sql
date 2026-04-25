-- =============================================================================
-- migrate_retroactive.sql
-- Script de migración retroactiva ONE-TIME para datos pre-existentes.
-- NO ejecutar en deploy fresco — solo sobre una base con registros sin owner_id.
-- Asigna owner_id del usuario 'roman' a todos los registros huérfanos.
-- Requiere que el usuario 'roman' exista en la tabla users antes de correr.
-- =============================================================================

-- Paso 1: Relajar NOT NULL temporalmente para permitir el UPDATE
ALTER TABLE sentinels ALTER COLUMN owner_id DROP NOT NULL;
ALTER TABLE signals   ALTER COLUMN owner_id DROP NOT NULL;
ALTER TABLE trades    ALTER COLUMN owner_id DROP NOT NULL;

-- Paso 2: Migración
DO $$
DECLARE
    roman_id        UUID;
    n_sentinels     INT := 0;
    n_signals       INT := 0;
    n_trades        INT := 0;
    n_performance   INT := 0;
    n_total         INT := 0;
BEGIN
    SELECT user_id INTO roman_id
    FROM users
    WHERE username = 'roman'
    LIMIT 1;

    IF roman_id IS NULL THEN
        RAISE EXCEPTION 'Usuario roman no encontrado en tabla users. Crear el usuario primero.';
    END IF;

    UPDATE sentinels SET owner_id = roman_id WHERE owner_id IS NULL;
    GET DIAGNOSTICS n_sentinels = ROW_COUNT;

    UPDATE signals SET owner_id = roman_id WHERE owner_id IS NULL;
    GET DIAGNOSTICS n_signals = ROW_COUNT;

    UPDATE trades SET owner_id = roman_id WHERE owner_id IS NULL;
    GET DIAGNOSTICS n_trades = ROW_COUNT;

    -- performance_scores no tiene owner_id directo (se accede vía sentinel_id)
    -- n_performance queda en 0 intencionalmente
    n_total := n_sentinels + n_signals + n_trades + n_performance;

    INSERT INTO migration_log (owner_id, records_migrated)
    VALUES (roman_id, n_total);

    RAISE NOTICE 'Migración completada: % sentinels, % signals, % trades. Total: % registros.',
        n_sentinels, n_signals, n_trades, n_total;
END;
$$;

-- Paso 3: Restaurar NOT NULL
ALTER TABLE sentinels ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE signals   ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE trades    ALTER COLUMN owner_id SET NOT NULL;
