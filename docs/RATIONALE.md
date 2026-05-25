# RATIONALE — Justificación de Parámetros Cuantitativos de Sentinel

> **Propósito:** documentar el "por qué" de cada parámetro numérico del bot. Cuando alguien (Roman / Code / Cowork / yo en 6 meses) se pregunta "¿por qué este threshold es 0.75?", la respuesta vive acá con referencia a literatura o experiencia que la justifica.

**Mantenedor:** Cowork (Roma) actualiza cuando se ajusta o agrega un parámetro. Roman valida.

**Archivo regenerado el:** 2026-05-25 (versión anterior perdida — esta versión es más compacta).

---

## 1. Position sizing

### KELLY_FRACTION = 0.5 (Half-Kelly)

**Valor:** 0.5

**Razón:**

Kelly puro (`f* = edge/odds`) maximiza el crecimiento logarítmico esperado del capital. Pero asume edge perfectamente conocido — en trading sistemático con estimaciones ruidosas, Kelly puro produce drawdowns del 50%+ que destruyen capital y disciplina.

Half-Kelly (`f = 0.5 × f*`) es la práctica institucional estándar (Thorp 1975, AQR risk parity docs, "Fortune's Formula" 2005). Captura aproximadamente 75% del crecimiento óptimo con aproximadamente 50% del drawdown. El trade-off es ampliamente aceptado en quant trading retail e institucional.

**Cuándo revisitar:** si en 2+ períodos de observación el drawdown sostenido es <5%, considerar Kelly 0.6-0.7. Si el drawdown supera 15%, bajar a Kelly 0.3.

### MAX_CAPITAL_PER_SENTINEL = 25%

**Valor:** 25.0 (porcentaje del equity)

**Razón:**

Tope anti-concentración. Si un solo Sentinel acumula buen Sharpe artificialmente (por sample chico, bug en el cálculo, o coincidencia), el Half-Kelly podría asignarle 60-80% del capital. Eso es riesgo idiosincrático no diversificado.

25% permite que el "mejor Sentinel" reciba 4× el capital del peor (que recibe 5% por MIN). Es asimetría suficiente para premiar performance sin colapsar la diversificación.

**Cuándo revisitar:** si en producción el mejor Sentinel toca 25% sostenido y los datos sugieren que el bot está dejando alpha sobre la mesa, considerar 35%. Hoy es defensivo por diseño.

### MIN_CAPITAL_PER_SENTINEL = 5%

**Valor:** 5.0 (porcentaje del equity)

**Razón:**

Piso para Sentinels sin historial suficiente o con performance temporal mala. Con 9 Sentinels, el piso 5% × 9 = 45% de capital "reservado" en caso extremo, dejando 55% para distribución por Sharpe.

5% es suficientemente chico para no dañar el bot si el Sentinel es realmente malo, y suficientemente grande para que pueda generar trades y datos durante el WARMUP_TRADES período.

**Cuándo revisitar:** si algún Sentinel acumula 30+ trades con Sharpe negativo sostenido en 2+ períodos, bajarle el piso a 2% o desactivarlo manualmente.

---

## 2. Risk management

### CORRELATION_THRESHOLD = 0.75

**Valor:** 0.75 (correlación de Pearson sobre rolling 60 velas)

**Razón:**

Por encima de 0.75 (correlación absoluta), dos tickers se mueven prácticamente como uno solo en términos de exposición direccional. Si el bot abre posiciones en ambos, está duplicando riesgo sin diversificar.

Literatura académica de portfolio construction sugiere 0.7-0.8 como rango razonable para detectar concentración escondida. 0.75 es punto medio defensivo.

**Cuándo revisitar:** con la persistencia de EXP-003 ahora podemos medir empíricamente. Si en el 2º período el guard descarta >30% de señales, el threshold puede ser muy estricto. Si descarta <5%, muy laxo.

### ATR_WINDOW = 14 (período del ATR)

**Valor:** 14 barras

**Razón:**

Wilder original (1978) usó 14 períodos como default para ATR. Es el estándar de la industria.

### MIN_POSITION_USD = $25

**Valor:** `Decimal("25")`

**Razón:**

Piso en dólares para que los fees de Alpaca + slippage no dominen la posición. Alpaca paper es "free" pero live tiene fees variables — con posiciones de $5-10, los fees + slippage pueden ser 5-20% del retorno esperado.

$25 es un piso conservador. En Fase 5 live con $500-$2K, este piso descarta señales de allocation muy chico (esperado, mejor que ejecutar y perder en fees).

**Asociado a:** `ATR_SIZING_ENABLED=true`. Cuando ATR_SIZING está OFF, el filtro de unidades usa `MIN_POSITION_SIZE = 1` (acciones enteras).

### MAX_POSITION_PCT_OF_EQUITY (ATR sizing)

**Valor:** depende de la implementación de `calculate_position_size`. Default razonable: 5-10% del equity por posición individual.

**Razón:** cap absoluto sobre el sizing por ATR para evitar que volatilidad muy baja (ej. TLT en período tranquilo) produzca posiciones absurdamente grandes.

---

## 3. Decay detection

### SHARPE_MINIMUM = 0.05 (per-trade, post-B.2)

**Valor:** 0.05

**Razón:**

Post-fix B.2 (commit `67164a5`), Sharpe se calcula per-trade sin anualizar. El valor anterior 0.5 era inválido — se aplicaba como umbral anualizado a un cálculo que no anualizaba correctamente.

Equivalente exacto del threshold anterior: 0.5 / 80.94 ≈ 0.006. Cowork eligió 0.05 (~8× más conservador) porque per-trade puede tener mucha variación y queremos detectar decay real, no ruido.

**Cuándo revisitar:** si en 2º período varios Sentinels rentables caen bajo 0.05 (falsos positivos), bajar a 0.02.

### WARMUP_TRADES_MINIMUM = 10

**Valor:** 10 trades

**Razón:**

Estadísticamente, 10 observaciones son el mínimo para calcular medidas como Sharpe con error razonable (intervalo de confianza chico). Con <10, cualquier métrica de performance es ruido.

Es un compromiso: 30+ trades sería estadísticamente mejor pero retrasa la detección de decay temprano. 10 captura el balance.

### DECAY_THRESHOLD_WIN_RATE = 0.40

**Valor:** 0.40

**Razón:**

40% de win rate es el piso debajo del cual ninguna estrategia con payoff razonable es sostenible. La fórmula de break-even win rate dado payoff (W) es `1 / (1+W)` — para WR=40%, payoff necesario = 1.5. Para WR=30%, payoff necesario = 2.33. Mean reversion típicamente tiene payoff 1-1.5, entonces WR<40% es señal de problema estructural.

### WARNING_THRESHOLD_WIN_RATE = 0.45

**Valor:** 0.45

**Razón:** umbral previo a decay para activar pre-aviso. Da margen para investigar antes de matar la estrategia.

### PROFIT_FACTOR_MINIMUM = 1.3 (EXP-002 / Rec 6)

**Valor:** 1.3

**Razón:**

PF = gross_profit / abs(gross_loss). Profitable strategies típicamente tienen PF entre 1.2 y 2.0. Por debajo de 1.3 sostenido, las ganancias no compensan los costos transaccionales en producción live.

Origen: Recomendación 6 de la investigación comparativa AQR. Industria usa 1.5 como "muy bueno", 1.3 como "aceptable", <1.0 como "fail".

### RTD_MINIMUM = 1.0 (EXP-002 / Rec 6)

**Valor:** 1.0

**Razón:**

Return-to-Drawdown = total_return / max_drawdown. RTD ≥ 1.0 significa que las ganancias acumuladas pagaron al menos el peor drawdown — la estrategia recupera lo que pierde en el peor escenario observado.

RTD < 1.0 sostenido = estrategia que pierde más en sus peores momentos de lo que gana en general. No es sostenible.

---

## 4. The Ear (filtro macro)

### RISK_SCORE_VETO_THRESHOLD = 0.7

**Valor:** 0.7

**Razón:**

Risk score se calcula sobre titulares matched por keywords (FOMC, rate, crash, recession, etc.) con peso por relevancia y recencia. 0.7 = combinación de varios titulares de alto peso o uno solo crítico.

0.5 sería muy laxo (vetos frecuentes por noticias menores). 0.9 sería muy estricto (solo eventos extremos disparan). 0.7 es punto medio.

**Observación período 1:** risk_score máximo observado fue 0.32 en 26 días. The Ear nunca actuó. El threshold no fue probado en período tranquilo.

### PARKING_BRAKE_TIME = 15:45 ET

**Valor:** 15:45 (Eastern Time)

**Razón:**

15 minutos antes del cierre del mercado regular (16:00 ET). Bloquea nuevas órdenes para evitar:
- Posiciones que no alcancen a ejecutarse antes del cierre.
- Slippage alto en los últimos minutos por volumen comprimido.
- Overnight risk si la orden no se completa intraday.

Industria estándar es entre 10 y 30 min antes del cierre. 15 min es punto medio.

---

## 5. Universe Selector

### UNIVERSE_SELECTION_TIMEOUT_SECONDS = 60

**Valor:** 60 segundos por llamada a Claude API

**Razón:**

Claude Sonnet 4.6 con prompts típicos de Universe Selection responde en 5-30 segundos. 60s es margen 2× para variabilidad. Si la API tarda más, probablemente está caída o sobrecargada — mejor abortar que esperar.

### UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS = 180

**Valor:** 180 segundos por ciclo completo (todos los Sentinels)

**Razón:**

Con 9 Sentinels y timeout per-call 60s, en serie tardaría hasta 540s. Pero las llamadas son en paralelo, y la mayoría termina rápido. 180s permite que ciclos lentos terminen sin quedarse colgados indefinidamente.

### UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD = $0.20

**Valor:** $0.20

**Razón:**

Cap por llamada a Claude API. Una llamada típica de Universe Selection es ~10K-30K tokens input + 1K-3K output. Con pricing actual de Sonnet 4.6 (~$3/$15 por MTok input/output), una llamada sale ~$0.05-$0.15. Cap en $0.20 protege contra llamadas anómalas (input enorme por bug).

### UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS = 7

**Valor:** 7 días

**Razón:**

Pending candidates de Universe Selection se expiran a los 7 días si no se ejecutaron. Evita acumular recomendaciones viejas que ya no son relevantes (régimen de mercado puede haber cambiado).

7 días es ~1 semana de trading — tiempo razonable para que una recomendación sea actualizable sin ser obsoleta.

---

## 6. Sentinels (parámetros técnicos por estrategia)

### S-2 Mantis (RSI Fast Reversion): RSI(2) períodos

**Razón:** RSI de período corto (2) captura reversiones intradía/intraweek. Larry Connors "Short Term Trading Strategies That Work" (2008) popularizó RSI(2) para mean reversion.

### S-3 Bollinger Bounce: Bollinger Bands 20 / 2σ

**Razón:** estándar Bollinger (1980s). 20 períodos = SMA referencial, 2 σ = ~95% del rango histórico. Toques fuera del banda = candidato a reversión.

### S-7 VWAP Reversion: VWAP intradiario

**Razón:** VWAP es referencia común de precio "justo" intraday. Desvíos significativos del VWAP atraen mean reversion natural.

### EMA 8/21/55 (estrategias de tendencia)

**Razón:** combinación Fibonacci-like estándar para trend-following multi-timeframe. EMA8 = corto plazo, EMA21 = medio, EMA55 = referencia tendencial. Cruces entre ellos generan señales.

### SMA 10/50 (filtros de tendencia)

**Razón:** SMA10 vs SMA50 es el filtro "Golden Cross / Death Cross" simplificado. Filtro de régimen secundario para estrategias que requieren tendencia confirmada.

---

## 7. Operacionales

### CORRELATION_ROLLING_WINDOW = 60 (velas)

**Valor:** 60 barras de 15 min ≈ 15 horas de trading ≈ 2 días hábiles.

**Razón:** suficiente para capturar correlación reciente sin contaminarse con regímenes viejos. Ventanas más cortas (20-30) son demasiado ruidosas. Más largas (>200) capturan correlación "histórica" que puede no aplicar al momento actual.

### ATR_SIZING refresh = al inicio de cada señal

**Razón:** ATR debe calcularse con datos recientes (rolling window 14 sobre los últimos N barras antes de la señal). Recálculo per-signal evita usar valores obsoletos.

---

## 8. Flags de comportamiento (env vars)

| Flag | Default | Razón |
|---|---|---|
| `DAILY_REPORT_ENABLED` | false | Solo activo durante períodos de observación con reporte a viewers. |
| `ATR_SIZING_ENABLED` | false (default), true en período 2 | Sizing por riesgo + bracket protections. |
| `PORTFOLIO_DD_LIMITS_ENABLED` | false (default), true en período 2 | Cap de drawdown a nivel portfolio. |
| `SHADOW_FRACTIONAL_ENABLED` | true (default), activo en período 2 | EXP-005 observador, no afecta comportamiento. |
| `KILL_SWITCH_ACTIVE` | false | Modo emergencia: bot lee/calcula pero no ejecuta. |

---

## Cuándo agregar entradas a este archivo

1. Cualquier parámetro nuevo se documenta acá ANTES de mergear a `main`.
2. Cualquier cambio a un parámetro existente se documenta con: valor anterior, valor nuevo, razón del cambio, fecha, commit hash, criterio para revertir.
3. Si un parámetro se elimina, mantener entrada con status "DEPRECATED" + fecha + qué lo reemplaza.

---

*RATIONALE regenerado por Cowork el 2026-05-25. Versión más compacta que la perdida (~250 líneas vs ~440). Cubre los parámetros principales con justificación citada. Iterar agregando parámetros nuevos a medida que aparezcan.*
