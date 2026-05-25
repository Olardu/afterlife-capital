# EXPERIMENTS — Registro de Experimentos Pre-Registrados de Sentinel

> **Propósito:** evitar el sesgo de confirmación retrospectivo. Cada cambio del bot que pueda afectar comportamiento se registra acá ANTES de implementarse, con hipótesis explícita y criterio de éxito definido. Al final del horizonte de evaluación, se contrasta con el resultado real y se cierra como éxito, fracaso o inconcluso.

**Origen:** lección de Recomendación 3 de la investigación comparativa de posicionamiento (AQR, Knight, Numerai). Decision-making sin pre-registro tiende a justificar a posteriori cualquier resultado.

**Mantenedor:** Cowork (Roma) registra y cierra. Code implementa. Roman valida criterio de éxito antes de cerrar.

**Archivo regenerado el:** 2026-05-25 (versión anterior perdida al reiniciar sesión Cowork).

---

## Protocolo

Antes de implementar cualquier cambio que altere el comportamiento del bot o introduzca lógica nueva:

1. **Cowork escribe un item EXP-NNN acá** con: hipótesis, hipótesis nula, criterio de éxito (binario o cuantitativo), criterio de fallo, horizonte de evaluación, métricas a observar.
2. **Roman valida** el criterio. Si no está de acuerdo, ajustar antes de implementar.
3. **Code implementa** referenciando el ID en el commit.
4. **Al cumplir el horizonte de evaluación**, Cowork compila las métricas y compara con el criterio. Cierra como ÉXITO / FALLO / INCONCLUSO con razón documentada.
5. **Si fue ÉXITO**: el cambio queda permanente. **Si fue FALLO**: rollback o iteración. **Si fue INCONCLUSO**: extender horizonte o reformular.

**Por qué importa:** prevenir el patrón "implementé X, los datos se ven OK, X funciona". Sin criterio pre-registrado, casi cualquier resultado se puede leer como confirmación.

---

## Plantilla

```
### #EXP-NNN — Título corto
- Fecha de registro: YYYY-MM-DD
- Implementado en commit: <hash>
- Status: registrado | implementado | en_evaluacion | éxito | fallo | inconcluso

**Hipótesis:**
Afirmación falsable que el experimento testea.

**Hipótesis nula (H0):**
Lo que esperaríamos ver si el cambio NO tuviera efecto.

**Criterio de éxito:**
Condición binaria o cuantitativa que define ÉXITO.

**Criterio de fallo:**
Condición que define FALLO claro (no es simplemente "no éxito").

**Horizonte de evaluación:**
Tiempo / cantidad de eventos para evaluar (ej: 30 días paper, 100 trades, etc).

**Métricas a observar:**
Lista de métricas concretas, dónde se persisten, cómo se calculan.

**Resultado (post-evaluación):**
[se llena al cierre]
```

---

## Experimentos registrados

### #EXP-001 — Sharpe per-trade sin anualizar (B.2)
- Fecha de registro: 2026-05-24
- Implementado en commit: `67164a5`
- Status: **éxito (implementación), en_evaluacion (impacto en producción)**

**Hipótesis:** quitar el factor de anualización `sqrt(252*26)≈80.94` del cálculo de Sharpe en `historian.calculate_performance` produce valores per-trade en rango razonable [-3, +3], preservando el orden relativo entre Sentinels para el weighting de `dispatcher.allocate_capital`.

**Hipótesis nula:** el orden relativo de allocations entre Sentinels se desordena post-fix, o los valores siguen siendo absurdos.

**Criterio de éxito:**
1. Tests TDD pasan rojo→verde mostrando antes/después con datos sintéticos.
2. En 2º período de observación, ningún Sentinel produce Sharpe per-trade |valor| > 5.
3. Allocations resultantes del Half-Kelly no concentran >50% en un Sentinel con <10 trades.

**Criterio de fallo:** algún Sentinel produce Sharpe > 10 en 2º período, o allocation se concentra >70% en un Sentinel con sample chico.

**Horizonte de evaluación:** 2º período de observación (30 días, junio).

**Métricas:** `performance_scores.sharpe` por Sentinel, `dispatcher.allocate_capital` output diario.

**Resultado:** TDD verde en 5 casos (suite 77→82). Pendiente evaluación en producción a fin del 2º período.

---

### #EXP-002 — Profit Factor + Return-to-Drawdown en lógica de decay (Opción C)
- Fecha de registro: 2026-05-24
- Implementado en commit: `de4f029`
- Status: **éxito (implementación), en_evaluacion (impacto en producción)**

**Hipótesis:** combinar PF (`gross_profit / abs(gross_loss)`) y RTD (`total_return / max_dd`) con los criterios actuales (win_rate, Sharpe) reduce falsos positivos de decay (matar Sentinels rentables con WR bajo pero payoff alto) y falsos negativos (no detectar Sentinels que pierden plata con WR alto pero payoff malo).

**Hipótesis nula:** los Sentinels que se "rescatan" por PF+RTD igualmente pierden plata, o los que se matan por la lógica nueva eran rentables.

**Criterio de éxito:** durante el 2º período, al menos 1 Sentinel marcado como `rescued_by_pf_rtd` mantiene PnL positivo en los siguientes 30 días, Y ningún Sentinel marcado como decay por la lógica nueva muestra trayectoria positiva post-marca.

**Criterio de fallo:** mayoría de rescatados degradan, o Sentinels descartados muestran recovery.

**Horizonte de evaluación:** 30 días post-período (es decir, observar Sentinels rescatados/descartados durante junio y ver cómo evolucionan en julio).

**Métricas:** `performance_scores.profit_factor`, `return_to_drawdown_ratio`, `performance_decay`, PnL evolutivo por Sentinel.

**Resultado:** TDD verde en 7 casos (suite 88→95). **OBS técnica pendiente:** `rescued_by_pf_rtd` es lógicamente redundante en Opción C tal como se implementó (los thresholds de rescued no se solapan con los de fail). Roman tiene que decidir si reformular el rescued (umbrales solapados) o aceptar la redundancia y dejarlo como está.

---

### #EXP-003 — Persistir output de CorrelationGuard en `signals`
- Fecha de registro: 2026-05-24
- Implementado en commit: `2bf79ec`
- Status: **éxito (implementación), en_evaluacion (impacto en análisis)**

**Hipótesis:** persistir el output completo de CorrelationGuard (`avg_correlation_at_decision`, `original_qty`, `adjusted_qty`, `reduction_factor`) en la tabla `signals` permite auditar el risk manager post-hoc: cuántas señales reduce, cuántas descarta, si el threshold 0.75 está bien calibrado.

**Hipótesis nula:** los datos persistidos no aportan información accionable (la lógica del guard ya estaba siendo efectiva sin necesidad de auditarla).

**Criterio de éxito:** al final del 2º período, ≥100 señales con `avg_correlation_at_decision` no-NULL en la tabla, y al menos 1 hallazgo accionable identificado en queries §6 del balance (ej: "threshold 0.75 es muy laxo / muy estricto", "tal Sentinel concentra mucho").

**Criterio de fallo:** datos persistidos correctamente pero sin patrones útiles identificables, o la persistencia introduce overhead significativo (>10% del tiempo de procesamiento por señal).

**Horizonte de evaluación:** fin del 2º período + análisis offline de 1-2 días.

**Métricas:** `signals.avg_correlation_at_decision`, `signals.reduction_factor`, conteo por status, queries §6.

**Resultado:** TDD verde en 6 casos (suite 82→88). Migración 013 aplicada a DB local. Decisión de diseño documentada: señales descartadas también se persisten (cambio de comportamiento intencional, aprobado).

---

### #EXP-004 — Fractional trading real (notional en path principal)
- Fecha de registro: 2026-05-24
- Implementado en commit: N/A
- Status: **WONTFIX 2026-05-24** (decisión Roman + Cowork)

**Hipótesis:** habilitar `notional` en `dispatcher.execute_order` reemplazando `qty=int(qty)` permite operar con cualquier capital sin perder señales por sizing chico en tickers caros.

**Resultado:** ARCHIVADO antes de implementar.

**Razón del archivo:** smoke test contra Alpaca paper REAL del 24-may confirmó error literal `{"code":42210000,"message":"fractional orders must be simple orders"}`. Alpaca prohíbe combinar fractional con bracket. Las 3 opciones de implementación (fractional puro / ATR_SIZING con stops por software / híbrido por ticker) todas rompían disciplina del 2º período de observación (cambiar comportamiento del bot a mitad del período = datos no comparables, lección AQR/Knight).

**Decisión:** postergar a Fase 3 como #FEAT-001 en BACKLOG, con #FEAT-002 (watchdog software), #FEAT-003 (webhooks Alpaca), #FEAT-004 (heartbeat externo) como precondiciones. En su lugar, EXP-005 (modo observador) captura datos durante el 2º período sin tocar comportamiento.

**Lección guardada:** la limitación es estructural del ecosistema retail con API programable (IBKR API tampoco soporta fractional en stocks, solo crypto/forex). No es solo Alpaca.

---

### #EXP-005 — Modo Observador Fractional
- Fecha de registro: 2026-05-25
- Implementado en commit: pendiente (T-K en curso, asignado a Code)
- Status: **registrado**

**Hipótesis:** el costo real de operar con qty entera (sin fractional) en paper con $100K es BAJO la mayoría del tiempo (la mayoría de señales entran con qty≥1 porque allocations son generosos), pero SIGNIFICATIVO en tickers caros con allocations chicos. La distribución exacta no se puede predecir desde el dato del período 1 (sizing trivial qty=1 todo el período).

**Hipótesis nula:** todas las señales pierden capital significativo por no tener fractional, o ninguna lo pierde. Cualquiera de los extremos sería sorpresa.

**Criterio de éxito (del experimento, NO del fractional en sí):**
1. Tabla `signals_shadow_fractional` con ≥100 registros al final del 2º período.
2. Distribución por `status` calculable: `matched`, `fractional_would_increase`, `signal_lost_to_int_floor`, `other`.
3. `dollar_diff` agregado calculable + desglose por ticker y por Sentinel.

**Criterio de fallo (del experimento):** persistencia del shadow rompe el flow ejecutable del bot, o introduce errores en el path principal.

**Horizonte de evaluación:** 30 días del 2º período (junio).

**Métricas:** registros de `signals_shadow_fractional`, agregaciones por status / ticker / Sentinel, suma `dollar_diff`, ratio `signal_lost_to_int_floor / total`.

**Decisión a tomar post-evaluación:** con la evidencia cuantificada, decidir prioridad real de #FEAT-001 (fractional real con mitigaciones). Si `dollar_diff` agregado es <5% del capital deployable y `signal_lost` <10% de señales totales, fractional baja prioridad. Si es >15% del capital o >25% de señales, fractional sube a P0 con dedicación.

**Resultado:** [pendiente, se llena al cierre del 2º período en julio].

---

*EXPERIMENTS.md regenerado por Cowork el 2026-05-25. Reemplaza versión perdida al reiniciar sesión 24-may noche. Versión anterior contenía los mismos 5 experimentos + protocolo equivalente.*
