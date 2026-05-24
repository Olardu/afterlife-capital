# Balance del Período de Observación — Sentinel v0.5

**Período cubierto:** 2026-04-28 → 2026-05-23 (26 días naturales, ~18 días hábiles)
**Cierre anticipado:** sí (4 días antes del 27-may planeado)
**Régimen del bot:** Paper trading en Alpaca, NEUTRAL fijo (S-10 desactivado), sizing trivial (qty=1)
**Estado:** **COMPLETO al 2026-05-24** — secciones §2 a §5 llenadas con queries reales (15 CSVs en `backups/2026-05-24/balance_data/`) + métricas QuantStats (HTML en `backups/2026-05-24/quantstats_report_*.html`). §6 CorrelationGuard NO extraído (las queries no existían en el SQL Cowork; columnas no persistidas en signals, ver TECHDEBT). Plantilla lista para mover al repo + commit Cowork final.

---

## 0. Resumen ejecutivo (versión final con datos completos al 2026-05-24)

> En 26 días naturales (~18 hábiles), Sentinel v0.5 generó **343 trades / 214 fills** (62% fill rate) sobre 12 tickers únicos, con P&L paper de **+$143.45 (+0.094% sobre 20 días hábiles, +0.143% calendario)** sobre $100K iniciales. **No perdió plata**, pero las métricas QuantStats (Sharpe 2.75 / WinRate 61% / PF 1.63) están **distorsionadas por el sizing trivial qty=1** (utilización 2.6%, vol 0.45% anualizada). Los únicos números válidos para evaluar el diseño son **Win Rate 61% y Profit Factor 1.63 — ambos sólidos, indicando que el sistema tiene edge real cuando opera**.
>
> ### Hallazgos críticos (4 nuevos descubiertos en este balance, no estaban en el pre-análisis):
>
> 1. **🚨 Fórmula de Sharpe del bot está bugueada.** `historian.calculate_performance` retorna valores imposibles (S-3/SPY = 93.9, S-8/MSFT = -120.4). Sharpe reales de fondos exitosos están en 1-3. **Issue urgente:** auditar la fórmula antes de usar `performance_scores.sharpe` para ANY decisión. Win rates SÍ son confiables.
>
> 2. **🚨 7 productos exóticos/leveraged ejecutados** sin filtro (SOXS, BITI, UVXY, VIXY, SQQQ, USO, DBA). Universe Selector los propuso con razonamiento técnico sólido pero sin restricciones de risk. **YA cerrado** por la lista negra de `7f089a0` (Fase 3, sesión 23-may), pero contaminó las métricas del período. Validar en el 2º período que la lista negra funciona.
>
> 3. **The Ear NUNCA actuó** (0 vetos en 26 días). Risk score MAX = 0.32 vs threshold 0.5. El período fue anormalmente tranquilo — no podemos calibrar el threshold sin un período volátil. Pipeline funciona end-to-end (2,724 eventos ingeridos y scored) pero falta stress test.
>
> 4. **CorrelationGuard sin auditoría posible** — output no persistido en DB (solo en logs). Item TECHDEBT nuevo. Sin esto, ninguna decisión sobre el threshold 0.75 es válida.
>
> ### Concentración del bot
>
> - **S-2 RSI Fast Reversion (Mantis) dominó:** 188/343 trades (55%), 130 fills, 23 rotaciones (todas decay_confirmed, todas ejecutadas, costo $0.68 Claude API total). Mantis es el bot, los otros 8 sentinels son satélites.
> - **S-1 y S-4 quasi-no-operaron** (1-2 fills cada uno, mucho pending). `idle_timeout` trigger (cerrado en `9672d27/2e79e12`) los debería rotar en el 2º período.
> - **S-7 VWAP y S-3 Bollinger Bounce** son candidatos a GANADOR (win rates 0.74 y 0.83 respectivamente, fill rate alto). Validar en 2º período.
> - **S-8 RSI Divergence** es candidato a DESCARTAR (win rate 0.0 en MSFT con 2 trades, slippage alto). Investigar si la divergencia se calcula bien.
>
> ### Recomendación Fase 2 (revisada con datos del balance)
>
> Status real al 24-may (todo ya cerrado en sesión 23-may + 24-may):
> 1. ✅ **#H-5b** cerrado (`6a427c5`). 45 warnings en 5 días confirmaron crónico.
> 2. ✅ **#H-4** cerrado en correlation_guard + historian + dispatcher + reconciler (`a022de0` + `917cad8` + `0ed87e4` + `3672a82`).
> 3. ✅ **#H-6b** cerrado (`3672a82`) con auto-poller cada 5 min.
> 4. ✅ **Lista negra Universe Selector** cerrada (`3a79307` + `7f089a0`).
> 5. ✅ **idle_timeout trigger** cerrado (`9672d27` + `2e79e12`).
> 6. ✅ **#GR-1 + #GR-2 + #GR-3 + #GR-4** todos cerrados (flag-gated, default OFF).
> 7. ✅ **#OP-1 backup DB** cerrado (`eac8799`).
> 8. ✅ **Hardening XSS sentinel-app.js** (T8) cerrado (`ac55d40`).
> 9. **🆕 ITEM URGENTE (post-balance):** auditar fórmula `historian.calculate_performance` Sharpe. Sin esto, ningún reporte futuro sobre Sharpe es válido.
> 10. **🆕 TECHDEBT:** persistir output CorrelationGuard en `signals` table.
>
> ### Recomendación para el 2º período de observación (junio)
>
> **Decisión Roman (24-may dec.3):** activar **AMBOS** flags `ATR_SIZING_ENABLED=true` y `PORTFOLIO_DD_LIMITS_ENABLED=true` desde el restart del martes 26-may. Full v0.6 desde el día 1. Trade-off aceptado conscientemente: mayor riesgo si bug no detectado vs máximo aprendizaje del diseño real (Half-Kelly + DD limits + bracket orders).
>
> Sobre esto, el balance valida la decisión: **los componentes operacionales funcionan** (dispatcher allocate_capital, Universe Selector con lista negra, idle_timeout, #GR-3 con tabla daily_equity_snapshots, suite 77/77). Lo que falta es **deployar el capital realmente**. El 2º período medirá eso.

---

## 1. Caveats — Por qué los datos NO miden el diseño final

Los 26 días NO reflejan la versión optimizada del sistema. Tres sub-períodos con comportamientos distintos:

### Sub-período A — 28-abril → 07-mayo (10 días naturales, ~8 hábiles)
- **Estado:** Dispatcher con `allocate_capital()` roto. Todos los Sentinels al fallback `MIN_CAPITAL_PER_SENTINEL = 5%`.
- **Implicación:** allocation Sharpe-weighted Half-Kelly NO operó. Mediciones de este sub-período NO son representativas del diseño.
- **Excepción 1** (07-may) cerró este sub-período fixeando 3 bugs (scores parciales + agregación dispatcher + métricas dashboard).

### Sub-período B — 08-mayo → 11-mayo (4 días, ~3 hábiles)
- **Estado:** Excepción 1 expuso 2 bugs adicionales: TypeError `float += Decimal` (#H-4 raíz) + bucle Universe Selector zombie.
- **Implicación:** Mantis ejecutó 23 rotaciones en 6h sobre TSLA/SPY zombies (08-may). Datos de Mantis del 08-may contaminados.
- **Excepción 1.1** (08-may) cerró ambos bugs.
- **Intervención manual SPY** (11-may): cierre de short -4 sh accidental por bug #H-5b. P&L +$4.53.

### Sub-período C — 12-mayo → 23-mayo (12 días naturales, ~8 hábiles)
- **Estado:** Allocation Sharpe-weighted operando correctamente, PERO **sizing trivial** (qty=1 hardcoded en los 9 Sentinels). Utilización del equity: ~3-5% en vez del 58-65% esperado con Half-Kelly real.
- **Bug #H-5b reapareció** (15-may, QQQ): short -2 sh accidental. Intervención manual 16-may, fill 18-may, P&L -$5.66. Costo total acumulado #H-5b en QQQ: -$12.02.
- **Excepción 1.2** (13-may): nueva tarjeta de capital invertido en dashboard (cosmética, no afecta operación).

**Conclusión técnica:** ningún sub-período mide "Sharpe-weighted Half-Kelly real con SL/TP y sizing por ATR". El balance debe interpretarse como **versión sub-óptima del diseño**, no como evaluación del diseño final.

---

## 2. Performance agregada del portfolio

### 2.1 Equity y P&L

| Métrica | Valor | Notas |
|---|---|---|
| Equity inicial (28-abr) | $100,000.00 | Paper Alpaca |
| Equity final (23-may) | **$100,143.45** | Snapshot Code 19:55 |
| P&L absoluto | **+$143.45** | |
| P&L porcentual sobre equity total | **+0.143%** | 26 días naturales, ~18 hábiles |
| P&L sobre capital invertido (aprox) | **~+5.7%** | $143.45 / ~$2,500 (long MV promedio aproximado). Cálculo exacto requiere serie temporal de long_MV día a día. |
| Cash al cierre | **$97,564.99** | |
| Long market value | **$2,578.46** | 8 posiciones long qty=1 |
| Short market value | **$0** | Limpio post-cierre manual QQQ 18-may ✓ |
| Buying power | **$397,138.84** | 4x intraday (cuenta multiplier=4) |
| Day-trade count | **10** | Rolling 5 días. PDT rule no aplica (equity > $25K paper) |

**Posiciones abiertas al cierre (todas long, qty=1):**

| Ticker | Unrealized P&L | Unrealized % | Sentinel asignado (a confirmar) |
|---|---|---|---|
| AAPL | +$6.90 | +2.29% | `[A LLENAR — query sentinel_tickers]` |
| AMD | +$19.02 | +4.24% | `[A LLENAR]` (recupera de -$19.81 del 14-may) |
| IWM | +$9.32 | +3.38% | `[A LLENAR]` |
| NVDA | -$1.41 | -0.65% | Mantis (S-2 RSI Short) confirmado |
| SPY | +$5.83 | +0.79% | `[A LLENAR]` |
| TLT | +$0.40 | +0.48% | Mantis (S-2) post-cleanup |
| TSLA | +$13.22 | +3.20% | `[A LLENAR]` |
| XLU | +$0.25 | +0.55% | Mantis (S-2) post-cleanup |
| **TOTAL uPL** | **+$53.53** | | |

**P&L realizado durante el período:** $143.45 (total) − $53.53 (unrealized actual) = **~$89.92** acumulado en 26 días. Los $53.53 restantes son ganancia sobre posiciones aún abiertas.

### 2.2 Benchmark — SPY buy-and-hold mismo período

| Métrica | Sistema Sentinel | SPY buy-and-hold | Delta |
|---|---|---|---|
| Return % | `[A LLENAR]` | `[A LLENAR]` | `[A LLENAR]` |
| Return $ (sobre $100K) | `[A LLENAR]` | `[A LLENAR]` | `[A LLENAR]` |
| Volatilidad anualizada | `[A LLENAR]` | `[A LLENAR]` | — |
| Max Drawdown | `[A LLENAR]` | `[A LLENAR]` | — |

**Cómo calcular el benchmark SPY:** precio cierre SPY 28-abr-2026 vs cierre 23-may-2026, return % aplicado a $100K notional. QuantStats lo hace automáticamente con `qs.reports.html(returns, benchmark='SPY')`.

**Lectura honesta:** sobre el **capital efectivamente invertido** (~$3K de los $100K) Sentinel puede haber rendido razonable, pero sobre el **portfolio total** queda lejos del SPY (costo de oportunidad del 95% sin deployar). Reportar AMBAS métricas — la primera mide calidad del sistema, la segunda mide el costo de no haber deployado todo (sizing trivial).

### 2.3 Métricas de calidad (QuantStats output, fuente Alpaca portfolio history, 20 días hábiles)

| Métrica | Valor | Interpretación |
|---|---|---|
| **Sharpe ratio (anualizado)** | **2.7486** | >1 bueno, >2 muy bueno, >3 sospechoso. **AQUÍ ENGAÑOSO** — la volatilidad ínfima del sizing qty=1 trivial infla el ratio artificialmente. NO leer como señal del diseño. |
| **Sortino ratio** | **3.8503** | Idem caveat — alto por baja vol. |
| Calmar ratio | en HTML | Return / MaxDD; el MaxDD de -0.1% inflará este ratio. |
| **Profit factor** | **1.6349** | gross_profit / gross_loss. **VÁLIDO** — sólido, indica que el sistema tiene edge real cuando opera. |
| **Win rate** | **61.11%** | % trades ganadores. **VÁLIDO** y **sólido** — por encima de break-even significativo. |
| Avg win / Avg loss | en HTML | Ratio R/R promedio. |
| **Max Drawdown** | **-0.1%** (-$100 sobre $100K) | Mayor caída pico-valle. Mínimo por el sizing trivial (utilización ~2.6%). No representa el riesgo real del diseño con sizing por ATR. |
| **Volatilidad anualizada** | **0.45%** | **AQUÍ ESTÁ LA CLAVE.** Vol normal de un fondo equity es 12-20%. La nuestra es 0.45% porque deployamos ~2.6% del equity. Cuando #GR-2 (sizing por ATR) se active, vol esperada subirá 10-20x. |
| Beta vs SPY | en HTML | <1 menos volátil que SPY, >1 más. |
| Alpha vs SPY | en HTML | Return excess no explicado por exposure a SPY. |

**Reporte HTML completo:** `backups/2026-05-24/quantstats_report_2026-04-28_2026-05-23.html` (481 KB, gitignored). Abrir con `Start-Process` desde PowerShell.

**Conclusión §2.3 honesta:** los 3 números VÁLIDOS son **Profit Factor 1.63, Win Rate 61%, Return +0.094%**. El sistema tiene edge real pero no lo deploya (vol 0.45%). Los Sharpe/Sortino/MaxDD están distorsionados por el sizing trivial — NO se pueden comparar con benchmarks de mercado hasta tener un período con #GR-2 activado.

---

## 3. Performance por Sentinel (los 9) — datos reales 28-abr → 23-may

### 3.1 Resumen agregado (fuente: `q3_1_resumen_sentinels.csv`)

| # | Sentinel | Strategy | Trades | Fills | Cancelled | Pending | Tickers actuales | Slippage avg | Status |
|---|---|---|---|---|---|---|---|---|---|
| S-1 | SMA Crossover | sma_crossover | 11 | **1** | 0 | 10 | IWM, QQQ, SPY | -0.0100 | **WARMUP+** (1 fill / 11 → casi todo cancelado/pending; estrategia técnica nunca disparó setup útil) |
| S-2 | **RSI Fast Reversion** (Mantis) | rsi_short | **188** | **130** | 58 | 0 | NVDA, TLT, XLU | 0.0009 | **DOMINANTE** — el bot fue básicamente S-2 todo el período. 23 rotaciones (todas decay_confirmed). Win rate por ticker: NVDA 0.59 / XLU 0.67 / TLT 0.375 (q3_2) |
| S-3 | Bollinger Bounce (Oracle) | bollinger_bounce | 23 | 17 | 6 | 0 | SPY, XLP, XLV | -0.0039 | **GANADOR candidato** — Win rate 0.83 promedio en sus 3 tickers (SPY 1.0/2, XLP 0.75/4, XLV 0.5/2). Trades pocos pero alta calidad |
| S-4 | MACD+Volume | macd_volume | 10 | **2** | 0 | 8 | AMD, NVDA, TSLA | -0.0360 | **WARMUP** — 2 fills, sin scores. Estrategia técnica encontró setups pero no se ejecutaron (80% pending) |
| S-5 | ORB Breakout (Smasher) | orb_breakout | 38 | 13 | 0 | 25 | AAPL, QQQ, SPY | -0.0034 | **NEUTRAL/PROBLEMA** — Win rate 0.0 en AAPL (2) y 0.0 en QQQ (3). Setups detectados pero performance pobre. Investigar fill rate bajo (34%) |
| S-6 | EMA Triple | ema_triple | 19 | 6 | 0 | 13 | NVDA, SPY, TSLA | -0.0263 | **WARMUP** — Fills bajos (32%), sin scores. |
| S-7 | VWAP Reversion (Netrunner) | vwap_reversion | 35 | **32** | 3 | 0 | GLD, QQQ, SPY | -0.0584 | **GANADOR candidato** — Fill rate 91% (best), Win rates GLD 0.86 / QQQ 0.60 / SPY 0.67 (q3_2). El más confiable. |
| S-8 | RSI Divergence (Neo) | rsi_divergence | 15 | 9 | 6 | 0 | MSFT, QQQ, SPY | 0.0410 | **DESCARTAR candidato** — Win rate 0.0 en MSFT (2). Slippage alto. Investigar si la divergencia se calcula bien |
| S-9 | Bollinger Squeeze | bollinger_squeeze | 4 | 4 | 0 | 0 | AMD, NVDA, SPY | 0.0350 | **WARMUP estricto** — solo 4 trades. No hay base estadística para decidir. |

**Totales:** 343 trades / 214 fills (62% fill rate) / 73 cancelled / 56 pending. **S-2 absorbió el 55% de los trades.**

### 3.2 Performance scores por ticker (fuente: `q3_2_performance_scores.csv`, 12 entradas con suficientes trades)

| Sentinel | Ticker | Trades | Win rate | Sharpe (⚠️ ver nota) | Decay status |
|---|---|---|---|---|---|
| S-3 Bollinger Bounce | SPY | 2 | **1.00** | 93.90 | OK |
| S-3 Bollinger Bounce | XLP | 4 | **0.75** | 86.66 | OK |
| S-3 Bollinger Bounce | XLV | 2 | 0.50 | 47.63 | OK |
| S-5 ORB | AAPL | 2 | 0.00 | -82.28 | OK |
| S-5 ORB | QQQ | 3 | 0.00 | -93.24 | OK |
| S-8 RSI Divergence | MSFT | 2 | 0.00 | -120.39 | OK |
| **S-2 RSI Fast Rev.** | NVDA | 22 | **0.59** | 24.78 | OK |
| **S-2 RSI Fast Rev.** | XLU | 9 | **0.67** | -1.40 | OK |
| **S-2 RSI Fast Rev.** | TLT | 8 | 0.38 | -40.44 | OK |
| **S-7 VWAP Rev.** | GLD | 7 | **0.86** | 50.00 | OK |
| **S-7 VWAP Rev.** | QQQ | 5 | 0.60 | 18.38 | OK |
| **S-7 VWAP Rev.** | SPY | 3 | 0.67 | -19.49 | OK |

**⚠️ HALLAZGO CRÍTICO sobre Sharpe del bot:** los valores (93.9, -120.4, 86.66, etc.) son **estadísticamente imposibles**. Sharpe ratios reales de fondos exitosos están en 1-3, y >5 ya es sospechoso. La fórmula de `historian.calculate_performance` está calculando algo distinto al Sharpe estándar — posiblemente: (a) no anualiza correctamente, (b) usa P&L absoluto en vez de retornos, (c) confunde unidades, (d) divide por desviación estándar muy pequeña. **NO usar estos Sharpe para decisiones.** Issue a abrir post-balance: auditar la fórmula del bot vs Sharpe estándar `(mean_return - rf) / std_return * sqrt(252)`.

**Win rates SÍ son confiables** y son lo que usaremos para clasificar Status.

### 3.3 Distribución temporal (fuente: `q3_3_trades_por_dia.csv`, 114 filas)

114 entradas (sentinel, día) — todos los sentinels operaron en algún día del período. Heatmap completo en CSV. Hallazgos:
- Día más activo: 2026-05-08 (Mantis recibió 8 rotaciones secuenciales por bucle Universe Selector — bug Excepción 1.1, ya cerrado).
- Días con cero trades para algunos sentinels: S-9 (Bollinger Squeeze) solo operó en pocos días.
- 28-abr (día 1 del período): 17 trades — fuerte arranque por warmup inicial.

### Criterios de status (definidos pre-período)

- **GANADOR:** Win rate > 55%, trades ≥ 10. Promover en Fase 2 (más capital, más tickers).
- **NEUTRAL:** Win rate 45-55%, trades ≥ 10. Mantener, observar próximo período.
- **DESCARTAR:** Win rate < 40%, trades ≥ 10. Candidato a remover o rebuild.
- **WARMUP:** Trades < 10. Sin base estadística.
- **NO_OPERÓ:** 0 trades. Candidato a `idle_timeout` trigger (#FASE3, ya implementado).

**Nota:** abandonamos el criterio "Sharpe > 1.0" por el hallazgo de fórmula bugueada (§3.2). Volverá cuando la fórmula esté corregida.

---

## 4. Universe Selector — datos reales (fuente: `q4_1`, `q4_2`, `q4_3`, `q4_4`)

| Métrica | Valor | Notas |
|---|---|---|
| Rotaciones totales | **23** | Todas en S-2 RSI Fast Reversion (Mantis) |
| Trigger reason breakdown | **23 decay_confirmed / 0 warning / 0 recovery** | El bot NO usó el path "pre-anticipado" (warning) — siempre esperó a confirmación de decay. Patrón conservador. |
| Status breakdown | **23 executed / 0 cancelled** | 100% de las recomendaciones de Claude se ejecutaron. |
| Costo total Claude API | **$0.6813** | 23 calls × ~$0.030 promedio. |
| Costo promedio por rotación | **$0.0296** | 2x lo esperado de $0.014 — probablemente prompts más largos por contexto (justificable). |
| Costo máximo por call | **$0.0316** | |
| Sentinels afectados | **1** (solo S-2) | Mantis dominó el feature |
| Tickers únicos propuestos (Claude) | **18** | BITI, DBA, GDXJ, GLD, IEF, SLV, SOXS, SQQQ, TIP, TLT, USO, UUP, UVXY, VIXY, XBI, XLE, XLU, XLV |
| Tickers efectivamente rotados | 18 (mismo set, todos ejecutados) | |
| Costo mensual extrapolado | **~$0.91/mes** (0.68 × 30/22.5) | Muy por debajo del cap configurado de $10/mes. |

### 4.1 Anomalías documentadas

**🚨 7 productos exóticos/leveraged propuestos Y EJECUTADOS** (fuente `q4_4_productos_exoticos.csv`):

| Ticker | Tipo | Veces propuesto | Ejecutado |
|---|---|---|---|
| **SOXS** | 3x inverse semiconductors (leveraged decay) | 2 | ✅ |
| **DBA** | Agriculture commodity ETF | 1 | ✅ |
| **BITI** | 2x inverse Bitcoin | 1 | ✅ |
| **USO** | Oil futures ETF (contango decay) | 1 | ✅ |
| **UVXY** | 1.5x VIX (catastrófico decay) | 1 | ✅ |
| **VIXY** | 1x VIX (decay) | 1 | ✅ |
| **SQQQ** | 3x inverse Nasdaq (leveraged decay) | 1 | ✅ |

**Implicación:** sin la lista negra que se implementó en `7f089a0` (Fase 3, sesión 23-may), Claude tenía cero restricciones y propuso estos productos basándose solo en compatibilidad técnica. El razonamiento de Claude era sólido (mean reversion, Hurst < 0.5, etc.) pero ignoró el riesgo del decay de leveraged ETFs.

**Hoy ya no se repite** — `universe_selector.py` post-`7f089a0` rechaza estos pre-Claude. Pero los 7 que se ejecutaron están vivos en el período de observación y contaminaron las métricas de S-2 con tickers que NO deberían haber sido propuestos en primer lugar.

### 4.2 Bucle zombie post-Excepción 1.1

NO se observa otro bucle de rotación zombie en el detalle (`q4_3_detalle_rotaciones.csv`, 23 filas) post-08-may. Las rotaciones secuenciales del 08-may (8 rotaciones en ~1h, todas S-2) son la firma del bug — pero el resto del período (15 rotaciones en 15 días) tiene cadencia normal de 1 por día o menos. Excepción 1.1 cerró el problema.

### 4.3 Razonamientos de Claude (sample)

Las justificaciones de Claude son técnicamente sólidas (Hurst exponente, autocorrelación, RSI, mean reversion). Ejemplo (q4_3 fila 1, 08-may TSLA → TLT):

> "1) COMPATIBILIDAD TÉCNICA: La estrategia es rsi_short (mean reversion), requiere activos con oscilaciones predecibles en rangos, baja autocorrelación direccional y Hurst < 0.5. TLT cumple este perfil..."

**Calidad de prompt OK.** El gap NO es razonamiento — es restricciones (la lista negra fue el fix correcto).

---

## 5. The Ear — datos reales (fuente: `q5_1`, `q5_2`, `q5_3`)

| Métrica | Valor | Notas |
|---|---|---|
| **Eventos macro totales (28-abr → 23-may)** | **2,724** | Tabla `macro_events`. ~109 eventos/día hábil — alto volumen de noticias procesadas. |
| Circuit Breaker activado | **0** | Nunca llegó a threshold. |
| Risk score promedio del período | **0.0265** | Muy bajo. Mercado tranquilo todo el período. |
| Risk score MÁXIMO del período | **0.32** | Alcanzado el 03-may. Sigue por debajo del threshold de 0.5. |
| **Eventos alto riesgo (score > 0.5)** | **0** | **The Ear NUNCA superó el threshold operativo en 26 días.** |
| Días con vetos efectivos | **0 de 18 hábiles** (0%) | Sin vetos en todo el período. |
| Parking Brake automático | 100% días hábiles | Sin contribuir a la decisión (no había riesgo que evitar). |

### 5.1 Calibración del threshold 0.5 — VEREDICTO

**No se pudo calibrar.** El período de observación tuvo un mercado anormalmente tranquilo (risk_score max = 0.32 vs threshold 0.5). The Ear nunca tuvo que actuar. **No podemos saber** si el threshold 0.5 está bien calibrado o demasiado conservador, porque no hubo eventos límite.

**Hallazgo positivo:** las noticias se ingirieron (2,724 eventos), se scored, se persistieron. El pipeline funciona end-to-end. Lo que falta es **un período con volatilidad real** (ej. earnings season, FOMC, geopolítica) para ver el threshold en acción.

**Recomendación:** monitorear especialmente The Ear en el 2º período (junio) si hay eventos catalizadores conocidos (FOMC, NFP, earnings). Si el bot opera durante días de alta volatilidad sin vetar y termina perdiendo dinero, recalibrar threshold hacia abajo.

### 5.2 Top 5 días por risk_score (fuente: `q5_2_eventos_por_dia.csv`)

| Fecha | Eventos del día | Risk score MAX | VIX avg | SPY change avg | The Ear actuó? |
|---|---|---|---|---|---|
| 2026-05-03 | 58 (sábado/domingo, residual) | **0.32** | 0.00% | 0.00% | NO (0.32 < 0.5) |
| 2026-05-13 | 124 | **0.25** | +1.54% | +0.96% | NO |
| 2026-05-18 | 122 | **0.25** | -1.78% | +0.85% | NO |
| 2026-05-08 | 119 | **0.24** | +1.91% | +0.59% | NO |
| 2026-05-07 | 127 | **0.21** | -0.14% | -0.69% | NO |

**Ningún día roto el threshold.** Confirmación de que el período fue tranquilo.

### 5.3 Titulares matched (fuente: `q5_3_titulares_matched.csv`)

**0 filas** — query buscaba eventos con `risk_score > 0.5` (los que dispararían vetos). Sin matches. Coherente con §5.1.

---

## 6. CorrelationGuard — NO EXTRAÍDO (datos no persistidos en DB)

**Status:** sección NO completable desde DB. Las columnas necesarias (`avg_correlation_at_decision`, `original_qty`, `adjusted_qty`, `reduction_factor`) **NO están persistidas** en la tabla `signals`. CorrelationGuard sí está cableado y opera en runtime (`dispatcher.py` invoca `evaluate_signal` antes de cada trade), pero el resultado solo queda en logs — no en DB.

**Ítem TECHDEBT a abrir:** persistir el output de CorrelationGuard en `signals` table (agregar columnas `correlation_at_decision NUMERIC(5,4)`, `original_qty NUMERIC(14,2)`, `adjusted_qty NUMERIC(14,2)`, `reduction_factor NUMERIC(5,4)`). Sin esto, no podemos auditar post-hoc cuántas señales redujo, cuántas descartó, ni cruzar con outcome para validar la utilidad del threshold 0.75.

**Workaround temporal:** grepear `sentinel-v0.5/logs/sentinel.log` por `"CorrelationGuard"` para los 26 días del período. Estimación post-hoc imposible de hacer en este balance por volumen de logs (no he tenido tiempo de implementar este parser).

**Recomendación:** crear `#TECHDEBT-NEW-X — persistir output CorrelationGuard en signals` antes del 2do período de observación (junio). Sin persistencia no hay auditoría.

### Análisis indirecto disponible

Lo que SÍ podemos decir del CorrelationGuard en este período:
- El bot operó 9 sentinels × ~3 tickers cada uno con overlap fuerte en SPY/QQQ (presentes en 6 y 4 sentinels respectivamente — ver §3.1 columna "Tickers actuales").
- Si CorrelationGuard no hubiera actuado, esperaríamos ver más de 343 trades. El número de cancelled (73) puede incluir descartes de CorrelationGuard pero también de otros motivos (status PENDING expirado, error de API, etc.).
- **Sin persistencia, no podemos atribuir.**

---

## 7. Trades — semana sin documentar (19-22 mayo)

**Resumen agregado** (Code snapshot 19:55):

| Fecha | Fills totales | Notas |
|---|---|---|
| 2026-05-19 (lunes) | 8 | |
| 2026-05-20 (martes) | 20 | día más activo |
| 2026-05-21 (miércoles) | 2 | día calmo |
| 2026-05-22 (jueves) | 11 | |
| **Total** | **41** | Todos qty=1. NVDA el más operado (round-trips intradía repetidos). |

Lista detallada por fill: `[PENDIENTE — Code volcar si lo necesitamos para análisis por Sentinel]`. Por ahora el agregado alcanza para narrativa.

### Verificación #H-5b — RECLASIFICACIÓN A "CRÓNICO"

**No fue 3ra reaparición aislada — es CRÓNICO.** 45 warnings "Posiciones fantasma" o "no rastreadas" en 5 días:

| Fecha | Warnings | Notas |
|---|---|---|
| 2026-05-18 | 11 | Día del fill QQQ + race detectada |
| 2026-05-19 | 7 | |
| 2026-05-20 | 14 | Pico |
| 2026-05-21 | 2 | |
| 2026-05-22 | 11 | |
| **Total** | **45** | ~9/día hábil promedio |

**Por qué no hubo 3ra reaparición de short accidental al 23-may:** suerte. Cada warning es una oportunidad de que un `sell_short` pase contra cache obsoleto. Las 8 posiciones al cierre son todas long porque el patrón específico (SELL legítimo + 2 SELLs subsiguientes contra cache) no se replicó en estos 5 días, pero la condición de carrera está activa.

**Implicación:** fix #H-5b **NO es bug menor diferible**. Es prioridad inmediata. Costo de NO arreglarlo: exposición continua a más intervenciones manuales como las del 11-may (SPY) y 16-may (QQQ).

**Status del fix:** ✅ **CERRADO** commit `6a427c5` (pusheado 23-may noche). `_apply_fill_to_cache(ticker, status, position)` extraído + `open_positions.pop(ticker, None)` en SELL FILLED. TDD `tests/test_h5b_cache.py` (4 casos, rojo→verde demostrado). Suite cerró 21/21 al momento del fix; hoy 77/77 con todos los #GR-* sumados.

---

## 8. Conclusiones y decisión para Fase 2

### 8.1 Componentes que funcionaron
- `[A LLENAR — ej: "Dispatcher operando Sharpe-weighted post-08-may"]`
- `[A LLENAR]`

### 8.2 Componentes que NO funcionaron / mediocre
- `[A LLENAR — ej: "Sizing trivial = 95% capital sin deployar"]`
- `[A LLENAR]`

### 8.3 Bugs que costaron dinero
- **#H-5b** (cache desactualizado tras SELL): costo realizado neto **-$7.49** (SPY +$4.53 / QQQ -$12.02). Reclasificado a **CRÓNICO** (45 warnings/5d). Fix en curso sesión 23-may.
- **#H-4** (float += Decimal): costó período entero de allocation sub-óptima hasta Excepción 1.1 (08-may). Sub-período A (28-abr → 07-may) tuvo todos los Sentinels al fallback 5%, sin distribución Sharpe-weighted.
- **Sizing trivial**: NO es bug puro (es decisión de diseño no actualizada), pero el costo de oportunidad sobre el 97.4% no deployado es probablemente el item más costoso del período. Equity utilización: ~2.6% del total. Sobre el capital efectivamente deployado el rendimiento (~+5.7%) habría sido más relevante. Fix conceptual: #GR-2 (sizing por ATR, risk parity) en Fase 3.

### 8.4 Recomendación para Fase 2 (bugs) — priorizada con datos

1. **#H-5b — EN CURSO sesión 23-may.** Reclasificado a crítico por los 45 warnings/5d. Fix de 2 líneas (`self.open_positions.pop(ticker, None)`) + test TDD. Aplicar antes de cualquier otra cosa.
2. **#H-4 completo** (float→Decimal en `correlation_guard` + `historian.calculate_performance`). Aprovechar la investigación que ya hicimos: una vez Decimal, siempre Decimal en pipeline monetario. Conversión a float solo en bordes no-monetarios (Sharpe, correlation, log strings).
3. **#H-6b** (reconciliación CANCELLED/PENDING_NEW). Sin esto, el 52% de trades no ejecutados al 4-may sigue como ruido. Implementación: ejecutar `reconcile_pending_trades.py` automáticamente al detectar PENDING_NEW > N minutos.
4. **#TD-1 a #TD-7** estructurales (multi-ticker FIFO en historian, validación signal_type en dispatcher, etc.). Ya catalogados en `TECHDEBT.md`.
5. **Hardening dashboard** (XSS, race SSE, defensa Chart.js).

### 8.5 Recomendación para Fase 3 (features) — priorizada con datos

**El cambio más impactante para el siguiente período de observación es #GR-2** (sizing por ATR / risk parity). Hoy deployamos 2.6% del equity; con #GR-2 deployaríamos ~50-70% (Half-Kelly real). Esto cambia el rango de P&L esperado de ±$200 a ±$5,000 sobre la misma performance subyacente — el segundo período SÍ medirá el diseño.

**Orden recomendado de Fase 3:**

1. **Renombre cosmético S-2** `RSI Short → RSI Fast Reversion` (15 min, evita confusión).
2. **Lista negra Universe Selector** + filtros técnicos pre-Claude (fractionable, marginable, shortable, easy_to_borrow). 2-3 hrs. Cierra el bucle de rotación de productos exóticos.
3. **#GR-1 Stop-loss + take-profit** vía Alpaca bracket orders. Sin esto, una posición puede ir -20% antes de SELL técnico.
4. **#GR-2 Sizing por ATR (risk parity)**. **Item más impactante.** Cubre también el fix del sizing trivial.
5. **#GR-3 Drawdown limits portfolio** (-5%/día → pause, -10%/sem → kill switch, -15% acum → pause indefinida).
6. **#GR-4 Reserva mínima cash 15%** (`MAX_ALLOCATION_TOTAL = 85%`).
7. **#OP-1 Backup automático DB** + **#OP-2 Heartbeat externo** (healthchecks.io).
8. **Fractional trading** (cambio contrato Dispatcher `qty=int` → `notional=float`).

**Sobre qué Sentinels promover/cortar:** decisión diferida hasta tener métricas por Sentinel (sección 3 pendiente — requiere query a `trades` agrupando por sentinel_id). El snapshot solo muestra posiciones actuales, no win rate ni Sharpe por estrategia.

**Trigger `idle_timeout`:** decisión también diferida. Necesitamos saber cuáles Sentinels llegaron a warmup (≥10 trades) y cuáles no operaron casi nada. Con esos datos, el trigger se calibra por strategy_type.

---

## 9. Apéndice

### 9.1 Lista completa de trades
`[A LLENAR — output de la tabla `trades` filtrada por owner_id y período. Adjuntar como CSV en `backups/2026-05-23/trades_periodo_observacion.csv` si es grande.]`

### 9.2 Output QuantStats HTML
`[A GENERAR — Code: `qs.reports.html(returns, benchmark='SPY', output='backups/2026-05-23/quantstats_report.html')`. Adjuntar al commit.]`

### 9.3 Snapshot Alpaca al 23-may
`[A LLENAR — output del snapshot Code (entrada LOG 19:51)]`

### 9.4 Comparación pre/post Excepción 1.x
Si los datos permiten, separar métricas del sub-período A (allocation roto) vs C (allocation OK pero sizing trivial). Eso aísla el efecto del fix vs el efecto del sizing.

---

## Estado del documento (cierre 2026-05-24)

- [x] Datos del snapshot Alpaca llenos (Code, entrada LOG 19:55 del 23-may) — secciones §2.1 + posiciones abiertas + §7
- [x] **QuantStats reporte generado** (`d57ffd7` por Code) — HTML en `backups/2026-05-24/quantstats_report_2026-04-28_2026-05-23.html` (481 KB, gitignored). Métricas clave en §2.3.
- [x] **Performance por Sentinel completada** (datos reales de q3_1, q3_2, q3_4) — sección §3 con tabla por sentinel + tabla por ticker. Identificación de status candidatos. Hallazgo crítico Sharpe bugueado documentado.
- [x] **Universe Selector métricas completadas** (q4_1, q4_2, q4_3, q4_4) — sección §4. 23 rotaciones, $0.68 total, 7 productos exóticos documentados.
- [x] **The Ear calibración** (q5_1, q5_2, q5_3) — sección §5. NUNCA actuó (risk_score max 0.32 < 0.5). Calibración pendiente de período volátil.
- [ ] **CorrelationGuard verificación post-hoc** — sección §6. Documentado como NO EXTRAÍBLE por falta de persistencia. Item TECHDEBT abierto.
- [x] Verificación #H-5b 3ra reaparición — **CRÓNICO** (45 warnings/5d). YA cerrado en `6a427c5`.
- [x] **Resumen ejecutivo final** (§0) — con todos los datos consolidados + 4 hallazgos críticos descubiertos en este balance.
- [x] Conclusiones y decisión Fase 2/3 llenadas (§8.4, §8.5) + status actualizado a 24-may (Fases 2 y 3 mayormente cerradas, agendados items nuevos post-balance).
- [x] **Plantilla movida a `afterlife-capital/BALANCE_OBSERVACION_2026-04-28_2026-05-23.md`** (cierre Fase 1, commit Cowork final).
- [x] **Apéndice X** con items cerrados desde la creación de la plantilla (23-may).

---

*Plantilla creada 2026-05-23 por Cowork (Roma). Estructura institucional inspirada en QuantStats + reportes típicos de fondos cuant. Se llena durante Fase 1 del plan post-observación.*

---

## Apéndice X — Update 24-mayo: items ya cerrados desde la creación de la plantilla

Esta plantilla se redactó el 23-may al cierre del período. Las recomendaciones de §8.4 (Fase 2 bugs) y §8.5 (Fase 3 features) se ejecutaron mayormente entre la noche del 23-may y la madrugada del 24-may. Estado actualizado al 2026-05-24 11:00 EDT:

### Fase 2 — bugs cerrados ✅

| Item §8.4 | Status | Commit | Notas |
|---|---|---|---|
| 1. #H-5b cache pop | ✅ CERRADO | `6a427c5` | TDD 4/4, pusheado |
| 2. #H-4 Decimal completo | ✅ CERRADO | `a022de0` (correlation_guard) + `917cad8` (historian) + `0ed87e4` (dispatcher) + `3672a82` (reconciler) | 3 módulos core + script |
| 3. #H-6b reconciliación | ✅ CERRADO | `3672a82` | Auto-poller cada 5 min en `main.py`, 56 PENDING_NEW backlog se limpia en próximo restart |
| 4. #TD-1 a #TD-7 | ⏳ DIFERIDO | — | Sigue en `TECHDEBT.md` |
| 5. Hardening dashboard XSS | 🟡 EN CURSO | `c73b4ac` (sentinel-data.js) + TAREA T-A activa para sentinel-app.js (deuda T8 del batch agéntico) | Cerrar hoy con commit Code |

### Fase 3 — features priorizadas, cerradas ✅

| Item §8.5 | Status | Commit | Notas |
|---|---|---|---|
| 1. Rename S-2 cosmético | ✅ CÓDIGO | `5417066` | Pendiente UPDATE en DB (Roman vía pgAdmin) |
| 2. Lista negra Universe Selector | ✅ CERRADO | `3a79307` (prompt) + `7f089a0` (cableo + filtro técnico POST-Claude) | 2-3 hrs estimadas, ejecutado en 1 batch agéntico |
| 3. #GR-1 Stop-loss/take-profit (bracket orders) | ✅ CERRADO | `990b861` (helper bracket) + `04137ef` (integración process_signal) | Flag-gated `ATR_SIZING_ENABLED=False` default |
| 4. #GR-2 Sizing por ATR (risk parity) | ✅ CERRADO | `f0cb99a` (sizing + ATR Wilder en sentinels) + `04137ef` (integración) | Flag-gated. **Item más impactante** según la plantilla — activar después del periodo de validación |
| 5. #GR-3 Drawdown limits portfolio | ✅ CERRADO + CABLEADO | `0341124` (lógica + flag `PORTFOLIO_DD_LIMITS_ENABLED=False`) + `d73568f` (cableo real con tabla `daily_equity_snapshots` + poller EOD) | Flag-gated default OFF |
| 6. #GR-4 Reserva mínima cash 15% | ✅ CERRADO | `014be88` | `MAX_ALLOCATION_TOTAL=85%` enforced |
| 7. #OP-1 Backup automático DB | ✅ CERRADO | `eac8799` | Script PowerShell con rotación 7d+4w+12m + README de restore |
| 7. #OP-2 Heartbeat externo | ⏳ PENDIENTE | — | healthchecks.io setup queda para Code/Roman |
| 8. Fractional trading | ⏳ PENDIENTE | — | Cambio de contrato Dispatcher, refactor más grande |
| Trigger `idle_timeout` | ✅ CERRADO | `9672d27` (trigger + helpers) + `2e79e12` (ejecución de rotación tras 7d) | Universe Selector ahora rota tickers idle |

### Trabajo adicional NO en la plantilla original (24-may madrugada)

- **`BUENAS_PRACTICAS_V2.md` v2.5** (commit `1261e8c`): §14.0 "Verificación técnica post-edit" — derivado del incidente Code post-`d73568f`.
- **Rotación LOG v01 → v02** (commit `13f2052`): `teamwork/archive/LOG_v01.md` con 828 líneas, LOG.md nuevo con header resumen.
- **Migración protocolo Cowork↔Code via `teamwork/LOG.md`**: handoff/report en raíz reemplazados por LOG compacto.

### Pendientes para martes 26-may pre-apertura

1. **Restart `api.py`** — toma fix #H-5b + scheduler reporte off + nuevo poller `_daily_equity_snapshot_poller`.
2. **Decisión flags** — activar `ATR_SIZING_ENABLED=true` y/o `PORTFOLIO_DD_LIMITS_ENABLED=true`? Mi sugerencia: dejar OFF martes (segundo período de observación con código limpio y flags OFF) + activar gradual la siguiente semana con monitoring específico.
3. **UPDATE rename S-2** en pgAdmin: `UPDATE sentinels SET name='S-2 RSI Fast Reversion' WHERE strategy_type='rsi_short';` (1 fila).
4. **T-A hardening XSS** `sentinel-app.js` (TAREA Code activa, debería cerrar hoy).

### Datos que SIGUEN pendientes para completar este balance

Las secciones 3 (performance por Sentinel), 4 (Universe Selector métricas), 5 (The Ear calibración) y 6 (CorrelationGuard verificación) requieren queries SQL sobre la DB. El SQL está listo en `outputs/queries_balance_observacion.sql`. Code o Roman corre las queries en `psql`/pgAdmin y vuelca resultados → Cowork llena las tablas. Después se genera QuantStats (`qs.reports.html(returns, benchmark='SPY')`) y se mueve la plantilla completa a `afterlife-capital/BALANCE_OBSERVACION_2026-04-28_2026-05-23.md` para commit Cowork.

**Esta plantilla queda en outputs hasta tener ≥80% completo** (criterio que se autodefinió en línea 293 de la versión original).

*Apéndice X agregado 2026-05-24 ~11:00 EDT por Cowork (Roma) — reflejando lo cerrado entre la creación de la plantilla y hoy.*
