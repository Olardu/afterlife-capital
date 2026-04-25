# Sentinel v0.5

Sistema de trading algorítmico multi-agente. 9 estrategias autónomas (Sentinels) coordinadas por un Dispatcher, con protecciones macro, gestión de capital Half-Kelly y persistencia en PostgreSQL. Operación en paper trading hasta validar.

## Stack

- Python 3.14, asyncio
- PostgreSQL 18 nativo en Windows (servicio `postgresql-x64-18`)
- alpaca-py con feed IEX (paper)
- aiohttp + NewsAPI (macro)
- scikit-learn (RandomForest, S-10 desactivado)
- pandas (cálculos manuales de indicadores, sin ta-lib)
- LangGraph: planeado, todavía no implementado (loop manual en `main.py`)

## Componentes

| Archivo | Rol |
|---|---|
| `main.py` | Entry point, initialize() + main_loop() alineado a 15 min ET |
| `config.py` | Constantes y validación de credenciales |
| `historian.py` | Pool asyncpg, signals/trades, performance decay |
| `dispatcher.py` | Orquestador: kill-switch, sizing Half-Kelly, ejecución Alpaca |
| `the_ear.py` | NewsAPI cada 15min, VIXY/SPY change, Circuit Breaker, Parking Brake |
| `correlation_guard.py` | Pearson manual sobre rolling 60 velas, umbral 0.75 |
| `regime_classifier.py` | S-10 RandomForest BULL/NEUTRAL/BEAR — **DESACTIVADO** |
| `sentinels/__init__.py` | BaseSentinel + 9 estrategias |
| `db/schema.sql` | 7 tablas con multi-tenant `owner_id` |

## 9 Sentinels operativos

| # | Tipo | Lógica |
|---|---|---|
| S-1 | sma_crossover | Cruce SMA(10)/SMA(50) |
| S-2 | rsi_short | RSI(2): <15 BUY / >85 SELL |
| S-3 | bollinger_bounce | Cierre fuera de BB(20, 2σ) |
| S-4 | macd_volume | MACD(12,26,9) + volumen >1.5×SMA(20) |
| S-5 | orb_breakout | Opening Range Breakout 9:30 ET |
| S-6 | ema_triple | EMA 8>21>55 alineadas |
| S-7 | vwap_reversion | Cierre fuera de VWAP±2σ intraday |
| S-8 | rsi_divergence | Divergencia RSI(14) en swings (k=3) |
| S-9 | bollinger_squeeze | BBW percentil 10 + breakout |

S-10 (RegimeClassifier) está implementado pero desactivado con early returns documentados — accuracy 0.3849 sobre 3 clases es casi random. Reactivar cuando haya 50-100 trades reales y features adicionales (RSI, MACD, breadth, yield curve).

## Arrancar

```powershell
cd sentinel-v0.5
venv\Scripts\activate
python main.py
```

Requiere PostgreSQL servicio activo y `.env` con credenciales.

## Estado actual (2026-04-25)

✅ **Operativo y testeado**:
- DB con 9 Sentinels insertados (5% allocation cada uno, 45% total)
- Tests integración: The Ear, Dispatcher pipeline, run_cycle vacío — sin errores
- Pendiente: primera corrida real lunes 9:30 ET

## Decisiones clave

- **Sin Docker**: PostgreSQL 18 nativo en Windows (Docker Desktop fallaba en setup inicial).
- **Refactor BaseSentinel**: `fetch_bars`, `_fetch_bars_sync`, `run` centralizados. Cada Sentinel solo define `__init__` + `analyze`.
- **`feed=DataFeed.IEX` obligatorio**: la cuenta paper sin SIP da 403 al pedir datos recientes. Aplicado en los 4 sitios que hacen StockBarsRequest.
- **S-10 desactivado**: ahorra 30-60s de arranque (no descarga 25 años de SPY ni entrena RF). `get_regime()` retorna `"NEUTRAL"` fijo. Reactivar editando los early returns en `regime_classifier.py`.
- **RSI con SMA, no Wilder**: cálculo simplificado en `_rsi()`. Diferencia marginal vs Wilder smoothing — mejorar después si hace falta.
- **Logs**: `logs/sentinel.log` con RotatingFileHandler (5MB, 3 backups).

## Próximos pasos

1. Lunes 2026-04-27 9:30 ET: primera corrida real con mercado abierto
2. Implementar nodo LangGraph real en `main.py` (actualmente loop manual con `asyncio.gather`)
3. Mejorar `_rsi()` a Wilder smoothing (S-2, S-8)
4. Reactivar S-10 cuando criterios estén
5. Deploy a Raspberry Pi 5

## Bugs conocidos

- Ninguno bloqueante al cierre 2026-04-25.
- ORB y VWAP retornan `price=0.0` cuando no hay barras del día actual ET (sábado/domingo o pre-market). El `run()` filtra por `qty=0.0` así que no afecta el pipeline, pero es estéticamente raro en logs.

## Seguridad

- Multi-tenant: todo dato lleva `owner_id`. Owner actual: `roman` (UUID `***REMOVED-UUID***`).
- `.env` excluido de git y de Drive sync.
- NEWS_API_KEY enviado en header `X-Api-Key` (nunca en URL params).
- Kill-switch: `dispatcher.activate_kill_switch("CONFIRMAR")` requiere passphrase exacta.
