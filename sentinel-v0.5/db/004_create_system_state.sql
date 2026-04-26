-- Migración 004: tabla system_state como canal IPC entre api.py y main.py
-- Fecha: 2026-04-26
-- Razón: api.py y main.py corren en procesos separados. Para que el botón
--        DETENER del dashboard pueda disparar dispatcher.activate_kill_switch()
--        necesitamos un canal compartido. PostgreSQL ya está en el path crítico
--        de ambos procesos, así que una tabla flag es la opción más simple
--        sin agregar dependencias (Redis, sockets) (#H-7).
-- Estado: para aplicar manualmente con psql como la migración 003.
--         No obstante, historian.connect() también ejecuta este DDL idempotente
--         al inicializar el pool — la migración existe como referencia histórica.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 004_create_system_state.sql

CREATE TABLE IF NOT EXISTS system_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO system_state (key, value) VALUES ('halt_requested', 'false')
ON CONFLICT (key) DO NOTHING;
