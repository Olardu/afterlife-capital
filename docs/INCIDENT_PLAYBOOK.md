# INCIDENT PLAYBOOK — Sentinel

> **Propósito:** runbook de emergencia. 5 escenarios catastróficos pre-pensados con: cómo detectarlo, primer paso, qué NO hacer, recovery completo. Para que cuando algo se rompe a las 11am, Roman no tenga que pensar desde cero.

**Mantenedor:** Cowork (Roma) actualiza. Code agrega scripts de recovery cuando los crea. Roman valida que los pasos sean ejecutables.

**Archivo regenerado el:** 2026-05-25 (versión anterior perdida al reiniciar sesión Cowork).

---

## Convenciones

Cada escenario tiene 4 secciones:
- **Detección:** cómo te das cuenta de que está pasando.
- **Primer paso (en frío):** lo único que tenés que hacer en los primeros 60 segundos.
- **NO hacer:** errores comunes que empeoran la situación.
- **Recovery completo:** pasos para volver a operación normal.

**Regla general en cualquier incidente:** primero estabilizar, después diagnosticar. NUNCA empezar a tocar código en caliente.

---

## Escenario 1 — Bot en loop infinito (CPU al 100%, no responde)

**Síntomas:**
- Dashboard no actualiza desde hace >10 minutos.
- `curl http://localhost:8000/api/health` no responde o timeout.
- `Get-Process python` en PowerShell muestra CPU >90% sostenido.
- Sin logs nuevos en `sentinel-v0.5/logs/sentinel.log` desde el momento del cuelgue.

**Detección automática:** healthchecks.io (cuando #FEAT-004 esté implementado) dispara alerta a Roman si el bot deja de pingar por >5 min.

**Primer paso (en frío):**
```powershell
# Forzar parar el proceso, sin discusión
Get-Process python | Where-Object {$_.Path -like "*afterlife-capital*"} | Stop-Process -Force
```

Después de eso, las posiciones abiertas en Alpaca SIGUEN PROTEGIDAS por sus bracket orders (SL/TP server-side) si estaban operando con `ATR_SIZING_ENABLED=true`. El broker cuida solo. Tenés tiempo para diagnosticar sin pánico.

**NO hacer:**
- NO matar el proceso Python sin antes verificar que no está en medio de un INSERT a la DB. Riesgo de transacción a medias. Mejor parar via endpoint si responde: `curl -X POST http://localhost:8000/api/admin/shutdown` (si existe).
- NO reiniciar inmediatamente sin revisar logs. El loop puede repetirse.
- NO tocar Alpaca manualmente sin verificar primero qué tiene el bot abierto.

**Recovery completo:**
1. Revisar últimas 200 líneas de `sentinel-v0.5/logs/sentinel.log` para identificar la operación que disparó el loop.
2. Verificar estado de posiciones reales en Alpaca: `python -c "from alpaca.trading.client import TradingClient; c=TradingClient(...); print(c.get_all_positions())"`.
3. Comparar con `self.open_positions` cache reconstruyendo desde DB (query: `SELECT ticker, qty FROM trades WHERE status='FILLED' AND closed_at IS NULL`).
4. Si hay desincronización entre Alpaca y DB → reconciliar primero (#H-5/#H-6b lo cubren parcialmente).
5. Identificada la causa del loop, fixearla con TAREA explícita en LOG, commit, push, restart.
6. Si la causa no es identificable inmediatamente, restart con flag `KILL_SWITCH_ACTIVE=true` para arrancar en modo seguro (sin operar) y observar.

---

## Escenario 2 — Cloudflare Tunnel caído (dashboard inaccesible, pero el bot operando)

**Síntomas:**
- Dashboard en `https://dashboard.afterlifecapital.co` da error de conexión o 502.
- Pero localmente `http://localhost:8000` responde normal.
- `cloudflared tunnel list` muestra el tunnel en estado distinto a "active".

**Detección automática:** healthchecks.io del endpoint público (si configurado) dispara alerta cuando cae.

**Primer paso (en frío):**

No es emergencia. **El bot sigue operando normalmente** porque Cloudflare Tunnel solo es la capa de acceso público al dashboard. Las posiciones, las decisiones, todo sigue en el localhost.

```powershell
# Verificar primero que efectivamente el bot está corriendo OK localmente
curl http://localhost:8000/api/health
```

Si el bot está sano localmente → la urgencia es 0. Si NO está sano → ir a Escenario 1 o 5.

**NO hacer:**
- NO reiniciar el bot pensando que el problema es del bot. El problema es de Cloudflare, no del bot.
- NO entrar en pánico — la operación del bot no depende del dashboard.

**Recovery completo:**
1. Reiniciar el daemon de cloudflared:
   ```powershell
   Get-Service cloudflared | Restart-Service
   ```
   o si corre como proceso:
   ```powershell
   Stop-Process -Name cloudflared -Force
   cloudflared tunnel run <tunnel-name>
   ```
2. Verificar con `cloudflared tunnel info <tunnel-name>` que volvió a "active".
3. Probar el dashboard público desde otro device (móvil con datos, no WiFi de casa).
4. Si Cloudflare sigue caído globalmente (chequear status.cloudflare.com), no hay nada que hacer del lado nuestro — esperar.

---

## Escenario 3 — Alpaca API caída con posiciones abiertas

**Síntomas:**
- Bot loguea errores `alpaca.common.exceptions.APIError` o timeouts repetidos.
- `https://status.alpaca.markets` muestra incidente abierto.
- Dashboard sigue funcional pero las posiciones no actualizan precio.

**Detección automática:** logs del bot llenándose de errores Alpaca + dashboard mostrando "Stale data" warning (cuando implementado).

**Primer paso (en frío):**

Tampoco es emergencia inmediata. Las posiciones abiertas con bracket orders están PROTEGIDAS server-side por Alpaca — los SL/TP se ejecutan en el lado de Alpaca aunque tu bot esté desconectado. No te van a saltar stops por la caída.

PERO: el bot NO va a poder abrir nuevas posiciones, NI cerrar posiciones manualmente, ni reconciliar cache, durante el outage.

```powershell
# Activar kill switch para que el bot deje de intentar (evita llenar logs)
curl -X POST http://localhost:8000/api/admin/kill-switch -d '{"active":true}'
```

**NO hacer:**
- NO intentar pánico-cerrar posiciones manualmente desde la web de Alpaca durante el outage (probablemente tampoco responda).
- NO tocar el código del bot — el problema es externo.
- NO desactivar `ATR_SIZING_ENABLED` durante el incidente — perdés la protección server-side de las posiciones nuevas cuando vuelva.

**Recovery completo:**
1. Esperar a que `status.alpaca.markets` muestre "Resolved".
2. Verificar reconectividad: `curl https://paper-api.alpaca.markets/v2/account` con auth headers.
3. Reconciliar estado: `python sentinel-v0.5/scripts/reconcile_positions.py` (cuando exista — #H-6b cubre parte).
4. Desactivar kill switch: `curl -X POST http://localhost:8000/api/admin/kill-switch -d '{"active":false}'`.
5. Observar primeros 2-3 cycles para asegurar que el bot retomó operación normal.

---

## Escenario 4 — The Ear emite veto erróneo (bloquea trading sin razón válida)

**Síntomas:**
- Dashboard muestra `can_trade=False` durante horas/días.
- Logs muestran `circuit_breaker activado` o `risk_score>0.7` persistente.
- Pero el mercado está calmo y no hay eventos macro reales (chequear con Bloomberg, Reuters, Twitter financiero).

**Detección:** Roman observa que el bot no opera nada en un día que sí debería operar.

**Primer paso (en frío):**

Inspeccionar qué titulares está catching The Ear:
```sql
SELECT created_at, risk_score, headlines_matched 
FROM macro_events 
WHERE created_at > NOW() - INTERVAL '24 hours' 
ORDER BY risk_score DESC LIMIT 20;
```

Identificar si hay un titular específico que dispara el risk_score alto.

**NO hacer:**
- NO desactivar The Ear sin entender qué disparó el veto. Puede ser correcto y vos no estás viendo el evento macro real.
- NO tocar el threshold (0.7) durante el período de observación.

**Recovery completo:**
1. Si el titular catched es claramente irrelevante (ej: artículo viejo, satira, ticker que no aplica) → agregar a blacklist de The Ear (función `_is_relevant_headline` o similar).
2. Si el patrón se repite con titulares similares → tunear keywords con tests sintéticos antes de tocar producción.
3. Si es bug genuino de la lógica de scoring → registrar como #BUG-FUNC en BACKLOG y agendar fix con TAREA explícita.
4. Workaround temporal (último recurso): bajar `RISK_SCORE_VETO_THRESHOLD` solo si lo vetado claramente debería haber pasado. Documentar en CHANGELOG + commit.

---

## Escenario 5 — Universe Selector recomienda tickers absurdos (penny stocks, leveraged ETFs, etc.)

**Síntomas:**
- Logs de `universe_selector` muestran recomendaciones tipo `TQQQ`, `SQQQ`, `UVXY`, `SPXL`, o tickers exóticos no conocidos.
- Dashboard muestra rotaciones recientes a tickers no validados.
- El balance del período 1 ya capturó 7 productos exóticos que pasaron (ver §4 del balance 24-may).

**Detección:** Roman al revisar dashboard / Cowork al hacer balance.

**Primer paso (en frío):**

Verificar si los tickers exóticos ya generaron trades:
```sql
SELECT t.ticker, t.qty, t.opened_at, t.filled_price 
FROM trades t 
WHERE t.ticker IN ('TQQQ', 'SQQQ', 'UVXY', 'SPXL', 'TZA', 'FAS', 'FAZ') 
  AND t.closed_at IS NULL;
```

Si hay posiciones abiertas en exóticos → primero cuidarlas (las bracket orders ya tienen SL, pero monitorear).

**NO hacer:**
- NO cerrar posiciones a pánico — pueden estar dentro de su lógica de salida normal. Usar el bracket server-side.
- NO desactivar Universe Selector completamente — perdés capacidad de rotar Sentinels malos.

**Recovery completo:**
1. Identificar la lista de tickers exóticos del período (los 7 ya documentados + nuevos).
2. Agregar a la **blacklist de Universe Selector** (función `_is_eligible_ticker` o similar). Esto está agendado como item en BACKLOG (estaba parte del plan post-observación Fase 3).
3. Reforzar el prompt del Universe Selector con instrucciones explícitas anti-leverage / anti-penny stock.
4. Tests sintéticos: alimentar al Universe Selector con la lista exótica del período y verificar que con el prompt nuevo NO los recomienda.
5. Commit + push + restart.
6. Validar en el siguiente cycle de Universe Selection que la blacklist se respeta.

---

## Reglas generales para cualquier incidente

1. **Estabilizar antes de diagnosticar.** Si hay riesgo a la operación o al capital, primero parar la sangría (kill switch, parar el proceso), después investigar.
2. **NO tocar el código en caliente.** Si necesitás fix, hacelo en una sesión con tests, no en producción a las 11am.
3. **Documentar el incidente.** Cada incidente sin documentación es un incidente que se va a repetir. Mínimo: entrada en LOG con timestamp, síntomas, qué hiciste, qué funcionó.
4. **Reconciliar antes de retomar.** Después de cualquier corte, verificar que el estado interno del bot (DB, cache, etc.) coincide con el estado real en Alpaca.
5. **Aprender:** post-incidente, agendar item en BACKLOG con la prevención (script de detección, test de regresión, hardening).

---

## Escenario: FinBERT (modelo de sentiment) no carga (#FEAT-007 / T-U) — añadido por Code

**Síntoma:** en el log de arranque o del primer ciclo de The Ear aparece
`SentimentAnalyzer: el modelo '...' no carga (...). Fallback a keyword matching.`

**Qué pasa (NO es un incidente que pare el bot):** el diseño es fail-safe. Si
`transformers`/`torch` no están instalados, el modelo no se puede descargar (sin red),
o la inferencia falla, `SentimentAnalyzer.score()` devuelve `None` y The Ear cae
**automáticamente** al keyword matching legacy. El `sentiment_method` de los
`macro_events` queda en `keyword`. El bot sigue operando normal — solo pierde la
señal FinBERT extra.

**Acción:**
1. Confirmar que es esto: `python -c "import torch, transformers; print('ok')"` en el
   venv del bot. Si falla → faltan las deps (`pip install -r requirements.txt`).
2. Pre-descargar el modelo: `python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='ProsusAI/finbert')"`.
3. Si no se puede resolver pre-apertura, **no bloquea**: dejar `THE_EAR_SENTIMENT_ENABLED=false`
   (o aceptar el fallback automático) y el bot opera con keyword matching como siempre.
4. Recién cuando `torch`/`transformers` carguen y el modelo esté en cache, activar el
   flag y reiniciar.

> Regla: un fallo de FinBERT NUNCA debe parar el trading. Si lo hace, es un bug —
> reportar. El fallback a keyword es la red de seguridad por diseño.

---

*INCIDENT_PLAYBOOK regenerado por Cowork el 2026-05-25. Reemplaza versión perdida. Iterar agregando escenarios cuando se identifiquen nuevos en producción.*
