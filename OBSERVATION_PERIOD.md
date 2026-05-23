# OBSERVATION_PERIOD.md — Período de Observación Protegida

**Fecha de inicio:** 27 de abril de 2026
**Fecha de revisión:** 27 de mayo de 2026
**Sistema:** Sentinel v2.3 con Universe Selection (Claude Sonnet 4.6 + Marco All Weather/AQR + Coordinación entre Sentinels Opción A)

---

## Por qué existe este documento

La investigación comparativa con casos de la industria (AQR, Bridgewater All Weather, Knight Capital, August Osei) identificó un patrón crítico: los sistemas de trading sistemático que se modifican constantemente durante validación contaminan la evidencia estadística que están tratando de generar. Cada cambio de parámetro, lógica o comportamiento durante el período de prueba hace que los datos antes y después no sean comparables.

Después de 7 días de construcción intensa (21–27 abril 2026), Sentinel v2.3 entra en período de observación protegida. El objetivo es generar 30 días de datos limpios que permitan evaluar honestamente si el sistema funciona como hipótesis.

> *"Cada cambio durante el período de validación contamina los datos. Si en día 15 de paper trading se cambia un threshold, los próximos 60 días no son comparables con los primeros 15."* — Recomendación 3, investigación comparativa

---

## Estado del sistema al inicio del período

### Componentes operativos

- 9 Sentinels con tickers iniciales fijos (rotables vía Universe Selector)
- Dispatcher con Sharpe-weighted Half-Kelly (KELLY_FRACTION = 0.5, tope 25%, piso 5%)
- CorrelationGuard (rolling 60 velas, threshold 0.75)
- The Ear (NewsAPI, keyword matching word-boundary, persistencia de titulares)
- Historian (Performance Score, Decay detection, Pre-Decay Warning)
- Universe Selector (Claude Sonnet 4.6, prompt All Weather + AQR, Coordinación Opción A)
- Regime Classifier (S-10) DESACTIVADO (régimen fijo NEUTRAL)

### Configuración numérica congelada

| Parámetro | Valor | Razón documentada |
|---|---|---|
| KELLY_FRACTION | 0.5 | Half-Kelly captura ~75% del crecimiento óptimo con ~50% del drawdown |
| MIN_CAPITAL_PER_SENTINEL | 5% | Piso para Sentinels sin historial |
| MAX_CAPITAL_PER_SENTINEL | 25% | Tope anti-concentración por Sentinel |
| CORRELATION_THRESHOLD | 0.75 | Reducción de tamaño cuando avg correlación supera este valor |
| WARNING_THRESHOLD_WIN_RATE | 0.45 | Pre-decay anticipado |
| WARNING_THRESHOLD_SHARPE | 0.65 | Pre-decay anticipado |
| DECAY_THRESHOLD_WIN_RATE | 0.40 | Decay confirmado, activa rotación |
| DECAY_THRESHOLD_SHARPE | 0.50 | Decay confirmado |
| WARMUP_TRADES_MINIMUM | 10 | Trades mínimos antes de evaluar performance |
| RISK_SCORE_VETO_THRESHOLD | 0.7 | Veto operativo de The Ear |
| PARKING_BRAKE_TIME | 15:45 ET | Sin órdenes nuevas |
| UNIVERSE_SELECTION_TIMEOUT_SECONDS | 60 | Per-call timeout a Claude API |
| UNIVERSE_SELECTION_CYCLE_TIMEOUT_SECONDS | 180 | Cycle timeout total |
| UNIVERSE_SELECTION_MAX_COST_PER_CALL_USD | 0.20 | Cost cap por llamada |
| UNIVERSE_SELECTION_CANDIDATE_TTL_DAYS | 7 | Expiración de pending_candidates |

---

## Reglas durante el período de observación

### ✅ PERMITIDO

**1. Bug fixes críticos.** Definición de "crítico":
- El bot crashea, pierde estado, o queda en estado inconsistente
- Pierde dinero por error técnico (ej: orden duplicada, persistencia rota)
- Datos corruptos en DB que requieren intervención
- Vulnerabilidades de seguridad expuestas

Ejemplos de fixes que sí calificarían:
- Si trades.status sigue rompiendo persistencia → fix
- Si Cloudflare Tunnel cae y no hay alerta → fix
- Si Universe Selector empieza a hacer rotaciones absurdas (ej: recomendar penny stocks) → investigar y posiblemente revertir cambio

**2. Documentación.** Sin restricciones:
- Actualizar BLUEPRINT_AS_BUILT.md
- Crear INCIDENT_PLAYBOOK.md
- Crear RATIONALE.md (razones detrás de cada parámetro)
- Logs de eventos importantes
- Notes sobre observaciones del paper trading

**3. Observabilidad read-only.** Scripts y herramientas que solo leen datos:
- Reportes semanales de The Ear (titulares matched, falsos positivos sospechosos)
- Análisis de rotation_decisions (¿qué propuso Claude? ¿se ejecutó?)
- Dashboards de métricas adicionales (sin alterar la lógica)
- Exports de datos para análisis offline

**4. Cosmética del dashboard.** Mejoras visuales que NO cambian comportamiento:
- Tema light vs dark
- Traducciones (4 idiomas ya soportados)
- Tooltips informativos
- Layouts mejorados
- Colores y estilos
- Card de Universe Selector en sección de agentes

**5. Migración de infraestructura.** Cambios de hardware/red sin cambios de código:
- Migrar a Mini PC (con plan documentado, ver MIGRATION_PLAN_MINIPC.md)
- Cambiar proveedor de DNS si hace falta
- Backup y restore de DB

### ❌ NO PERMITIDO

**1. Modificar el SYSTEM_PROMPT del Universe Selector.** Está congelado.

**2. Cambiar thresholds.** Ningún valor de la tabla "Configuración numérica congelada" puede modificarse.

**3. Agregar o remover Sentinels.** Los 9 actuales son los que validan.

**4. Cambiar lógica de cualquier agente.** Sentinels, Dispatcher, CorrelationGuard, The Ear, Historian, Universe Selector — todos congelados.

**5. Ajustar parámetros de estrategias técnicas.** SMA 10/50, RSI(2), EMA 8/21/55, Bollinger BBW p10, etc. — todos congelados.

**6. Modificar prompts a Claude.** Ni el system prompt ni el user prompt template.

**7. Cambiar timeouts.** A menos que sean bloqueantes (cycle timeout muy corto causando que TODOS los Sentinels hagan timeout).

**8. Activar el Regime Classifier (S-10).** Sigue desactivado hasta que haya 50-100 trades reales.

**9. Cambiar de paper a live trading.** El período de observación es exclusivo de paper trading.

**10. Implementar features pendientes.** v2.5 (multimercado), v3.0 (La Forja), batching de Universe Selector, FinBERT — todo eso queda fuera del período.

---

## Excepciones documentables

Si durante el período surge una situación que requiere un cambio que cae en zona gris (ej: un parámetro está claramente mal calibrado y el sistema está perdiendo dinero por eso, no porque la estrategia falle), aplicar este proceso:

1. **Documentar la situación** en este archivo bajo sección "Excepciones".
2. **Justificar por qué el cambio es necesario** (no opcional).
3. **Anotar la fecha exacta del cambio** para poder separar los datos antes y después en análisis posterior.
4. **Marcar los datos como "antes excepción N"** vs "después excepción N".
5. **Reiniciar el contador del período de observación** desde la fecha del cambio.

El objetivo es preservar la disciplina, pero no a costa de comportamiento operativo claramente erróneo.

---

## Excepciones registradas

### Excepción 1 — Bug fix: Scores parciales + Agregación de Dispatcher

**Fecha:** 7 de mayo de 2026

**Situación:** Investigación profunda reveló tres bugs interconectados que impedían al sistema funcionar como fue diseñado:

1. **historian.py — evaluate_decay() no escribía scores hasta warmup completo (10 RT por ticker).** Esto dejaba a Dispatcher, CorrelationGuard, Universe Selector y Dashboard sin datos para 8 de 9 Sentinels. El sistema operaba ciego con todos los Sentinels en el piso de 5%.

2. **dispatcher.py — allocate_capital() sobrescribía allocation per-sentinel con el último ticker procesado** en vez de agregar. Como los scores venían ordenados por sharpe DESC, el ticker con peor Sharpe ganaba. Mantis (S-2) con Sharpe 39.96 en NVDA quedaba diluido.

3. **api.py + sentinel-data.js — Dashboard mostraba Sharpe promedio simple** incluyendo tickers sin datos (sharpe=0), diluyendo artificialmente las métricas visibles (39.96 → 13.32).

**Justificación:** Estos son bugs de implementación, no cambios de lógica o thresholds. El sistema fue diseñado para escribir scores y alimentar al Dispatcher (no lo hacía hasta 10 RT), agregar scores por sentinel (sobrescribía con el último ticker), y mostrar métricas representativas (diluía con zeros). Sin estos fixes, el período de observación no evalúa la hipótesis del sistema sino una versión rota.

**Cambios realizados:**
- `historian.py`: evaluate_decay() ahora escribe scores parciales con ≥2 RT (decay solo se evalúa con ≥10 RT)
- `dispatcher.py`: allocate_capital() agrega por sentinel usando promedio ponderado por trades
- `api.py`: Endpoint /api/sentinels ahora expone total_trades por ticker
- `dashboard/sentinel-data.js`: Sharpe usa promedio ponderado por trades, excluyendo tickers sin datos
- `dashboard/index.html`: Cache-bust actualizado a v=20260507b

**Marca de datos:** Datos generados antes del 7 de mayo de 2026 = "pre-excepción-1". Datos posteriores = "post-excepción-1".

**Contador del período:** NO se reinicia. Estos fixes no cambian la hipótesis bajo prueba, solo permiten que se pruebe correctamente.

---

### Excepción 1.2 — 2026-05-13: tarjeta de capital invertido en el dashboard

**Fecha:** 13 de mayo de 2026.

**Situación:** El dashboard actual mostraba `Capital`, `PnL día` y `Max DD` sobre el **equity total** (~$100K). Esa métrica diluye la rentabilidad real porque el sistema solo despliega ~1.6% del capital (hallazgo del sizing trivial del 2026-05-11). Resultado: el operador ve "PnL día -0.015%" cuando en realidad el sistema ganó/perdió ~1% sobre el capital efectivamente invertido. Las decisiones de revisión durante el período de observación se vuelven imposibles si la métrica visible es engañosa.

**Cambio:**
- Nuevo endpoint `/api/account/capital` (en `sentinel-v0.5/api.py`). Read-only, formato `{ data, meta }` cumpliendo `BUENAS_PRACTICAS_V2.md` sección 6.2, responsabilidad única (solo métricas de capital — no positions ni unrealized pnl). Reutiliza `client.get_account()` de Alpaca.
- Tarjeta nueva en `dashboard/index.html` debajo de la curva de Equity (3 líneas: Capital total / Invertido / PnL s/ invertido).
- Función `loadCapitalMetrics()` en `dashboard/sentinel-data.js` (camelCase, <30 líneas, error handling con fallback a `—`, llamada desde `reloadFromAPI()`).
- i18n en 4 idiomas (`sentinel-i18n.js`).
- `dashboard/CHANGELOG-UI.md` actualizado para Claude Design.

**Justificación de la excepción:** Cosmética del dashboard + endpoint read-only sin lógica del bot. Cumple punto 4 ("Cosmética del dashboard") y punto 3 ("Observabilidad read-only") de la sección PERMITIDO. NO toca: thresholds, prompts, lógica de Sentinels, Dispatcher, CorrelationGuard, The Ear, Historian, Universe Selector, schema DB, datos persistidos. NO modifica endpoints existentes (el viejo `/api/account/equity` queda intacto — deuda técnica para refactorizar a formato `{ data, meta }` en Fase 2 post-27-may).

**Marca de datos:** ninguna. El cambio no afecta el comportamiento del bot ni los datos del período de observación. Solo expone información ya existente en Alpaca que antes no era visible.

**Contador del período:** NO se reinicia. Mismo argumento que Excepción 1 y 1.1: arreglos de visibilidad/correctitud sin cambio de hipótesis.

**Validaciones:**
- `python -m py_compile sentinel-v0.5/api.py` → OK.
- `node --check dashboard/sentinel-data.js && node --check dashboard/sentinel-i18n.js` → OK.
- CRLF preservado en `sentinel-i18n.js` (456 CRLF, 0 LF puro). LF preservado en api.py, index.html, sentinel-data.js.
- Backups completos en `backups/2026-05-13/`.

**Activación:** requiere `sentinel-stop.bat` → 10s → `sentinel-start.bat` para que `api.py` cargue el endpoint nuevo. Los cambios en `dashboard/*` ya están en disco; navegador debe hacer cache-bust (`?v=20260513a` ya aplicado en `index.html`).

---

### Intervención manual 2026-05-16: cierre de short QQQ accidental por bug #H-5b (reaparición)

**Tipo:** corrección de bug (permitida según sección PERMITIDO punto 1 de este documento).
**Ejecutor pendiente:** Roman manual vía Alpaca Dashboard, lunes 18-may pre-apertura.
**Detalle completo:** `backups/2026-05-16/manual_intervention_qqq_short_cleanup.md`.

**Resumen:** El viernes 15-may, el cache `dispatcher.open_positions` quedó desactualizado tras los SELLs de apertura sobre IWM, TSLA y SPY (logs `Posiciones fantasma (local pero no en Alpaca)` a las 09:45:04 y 10:00:04). El mismo patrón se manifestó con QQQ: el primer SELL del 09:45:09 cerró legítimamente el long del 13-may (compra @ $713.67 → exit @ $707.31, -$6.36), pero el dispatcher dejó pasar dos SELLs subsiguientes contra cache obsoleto a las 09:45:14 (`sell_short` @ $707.28) y 10:30:07 (`sell_short` @ $710.85). Resultado: posición QQQ short -2 shares @ avg $708.48 que el bot NUNCA decidió tomar.

**Estado al sábado 16-may (mercado cerrado):**
- Equity: $100,087.20 | Cash: $99,883.07 | balance_asof = 2026-05-15
- Long market value: $1,621.99 | Short market value: -$1,417.86
- Posición QQQ: -2 sh @ avg $708.48, current price $708.93, unrealized PnL -$0.90
- Otras posiciones long sin tocar: AAPL, NVDA, SPY, TLT, XLP, XLU, XLV (todas qty=1, sizing trivial).
- P&L día 15-may: -$84.64 (-0.08%). Trade peor: AMD -$19.81 (entry 14-may por S-4 MACD+Volume @ $449.26 / exit 15-may @ $429.45 con caída intradía de -4.41%).

**Plan de cierre (lunes 18-may pre-apertura):**
1. `sentinel-stop.bat` para evitar race con opening cross.
2. Alpaca Dashboard → Positions → QQQ → Close position (market BUY 2 sh).
3. Verificar `GET /v2/positions/QQQ` → 404, registrar fill price, hora, cash, equity post-fill.
4. `sentinel-start.bat`.

**Fill confirmado (verificado vía Alpaca API 2026-05-18 09:35 ET):**
- Submitted (Roman): sábado 16-may 17:17 ET (after-hours, queued para opening cross). Order ID `47b0c814-8677-4bd3-9178-a4c570ae9e15`. Position intent `buy_to_close`.
- Filled at: **lunes 18-may 09:30:41 ET** (13:30:41 UTC), 41 segundos post-apertura.
- Filled avg price: **$711.31** (2 sh).
- Realized P&L del cierre: **(708.48 − 711.31) × 2 = −$5.66** (pérdida del opening cross). Costo total acumulado del bug #H-5b en QQQ (15-may + 18-may): **−$12.02**.
- Posición QQQ post-fill: **0 shares** (`GET /v2/positions/QQQ` → 404 "position does not exist") ✅
- Cash post-fill: **$99,199.61** | Equity: **$100,081.85** | Short market value: **$0** | Long market value: $882.24 | Buying power: $396,700.96.
- **Race condition detectada — pero mitigada por la guardrail anti-duplicado del dispatcher:**
  - 09:30:34 — S-8 RSI Divergence emitió señal BUY QQQ @ $712.14 (post bullish div price 708.5650→706.9200 RSI 28.23→31.79).
  - 09:30:36 — Dispatcher WARNING: `Posiciones no rastreadas (Alpaca pero no local): {'SPY','QQQ','XLU','XLV','TLT','AAPL','XLP','NVDA'}` — cache local desincronizado (efecto de #H-5b en arranque).
  - 09:30:41 — Fill manual del BUY 2 @ $711.31.
  - 09:30:43 — Dispatcher: `Señal BUY QQQ omitida — ya hay posición abierta este cycle`. La guardrail previno que el bot enviara un BUY 1 adicional sobre la posición recién cerrada. Sin esa protección, la cuenta hubiera quedado long +1 QQQ.
- **Confirmación de intervención externa:** `Grep` sobre `sentinel.log` con patrón `^2026-05-18.*Orden enviada.*QQQ BUY qty=2` → **0 matches**. El fill no provino del dispatcher.
- **Nota sobre el plan original:** Roman optó por enviar la orden el sábado after-hours (Alpaca la re-routed automáticamente al opening cross del lunes), en lugar de stop/start del bot. La guardrail anti-duplicado funcionó como red de seguridad, así que el approach fue equivalente en resultado al del 11-may con SPY.
- **Estado:** evento **CERRADO LIMPIAMENTE**. Sección 7 de `backups/2026-05-16/manual_intervention_qqq_short_cleanup.md` completa.
- **Implicación técnica:** #H-5b sigue activo en el cache `dispatcher.open_positions` (mensaje "Posiciones no rastreadas" reaparece). El fix definitivo queda diferido a post-27-may, pero el costo realizado del bug está acotado (~−$12 acumulados en QQQ; +$4.53 ganados en SPY del 11-may). Considerar elevar la guardrail "señal omitida — ya hay posición abierta" a Excepción 1.3 si Roman quiere blindar adicionalmente antes del fix.

**Marca de datos:**
- Trades en QQQ entre 2026-05-15 09:45:14 ET y la hora del cierre manual: contaminados por bug. Excluir del análisis de performance del Sentinel responsable al cierre del 27-may.
- Posición QQQ post-cierre manual: limpia (0 shares).
- **Patrón confirmado, no incidente aislado:** segundo evento del bug #H-5b en 5 días (SPY 11-may + QQQ 15-may). El fix sigue diferido a post-27-may, pero el riesgo residual ya está documentado dos veces — considerar adelantar guardrail read-only (alerta automática cuando aparece "Posiciones fantasma" en log) como Excepción 1.3 si Roman lo autoriza.

**No reinicia contador del período:** corrección de bug, no cambio de hipótesis.

---

### Intervención manual 2026-05-11: cierre de short SPY accidental por bug #H-5b

**Tipo:** corrección de bug (permitida según sección PERMITIDO punto 1 de este documento).
**Ejecutor:** Roman manual vía Alpaca Dashboard.
**Detalle completo:** `backups/2026-05-11/manual_intervention_spy_short_cleanup.md`.

**Resumen:** SPY tenía posición short -4 shares acumulada del 8 al 11 de mayo por bug #H-5b (cache desactualizado en `dispatcher.open_positions` tras SELL). El bot nunca decidió tomar short — fueron SELLs concurrentes sobre posición ya cerrada en Alpaca que el dispatcher dejó pasar contra cache obsoleto. Roman compró 4 shares de SPY a market para netear la posición a 0.

**Fill confirmado (verificado vía Alpaca API 2026-05-12 09:45 ET):**
- Filled at: 2026-05-12 09:31:32 ET (opening cross + ~90s)
- Filled avg price: $736.685 (4 shares)
- Realized P&L: ~+$4.53 (gap-down favoreció el cierre; entry avg $737.818 → exit $736.685)
- Posición SPY post-fill: **0 shares** (`GET /v2/positions/SPY` → 404 "position does not exist") ✅
- Cash post-fill: $98,155.16 | Equity: $100,168.01 | Short market value: $0
- **Estado:** evento **CERRADO** limpiamente.

**Marca de datos:**
- Trades en SPY entre 2026-05-08 y 2026-05-11 22:20 ET: contaminados por bug. Excluir del análisis de performance de Sentinels al cierre del 27-may.
- Posición SPY post-2026-05-12 09:31:32 ET: limpia (0 shares).
- Race condition con el bot el 12-may: **no se materializó** — bot con `parking_brake=True` desde 2026-05-11 22:18, sin emisiones de trade en el opening.
- **Riesgo residual:** si el bug #H-5b se vuelve a manifestar antes del fix post-27-may, repetir intervención y documentar.

**No reinicia contador del período:** corrección de bug, no cambio de hipótesis.

---

### Hallazgo 2026-05-11: el sizing real del Dispatcher NO es Half-Kelly (descubierto post-fix)

**Estado:** documentado, NO se fixea durante observación.

**Observación:** después de aplicar los fixes de Excepción 1.1 (Decimal/float + JOIN scores), el log del 11-may muestra `Capital asignado` operando correctamente — Mantis recibe 23-24%, otro Sentinel (c1968aa2) recibe 25%, los demás caen al piso de 5%. Universe Selector se calmó. **Pero las órdenes siguen saliendo con `qty=1` invariablemente.**

**Causa:** `dispatcher.process_signal` línea 324 hace `qty = min(qty, max_qty)`, y todos los Sentinels (`sentinels/__init__.py`) emiten `qty=1.0` hardcoded en su `analyze()`. Resultado: `min(1, max_qty) = 1` siempre. El allocation se usa como **límite superior**, no como **target**.

**Verificación contra Alpaca (2026-05-11):**
- Equity: $100,161.34
- Position value: $4,907.73
- **Utilización del equity: 4.9%** (vs 58-65% esperado con Half-Kelly real)
- Mantis con NVDA a $218 tiene 1 share. Su allocation de 23% son $23K → 99% sin usar.

**Implicación para el período de observación:**

Los datos del 28-abr al 27-may NO miden "Sharpe-weighted Half-Kelly real". Miden "qty=1 plano con allocation Sharpe-weighted no consumida". Es comportamiento de diseño preexistente, no regresión.

**Marca de datos:** datos de todo el período de observación = "qty=1 fijo, allocation real solo activa post-2026-05-08". Al hacer el balance del 27-may, considerar que las métricas reflejan una **versión sub-óptima** del diseño, no la versión final.

**Fix propuesto para post-27-may (Excepción 1.2 si se quiere fixear antes del balance, o item normal del bloque):**

```python
# dispatcher.py L324 actual:
qty = min(qty, max_qty)

# Cambio mínimo para Half-Kelly real:
qty = max_qty   # usa el allocation completo
```

Variante más completa: si los Sentinels emiten `qty` como "confidence" en lugar de fijo, el sizing sería `qty = max_qty * confidence`. Eso requiere modificar los 9 Sentinels también.

**Conexión con plan post-27-may:** este fix encaja con #GR-2 (position sizing por ATR). El item #GR-2 reemplaza al fix simple de arriba con una versión que ajusta por volatilidad del activo. Aplicar #GR-2 directamente cuando se aborde el sizing, no el fix mínimo de 1 línea.

---

### Excepción 1 ampliada — 2026-05-08: dos bugs heredados de la Excepción 1

**Fecha:** 8 de mayo de 2026 (primer día de mercado post-Excepción 1).

**Situación:** El primer día con los fixes de la Excepción 1 vivos en producción reveló dos bugs que esos fixes destaparon, no introdujeron:

1. **dispatcher.allocate_capital — TypeError float += Decimal.** El nuevo código de agregación per-Sentinel mezcla `weighted_sharpe_sum` (inicializado float `0.0`) con `score["sharpe_ratio"]` (asyncpg devuelve `decimal.Decimal` para columnas NUMERIC). 21 errores `unsupported operand type(s) for +=: 'float' and 'decimal.Decimal'` el 08-may, uno por ciclo. Resultado: `cycle_allocation = {}` siempre, todos los Sentinels caen al fallback `MIN_CAPITAL_PER_SENTINEL = 5%`, no hay distribución Sharpe-weighted Half-Kelly. Esto es el ticket histórico **#H-4** (último 🟠 ALTO pendiente del backlog post-auditoría) que la Excepción 1 expuso al introducir un nuevo punto de mezcla de tipos.

2. **historian.get_sentinel_scores — scores zombies.** Después de una rotación, `evaluate_decay()` deja de actualizar el score del ticker rotado (porque ya no está en `sentinel_tickers.is_active`), pero la fila vieja de `performance_scores` permanece intacta. `get_sentinel_scores()` no hace JOIN con `sentinel_tickers`, así que devuelve scores zombies que el Universe Selector sigue interpretando como "en decay" → dispara nueva rotación → loop. **Mantis (S-2) ejecutó 23 rotaciones en 6 horas el 08-may sobre TSLA y SPY ya rotados**, costo ~$0.65 USD a Claude, acumulando 18 tickers nuevos en su universo (TLT, GLD, USO, IEF, VIXY, XLV, SLV, DBA, XLU, XLE, UUP, UVXY, SQQQ, GDXJ, BITI, TIP, SOXS, XBI).

**Justificación:** Bugs de implementación, no cambios de lógica ni thresholds. Sin estos fixes, la Excepción 1 no logra su objetivo: el Dispatcher seguía sin distribuir capital según Sharpe (fallback plano de 5% en todos), y el Universe Selector entraba en bucle de rotación con costo creciente.

**Cambios realizados:**

- `dispatcher.py` líneas 153-163: conversión explícita `float()` e `int()` al leer scores. Cierra #H-4 en este punto.
- `historian.py` líneas 585-619: `get_sentinel_scores()` agrega `JOIN sentinel_tickers ON ps.sentinel_id = st.sentinel_id AND ps.ticker = st.ticker WHERE st.is_active = TRUE`. Filtra zombies sin destruir datos históricos.
- DB `sentinel_tickers`: limpieza de Mantis post-bucle. Plan: dejar `NVDA` (estrella histórica con Sharpe 39.96), `XLU` (utilities, mean reversion para rsi_short, Ambiente 3 All Weather), `TLT` (bonos largos, Ambiente 4 All Weather) como `is_active = TRUE`. Los 18 nuevos + TSLA + SPY quedan `is_active = FALSE` sin borrar registros (preservamos historial auditable de qué propuso Claude bajo el bug).
- DB `pending_candidates`: discard de cualquier candidato pendiente de Mantis con razón `cleanup_mantis_2026-05-08_post_loop_fix`.

**Marca de datos:** Datos del 08-may pre-cleanup = "pre-excepción-1.1" (Mantis con 18 tickers acumulados, allocation 5% piso plano, Universe Selector en bucle). Datos post-cleanup y reinicio = "post-excepción-1.1".

**Contador del período:** NO se reinicia. Mismo argumento que Excepción 1: arreglos de implementación, no cambios de hipótesis ni thresholds.

**Validación:**

- Simulación ejecutada (`backups/2026-05-08/test_fixes_simulation.py`) reproduce el TypeError exacto de los logs (Escenario A) y demuestra que ambos fixes juntos producen allocation Half-Kelly correcta (Escenario D): Mantis recibe 25% techo, Sharpe agregado limpio (39.96 sin dilución por zombies).
- Proyección: con allocation real al 25% y NVDA ~$120, qty pasa de 1 share por orden (fallback) a ~208 shares (allocation real).
- Lo que NO se cambió: prompts a Claude, thresholds (`WARMUP_TRADES_REQUIRED`, `WARNING_THRESHOLD_*`, `DECAY_THRESHOLD_*`, `KELLY_FRACTION`, `MIN/MAX_CAPITAL_PER_SENTINEL`), lógica de los 9 Sentinels, lógica de The Ear / CorrelationGuard / RegimeClassifier.

**Decisión deferida (post-2026-05-27):** Roman propuso agregar al Universe Selector un trigger nuevo `idle_timeout` para rotar tickers inactivos (sin trades en X días). Cae en la regla "Cambiar lógica de cualquier agente" del NO PERMITIDO — se documenta en `NEXT_ITERATION.md` para diseño cuidadoso después del cierre del período de observación.

---

## Migración a Mini PC

La migración de hardware (de ROG Ally X a Mini PC dedicado) está **permitida** durante el período de observación porque NO cambia lógica ni comportamiento del sistema, solo el lugar donde se ejecuta.

Proceso detallado en `MIGRATION_PLAN_MINIPC.md`. Resumen:
- Hacer en fin de semana (mercado cerrado)
- Snapshot completo de DB antes de migrar
- Bot apagado en ROG ANTES de arrancar en Mini PC (nunca ambos a la vez)
- Mismo Python, mismas dependencias, mismo .env
- Documentar como evento en MIGRATION_LOG.md
- Marcar datos del paper trading "antes" vs "después" para análisis si hace falta

---

## Plan de revisión al cierre del período

**Fecha:** 27 de mayo de 2026

**Métricas a evaluar:**

1. **Trades totales:** ¿cuántos trades FILLED se ejecutaron? Mínimo deseable: 50+ por Sentinel (450+ totales) para análisis estadístico significativo.

2. **Performance agregada:** equity curve del portfolio paper. ¿Creció? ¿Decreció? ¿Volatilidad?

3. **Performance por Sentinel:** win_rate, sharpe, profit_factor (si se agrega), drawdown máximo, slippage promedio.

4. **Universe Selector:** ¿cuántas rotaciones se ejecutaron? ¿Cuáles fueron las recomendaciones de Claude? ¿Acertó? Costo total acumulado.

5. **The Ear:** ¿cuántas veces vetó trading (risk > 0.7)? ¿Esos vetos coincidieron con días malos del mercado? Calibración del threshold.

6. **CorrelationGuard:** ¿cuántas señales redujo? ¿cuántas descartó? ¿La concentración real del portfolio fue gestionada?

7. **Sistema:** ¿hubo crashes? ¿downtime? ¿bugs detectados? ¿alertas a tiempo?

**Decisión al cierre:**

A. **Si el sistema mostró comportamiento positivo:** extender período otros 30 días para validar consistencia, luego considerar transición a v0.7 (paper trading validado) y posteriormente a v1.0 (live trading).

B. **Si el sistema mostró comportamiento mixto:** identificar componentes que funcionaron vs no funcionaron, ajustar específicamente los problemáticos en una sesión de cambios documentados, reiniciar período de observación.

C. **Si el sistema falló estructuralmente:** evaluar si el problema es de implementación (fixable) o de hipótesis (las 9 estrategias clásicas no producen alpha en ensemble sobre equity USA). En caso B, considerar pivote significativo.

---

## Disciplina psicológica

Esta sección está dirigida específicamente a Roman.

Durante los próximos 30 días vas a sentir presión para:

**Tocar el sistema cuando muestre números mediocres.** "Si solo ajusto este threshold, capaz funcione mejor". Esa es exactamente la trampa que la investigación describe. Los números mediocres son INFORMACIÓN, no problema. Sirven para evaluar al final.

**Acelerar a live trading si los números son buenos.** Si en día 15 el equity curve va arriba 5%, va a aparecer la voz interna que dice "ya está, vamos a real". 30 días es el mínimo, no el target. Disciplina sostenida > entusiasmo prematuro.

**Construir features nuevos "que se me ocurrió".** Cualquier idea que aparezca durante el período se anota en NEXT_ITERATION.md y se implementa DESPUÉS del 27 de mayo. No se toca el sistema en operación.

**Abandonar si los números son malos.** Un drawdown del 5-10% en paper trading es esperado y no es señal de fallo del sistema. Es información sobre régimen. Solo si hay falla estructural verificable se actúa.

> "Pain + Reflection = Progress." — Ray Dalio, después de quebrar Bridgewater en 1982.

---

## Contacto y soporte durante el período

Si algo crítico requiere acción inmediata:
- Claude (Roma) está disponible para diagnosticar y armar prompts para Code
- Code ejecuta los cambios técnicos
- Decisión final: Roman

Para todo lo no crítico: anotar y dejar para sesión de cierre del período.

---

*Documento creado el 27 de abril de 2026.*
*Vigente hasta el 27 de mayo de 2026 o hasta primera excepción documentada (la que ocurra primero).*
*Cerrado anticipadamente el 23 de mayo de 2026 — ver sección "Cierre del período" más abajo.*

---

## Cierre del período — 2026 de mayo de 2026

**Fecha de cierre formal:** 23 de mayo de 2026 (sábado).
**Fecha originalmente prevista:** 27 de mayo de 2026.
**Período efectivamente cubierto:** 28-abril → 23-mayo = **26 días** (en lugar de los 30 planeados).
**Decidido por:** Roman.

### Motivo del cierre anticipado

Decisión de Roman, documentada textualmente:

> *"La plataforma nunca funcionó como se tenía planeado, no todas las estrategias funcionaron, no se invirtió todo el capital que se disponía para eso, hubo errores que no se tuvieron presentes. Para evitar seguir acumulando datos incompletos, pero igual valiosos, y para aprovechar mi fin de semana largo, decidí mejor terminar acá y no esperar los 4 días que faltan."*

Esta es la **conclusión inversa** de la trampa psicológica que la sección "Disciplina psicológica" de este mismo documento advierte. No es "los números son aburridos, quiero tocar el sistema" — es "el sistema no operó en su forma de diseño durante el período, acumular más días sub-óptimos no aporta señal adicional; mejor cortar, hacer el balance honesto, arreglar lo identificado, y correr un segundo período limpio". Eso es exactamente "evaluar al final del período" según el espíritu del documento.

### Caveats acumulados (críticos para el análisis del balance)

Los datos del período NO miden la versión final del diseño. Tres sub-períodos distintos:

1. **28-abril → 07-mayo (10 días):** Dispatcher con `allocate_capital()` roto. Todos los Sentinels al fallback `MIN_CAPITAL_PER_SENTINEL = 5%` plano. Sharpe-weighted Half-Kelly NO operando como diseño. Excepción 1 documentada al final de este sub-período (07-may).
2. **08-mayo → 11-mayo (4 días):** Período de bugs descubiertos por Excepción 1: TypeError `float += Decimal` en dispatcher + bucle zombie de Universe Selector con Mantis (23 rotaciones en 6h, costo ~$0.65). Excepción 1.1 cierra estos bugs el 08-may.
3. **12-mayo → 23-mayo (12 días):** Dispatcher operando Sharpe-weighted allocation correctamente, PERO sizing trivial (qty=1 hardcoded en los Sentinels). Utilización del equity: ~3-5% en vez del 58-65% esperado con Half-Kelly real. Bug #H-5b reapareció dos veces (SPY 11-may, QQQ 15-may) generando shorts accidentales con intervención manual.

**Conclusión técnica:** ningún sub-período mide "Sharpe-weighted Half-Kelly real con SL/TP y sizing por ATR". El balance del 27-may → 23-may debe interpretarse como **versión sub-óptima del diseño**, no como evaluación del diseño final.

### Eventos documentados durante el período

- **Excepción 1** (07-may): scores parciales + agregación de Dispatcher.
- **Excepción 1.1** (08-may): Decimal/float + JOIN scores zombies + cleanup Mantis.
- **Excepción 1.2** (13-may): Capital card en el dashboard (endpoint `/api/account/capital` read-only + cosmética).
- **Intervención manual 11-may** (SPY): cierre de short -4 sh accidental por bug #H-5b. Fill 12-may 09:31:32 ET. P&L: +$4.53.
- **Hallazgo 11-may:** sizing trivial documentado. Diferido a #GR-2 post-cierre.
- **Intervención manual 16-may** (QQQ): cierre de short -2 sh accidental por bug #H-5b (segunda reaparición). Fill 18-may 09:30:41 ET. P&L: −$5.66. Costo total #H-5b en QQQ: −$12.02.

Contador del período NO fue reiniciado por ninguna excepción (todos fueron bug fixes que permitían medir la hipótesis original, no cambios de hipótesis).

### Estado del sistema al cierre (23-may, mercado cerrado fin de semana)

Pendiente de verificación al inicio de Fase 1 (los últimos datos formales son del 18-may post-fill QQQ). Snapshot necesario:
- Equity, cash, long/short MV actuales.
- Posiciones abiertas.
- ¿Hubo tercera reaparición de #H-5b entre el 18-may y el 23-may?
- Trades de la semana 19-22 mayo.
- P&L semanal y acumulado del período.

### Restricciones — LEVANTADAS a partir del 23-may

A partir de esta fecha, todas las reglas de la sección "❌ NO PERMITIDO" de este documento **dejan de aplicar**. Específicamente, ahora SÍ está permitido:

- Modificar el `SYSTEM_PROMPT` del Universe Selector.
- Cambiar thresholds, prompts, parámetros de estrategias técnicas.
- Agregar o remover Sentinels.
- Cambiar lógica de cualquier agente.
- Modificar prompts a Claude.
- Cambiar timeouts (incluso no bloqueantes).
- Reactivar el Regime Classifier (S-10) si hay 50-100 trades.
- Implementar features pendientes (fractional, leverage, gestión de riesgo, etc.).

**Pero no de forma indiscriminada:** los cambios siguen el plan estructurado de 6 fases documentado en la memoria `project_sentinel_post_observation_plan.md` y reflejado en `NEXT_ITERATION.md`. La Fase 1 (análisis del período) debe completarse antes de avanzar a Fases 2-3 (auditoría código, features).

### Transición a paper trading sigue activa

El cierre del período de observación NO implica transición a live trading. El bot sigue operando en paper Alpaca durante:

- Fase 1: análisis (1-3 días).
- Fase 2: auditoría código + bugs (4-7 días).
- Fase 3: features bloqueadas (8-14 días).
- Fase 4: **segundo período de observación de 30 días** sobre el código limpio (junio).

Recién después de Fase 4 exitosa se evalúa transición a v1.0 (live conservador con capital pequeño + fractional + sin leverage), prevista para julio 2026.

### Próximos pasos inmediatos

1. **HANDOFF #2** = pendiente de decisión de Roman tras este cierre.
2. **Snapshot del estado del bot al 23-may** vía Alpaca API + Read del log.
3. **Notificar a Code** que actualice `sentinel-v0.5/CLAUDE.md` reflejando el cierre del período (vía HANDOFF).
4. **Generar balance del período** con QuantStats + métricas por Sentinel (Fase 1).

---

*Cierre formal documentado el 23 de mayo de 2026.*
