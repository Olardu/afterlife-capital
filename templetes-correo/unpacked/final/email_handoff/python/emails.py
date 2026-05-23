"""
Sentinel Control — Email Service
=================================
Envío de emails transaccionales vía Resend.

Uso:
    from emails import send_welcome_email, send_access_revoked_email

    send_welcome_email(email="user@example.com", role="VIEWER")
    send_access_revoked_email(email="user@example.com")

Variables de entorno requeridas:
    RESEND_API_KEY      API key de Resend (re_xxxxxxxx)
    EMAIL_FROM          (opcional) Default: "Afterlife Capital <noreply@afterlifecapital.co>"
    DASHBOARD_URL       (opcional) Default: "https://sentinel.afterlifecapital.co"
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Literal

import resend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

Role = Literal["ADMIN", "VIEWER"]

EMAIL_FROM = os.getenv(
    "EMAIL_FROM",
    "Afterlife Capital <noreply@afterlifecapital.co>",
)
DASHBOARD_URL = os.getenv(
    "DASHBOARD_URL",
    "https://sentinel.afterlifecapital.co",
)

# Carpeta donde viven los templates HTML (al lado de python/, en ../templates/)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Inicializar API key de Resend (lazy: si no está, el envío falla con mensaje claro)
resend.api_key = os.getenv("RESEND_API_KEY", "")


# ---------------------------------------------------------------------------
# Bloques HTML para permisos extra de ADMIN
# ---------------------------------------------------------------------------

_ADMIN_PERM_ES = (
    '<tr><td style="padding:6px 0;font-family:\'Courier New\',Courier,monospace;'
    'font-size:13px;line-height:1.6;color:#d8e6f5;">'
    '<span style="color:#ff00d4;">›</span>&nbsp; '
    '<b style="color:#ff00d4;letter-spacing:1px;">[ADMIN]</b> '
    'Controlar el sistema (iniciar / detener / ajustar)'
    '</td></tr>'
)

_ADMIN_PERM_EN = (
    '<tr><td style="padding:6px 0;font-family:\'Courier New\',Courier,monospace;'
    'font-size:13px;line-height:1.6;color:#d8e6f5;">'
    '<span style="color:#ff00d4;">›</span>&nbsp; '
    '<b style="color:#ff00d4;letter-spacing:1px;">[ADMIN]</b> '
    'Control the system (start / stop / adjust)'
    '</td></tr>'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_template(name: str) -> str:
    """Lee un template HTML del directorio templates/."""
    path = TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template no encontrado: {path}")
    return path.read_text(encoding="utf-8")


def _ensure_api_key() -> None:
    if not resend.api_key:
        raise RuntimeError(
            "RESEND_API_KEY no configurada. "
            "Definí la variable de entorno o pasale resend.api_key='re_xxxx'."
        )


# ---------------------------------------------------------------------------
# Renderers (devuelven HTML — útil para tests / preview sin enviar)
# ---------------------------------------------------------------------------

def render_welcome_html(email: str, role: Role) -> str:
    """Renderiza el HTML del email de bienvenida sin enviarlo."""
    if role not in ("ADMIN", "VIEWER"):
        raise ValueError(f"role debe ser ADMIN o VIEWER, recibido: {role!r}")

    tpl = _load_template("welcome.html")
    return tpl.format(
        email=email,
        role=role,
        admin_permissions_es=_ADMIN_PERM_ES if role == "ADMIN" else "",
        admin_permissions_en=_ADMIN_PERM_EN if role == "ADMIN" else "",
    )


def render_revoked_html(email: str) -> str:
    """Renderiza el HTML del email de revocación sin enviarlo."""
    tpl = _load_template("revoked.html")
    return tpl.format(email=email)


# ---------------------------------------------------------------------------
# Senders (renderizan + envían vía Resend)
# ---------------------------------------------------------------------------

def send_welcome_email(email: str, role: Role) -> dict:
    """
    Envía el email de bienvenida cuando el admin agrega un usuario.

    Args:
        email: dirección del nuevo usuario.
        role:  "ADMIN" o "VIEWER".

    Returns:
        Respuesta de Resend (dict con `id` del mensaje).

    Raises:
        ValueError: si role inválido.
        RuntimeError: si RESEND_API_KEY no está configurada.
    """
    _ensure_api_key()
    html = render_welcome_html(email, role)

    params: resend.Emails.SendParams = {
        "from": EMAIL_FROM,
        "to": [email],
        "subject": "Bienvenido a Sentinel Control / Welcome to Sentinel Control",
        "html": html,
        "headers": {
            "X-Entity-Ref-ID": f"sentinel-welcome-{email}",
        },
    }

    try:
        result = resend.Emails.send(params)
        logger.info("welcome email sent → %s (role=%s, id=%s)", email, role, result.get("id"))
        return result
    except Exception as exc:
        logger.exception("welcome email failed → %s: %s", email, exc)
        raise


def send_access_revoked_email(email: str) -> dict:
    """
    Envía el email de revocación cuando el admin elimina un usuario.

    Args:
        email: dirección del usuario eliminado.

    Returns:
        Respuesta de Resend.
    """
    _ensure_api_key()
    html = render_revoked_html(email)

    params: resend.Emails.SendParams = {
        "from": EMAIL_FROM,
        "to": [email],
        "subject": "Acceso revocado / Access revoked — Sentinel Control",
        "html": html,
        "headers": {
            "X-Entity-Ref-ID": f"sentinel-revoked-{email}",
        },
    }

    try:
        result = resend.Emails.send(params)
        logger.info("revoked email sent → %s (id=%s)", email, result.get("id"))
        return result
    except Exception as exc:
        logger.exception("revoked email failed → %s: %s", email, exc)
        raise


# ---------------------------------------------------------------------------
# CLI rápido para tests:  python emails.py welcome user@x.com ADMIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 3:
        print("Uso:")
        print("  python emails.py welcome <email> <ADMIN|VIEWER>")
        print("  python emails.py revoked <email>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "welcome":
        if len(sys.argv) != 4:
            print("welcome requiere: <email> <ADMIN|VIEWER>")
            sys.exit(1)
        send_welcome_email(sys.argv[2], sys.argv[3])
    elif cmd == "revoked":
        send_access_revoked_email(sys.argv[2])
    else:
        print(f"Comando desconocido: {cmd}")
        sys.exit(1)
