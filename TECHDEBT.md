# TECHDEBT — OBSOLETO desde 2026-05-25

> **🚨 ARCHIVO OBSOLETO. NO AGREGAR ITEMS ACÁ.**
>
> Todo el contenido de este archivo fue migrado a `BACKLOG.md` (raíz del repo) el 2026-05-25 con sus IDs `#TD-N` preservados. Una sola fuente de verdad, organizable por tipo y prioridad.
>
> Este archivo queda como **referencia histórica** de la auditoría 2026-04-25. **Para acción operativa: ir a `BACKLOG.md` sección P2.**

---

# Contenido histórico (consolidado en BACKLOG.md el 2026-05-25)

Issues 🟡 medios y 🟢 bajos detectados durante la auditoría 2026-04-25.
**No priorizados.** Referencia para futuro refactor — abordar en bloques cuando se toque cada módulo.

---

## sentinel-v0.5/api.py

- **🟡 línea 390**: `Query(..., regex="^(today|...)$")` — `regex` está deprecated en FastAPI 0.110+ a favor de `pattern`. Genera DeprecationWarning. Cambio: `Query(..., pattern="^(today|...)$")`.
- **🟡 línea 454, 515**: `datetime.utcnow()` deprecated en Python 3.12+. Reemplazar por `datetime.now(timezone.utc)`.
- **🟡 línea 116**: `app = FastAPI(title="SENTINEL v0.5 API", lifespan=lifespan)` — falta `version` parameter. Util para `/docs` y para el header del JSON de OpenAPI.
- **🟡 línea 60-66**: `RotatingFileHandler(filename="logs/api.log", ...)` — path relativo. Si uvicorn arranca desde otro directorio (CWD distinto), crea `logs/api.log` en ese otro dir. Resolver con `Path(__file__).parent / "logs" / "api.log"`.
- **🟡 línea 106**: `logger.info(f"... owner_id={_owner_id} ...")` — loggea UUID en cada start. No es secret pero es PII de bajo nivel. Considerar enmascarar primeros 8 chars.
- **🟡 línea 524-540**: SSE `event_generator` no detecta cliente desconectado explícitamente. sse-starlette debería propagar `asyncio.CancelledError` cuando el cliente cierra; verificar comportamiento bajo Cloudflare tunnel (proxy puede mantener la conexión "viva" más allá del cliente real).
- **🟡 línea 219-290**: `/api/sentinels` itera todos los rows en Python para agrupar. Para 9 sentinels × 3 tickers no es problema; con 50+ sentinels podría ser O(n²). Optimizar con `array_agg` en SQL si crece.
- **🟢 línea 174**: `_http_500` siempre lanza. La mayoría de los call sites no necesitan ese helper porque el except ya hace `raise HTTPException`. Refactor cosmético.
- **🟢 línea 491**: `_SSE_INTERVAL_SECONDS = 900` debería estar en `config.py` no acá.
- **🟢 línea 552-568**: comentario "El mount en '/' debe ser el ÚLTIMO add" es correcto pero StaticFiles también captura HEAD/OPTIONS — verificar que `OPTIONS /api/*` no se mountee como static (parece que FastAPI lo resuelve antes).
- **🟢 línea 462-464**: `system_health` con `uptime_seconds: None` — TODO declarado. Trackear desde un `STARTUP_AT = datetime.utcnow()` global.

---

## sentinel-v0.5/the_ear.py

- **🟡 línea 33-40**: keywords lists hardcoded en inglés. Si NewsAPI devuelve artículos en otro idioma, no detecta. Para v0.5 OK; para internacionalizar requiere lista por idioma.
- **🟡 línea 122**: `raw = (neg_hits - pos_hits * 0.5) / len(articles)` — heurístico simple. El score depende del número de artículos: 1 keyword negativa en 1 artículo = 1.0, en 20 artículos = 0.05. Documentado como "suficiente para v0.5". TODO: pasar a sentiment analysis real (HuggingFace pipeline o similar) cuando haya tiempo.
- **🟡 línea 60**: `if not NEWS_API_KEY: ... return []` — silently skips. Mejor levantar warning + métrica para que se vea en logs centralizados.
- **🟡 línea 195-200**: `pct_change` retorna 0.0 si no hay 2 barras. Eso enmascara fallas de datos como "todo está bien". Distinguir "sin datos" de "0% change" devolviendo `None`.
- **🟢 línea 75**: `aiohttp.ClientSession()` se crea por cada `fetch_news` call. Reutilizar una session compartida ahorra TCP handshake repetido. Microoptimización.

---

## sentinel-v0.5/dispatcher.py

- **🟡 línea 287**: `side = "BUY" if signal_type == "BUY" else "SELL"` — defensa débil. Si signal_type llega como `"HOLD"` (no debería pero podría), genera un SELL. Validar al inicio: `if signal_type not in ("BUY", "SELL"): return {"reason": "invalid_signal"}`.
- **🟡 línea 363**: `_is_limit_strategy` matchea por substring. `"mean_reversion" in st or "pairs" in st` es frágil. Por ejemplo `bollinger_bounce` (es mean reversion) NO matchea — su strategy_type no contiene la palabra. Usar set explícito:
  ```python
  _LIMIT_STRATEGIES = {"bollinger_bounce", "rsi_short", "vwap_reversion"}
  ```
- **🟡 línea 220-225**: el fallback `ear_state = {"can_trade": False, ...}` cuando `the_ear.evaluate()` falla — bloquea operaciones. Defensa correcta pero silencioso. Loggear como `CRITICAL` no `error`, porque significa el bot no opera.
- **🟡 línea 247**: `sentinel_alloc = allocation.get(str(sentinel_id), MIN_CAPITAL_PER_SENTINEL)` — si el `sentinel_id` no está en allocation (porque `allocate_capital` solo devuelve los que tienen score), default a 5%. OK pero ese fallback debería loggearse para que sea evidente que el sentinel está en warmup.
- **🟡 línea 343**: `approved = order_result.get("status") != "CANCELLED"` — si status es `PENDING`, `approved=True`. Confuso: pendiente no es aprobado. Cambiar a `approved = order_result.get("status") == "FILLED"`.
- **🟡 línea 567-568**: `await self.sync_positions_from_alpaca()` en cada run_cycle. Si Alpaca está lento, retrasa todo. Podría hacerse async paralelo con el resto del init de cycle.
- **🟢 línea 50**: `self.open_positions: list[dict]` con docstring inline. Mover a un dataclass `Position` para tipado fuerte.
- **🟢 línea 134**: `kelly_adjusted = base * KELLY_FRACTION` — el `base` ya es proporcional al sharpe, multiplicar por 0.5 es Half-Kelly conceptual pero no necesariamente lo que dice la teoría (Kelly clásico: `f = p - q/b`). Validar la fórmula con un quant antes de live.
- **🟢 línea 526**: `KILL SWITCH ACTIVADO — cerrando todas las posiciones.` — el log no incluye PNL final ni qty cerradas. Útil agregar para post-mortem.

---

## sentinel-v0.5/historian.py

- **🟡 línea 162-219**: `calculate_performance` con pareo FIFO documentado como "limitación v0.5" línea 189-192. Si un Sentinel emite BUY-BUY-SELL, el segundo BUY queda huérfano y se descarta. OK por ahora porque `last_signal` previene duplicados consecutivos, pero si un Sentinel cambia ticker entre dos BUYs (multi-ticker), el pareo se rompe. Actualizar a pareo por ticker dentro del cálculo.
- **🟡 línea 207-213**: cálculo de Sharpe sin annualization. Sharpe "verdadero" multiplica por `sqrt(N_periods_per_year)`. Para 15min bars en mercado equity = sqrt(252 * 26) ≈ 81. Sin esa conversión, el threshold `SHARPE_MINIMUM = 0.5` está en escala de Sharpe per-period, no per-year.
- **🟡 línea 240-245**: warmup retorna False sin insertar en `performance_scores`. Esto significa que `/api/performance` está vacío hasta que un Sentinel acumule 10 trades. Para feedback visual del dashboard, considerar insertar con `total_trades < WARMUP` y un flag `is_warmup` separado.
- **🟢 línea 31-35**: `min_size=2, max_size=10` hardcoded. Mover a `config.py` (`DB_POOL_MIN`, `DB_POOL_MAX`).
- **🟢 línea 366-401**: `get_trade_history` no se usa en ningún call site del código auditado. Posiblemente código muerto. Verificar.

---

## sentinel-v0.5/config.py

- **🟡 línea 21-27**: `_CRITICAL_CREDENTIALS` se define al cargar el módulo. Si `validate_config()` se llama después de un `os.environ.update(...)`, los valores no se refrescan. Documentar o convertir a property.
- **🟡 línea 116-117**: comentario importante "load_dotenv() debe ejecutarse ANTES de importar config" — buen warning pero frágil. Si se importa accidentalmente antes, falla silenciosamente. Mover el `load_dotenv()` adentro de `config.py` con guard idempotente.
- **🟢 línea 35-71**: constantes con `_SECONDS`, `_THRESHOLD`, `_MINIMUM` mezcladas. Considerar agruparlas en dataclasses por agente para parametrización testable.

---

## sentinel-v0.5/correlation_guard.py

- **🟡 línea 191**: `if incoming_ticker not in bars` — aprueba con warning. Igual que `the_ear._fetch_price_changes`, enmascara falla de datos como "todo bien". Mejor: rechazar la señal con `reason="no_data"`.
- **🟡 línea 174**: `all_tickers = list({incoming_ticker} | set(open_tickers))` — convierte set a list, pero el orden no es determinista. Si Alpaca cobra por orden de tickers o si hay dependencia implícita en el orden, puede generar inconsistencias. Ordenar.
- **🟡 línea 209-211**: `if pos_ticker == incoming_ticker: correlations.append(1.0)` — si la incoming es el mismo ticker que ya está abierto, agrega 1.0 al promedio. Resultado: avg muy alto, reducción agresiva. Pero si hay 5 posiciones distintas + 1 BUY del mismo ticker, el avg = (1.0 + 4 × ~0.4) / 5 = 0.52, lo cual no descarta. Considerar manejarlo aparte: ticker duplicado → veto inmediato (relacionado con #H-5).

---

## sentinel-v0.5/regime_classifier.py

- **🟡 línea 212-215**: `initialize()` está cortado por un `return` temprano que skips el train. Código después del `return` (línea 217-226) es inalcanzable. Igual con `classify_today` (línea 248). Funciona pero linter / IDE marca como dead code. Cuando se reactive S-10, sacar los returns.
- **🟡 línea 91**: `df["forward_return"] = df["close"].pct_change(5).shift(-5)` — `pct_change(5)` calcula return de 5 días pasado, `shift(-5)` lo mueve a 5 días futuro. Verificar que la lógica es: "return forward = (close[t+5] - close[t]) / close[t]" vs lo que actualmente calcula. Posible off-by-one.
- **🟢 línea 141-143**: `split = max(len(X) - 252, 1)` — split fijo en últimos 252 días. Para datos largos (25 años) eso da 95% train / 5% test. Buena práctica para time series, pero documentar.

---

## sentinel-v0.5/main.py

- **🟡 línea 288-298**: `_seconds_to_next_candle()` puede devolver < 1.0s si `now.second` es alto. El `max(float(wait), 1.0)` cubre eso, pero si `wait = 1.0` exactamente el ciclo se ejecuta cada 1s en momentos límite.
- **🟡 línea 309-313**: `ear_task = asyncio.create_task(...)`. Si la task explota silenciosamente (excepción no capturada), `await ear_task` solo lo nota cuando se cancela en el `finally`. Loop principal nunca lo verifica. Agregar `done_callback` que loggee si el task termina inesperadamente.
- **🟡 línea 282`: `logger.error(f"Sentinel[{i}] lanzó excepción: {result}")` — solo el índice, no el nombre. Difícil debug. Cambiar por `sentinels[i].name`.
- **🟡 línea 53-58**: misma issue que api.py — RotatingFileHandler con path relativo. Path absoluto.
- **🟢 línea 85-89**: `_seconds_to_next_candle` no maneja el caso de cierre de mercado (16:00). El loop dormirá hasta 16:00 + 15min y dispara fuera de horario. `_is_market_open` lo cubre porque el siguiente iteration del while detecta y duerme 60s. OK pero ineficiente.
- **🟢 línea 137**: comentario dice "puede tardar 30-60s" para RegimeClassifier, pero está desactivado. Actualizar.

---

## sentinel-v0.5/sentinels/__init__.py

- **🟡 línea 175-183**: `_rsi` usa SMA-smoothing en lugar de Wilder smoothing (EMA). Documentado en sesiones previas como aceptable para v0.5. Migrar a Wilder cuando se calibre con datos reales.
- **🟡 línea 156-167**: `await asyncio.gather(*[self._run_single(t) for t in self.tickers], return_exceptions=True)` — concurrencia por ticker dentro del Sentinel. Si todos los Sentinels hacen lo mismo y todos comparten el ThreadPool del executor, fácilmente saturable. Considerar limitar concurrencia con `asyncio.Semaphore`.
- **🟢 línea 27-28**: `_BARS_LOOKBACK = 150`, `_FETCH_DAYS = 10` — documentado pero hardcoded. Mover a `config.py`.

---

## dashboard/index.html (handoff Design)

- **🟡 línea 113-119**: `.detener-btn` con `text-shadow` — solo demo. Sin funcionalidad real.
- **🟡 línea 537-538**: `data-i18n="view_simple"` y `view_full` — pero el texto inicial en el HTML es "SIMPLE" y "COMPLETA" (español). Si el cliente carga con lang=en, hay un flash en español antes que `applyI18n()` lo cambie. FOUC menor.
- **🟢**: el HTML del handoff hardcodea valores como `9/9`, `27`, `15MIN`, `0.12` en líneas 528-532. `sentinel-data.js` los sobrescribe pero hay un FOUC inicial con datos mock. Aceptable.

---

## dashboard/sentinel-data.js (custom)

- **🟡 línea 270-280**: `killTickMock` reemplaza `window.setTimeout` globalmente. Si alguna lib externa (futuras) usa `setTimeout(fn, 2500)` con una función llamada `tick`, también se intercepta. Documentado en comentarios. Para defensa, agregar un mecanismo de unload del intercept después de N segundos (cuando ya pasó el momento del boot de app.js).
- **🟡 línea 320-340 `setupPersistence`**: `localStorage.getItem('sentinel.lang')` puede devolver cualquier string. Si alguien manipula localStorage con `<script>alert(1)</script>` como lang, pasa a STATE.lang. No hay XSS por sí solo (T() resuelve a key fallback) pero es input no sanitizado.
- **🟡 línea 281-286 `_fetchJson`**: si la API responde 401 (cuando se agregue auth de #H-1), retorna null sin distinguir de error de red. Mejor: detectar 401 específicamente y mostrar prompt de re-auth.
- **🟡 línea 357-371 `connectSSE`**: el handler de error sólo tiene comentario. EventSource auto-reconecta pero sin feedback visual. Agregar banner si `readyState === EventSource.CLOSED` por más de N segundos.
- **🟡 línea 222-235 `loadStatus`**: actualiza valores del header con `setText('hSistema', ...)`, pero busca elementos por ID que el handoff no garantiza (depende de coincidir nombre exacto). Si Design cambia el HTML en una nueva entrega, esto se rompe silenciosamente.
- **🟡 línea 200-220 `loadMacro`**: inyecta `_news_dyn_*` keys en `I18N`. Si el i18n se reload (no debería), las keys se pierden. Documentar la inyección.
- **🟢**: el comentario inicial es muy detallado, lo cual es bueno, pero hace el archivo > 480 líneas. Considerar separar constantes en `sentinel-constants.js`.

---

## dashboard/sentinel-app.js (handoff Design — NO modificable según handoff)

> ⚠️ Estos issues NO se pueden arreglar localmente sin perder el "handoff oficial".
> Si Design entrega una nueva versión, considerarlos como input para el equipo Design.

- **🟡 línea 22, 36-37, 60, 95-110, 147, 165, 187, 198, 216-219, 230-231, 236-244**: `innerHTML` con strings interpolados (template literals) sin escape. Datos vienen mayormente de constantes hardcoded (i18n, citas) pero también de `STATE.trades` (sentName, ticker, etc.) que pasan por la API. Si se permite que el name de un Sentinel se edite (futuro panel admin), XSS posible.
- **🟡 línea 131-148 `renderDetail`**: PnL/win/sharpe por ticker calculados con `tk.charCodeAt(0)` — datos sintéticos decorativos. Cuando haya `/api/sentinels/:id` con detalle real, reemplazar.
- **🟡 línea 283-320 `tick`**: el tick mock que `sentinel-data.js` neutraliza. Si el intercept falla en algún navegador (raro, pero posible con extensiones), corre y pisa los datos reales.
- **🟡 línea 367-377 `downloadReport`**: genera el reporte en cliente con `buildReport(range)`. Coexiste con `/api/report?range=` del backend que es más completo (incluye persistencia real). El cliente no usa el endpoint del server. Idealmente: cambiar `downloadReport` para hacer `fetch('/api/report?range=' + range)` y descargar la respuesta.
- **🟡 línea 380-419**: handlers de eventos delegados via `addEventListener` directo sobre IDs (no event delegation con `closest`). Si el HTML cambia el ID, se rompe en silencio.
- **🟢 línea 264-266**: regex `g` flag en `replace` para SIGNAL BUY/SELL/HOLD — funciona pero múltiples SIGNAL en un mismo log line podrían causar nesting de spans (extremadamente improbable).
- **🟢 línea 403**: `alert('SISTEMA DETENIDO (demo)')` — placeholder visible en producción. Quitar o reemplazar con la implementación real (ver #H-7).

---

## Otros / cross-cutting

- **🟡** Logs en `logs/sentinel.log` y `logs/api.log` — sin rotación de archivos antiguos más allá de los 3 backups. Para 24/7 + 5MB max, llena rápido en producción. Considerar `TimedRotatingFileHandler` con rotación diaria.
- **🟡** `requirements.txt` con `>=` pinning (alpaca-py>=0.21.0, etc.) — vulnerable a breaking changes en updates. Para producción, pinear a versión exacta y actualizar manualmente.
- **🟡** No hay tests automatizados. Las verificaciones que hice son via curl + parseo manual. Para v2.5 con cambios grandes, mínimo unit tests para `correlation_guard.calculate_correlation`, `historian.calculate_performance`, `dispatcher.allocate_capital`.
- **🟡** No hay healthcheck endpoint dedicado (`/api/healthz`). `/api/status` cumple ese rol pero también devuelve datos. Separar en `/api/healthz` (200/503) para load balancers.
- **🟢** `db/schema.sql` tiene `DEFAULT NOW()` en created_at — server time. Si la DB está en otro timezone que ET, los reportes "today" se desincronizan. Standard `TIMESTAMP WITH TIME ZONE` seria mejor; lo actual es `TIMESTAMP` (without TZ).
- **🟢** No hay versionado de la API (`/api/v1/...`). Para v2.5 con cambios potencialmente breaking, agregar prefijo desde ahora.
