# ENDPOINTS_BACKLOG.md — Plan de Expansión de la API

**Creado:** 4 de mayo de 2026
**Implementar después de:** 27 de mayo de 2026 (cierre del período de observación)
**Prioridad:** Todos los endpoints son read-only — ninguno modifica lógica del bot

> **Regla #0:** Antes de implementar cualquier endpoint nuevo, se debe crear y mantener
> una documentación completa de TODA la API (existente + nueva) en un archivo
> `API_REFERENCE.md`. Esto evita consultas a ciegas, duplicación de funcionalidad,
> y asegura que cualquier agente (Claude, Code, o humano) sepa exactamente qué
> endpoints existen, qué parámetros aceptan, y qué devuelven.

---

## Parte 1 — Endpoints existentes (inventario actual)

Estos endpoints ya están operativos en `api.py` al 4 de mayo de 2026:

### Autenticación
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/auth/login` | Inicia flujo OAuth con Google |
| GET | `/auth/callback` | Callback de Google OAuth |
| GET | `/auth/logout` | Cierra sesión |
| GET | `/auth/me` | Usuario autenticado actual |

### Core del sistema
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/status` | Estado general del sistema (online/offline, sentinels count, régimen, risk) |
| GET | `/api/sentinels` | Los 9 Sentinels con tickers, señales, PnL, win rate, Sharpe |
| GET | `/api/trades` | Todos los trades (FILLED, CANCELLED, PENDING_NEW) |
| GET | `/api/macro` | Datos macro de The Ear (risk score, VIX, SPY delta) |
| GET | `/api/market-status` | Estado del mercado (abierto/cerrado, próxima apertura) |
| GET | `/api/macro_events` | Eventos macro recientes que movieron decisiones |
| GET | `/api/performance` | Historian: performance scores, decay status |

### Cuenta Alpaca
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/account/equity` | Equity, cash, buying power, posiciones abiertas con unrealized P&L |
| GET | `/api/account/portfolio-history` | Curva de equity histórica (períodos: 4H, 8H, 1D, 1W, 1M, 1A) |

### Reporting
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/report` | Descarga reporte del sistema |

### Control operativo
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/system/state` | Estado del bot (running/halted) |
| POST | `/api/system/halt` | Detener el bot |
| POST | `/api/system/resume` | Reanudar el bot |

### Administración
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/users` | Lista usuarios registrados |
| POST | `/api/admin/users` | Crear usuario (email + role) |
| DELETE | `/api/admin/users/{user_id}` | Eliminar usuario |
| GET | `/api/admin/api-keys` | Lista API keys |
| POST | `/api/admin/api-keys` | Crear API key |
| POST | `/api/admin/api-keys/{key_id}/reveal` | Revelar API key |
| DELETE | `/api/admin/api-keys/{key_id}` | Eliminar API key |

### Universe Selector
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/rotations` | Historial de decisiones de rotación |
| GET | `/api/admin/rotations/{decision_id}` | Detalle de una rotación |
| POST | `/api/admin/rotations/{decision_id}/rollback` | Revertir una rotación |
| GET | `/api/admin/candidates` | Candidatos pendientes de rotación |
| GET | `/api/rotations/recent` | Rotaciones recientes (para dashboard) |

### Streaming
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/sse` | Server-Sent Events para actualizaciones en tiempo real |

### Frontend
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard SPA principal |
| GET | `/admin` | Panel de administración |

---

## Parte 2 — Endpoints pendientes del Frente B (dashboard)

Estos endpoints son necesarios para eliminar los "—" que quedan en el dashboard.

### 2.1 Señales procesadas
```
GET /api/signals/summary
```
**Muestra:** Total de señales generadas, aprobadas, rechazadas por The Ear, reducidas por CorrelationGuard.
**Requiere:** Agregar columnas a tabla `signals`: `approved` (bool), `correlation_action` (enum: none/reduced/discarded), `rejection_reason` (text).
**KPIs que alimenta:** "Señales procesadas: aprobadas X / rechazadas Y" en el dashboard.

### 2.2 Max Drawdown
```
GET /api/metrics/drawdown?period=1W|1M|1A
```
**Muestra:** Max drawdown del portfolio en el período seleccionado. Se calcula desde el array de equity que ya devuelve `/api/account/portfolio-history`.
**Requiere:** Solo lógica de cálculo, sin cambios de schema.
**KPI que alimenta:** "Max DD" debajo de la curva de equity.

### 2.3 Correlación
```
GET /api/correlation/status
```
**Muestra:** Correlación promedio actual entre Sentinels, pares más correlacionados, señales reducidas/descartadas.
**Requiere:** Columnas en `signals` (ver 2.1) + lectura del CorrelationGuard state.
**KPIs que alimenta:** Correlation avg, señales reducidas, señales descartadas.

### 2.4 Sistema / versión
```
GET /api/system/version
```
**Muestra:** Versión del build, uptime desde último reinicio, timestamp de arranque.
**Requiere:** Variable de entorno o constante en código.
**KPIs que alimenta:** Uptime y Build version en el dashboard.

---

## Parte 3 — Endpoints nuevos de observabilidad avanzada

### Categoría: Análisis de ejecución

#### 3.1 Calidad de ejecución
```
GET /api/execution/quality?sentinel_id=X&ticker=Y&period=1W|1M
```
**Muestra:** Slippage promedio, mediano, máximo por Sentinel y/o ticker. Desglose por hora del día para identificar patrones (ej: peor slippage en los primeros 15 min de apertura).
**Datos fuente:** Tabla `trades` (slippage ya se guarda).
**Valor:** Identifica si ciertas estrategias o tickers tienen costos ocultos de ejecución.

#### 3.2 Fill rate
```
GET /api/execution/fill-rate?sentinel_id=X&period=1W|1M
```
**Muestra:** Ratio FILLED / total de órdenes por Sentinel y ticker. Ranking de quién cancela más.
**Datos fuente:** Tabla `trades` (status ya se guarda).
**Valor:** Si un Sentinel cancela 50% de sus órdenes, su estrategia podría estar generando señales a precios inalcanzables.

### Categoría: Contexto de mercado

#### 3.3 Historial de régimen
```
GET /api/market/regime-history?days=30
```
**Muestra:** Régimen implícito de cada sesión (basado en VIX, rango de SPY, volumen). Aunque S-10 está desactivado, guardar esta data permite correlacionar resultados con condiciones de mercado cuando se active.
**Requiere:** Tabla nueva `market_sessions` o cálculo desde datos de Alpaca.
**Valor:** "¿El sistema pierde más en mercado lateral o en tendencia?" — pregunta clave para calibrar S-10.

#### 3.4 Estadísticas de sesión
```
GET /api/market/session-stats?date=2026-05-04
```
**Muestra:** Volumen del mercado, rango intraday de SPY/QQQ, volatilidad (ATR), si hubo eventos macro relevantes.
**Valor:** Contextualiza los resultados: perder $15 en un día muerto vs perder $15 cuando SPY subió 2% son cosas muy diferentes.

### Categoría: Capital y riesgo

#### 3.5 Historial de asignación de capital
```
GET /api/capital/allocation-history?days=7
```
**Muestra:** Cómo el Dispatcher distribuyó capital en cada ciclo. Porcentaje asignado a cada Sentinel en el tiempo.
**Requiere:** Logging de decisiones del Dispatcher (tabla nueva `allocation_log`).
**Valor:** Valida que el Sharpe-weighted Half-Kelly realmente está diferenciando entre Sentinels. Si siempre da 5% a todos, no está funcionando.

#### 3.6 Exposición actual
```
GET /api/capital/exposure
```
**Muestra:** Exposición neta (long - short), bruta (long + short), porcentaje de cash, exposición por sector/asset class.
**Datos fuente:** Posiciones actuales de Alpaca + clasificación de tickers.
**Valor:** Foto agregada del riesgo. Ahora solo ves posiciones individuales pero no el panorama completo.

#### 3.7 Concentración de riesgo
```
GET /api/risk/concentration
```
**Muestra:** Cuántos Sentinels tienen el mismo ticker, exposición por sector, si CorrelationGuard está reduciendo efectivamente.
**Datos fuente:** Estado actual de Sentinels + posiciones.
**Valor:** Si 3 Sentinels operan NVDA simultáneamente, hay riesgo de concentración que debería estar gestionado.

### Categoría: Auditoría y trazabilidad

#### 3.8 Cadena de decisión
```
GET /api/audit/decision-chain/{trade_id}
```
**Muestra:** Para un trade específico, toda la cadena: señal del Sentinel → evaluación del Dispatcher → verificación de The Ear → check de correlación → orden enviada a Alpaca → resultado final.
**Requiere:** Logging en cada etapa de la pipeline (tabla `decision_log` o columnas adicionales en `signals`/`trades`).
**Valor:** Post-mortem de cualquier trade. "¿Por qué se compró TSLA a las 13:30?" — la respuesta completa de punta a punta.

#### 3.9 Oportunidades perdidas
```
GET /api/audit/missed-opportunities?period=1W
```
**Muestra:** Señales generadas que NO se ejecutaron: vetadas por The Ear, reducidas por CorrelationGuard, rechazadas por capital insuficiente, bloqueadas por parking brake. Para cada una, si hubiera sido ganadora o perdedora (calculado retroactivamente con precio de mercado al cierre).
**Requiere:** Logging de rechazos (columnas en `signals`) + cálculo retroactivo.
**Valor:** ¿Los filtros están protegiendo o frenando? Si el 70% de las señales rechazadas habrían sido ganadoras, los filtros están demasiado agresivos.

### Categoría: Reporting y benchmarking

#### 3.10 Reporte diario ✅ IMPLEMENTADO (2026-05-04)
```
GET /api/report/daily?dt=2026-05-04
```
**Muestra:** Resumen completo del día: trades ejecutados/cancelados, P&L realizado/no realizado, señales generadas, rotaciones del Universe Selector, eventos de The Ear, posiciones abiertas al cierre.
**Valor:** Base para el email diario al cierre del mercado. Un solo endpoint que consolida todo.
**Estado:** Implementado en api.py + email_service.py. Scheduler automático 16:30 ET L-V.

#### 3.11 Atribución de P&L
```
GET /api/report/attribution?period=1D|1W|1M
```
**Muestra:** Desglose del P&L por Sentinel, por estrategia, por ticker. "Hoy ganamos $27: $40 de S-2 en SPY, -$12 de S-7 en GLD, -$1 de posiciones abiertas."
**Datos fuente:** Tabla `trades` con joins a `sentinels`.
**Valor:** Saber de dónde viene el dinero y a dónde se va. Fundamental para decidir qué Sentinels escalar y cuáles reevaluar.

#### 3.12 Benchmark vs mercado
```
GET /api/report/benchmark?period=1W|1M|1A
```
**Muestra:** Rendimiento del sistema vs SPY buy-and-hold en el mismo período. Alpha, beta, tracking error.
**Datos fuente:** Portfolio history (ya existe) + precios históricos de SPY (Alpaca bars API).
**Valor:** La pregunta fundamental: ¿estamos generando alpha o simplemente siguiendo el mercado con más volatilidad?

### Categoría: Universe Selector

#### 3.13 Costo acumulado del Universe Selector
```
GET /api/universe/cost?period=1W|1M
```
**Muestra:** Costo total de llamadas a Claude API, número de llamadas, costo promedio por ciclo, tendencia.
**Datos fuente:** Tabla `rotation_decisions` (cost ya se guarda).
**Valor:** Control de gastos operativos. Si el Universe Selector cuesta $50/mes y genera $30 de alpha, no es viable.

#### 3.14 Efectividad de rotaciones
```
GET /api/universe/effectiveness
```
**Muestra:** Para cada rotación ejecutada: performance del ticker antes de ser removido vs performance del ticker que lo reemplazó. ¿Claude acertó?
**Requiere:** Cálculo retroactivo comparando performance pre/post rotación.
**Valor:** Valida si el Universe Selector agrega valor o es ruido costoso.

### Categoría: The Ear

#### 3.15 Historial de vetos
```
GET /api/ear/history?days=30
```
**Muestra:** Cada vez que risk > 0.7, qué titulares lo dispararon, duración del veto, y qué pasó con el mercado durante ese período.
**Datos fuente:** Tabla `macro_events` + cálculo retroactivo.
**Valor:** Calibración del threshold. Si los vetos coinciden con días malos → bien calibrado. Si no → ajustar post-observación.

---

## Parte 4 — Documentación obligatoria

### API_REFERENCE.md

**ANTES de implementar cualquier endpoint nuevo**, crear `API_REFERENCE.md` con:

1. **Inventario completo** de todos los endpoints existentes (Parte 1 de este documento es el punto de partida)
2. **Para cada endpoint:**
   - Método y ruta
   - Parámetros (query, path, body) con tipos y valores por defecto
   - Response schema (JSON de ejemplo)
   - Códigos de error posibles
   - Autenticación requerida (público, usuario, admin)
3. **Mantener actualizado** cada vez que se agregue o modifique un endpoint
4. **Incluir sección de "Endpoints deprecados"** si se reemplazan o eliminan

**Por qué:** Sin documentación centralizada, cada sesión de Claude (Roma, Code, o Design) tiene que adivinar qué endpoints existen, probar a ciegas, o buscar en el código fuente. Esto desperdicia tiempo, genera errores, y puede causar que se dupliquen funcionalidades.

---

## Orden de implementación sugerido

### Fase 1 — Quick wins (sin cambios de schema)
1. `/api/metrics/drawdown` — cálculo puro desde datos existentes
2. `/api/system/version` — trivial
3. `/api/execution/quality` — query sobre tabla trades
4. `/api/execution/fill-rate` — query sobre tabla trades
5. `/api/universe/cost` — query sobre rotation_decisions
6. `/api/capital/exposure` — datos de Alpaca positions
7. `/api/report/daily` — ✅ IMPLEMENTADO 2026-05-04
8. `/api/report/attribution` — query con joins

### Fase 2 — Requieren schema additions (columnas nuevas)
9. `/api/signals/summary` — columnas en signals
10. `/api/correlation/status` — columnas en signals
11. `/api/audit/decision-chain` — tabla decision_log
12. `/api/audit/missed-opportunities` — logging de rechazos
13. `/api/capital/allocation-history` — tabla allocation_log

### Fase 3 — Requieren datos externos o cálculos complejos
14. `/api/report/benchmark` — datos de SPY histórico
15. `/api/market/regime-history` — tabla nueva o cálculo
16. `/api/market/session-stats` — datos de mercado
17. `/api/universe/effectiveness` — cálculo retroactivo
18. `/api/ear/history` — cálculo retroactivo
19. `/api/risk/concentration` — clasificación de tickers por sector

---

*Documento creado el 4 de mayo de 2026.*
*Implementación programada para después del 27 de mayo de 2026.*
