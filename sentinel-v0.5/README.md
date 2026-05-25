# SENTINEL v0.5 — Afterlife Capital

Infraestructura de inversión autónoma multi-agente para paper trading.

## Stack

- Python 3.11+
- LangGraph (orquestación de agentes)
- PostgreSQL (persistencia vía asyncpg)
- Alpaca Markets (ejecución paper trading, feed IEX)
- NewsAPI (contexto macro)
- scikit-learn (Regime Classifier)

## Arquitectura

5 agentes principales operando sobre un grafo LangGraph:

| Agente | Archivo | Responsabilidad |
|---|---|---|
| Dispatcher | dispatcher.py | Orquestador central, Half-Kelly sizing |
| CorrelationGuard | correlation_guard.py | Anti-concentración, correlación rolling 60 velas |
| The Ear | the_ear.py | Contexto macro, Circuit Breaker, Parking Brake |
| Historian | historian.py | Memoria PostgreSQL, feedback loop, decay |
| Regime Classifier | regime_classifier.py | Clasifica sesión BULL / NEUTRAL / BEAR |

Los Sentinels (`sentinels/`) son agentes de estrategia independientes.
S-1 SMA Crossover implementado. S-2 a S-10 por definir.

## Setup

1. Instalar dependencias: `pip install -r requirements.txt`
2. Copiar `.env.example` a `.env` y completar con credenciales reales
3. Levantar PostgreSQL y ejecutar `db/schema.sql`
4. Crear usuario Roman en tabla `users`
5. Ejecutar: `python main.py`

## Estructura de archivos

```
sentinel-v0.5/
├── .env.example              # Variables de entorno requeridas (sin valores reales)
├── config.py                 # Configuración central — credenciales y parámetros del sistema
├── main.py                   # Entry point — inicializa y orquesta el grafo LangGraph
├── dispatcher.py             # Agente orquestador central, distribución de capital Half-Kelly
├── correlation_guard.py      # Módulo anti-concentración, correlación rolling 60 velas
├── the_ear.py                # Agente macro: NewsAPI, Circuit Breaker, Parking Brake
├── historian.py              # Memoria PostgreSQL, performance scores, feedback loop
├── regime_classifier.py      # S-10 meta-agente, clasifica sesión BULL/NEUTRAL/BEAR
├── requirements.txt          # Dependencias del proyecto
├── sentinels/
│   └── __init__.py           # BaseSentinel (ABC) + S-1 SMA Crossover + SENTINEL_REGISTRY
├── db/
│   ├── schema.sql            # Esquema PostgreSQL completo (7 tablas)
│   └── migrate_retroactive.sql  # Script ONE-TIME para datos pre-existentes
└── logs/
    └── .gitkeep              # Directorio de logs (sentinel.log se genera en runtime)
```

## Reglas de seguridad

- Arquitectura multi-tenant: todo registro lleva `owner_id` (UUID)
- Kill Switch global con confirmación de dos pasos (`"CONFIRMAR"`)
- Circuit Breaker automático: VIX +30% o SPY -2% en 15 min
- Parking Brake: sin nuevas órdenes después de las 15:45 ET
- Paper trading con Alpaca IEX — sin dinero real hasta validar

## Heartbeat / monitoreo (#OP-2)

El loop principal pinga un check externo (healthchecks.io) al final de cada ciclo
de 15 min. Si el bot se cae o se cuelga, healthchecks.io deja de recibir pings y
alerta por email/SMS. Es best-effort: un fallo de red en el ping se loggea como
warning y **no** interrumpe el trading.

Configuración (opcional, flag-gated — vacío = deshabilitado):

1. Crear una cuenta gratuita en https://healthchecks.io/
2. Crear un check para "Sentinel bot main loop" con período esperado ~15 min
   (+ grace) y configurar la alerta por email.
3. Copiar la URL de ping (formato `https://hc-ping.com/<UUID>`).
4. Agregar al `.env`: `HEARTBEAT_URL=https://hc-ping.com/<UUID>`
5. Reiniciar `main.py`. El bot empieza a pinguear una vez por ciclo.

## Sentiment analysis FinBERT (#FEAT-007 / The Ear)

The Ear puede complementar el keyword matching con sentiment finance-tuned
(modelo `ProsusAI/finbert`) cuando `THE_EAR_SENTIMENT_ENABLED=true`. El modelo se
carga lazy al primer uso y corre 100% local en CPU (sin red ni costo recurrente).

Setup (una vez, tras `pip install -r requirements.txt`):

1. Las deps `torch`/`transformers` ya vienen en `requirements.txt` (CPU build).
2. Pre-descargar el modelo (~440 MB → `~/.cache/huggingface/`) para evitar latencia
   en el primer ciclo:
   ```
   python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='ProsusAI/finbert')"
   ```
3. Activar en `.env`: `THE_EAR_SENTIMENT_ENABLED=true` (default `false`).
   Opcional: `THE_EAR_FINBERT_VETO_THRESHOLD=-0.6` (umbral de veto, a calibrar).
4. Reiniciar `main.py`. Si el modelo no carga, The Ear cae automáticamente al
   keyword matching legacy (no rompe el bot).

> **Nota de versiones:** se usa `torch 2.9.1+cpu` / `transformers 5.9.0` /
> `ProsusAI/finbert` (la spec original pedía torch 2.5.0 / transformers 4.45 /
> finbert-tone — incompatibles con Python 3.14). Plan de recalibración del umbral
> en `docs/finbert_recalibration_plan.md`.

## Versionado

| Versión | Estado | Descripción |
|---|---|---|
| v0.5 | En construcción | Arquitectura completa en local |
| v0.7 | Pendiente | Paper trading activo validado |
| v1.0 | Pendiente | Operacional |

## Autor

Diseñado y arquitectado por el equipo de Afterlife Capital.
Código generado con asistencia de IA.
Proyecto Afterlife Capital.
