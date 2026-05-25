# AFTERLIFE CAPITAL — Sentinel Admin Panel

Panel de administración (`/admin`) para Sentinel Control. Gestión de
usuarios — solo accesible para administradores.

## Archivos

| Archivo         | Propósito |
| --------------- | --------- |
| `admin.html`    | Página standalone (HTML + CSS inline) |
| `admin-app.js`  | Cliente JS: fetch a la API, render de tabla, formulario |

> Diseño consistente con `Sentinel Dashboard v2.html` (mismas variables CSS,
> tipografía Orbitron / Share Tech Mono / JetBrains Mono, paleta cyan/magenta).
> Tema cyber por defecto. Solo localización en español.

## Estructura visual

1. **Header fijo** — brand `AFTERLIFE CAPITAL — ADMIN PANEL` + botón
   `← VOLVER AL DASHBOARD` (link a `/`).
2. **Título** — `USER CONTROL` (cyan / magenta) con descriptor.
3. **Sección "Usuarios registrados"** — tabla con columnas:
   - `EMAIL` (con tag `OWNER` para `owner@example.com`)
   - `ROL` (badge de color: ADMIN = magenta, VIEWER = cyan)
   - `FECHA DE REGISTRO`
   - `ACCIONES` — botón `ELIMINAR` (rojo). El owner muestra `— OWNER —`
     en lugar del botón.
4. **Sección "Agregar usuario"** — input email + selector de rol
   (VIEWER por defecto) + botón `+ AGREGAR`. Mensajes de feedback inline:
   - éxito (verde): `Usuario agregado. Email de bienvenida enviado.`
   - duplicado (rojo): `Ese email ya está registrado.`
5. **Footer** — link `CERRAR SESIÓN` (a `/auth/logout`) + `Sentinel v0.5`.

## API esperada

El cliente espera estos endpoints en el mismo origen:

### `GET /api/admin/users`

Devuelve la lista de usuarios. Respuestas aceptadas:

```json
[
  { "id": "u_001", "email": "owner@example.com", "role": "ADMIN",  "created_at": "2025-08-12T10:24:00Z" },
  { "id": "u_002", "email": "viewer@example.com",  "role": "VIEWER", "created_at": "2025-09-03T14:18:00Z" }
]
```

o, alternativamente:

```json
{ "users": [ { "id": "...", "email": "...", "role": "...", "created_at": "..." } ] }
```

Campos por usuario:

| Campo        | Tipo                        | Notas |
| ------------ | --------------------------- | ----- |
| `id`         | string                      | Usado para el endpoint DELETE |
| `email`      | string                      | Mostrado tal cual |
| `role`       | `"ADMIN"` \| `"VIEWER"`     | Mayúsculas; otro valor se trata como VIEWER |
| `created_at` | ISO 8601 string             | Mostrado en formato `YYYY-MM-DD HH:MM` |

### `POST /api/admin/users`

Body:

```json
{ "email": "nuevo@example.com", "role": "VIEWER" }
```

Respuestas:

| Status | Comportamiento del cliente |
| ------ | --------------------------- |
| `2xx`  | Muestra `Usuario agregado. Email de bienvenida enviado.`, recarga la tabla |
| `409`  | Muestra `Ese email ya está registrado.` |
| `4xx`/`5xx` (otros) | Muestra `Error al agregar usuario: <mensaje>`. Si el body es JSON con `{"error":"..."}`, se usa ese texto. |

> El backend es responsable de **enviar el email de bienvenida** al crear
> el usuario. El frontend solo asume que se envió tras un 2xx.

### `DELETE /api/admin/users/{user_id}`

| Status | Comportamiento |
| ------ | -------------- |
| `2xx`  | Recarga la tabla |
| otro   | Muestra error inline |

El cliente pide confirmación con `window.confirm(...)` antes de llamar.

### Manejo global de auth

Aplicado a las 3 llamadas anteriores:

| Status | Comportamiento |
| ------ | -------------- |
| `401`  | `window.location.href = '/auth/login'` |
| `403`  | Reemplaza el contenido por banner `ACCESO DENEGADO — No tienes permisos para acceder a este panel.` |

Todas las llamadas usan `credentials: 'same-origin'` — la auth se asume
basada en cookie de sesión / JWT en cookie HTTP-only. Si el backend usa
header `Authorization: Bearer ...`, hay que inyectarlo en
`apiListUsers`, `apiAddUser`, `apiDeleteUser` (en `admin-app.js`).

## Owner protegido

La constante `OWNER_EMAIL` en `admin-app.js` (`'owner@example.com'`)
es el dueño del sistema. Para esa fila:

- Se muestra el tag `OWNER` junto al email.
- El botón `ELIMINAR` se reemplaza por `— OWNER —`.

> **Importante:** esta es una protección visual. La protección real debe
> estar en el backend — `DELETE /api/admin/users/{owner_id}` debe
> devolver `403` o `409` aunque la haga otro admin.

## Integración

1. Servir `admin.html` y `admin-app.js` bajo la ruta `/admin` (mismo
   origen que la API).
2. Proteger la ruta a nivel de servidor: redirigir a `/auth/login` si no
   hay sesión, devolver `403` si la sesión no es ADMIN. (El frontend
   también respeta estos códigos, pero la primera línea de defensa es el
   servidor.)
3. Verificar que `GET /api/admin/users` devuelve la forma esperada.

### Modo demo

Si `GET /api/admin/users` falla por **error de red** (no 4xx/5xx),
`admin-app.js` cae a un set de 5 usuarios mock para previsualizar el
diseño en hosts estáticos. En producción detrás de la API real este
fallback no se activa. La columna `actualizado HH:MM:SS` añade el sufijo
`· DEMO` cuando está en este modo.

## Personalización rápida

| Cambio                  | Dónde |
| ----------------------- | ----- |
| Email del owner         | `OWNER_EMAIL` en `admin-app.js` |
| Base de la API          | `API_BASE` en `admin-app.js` |
| Versión en el footer    | `Sentinel v0.5` en `admin.html` |
| Paleta / tipografía     | bloque `:root { ... }` en `<style>` de `admin.html` |

## Build

`v0.5` — coherente con `Sentinel Dashboard v0.5`.
