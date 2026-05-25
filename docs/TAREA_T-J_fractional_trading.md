# TAREA T-J — Fractional Trading (EXP-004 / P1 #6)

**Estado:** spec regenerada por Cowork el 2026-05-24 ~22:35 EDT tras pérdida del outputs/ original en reinicio de sesión. Sustituye al resumen ejecutivo del LOG `[21:20]` con detalle verificado contra código real.

**Pausa de push:** LEVANTADA (LOG 21:45 Caso A). Flujo normal: commit local → reporte → `[COWORK PUSH-OK]` → push.

**Aplica §14.0 v2.7 completo:** Edit quirúrgico (`dispatcher.py` 1500+ líneas, prohibido reescribir entero per §14.0.6) · checklist post-edit obligatorio (`py_compile` + `pytest` + `git diff --stat` + `validate-workspace.ps1`) · §14.0.7 cierre = cierre · verificación de firmas reales del código ya hecha por Cowork (ver §2 abajo, validar contra HEAD antes de editar).

---

## §1 — Contexto y motivación

Hoy `dispatcher.execute_order` (L688) hace `qty = int(math.floor(qty))` y descarta señales con `qty < 1`. Con tickers caros (NVDA $218, MSFT $400+) y capital chico ($500-$2K iniciales de Fase 5), el sizing pierde granularidad: una asignación de $100 al ticker MSFT termina en `qty=0` → CANCELLED. Fractional habilita `notional=$X.YZ` → Alpaca convierte a fracciones de acción.

**Crítico para Fase 5 live** y para que la diversificación funcione con cualquier capital. Cierra **P1 #6** de la lista de robustez dura y **EXP-004** del protocolo de experimentos.

---

## §2 — Estado actual del código (verificado por Cowork antes de spec)

Lecturas realizadas: `dispatcher.py` L280-498 y L638-820, `correlation_guard.py` L130-283, `config.py` L60-131. Resumen:

**`dispatcher.execute_order` (L638-747)** — firma actual:
```python
async def execute_order(
    self, ticker: str, side: str, qty: Decimal,
    strategy_type: str = "", limit_price: Decimal = None,
    take_profit_price: Optional[Decimal] = None,
    stop_loss_price: Optional[Decimal] = None,
) -> dict
```
- **L688:** `qty = int(math.floor(qty))` ← punto exacto donde se pierde el fractional.
- **L689-693:** si `qty < 1` → return `{order_id: None, status: "CANCELLED"}`.
- Delega a `_submit_order_sync` (L749) con 3 ramas: bracket (L783, usa `OrderClass.BRACKET`), limit (L799), market (L808). Las tres pasan `qty=...` (no notional).

**`dispatcher.process_signal` (L280-498)** — firma:
```python
async def process_signal(
    self, sentinel_id, owner_id, ticker, signal_type,
    price: Decimal, qty: Decimal, strategy_type='',
    ear_state=None, allocation=None, account_equity=None,
) -> dict
```
- L286: `price` disponible (es `price_at_signal`).
- L382-417: `qty` se reescribe — con `ATR_SIZING_ENABLED=true` viene de `calculate_position_size`; con flag OFF se calcula `min(qty, max_qty)` con `max_qty = account_equity * sentinel_alloc / 100 / price`.
- L427-432: `CorrelationGuard.evaluate_signal(incoming_qty=qty, ...)` retorna dict con `original_qty`, `adjusted_qty`, `avg_correlation`, `reason`.
- L454: `final_qty = guard_result["adjusted_qty"]`.
- L482-490: `execute_order(qty=final_qty, take_profit_price=..., stop_loss_price=...)`.
- **NO hay check explícito de `final_qty < MIN_POSITION_SIZE` en process_signal** — vive dentro del guard (L256) y otra vez en execute_order (L689).

**`correlation_guard.evaluate_signal` (L136-282)** — firma:
```python
async def evaluate_signal(
    self, incoming_ticker: str, incoming_qty: Decimal,
    open_positions: list[dict], performance_scores: list[dict],
) -> dict
```
- Retorna dict con 5 claves: `approved`, `original_qty`, `adjusted_qty`, `avg_correlation`, `reason`. **NO retorna `reduction_factor` explícito** — dispatcher lo reconstruye en L462-465 como `adjusted/original`.
- **L256:** `if adjusted_qty < Decimal(MIN_POSITION_SIZE)` ← descarte en unidades, NO en dólares. **Sin acceso a `price`** — el guard no recibe precio. Para hacer check en $ hay que pasar `price` o delegar el check al dispatcher.

**`config.py` constantes relevantes:**
- L81: `MIN_POSITION_USD = Decimal("25")` ← **YA EXISTE** (asociada originalmente a ATR_SIZING). NO crearla.
- L99: `MIN_POSITION_SIZE = 1` ← unidades, el viejo. Deprecar (no borrar — mantener para backward compat de tests).
- L75: `ATR_SIZING_ENABLED` (flag .env, default false).
- L86: `PORTFOLIO_DD_LIMITS_ENABLED` (flag .env, default false).
- L122-125: `SHARPE_MINIMUM=0.05`, `PROFIT_FACTOR_MINIMUM=1.3`, `RTD_MINIMUM=1.0` (de T-G y T-I).

---

## §3 — Cambios propuestos por archivo

### 3.1 — `sentinel-v0.5/dispatcher.py`

**Cambio A — `execute_order`: agregar parámetro `notional` opcional.**

Firma nueva:
```python
async def execute_order(
    self, ticker: str, side: str, qty: Decimal,
    strategy_type: str = "", limit_price: Decimal = None,
    take_profit_price: Optional[Decimal] = None,
    stop_loss_price: Optional[Decimal] = None,
    notional: Optional[Decimal] = None,  # ← NUEVO
) -> dict
```

Lógica:
- Si `notional is not None`: ignorar `qty` (o validar coherencia opcional), enviar a Alpaca con `notional=str(notional.quantize(Decimal("0.01")))` (2 decimales, banker's rounding) en lugar de `qty=`.
- Si `notional is None`: comportamiento actual (backward compat).
- **Pre-validación en execute_order:** si `notional` y `notional < MIN_POSITION_USD` → return `CANCELLED` con `reason="below_min_usd"`.
- Para `notional`: **NO** aplicar `int(math.floor)` — pasar el monto exacto.

**Cambio B — rama bracket en `_submit_order_sync` (L783):** este es el punto crítico que define las opciones a/b/c según el smoke test (ver §4). Implementación DEPENDE del resultado del smoke. NO codear hasta saber.

**Cambio C — `process_signal` L482:** calcular `notional = final_qty * price` y pasarlo a `execute_order`. Mantener `qty=final_qty` para que execute_order pueda decidir (si es path bracket que NO soporte notional, fallback a qty).

### 3.2 — `sentinel-v0.5/config.py`

- **NO crear `MIN_POSITION_USD`** (ya existe L81). Agregar comentario que ahora también gobierna fractional (no solo ATR_SIZING).
- `MIN_POSITION_SIZE = 1`: agregar comentario `# DEPRECATED post-T-J: usar MIN_POSITION_USD. Se mantiene por backward compat (tests viejos).`

### 3.3 — `sentinel-v0.5/correlation_guard.py`

**Opción simple (recomendada Cowork):** mover el check de `MIN_POSITION_SIZE` del guard al dispatcher. Razón: el guard no tiene precio, y agregárselo solo para esto introduce acoplamiento innecesario. El dispatcher YA tiene el precio (L286).

- L256 actual: `if adjusted_qty < Decimal(MIN_POSITION_SIZE): ... discarded_high_correlation`.
- Cambio: el guard NO descarta por tamaño. Solo aplica reducción y retorna `adjusted_qty`. El dispatcher hace el check en $ post-guard:
  ```python
  final_qty = guard_result["adjusted_qty"]
  final_notional = final_qty * price
  if final_notional < MIN_POSITION_USD:
      # persistir señal descartada (EXP-003) con reduction_factor=0
      return {**base_result, "reason": "below_min_usd_after_correlation_reduction"}
  ```
- **Implicación:** caso edge — si CorrelationGuard reduce a qty=0.0001 y price=$1000 → notional=$0.10 → descartado por dispatcher (correcto). Si guard reduce a qty=0.5 y price=$200 → notional=$100 → aprobado (correcto, fractional).

### 3.4 — Tests TDD nuevos `sentinel-v0.5/tests/test_dispatcher_fractional.py`

Ver §5 abajo (6 casos).

---

## §4 — Smoke test contra Alpaca paper REAL (OBLIGATORIO)

**Script:** `sentinel-v0.5/scripts/smoke_test_fractional.py` (nuevo, < 150 líneas).

**Pre-condiciones:**
- `.env` con `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` (paper) ya cargadas.
- Confirmar `paper=True` hardcoded.
- Mercado abierto (si está cerrado, los tests darán `pending_new` — anotar y reintentar martes pre-apertura).

**Tests del smoke:**

**Test 1 — Orden simple con notional (fractional puro):**
```python
order = MarketOrderRequest(
    symbol="AAPL", notional="50.00",
    side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
)
resp = client.submit_order(order)
# Verificar: resp.qty es fraccional (ej. "0.2747"), resp.notional == "50.00",
# resp.status in ("accepted", "filled", "pending_new").
```
Esperado: éxito. Si falla → BLOQ y reportar error literal.

**Test 2 — Orden bracket con notional (LA QUE DEFINE EL DISEÑO):**
```python
order = MarketOrderRequest(
    symbol="AAPL", notional="50.00",
    side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
    order_class=OrderClass.BRACKET,
    take_profit=TakeProfitRequest(limit_price="220.00"),
    stop_loss=StopLossRequest(stop_price="200.00"),
)
resp = client.submit_order(order)
```
**Resultado define la implementación:**
- **Si Alpaca acepta** (status OK): **Opción (default)** = bracket+notional funciona end-to-end. Implementar pasando notional en todas las ramas.
- **Si Alpaca rechaza** (típicamente `HTTPError 422` "fractional with bracket not supported"): elegir entre:
  - **Opción (a)** — bracket usa `qty` (path ATR_SIZING_ENABLED), notional solo en path simple. Pierde fractional cuando flags ON. **Más simple, recomendada Cowork si Alpaca rechaza.**
  - **Opción (b)** — orden simple con notional → esperar fill → submeter SL/TP separados post-fill como órdenes hijas. Mantiene fractional + protección server-side, pero requiere refactor de `execute_order` para 2 fases async + reconciliación si la 2a fase falla. Más complejo.
  - **Opción (c)** — aceptar restricción, documentar como limitación de Alpaca, fractional solo en path simple. Equivale a (a) pero sin path mixto.

**Cleanup obligatorio post-smoke:** cancelar / cerrar las posiciones de test inmediatamente (`client.close_position("AAPL")` o `client.cancel_order(order_id)`) para no contaminar el período de observación. Reportar literal qué se canceló.

**Reporte:** literal de la respuesta de Alpaca para ambos tests + decisión a/b/c justificada + plan de implementación.

---

## §5 — Tests TDD (6 casos en `tests/test_dispatcher_fractional.py`)

Demostrar rojo→verde: tests con código viejo deberían fallar al menos 4 de 6; con fix → 6/6 OK.

1. **Notional fractional path simple:** mock Alpaca, `process_signal` con `price=$218 qty=0.3` (notional=$65.40) → `execute_order` envía `notional="65.40"`, NO `qty=0`. Verificar Alpaca recibe notional string con 2 decimales.

2. **Notional bajo el piso → descarte:** `process_signal` con `qty=0.05 price=$300` (notional=$15) < $25 MIN_POSITION_USD → return `reason="below_min_usd"`, señal persistida en DB con `reduction_factor=0`, ningún submit a Alpaca.

3. **Bracket con notional (depende del smoke):** si smoke confirma soporte → test feliz con bracket+notional. Si NO soporte → test verifica que con `take_profit_price/stop_loss_price` NO None se pasa `qty` (no notional) y el path entero queda como antes para ese caso (opción a).

4. **Backward compat: caller pasa solo `qty` sin `notional`:** comportamiento idéntico al pre-T-J (int floor, qty<1 → CANCELLED). Asegura que tests existentes de execute_order siguen pasando.

5. **CorrelationGuard reduce + dispatcher chequea $:** mock guard retorna `adjusted_qty=0.1 original_qty=1.0 reduction_factor=0.1`, price=$50 → notional=$5 < $25 → dispatcher descarta con `reason="below_min_usd_after_correlation_reduction"`, persiste con `reduction_factor=0` (no 0.1, ya que efectivamente se descartó), guarda `avg_correlation` y `adjusted_qty` originales del guard para auditoría.

6. **Integración end-to-end mock:** flow completo desde signal_in → kill_switch OK → ear_state OK → allocate_capital → ATR/notional → guard (intacta) → process_signal final llama execute_order con notional correcto, persiste signal con todas las columnas (incluyendo avg_correlation, original/adjusted/reduction de CorrelationGuard).

**Suite esperada post-fix:** 95/95 (actuales) + 6 nuevos = **101/101**.

---

## §6 — Restricciones (§14.0 v2.7)

- **Backup pre-edit** de `dispatcher.py`, `correlation_guard.py`, `config.py` en `backups/2026-05-24/` (o `2026-05-25/` si pasaste medianoche EDT) con sufijo `_pre_TJ`.
- **Edit quirúrgico**, NO `Write` masivo sobre `dispatcher.py` (1500+ líneas) ni sobre el resto. §14.0.6 es regla DURA: prohibido `Write` > 300 líneas; prohibido `Edit` con `new_string` > 300 líneas.
- **Verificación de firmas reales** ya hecha en §2 — validar contra HEAD actual antes de editar (puede haber drift si pasaron commits). Si firma difiere → reportar antes de avanzar.
- **Smoke test contra Alpaca paper REAL OBLIGATORIO** antes del commit final. NO se pasa solo con mocks. Si Alpaca está caído o mercado cerrado → ejecutar martes pre-apertura como parte del restart.
- **Suite tests post-fix:** 95 → **101/101** (6 nuevos).
- **`validate-workspace.ps1`** pre-commit: 0 errores, 0 warnings.
- **NO push hasta `[COWORK PUSH-OK]`** (validación Cowork sin sensibles + `git diff --stat` coherente).
- **Mensaje commit:** `feat(dispatcher): EXP-004 fractional trading (notional en vez de qty) + smoke test Alpaca + tests TDD`.
- **§14.0.7 cierre = cierre:** sin más Edits post-commit en la misma sesión. Si surge cleanup → nueva TAREA.

---

## §7 — Reporte esperado en `[CODE DONE]`

En LOG con literal:

1. **Hash del commit** + lista de archivos modificados/creados.
2. **`git status --short` literal** post-commit.
3. **Output `validate-workspace.ps1`** (Archivos chequeados / Errores / Warnings / mensaje OK).
4. **Output `pytest sentinel-v0.5/tests/ -q`** con número final (esperado `101 passed`).
5. **Output literal del smoke test** contra Alpaca paper:
   - Test 1 (simple+notional): respuesta de Alpaca o error literal.
   - Test 2 (bracket+notional): respuesta o error literal.
   - **Decisión a/b/c tomada + justificación** + plan de implementación que terminaste haciendo.
   - Confirmación de cleanup (posiciones cerradas, sin AAPL residual en cartera).
6. **CAVEAT operacional pendiente para Roman:** si descubriste algún edge case (ej. ratelimits Alpaca, comportamiento de fills parciales en notional, etc.), anotar para tener en cuenta el martes.

---

## §8 — Después de T-J

- Cowork valida → `[COWORK PUSH-OK]` → push.
- Próximo en lista robustez: **P1 #7 — Cobertura ≥95% módulos críticos** (sin spec aún; Cowork puede pre-armar mientras Code descansa).
- Mover los 4 docs Cowork de outputs/ al repo cuando Cowork los regenere (INCIDENT_PLAYBOOK, RATIONALE, EXPERIMENTS, FASE4_PLAN).
- Decidir `rescued_by_pf_rtd` redundante (Opción C de T-I — tu OBS en LOG 21:15).

---

*Spec regenerada por Cowork el 2026-05-24. Sustituye al archivo original perdido al reiniciar sesión. Validar contra HEAD antes de editar (puede haber drift).*

---

## §9 — ACTUALIZACIÓN POST-SMOKE-TEST (2026-05-24 23:15 EDT, agregada por Cowork tras leer BLOQ de Code)

Code corrió el smoke test contra Alpaca paper REAL hoy (Roman autorizó). Resultado literal (LOG entrada `[23:15 CODE BLOQ]`):

- **Test 1 — MARKET notional simple:** ✅ ACEPTADA. `notional=2, qty=None, order_class=simple, status=accepted`. Cancelada OK.
- **Test 2 — MARKET notional + BRACKET (TP/SL):** ❌ RECHAZADA. Error literal Alpaca: `{"code":42210000,"message":"fractional orders must be simple orders"}`.
- Limpieza verificada: 0 órdenes abiertas residuales.

**Resultado:** el conflicto que anticipaba el caveat del §4 quedó CONFIRMADO por evidencia. Alpaca prohíbe notional/fractional en bracket orders. Con `ATR_SIZING_ENABLED=true` (decisión Roman 12:30 para el martes), el path principal usa bracket → **fractional y el path del martes son mutuamente excluyentes**. La opción default queda descartada.

**Recomendación Cowork (alineada con Code en el BLOQ): OPCIÓN (a) — bracket→qty entero, simple→notional.**

Razones:
1. **A 2 días de operar el martes con flags ON, opción (b) es riesgo no justificado.** El refactor fill-then-bracket introduce timing async, manejo de fills parciales, reconciliación si falla la 2ª fase (posición desprotegida en mercado) y complica el path crítico justo cuando vamos a verlo en producción por primera vez con sizing real.
2. **Fractional real solo es crítico para Fase 5 live** ($500-$2K). El 2º período de observación corre en paper con $100K — bracket+qty entero sigue siendo viable. Fractional en bracket se evalúa en Fase 5 con tiempo y stress test.
3. **Opción (a) es trivial** (cambio acotado al path simple sin tocar bracket). Tests TDD ajustados. Riesgo de regresión mínimo.
4. **Deja la puerta abierta a (b)** para cuando Fase 5 lo justifique. (c) sería renunciar; (a) habilita fractional donde es seguro hoy y pospone donde no.

**Implicaciones para implementación si Roman aprueba (a):**

- `execute_order`: agregar param `notional: Optional[Decimal] = None`. Si `is_bracket=True` (L680) → ignorar `notional`, usar `qty` (path actual). Si `is_bracket=False` y `notional is not None` → usar `notional` en `MarketOrderRequest`.
- `process_signal` L482-490: calcular `final_notional = final_qty * price` y pasarlo. `execute_order` decide internamente cuál usar según `is_bracket`.
- Check `< MIN_POSITION_USD`: aplica al path simple cuando notional. Para path bracket sigue aplicando `qty < 1` (semántica vieja). Documentar esta diferencia.
- Tests TDD §5 Test 3: en lugar de "depende del smoke", afirma explícitamente que **bracket+notional NO se envía** (defensa contra regresión futura — si alguien intenta forzarlo, Alpaca rechaza igual, pero el test atrapa el error en CI sin gastar API).
- **Opciones (b) y (c) quedan rejected con razón documentada en commit message** para no perder la evidencia del smoke.

**Cambio operacional para martes (si se aprueba (a)):**

- Con flags ON el martes, los Sentinels que producen señales fractional (qty<1 → notional<$25 por allocation) van a ser DESCARTADOS por el filtro de execute_order. **Esto NO es nuevo** — hoy ya pasa (qty<1 → CANCELLED). La diferencia es que ahora el descarte es explícito y persistido (auditable). Si el bot el martes muestra muchos descartes "below_min_usd_after_correlation_reduction", es señal de capital muy chico para tickers caros (esperado con $100K paper y MAX_CAPITAL_PER_SENTINEL=25%).

**Pendiente Roman:** decidir (a) / (b) / (c). Cowork recomienda (a). Code recomienda (a) y queda en BLOQ esperando.
