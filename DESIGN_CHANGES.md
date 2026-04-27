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

### 6. Link ADMIN en header
- **Archivo**: `dashboard/sentinel-data.js` + CSS inyectado desde JS
- **Fecha**: 2026-04-26
- **Razón**: los administradores necesitan acceso rápido al panel de gestión de usuarios (`/admin`). El handoff no contempla un control para esto.
- **Implementación**: al boot, `setupAdminLink()` hace fetch a `/auth/me`. Si la respuesta tiene `role=ADMIN`, se inyecta un `<a id="adminLink" href="/admin">ADMIN</a>` justo antes del `#detenerBtn`. Estilo magenta (`#ff00ff`) con borde y `letter-spacing` consistente con la tipografía del header. CSS inyectado vía `<style id="sentinel-adminlink-style">`.
- **Impacto visual**: badge magenta discreto a la izquierda del botón DETENER. Solo aparece para `role=ADMIN`. Para `VIEWER` no se inyecta, ni se carga.
- **Nota para Design**: considerar un slot nativo para iconos de admin en el header del handoff cuando se regenere.

## Handoffs adicionales de Design integrados

Estos no son desviaciones del handoff dashboard original, sino *handoffs nuevos* que Design entregó después y reemplazaron implementaciones provisionales del backend.

### A. Templates de email transaccional (Resend)
- **Archivos**: HTML embebidos en `sentinel-v0.5/email_service.py` (constantes `_WELCOME_TEMPLATE`, `_REVOKED_TEMPLATE`).
- **Fecha**: 2026-04-26
- **Origen**: handoff `templetes-correo/email_handoff/templates/{welcome.html, revoked.html}`.
- **Variables del template**: `{email}`, `{role}`, `{admin_permissions_es}`, `{admin_permissions_en}`. Las dos últimas son bloques HTML que se inyectan solo cuando `role=ADMIN`, vacíos para `VIEWER`.
- **Estructura**: layout 100% con `<table>` + CSS inline (compatible Outlook 2007+, Gmail, Apple Mail). Bilingüe ES/EN separados por divider magenta. `Courier New` como fuente (sin webfonts, máxima compatibilidad cross-client).
- **Subject**: bilingüe (`Bienvenido a Sentinel Control / Welcome to Sentinel Control`, `Acceso revocado / Access revoked — Sentinel Control`).
- **Header**: `X-Entity-Ref-ID` para tracking en Resend.

### B. Panel admin
- **Archivos**: `dashboard/admin.html`, `dashboard/admin-app.js`.
- **Fecha**: 2026-04-26
- **Origen**: handoff `panel-admin/design_handoff_sentinel_admin/`.
- **Adapter agregado**: `apiListUsers` mapea `user_id → id` para mantener compatible el JS de Design con la API real (que retorna `user_id`). Una sola línea `list.map(u => ({ ...u, id: u.id || u.user_id }))` — la lógica `id/user_id` queda aislada en un solo punto. Resto del JS (Design) sin tocar.
- **Endpoints consumidos**: `GET/POST/DELETE /api/admin/users` (sin cambios en api.py).
- **Manejo auth**: 401 → `/auth/login`; 403 → banner inline "ACCESO DENEGADO". Coherente con sentinel-data.js.

### 7. Sección de API Keys en panel admin (admin.html + admin-app.js)
- **Archivos**: `dashboard/admin.html`, `dashboard/admin-app.js`.
- **Fecha**: 2026-04-27
- **Razón**: el administrador necesita gestionar credenciales de servicios
  externos (Alpaca, NewsAPI, Resend, Google OAuth, futuro Anthropic) sin editar
  manualmente el archivo `.env` del servidor. El backend persiste las keys
  encriptadas con Fernet (#FIX-008). Por ahora el bot sigue leyendo desde
  `.env` — la sincronización automática es trabajo de una sesión futura.
- **Componentes afectados**:
  - Sección nueva "API KEYS" debajo de "AGREGAR USUARIO".
  - Tabla con columnas: Servicio, Valor (enmascarado), Descripción, Última
    rotación, Acciones.
  - Botón toggle MOSTRAR/OCULTAR por fila — al revelar pinta el plaintext y
    arranca un timer de 30s para volver a ocultarlo.
  - Botón ELIMINAR con `confirm()` por fila.
  - Banner amber arriba de la tabla advirtiendo que el bot todavía lee desde
    `.env`.
  - Sección "AGREGAR / ACTUALIZAR API KEY" con form: `service_name` (text),
    `value` (password), `description` (text). Upsert por `service_name`.
- **Estilo aplicado**: consistente con el handoff existente del panel admin
  (cyberpunk: cyan `#00f5ff` para acciones de info, magenta `#ff00d4` para
  estado revealed, amber `#ff9e2c` para warnings, red `#ff2060` para
  destructivas). Reutiliza `.tbl`, `.btn-del`, `.btn-add`, `.field`,
  `.feedback` del handoff. Solo agrega clases nuevas: `.warn-banner`,
  `.btn-toggle`, `.key-cell`, `.api-key-form`.
- **Endpoints consumidos**:
  - `GET    /api/admin/api-keys` — lista con valores enmascarados.
  - `POST   /api/admin/api-keys` — upsert (body: `service_name, value, description`).
  - `POST   /api/admin/api-keys/{key_id}/reveal` — devuelve plaintext (loggea
    WARN con email del admin que reveló).
  - `DELETE /api/admin/api-keys/{key_id}`.
  Todos ADMIN-only (gating por `_ADMIN_PREFIXES = ('/api/admin/',)`).
- **Nota para Design**: para una próxima iteración, considerar:
  - Ícono ojo abierto/cerrado para los toggles MOSTRAR/OCULTAR (hoy texto).
  - Botón copy-to-clipboard al lado del valor revelado.
  - Animación del countdown de 30s (barra de progreso o número visible).
  - Badge visual para keys con > 90 días sin rotar (alerta de seguridad).
  - Estado "key próxima a expirar" si se persisten fechas de expiración por servicio.

### 8. Banner de rotaciones recientes en dashboard (sentinel-data.js)
- **Archivo**: `dashboard/sentinel-data.js`.
- **Fecha**: 2026-04-27
- **Razón**: el módulo Universe Selection (#UNIVERSE-SELECTION) rota tickers
  de Sentinels automáticamente cuando detectan decay. El admin (y los viewers)
  necesitan visibilidad inmediata cuando esto ocurre, sin tener que abrir el
  panel admin. Una franja discreta debajo del header señala la rotación más
  reciente de las últimas 24h.
- **Componentes afectados**:
  - Banner full-width insertado debajo de `header.header-fixed` por JS.
  - Tag `⟲ ROTATION` magenta + nombre del Sentinel + ticker viejo (rojo) →
    ticker nuevo (verde) + tiempo relativo ("hace 2h").
  - CTA "VER DETALLE" → `/admin#rotations` (solo si `window._userRole === 'ADMIN'`).
  - Botón × para ocultar el banner por la sesión.
- **Estilo aplicado**: gradiente sutil magenta/cyan consistente con la paleta
  del handoff. Usa `Share Tech Mono` (`--mono` ya inyectada por
  sentinel-app.js). No usa `!important` — orden de inserción garantiza
  precedencia sin pisar otros estilos.
- **Endpoints consumidos**:
  - `GET /api/rotations/recent?limit=5` (VIEWER + ADMIN; expone solo
    ticker/timestamp/sentinel — sin razonamiento ni costo).
- **Nota para Design**: para una próxima iteración, considerar:
  - Animación de entrada cuando aparece una rotación nueva (slide-down 200ms).
  - Variante con icono SVG personalizado en lugar del glyph `⟲`.
  - Colapsado por defecto con un botón "ver últimas rotaciones" si hay más
    de una en el período.
  - Toast/notification temporal en lugar de banner persistente.

### 9. Sección "Rotaciones de Universo" + "Candidatos pendientes" en panel admin (admin.html + admin-app.js)
- **Archivos**: `dashboard/admin.html`, `dashboard/admin-app.js`.
- **Fecha**: 2026-04-27
- **Razón**: las rotaciones automáticas del Universe Selection necesitan un
  surface de auditoría completo: ver historial de decisiones, leer el
  razonamiento de Claude, revisar candidatos alternativos propuestos,
  analizar el costo en tokens, y poder hacer rollback si algo se ve mal.
  La Watchlist Anticipada (pending_candidates) también necesita
  visualización aunque sea read-only.
- **Componentes afectados**:
  - Sección **ROTACIONES DE UNIVERSO** (tabla con Fecha, Sentinel,
    Rotación old→new, Estado, Costo USD, Acciones).
  - Filtro de status arriba de la tabla (todos / executed / pending /
    rolled_back / failed / discarded).
  - Botón **DETALLE** por fila → modal centrado con razonamiento completo,
    candidatos alternativos con confidence + razón corta, performance del
    ticker viejo, modelo usado, tokens consumidos, costo USD.
  - Botón **ROLLBACK** por fila — solo visible si `status='executed'` AND
    `executed_at < 7 días`. `confirm()` antes de ejecutar; el email del
    admin queda registrado en `rotation_decisions.rolled_back_by`.
  - Sección **CANDIDATOS PENDIENTES** (tabla read-only con Sentinel,
    Candidato, Propuesto, Expira).
  - Status badges con color semántico: verde executed, amarillo pending,
    magenta rolled_back, rojo failed, gris discarded.
  - Modal con backdrop blur + close por × / click backdrop / Escape.
- **Estilo aplicado**: 100% consistente con el handoff existente del panel
  admin. Reutiliza `.tbl`, `.btn-del`, `.field`, `.feedback`, `.section`,
  `.panel`, `.role-badge` (extendido como `.status-badge` con la misma
  estructura y palette). Solo agrega clases nuevas: `.btn-rollback`,
  `.btn-detail`, `.tk-old`, `.tk-new`, `.tk-arrow`, `.modal-backdrop`,
  `.modal-card`, `.modal-row`, `.filters-bar`, `.candidate-list`.
- **Endpoints consumidos**:
  - `GET    /api/admin/rotations?status=...&limit=N` — lista filtrable.
  - `GET    /api/admin/rotations/{id}` — detalle completo (modal).
  - `POST   /api/admin/rotations/{id}/rollback` — revierte rotación.
  - `GET    /api/admin/candidates` — Watchlist activa.
  Todos ADMIN-only (gating por `_ADMIN_PREFIXES = ('/api/admin/',)`).
- **Nota para Design**: para una próxima iteración, considerar:
  - Mini-chart inline en cada fila mostrando win_rate trend del ticker
    viejo (sparkline 30 trades) — visual rápido del decay detectado.
  - Tab/segmented control en lugar de `<select>` para el filtro de status.
  - Diff visual del prompt enviado a Claude (system + user) en el modal —
    útil para auditar prompts evolutivos.
  - Indicador visual de "candidato pre-aprobado" en candidatos pendientes
    (countdown hasta expiración + barra de progreso).
  - Drag-and-drop para reordenar candidatos alternativos del modal y
    "preferir" uno distinto al recommended (requeriría endpoint nuevo).
  - Comparador lado-a-lado de dos rotaciones del mismo Sentinel
    (eficiencia A vs B).

## Histórico de revisiones de este documento

- 2026-04-26 — versión inicial. Captura cambios 1–5 acumulados desde el handoff original.
- 2026-04-26 — agregado cambio 6 (link ADMIN en header).
- 2026-04-26 — agregada sección "Handoffs adicionales" con A (emails) y B (panel admin) integrados.
- 2026-04-27 — agregado cambio 7 (sección API Keys en panel admin, #FIX-008).
- 2026-04-27 — agregados cambios 8 y 9 (banner de rotaciones en dashboard, secciones de Rotaciones y Candidatos en panel admin, #UNIVERSE-SELECTION).
