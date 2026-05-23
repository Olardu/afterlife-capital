# API_REFERENCE.md — Sentinel v0.5 API

**Última actualización:** 4 de mayo de 2026
**Base URL (tunnel):** `https://sentinel.afterlifecapital.co`
**Base URL (local):** `http://localhost:8080`
**Framework:** FastAPI + Uvicorn
**Puerto local:** 8080 (`uvicorn api:app host=0.0.0.0 port=8080`)
**Autenticación:** Google OAuth 2.0 con sesión firmada (cookie)

---

## Índice

1. [Autenticación y sesiones](#1-autenticación-y-sesiones)
2. [Estado del sistema](#2-estado-del-sistema)
3. [Sentinels](#3-sentinels)
4. [Trades](#4-trades)
5. [Macro / The Ear](#5-macro--the-ear)
6. [Mercado](#6-mercado)
7. [Performance](#7-performance)
8. [Cuenta Alpaca](#8-cuenta-alpaca)
9. [Reporte](#9-reporte)
10. [Control operativo (Kill Switch)](#10-control-operativo-kill-switch)
11. [Administración de usuarios](#11-administración-de-usuarios)
12. [Administración de API keys](#12-administración-de-api-keys)
13. [Universe Selector (rotaciones)](#13-universe-selector-rotaciones)
14. [Server-Sent Events (SSE)](#14-server-sent-events-sse)
15. [Frontend estático](#15-frontend-estático)
16. [Códigos de error comunes](#16-códigos-de-error-comunes)
17. [Notas sobre autenticación y roles](#17-notas-sobre-autenticación-y-roles)

---

## 1. Autenticación y sesiones

Todas las rutas `/api/*` requieren sesión válida (excepto `/api/market-status` que es pública).
La sesión se establece vía Google OAuth y se persiste en cookie firmada.

### `GET /auth/login`

Inicia el flujo OAuth con Google. Redirige al usuario a la pantalla de consentimiento de Google.

**Auth:** Pública
**Response:** 302 Redirect a Google OAuth

---

### `GET /auth/callback`

Callback de Google OAuth. Intercambia el código por token, verifica que el email esté registrado en la tabla `users`, y crea la sesión.

**Auth:** Pública
**Response éxito:** 302 Redirect a `/` (dashboard)
**Response error:**
- Email no verificado → 403 HTML "Acceso denegado"
- Email no registrado en `users` → 403 HTML "Acceso denegado"
- Error de OAuth → 302 Redirect a `/auth/login`

---

### `GET /auth/logout`

Limpia la sesión y redirige al login.

**Auth:** Pública
**Response:** 302 Redirect a `/auth/login`

---

### `GET /auth/me`

Devuelve el usuario autenticado actual.

**Auth:** Sesión requerida
**Response 200:**
```json
{
  "email": "***REMOVED-EMAIL***",
  "role": "ADMIN",
  "user_id": "uuid-string"
}
```
**Response 401:**
```json
{"detail": "unauthorized"}
```

---

## 2. Estado del sistema

### `GET /api/status`

Estado general del sistema: sentinels activos, régimen, riesgo, parking brake.

**Auth:** Sesión requerida
**Parámetros:** Ninguno
**Response 200:**
```json
{
  "system": "ONLINE",
  "sentinels_active": 9,
  "sentinels_total": 9,
  "regime": "NEUTRAL",
  "tickers_total": 27,
  "refresh_interval": "15MIN",
  "risk_score": 0.0,
  "circuit_breaker": false,
  "parking_brake": true
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| system | string | Siempre "ONLINE" si la API responde |
| sentinels_active | int | Sentinels con `is_active = TRUE` |
| sentinels_total | int | Total de sentinels del owner |
| regime | string | Siempre "NEUTRAL" (S-10 desactivado) |
| tickers_total | int | Total de tickers activos en todos los sentinels |
| refresh_interval | string | Intervalo de actualización del dashboard |
| risk_score | float | Último risk score de The Ear (0.0 a 1.0) |
| circuit_breaker | bool | Si el circuit breaker está activado |
| parking_brake | bool | Si la hora actual ET >= 15:45 (PARKING_BRAKE_TIME) |

---

## 3. Sentinels

### `GET /api/sentinels`

Los 9 Sentinels con sus tickers asignados, última señal, y métricas de performance.

**Auth:** Sesión requerida
**Parámetros:** Ninguno
**Response 200:**
```json
[
  {
    "sentinel_id": "d78bd2dd-10fc-4df5-b592-e37b4fc09342",
    "name": "S-1 SMA Crossover",
    "strategy_type": "sma_crossover",
    "allocation_pct": 5.0,
    "decay_status": false,
    "total_trades": 0,
    "tickers": [
      {
        "ticker": "IWM",
        "last_signal": "SELL",
        "last_signal_at": "2026-05-04T12:45:18.386796",
        "pnl": 0.0,
        "win_rate": 0.0,
        "sharpe_ratio": 0.0
      }
    ]
  }
]
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| sentinel_id | UUID string | Identificador único del sentinel |
| name | string | Nombre display (ej: "S-2 RSI Short") |
| strategy_type | string | Tipo de estrategia (ej: "rsi_short") |
| allocation_pct | float | Porcentaje de capital asignado por el Dispatcher |
| decay_status | bool | True si algún ticker tiene performance_decay activado |
| total_trades | int | Suma de total_trades de performance_scores (0 si no hay scores) |
| tickers[].pnl | float | Siempre 0.0 (TODO: calcular FIFO cuando haya trades reales) |
| tickers[].win_rate | float | Win rate del performance_score (0.0 si no hay datos) |
| tickers[].sharpe_ratio | float | Sharpe ratio del performance_score (0.0 si no hay datos) |

**Nota:** `pnl` es placeholder. El PnL real por ticker requiere cálculo FIFO BUY/SELL que aún no está implementado.

---

## 4. Trades

### `GET /api/trades`

Historial de trades filtrado por período de observación (>= 28 abril 2026).

**Auth:** Sesión requerida
**Parámetros query:**

| Parámetro | Tipo | Default | Rango | Descripción |
|-----------|------|---------|-------|-------------|
| limit | int | 50 | 1-500 | Máximo de trades a devolver |
| sentinel | UUID string | null | — | Filtrar por sentinel_id |
| ticker | string | null | — | Filtrar por ticker (se convierte a mayúsculas) |

**Response 200:**
```json
[
  {
    "trade_id": "375ccc0a-1f9b-4475-9039-b7d7fa058d67",
    "sentinel_name": "S-2 RSI Short",
    "ticker": "TSLA",
    "side": "SELL",
    "qty": 1.0,
    "filled_price": null,
    "slippage": null,
    "status": "CANCELLED",
    "created_at": "2026-05-04T15:15:17.401588"
  },
  {
    "trade_id": "061944f6-1804-49d5-a4ad-61425f13afad",
    "sentinel_name": "S-2 RSI Short",
    "ticker": "SPY",
    "side": "SELL",
    "qty": 1.0,
    "filled_price": 718.05,
    "slippage": 0.0,
    "status": "FILLED",
    "created_at": "2026-05-04T15:15:12.611314"
  }
]
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| trade_id | UUID string | Identificador único del trade |
| sentinel_name | string | Nombre del sentinel que generó el trade |
| ticker | string | Símbolo del instrumento |
| side | string | "BUY" o "SELL" |
| qty | float | Cantidad de shares |
| filled_price | float o null | Precio de ejecución (null si no se llenó) |
| slippage | float o null | Diferencia entre precio esperado y ejecutado (null si no se llenó) |
| status | string | "FILLED", "CANCELLED", "PENDING_NEW", "PARTIALLY_FILLED", "EXPIRED", "REJECTED", "NEW", "ACCEPTED", "SUSPENDED" |
| created_at | ISO 8601 | Timestamp de creación de la orden |

**Errores:**
- 400: `"sentinel debe ser UUID válido"` si se pasa un sentinel_id inválido

**Nota:** Solo devuelve trades con `created_at >= 2026-04-28` (inicio del período de observación). Trades anteriores se consideran contaminación.

---

## 5. Macro / The Ear

### `GET /api/macro`

Datos macro actuales y recientes de The Ear.

**Auth:** Sesión requerida
**Parámetros:** Ninguno
**Response 200:**
```json
{
  "current_risk_score": 0.0,
  "circuit_breaker": false,
  "parking_brake": true,
  "recent_events": [
    {
      "risk_score": 0.0,
      "vix_level": 0.0,
      "spy_change_15min": 0.0,
      "circuit_breaker_triggered": false,
      "created_at": "2026-05-04T19:54:00.123456"
    }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| current_risk_score | float | Risk score más reciente (0.0 a 1.0). > 0.7 activa veto |
| circuit_breaker | bool | Si el circuit breaker está activo |
| parking_brake | bool | Si hora ET >= 15:45 |
| recent_events | array | Últimos 20 eventos macro ordenados por created_at DESC |

---

### `GET /api/macro_events`

Eventos macro con titulares de noticias que movieron decisiones.

**Auth:** Sesión requerida (VIEWER + ADMIN)
**Parámetros query:**

| Parámetro | Tipo | Default | Rango | Descripción |
|-----------|------|---------|-------|-------------|
| limit | int | 10 | 1-100 | Número de eventos a devolver |

**Response 200:**
```json
[
  {
    "event_id": "uuid-string",
    "created_at": "2026-05-04T19:54:00.123456",
    "risk_score": 0.0,
    "vix_change": 0.0,
    "spy_change": 0.0,
    "regime": "NEUTRAL",
    "circuit_breaker": false,
    "parking_brake": true,
    "news_titles": []
  }
]
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| event_id | UUID string o null | ID del evento |
| vix_change | float o null | Nivel de VIX en el momento del evento |
| spy_change | float o null | Cambio de SPY en 15 minutos |
| regime | string | Siempre "NEUTRAL" (S-10 desactivado) |
| news_titles | array | Lista de titulares que matchearon keywords de The Ear |

---

## 6. Mercado

### `GET /api/market-status`

Estado del mercado NYSE con tiempos hasta próximo cambio.

**Auth:** Pública (no requiere sesión)
**Parámetros:** Ninguno
**Response 200:**
```json
{
  "is_open": false,
  "status": "CLOSED",
  "next_open": "2026-05-05T09:30:00-04:00",
  "next_close": null,
  "current_time_et": "2026-05-04T20:13:36.622545-04:00"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| is_open | bool | True solo si status == "OPEN" |
| status | string | "OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS" |
| next_open | ISO 8601 o null | Próxima apertura regular (null si ya está abierto) |
| next_close | ISO 8601 o null | Próximo cierre (null si está cerrado) |
| current_time_et | ISO 8601 | Hora actual en Eastern Time |

---

## 7. Performance

### `GET /api/performance`

Performance scores de Historian: win rate, Sharpe, decay por sentinel/ticker.

**Auth:** Sesión requerida
**Parámetros:** Ninguno
**Response 200:**
```json
[
  {
    "sentinel_name": "S-2 RSI Short",
    "ticker": "SPY",
    "win_rate": 0.55,
    "sharpe_ratio": 1.2,
    "total_trades": 15,
    "performance_decay": false,
    "calculated_at": "2026-05-04T18:00:00.000000"
  }
]
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| sentinel_name | string | Nombre del sentinel |
| ticker | string | Símbolo del instrumento |
| win_rate | float o null | Porcentaje de trades ganadores (0.0-1.0) |
| sharpe_ratio | float o null | Sharpe ratio calculado |
| total_trades | int o null | Total de trades evaluados |
| performance_decay | bool o null | True si Historian detectó decay |
| calculated_at | ISO 8601 o null | Última vez que se calculó |

**Nota:** Ordenado por `sharpe_ratio DESC NULLS LAST`. Puede devolver array vacío si no hay performance scores calculados.

---

## 8. Cuenta Alpaca

### `GET /api/account/equity`

Balance, equity, posiciones abiertas y P&L no realizado. Consulta directa a la API de Alpaca.

**Auth:** Sesión requerida
**Parámetros:** Ninguno
**Response 200:**
```json
{
  "equity": 100029.0,
  "cash": 98725.74,
  "portfolio_value": 100029.0,
  "buying_power": 395141.97,
  "positions_count": 4,
  "unrealized_pl": -15.2,
  "positions": [
    {
      "ticker": "GLD",
      "qty": 1.0,
      "market_value": 415.0,
      "unrealized_pl": -2.73,
      "avg_entry": 417.73,
      "current_price": 415.0
    }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| equity | float | Equity total de la cuenta (cash + posiciones) |
| cash | float | Cash disponible |
| portfolio_value | float | Valor del portfolio (= equity si no hay margin) |
| buying_power | float | Poder de compra (incluye margin si aplica) |
| positions_count | int | Número de posiciones abiertas |
| unrealized_pl | float | P&L no realizado sumado de todas las posiciones |
| positions[] | array | Detalle de cada posición abierta |

**Nota:** Este endpoint hace llamadas en tiempo real a Alpaca — no cachea datos. Si Alpaca está caído, devuelve 500.

---

### `GET /api/account/portfolio-history`

Curva de equity histórica para el dashboard. Consulta directa a la REST API de Alpaca.

**Auth:** Sesión requerida
**Parámetros query:**

| Parámetro | Tipo | Default | Valores | Descripción |
|-----------|------|---------|---------|-------------|
| period | string | "1D" | 4H, 8H, 1D, 1W, 1M, 1A | Período de visualización |

**Mapeo interno a parámetros Alpaca:**

| Period | Alpaca period | Alpaca timeframe | Post-procesamiento |
|--------|--------------|-------------------|---------------------|
| 4H | 1D | 5Min | Recorta a últimas 48 barras |
| 8H | 1D | 15Min | Recorta a últimas 32 barras |
| 1D | 1D | 5Min | Sin recorte |
| 1W | 1W | 1H | Sin recorte |
| 1M | 1M | 1D | Sin recorte |
| 1A | 1A | 1D | Sin recorte |

**Response 200:**
```json
{
  "timestamps": [1777881600, 1777881900, 1777882200],
  "equity": [100044.58, 100044.58, 100045.15],
  "profit_loss": [-1.9, -1.9, -1.33],
  "profit_loss_pct": [0.0, 0.0, 0.0],
  "base_value": 100044.58,
  "period": "1D"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| timestamps | int[] | Unix timestamps de cada barra |
| equity | float[] | Valor de equity en cada barra |
| profit_loss | float[] | P&L en dólares vs base_value en cada barra |
| profit_loss_pct | float[] | P&L porcentual vs base_value |
| base_value | float | Primer valor de equity del rango (punto de equilibrio / breakeven) |
| period | string | El período solicitado (eco del parámetro) |

**Errores:**
- 422: Si `period` no es uno de los valores válidos (4H, 8H, 1D, 1W, 1M, 1A)

**Nota:** Barras con equity null se filtran automáticamente. `extended_hours=true` se envía a Alpaca.

---

## 9. Reporte

### `GET /api/report`

Reporte JSON exhaustivo del sistema. Consolida trades, macro, performance, dispatcher, y health.

**Auth:** Sesión requerida
**Parámetros query:**

| Parámetro | Tipo | Default | Valores | Descripción |
|-----------|------|---------|---------|-------------|
| range | string | "today" | today, last_week, last_month, all | Rango temporal del reporte |

**Mapeo de range a filtro temporal:**

| Range | Filtro |
|-------|--------|
| today | Desde 00:00 UTC del día actual |
| last_week | Últimos 7 días |
| last_month | Últimos 30 días |
| all | Sin filtro temporal |

**Response 200:**
```json
{
  "metadata": {
    "generated_at": "2026-05-04T23:45:00.000000Z",
    "range": "today",
    "owner": "roman",
    "system_version": "SENTINEL v0.5"
  },
  "system_health": {
    "uptime_hours": 12.5,
    "total_trades": 21,
    "macro_events": 48,
    "circuit_breaker_activations": 0,
    "errors_by_module": {},
    "reconnections": {},
    "parking_brake_activations": null
  },
  "strategy_performance": [
    {
      "sentinel": "S-1 SMA Crossover",
      "strategy": "sma_crossover",
      "tickers": ["IWM", "QQQ", "SPY"],
      "win_rate": 0.0,
      "sharpe_ratio": 0.0,
      "total_trades": 0,
      "trades_in_range": 2,
      "slippage_avg": -0.03,
      "decay_status": false,
      "allocation_pct": 5.0
    }
  ],
  "macro_context": {
    "events_total": 48,
    "risk_score_avg": 0.02,
    "regime_distribution": null,
    "parking_brake_now": true,
    "news_that_moved_decisions": [
      {
        "timestamp": "2026-05-04T19:54:00.123456",
        "risk_score": 0.0,
        "impact": "neutral",
        "titles": []
      }
    ]
  },
  "correlation_guard": {
    "threshold": 0.75,
    "rolling_window_candles": 60,
    "signals_reduced": null,
    "signals_discarded": null,
    "avg_correlation": null
  },
  "dispatcher": {
    "kelly_fraction": 0.5,
    "max_capital_per_sentinel_pct": 25.0,
    "min_capital_per_sentinel_pct": 5.0,
    "regime": "NEUTRAL",
    "kill_switch_active": false,
    "signals_received": 150,
    "signals_approved": null,
    "signals_rejected": null,
    "rejection_reasons": null
  },
  "trades": []
}
```

**Campos con valor `null` (pendientes de implementación):**
- `system_health.errors_by_module` — requiere tabla de logs o handler dedicado
- `system_health.reconnections` — requiere tracking de reconexiones Alpaca/PostgreSQL/NewsAPI
- `system_health.parking_brake_activations` — parking brake se calcula en runtime, no se persiste
- `macro_context.regime_distribution` — requiere S-10 activo
- `correlation_guard.signals_reduced/discarded/avg_correlation` — requiere columnas `signals.correlation_action`
- `dispatcher.signals_approved/rejected/rejection_reasons` — requiere columna `signals.approved`

### `GET /api/report/daily`

Reporte diario consolidado al cierre del mercado. Combina trades, equity, posiciones, macro events, rotaciones y P&L por Sentinel en un solo endpoint. También alimenta el email automático de las 16:30 ET.

**Auth:** Sesión requerida
**Parámetros query:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| dt | string | null (hoy ET) | Fecha en formato YYYY-MM-DD |

**Response 200:**
```json
{
  "date": "2026-05-04",
  "equity": 100247.30,
  "cash": 98412.15,
  "pnl": 27.40,
  "pnl_pct": 0.027,
  "positions_count": 3,
  "filled_count": 8,
  "cancelled_count": 4,
  "risk_score": 0.32,
  "trades": [
    {
      "trade_id": "uuid",
      "sentinel_name": "S-2 RSI Mean Revert",
      "ticker": "SPY",
      "side": "buy",
      "qty": 2,
      "filled_price": 562.40,
      "slippage": -0.02,
      "status": "FILLED",
      "created_at": "2026-05-04T13:35:00"
    }
  ],
  "pnl_by_sentinel": [
    { "name": "S-2 RSI Mean Revert", "pnl": 40.20 },
    { "name": "S-7 Scalper", "pnl": -12.80 }
  ],
  "positions": [
    {
      "ticker": "QQQ",
      "qty": 3.0,
      "market_value": 1463.40,
      "unrealized_pl": 8.40,
      "avg_entry": 485.00,
      "current_price": 487.80
    }
  ],
  "ear_events": [
    {
      "timestamp": "2026-05-04T14:30:00",
      "risk_score": 0.72,
      "impact": "risk_elevated",
      "titles": ["US Jobs Report higher than expected"]
    }
  ],
  "rotations": [
    {
      "decision_id": "uuid",
      "sentinel_name": "S-4 The Revert",
      "old_ticker": "AMZN",
      "new_ticker": "MSFT",
      "trigger_reason": "decay_confirmed",
      "claude_confidence": 0.85,
      "status": "executed"
    }
  ]
}
```

**Error 400:** Fecha inválida (formato incorrecto)

**Notas:**
- `pnl_by_sentinel` es una aproximación basada en trades FILLED (BUY = costo, SELL = ingreso)
- El scheduler automático envía este reporte por email a las 16:30 ET (L-V) a todos los usuarios activos
- Si no hay trades, posiciones, eventos o rotaciones, los arrays correspondientes vienen vacíos

---

## 10. Control operativo (Kill Switch)

### `GET /api/system/state`

Estado actual del kill switch.

**Auth:** Sesión requerida
**Parámetros:** Ninguno
**Response 200:**
```json
{
  "halt_requested": false,
  "system_halted": false
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| halt_requested | bool | True si se pidió halt pero el bot aún no lo procesó (se consume en ≤5s) |
| system_halted | bool | True si el bot está efectivamente detenido |

---

### `POST /api/system/halt`

Solicita detener el bot. El bot lo procesa en ≤5 segundos.

**Auth:** ADMIN requerido
**Body:** Ninguno
**Response 200:**
```json
{
  "status": "halt_requested",
  "message": "Kill switch se activará en máximo 5 segundos"
}
```
**Si ya está detenido:**
```json
{"status": "already_halted"}
```
**Response 403:**
```json
{
  "error": "forbidden",
  "message": "Solo administradores pueden controlar el sistema"
}
```

---

### `POST /api/system/resume`

Solicita reanudar el bot. El bot lo procesa en ≤5 segundos.

**Auth:** ADMIN requerido
**Body:** Ninguno
**Response 200:**
```json
{
  "status": "resume_requested",
  "message": "Sistema se reactivará en máximo 5 segundos"
}
```
**Si ya está corriendo:**
```json
{"status": "already_running"}
```
**Response 403:** Igual que `/api/system/halt`

**Nota técnica:** api.py y main.py son procesos separados. La comunicación usa la tabla `system_state` como canal IPC. main.py pollea cada 5 segundos tres flags: `halt_requested`, `system_halted`, `resume_requested`.

---

## 11. Administración de usuarios

Todos los endpoints bajo `/api/admin/*` requieren `role=ADMIN`.

### `GET /api/admin/users`

Lista todos los usuarios registrados.

**Auth:** ADMIN
**Parámetros:** Ninguno
**Response 200:**
```json
[
  {
    "user_id": "uuid-string",
    "email": "***REMOVED-EMAIL***",
    "role": "ADMIN",
    "username": "roman",
    "created_at": "2026-04-20T10:00:00.000000"
  }
]
```

---

### `POST /api/admin/users`

Crea un nuevo usuario y envía email de bienvenida en background.

**Auth:** ADMIN
**Body JSON:**
```json
{
  "email": "user@example.com",
  "role": "VIEWER"
}
```

| Campo | Tipo | Requerido | Valores | Descripción |
|-------|------|-----------|---------|-------------|
| email | string | Sí | email válido | Email del nuevo usuario |
| role | string | No | "ADMIN", "VIEWER" | Default: "VIEWER" |

**Response 200:**
```json
{
  "status": "created",
  "user": {
    "user_id": "uuid-string",
    "email": "user@example.com",
    "role": "VIEWER"
  }
}
```

**Errores:**
- 400: `"invalid_email"` — email vacío o sin @
- 400: `"invalid_role"` — role no es ADMIN ni VIEWER
- 400: `"invalid_json"` — body no es JSON válido
- 409: `"email_exists"` — el email ya está registrado

**Side effect:** Envía email de bienvenida vía Resend (fire-and-forget, no bloquea).

---

### `DELETE /api/admin/users/{user_id}`

Elimina un usuario y envía email de notificación en background.

**Auth:** ADMIN
**Parámetros path:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| user_id | UUID string | ID del usuario a eliminar |

**Response 200:**
```json
{"status": "removed"}
```

**Errores:**
- 400: `"invalid_user_id"` — user_id no es UUID válido
- 403: `"cannot_remove_owner"` — no se puede eliminar al owner del sistema
- 404: `"not_found"` — usuario no existe

---

## 12. Administración de API keys

Las keys se almacenan encriptadas con Fernet (`crypto_utils`). El bot actualmente lee de `.env` en producción — esta tabla es para gestión visual y futura migración.

### `GET /api/admin/api-keys`

Lista todas las API keys registradas (sin revelar valores).

**Auth:** ADMIN
**Response 200:**
```json
[
  {
    "key_id": "uuid-string",
    "service_name": "alpaca",
    "description": "Alpaca Paper Trading API Key",
    "last_rotated_at": "2026-04-20T10:00:00.000000",
    "created_at": "2026-04-20T10:00:00.000000",
    "updated_at": "2026-04-20T10:00:00.000000"
  }
]
```
**Response 503:** Si `MASTER_ENCRYPTION_KEY` no está configurada

---

### `POST /api/admin/api-keys`

Crea o actualiza una API key (upsert por service_name).

**Auth:** ADMIN
**Body JSON:**
```json
{
  "service_name": "resend",
  "value": "re_xxxxxxxxxxxx",
  "description": "Resend API key para emails"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| service_name | string | Sí | Nombre del servicio (clave de upsert) |
| value | string | Sí | Valor de la API key (se encripta) |
| description | string | No | Descripción opcional |

**Response 200:**
```json
{
  "status": "saved",
  "key": { ... }
}
```

**Errores:**
- 400: `"service_name_required"`, `"value_required"`, `"invalid_json"`
- 503: Error de encriptación

---

### `POST /api/admin/api-keys/{key_id}/reveal`

Revela el valor plaintext de una API key. Se loggea con WARN.

**Auth:** ADMIN
**Response 200:**
```json
{"value": "re_xxxxxxxxxxxx"}
```

**Errores:**
- 400: `"invalid_key_id"`
- 404: `"not_found"`
- 503: Error de desencriptación

---

### `DELETE /api/admin/api-keys/{key_id}`

Elimina una API key.

**Auth:** ADMIN
**Response 200:**
```json
{"status": "removed"}
```

**Errores:**
- 400: `"invalid_key_id"`
- 404: `"not_found"`

---

## 13. Universe Selector (rotaciones)

### `GET /api/admin/rotations`

Historial de decisiones de rotación del Universe Selector (Claude Sonnet 4.6).

**Auth:** ADMIN
**Parámetros query:**

| Parámetro | Tipo | Default | Valores | Descripción |
|-----------|------|---------|---------|-------------|
| limit | int | 50 | 1-500 | Máximo de rotaciones a devolver |
| status | string | null | pending, executed, rolled_back, failed, discarded | Filtrar por estado |

**Response 200:**
```json
[
  {
    "decision_id": "uuid-string",
    "sentinel_id": "uuid-string",
    "sentinel_name": "S-3 Bollinger Bounce",
    "old_ticker": "XLK",
    "new_ticker": "XLV",
    "trigger_reason": "decay_detected",
    "claude_reasoning": "XLK muestra decay sostenido...",
    "candidates_proposed": [
      {"ticker": "XLV", "score": 0.85, "rationale": "..."},
      {"ticker": "XLE", "score": 0.72, "rationale": "..."}
    ],
    "cost_usd": 0.08,
    "status": "executed",
    "executed_at": "2026-05-02T14:00:00.000000",
    "created_at": "2026-05-02T13:55:00.000000"
  }
]
```

**Errores:**
- 400: `"invalid_status"` si el status no es uno de los valores válidos

---

### `GET /api/admin/rotations/{decision_id}`

Detalle completo de una decisión de rotación específica.

**Auth:** ADMIN
**Parámetros path:** `decision_id` (UUID string)
**Response 200:** Mismo schema que un item de `/api/admin/rotations`
**Errores:**
- 400: `"invalid_decision_id"`
- 404: `"not_found"`

---

### `POST /api/admin/rotations/{decision_id}/rollback`

Revierte una rotación ejecutada (restaura el ticker anterior).

**Auth:** ADMIN
**Parámetros path:** `decision_id` (UUID string)
**Response 200:**
```json
{
  "status": "rolled_back",
  "decision_id": "uuid-string",
  "by": "***REMOVED-EMAIL***"
}
```

**Errores:**
- 400: `"invalid_decision_id"`
- 409: `"rotation_not_rollbackable"` — la rotación no está en estado que permita rollback

---

### `GET /api/admin/candidates`

Candidatos pendientes de rotación (pending_candidates con TTL de 7 días).

**Auth:** ADMIN
**Parámetros:** Ninguno
**Response 200:** Array de candidatos pendientes (formato varía según estructura de DB)

---

### `GET /api/rotations/recent`

Últimas rotaciones ejecutadas. Versión simplificada para el dashboard (sin razonamiento ni costos).

**Auth:** Sesión requerida (VIEWER + ADMIN)
**Parámetros query:**

| Parámetro | Tipo | Default | Rango | Descripción |
|-----------|------|---------|-------|-------------|
| limit | int | 5 | 1-20 | Número de rotaciones a devolver |

**Response 200:**
```json
[
  {
    "decision_id": "uuid-string",
    "sentinel_name": "S-3 Bollinger Bounce",
    "old_ticker": "XLK",
    "new_ticker": "XLV",
    "executed_at": "2026-05-02T14:00:00.000000",
    "trigger_reason": "decay_detected"
  }
]
```

**Nota:** Solo devuelve rotaciones con `status = "executed"`.

---

## 14. Server-Sent Events (SSE)

### `GET /api/sse`

Stream de actualizaciones en tiempo real para el dashboard. Envía un snapshot cada 15 minutos.

**Auth:** Sesión requerida
**Response:** `text/event-stream`

**Evento `update`:**
```json
{
  "ts": "2026-05-04T23:45:00.000000Z",
  "status": { /* mismo schema que GET /api/status */ },
  "sentinels": [
    {
      "sentinel_id": "uuid-string",
      "name": "S-1 SMA Crossover",
      "strategy_type": "sma_crossover",
      "tickers": ["IWM", "QQQ", "SPY"]
    }
  ],
  "trades": [ /* últimos 10 trades, mismo schema que GET /api/trades */ ]
}
```

**Evento `error`:**
```json
{"error": "mensaje de error"}
```

**Comportamiento:**
- Primer payload se envía inmediatamente al conectar
- Posteriores cada 900 segundos (15 minutos)
- Ping cada 15 segundos para mantener la conexión viva
- Errores NO matan el stream — se envían como evento `error` y se espera al próximo ciclo

---

## 15. Frontend estático

### `GET /`

Dashboard SPA principal. Redirige a `/auth/login` si no hay sesión.

**Auth:** Sesión requerida (cualquier role)
**Response:** HTML (FileResponse de `dashboard/index.html`)

---

### `GET /admin`

Panel de administración de usuarios y API keys.

**Auth:** ADMIN requerido
**Response:**
- Sin sesión → 302 Redirect a `/auth/login`
- VIEWER → 302 Redirect a `/` (silent, no 403)
- ADMIN → HTML (FileResponse de `dashboard/admin.html`)

---

## 16. Códigos de error comunes

| Código | Significado | Cuándo |
|--------|-------------|--------|
| 400 | Bad Request | Parámetros inválidos (UUID mal formado, email inválido, etc.) |
| 401 | Unauthorized | Sin sesión activa. Response: `{"error": "unauthorized"}` |
| 403 | Forbidden | Sesión activa pero role insuficiente. Response: `{"error": "forbidden", "message": "..."}` |
| 404 | Not Found | Recurso no existe (usuario, API key, rotación) |
| 409 | Conflict | Email ya existe, rotación no es rollbackable |
| 422 | Validation Error | Parámetro query fuera de rango o regex (FastAPI automático) |
| 500 | Internal Server Error | Error de base de datos o Alpaca API. Response: `{"detail": "operación: mensaje"}` |
| 503 | Service Unavailable | MASTER_ENCRYPTION_KEY no configurada (API keys) |

---

## 17. Notas sobre autenticación y roles

### Rutas públicas (sin sesión)
- `/auth/login`, `/auth/callback`, `/auth/logout`
- `/api/market-status`
- Assets estáticos: `/sentinel-data.js`, `/sentinel-app.js`, `/sentinel-i18n.js`, `/favicon.ico`, `/assets/*`

### Rutas que requieren sesión (VIEWER + ADMIN)
- Todos los `/api/*` excepto los públicos y los de admin
- `/` (dashboard)

### Rutas que requieren ADMIN
- `/admin` (panel HTML)
- `POST /api/system/halt`
- `POST /api/system/resume`
- Todo bajo `/api/admin/*` (usuarios, API keys, rotaciones admin, candidatos)

### Middleware de sesión
- Cookie: `sentinel_session` (configurable vía SESSION_COOKIE_NAME)
- Max age: configurable vía SESSION_MAX_AGE_SECONDS
- HTTPS only: configurable vía SESSION_HTTPS_ONLY (default true)
- Same-site: lax

---

*Documento generado el 4 de mayo de 2026.*
*Verificado contra api.py y responses reales del sistema en producción (paper trading).*
*Mantener actualizado cada vez que se agregue o modifique un endpoint.*
