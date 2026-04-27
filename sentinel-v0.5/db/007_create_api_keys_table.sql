-- Migración 007: tabla api_keys para gestión visual de credenciales
-- Fecha: 2026-04-27
-- Razón: hoy las API keys (Alpaca, NewsAPI, Resend, Google OAuth, futuro
--        Anthropic) se editan manualmente en .env del servidor. El admin
--        necesita visualizar, ocultar (asteriscos) y rotar sin tocar el
--        filesystem. Las keys se guardan ENCRIPTADAS con Fernet usando
--        MASTER_ENCRYPTION_KEY del .env (#FIX-008).
--
--        Esta tabla es solo gestión visual + futura migración planificada.
--        En este branch el bot SIGUE leyendo desde .env — la sincronización
--        automática es un cambio de mayor riesgo que toca config.py y el
--        ciclo de vida del bot, fuera de scope.
--
-- Estado: aplicar manualmente con psql cuando se quiera empezar a usar
--         el panel admin. historian.connect() también ejecuta este DDL
--         idempotente para no requerir intervención manual.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 007_create_api_keys_table.sql

CREATE TABLE IF NOT EXISTS api_keys (
    key_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT         NOT NULL UNIQUE,
    encrypted_value TEXT         NOT NULL,
    description     TEXT,
    last_rotated_at TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_service_name ON api_keys(service_name);
