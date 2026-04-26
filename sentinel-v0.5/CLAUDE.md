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
| `api.py` | FastAPI backend (REST + SSE) en puerto 8080. Sirve dashboard estático. |
| `db/schema.sql` | 7 tablas con multi-tenant `owner_id` |
| `db/003_add_order_id_to_trades.sql` | Migración aplicada 2026-04-25: columna order_id en trades. |

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
- DB con 9 Sentinels insertados (5% allocation cada uno, 45% total). Multi-ticker: 27 tickers en `sentinel_tickers`.
- Tests integración: The Ear, Dispatcher pipeline, run_cycle vacío — sin errores
- API FastAPI en `localhost:8080` y `sentinel.afterlifecapital.co` (Cloudflare tunnel)
- Dashboard handoff Design integrado y conectado a `/api/*`
- Pendiente: primera corrida real lunes 9:30 ET

### Hardening post-auditoría (sesiones 1, 2 y 2.5 — 2026-04-25)

11 commits aplicados sobre `feature/design-handoff-integration`:
- `#H-2` Race en TheEar.evaluate → `asyncio.Lock`.
- `#H-3` Sin timeouts → asyncpg pool con `command_timeout=10`/`timeout=5` + `asyncio.wait_for(timeout=15)` en los 11 call sites de Alpaca.
- `#H-5` open_positions desync → refactor `list[dict]` → `dict[str, dict]` + check explícito de duplicado BUY.
- `#H-6` Limit orders bloqueaban cycle → migración 003 con `order_id`, `record_trade` lo persiste, `_check_later` background task con `asyncio.create_task` reconcilia tras 60s vía `update_trade_status(order_id=...)`.
- `_is_limit_strategy` → set explícito (5 estrategias mean-reversion-like).
- `approved` ahora es `status == "FILLED"`, no `!= "CANCELLED"` (PENDING ya no se cuenta).
- `done_callback` en ear_task para detectar fallas silenciosas.

Issues 🟠 ALTOS pendientes (3): `#H-1` API sin auth, `#H-4` float→Decimal en cálculos, `#H-7` kill switch operacional inaccesible.

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
- `record_trade` falla si la migración 003 no se aplicó (no validamos schema al startup). Aplicada manualmente en local.
- `update_trade_status` no warns si 0 rows afectados (ej. order_id no existe en DB).
- `record_trade` se hace en el mismo try que `record_signal`; si `record_signal` falla, la orden ya está en Alpaca pero sin fila DB.
- Reconciliación post-restart de limit orders: si el sistema cae con tasks `_check_later` en vuelo, mueren con el proceso. La orden Alpaca queda activa pero sin tracking. TODO en `dispatcher.execute_order`.

## Seguridad

- Multi-tenant: todo dato lleva `owner_id`. Owner actual: `roman` (UUID `***REMOVED-UUID***`).
- `.env` excluido de git y de Drive sync.
- NEWS_API_KEY enviado en header `X-Api-Key` (nunca en URL params).
- Kill-switch: `dispatcher.activate_kill_switch("CONFIRMAR")` requiere passphrase exacta.
