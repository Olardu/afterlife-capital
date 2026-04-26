# AUDIT_FULL — Sentinel v0.5

Fecha: 2026-04-25
Branch auditado: `feature/design-handoff-integration`
Commit HEAD: `3479310`
Scope: Tier 1 + Tier 2

Archivos efectivamente leídos y auditados:
- `sentinel-v0.5/api.py` (576 líneas)
- `sentinel-v0.5/the_ear.py` (293 líneas)
- `sentinel-v0.5/dispatcher.py` (639 líneas)
- `sentinel-v0.5/historian.py` (438 líneas)
- `sentinel-v0.5/config.py` (118 líneas)
- `sentinel-v0.5/correlation_guard.py` (268 líneas)
- `sentinel-v0.5/regime_classifier.py` (288 líneas)
- `sentinel-v0.5/main.py` (337 líneas)
- `sentinel-v0.5/sentinels/__init__.py` (parcial — clase base, helpers, registry)
- `dashboard/index.html` (HTML+CSS handoff Design v2)
- `dashboard/sentinel-data.js` (482 líneas — contenido propio)
- `dashboard/sentinel-app.js` (424 líneas — handoff Design)

## Resumen Ejecutivo

| Severidad | Cantidad |
|-----------|----------|
| 🔴 CRÍTICO | **0** |
| 🟠 ALTO | **7** |

**Top 3 issues más urgentes** (no priorizo entre ellos — los tres deben resolverse antes de v2.5/live):

1. **API pública sin autenticación** en sentinel.afterlifecapital.co. Todos los `/api/*` (incluyendo `/api/report` que descarga JSON con trades + estrategias) son legibles desde cualquier origen sin token. Para paper no hay daño material; para live es leak de edge competitivo.
2. **Race condition en `TheEar.evaluate()`** entre `start_polling()` (task background) y `Dispatcher.run_cycle()` (task principal). Mutación concurrente de estado compartido (`circuit_breaker_active`, `last_risk_score`, `_last_vix_change`) sin lock + duplicación de filas en `macro_events`.
3. **Sin timeouts en `asyncpg` pool ni en llamadas Alpaca**. Una query DB colgada o un Alpaca outage congela el sistema en silencio: el bot deja de operar y nadie se entera porque no hay watchdog.

---

## Issues 🟠 Altos

### #H-1: API sin autenticación expuesta vía Cloudflare tunnel

- **Archivo:** `sentinel-v0.5/api.py:118-124` (configuración CORS y app); todos los endpoints `/api/*`
- **Categoría:** Seguridad
- **Descripción:** La API se sirve en `sentinel.afterlifecapital.co` (subdominio público). Ningún endpoint exige autenticación: `/api/status`, `/api/sentinels`, `/api/trades`, `/api/macro`, `/api/performance`, `/api/report`, `/api/sse`. CORS abierto a `*` con `allow_credentials=False` (lo cual descarta CSRF clásico, pero no oculta los datos). Cualquiera que conozca el subdominio puede leer el estado completo del sistema y descargar el JSON de reporte con todos los trades y estrategias.
- **Impacto:**
  - **Hoy (paper):** revela qué estrategias usás (los 9 nombres + strategy_type), qué tickers operás, win_rate y sharpe por (sentinel, ticker), y todo el historial de trades. No hay daño material directo, pero rompe la "security through obscurity" del subdominio.
  - **En live trading (v2.5+):** los mismos datos son edge competitivo. Cualquiera puede automatizar scraping de las decisiones del sistema y front-runnear o copiar.
  - **Botón STOP futuro:** el handoff diseña `POST /api/system/halt`. Si se agrega sin auth, **cualquiera para el bot**.
- **Reproducción:** desde otra máquina: `curl https://sentinel.afterlifecapital.co/api/report?range=all > leak.json` — descarga el reporte completo sin credenciales.
- **Recomendación:**
  Agregar middleware de autenticación. Patrón mínimo viable con `X-API-Key`:
  ```python
  # api.py — agregar después de CORS middleware
  from fastapi import Request
  from fastapi.responses import JSONResponse

  API_KEY = os.environ.get("DASHBOARD_API_KEY")  # nuevo en .env
  PUBLIC_PATHS = {"/", "/sentinel-app.js", "/sentinel-data.js", "/sentinel-i18n.js"}

  @app.middleware("http")
  async def require_api_key(request: Request, call_next):
      path = request.url.path
      if path.startswith("/assets/") or path in PUBLIC_PATHS:
          return await call_next(request)
      if path.startswith("/api/"):
          if request.headers.get("X-API-Key") != API_KEY:
              return JSONResponse({"error": "unauthorized"}, status_code=401)
      return await call_next(request)
  ```
  En `dashboard/sentinel-data.js` `_fetchJson`, agregar `headers: {"X-API-Key": <key>}` leído de `localStorage.getItem('sentinel.apikey')` con prompt al primer load.

---

### #H-2: Race condition en `TheEar.evaluate()` — doble llamada concurrente

- **Archivo:** `sentinel-v0.5/the_ear.py:226-276` y `sentinel-v0.5/dispatcher.py:578-582` (caller A) + `sentinel-v0.5/main.py:310-313` (caller B vía `start_polling`)
- **Categoría:** Bug / Estabilidad
- **Descripción:** `TheEar.evaluate()` es llamado desde dos tasks concurrentes:
  - `dispatcher.run_cycle()` línea 579 — task principal cada 15 min en horario de mercado.
  - `the_ear.start_polling()` línea 287-292 — task background que corre `await self.evaluate()` cada `NEWS_FETCH_INTERVAL_SECONDS` (también 15 min).

  Como ambos intervalos son 15 min y ambos arrancan al mismo tiempo en `main.main()` línea 305, eventualmente caen en la misma ventana. Dentro de `evaluate()` se mutan sin lock:
  - `self.last_risk_score` (línea 247)
  - `self._last_vix_change`, `self._last_spy_change` (línea 142-143)
  - `self.circuit_breaker_active` (línea 161)
  - `self.parking_brake_active` (línea 223)

  Además, ambos llaman `self.historian.record_macro_event()` (línea 254) — generan **filas duplicadas** en `macro_events` con timestamps muy cercanos.
- **Impacto:** En live trading, una de las dos llamadas puede dejar `circuit_breaker_active = False` cuando la otra acaba de detectar VIX +30% (porque la otra ya sobreescribió el flag al final de su evaluate). El Dispatcher consulta el flag inconsistente y procesa señales que debería bloquear. Adicionalmente, `/api/macro` devuelve eventos duplicados y el dashboard renderiza las mismas líneas dos veces.
- **Recomendación:**
  Agregar `asyncio.Lock` en `TheEar`:
  ```python
  # the_ear.py
  class TheEar:
      def __init__(self, historian: Historian):
          # ... existente ...
          self._eval_lock = asyncio.Lock()

      async def evaluate(self) -> dict:
          async with self._eval_lock:
              # ... cuerpo existente sin cambios ...
  ```
  Eso garantiza ejecución secuencial. Si el costo de esperar el lock es inaceptable, alternativa: eliminar la doble fuente — quitar `start_polling()` y dejar que `dispatcher.run_cycle()` sea la única fuente de evaluate. Pero ojo: `start_polling()` corre 24/7, `run_cycle()` solo en horario; sacarlo perdería heartbeat fuera de mercado.

---

### #H-3: Sin timeouts en `asyncpg` pool ni en llamadas Alpaca

- **Archivo:** `sentinel-v0.5/historian.py:31-35` (pool), `sentinel-v0.5/dispatcher.py:62/250/396/415/519` (Alpaca via `to_thread`), `sentinel-v0.5/correlation_guard.py:43`, `sentinel-v0.5/the_ear.py:141`, `sentinel-v0.5/regime_classifier.py:171`, `sentinel-v0.5/sentinels/__init__.py:93`
- **Categoría:** Estabilidad
- **Descripción:** `asyncpg.create_pool()` se llama sin `command_timeout` ni `timeout`. Si una query queda colgada (lock, deadlock parcial, conexión muerta sin TCP RST), la corutina nunca retorna y eventualmente drena las 10 conexiones del pool. El sistema deja de procesar señales sin error visible.

  Lo mismo aplica a Alpaca: cada `asyncio.to_thread(self._fetch_bars_sync)` o `_submit_order_sync` cuelga el thread del executor si Alpaca no responde. ThreadPoolExecutor por default tiene `min(32, os.cpu_count()+4)` workers — saturable rápidamente con 9 sentinels × 3 tickers + correlation_guard + the_ear pidiendo bars en paralelo.
- **Impacto:** En live trading, un Alpaca outage de 60s o un problema en PostgreSQL cuelga el sistema. El dashboard sigue mostrando datos viejos vía SSE (que también queda colgado). No hay watchdog que detecte el hang. Roman se entera cuando ve que no hay trades nuevos.
- **Recomendación:**
  Para asyncpg:
  ```python
  # historian.py:31
  self.pool = await asyncpg.create_pool(
      dsn=self.database_url,
      min_size=2,
      max_size=10,
      command_timeout=10,           # query individual
      timeout=5,                    # acquire connection
  )
  ```
  Para Alpaca, envolver cada `asyncio.to_thread` en `asyncio.wait_for`:
  ```python
  # patrón para todos los call sites
  try:
      result = await asyncio.wait_for(
          asyncio.to_thread(self._submit_order_sync, ...),
          timeout=15.0,
      )
  except asyncio.TimeoutError:
      logger.error("Alpaca timeout")
      return {"status": "CANCELLED", ...}
  ```
  Hay 6 sitios con `asyncio.to_thread` que requieren este wrapper.

---

### #H-4: Cálculos financieros con `float` en lugar de `Decimal`

- **Archivo:** `sentinel-v0.5/dispatcher.py:255-258` (sizing), `sentinel-v0.5/historian.py:201-213` (returns/sharpe), `sentinel-v0.5/dispatcher.py:314-317` (slippage)
- **Categoría:** Bug
- **Descripción:** Todo cálculo monetario usa `float`:
  - `dispatcher.py:256`: `max_dollar_value = account_equity * (sentinel_alloc / 100.0)`
  - `dispatcher.py:257`: `max_qty = max_dollar_value / price`
  - `dispatcher.py:315`: `slippage = order_result["filled_price"] - price`
  - `historian.py:202`: `(sell.filled_price - buy.filled_price) / buy.filled_price`

  En el schema `db/schema.sql`, las columnas son `DECIMAL(10,4)`. asyncpg las devuelve como `Decimal` y los `float()` casts las degradan a precisión binaria. Para shares enteras de tickers populares no se nota; para activos de alto valor (NVDA $138, TSLA $412) en cuentas con > $1M, errores acumulables.
- **Impacto:**
  - Drift entre lo que reporta Sentinel vs lo que reporta Alpaca. Performance scores divergen ligeramente.
  - En live trading con shares fraccionales (Alpaca lo permite), el `min(qty, max_qty)` puede emitir `qty=2.0000000001` que Alpaca rechaza por overflow del notional.
  - Reconciliación manual al cierre del día.
- **Recomendación:**
  Tipar las funciones financieras con `Decimal` en lugar de `float` desde el ingreso a `dispatcher.process_signal`. Patrón:
  ```python
  # dispatcher.py:173 — cambiar firma
  from decimal import Decimal

  async def process_signal(
      self, ...,
      price: Decimal,
      qty: Decimal,
      ...
  ):
      # toda la aritmética interna con Decimal
      max_dollar_value = Decimal(account_equity) * (Decimal(sentinel_alloc) / Decimal(100))
      max_qty = max_dollar_value / Decimal(price)
      qty = min(qty, max_qty)
      ...
  ```
  En el call site (`dispatcher.run_cycle:603-610`), convertir las señales de los Sentinels (que actualmente devuelven floats) a Decimal antes de pasar.
  Misma transformación para `historian.calculate_performance` línea 201-213.

---

### #H-5: `Dispatcher.open_positions` se desincroniza intra-cycle (potencial doble-compra)

- **Archivo:** `sentinel-v0.5/dispatcher.py:50, 287-293, 334-341, 567-568`
- **Categoría:** Bug
- **Descripción:** `self.open_positions` es una `list[dict]`. El sync con Alpaca ocurre solo al inicio de cada `run_cycle` (línea 568). Dentro del for de `pending_signals` (línea 603), por cada señal procesada se hace `process_signal()` y, si el order fue FILLED, se hace `self.open_positions.append(...)` (línea 336). El `has_position` check para SELL (línea 289) lee la lista local. Pero si dos sentinels distintos emiten BUY del mismo ticker en el mismo cycle, ambos pasan por el pipeline secuencialmente:
  1. Sentinel A emite BUY SPY qty=10. Pipeline procesa, append a `open_positions`.
  2. Sentinel B emite BUY SPY qty=8. Pipeline ve `open_positions` con SPY (qty=10), pero no chequea duplicado para BUY (solo para SELL `no_open_position`). Procesa otra orden BUY SPY qty=8.
  Resultado: dos órdenes BUY SPY consecutivas. CorrelationGuard ve correlación 1.0 (mismo ticker en open_positions) y reduce qty con `reduction_factor`, pero si la segunda señal viene de un Sentinel con sharpe alto, la reducción puede no ser suficiente para descartar. Capital duplicado en SPY.
- **Impacto:** En live trading: sobre-exposición a un mismo ticker. Viola el spirit del CorrelationGuard ("anti-concentración") porque el caso "mismo ticker" no se trata como descarte explícito sino como reducción proporcional.
- **Recomendación:**
  Cambiar `open_positions` de `list[dict]` a `dict[str, dict]` indexado por ticker. En `process_signal` línea 287, agregar check explícito:
  ```python
  side = "BUY" if signal_type == "BUY" else "SELL"

  # NUEVO: descartar BUY si ya hay posición abierta del mismo ticker
  if side == "BUY" and ticker in self.open_positions:
      logger.info(f"Señal BUY {ticker} omitida — ya hay posición abierta este cycle.")
      return {**base_result, "reason": "duplicate_ticker_buy"}

  if side == "SELL":
      if ticker not in self.open_positions:
          # ...
  ```
  Cambiar todo el código que itera `for p in self.open_positions` para usar `for ticker, p in self.open_positions.items()`. `_get_alpaca_positions` debe devolver dict.

---

### #H-6: Limit orders bloquean el procesamiento de las señales restantes 60s

- **Archivo:** `sentinel-v0.5/dispatcher.py:411-418, 603-613`
- **Categoría:** Bug / Estabilidad
- **Descripción:** Cuando `process_signal()` detecta strategy_type que matchea `_is_limit_strategy` (substring `mean_reversion` o `pairs`), `execute_order` envía limit + `await asyncio.sleep(60)` (línea 412) + check + cancel. Esto bloquea el procesamiento del resto de señales en el cycle, porque `run_cycle:603` itera `pending_signals` con `for ... await process_signal(...)` (secuencial).

  Con 9 sentinels × 3 tickers = hasta 27 señales potenciales por cycle. Si en un cycle hay 4 señales de mean_reversion, son 4 × 60s = 240s solo de esperas. El cycle de 15min se desincroniza: la señal #5 se procesa después del próximo cycle haya empezado, generando solapamiento.
- **Impacto:** Pérdida de oportunidades. La señal #N se ejecuta minutos después del precio de señal, generando slippage adicional. En live, esto invalida la lógica de mean reversion (que asume entrada inmediata al cruzar el threshold).
- **Recomendación:**
  Disparar el wait del limit en background con `asyncio.create_task`. Patrón:
  ```python
  # dispatcher.py — execute_order, después del submit
  if not is_limit:
      return submit_result

  order_id = submit_result.get("order_id")
  if not order_id:
      return submit_result

  # Lanzar verificación en background — no bloquear el cycle
  async def _check_later(oid):
      await asyncio.sleep(60)
      try:
          final = await asyncio.to_thread(self._check_and_cancel_limit_sync, oid)
          # actualizar trade en DB con final["status"] y filled_price
          # vía historian.update_trade_status (ya existe)
      except Exception as e:
          logger.error(f"Limit check {oid}: {e}")

  asyncio.create_task(_check_later(order_id), name=f"limit_check_{order_id}")
  return submit_result   # devuelve PENDING inmediatamente, el sleep no bloquea
  ```
  Requiere también que `historian.record_trade` acepte status `PENDING` (ya lo hace, schema lo permite — línea 84) y que `update_trade_status` se llame al completar el background task.

---

### #H-7: No hay forma operacional de activar el kill switch en producción

- **Archivo:** `sentinel-v0.5/dispatcher.py:505-543`, `sentinel-v0.5/api.py` (todo)
- **Categoría:** Seguridad / Estabilidad
- **Descripción:** `Dispatcher.activate_kill_switch(confirmation)` y `deactivate_kill_switch(confirmation)` existen pero no están expuestos en ningún endpoint de la API ni hay CLI/script para invocarlos. El botón "DETENER" del dashboard (`sentinel-app.js:403`) sólo hace `alert('SISTEMA DETENIDO (demo)')`. Si Roman necesita parar el bot por una emergencia (movimiento extremo, datos corruptos), tiene que SSH al server y matar el proceso o ejecutar Python interactivo para llamar al método.
- **Impacto:** Sin kill switch funcional, no hay safety net operacional. En live trading esto es regla #1: tiene que haber un botón rojo que funcione en menos de 30s.
- **Recomendación:**
  Agregar endpoint POST a la API con auth (depende de #H-1). Mínimo:
  ```python
  # api.py
  from pydantic import BaseModel

  class HaltRequest(BaseModel):
      confirmation: str

  @app.post("/api/system/halt")
  async def halt(req: HaltRequest, request: Request):
      # auth ya cubre con middleware de #H-1
      # importar Dispatcher requiere refactor — exponerlo via lifespan
      from main import _system   # o cargar el dispatcher en lifespan
      await _system["dispatcher"].activate_kill_switch(req.confirmation)
      return {"halted": _system["dispatcher"].kill_switch_active}
  ```
  El dashboard `sentinel-app.js:403` debe enviar `POST` con `{"confirmation": "CONFIRMAR"}`. Considerar también cancelación remota desde `main.py` — el dispatcher hoy lo maneja synchronously.

  **Dependencia:** este endpoint requiere primero #H-1 (auth) — sin auth, cualquiera detiene el bot.

---

## Notas finales

### Limitaciones de la auditoría

- **Sin runtime check del comportamiento bajo carga.** No se ejecutó stress testing ni se observó memoria/CPU bajo trades reales. Las race conditions y leaks potenciales se infirieron del código.
- **No se auditó la configuración de Cloudflare tunnel ni del firewall.** Si Cloudflare tiene Access policies activas (auth a nivel edge), eso mitigaría #H-1 sin tocar código. Pero según contexto del usuario, no parece estar habilitado.
- **No se auditó `db/schema.sql`** (estaba en TIER 2 implícito pero no listado). Las constraints `UNIQUE` y `FK` impactan algunos issues; revisarlo da contexto adicional.
- **`dashboard/sentinel-app.js` proviene del handoff** (no se modifica por regla). Cualquier issue ahí (innerHTML sin escape, etc.) se reporta como TECHDEBT — no se puede arreglar localmente sin rehacer el handoff.

### Orden sugerido de fixes (con dependencias)

1. **#H-1 (auth API)** — primero. Bloquea #H-7. Trabajo: ~3-4h (middleware + cliente + .env).
2. **#H-7 (kill switch operacional)** — depende de #H-1. ~2-3h.
3. **#H-2 (race the_ear)** — independiente. ~30min (un asyncio.Lock).
4. **#H-3 (timeouts)** — independiente. ~1-2h (varios call sites).
5. **#H-5 (open_positions desync)** — independiente. ~2-3h (refactor a dict + tests manuales).
6. **#H-6 (limit orders bloqueantes)** — depende parcialmente de cambios en historian (update_trade_status, ya existe). ~3-4h.
7. **#H-4 (Decimal vs float)** — más invasivo. Hacer al final, antes de live. ~4-6h (toca varios módulos).

**Tiempo total estimado para resolver los 7 ALTOS:** 16-25 horas de desarrollo + testing manual.

Si Roman puede dedicar **una jornada completa** (8h), prioridad sería: #H-2, #H-3, #H-5 (los tres bugs operacionales que ya muerden hoy en paper). #H-1, #H-7, #H-6, #H-4 se hacen en una segunda jornada antes de v2.5/live.

### Issues NO encontrados (verificados)

- **SQL injection:** todas las queries usan parámetros `$N` de asyncpg. El f-string en `api.py:315` (`/api/trades`) interpola sólo números (`${len(params)}`), no input de usuario.
- **Path traversal:** `StaticFiles(directory=str(DASHBOARD_DIR))` con path resuelto. No hay endpoints que escriban archivos.
- **Credenciales hardcoded:** todo viene de env vars vía `config.py`. Cero strings tipo `sk_live_...` en el código.
- **CSRF:** todos los endpoints son GET. No hay endpoints state-changing en producción (kill switch es interno).
- **Validación de query params:** `Query(..., ge=1, le=500)`, `Query(..., regex=...)`, UUID parse con try/except. OK.
