# NEXT_ITERATION.md — Ideas y mejoras para después del período de observación

**Período de observación:** 27 abril – 27 mayo 2026
**Regla:** Nada de esta lista se implementa hasta después del cierre. Solo anotar.

---

## Post-Observación (después del 27 de mayo)

### Bugs / Reconciliación

- **#H-6b — Reconciliación automática de CANCELLED/PENDING_NEW.** Cuando un trade queda CANCELLED o PENDING_NEW, el bot no reconcilia automáticamente con Alpaca. Resultado: posiciones huérfanas o fantasma. Fix: ejecutar reconcile_pending_trades.py automáticamente al detectar estos estados. Observado 2026-05-04: 52% de trades no ejecutados (4 cancelled + 7 pending de 21). S-2 RSI Short y S-5 ORB son los más afectados.
- **Estudiar lógica para minimizar cancelaciones** — analizar patrones de por qué se cancelan trades y ajustar para prevenirlo desde el origen.

### Universe Selector

- **Plugin Equity Research + Financial Analysis (Anthropic)** — Evaluar los plugins de Claude para alimentar al Universe Selector con datos fundamentales (earnings, valuaciones, tesis alcista/bajista) además del contexto macro actual.

  **Instalación (puede hacerse ya, en Cowork app):**
  1. Cowork → Customize → `+` → "Add marketplace from GitHub"
  2. URL: `https://github.com/anthropics/financial-services-plugins`
  3. Instalar **Financial Analysis primero** (core, provee skills y connectors compartidos)
  4. Después instalar **Equity Research**

  **Capacidades sin connectors premium:** parsing de 10-K/10-Q, modelos DCF/LBO, comparable company analysis, draft de research notes, screening cualitativo. Funciona con datos públicos (SEC EDGAR, Yahoo Finance, web search).

  **Capacidades con connectors premium (requieren subscripción):** Daloopa, Morningstar, S&P Global, FactSet, Moody's, MT Newswires, Aiera, LSEG, PitchBook. Fuera de presupuesto retail.

  **Alcance del plugin instalado:**
  - Disponible para conversaciones Cowork (refinar prompts, evaluar candidatos manualmente, validación de diseño).
  - **NO se usa automáticamente desde Universe Selector del bot** (que llama a Claude vía `claude_client.py` con system prompt fijo y JSON schema).
  - Para que el bot tenga las capacidades del plugin, hay que portar skills al system prompt o agregar tool calls. Trabajo post-27-may.

- **Refinamiento del prompt del Universe Selector — lista negra de leveraged/decay products** — Bug 2026-05-08 mostró que Universe Selector propuso BITI, SQQQ, UVXY, VIXY, USO a Mantis (rsi_short, mean reversion). Estos productos son leveraged inverse o tienen estructura de futuros con decay diario sostenido (-3-5% por mes por oscilación normal del subyacente, independiente de la dirección). Incompatibles con cualquier estrategia mean-reversion de varios días/semanas.

  **Cambios al SYSTEM_PROMPT de `universe_selector.py`:**
  - Agregar sección "NUNCA propongas leveraged products o productos con decay diario" con lista explícita: leveraged inverse ETFs (SQQQ, SOXS, TZA, SDS, FAZ), leveraged long ETFs (TQQQ, UPRO, SPXL, TNA, FAS), volatility ETFs/ETNs (UVXY, VIXY, VXX, SVXY), commodity futures funds con decay (USO, UNG, DBA en menor medida), inverse single-stock (BITI, ETHU). Lista no exhaustiva pero suficiente.
  - Agregar filtro técnico explícito en el código del Universe Selector: antes de proponer un candidato, verificar `fractionable=TRUE`, `marginable=TRUE`, `shortable=TRUE`, `easy_to_borrow=TRUE` vía Alpaca Assets API. Si no cumple alguno, descartar antes de incluir en prompt.
  - Documentar en `claude_reasoning` del `rotation_decisions` el motivo de exclusión para auditoría.

- **Trigger `idle_timeout` (rotar tickers inactivos)** — propuesta de Roman 2026-05-08. Hoy Universe Selector solo rota cuando hay decay confirmado (≥`WARMUP_TRADES_REQUIRED` trades + `sharpe < DECAY_THRESHOLD_SHARPE` o `win_rate < DECAY_THRESHOLD_WIN_RATE`). Si un ticker tiene 0 trades porque la estrategia técnica nunca encuentra setup (caso AMD en S-4 y S-9), queda zombie inverso: asignado pero silencioso. Diseño cuidadoso requerido:
  - Umbral por `strategy_type` (no uniforme: `orb_breakout` y `bollinger_squeeze` por diseño tienen baja frecuencia, `rsi_short` dispara seguido).
  - Guard de mercado: suspender trigger si VIX promedio del último período es muy bajo (mercado plano → todos los tickers callados, no es problema del ticker).
  - Score de "fitness latente": contar setups técnicos teóricos no emitidos (próximos al threshold de la estrategia) para distinguir "no apto" de "tranquilo".
  - Respetar piso de `WARMUP_TRADES_REQUIRED` para no rotar tickers que están madurando.
  - **NO PERMITIDO durante observación** según `OBSERVATION_PERIOD.md` regla 4 ("cambiar lógica de cualquier agente"). Por eso queda acá.

### Dispatcher — Leverage escalonado (hipótesis de Roma, 2026-05-10)

Cap autoimpuesto en `dispatcher.allocate_capital`: limitar uso máximo de buying_power al 125% del equity (escala inicial), condicionado a métricas de seguridad. NO es API call a Alpaca — el margin disponible está siempre presente en `buying_power`, se "activa" automáticamente cuando una orden excede cash.

**Datos Alpaca confirmados (mayo 2026):** mínimo $2,000 equity, 2x overnight / 4x intraday (este último baja umbral a $2K el 4-jun cuando FINRA retira PDT), tasa 6.25% anual non-elite, cobro solo sobre debit balance al cierre (intraday cerrado antes del close = $0). Paper trading NO aplica borrow fees ni margin interest → resultados con leverage en paper están inflados vs live.

**Implementación esperada:**
- Nuevo campo `LEVERAGE_CAP_MULTIPLIER = 1.25` (default 1.0). Multiplica el `account_equity` antes del clamping en `allocate_capital`.
- Lógica de activación basada en métricas: Sharpe agregado del sistema durante N semanas, drawdown techo, correlación entre Sentinels (si sube por encima Z, bajar leverage porque diversificación se desactiva). Cap absoluto 1.5x.
- Default seguro: arranque, post-reset, o ambigüedad → 1.0x.
- Simulación de interés (Opción 1 recomendada): tabla nueva `simulated_costs`, ciclo nocturno post-close calcula `debit_balance × 0.0625 / 360`. Dashboard muestra P&L bruto vs P&L ajustado lado a lado. Implementable como módulo aislado tipo `the_ear.py`, sin tocar lógica del dispatcher.

**Pre-condiciones:**
1. Cierre del período de observación 27-may.
2. Validación de que el Dispatcher recién arreglado (Excepción 1.1) opera Sharpe-weighted Half-Kelly correctamente sobre baseline limpio durante el próximo período de observación amplio.
3. Resolución de #H-4 más allá de `dispatcher.allocate_capital` (revisión integral float→Decimal en cálculos financieros).
4. Bloque de revisión de infraestructura post-27-may (IEX vs SIP, timeframes).

**Riesgos:** 2x leverage = ganar Y perder el doble. En margin call, Alpaca puede liquidar sin previo aviso. Si correlación entre Sentinels sube en mercado adverso, efecto diversificador se neutraliza precisamente cuando más se necesita. Concentración >70% en un símbolo con balance margin >$100K → maintenance margin sube a 50%.

### Dispatcher — Fractional trading (propuesta de Roma, 2026-05-10)

Habilitar fractional shares. Capital pequeño esperado en fase live ($500-2,000) hace mecánicamente imposible repartir entre 9 Sentinels sin fractional — un bot con $50-200 no puede comprar ni 1 share de NVDA/GOOGL/BRK-B. Universe Selection quedaría sesgado a evitar equities caros, distorsionando la selección.

**Datos Alpaca confirmados:** habilitado por defecto en paper y live, >5,000 activos fractionables, mínimo $1 por orden, hasta 9 decimales en `qty` o `notional`, fees iguales que whole shares. Limitaciones: solo long (no short), verificar `fractionable: true` por activo, sin price improvement.

**Cambios técnicos esperados:**
- Auditar 9 Sentinels: clasificar long-only vs long-short. Para los de short, decidir entre (a) excluir del scope live inicial, (b) modificarlos a long-cash, (c) asignarles whole shares. Recomendado (a) o (b) mientras capital sea pequeño.
- Universe Selection: agregar filtros `fractionable=TRUE`, `marginable=TRUE` (cuando se active leverage), `easy_to_borrow=TRUE` (solo si bots shortean con whole shares).
- Cambiar contrato del Dispatcher de `qty=int` a `notional=float`. Más legible, alinea con lógica natural de asignador de capital, robusto a movimiento de precio entre decisión y orden.
- Cap mínimo por bot ~$25-50 para que las fees regulatorias no dominen. Si capital_total / 9 < $25, dispatcher concentra en menos bots o salta el ciclo.
- Métricas dashboard: "fractional fills vs whole share fills", "% capital asignado vía notional".

**Discrepancia con timing propuesto por Roma:** Roma sugiere implementar ya, sin esperar al 27-may, argumentando que es "infraestructura, no estrategia base". **Empujo de vuelta**: cambiar `qty=int` a `notional=float` modifica la cantidad efectivamente ejecutada (ya no rounding al floor entero), lo cual cambia P&L y rompe comparabilidad de datos del período de observación. Específicamente choca con el bug que cerramos hoy en Excepción 1.1 — necesitamos validar primero que el Dispatcher opera correctamente con `qty=int` antes de cambiar la primitiva. Recomendación: rama feature `feature/fractional-trading` mergeada a main el 28-may junto con bloque de infraestructura.

**Caveat de Roman 2026-05-10: filtro fractionable NO debe ser hard exclusion.** Si filtramos hard por `fractionable=TRUE`, ignoramos tickers técnicamente excelentes pero no fractionables (small caps, ADRs, ETFs nicho). En la práctica con los 27 tickers actuales, los 27 son fractionables — pero a futuro con estrategias que exploren universos más amplios, el filtro hard puede descartar oportunidades reales. **Diseño correcto: feasibility check contextualizado.**

Regla de decisión:
```
IF fractionable:
    feasible (operar con notional=$X)
ELIF budget_del_slot >= price * MIN_SHARES_FOR_NON_FRACTIONABLE:
    feasible (operar con qty=int, modo whole shares)
ELSE:
    no feasible → descartar
```

Parámetros calibrables en `config.py`:
- `MIN_SHARES_FOR_NON_FRACTIONABLE` (sugerido: 3-5) — por debajo, el ticker se vuelve "todo o nada" y restringe flexibilidad de scaling in/out.
- `MIN_NOTIONAL_FOR_FRACTIONABLE` (sugerido: $25-50) — por debajo, fees relativas dominan.

**Implicaciones técnicas:**
- El Dispatcher tiene que soportar AMBOS modos de ejecución por ticker, no solo notional. Mezcla de `qty=int` y `notional=float` en un mismo ciclo según el activo. Refactor de `execute_order` para detectar el modo apropiado.
- El Universe Selector recibe el presupuesto del Sentinel como parte del contexto y aplica la regla. Si quiere proponer un non-fractionable, debe demostrar que es feasible (caben ≥3-5 shares en el budget).
- Conexión con risk budgeting intra-Sentinel: el "modo de ejecución" depende de fractional flag + budget del slot interno. Un mismo ticker puede ser apto para Sentinel A con $5K y no apto para Sentinel B con $200.

**Cambios al SYSTEM_PROMPT del Universe Selector** (adicionales a los listados arriba):

> Cuando un ticker no sea fractionable, evaluarlo bajo el modo whole shares: solo recomendarlo si el presupuesto típico del Sentinel permite comprar al menos `MIN_SHARES_FOR_NON_FRACTIONABLE` shares enteras. Si el ticker tiene precio que excede budget/3, descartarlo aunque sea técnicamente excelente.

**Lo que sí se puede hacer durante observación (no toca código de producción):**
- Auditoría documental de los 9 Sentinels (long-only vs long-short).
- Verificar `fractionable: true` flag en assets actuales del universo (SQL contra `sentinel_tickers` cruzado con Alpaca Assets API).
- Diseño del schema de `simulated_costs`.

### Dispatcher — Risk budgeting jerárquico intra-Sentinel (propuesta Roman 2026-05-10)

Tercer nivel de gestión de capital, ANIDADO dentro de cada Sentinel. Hoy el sistema tiene dos niveles (Dispatcher entre Sentinels, Universe Selector elige tickers). Falta el tercero: cómo cada Sentinel reparte SU asignación entre SUS tickers.

**Problema concreto observado el 2026-05-08:**
Mantis recibió $25K (25% del equity) y operó NVDA, XLU, TLT con la misma escala de convicción a nivel de sizing. Si TLT resultaba estructuralmente no apto para rsi_short (por ejemplo, decay como tenían los leveraged inverse rotados bajo el bug), Mantis le ponía el mismo presupuesto que a NVDA (Sharpe 47.19). La pérdida sería a escala completa, no a escala de exploración.

**Concepto:**
- Tickers "maduros" (≥ `WARMUP_TRADES_REQUIRED` trades con métricas calculadas) reciben presupuesto mayor.
- Tickers "nuevos" (< WARMUP) reciben presupuesto pequeño de exploración (10-15% cada uno).
- Cuando un nuevo cruza WARMUP, pasa al grupo maduro y rebalancea.
- Si un nuevo falla rápido en pocos trades (Sharpe muy negativo), Universe Selector lo rota con menos pérdida acumulada.

**Tres implementaciones posibles (de simple a sofisticada):**

- **Opción A — Equal-weighted con cap de exploración (recomendada):** maduros reparten la mayor parte en partes iguales, nuevos reciben un % fijo. Lee `total_trades` per-ticker (ya existe en `performance_scores`). Implementación ~1-2 días.
- **Opción B — Sharpe-weighted intra-Sentinel (mini Half-Kelly anidado):** mismo algoritmo de `allocate_capital` pero anidado dentro del Sentinel. Tickers con Sharpe alto reciben más; nuevos arrancan con piso. Más sofisticado, ~3-5 días.
- **Opción C — Multi-armed bandit (Thompson sampling / UCB):** algoritmo ML estándar de exploration vs exploitation. Overkill para v0.5. Anotado como dirección futura si el sistema crece a v3+.

**Pre-condiciones:**
- **Requiere fractional habilitado.** Sin fractional, el mínimo qty=1 hace mecánicamente imposible "presupuesto pequeño de exploración" para activos caros. Va junto con fractional en Fase 3, no antes.
- Cambio quirúrgico al sizing en `dispatcher.process_signal`: agregar multiplicador per-ticker después de `sentinel_alloc`.

**Beneficios:**
1. Tickers nuevos tienen oportunidad garantizada de operar (no compiten contra estrella del Sentinel por toda la asignación).
2. Acumulan trades rápido → se evalúan rápido → Universe Selector decide rotación con menos pérdida acumulada si el ticker no es apto.
3. Tickers exitosos escalan naturalmente su peso interno cuando cruzan WARMUP.
4. Es Half-Kelly aplicado dentro del Sentinel, no solo entre Sentinels — coherente con la filosofía Kelly conservadora del sistema completo.

**Caveat:**
Cae en regla 4 del `OBSERVATION_PERIOD.md`. Implementación post-27-may, junto con fractional.

### Dispatcher — Paper-Live paralelo (shadow trading Nivel 2)

Cuando se llegue a live, mantener cuenta paper experimental en paralelo a live conservador. Práctica estándar de quant funds.

**Modelo recomendado (Nivel 2):**
- **Live:** versión validada y estable. Cambios solo después de promoción desde paper.
- **Paper experimental:** nuevos parámetros, nuevos bots, ajustes de Universe Selection, hipótesis de leverage, timeframes alternativos. Sin riesgo de capital.
- Criterio de promoción paper → live: mínimo 30 días paper consistentes (idealmente 60), métricas comparadas (Sharpe, drawdown máximo, win rate, hit rate), mejora estadísticamente significativa, sin cambios estructurales en mercado durante evaluación.

**Implementación técnica:**
- Alpaca permite hasta 3 paper accounts. Live es separada con API keys distintas.
- **NO refactorizar el bot a dual-context** (mucho overhead de coordinación). Approach más simple y robusto: dos instancias en paralelo.

```
sentinel-v0.5/         ← live  con .env apuntando a credenciales live
sentinel-v0.5-paper/   ← paper con .env apuntando a credenciales paper
```

- Cada instancia con su propio `main.py`, su propio log, su propio kill switch. Comparten DB PostgreSQL pero con `owner_id` distinto (multi-tenant ya implementado).
- Dashboard puede leer ambas vía filter de owner_id (extensión natural).
- Ventajas vs dual-context: cero refactor, aislamiento real, logs separados.
- Desventaja: doble consumo CPU/memoria/conexiones DB. Sostenible en mini PC dedicado, pesado en ROG.

**Costo oculto del paper a recordar:** paper accounts no aplican borrow fees ni margin interest. Si paper experimental usa leverage, hay que aplicar la simulación de interés (módulo `simulated_costs` mencionado arriba) o las decisiones de promoción serán erróneas.

### The Ear

- **Upgrade de keyword matching a FinBERT** — modelo open-source finance-tuned. Paper de Kirtac & Germano (2024): OPT-based sentiment predijo retornos con 74.4% accuracy vs keyword matching.
- **Nota matutina** — complementar The Ear con una nota matutina estructurada (posible vía plugin Equity Research) para dar contexto más profundo sobre qué esperar del día.

### Alertas

- **Canal de alertas críticas separado** (SMS/push/Telegram) — para Circuit Breaker activado, Kill Switch disparado, órdenes fallando repetidamente, bot caído. No depender solo de email.

### Gestión de riesgo (huecos identificados 2026-05-10 — críticos para fase live)

- **#GR-1 — Stop-loss y take-profit obligatorios a nivel de posición.** Hoy NO existen. Los Sentinels emiten SELL solo cuando técnicamente lo indica su estrategia. En live una posición se puede mover 20-30% en contra antes de que el indicador técnico dé señal de salida natural. Implementación:
  - Stop-loss obligatorio en cada entrada, calculado por ATR (Average True Range × multiplier configurable, ej. 1.5× ATR) o % fijo (ej. 5%).
  - Take-profit opcional, idealmente 2-3× el stop-loss para R/R favorable.
  - Implementación vía Alpaca **bracket orders** (entry + TP + SL atómica) o **OCO orders** (one-cancels-other). Soportado nativamente en Alpaca API.
  - El TP/SL puede definirse a nivel de Sentinel (un valor por strategy_type) o a nivel de ticker (ajustado por ATR del activo).

- **#GR-2 — Position sizing por volatilidad (ATR-based, risk parity).** Hoy sizing es dollar-equal: si Mantis recibe $25K y emite BUY en NVDA (ATR alto) o XLU (ATR bajo), ambos reciben el mismo dollar amount. Pero el riesgo por share es muy distinto. La práctica estándar es **risk parity**:
  ```
  position_size = capital_a_arriesgar / (ATR × multiplier)
  ```
  Cada posición arriesga el mismo % del portfolio (típicamente 1%), independiente del precio del activo. Requiere calcular y persistir ATR por ticker en el Historian.

- **#GR-3 — Drawdown limits a nivel portfolio (auto-pause).** Hoy el Circuit Breaker es solo macro (VIX +30%, SPY -2%). Falta circuit breaker basado en performance del portfolio propio:
  - Si equity cae > 5% en un día → pausar nuevas entradas, gestionar solo existentes.
  - Si cae > 10% en una semana → kill switch automático, requerir reactivación manual.
  - Si cae > 15% acumulado desde inicio → pausa indefinida, review manual.
  - Protege contra "todos los Sentinels en racha mala simultánea" (más probable de lo que parece porque comparten la lectura macro del The Ear).

- **#GR-4 — Reserva mínima de cash obligatoria.** El Dispatcher hoy puede asignar hasta 100%. Cap absoluto sugerido: `MAX_ALLOCATION_TOTAL = 85%` (15% siempre en cash). Razones:
  - Flexibilidad operativa (fees, slippage, gaps).
  - Buffer ante drawdown (cash actúa como amortiguador antes de liquidación forzada del broker).
  - Oportunidad asimétrica (si el mercado cae brutal y aparece setup claro, poder entrar).

### Operacional (huecos identificados 2026-05-10 — críticos para producción)

- **#OP-1 — Backup automático periódico de la DB.** No hay cron de `pg_dump`. Último backup manual: 2026-04-28. Implementación:
  - Script `backup_db.sh` con `pg_dump` diario.
  - Rotación de 7 días + 4 semanas + 12 meses.
  - Copia a destino offline (drive externo, S3 si se quiere cloud).
  - **Verificar restore al menos una vez por mes** (un backup no validado no es un backup).

- **#OP-2 — Heartbeat externo (monitoreo de uptime).** Hoy si el bot crashea silenciosamente, no hay aviso. Implementación:
  - El bot pinga `healthchecks.io` (free tier) cada N minutos desde el main loop.
  - Si el servicio no recibe ping en X minutos, alerta vía email/SMS/Telegram.
  - **Independiente del proceso del bot** — si el bot está caído, el servicio externo lo nota.
  - Cubre exactamente el caso del 2026-05-08 (log silencioso, bot caído, no había forma de enterarse hasta revisar manualmente).

- **#OP-3 — Manejo de "modo degraded" ante caída de APIs externas.** Hoy si Alpaca / NewsAPI / Claude API caen, el bot reacciona con timeouts y errores en logs, pero no tiene un modo explícito de "degraded operation". Implementación:
  - Si NewsAPI cae > N minutos: The Ear pausa veto-by-risk-score, sigue operando solo con VIX/SPY.
  - Si Claude API cae: Universe Selector se desactiva temporalmente, sistema sigue operando con tickers actuales.
  - Si Alpaca data feed cae (no orders, solo data): Sentinels pausan emisión de señales.
  - Si Alpaca trading cae: kill switch automático.
  - Logging explícito de modo operativo + dashboard indica el modo actual.

### Métricas y aprendizaje (huecos identificados 2026-05-10)

- **#ME-1 — Slippage tracking y análisis.** `trades.slippage` existe en schema pero no se usa en métricas. Crítico porque:
  - Paper Alpaca da fill al NBBO directo, sin slippage real.
  - Live = 5-30 bps por trade en activos líquidos, más en small caps.
  - Sharpe paper SIEMPRE > Sharpe live por esta razón.
  Implementación:
  - Reporte regular de slippage promedio por Sentinel y por ticker.
  - Métrica en dashboard.
  - Ajuste de expectativas: `Sharpe_esperado_live = Sharpe_paper × (1 - slippage_factor)`.

- **#ME-2 — Feedback loop estructurado del Universe Selector.** Hoy Claude propone rotaciones pero no se evalúa post-hoc si fueron acertadas. Implementación:
  - N días después de cada rotación (ej. 14 días), un job calcula el Sharpe del ticker nuevo.
  - Compara contra Sharpe que tenía el ticker rotado al momento de la decisión.
  - Marca la rotación como "acertada" / "errada" / "neutral".
  - El historial de aciertos/erradas se incluye en el prompt del Universe Selector como contexto.
  - Es **aprendizaje del Universe Selector basado en su propio track record**.

- **#ME-3 — Métricas de "trades fallidos" como categoría.** % de signals que terminan en trade real ejecutado vs cancelled vs pending. Ya hay datos en `trades.status`, falta dashboard que exponga la métrica.

- **#ME-4 — Tracking de costo Claude API per Sentinel.** Hoy se trackea costo total y por rotation_decision. Sería interesante saber qué Sentinel consume más calls de Universe Selector. Permite optimización del prompt o ajuste de thresholds por Sentinel.

### Compliance, reportes y datos (huecos identificados 2026-05-10)

- **#CR-1 — Reportes fiscales para fase live.** Para fase live con dinero real, los trades generan eventos fiscales:
  - Wash sales, short-term vs long-term gains, costo base ajustado.
  - Exportar en formato compatible con TurboTax / contador.
  - Llevarlo desde el inicio de live, no retroactivo.

- **#CR-2 — Manejo correcto de splits y dividendos.** ¿Historian ajusta precios históricos por splits? ¿Dividendos se cobran y contabilizan en equity? Para holdings de varios días o semanas, esto importa. Verificar comportamiento actual.

- **#CR-3 — Fees realistas simulados en paper.** Alpaca paper no cobra. Live va a tener SEC fee, FINRA TAF, exchange fees. Simular estos costos en paper para que el "Sharpe simulado" sea más representativo del live esperado (relacionado con #ME-1 simulated_costs ya planeado para leverage).

### Trading mechanics adicionales (huecos identificados 2026-05-10 — menores)

- **#TM-1 — Múltiples timeframes.** Todos los Sentinels operan en 15min. Diversificación temporal (5min, 1h, daily) reduciría correlación temporal entre Sentinels (todos reaccionan a la misma vela).

- **#TM-2 — Bracket orders nativas de Alpaca.** Cuando se implemente #GR-1 (SL/TP), usar bracket orders en lugar de gestionar SL/TP con órdenes separadas. Es atómico, menos riesgo de race conditions.

- **#TM-3 — Trailing stops.** Variante de stop-loss que se ajusta al alza con el precio. Útil para estrategias de trend following (S-1, S-4, S-6).

- **#TM-4 — A/B testing de variantes del prompt del Universe Selector.** Hoy cambias el prompt y perdés comparabilidad. Versionar prompts y permitir runs paralelos (relacionado con shadow trading Nivel 2).

- **#TM-5 — Performance attribution.** Descomponer el retorno por fuente: stock picking vs market timing vs allocation. Ayuda a saber qué componente está agregando valor.

### Herramientas externas a integrar (descubiertas 2026-05-10 — Fase 2/3 post-27-may)

- **#HE-1 — QuantStats (`ranaroussi/quantstats`).** Biblioteca Python que genera reportes HTML profesionales con métricas estándar de quant: Sharpe, Sortino, Calmar, MAR ratio, drawdown analysis, monthly returns heatmap, rolling Sharpe, comparación contra benchmark (SPY).
  - Una línea: `qs.reports.html(returns, benchmark='SPY', output='report.html')` → reporte tipo institutional.
  - **Quick win**: 1-2 horas de integración. Genera el reporte mensual/semanal del período de observación con calidad de fondo, muy superior a las métricas actuales del dashboard.
  - Encaja perfectamente con Fase 1 (análisis exhaustivo del período) del plan post-27-may.

- **#HE-2 — Investment Thesis Tracking (skill de `tradermonty/claude-trading-skills`).** Cubre exactamente el gap del feedback loop del Universe Selector (item #ME-2 documentado arriba).
  - State machine persistente: `IDEA → ENTRY_READY → ACTIVE → CLOSED + postmortem`.
  - Cada rotación del Universe Selector se convierte en tesis trackeada con análisis MAE (Maximum Adverse Excursion) y MFE (Maximum Favorable Excursion) al cerrar.
  - Permite saber post-hoc si las rotaciones que propuso Claude fueron acertadas.
  - **Esfuerzo:** 2-3 días para adaptarlo a la estructura de Sentinel (tabla `rotation_decisions` ya tiene la base, falta el state machine + postmortem job).
  - Repo: https://github.com/tradermonty/claude-trading-skills

- **#HE-3 — Alpaca MCP Server oficial (`alpacahq/alpaca-mcp-server`).** Para uso conversacional en Cowork (no para integrar al bot, que ya usa `alpaca-py` SDK directo).
  - Da acceso a cuenta, posiciones, market data, históricos, ejecución de órdenes vía natural language.
  - **Valor:** reduce friction en conversaciones técnicas con Claude (debugging, análisis post-hoc).
  - Instalación equivalente a los plugins de Equity Research / Financial Analysis: ~10 minutos.

- **#HE-4 — Framework de backtesting (Backtrader o QSTrader).** Hoy el sistema NO tiene backtesting. Cualquier hipótesis nueva (cambio threshold, nuevo Sentinel, ajuste Universe Selector prompt) solo se valida ejecutando en paper vivo. Lento e ineficiente.
  - **Backtrader** (`mementum/backtrader`): popular, multi-asset, multi-strategy, broker integration. Madura.
  - **QSTrader**: institutional-grade, modular, foco particular en risk management. Más reciente.
  - Alternativa más simple: **Backtesting.py** (`kernc/backtesting.py`) — ideal para validar estrategias individuales rápidamente.
  - **Esfuerzo:** 1 semana de integración cuidadosa para tener un workflow `(strategy + data) → backtest → metrics → comparison`.
  - **Valor:** habilita validar TODA hipótesis futura (incluyendo cambios al prompt del Universe Selector, nuevos Sentinels, nuevos parámetros) sin requerir semanas de paper trading.
  - Crítico antes de pensar en v2.x (multimercado, La Forja).

- **#HE-5 — Plugin Wealth Management de Anthropic.** Para fase live, no para período de observación.
  - **Tax-loss harvesting:** identificar posiciones con pérdidas no realizadas que pueden cerrarse para reducir carga fiscal. Crítico fin de año.
  - **Portfolio rebalancing:** análisis estructurado.
  - Instalación: ~10 minutos en Cowork, junto con Equity Research / Financial Analysis.
  - Habilitar cuando se acerque transición a live.

- **#HE-6 — Riskfolio-Lib (`dcajasn/Riskfolio-Lib`).** Para v2.x cuando se quiera ir más allá de Sharpe-weighted Half-Kelly.
  - Modelos: Mean-Variance, Black-Litterman, Risk Parity, CVaR optimization, Hierarchical Risk Parity (HRP).
  - **No urgente**: el Half-Kelly actual es buena heurística. Esto es optimización fina cuando haya AUM significativo y track record largo.

### Dashboard multi-rol — evolución a multi-tenant con socios LLC (propuesta Roman 2026-05-10, revisada)

**Modelo correcto:** NO es Investment Adviser con clientes externos. **Es LLC con múltiples socios** (Afterlife Capital LLC) donde el capital agregado de todos opera bajo la misma entidad. Los socios son co-owners de la empresa, no clientes. Roman decide a quién invita a participar — sin captación masiva, sin marketing, sin registro abierto.

**Diferencia crítica con el modelo anterior:** los socios NO son clientes a los que vos prestás servicio de gestión. Son **dueños de la LLC**. La LLC tiene su capital, la LLC invierte ese capital, los retornos se distribuyen entre socios según ownership.

#### Lo que cambia técnicamente (simplificación significativa)

**Una sola cuenta Alpaca (de la entity/LLC):**
- Solo una `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`. Sin multi-account.
- El bot opera la cuenta consolidada como hoy.
- **Multi-account técnico que se había planteado antes NO se necesita.**

**Beneficios operacionales del capital agregado:**
- Diversificación real (9 Sentinels con allocation significativa, no qty=1).
- Acceso a activos caros sin depender solo de fractional.
- Position sizing absoluto mayor (importante con Half-Kelly).
- Costos fijos diluidos (Claude API, eventual market data premium).
- Tax loss harvesting más eficiente a escala.

**Fund accounting interno (sí es necesario):**

Tablas nuevas en schema:
```sql
CREATE TABLE members (
    member_id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(user_id),
    name TEXT,
    joined_at TIMESTAMPTZ,
    is_active BOOLEAN
);

CREATE TABLE capital_movements (
    movement_id UUID PRIMARY KEY,
    member_id UUID REFERENCES members(member_id),
    type TEXT CHECK (type IN ('deposit', 'withdrawal', 'distribution')),
    amount_usd NUMERIC,
    occurred_at TIMESTAMPTZ,
    notes TEXT
);
```

Con esto se puede calcular en cualquier momento:
- % ownership de cada miembro: `(deposits - withdrawals) / total NAV de la LLC`.
- Distribuciones proporcionales según ownership al momento de la ganancia.
- High water mark por miembro (opcional, para no beneficiar al miembro nuevo de ganancias previas).

**Esfuerzo:** ~1 semana de fund accounting básico. Bien definido, no innovación.

#### Roles del dashboard (versión correcta)

| Rol | Aporta capital | Ve | Puede hacer |
|---|---|---|---|
| **ADMIN** (Roman) | Sí (es el socio mayoritario + gestor) | Todo el sistema: portafolio, miembros, aportes, distribuciones | Todo, incluido Kill Switch, panel admin, gestión de miembros |
| **MEMBER** (socios allegados) | Sí | Portafolio agregado de la LLC + SU % ownership + SU saldo actual + SU historial de aportes y distribuciones | Solicitar retiro (via UI, no automático) |
| **VIEWER** (familia/amigos sin aporte) | No | Portafolio agregado read-only, sin info de miembros ni distribuciones | Nada operacional |

Implementación técnica:
- Extender `users.role` con `MEMBER`.
- Relación 1:1 entre `users.user_id` y `members.user_id` cuando aplica.
- Routing dashboard: `/admin`, `/member/{id}`, `/viewer`.
- Cada vista MEMBER filtra a su % de la LLC usando las queries de fund accounting.
- VIEWER ve el portafolio agregado pero NO ve la lista de members ni sus aportes.
- **Todos disclaimers visibles en VIEWER:** "Esto NO es asesoramiento de inversión, solo información sobre el portafolio de Afterlife Capital LLC."

**Esfuerzo total dashboard multi-rol:** ~2-3 semanas (mismo estimado anterior, scope distinto).

#### Lo que cambia legalmente (más simple de lo planteado antes)

**Para una LLC multi-member con socios allegados, lo que se necesita:**

✅ **Sí necesitás (estándar para cualquier multi-member LLC):**
- Operating Agreement con: aportes iniciales por socio, % ownership, distribución de ganancias/pérdidas, gestión de retiros, governance, qué pasa si un socio sale.
- EIN de la LLC y registro federal/estatal (Wyoming, según el plan existente).
- K-1 tax forms anuales por miembro (pass-through taxation).
- Cuenta Alpaca de entity (no personal). Trámite mecánico — articles of incorporation, EIN, operating agreement. Sin licencia.

✅ **Probablemente necesitás (depende de cómo formalices la oferta):**
- **Securities offering exemption** — cuando se le ofrece participación a alguien, técnicamente es oferta de securities:
  - **Section 4(a)(2)** — para ofertas privadas a personas con relación previa y "sofisticación financiera". Sin papeleo formal, limita a friends and family reales.
  - **Reg D 506(b)** — más formal, hasta 35 non-accredited con relación previa, Form D filing con SEC. Provee safe harbor.
- **Blue Sky compliance** estatal en jurisdicciones de los socios.

❌ **NO necesitás (a diferencia del modelo Investment Adviser):**
- Series 65 license.
- Registración como Investment Adviser.
- Form ADV.
- Compliance officer formal.
- Múltiples cuentas Alpaca segregadas.

**Razón:** la LLC opera su propio capital agregado, no "el dinero de otros". Cada socio puso plata para ser dueño de un % de la LLC, no para que vos invirtieras por él como servicio remunerado.

#### Plan de evolución por fases (revisado)

| Fase | Cuándo | Qué incluye |
|---|---|---|
| **Alpha** | Durante o post-observación 27-may | Dashboard multi-rol (ADMIN + VIEWER refinado). Sin socios todavía. Disclaimers visibles. |
| **Beta** | Post-validación fase live Q3 2026 + LLC Wyoming activa | Primeros socios allegados. Operating Agreement formal. Fund accounting en DB. Cuenta Alpaca a nombre de LLC. K-1 por miembro al cierre fiscal. |
| **Gamma** | Si la LLC crece a 10+ socios o se quiere ofrecer más estructuradamente | Reg D 506(b) filing, abogado de securities para revisar Operating Agreement, posible inclusión de accredited investor requirements. |
| **Delta** | Casi nunca según plan Roman | Solo si en algún momento se decide hacer captación pública o cobrar performance fee → ahí sí cambia el modelo a fondo formal. No es el plan. |

#### Sobre los "clientes seleccionados"

Aclaración Roman 2026-05-10: NO hay plan de captación masiva ni marketing. Solo personas allegadas que Roman decide invitar. **Eso encaja en la misma estructura de socios**, no en clientes externos. Cada nuevo "cliente seleccionado" es un nuevo MEMBER de la LLC.

Diferencia con socios fundadores: solo timing y posiblemente términos del Operating Agreement (preferencia en governance para los primeros, etc.). Técnicamente todos son MEMBERs.

#### Caveat importante (sigue vigente, aunque más acotado)

Aunque el modelo LLC multi-member sea más simple regulatoriamente que Investment Adviser, **antes de que el primer socio aporte capital real**, conviene:

1. Operating Agreement revisado por abogado (~$500-1500 una vez).
2. Confirmar que el offering cae bajo exención apropiada (4(a)(2) o Reg D 506(b)).
3. Si los socios son de múltiples estados, verificar Blue Sky en cada uno.

El costo total de setup legal para fase Beta es probablemente **$1,500-3,000 USD** — mucho menos que el $5-15K que mencioné antes para el modelo Investment Adviser. Y NO requiere licencias profesionales.

#### Conexión con memoria existente

Esto refuerza el plan de **LLC Wyoming** (`project_llc_wyoming.md` en memoria). Wyoming es buena jurisdicción para multi-member LLC por bajo costo de mantenimiento, no requiere operating agreement público, charging order protection sólida. La estructura propuesta encaja directamente con esa decisión.

### Dashboard — redefinición arquitectónica (propuesta Roman 2026-05-10)

**Diagnóstico:** el dashboard actual está diseñado como "consola de trading floor en tiempo real" (stream de datos en vivo, métricas mezcladas, foco visual estético). Pero el caso de uso real es distinto: el bot opera solo cada 15min, no requiere supervisión humana continua. Cuando Roman abre el dashboard, lo hace para checkpoints periódicos, no para tomar decisiones de trading en vivo. **Es más bonito que funcional.**

**Reformulación: cuatro vistas separadas, con propósitos distintos.**

#### Vista 1 — "Qué requiere mi atención" (default landing)

Si todo OK, casi vacía. Si algo importa, lo destaca claramente.

- Alertas activas: Circuit Breaker, Kill Switch, errores recurrentes, bot caído.
- Drift contra plan: Sentinel con drawdown > X%, rotación atípica, costo Claude > Y, slippage anormal.
- "Qué pasó desde la última visita" (rotaciones, kills, anomalías) — requiere persistir `last_dashboard_visit_at` por usuario.
- Salud del sistema: uptime, último ciclo OK, latencia Alpaca / NewsAPI / Claude API, estado del heartbeat externo (#OP-2).

Objetivo: en 10 segundos saber si hay que investigar más o cerrar y seguir.

#### Vista 2 — Performance

- Equity curve con benchmark SPY.
- Sharpe / drawdown / win rate por Sentinel con tendencia (rolling, no snapshot).
- Rotaciones recientes con outcome a 14 días (requiere Investment Thesis Tracking #HE-2 + #ME-2 feedback loop).
- Trades recientes con outcome real: FILLED vs CANCELLED vs PENDING, slippage real (#ME-1).
- Botón "Generar reporte QuantStats" → descargable HTML profesional (#HE-1).

#### Vista 3 — Auditoría

Para sesiones de revisión profunda (cierre de período de observación, decisiones de cambio):

- Reportes QuantStats descargables: semanal, mensual, custom range.
- Logs filtrados por nivel y módulo.
- Configuración actual: todos los thresholds visibles en una sola tabla con su justificación (RATIONALE.md inline).
- Historial completo de rotaciones con razonamiento de Claude (`claude_reasoning`).
- Audit log inmutable (relacionado con #CR-1 compliance).

#### Vista 4 — Operación

Acciones manuales:

- Kill Switch (ya existe).
- Panel admin (ya existe).
- Pause selectivo por Sentinel — nuevo. Relacionado con #GR-3 drawdown limits que también pausan automáticamente.
- Trigger manual de rotation si se quiere forzar.
- Trigger manual de rebalance.

#### Principio rector

**Separar "lo que importa ahora" de "lo que importa siempre".** Cada vista responde a una pregunta específica:
- Vista 1: "¿Pasa algo?"
- Vista 2: "¿Está rindiendo?"
- Vista 3: "¿Por qué pasó X?"
- Vista 4: "Quiero hacer Y"

**Esfuerzo estimado:** 1-2 semanas de trabajo cuidadoso. Requiere coordinación con el handoff Design si se quiere mantener el lenguaje visual existente. Alternativa: nuevo handoff Design con este briefing.

**Pre-condiciones:** la vista 2 depende de #HE-2 (Investment Thesis Tracking) y #ME-1 (slippage tracking). La vista 1 depende de #OP-2 (heartbeat). Hacerlo después de esas piezas o stub las dependencias mientras tanto.

### Deuda técnica adicional (cruce contra TECHDEBT.md, identificada 2026-05-10)

#### Estructural — importa para que el sistema funcione bien

- **#TD-1 — `historian.calculate_performance` FIFO pairing rompe con multi-ticker.** Si un Sentinel emite BUY-BUY-SELL en distintos tickers, el cálculo se desincroniza. Crítico cuando hay >1 ticker activo por Sentinel (Mantis con NVDA+XLU+TLT post-cleanup). Actualizar a pareo por ticker.
- **#TD-2 — `dispatcher.process_signal` no valida `signal_type` al inicio.** Si llega "HOLD" o algo inesperado, se interpreta como SELL por el `if signal_type == "BUY" else "SELL"`. Defensa débil. Agregar `if signal_type not in ("BUY", "SELL"): return invalid_signal`.
- **#TD-3 — `correlation_guard` enmascara falla de datos como "todo bien".** `if incoming_ticker not in bars` aprueba con warning en lugar de rechazar con `reason="no_data"`. El sistema decide con datos parciales sin saberlo.
- **#TD-4 — `correlation_guard` con ticker duplicado.** Si incoming es el mismo ticker ya abierto, agrega 1.0 al promedio de correlaciones. Distorsiona la métrica. Manejar aparte como veto inmediato (relacionado con #H-5b).
- **#TD-5 — `the_ear._fetch_price_changes` retorna 0.0 si no hay 2 barras.** Enmascara "sin datos" como "0% change". El Circuit Breaker puede no activarse cuando debería. Cambiar a `None` para distinguir.
- **#TD-6 — `the_ear` silently skips si `NEWS_API_KEY` falta.** Si por error se pierde la API key, The Ear deja de funcionar sin alerta. Loggear como warning + métrica visible.
- **#TD-7 — Logs de fallback poco visibles.** Cuando The Ear falla, el dispatcher cae a `can_trade=False` con log nivel `error`. Debería ser `CRITICAL`. Cuando un Sentinel cae al fallback de 5% por sin score, no se loggea — debería loggearse explícitamente.

#### Infraestructura — importa para 24/7 producción

- **#TD-8 — Logs sin rotación temporal.** `RotatingFileHandler(5MB × 3 backups)` llena rápido en 24/7. Cambiar a `TimedRotatingFileHandler` con rotación diaria.
- **#TD-9 — `requirements.txt` con `>=` pinning.** Vulnerable a breaking changes en updates de dependencias. Pinear a versión exacta para producción y actualizar manualmente.
- **#TD-10 — No hay `/api/healthz` dedicado.** `/api/status` cumple ese rol pero también devuelve datos. Separar en `/api/healthz` (200/503) para load balancers. Conecta con #OP-2 (heartbeat externo).
- **#TD-11 — `RotatingFileHandler` con path relativo** en api.py y main.py. Si uvicorn arranca desde otro CWD, crea logs en otro directorio. Resolver con `Path(__file__).parent / "logs" / "sentinel.log"`.
- **#TD-12 — DB sin `TIMESTAMP WITH TIME ZONE`.** Timestamps son sin TZ, server time (EDT). Reportes "today" se desincronizan si la DB cambia de TZ. Crítico durante migración a Mini PC. Migración: alterar columnas a `TIMESTAMPTZ`.
- **#TD-13 — API sin versionado** (`/api/v1/`). Para futuras versiones con cambios potencialmente breaking.

#### Python / FastAPI deprecations (futura compatibility)

- **#TD-14 — `Query(..., regex=...)` deprecated en FastAPI 0.110+** → cambiar a `pattern=`.
- **#TD-15 — `datetime.utcnow()` deprecated en Python 3.12+** → `datetime.now(timezone.utc)`.
- **#TD-16 — `FastAPI(version=...)` falta.** Cosmético, útil para `/docs` y header del JSON OpenAPI.

#### Dashboard JS — robustez

- **#TD-17 — `localStorage` input no sanitizado** en sentinel-data.js. Si alguien manipula `sentinel.lang` con string raro, pasa a STATE.
- **#TD-18 — `_fetchJson` no distingue 401 de error de red.** Cuando se agregue auth refresh, no podés re-auth.
- **#TD-19 — Handlers de eventos sin `closest`/event delegation.** Si el handoff Design cambia IDs en una nueva entrega, todo se rompe en silencio.
- **#TD-20 — `killTickMock` reemplaza `window.setTimeout` globalmente.** Si una lib futura usa `setTimeout(tickFn, ...)`, también se intercepta. Agregar mecanismo de unload del intercept.
- **#TD-21 — Banner cuando SSE se desconecta** por más de N segundos. Hoy reconecta en silencio.

#### Refactor cosmético / código muerto

- **#TD-22 — `regime_classifier.py` con código inalcanzable** después de `return` tempranos (S-10 desactivado). Cuando se reactive, sacar los returns.
- **#TD-23 — `historian.get_trade_history` posiblemente código muerto** (no se usa en ningún call site). Verificar y eliminar.
- **#TD-24 — Constantes hardcodeadas que deberían ir a `config.py`**: `_BARS_LOOKBACK`, `_FETCH_DAYS` (sentinels), `_SSE_INTERVAL_SECONDS` (api), `min_size/max_size` del pool de DB (historian).
- **#TD-25 — `self.open_positions: dict[str, dict]` → `dataclass Position`** para tipado fuerte. Mejora legibilidad y type checking.

#### Validación matemática / quant

- **#TD-26 — Fórmula Half-Kelly del Dispatcher requiere validación de quant.** `base = (sharpe / total_sharpe) * 100; kelly_adjusted = base * KELLY_FRACTION` es Sharpe-weighted Half-Kelly heurístico, no Kelly clásico (`f = p - q/b`). Antes de fase live, auditar formalmente con criterio cuantitativo. Cubierto por plan de "code review externo con IAs independientes".

### Documentación

- **INCIDENT_PLAYBOOK.md** — secuencia escrita para escenarios catastróficos: (1) Kill Switch primero, (2) después diagnosticar.
- **RATIONALE.md** — razones detrás de cada parámetro congelado.
- **Directrices de diseño para emails** — mejorar peso de fuente, contraste, y crear guía visual fácil de actualizar.

### Features (v2.5+)

- **Multimercado** — expandir más allá de equity USA.
- **La Forja (v3.0)** — sistema de creación y prueba de nuevas estrategias.
- **Batching de Universe Selector** — optimizar llamadas a Claude API.
- **Regime Classifier (S-10)** — reactivar después de 50-100 trades reales con RSI, MACD, breadth, yield curve.

---

## Plan de revisión exhaustiva post-27-may (propuesta Roman 2026-05-10)

> Pausa total del bot, balance y auditoría completa antes de avanzar con cualquier feature (fractional, leverage, paper-live paralelo, plugin Equity Research, idle_timeout).

### Fase 1 — Análisis de funcionamiento (días 1-3 post-27-may)

**Métricas del período de observación (a calcular sobre datos 28-abr → 27-may):**

- Trades totales por Sentinel: ¿alcanzó cada uno el umbral de 50+ trades para análisis estadísticamente significativo?
- Win rate, Sharpe ratio, profit factor, drawdown máximo por Sentinel y agregado.
- Slippage promedio (cuando se persista en `trades.slippage`).
- Equity curve del portfolio paper completo.
- Universe Selection: número total de rotaciones, costo total Claude API, % de candidatos pre-aprobados (warning) vs urgentes (decay), efectividad de las rotaciones (¿los nuevos tickers superaron a los rotados?).
- The Ear: número de veces que vetó trading (`can_trade=False`), correlación entre vetos y movimientos macro reales del día, falsos positivos/negativos.
- CorrelationGuard: cantidad de señales reducidas vs descartadas, concentración real promedio del portfolio.

**Decisión sobre cada componente:**
- ¿Funcionó? ¿Funcionó parcialmente? ¿Falló? → input para Fase 2.

### Fase 2 — Auditoría de calidad de código (días 4-7)

**Aplicar `BUENAS_PRACTICAS_V2.md v2.3` y `PROTOCOL_SESSION.md` al codebase completo:**

- Convertir TODO el sistema a las convenciones del manual (naming, estructura, comentarios, tests).
- Cubrir backlog #H pendiente: **#H-4 float→Decimal en cálculos financieros** (cerrado parcialmente en `dispatcher.allocate_capital`, pero hay otros sitios: `correlation_guard`, `historian.calculate_performance`, etc. — ver `outputs/decimales_en_finanzas_profesionales.md` de Cowork con la guía completa).
- ~~Cerrar **#H-5b cache desactualizado en open_positions tras SELL**~~ ✅ **CERRADO 2026-05-23** (commit `6a427c5` — refactor a helper `_apply_fill_to_cache` + TDD 4 casos. Fix definitivo aplicado tras confirmar que el bug era crónico: 45 warnings "Posiciones fantasma" en 5 días según snapshot del 23-may).
- Hardening dashboard: XSS innerHTML, race SSE, defensa Chart.js (item del backlog operativo del CLAUDE.md).
- Mejorar `_rsi()` a Wilder smoothing real (S-2, S-8).
- Reconciliación post-restart de limit orders (#H-6b).
- Test coverage: agregar tests unitarios para `dispatcher.allocate_capital`, `historian.evaluate_decay`, `universe_selector.evaluate_all_sentinels`. Cobertura objetivo mínima 70% sobre módulos core.

**Items nuevos derivados de la sesión 23-may (Cowork + Code):**

- **#FASE2-NEW-1 — Implementación de §15 (Automatización + Enforcement).** La sección §15 del manual v2.3 es spec; implementarla en este repo es trabajo aparte:
  - Setup pre-commit (`.pre-commit-config.yaml`) con: `gitleaks`/`detect-secrets`, `check-added-large-files`, `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `ruff` (Python), `black --check`, `pytest --collect-only`.
  - Setup CI (GitHub Actions): suite de tests completa, audit de archivos sensibles en PRs, lint completo, gate de cobertura ≥ piso definido en módulos críticos.
  - Decidir stack (`ruff` vs `flake8 + isort`, `gitleaks` vs `detect-secrets`, `pytest-cov` para cobertura).
  - Estimación: 2-3 sesiones de ingeniería. Cierra el gap exacto que casi nos cuesta exponer `.env.bak` con secretos en sesión 23-may.

- **#FASE2-NEW-2 — Normalizar `requirements.txt` a versiones exactas (==).** Observación de Code en LOG 20:20: el archivo hoy mezcla `>=` (resto) con `==` (quantstats nuevo). §7.5 del manual pide `==` para producción. Pinear todas las deps con versión exacta. Documentar política de actualización (cuándo se actualiza una versión y quién valida).

- **#FASE2-NEW-3 — Agregar marcadores `§` + índice interno a archivos >500 LOC.** Observación de Code en LOG 20:20: `api.py` (1860 LOC), `historian.py` (1650 LOC), `email_service.py` (1432 LOC), `dispatcher.py` (~717 LOC). §2.2 del manual requiere para archivos >500 líneas: justificación documentada de por qué no se ha separado + secciones con separadores `# § N — Título` + índice interno al inicio. Aplicar a los 4 archivos. **Hacer esto ANTES de cualquier refactor** — habilita Edit seguro y navegación sin truncado.

- **#FASE2-NEW-4 — Cobertura ≥95% en módulos críticos (§8.6 del manual v2.3).** Definir paths críticos = `dispatcher` (sizing, allocate_capital, process_signal, callbacks de fills, `_apply_fill_to_cache`), `historian` (calculate_performance, evaluate_decay, get_sentinel_scores), `the_ear` (evaluate, circuit_breaker), `correlation_guard` (correlation calc), `universe_selector` (evaluate_all_sentinels). Tests TDD para cada uno. Configurar `pytest-cov` con fail-under=95 en esos módulos.

- **#FASE2-NEW-5 — Gate pre-live (§8.6).** Antes de transición a fase live (Fase 5), validar checklist:
  - [ ] Test unitario para cada función crítica (definidas en #FASE2-NEW-4).
  - [ ] Test rojo→verde demostrado para cada bug financiero (TDD).
  - [ ] Test de regresión por cada bug previo (#H-4, #H-5b, #H-6b, etc.).
  - [ ] Cobertura ≥95% confirmada por CI sobre módulos críticos.
  - **Sin checklist completo, NO se promueve a live.**

**Code review externo (opcional pero recomendado):**
- Una IA independiente (Plan documentado en memoria: `project_audit_ia_independiente.md` — 3 perfiles distintos para auditoría desde código / matemáticas / investigación).
- Particular atención a: race conditions en async (TheEar, Universe Selector concurrente), manejo de errores (exception swallowing), seguridad (SQL injection en queries dinámicas, validación de inputs del panel admin).

### Fase 3 — Implementación de features bloqueadas (días 8-14)

**Por orden de prioridad (más conservador a más ambicioso):**

1. **Renombre cosmético `S-2 RSI Short → RSI Fast Reversion`** en dashboard. 15 min de trabajo.
2. **Fix #H-5b** (`self.open_positions.pop(ticker, None)` en SELL filled). 30 min.
3. **Refinamiento del prompt del Universe Selector** con lista negra de leveraged/decay products + filtros técnicos (fractionable, shortable, etc.). 2-3 hrs.
4. **Fractional trading**: cambio de contrato Dispatcher `qty=int` → `notional=float`, filtros en Universe Selection, cap mínimo por bot. ~1 día.
5. **Módulo `simulated_costs`** para interés de margin paper (preparación para leverage). ~1 día.
6. **Trigger `idle_timeout`** en Universe Selector con umbrales por strategy_type. ~1 día.
7. **Reactivar S-10 RegimeClassifier** (si hay 50-100 trades reales acumulados, evaluar accuracy con features adicionales).
8. **Plugin Equity Research**: instalación en Cowork primero (para uso conversacional), después porting de skills al system prompt del Universe Selector. ~2-3 días.

### Fase 4 — Próximo período de observación amplio (30 días, junio)

- Sistema con todos los fixes aplicados, código limpio, lista negra de productos exóticos.
- Sigue en paper, sigue sin leverage.
- Validar que las métricas mejoran consistentemente vs el período abril-mayo.
- Solo después de este segundo período exitoso, evaluar transición a v1.0 (live con capital pequeño + fractional, sin leverage todavía).

### Fase 5 — Live conservador (julio 2026, condicionado)

- Capital inicial pequeño ($500-2,000).
- Solo bots long-cash validados.
- Fractional habilitado.
- Sin leverage.
- Paper experimental en paralelo (Nivel 2 shadow trading) para futuras hipótesis.

### Fase 6 — Hipótesis exploratorias (post-julio, condicionado)

- Si live conservador muestra alpha sostenido durante 30+ días: evaluar hipótesis de leverage escalonado (1.25x con condiciones).
- Considerar shorts intencionales (modificación lógica del Dispatcher).
- Multimercado, La Forja, etc.

---

*Cada idea se evalúa en la sesión de cierre del 27 de mayo. Priorizar por impacto vs esfuerzo.*

*Actualización 2026-05-23: período cerrado anticipadamente (ver `OBSERVATION_PERIOD.md` sección "Cierre del período"). Nuevos items #FASE2-NEW-1 a #FASE2-NEW-5 agregados a Fase 2 con base en hallazgos de la sesión Cowork↔Code del 23-may. Manual actualizado a v2.3. #H-5b cerrado.*
