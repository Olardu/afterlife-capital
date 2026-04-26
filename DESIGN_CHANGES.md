# Cambios al Diseño — Desviaciones del Handoff Original

Archivo base del handoff: Claude Design, "Sentinel Dashboard v2", entregado 2026-04-25.

Archivos del handoff que **no se modifican**:

- `dashboard/index.html`
- `dashboard/sentinel-app.js`
- `dashboard/sentinel-i18n.js`

Archivo custom que adapta el handoff: `dashboard/sentinel-data.js`. Todo cambio de comportamiento y los CSS adicionales se inyectan desde ahí.

## Cambios acumulados

### 1. Tick mock neutralizado
- **Archivo**: `dashboard/sentinel-data.js`
- **Fecha**: 2026-04-25
- **Razón**: el handoff llama `setTimeout(tick, 2500)` al final de `sentinel-app.js` y arranca un loop que muta datos mock. En modo conectado a la API los updates llegan por SSE — no queremos que el tick mock pise los datos reales.
- **Implementación**: monkey-patch de `window.setTimeout` antes de que `sentinel-app.js` cargue. Si la fn es `tick` la descarta y retorna -1.
- **Impacto visual**: ninguno — los datos falsos dejan de moverse, los reales los reemplazan.

### 2. Persistencia de preferencias en localStorage
- **Archivo**: `dashboard/sentinel-data.js`
- **Fecha**: 2026-04-25
- **Razón**: el handoff no persiste `lang/view/theme` entre recargas.
- **Implementación**: event delegation en `document` que guarda en `localStorage` cuando el usuario clickea las pills de idioma, view o theme. Restauración al boot.
- **Impacto visual**: ninguno — solo persistencia.

### 3. Botón DETENER conectado al kill switch real
- **Archivo**: `dashboard/sentinel-data.js`
- **Fecha**: 2026-04-26
- **Razón**: el handoff cableó `#detenerBtn` a `alert('SISTEMA DETENIDO (demo)')`. Necesitamos que dispare el kill switch real vía `POST /api/system/halt`.
- **Implementación**: `document.addEventListener('click', ..., true)` con `closest('#detenerBtn')` + `stopImmediatePropagation()`. La fase capture sobre `document` corre antes que el listener target del handoff. Un `addEventListener(..., true)` sobre el botón mismo NO funciona — en el target, los listeners corren en orden de registro independientemente de `useCapture`.
- **Impacto visual**: el botón muestra `confirm()` en lugar de `alert(demo)`.

### 4. Toggle INICIAR / DETENER
- **Archivo**: `dashboard/sentinel-data.js` + CSS inyectado desde JS
- **Fecha**: 2026-04-26
- **Razón**: después de un halt, el botón debe permitir reactivar el sistema. El handoff solo contempla un estado.
- **Implementación**:
  - Inyección dinámica de keys `btn_iniciar` en `I18N` (es/en/ja/th).
  - Mutación del atributo `data-i18n` del botón entre `btn_detener` y `btn_iniciar`. La función `applyI18n()` del handoff lee `data-i18n`, así el cambio de idioma respeta el estado actual sin pisar el texto.
  - Inyección de un `<style>` con `#detenerBtn.system-halted { ... }` con `!important` para anteceder al CSS del handoff.
  - Click handler bifurca: si está en estado halted → `POST /api/system/resume`; si no → `POST /api/system/halt`.
  - Estado se refresca al boot (`refreshKillSwitchState`) y en cada update del SSE (vía `reloadFromAPI`).
- **Impacto visual**: el botón cambia de rojo a verde cuando `system_halted=true`. Texto cambia a "+ INICIAR" / "+ START" / "+ 開始" / "+ เริ่ม".
- **Nota para Design**: si se regenera el handoff, sería más limpio que el botón tenga estados nativos (halted / running) en el CSS y un atributo controlado por el dashboard.

### 5. Redirección automática a login en 401
- **Archivo**: `dashboard/sentinel-data.js`
- **Fecha**: 2026-04-26
- **Razón**: con auth Google OAuth habilitada, los `fetch` a `/api/*` pueden retornar 401 cuando la sesión expira. Sin manejo, el dashboard quedaría en estado roto silencioso.
- **Implementación**: `_fetchJson` detecta `r.status === 401` y dispara `window.location.href = '/auth/login'`. Un flag interno `_redirectingToLogin` evita redirects en cascada cuando varios fetch concurrentes reciben 401 al mismo tiempo. Status `403` muestra un `alert("No tenés permisos para esta acción.")` y devuelve `null` (caso role=VIEWER intentando un endpoint ADMIN).
- **Impacto visual**: el dashboard desaparece y aparece la pantalla de login de Google.
- **Nota para Design**: considerar agregar una pantalla de "sesión expirada" en el handoff para futura entrega.

## Histórico de revisiones de este documento

- 2026-04-26 — versión inicial. Captura cambios 1–5 acumulados desde el handoff original.
