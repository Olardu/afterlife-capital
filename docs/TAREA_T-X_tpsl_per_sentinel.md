# TAREA T-X — TP/SL ATR Multipliers Per-Sentinel (Opción B)

**Autor:** Cowork (Roma) · **Fecha:** 2026-05-26 noche post-incidente
**Bloque:** Risk Management refinement · **Prioridad:** P0 pre-apertura miércoles 27-may
**Estimación:** 60-90 min Code (config + dispatcher wire + 9 sets de tests TDD + validación)
**Dependencias:** Bot operativo HEAD `7a87aa2` + commit local `3cc5b09` (fix CorrelationGuard ventana 10 días) ya hecho. ATR_SIZING_ENABLED=true activo desde 25-may.

---

## 0. Por qué este cambio

Hoy en `config.py`:
```python
ATR_STOP_MULTIPLIER  = 2.0     # SL = entry − 2×ATR (global)
RR_RATIO_TAKE_PROFIT = 2.0     # TP = entry + (2×ATR × 2.0) = entry + 4×ATR (global)
```

Mismos multiplicadores para **todos los Sentinels**, independiente de su naturaleza:
- S-1 SMA Crossover (tendencia largo plazo) usa TP=4×ATR → corta tendencias largas a la mitad de camino.
- S-7 VWAP Reversion (intradía mean-rev) usa TP=4×ATR → demasiado lejos para una reversión intradía que sólo busca la vuelta al VWAP.
- S-5 ORB (intradía breakout) usa SL=2×ATR → demasiado oxígeno; pierde la ventana intradía.

**Resultado:** los Sentinels operan con TP/SL que no se alinean con su lógica. Sharpes y win rates históricos NO incluían TP/SL (esos son del período qty=1 sin brackets); cuando el bot opera con ATR activo (desde 25-may), el comportamiento real diverge de lo testeado.

**Decisión Roman 2026-05-26:** aplicar Opción B (per-Sentinel customizado) con análisis técnico cuidadoso de cada Sentinel, no números al aire.

---

## 1. Análisis técnico de cada Sentinel

Análisis hecho leyendo `sentinels/__init__.py` (lógica de generación de señales y horizonte temporal implícito) + literatura técnica estándar (AQR, ETF gold-standards de risk parity, fundamentos de RSI/Bollinger/MACD).

### S-1 SMA Crossover (`sma_crossover`) — Trend Following largo plazo

- **Lógica:** Golden cross SMA(10)/SMA(50) → BUY. Death cross → SELL.
- **Horizonte:** una posición típica dura **días-semanas** hasta que SMA(10) cruza de vuelta.
- **Estilo:** dejar correr ganancias, cortar pérdidas pronto. Asimétrico clásico de trend following.
- **Recomendado:** **SL_MULT=2.0, RR_RATIO=3.0** → TP=6×ATR.
- **Por qué:** SL medio (2×ATR) absorbe ruido intradía sin matar un trend. TP=6×ATR permite que un trend de 5-10 días desarrolle. Ratio R/R=3:1 es estándar en literatura de trend following (Covel "Trend Following", Faith "Way of the Turtle").

### S-2 RSI Fast Reversion (`rsi_short`) — Mean-Reversion ultra rápida

- **Lógica:** RSI(2) < 15 → BUY (oversold extremo); RSI > 85 → SELL.
- **Horizonte:** RSI(2) es famoso por rebotar en **1-5 barras** (Larry Connors "Short-Term Trading Strategies"). Recuperación muy rápida.
- **Estilo:** capturar el rebote rápido y salir antes de que el mercado decida si confirma reversión o sigue cayendo.
- **Recomendado:** **SL_MULT=1.5, RR_RATIO=1.0** → TP=1.5×ATR.
- **Por qué:** SL chico (1.5×ATR) porque si después de oversold extremo el precio sigue cayendo, no es oversold sino fuerza vendedora — salir rápido. TP chico (1.5×ATR) porque el rebote del RSI(2) es estadísticamente limitado a 1-2×ATR. Ratio 1:1 simétrico = el rebote no busca trend, busca la reversión técnica.

### S-3 Bollinger Bounce (`bollinger_bounce`) — Mean-Reversion mediana

- **Lógica:** Close < banda inferior (SMA20 − 2σ) → BUY; close > superior → SELL.
- **Horizonte:** vuelta natural al medio (SMA20) o tocar la banda opuesta, típicamente **3-10 barras**.
- **Estilo:** mean-reversion sobre 20 barras (más lenta que S-2 RSI).
- **Recomendado:** **SL_MULT=2.0, RR_RATIO=1.5** → TP=3×ATR.
- **Por qué:** SL medio (2×ATR) porque vuelta a las bandas en mercados con volatilidad normal puede oscilar. TP=3×ATR aproxima la distancia al medio o a la banda opuesta (~2σ del SMA20 ≈ 2-3×ATR según volatilidad). Ratio 1.5:1 deja respiro pero no sobre-expone.

### S-4 MACD + Volume (`macd_volume`) — Trend con confirmación

- **Lógica:** MACD(12,26,9) cruce + volumen > 1.5×SMA(20) → señal.
- **Horizonte:** trend confirmado por volumen suele durar **días-semanas**.
- **Estilo:** trend following con filtro de calidad (volumen).
- **Recomendado:** **SL_MULT=2.5, RR_RATIO=2.5** → TP=6.25×ATR.
- **Por qué:** SL grande (2.5×ATR) porque el filtro de volumen reduce false signals — vale darle más oxígeno al setup. TP grande (6.25×ATR) consistente con trend. Ratio 2.5:1 es estándar para momentum confirmado.

### S-5 Opening Range Breakout (`orb_breakout`) — Intradía momentum

- **Lógica:** Breakout del high/low de la primera vela del día + volumen alto.
- **Horizonte:** **horas, dentro del día**. Trade intradía.
- **Estilo:** capturar el momentum direccional del día.
- **Recomendado:** **SL_MULT=1.0, RR_RATIO=2.0** → TP=2×ATR.
- **Por qué:** SL apretado (1×ATR) porque si el breakout falla rápido y vuelve al rango, salir rápido — false breakouts son la principal pérdida en ORB. TP=2×ATR captura el day-trend razonable. Ratio 2:1 cubre costos + breakeven 33%. Estándar en literatura de daytrading ORB (Ross Cameron, Linda Bradford Raschke).

### S-6 EMA Triple (`ema_triple`) — Trend smoother

- **Lógica:** Alineación EMA(8) > EMA(21) > EMA(55) → BUY; inversa → SELL.
- **Horizonte:** similar a S-1, **días-semanas**. EMA es más reactiva que SMA pero la alineación de 3 tarda en romperse.
- **Estilo:** trend following más reactivo que S-1.
- **Recomendado:** **SL_MULT=2.0, RR_RATIO=3.0** → TP=6×ATR.
- **Por qué:** mismos parámetros que S-1 porque la naturaleza es la misma (trend largo). EMAs son más rápidas pero el horizonte sigue siendo días.

### S-7 VWAP Mean Reversion (`vwap_reversion`) — Intradía mean-rev

- **Lógica:** Precio cae 2σ debajo del VWAP intradía → BUY; sube 2σ encima → SELL.
- **Horizonte:** vuelta al VWAP, típicamente **30 min - pocas horas** dentro del día.
- **Estilo:** capturar la reversión a la media intradía del precio típico ponderado por volumen.
- **Recomendado:** **SL_MULT=1.0, RR_RATIO=1.0** → TP=1×ATR.
- **Por qué:** SL apretado (1×ATR) porque si el precio sigue alejándose del VWAP, hay nueva información direccional — la mean-rev intradía falló. TP chico (1×ATR) porque la distancia esperada al VWAP es justamente ~1-2σ del precio típico (≈1×ATR intradía). Ratio 1:1 — el target es la vuelta al VWAP, no un trend.

### S-8 RSI Divergence (`rsi_divergence`) — Reversal con confirmación

- **Lógica:** Precio nuevo high pero RSI(14) no (bearish div) → SELL; precio nuevo low pero RSI no (bullish div) → BUY.
- **Horizonte:** las reversiones por divergencia confirmada pueden ser **días**, son setups de cambio de tendencia.
- **Estilo:** reversal con confirmación técnica (RSI no acompaña al precio).
- **Recomendado:** **SL_MULT=2.0, RR_RATIO=2.0** → TP=4×ATR.
- **Por qué:** mantener los defaults globales actuales porque este estilo es justo el caso que motiva el R/R 2:1 estándar — reversal con probabilidad razonable pero no trend de largo plazo. Sirve de baseline neutral.

### S-9 Bollinger Squeeze Breakout (`bollinger_squeeze`) — Volatility breakout

- **Lógica:** BBW (Bollinger Band Width) en percentil 10 (squeeze) + breakout de banda → señal.
- **Horizonte:** post-squeeze el precio suele expandir **días-semanas**.
- **Estilo:** capturar el move grande que sigue a una compresión de volatilidad.
- **Recomendado:** **SL_MULT=1.5, RR_RATIO=3.0** → TP=4.5×ATR.
- **Por qué:** SL apretado (1.5×ATR) porque false breakouts en squeeze son comunes — si el breakout falla, el squeeze comprime de nuevo rápido. TP grande (4.5×ATR) porque cuando el breakout es real, el move es proporcional a la compresión previa (Bollinger "Bollinger on Bollinger Bands"). Ratio 3:1 para compensar la frecuencia de false breakouts.

---

## 2. Tabla resumen para implementación

| `strategy_type` | SL_MULT | RR_RATIO | TP_MULT (=SL×RR) | Estilo | Horizonte |
|---|---|---|---|---|---|
| `sma_crossover` | 2.0 | 3.0 | 6.0 | Trend long | Días-semanas |
| `rsi_short` | 1.5 | 1.0 | 1.5 | Mean-rev rápida | 1-5 barras |
| `bollinger_bounce` | 2.0 | 1.5 | 3.0 | Mean-rev mediana | 3-10 barras |
| `macd_volume` | 2.5 | 2.5 | 6.25 | Trend confirmado | Días-semanas |
| `orb_breakout` | 1.0 | 2.0 | 2.0 | Intradía momentum | Horas |
| `ema_triple` | 2.0 | 3.0 | 6.0 | Trend smoother | Días-semanas |
| `vwap_reversion` | 1.0 | 1.0 | 1.0 | Intradía mean-rev | 30min-pocas horas |
| `rsi_divergence` | 2.0 | 2.0 | 4.0 | Reversal confirmado | Días |
| `bollinger_squeeze` | 1.5 | 3.0 | 4.5 | Volatility breakout | Días-semanas |

**Defaults globales actuales (fallback):** SL=2.0, RR=2.0, TP=4.0 — quedan como respaldo si Sentinel no está en el dict.

---

## 3. Implementación esperada

### 3.1 `config.py` — agregar dict + helper

Insertar justo después de las líneas 95-96 (que definen `ATR_STOP_MULTIPLIER` y `RR_RATIO_TAKE_PROFIT`):

```python
# --- T-X: Multipliers ATR per-Sentinel (#FEAT-011/Opción B) ---
# SL = entry - SL_MULT × ATR (riesgo absoluto)
# TP = entry + SL_MULT × ATR × RR_RATIO (recompensa)
# Defaults globales arriba se mantienen como fallback si el strategy_type
# no está en este dict.
# Justificación de cada par en docs/TAREA_T-X_tpsl_per_sentinel.md (sección 1).
ATR_PER_SENTINEL = {
    "sma_crossover":     {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("3.0")},
    "rsi_short":         {"sl_mult": Decimal("1.5"), "rr_ratio": Decimal("1.0")},
    "bollinger_bounce":  {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("1.5")},
    "macd_volume":       {"sl_mult": Decimal("2.5"), "rr_ratio": Decimal("2.5")},
    "orb_breakout":      {"sl_mult": Decimal("1.0"), "rr_ratio": Decimal("2.0")},
    "ema_triple":        {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("3.0")},
    "vwap_reversion":    {"sl_mult": Decimal("1.0"), "rr_ratio": Decimal("1.0")},
    "rsi_divergence":    {"sl_mult": Decimal("2.0"), "rr_ratio": Decimal("2.0")},
    "bollinger_squeeze": {"sl_mult": Decimal("1.5"), "rr_ratio": Decimal("3.0")},
}


def get_atr_multipliers_for_strategy(strategy_type: str) -> dict:
    """
    Devuelve {sl_mult, rr_ratio} para el strategy_type del Sentinel.
    Si no está en ATR_PER_SENTINEL, usa los defaults globales (fallback seguro).

    Args:
        strategy_type: identificador del Sentinel (ej. "sma_crossover").

    Returns:
        dict con 'sl_mult' y 'rr_ratio' Decimal.
    """
    override = ATR_PER_SENTINEL.get(strategy_type)
    if override is not None:
        return override
    return {"sl_mult": ATR_STOP_MULTIPLIER, "rr_ratio": RR_RATIO_TAKE_PROFIT}
```

### 3.2 `dispatcher.py` — usar override en `process_signal`

En la rama `if config.ATR_SIZING_ENABLED:` (línea ~391), después de calcular `atr_value` y antes de llamar `calculate_position_size`:

```python
# Obtener strategy_type del Sentinel para multipliers per-Sentinel (T-X).
# Si no se puede determinar (fallback), se usan defaults globales.
strategy_type = await self._get_strategy_type(sentinel_id)  # nuevo helper, ver 3.3
multipliers = config.get_atr_multipliers_for_strategy(strategy_type)

sizing = calculate_position_size(
    ticker=ticker,
    equity=account_equity,
    current_price=price,
    atr=Decimal(str(atr_value)),
    atr_multiplier=multipliers["sl_mult"],
    rr_ratio=multipliers["rr_ratio"],
)
```

### 3.3 Helper `_get_strategy_type` en dispatcher.py

Probablemente ya existe info de strategy_type via la tabla `sentinels` o el registry. Si no existe, agregar:

```python
async def _get_strategy_type(self, sentinel_id: UUID) -> str:
    """
    Devuelve el strategy_type del Sentinel desde DB (tabla sentinels).
    Si no se encuentra, devuelve "unknown" → calculate_position_size usará defaults.
    """
    try:
        async with self.historian._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT strategy_type FROM sentinels WHERE sentinel_id = $1",
                sentinel_id,
            )
            return row["strategy_type"] if row else "unknown"
    except Exception as e:
        logger.warning(f"No pude obtener strategy_type para {sentinel_id}: {e}")
        return "unknown"
```

(Code adapta según patrón existente — quizás ya hay un método similar para obtener atributos del Sentinel.)

### 3.4 Tests TDD

Crear `tests/test_atr_per_sentinel.py`:

```python
# Test 1: helper devuelve override correcto cuando strategy_type está en el dict.
def test_get_atr_multipliers_sma_crossover():
    m = get_atr_multipliers_for_strategy("sma_crossover")
    assert m["sl_mult"] == Decimal("2.0")
    assert m["rr_ratio"] == Decimal("3.0")

# Test 2: fallback a defaults globales si strategy_type desconocido.
def test_get_atr_multipliers_unknown_falls_back():
    m = get_atr_multipliers_for_strategy("desconocido")
    assert m["sl_mult"] == ATR_STOP_MULTIPLIER
    assert m["rr_ratio"] == RR_RATIO_TAKE_PROFIT

# Tests 3-11: uno por cada Sentinel verificando el par correcto.
def test_atr_per_sentinel_rsi_short():
    m = get_atr_multipliers_for_strategy("rsi_short")
    assert m == {"sl_mult": Decimal("1.5"), "rr_ratio": Decimal("1.0")}

# ... (repetir para los 9)

# Test 12: integración con calculate_position_size — verifica TP/SL calculados
# con override son los esperados.
def test_calculate_position_size_with_sma_override():
    sizing = calculate_position_size(
        ticker="TEST",
        equity=Decimal("100000"),
        current_price=Decimal("100"),
        atr=Decimal("2"),
        atr_multiplier=Decimal("2.0"),
        rr_ratio=Decimal("3.0"),
    )
    # SL = 100 - 2×2 = 96; TP = 100 + 2×2×3 = 112
    assert sizing["stop_price"] == Decimal("96.00")
    assert sizing["take_profit_price"] == Decimal("112.00")

# Tests 13-20: uno por cada Sentinel con calculate_position_size.
```

**Total ~20 tests TDD.** Cubre helper + integración + matemática per-Sentinel.

---

## 4. Validación final T-X

1. ✅ Suite verde (la tuya post-fix CorrelationGuard fue 659; con T-X serían ~679-680).
2. ✅ Cobertura ≥95% en config + dispatcher (módulos críticos del proyecto).
3. ✅ Ruff limpio + validate-workspace 0/0.
4. ✅ `py_compile` OK en config.py y dispatcher.py.
5. ✅ Backup pre-edit catalogado: `backups/2026-05-26/config.py.bak.preTX` + `dispatcher.py.bak.preTX`.
6. ✅ Commit LOCAL sin push (mismo modelo de los sprints recientes).
7. ✅ `git status --short` literal en el reporte `[CODE DONE]`.

---

## 5. Riesgos y rollback

| Riesgo | Mitigación | Rollback |
|---|---|---|
| Multipliers mal calibrados causan worse performance | Tests TDD aseguran que los valores aplicados son los esperados. Justificación técnica en sección 1 — no son números al aire | Revertir a defaults globales: comentar/vaciar `ATR_PER_SENTINEL` y usar SL=2.0/RR=2.0 uniformes |
| `_get_strategy_type` falla y devuelve "unknown" siempre | Fallback automático a defaults globales (helper diseñado para ello) | Logs muestran warning; el bot opera con globales mientras tanto |
| Algún Sentinel tiene un strategy_type distinto al esperado | Verificar contra la tabla `sentinels` antes de aplicar — listar todos los strategy_types existentes | Agregar el que falte al dict |
| Cambio de comportamiento súbito el miércoles 27-may sorprende | Cambio es solo en multipliers, no en lógica de generación de señales. Cada Sentinel sigue operando con su mismo trigger. Sólo cambia distancia TP/SL | Revertir a globales y reiniciar |

---

## 6. Para Roman pre-apertura miércoles 27-may

Después de Code cerrar T-X + restart del bot (Roman manual), el bot va a operar con TP/SL ajustados per-Sentinel. **Es razonable que las próximas semanas haya divergencia entre métricas históricas (qty=1 sin brackets) y las nuevas (ATR + brackets per-Sentinel)** — eso es esperado, no bug.

**Métricas a vigilar post-T-X (días 1-10 del período 2):**
- Win rate per-Sentinel: debería subir en mean-reverters (S-2, S-7) por TPs cercanos que capturan rebotes; bajar marginalmente en trend (S-1, S-6) por SLs que sacan en ruido.
- P&L per-trade per-Sentinel: trend (S-1, S-4, S-6) debería tener ganadores más grandes (TP=6×ATR); mean-rev (S-2, S-7) ganadores chicos pero más frecuentes.
- Distribución de razones de cierre: `take_profit_hit` vs `stop_loss_hit` vs `signal_close` — esperamos balance, NO 90% de stops.

Si después de ~2 semanas algún Sentinel muestra pattern claramente subóptimo (e.g. todos sus trades cierran por SL), iterar el SL_MULT en otro sprint.

---

**End spec T-X.**

Code adapta detalles de implementación según convenciones del proyecto. Drifts reportados en LOG. Suite verde + validate-workspace 0/0 obligatorios antes de `[CODE DONE]`.
