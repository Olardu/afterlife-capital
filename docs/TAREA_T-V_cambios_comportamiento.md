# TAREA T-V — 3 cambios de comportamiento del bot (pre-distilFinBERT idealmente)

> **Bloque grande con 3 sub-objetivos que cambian comportamiento del bot:** #FEAT-014 cooldown post-loss + #TECH-003 migrar calculate_performance a FIFO + Wilder RSI smoothing. Roman pidió armarlos juntos (2026-05-25 noche). **Posicionamiento ideal:** entre T-T y T-U, antes del martes 26-may pre-apertura — para que el bot arranque el martes con TODOS los cambios juntos.

**Caveat:** si Code no alcanza a cerrar T-V antes del martes pre-apertura, **T-V queda para sprint del próximo fin de semana (~31 may / 1-2 jun)**. NO bloquea el martes — el bot puede arrancar con T-T + T-U sin T-V.

---

## Aplica §14.0 v2.7 completo

- Edit quirúrgico (los 3 sub-objetivos tocan archivos >1000 LOC).
- Checklist post-edit por sub-commit.
- §14.0.7 cierre = cierre por sub-commit.
- Verificación de estado real ANTES de listar items.
- Commits LOCALES sin push (modelo [04:45]).
- Clean-git-locks autónomo.
- Drift adaptable.
- Suite verde por commit + validate-workspace 0/0 + CI local verde.

**Migraciones SQL:** ninguna esperada. Los 3 sub-objetivos NO requieren columnas nuevas (FIFO usa data ya persistida en `trades`, cooldown lee de la misma tabla, Wilder es cálculo puro).

---

## Sub-0 — Audit estado actual

Verificá antes de tocar:
- ¿Existe lógica de cooldown post-loss en `dispatcher.py`? (no debería).
- ¿`calculate_performance` ya usa `tax_lots.match_fifo`? (no, sigue con zip ingenuo).
- ¿`_rsi()` en `sentinels/__init__.py` usa SMA o Wilder smoothing? (SMA según TECHDEBT histórico, verificar).

Reportá hallazgos en commit message del Sub-1.

---

## Sub-1 — #FEAT-014 Cooldown post-loss en mean reversion

**Contexto:** análisis cualitativo período 1 (`docs/analisis_cualitativo_periodo_1.md`) + #CR-1 mostraron que **27% de los disposals son wash sales** (bot re-entra rápido por mean reversion → dispara wash sales fuerte). En LIVE con sizing real, esto difiere pérdidas masivamente y complica reporte fiscal.

**Diseño:**

**1. Parámetro nuevo en `config.py`:**
```python
COOLDOWN_POST_LOSS_DAYS = 7  # default conservador; reglas IRS wash sale = 30d, pero 7d evita re-entrada inmediata sin ser demasiado restrictivo
COOLDOWN_POST_LOSS_ENABLED = os.environ.get("COOLDOWN_POST_LOSS_ENABLED", "true").lower() == "true"
```
Roman puede ajustar el threshold via env var post-arranque (`COOLDOWN_POST_LOSS_DAYS=14` por ejemplo).

**2. Cambio en `dispatcher.process_signal`:**

Antes de aprobar un BUY, verificar si hubo un SELL con pérdida en ese ticker dentro de los últimos N días:

```python
# Después del Universe Selector + CorrelationGuard, antes de execute_order:
if side == "BUY" and config.COOLDOWN_POST_LOSS_ENABLED:
    last_loss = await self.historian.get_last_loss_on_ticker(owner_id, ticker, days=config.COOLDOWN_POST_LOSS_DAYS)
    if last_loss is not None:
        logger.info(f"Señal {ticker} bloqueada por cooldown post-loss: última pérdida en {last_loss['date']}, ${last_loss['loss']}.")
        # Persistir con reason="cooldown_post_loss" (patrón EXP-003)
        await self.historian.record_signal(..., adjusted_qty=Decimal("0"), reduction_factor=Decimal("0"))
        return {**base_result, "reason": "cooldown_post_loss"}
```

**3. Nuevo método `historian.get_last_loss_on_ticker(owner_id, ticker, days)`:**

Query SQL que retorna la última operación SELL con pérdida en el ticker dentro del rango (o None si no hay):

```sql
SELECT t.filled_at, t.filled_price, t.qty, ...
FROM trades t
WHERE t.owner_id = $1
  AND t.ticker = $2
  AND t.side = 'SELL'
  AND t.status = 'FILLED'
  AND t.filled_at > CURRENT_DATE - INTERVAL '$3 days'
  -- y la operación generó pérdida: usar motor FIFO de tax_lots o cálculo on-the-fly
  AND <condición de pérdida>
ORDER BY t.filled_at DESC
LIMIT 1;
```

**Decisión técnica:** ¿usar `tax_lots.match_fifo` para detectar la pérdida? Sí — coherente con #CR-1. Caller llama a `historian._get_filled_trades(...)` + `tax_lots.match_fifo(...)` + filtra disposals con `gain < 0`.

**Tests TDD** `tests/test_cooldown.py` (6-8 casos):
- Sin SELL previo → no bloquea.
- SELL con ganancia → no bloquea (no es loss).
- SELL con pérdida hace 5 días, cooldown=7 → bloquea.
- SELL con pérdida hace 10 días, cooldown=7 → NO bloquea.
- Flag OFF → comportamiento legacy (no bloquea).
- Edge case: múltiples SELL con pérdida → toma el más reciente.
- Persistencia del descarte en `signals` con reason correcto.

**Suite esperada:** suite actual + 6-8 = ~495-497/497.

**Commit:** `feat(dispatcher): #FEAT-014 cooldown post-loss en mean reversion (evita 27% wash sales)`.

---

## Sub-2 — #TECH-003 Migrar `calculate_performance` a motor FIFO de tax_lots

**Contexto:** `historian.calculate_performance` actualmente parea trades con `zip(buys, sells)` ingenuo 1:1. Si un Sentinel emite BUY-BUY-SELL del mismo ticker, el 2do BUY queda huérfano. #TD-1 antiguo. El motor FIFO real ya existe en `tax_lots.py` (creado en T-S/#CR-1).

**Diseño:**

**1. Refactor de `historian.calculate_performance`:**

Antes (zip ingenuo):
```python
returns = [(sell.price - buy.price) / buy.price for buy, sell in zip(buys, sells)]
```

Después (FIFO real):
```python
from tax_lots import match_fifo
disposals = match_fifo(trades_filled_for_sentinel_and_ticker)
returns = [d.gain / d.cost_basis for d in disposals]
```

**2. Mantener interfaz pública igual:** la función sigue retornando `dict` con `win_rate`, `sharpe_ratio`, `total_trades`. Los **values** cambian (más correctos), pero la estructura no — `evaluate_decay` y callers downstream NO se enteran.

**3. Caveat de impacto:** los scores per-Sentinel del período 1 van a ser recalculados implícitamente al primer arranque post-merge. Eso significa:
- Sentinels que aparecían como "performing well" con el cálculo ingenuo pueden caer a "decay" con el cálculo correcto, y viceversa.
- **Decisión técnica:** ¿flush de `performance_scores` antes del primer recálculo? NO — la tabla se sobreescribe naturalmente con upserts. Si querés un baseline limpio, podés truncar la tabla manualmente, pero NO lo automatizo en T-V.

**Tests TDD** `tests/test_calculate_performance_fifo.py` (5-7 casos):
- BUY-SELL simple → mismo resultado que zip.
- BUY-BUY-SELL (mismo ticker) → motor FIFO maneja correctamente, zip ingenuo NO (test demuestra diferencia).
- BUY-SELL-BUY-SELL → cuatro trades, dos disposals.
- Sentinel con multi-ticker → pareo independiente por ticker (sigue siendo correcto).
- Solo BUY sin SELL → 0 disposals, sharpe=0.
- Regresión: data sintética del período 1 → comparar zip vs FIFO, documentar diferencias.

**Suite esperada:** suite actual + 5-7 = ~502-504/504.

**Commit:** `refactor(historian): #TECH-003 calculate_performance usa motor FIFO de tax_lots (cierra #TD-1)`.

---

## Sub-3 — Wilder RSI smoothing en `_rsi()`

**Contexto:** `sentinels/__init__.py._rsi()` usa SMA-smoothing simple. El estándar de la industria (Wilder, "New Concepts in Technical Trading Systems" 1978) usa Wilder smoothing (EMA con período = N). Para S-2 (RSI Fast Reversion, RSI 2) y S-8 (RSI Divergence), la diferencia de método cambia las señales en momentos puntuales.

**Diseño:**

**1. Cambio en `sentinels/__init__.py._rsi()`:**

Antes (SMA-smoothing):
```python
def _rsi(prices, period=14):
    gains = [max(p2-p1, 0) for p1, p2 in zip(prices[:-1], prices[1:])]
    losses = [max(p1-p2, 0) for p1, p2 in zip(prices[:-1], prices[1:])]
    avg_gain = sum(gains[-period:]) / period  # SMA
    avg_loss = sum(losses[-period:]) / period  # SMA
    ...
```

Después (Wilder smoothing):
```python
def _rsi(prices, period=14):
    gains = [max(p2-p1, 0) for p1, p2 in zip(prices[:-1], prices[1:])]
    losses = [max(p1-p2, 0) for p1, p2 in zip(prices[:-1], prices[1:])]
    # Wilder: primer avg con SMA, luego smoothing exponencial con alpha = 1/period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
    return 100 - (100 / (1 + rs))
```

**2. Verificación contra cálculo manual:** elegir un set de 30 precios sintéticos, calcular RSI con Wilder a mano (o con biblioteca conocida tipo `pandas_ta`), comparar contra output del bot. Tolerancia ε=0.001.

**3. Documentar en `docs/RATIONALE.md`** la decisión + referencia a Wilder 1978.

**Tests TDD** `tests/test_rsi_wilder.py` (4-5 casos):
- 30 precios sintéticos → RSI Wilder == cálculo manual con ε=0.001.
- Caso edge: todos los precios crecientes (avg_loss=0) → RSI=100.
- Caso edge: todos los precios decrecientes → RSI=0.
- Período=2 (S-2 Mantis) → resultado verificable manual.
- Período=14 (estándar) → cruzar con valor conocido de un dataset histórico.

**Suite esperada:** suite actual + 4-5 = ~509-510/510.

**Commit:** `refactor(sentinels): Wilder RSI smoothing (estándar industria) en lugar de SMA-smoothing`.

---

## Restricciones globales T-V

- Suite verde antes de cada commit (esperado +15-20 tests totales entre los 3 sub-objetivos).
- Validate-workspace 0/0.
- CI local verde.
- **Sin migración SQL** necesaria.
- Drift adaptable si encontrás items ya parcialmente implementados.
- Reporte parcial OK si tokens se acaban (los 3 sub-objetivos son independientes — Code puede cerrar 1-2 y dejar el resto).

## Reporte final T-V

`[CODE DONE T-V]` con:
1. Lista commits con hashes (esperado 3-4).
2. `git status --short` literal.
3. Output `validate-workspace.ps1`.
4. Output `pytest tests/ -q` final + delta de tests.
5. Cualquier drift detectado.
6. **Datos del impacto del FIFO:** opcional, recálculo de performance scores del período 1 con FIFO vs zip — documentar diferencias notables.
7. Pendientes Roman manual (activar `COOLDOWN_POST_LOSS_ENABLED=true` por defecto, ajustar `COOLDOWN_POST_LOSS_DAYS` post-arranque según data).

---

## Orden de prioridad si Code corre justo de tokens

Si por restricciones de tiempo Code solo puede cerrar **1 sub-objetivo** antes del martes:

**Prioridad 1: Sub-2 #TECH-003 FIFO calculate_performance** — fix de bug latente, los scores actuales son ruido si hay BUY-BUY-SELL.

**Prioridad 2: Sub-1 #FEAT-014 Cooldown** — evita wash sales, importante con sizing real.

**Prioridad 3: Sub-3 Wilder RSI** — cosmético / corrección de método, impacto operacional menor.

Si Code solo cierra 1-2, el resto va al sprint del próximo finde sin problema.

---

## Después de T-V

- Cowork valida + Roman decide push del bundle (T-T + T-U + T-V si entró).
- **Martes 26-may pre-apertura:** Roman activa flags + restart con TODO incluido.
- Bot del martes arranca con FinBERT + cooldown + FIFO performance + Wilder RSI (si T-V entró) o sin ellos (si no).

---

*TAREA T-V pre-armada por Cowork 2026-05-25 noche. Posicionamiento ideal: entre T-T y T-U si Code tiene tiempo. Si no alcanza, próximo finde. Sub-objetivos independientes — Code puede cerrar parcial sin problemas. Decisiones técnicas autónomas en su scope. Suite verde por commit. Modelo NO-push.*
