# Sentinel Control — Email Templates Handoff

Paquete de implementación para los dos emails transaccionales de Sentinel Control.
Listos para usar con **Resend** desde `noreply@afterlifecapital.co`.

---

## 📦 Contenido del paquete

```
email_handoff/
├── README.md                       ← Este archivo
├── templates/
│   ├── welcome.html                ← Template 1 (bienvenida)
│   └── revoked.html                ← Template 2 (acceso revocado)
├── python/
│   ├── emails.py                   ← Módulo listo para importar
│   └── requirements.txt            ← Dependencias
├── examples/
│   ├── send_welcome.py             ← Ejemplo de envío (welcome)
│   └── send_revoked.py             ← Ejemplo de envío (revoked)
└── preview/
    └── preview.html                ← Vista local de los 2 templates
```

---

## 🚀 Quickstart

```bash
pip install -r python/requirements.txt
export RESEND_API_KEY="re_xxxxxxxx"
python examples/send_welcome.py
```

O desde tu código:

```python
from emails import send_welcome_email, send_access_revoked_email

# Cuando el admin agrega un usuario:
send_welcome_email(email="user@example.com", role="VIEWER")

# Cuando el admin lo elimina:
send_access_revoked_email(email="user@example.com")
```

---

## 📧 Template 1 — Bienvenida (`welcome.html`)

**Cuándo se envía:** cuando el admin agrega un nuevo usuario al panel.

**Asunto sugerido:** `Bienvenido a Sentinel Control / Welcome to Sentinel Control`

**Variables:**

| Variable | Tipo | Descripción |
|---|---|---|
| `{email}` | str | Email del destinatario (también se muestra en el cuerpo) |
| `{role}` | str | `ADMIN` o `VIEWER` |
| `{admin_permissions_es}` | HTML | Fila extra ES si rol = ADMIN. Vacío si VIEWER. |
| `{admin_permissions_en}` | HTML | Fila extra EN si rol = ADMIN. Vacío si VIEWER. |

El módulo `emails.py` rellena estas variables automáticamente — no tenés que armar el HTML a mano.

---

## 📧 Template 2 — Acceso revocado (`revoked.html`)

**Cuándo se envía:** cuando el admin elimina un usuario del panel.

**Asunto sugerido:** `Acceso revocado / Access revoked — Sentinel Control`

**Variables:**

| Variable | Tipo | Descripción |
|---|---|---|
| `{email}` | str | Email del destinatario |

---

## ⚙️ Configuración Resend

```python
# .env
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxx
EMAIL_FROM="Afterlife Capital <noreply@afterlifecapital.co>"
DASHBOARD_URL="https://sentinel.afterlifecapital.co"
```

**Verificación de dominio (Resend):**
1. Login en [resend.com/domains](https://resend.com/domains)
2. Add Domain → `afterlifecapital.co`
3. Configurar registros DNS (SPF, DKIM, DMARC) que indica Resend
4. Esperar verificación (~minutos)
5. Crear API key en [resend.com/api-keys](https://resend.com/api-keys)

---

## 🎨 Decisiones de diseño

- **Layout 100% con `<table>`** — compatibilidad universal (Outlook 2007+, Gmail, Apple Mail, Yahoo, ProtonMail).
- **CSS inline** — sin `<style>` blocks (Gmail los recorta).
- **Sin web fonts** — usa `'Courier New', Courier, monospace`. Las fuentes del dashboard (Share Tech Mono, Orbitron) no funcionan en email; Courier es la mono más cercana visualmente y renderiza idéntica en todos los clientes.
- **Paleta exacta del dashboard:** `#030610` bg, `#00f5ff` cyan, `#ff00d4` magenta, `#ff2060` red, `#ffe000` yellow, `#00ff88` green.
- **Sin `text-shadow`, gradientes, flexbox, grid, clip-path o backdrop-filter** — incompatibles con Outlook.
- **Ancho 600px** — estándar de email.
- **Preheader oculto** bilingüe en cada template.
- **Bilingüe ES → EN** separados por divisor magenta.

---

## 🧪 Testing

**Vista previa local:**
```bash
open preview/preview.html
```
Tiene un toggle ADMIN / VIEWER para ver el welcome con las dos variantes de rol.

**Probar en clientes reales:**
- [Litmus](https://litmus.com) o [Email on Acid](https://www.emailonacid.com) para preview cross-client
- O simplemente envíate un email de prueba: `send_welcome_email("tu@email.com", "ADMIN")`

---

## 🔌 Integración con tu API (FastAPI ejemplo)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from emails import send_welcome_email, send_access_revoked_email

router = APIRouter(prefix="/admin/users", tags=["users"])

class CreateUser(BaseModel):
    email: EmailStr
    role: str  # "ADMIN" | "VIEWER"

@router.post("")
async def create_user(payload: CreateUser):
    if payload.role not in ("ADMIN", "VIEWER"):
        raise HTTPException(400, "role must be ADMIN or VIEWER")
    # ... persistir usuario en DB ...
    send_welcome_email(payload.email, payload.role)
    return {"ok": True}

@router.delete("/{email}")
async def delete_user(email: str):
    # ... eliminar usuario de DB ...
    send_access_revoked_email(email)
    return {"ok": True}
```

---

## 📝 Notas finales

- Los templates son strings con placeholders `{...}` listos para `.format()`.
- No hay otras llaves `{}` en los HTML, así que `.format()` no rompe.
- Si más adelante agregás CSS con `{}`, escapá las llaves duplicándolas: `{{` y `}}`.
- Los emails marcan `noreply@afterlifecapital.co` — configurá rebote/auto-reply para devolver "este buzón no se monitorea".

---

**Footer de los emails:** `Afterlife Capital · Sentinel v0.5 · Correo automático, no responder.`
