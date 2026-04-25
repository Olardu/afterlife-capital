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

## Versionado

| Versión | Estado | Descripción |
|---|---|---|
| v0.5 | En construcción | Arquitectura completa en local |
| v0.7 | Pendiente | Paper trading activo validado |
| v1.0 | Pendiente | Operacional |

## Autor

Diseñado y arquitectado por Roman Olarte.
Código generado con asistencia de IA.
Proyecto Afterlife Capital — Cambio de Ruta.
