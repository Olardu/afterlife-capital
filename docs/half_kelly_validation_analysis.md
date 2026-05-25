# Half-Kelly Validation Analysis — Sentinel v0.5

> **Análisis de la fórmula de allocation del Dispatcher** vs Kelly clásico. Research preparatorio para #TD-26 (validación matemática) + insumo para futura auditoría externa #OPS-006 (perfil "matemáticas").

**Mantenedor:** Cowork (Roma).

**Fecha:** 2026-05-25.

**Estado:** research preparatorio. NO sustituye auditoría externa — es base para que un quant externo o IA con perfil matemáticas tenga contexto antes de validar/desafiar la fórmula.

---

## §1 — Fórmula actual en el bot

En `sentinel-v0.5/dispatcher.py`, función `allocate_capital`:

```python
# Pseudo-código simplificado
total_sharpe = sum(max(sentinel.sharpe, 0) for sentinel in sentinels)
for sentinel in sentinels:
    if total_sharpe > 0:
        base = (max(sentinel.sharpe, 0) / total_sharpe) * 100  # % proporcional al Sharpe
    else:
        base = MIN_CAPITAL_PER_SENTINEL  # fallback 5%
    
    kelly_adjusted = base * KELLY_FRACTION  # 0.5 = Half-Kelly
    
    # Clamps:
    allocation = max(MIN_CAPITAL_PER_SENTINEL, min(MAX_CAPITAL_PER_SENTINEL, kelly_adjusted))
    # MIN = 5%, MAX = 25%
```

**Constantes (en `config.py`):**
- `KELLY_FRACTION = 0.5` (Half-Kelly).
- `MAX_CAPITAL_PER_SENTINEL = 25.0` (% del equity).
- `MIN_CAPITAL_PER_SENTINEL = 5.0` (% del equity).
- `MAX_ALLOCATION_TOTAL = 85.0` (% del equity total disponible para invertir, 15% en cash).

**Resultado:** cada Sentinel recibe un % del equity entre 5% y 25%, proporcional a su Sharpe relativo al sistema, multiplicado por Half-Kelly.

---

## §2 — Kelly Criterion clásico (referencia)

**Fórmula original** (Kelly 1956, "A New Interpretation of Information Rate"):

```
f* = p - q/b

donde:
- f* = fracción óptima del capital a apostar
- p  = probabilidad de ganar (win rate)
- q  = 1 - p (probabilidad de perder)
- b  = ratio ganancia/pérdida (odds, payoff)
```

**Half-Kelly:** `f = 0.5 × f*` — estándar institucional (Thorp, "Fortune's Formula" 2005). Captura ~75% del crecimiento óptimo con ~50% del drawdown.

**Caso ejemplo (un solo bet):**
- Win rate p = 60%, payoff b = 1.5 (gano 1.5x lo apostado, pierdo lo apostado).
- f* = 0.60 - 0.40/1.5 = 0.60 - 0.267 = 0.333 → Kelly puro = 33.3% del capital.
- Half-Kelly = 16.7%.

---

## §3 — Comparación: la fórmula del bot NO es Kelly clásico

| Aspecto | Kelly clásico | Fórmula del bot |
|---|---|---|
| Input | `p` y `b` por trade | `sharpe_ratio` agregado por Sentinel |
| Distribución de retornos | Cualquier distribución (incluyendo fat tails) | Implícitamente Gaussiana (Sharpe usa varianza) |
| Optimiza | Crecimiento logarítmico esperado del capital | Aproximación de Maximum Sharpe Ratio Portfolio (MSRP) |
| Multi-asset | Requiere matriz de covarianzas | No usa covarianzas (delegado a CorrelationGuard separadamente) |
| Tail risk | Captura tails | Subestima tails |
| Robustez a sample chico | Sensible (estimar p, b con pocos trades es ruidoso) | Sensible (Sharpe per-trade con pocos trades también es ruidoso) |

**Conclusión #1:** la fórmula del bot **es una HEURÍSTICA basada en Sharpe-weighted allocation con un Half-Kelly multiplier aplicado al peso**. NO es Kelly clásico calculado.

---

## §4 — Sharpe-Weighted Allocation: justificación teórica

La fórmula `base = sharpe / total_sharpe` es una aproximación del **Maximum Sharpe Ratio Portfolio (MSRP)** bajo supuestos simplificadores:

**Supuesto 1:** Sentinels son **independientes** (correlación 0).
- En Sentinel **NO es cierto** — varios Sentinels comparten tickers o sectores (S-3 SPY+XLP+XLV correlaciona con S-7 GLD+QQQ+SPY).
- **Mitigación:** `CorrelationGuard` separadamente reduce posiciones correlacionadas en runtime.

**Supuesto 2:** Returns Gaussianos (mean + variance suficiente).
- Returns financieros tienen **fat tails** (kurtosis > 3) → Sharpe subestima riesgo de cola.
- **Mitigación parcial:** `MAX_CAPITAL_PER_SENTINEL = 25%` cap previene asignaciones extremas.

**Supuesto 3:** Sharpe estimado es "verdadero" (sample suficiente).
- Con <30 trades, error estándar del Sharpe es grande.
- **Mitigación:** `WARMUP_TRADES_MINIMUM = 10` previene allocations basadas en sample mínimo, pero 10 sigue siendo bajo.

**Conclusión #2:** la heurística es **razonable** cuando los supuestos se cumplen aproximadamente, pero **subóptima** en condiciones adversas (correlación alta, fat tails, sample chico).

---

## §5 — Por qué el Half-Kelly (0.5) ayuda

Multiplicar por 0.5 sirve para:

1. **Compensar errores de estimación.** Estimar `f*` con datos ruidosos sobreestima sistemáticamente (selection bias). Multiplicar por 0.5 corrige el sesgo (Thorp, 1975).

2. **Reducir drawdown.** Half-Kelly tiene ~50% del drawdown máximo de Kelly puro, capturando ~75% del crecimiento. Trade-off favorable.

3. **Tolerancia psicológica.** Drawdowns de Kelly puro (60-80%) son intolerables para casi cualquier operador. Half-Kelly (~30%) es manejable.

4. **Reservas implícitas.** Combinado con `MAX_ALLOCATION_TOTAL = 85%`, garantiza buffer de cash para fees, slippage, oportunidades.

**Conclusión #3:** Half-Kelly es **práctica estándar institucional** y tiene sentido aplicarla incluso a una aproximación heurística como la del bot.

---

## §6 — Riesgos identificados

### Riesgo A: Sharpe-weighted concentra mal en distribuciones asimétricas

Sentinels mean-reversion típicamente tienen **muchas ganancias chicas + pocas pérdidas grandes** (payoff asimétrico). El Sharpe **subestima** el riesgo de cola.

Ejemplo: Sentinel con 40 trades positivos de 0.5% + 1 trade negativo de -20% tiene Sharpe positivo pero está jugado a un crash.

**Mitigación actual:** `MAX_CAPITAL_PER_SENTINEL = 25%` limita daño. Pero NO previene asignar el máximo a un Sentinel con perfil de cola peligroso.

**Mejora posible (Fase 3+):** usar **CVaR-weighted** en vez de Sharpe-weighted. CVaR (Conditional Value at Risk) penaliza colas explícitamente.

### Riesgo B: Sin matriz de covarianzas, el portfolio no es Mean-Variance óptimo

Kelly multi-asset óptimo requiere matriz de covarianzas completa. La fórmula del bot la ignora — confía en CorrelationGuard runtime.

**Problema:** CorrelationGuard solo reduce posiciones EN MOMENTO de la señal. NO ajusta el ALLOCATION de cada Sentinel pre-señal. Esto significa que dos Sentinels muy correlacionados pueden recibir 25% + 25% = 50% del capital antes de que CorrelationGuard actúe.

**Mejora posible (Fase 3+):** ajustar allocation por correlación EX-ANTE (no solo ex-post). Hierarchical Risk Parity (HRP, López de Prado 2016) es opción robusta.

### Riesgo C: Estimación de Sharpe con sample chico

Con 10 trades (WARMUP_TRADES_MINIMUM), el error estándar del Sharpe es ~`√(1+0.5*sharpe²)/N` ≈ 0.3-0.4. Eso significa Sharpe estimado de 1.0 puede ser realmente 0.6 o 1.4 — diferencia significativa para allocation.

**Mitigación actual:** ninguna explícita. WARMUP_TRADES_MINIMUM=10 es bajo.

**Mejora posible:** aumentar WARMUP a 30+ trades, o usar Bayesian shrinkage (apretar estimaciones hacia el promedio del sistema).

---

## §7 — Veredicto del research

**La fórmula del bot es una HEURÍSTICA RAZONABLE para retail con capital chico, NO un óptimo matemático.** Funciona bien cuando:

1. Los Sentinels son aproximadamente independientes (verificable).
2. Las distribuciones de retornos son aproximadamente Gaussianas (típico en mean reversion intradiaria).
3. Los samples son suficientes (WARMUP ≥10, idealmente ≥30).
4. Los caps (MAX 25%, MIN 5%) previenen extremos.

**Funciona MAL cuando:**

1. Eventos de cola (flash crash, gap overnight con sorpresa).
2. Sentinels altamente correlacionados (CorrelationGuard ayuda pero no es suficiente).
3. Sample muy chico (Sharpe ruidoso).
4. Distribuciones muy asimétricas (Sharpe ignora skewness).

**Para FASE 5 LIVE inicial** ($500-$2K), la heurística es **aceptable** porque el capital es chico y los caps absolutos limitan el daño máximo posible. Para escalas mayores (>$50K) o si se entra a live con socios MEMBER, **conviene auditoría externa formal** (#OPS-006 perfil matemáticas) y eventualmente migrar a algo más robusto (HRP o CVaR-optimized).

---

## §8 — Recomendaciones concretas

**Pre-Fase 5 (corto plazo):**
1. **No tocar la fórmula** — funciona "suficientemente bien" para validar el resto del sistema en live con capital chico.
2. **Documentar caveats** en `RATIONALE.md` — ya está parcialmente.
3. **Aumentar WARMUP_TRADES_MINIMUM** de 10 a 20-30 si en el período 2 vemos varios Sentinels operando con muy pocos trades (reduce ruido en Sharpe).

**Pos-Fase 5 (Fase 6+, evolución):**
1. **Contratar auditoría matemática** (#OPS-006 perfil "mate") cuando el capital justifique ($5K-$10K+).
2. **Evaluar Hierarchical Risk Parity (HRP)** como reemplazo de la heurística Sharpe-weighted — más robusto a correlación + fat tails. Librería `Riskfolio-Lib` (#HE-6) lo implementa.
3. **Considerar CVaR-optimized allocation** si los datos del período 2-3 muestran skewness importante en returns.
4. **Implementar Bayesian shrinkage** del Sharpe (apretar hacia media del sistema) para reducir ruido con sample chico.

**Auditoría externa (#OPS-006 perfil matemáticas) — preguntas a hacer:**

1. ¿La fórmula `(sharpe / total_sharpe) * 100 * 0.5` es defendible como aproximación de MSRP + Half-Kelly para 9 Sentinels parcialmente correlacionados?
2. ¿Qué tan grande es el error vs MSRP teórico óptimo (con matriz de covarianzas) en condiciones realistas del bot?
3. ¿El cap `MAX_CAPITAL_PER_SENTINEL = 25%` es suficiente para limitar el daño de un Sentinel con perfil de cola asimétrica?
4. ¿Conviene migrar a HRP, CVaR-optimized, o Black-Litterman antes de Fase 5? ¿Con qué dato lo justifica?
5. ¿`WARMUP_TRADES_MINIMUM = 10` es muy bajo? ¿Cuál sería el mínimo defendible?
6. ¿La separación de allocation (ex-ante) y CorrelationGuard (ex-post) es razonable, o conviene integrar correlación en el allocation directamente?

---

## §9 — Referencias

**Académicas:**
- Kelly Jr., J.L. (1956). *"A New Interpretation of Information Rate"*. Bell System Technical Journal.
- Thorp, E.O. (1975). *"Portfolio choice and the Kelly criterion"*. Investment Portfolio Decision Making.
- Poundstone, W. (2005). *"Fortune's Formula"*. Hill and Wang.
- López de Prado, M. (2016). *"Building Diversified Portfolios that Outperform Out-of-Sample"*. Journal of Portfolio Management. (HRP)
- Rockafellar, R.T. & Uryasev, S. (2000). *"Optimization of Conditional Value-at-Risk"*. Journal of Risk.

**Práctica institucional:**
- AQR Capital — risk parity research docs (públicos).
- Bridgewater Associates — All Weather strategy whitepapers.

**Software:**
- `Riskfolio-Lib` (Python) — implementa MSRP, HRP, CVaR, Black-Litterman. #HE-6 en BACKLOG.

---

*Half-Kelly Validation Analysis armado por Cowork el 2026-05-25 como research preparatorio para #TD-26 y #OPS-006. NO sustituye auditoría externa formal — es base de contexto para que un quant externo o IA con perfil matemáticas tenga referencia antes de validar/desafiar la fórmula.*
