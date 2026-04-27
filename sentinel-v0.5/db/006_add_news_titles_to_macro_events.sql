-- Migración 006: agregar columna news_titles a macro_events
-- Fecha: 2026-04-27
-- Razón: The Ear hace keyword matching sobre NewsAPI y persiste un risk_score
--        agregado, pero los titulares específicos que levantaron el score se
--        descartaban. Sin ellos no se puede auditar por qué se redujo el
--        trading en un momento dado. La columna news_titles guarda los TOP 5
--        titulares con mayor contribución al score (#FIX-007).
-- Estado: idempotente — se puede re-aplicar sin riesgo.
--         historian.connect() también ejecuta este DDL al inicializar el pool,
--         así que se aplica automáticamente al próximo restart del bot/API.
--
-- Para reproducir en otro entorno:
--   psql $DATABASE_URL -f 006_add_news_titles_to_macro_events.sql

ALTER TABLE macro_events
    ADD COLUMN IF NOT EXISTS news_titles JSONB NOT NULL DEFAULT '[]'::jsonb;
