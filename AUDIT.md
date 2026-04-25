# Audit report — dashboard redesign 2026-04-25

Branch auditado: `feature/dashboard-redesign`
Commit base: `5ef72da`
Archivos auditados:
- `dashboard/index.html` (final post-redesign)
- `sentinel-v0.5/api.py` (solo lectura — NO se modificó)

Severidades reportadas: **Media** y **Alta** (ignoré informativos / low por instrucción).
Solo reporto. No aplico correcciones sin aprobación.

---

## Issues encontrados

### #1 — XSS por innerHTML sin escape de strings provenientes de la API

- **Severidad:** Media
- **Archivo:** `dashboard/index.html`
- **Líneas:** 974 (renderSentinels), 1086 (renderTrades), 1143 (renderFlow), 1186 (renderNews)

Los `innerHTML = ...` interpolan strings de la API directamente: `t.sentinel_name`,
`t.ticker`, `t.side`, `t.status`, `s.name`, `s.strategy_type`, etc. La API hoy
devuelve datos limpios desde PostgreSQL, pero si un día se permite editar el
nombre del Sentinel desde el dashboard o por SQL externo, un nombre como
`<img src=x onerror=alert(1)>` ejecutaría JS arbitrario.

El helper `escapeHtml()` ya existe en el archivo (lo introduje en feature 2.5
para los logs). No se está usando en el resto del rendering.

**Recomendación**: aplicar `escapeHtml()` a TODO valor de la API antes de
interpolar en innerHTML. Patrón estándar: `${escapeHtml(t.sentinel_name)}`.

---

### #2 — API sin autenticación

- **Severidad:** Media (Alta si se expone a internet)
- **Archivo:** `sentinel-v0.5/api.py`
- **Líneas:** todos los endpoints (146 → 460)

`api.py` no tiene autenticación en ningún endpoint. `/api/sentinels`,
`/api/trades`, `/api/macro`, `/api/performance`, `/api/report` exponen el
estado completo del sistema de un owner. CORS está abierto a `*`.

En localhost / paper trading sin exposición pública es aceptable. **Si se
deploya a Railway o Raspberry Pi con puerto abierto, esto es Alta.**

**Recomendación**:
- Para localhost: dejar así con un comentario explícito en el README.
- Para deploy: HTTP Basic Auth con un user/password en `.env`, o middleware
  que verifique un header `X-API-Key` contra una env var. Aplicar antes de
  abrir el puerto al exterior.

---

### #3 — Equity calculada con slippage como proxy (placeholder declarado)

- **Severidad:** Media
- **Archivo:** `dashboard/index.html`
- **Funciones:** `renderEquity()` línea 1213, `renderMiniCharts()` línea 1037

La curva de equity y los mini-charts calculan PnL acumulado como:
`acc += sign(side) * slippage * qty`

Esto **no es PnL real**. Slippage es la diferencia entre precio de señal y
precio de fill — útil para medir ejecución, no resultado de operación. Un
trade ganador con slippage cero contribuye 0 a la curva.

El código tiene un comentario que dice "Placeholder visual hasta que haya
FIFO real" pero el dashboard no muestra ese disclaimer al usuario.

**Recomendación**:
- Marcar visualmente la curva con un badge "PLACEHOLDER" o un tooltip "PnL
  real disponible cuando se implemente pareo FIFO BUY→SELL en el Historian".
- Long-term: mover el cálculo de PnL al backend (`calculate_performance` ya
  pareando ciclos en historian.py:161) y exponerlo via /api/sentinels.

---

### #4 — Filtro nunca-matchea en `renderMiniCharts`

- **Severidad:** Media
- **Archivo:** `dashboard/index.html`
- **Línea:** 1023 (`STATE.trades.filter(t => t.sentinel_name === s.name || t.sentinel_id === sid)`)

`/api/trades` (api.py:208) hace `JOIN sentinels` y devuelve `sentinel_name`,
pero **no incluye `sentinel_id`** en el SELECT. La segunda parte del OR
(`t.sentinel_id === sid`) nunca matchea — depende solo del nombre.

Si dos Sentinels tienen el mismo nombre (poco probable hoy, pero el schema
no lo prohíbe explícitamente), los trades del segundo aparecen en el primero.

**Recomendación**: agregar `t.sentinel_id` al SELECT de `/api/trades` en
api.py:218 y dejar el filtro robusto. Alternativa más simple sin tocar
api.py: filtrar solo por `sentinel_name` y aceptar que el dashboard se basa
en nombres únicos.

---

### #5 — Race condition potencial en SSE

- **Severidad:** Media
- **Archivo:** `dashboard/index.html`
- **Función:** `connectSSE()` línea ~1320

El handler de evento `update` llama a `loadAll()` (async, hace 5 fetch en
paralelo y re-renderiza todo). Si SSE dispara dos updates antes de que el
primer `loadAll()` termine, dos `loadAll()` corren en paralelo. Si el
primero termina después del segundo, su asignación de `STATE.*` pisa la
versión nueva con datos viejos.

En la práctica el SSE dispara cada 15 minutos y `loadAll()` tarda <1s, así
que la ventana de race es muy chica. Pero el reconnect del navegador en
caída de red puede generar updates rápidos consecutivos.

**Recomendación**: agregar un flag o AbortController:
```js
let inFlight = null;
async function loadAll() {
  if (inFlight) return inFlight;
  inFlight = (async () => { /* ... */ })();
  try { return await inFlight; } finally { inFlight = null; }
}
```

---

### #6 — Sin defensa si Chart.js no carga (CDN offline)

- **Severidad:** Media
- **Archivo:** `dashboard/index.html`
- **Funciones:** `renderEquity()` 1213, `renderMiniCharts()` 1014

`new Chart(canvas, ...)` lanza `ReferenceError` si Chart.js no cargó (CDN
caído, bloqueado por adblock, sin internet). El handler `init()` no tiene
try/catch alrededor de `loadAll()`, así que el error rompe el render
completo (el dashboard queda con datos a medias).

**Recomendación**: chequear `typeof Chart === "function"` al inicio de cada
función que instancia gráficos; si falta, mostrar empty-state con texto
"Chart.js no disponible" y seguir.

---

## Issues evaluados y descartados (no reporto)

- **CORS `*`**: Roman lo justificó como aceptable en paper trading. No es
  problema mientras no haya datos sensibles ni cookies/sesiones.
- **SQL injection en api.py**: todas las queries usan parámetros `$N` de
  asyncpg. Verificado.
- **Path traversal en StaticFiles**: bind a `DASHBOARD_DIR` resuelto con
  `Path(__file__).resolve().parent.parent / "dashboard"`. Sin riesgo.
- **Credenciales hardcoded**: `api.py` lee de env vars vía `config.py`. El
  dashboard no contiene credenciales. ✓
- **Logging de PII**: api.py:104 loggea el `owner_id` UUID. No es secreto
  funcionalmente — descartado.
- **Validation de query params**: limit/range/sentinel tienen Query
  validators apropiados.

---

## Resumen ejecutivo

6 issues Media. Ninguno Alta en el contexto actual (localhost, single-user,
paper trading). El más importante es **#1 (XSS) y #5 (race SSE)** porque son
defensas que cuestan poco aplicar y previenen problemas futuros.

Si se va a deploy a internet, **#2 (auth) sube a Alta** y debe abordarse
antes del deploy.
