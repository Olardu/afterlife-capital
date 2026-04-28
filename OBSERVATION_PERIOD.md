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

(Vacío al inicio del período. Se completa si surge alguna.)

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
