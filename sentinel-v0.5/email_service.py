# email_service.py
# Integración con Resend (https://resend.com) para emails transaccionales.
# Sender autorizado: noreply@afterlifecapital.co (dominio verificado).
#
# Uso:
#   from email_service import send_welcome_email, send_removal_email
#   await send_welcome_email("nuevo@ejemplo.com", role="VIEWER")
#
# Las funciones nunca lanzan excepciones — retornan True/False y loggean los
# errores. La idea es que un fallo de Resend NO bloquee la creación del
# usuario en DB; el admin puede reenviar manualmente si hace falta.

import logging
from typing import Optional

import httpx

from config import RESEND_API_KEY

logger = logging.getLogger("sentinel.email")


_RESEND_ENDPOINT = "https://api.resend.com/emails"
_FROM_ADDRESS    = "Afterlife Capital <noreply@afterlifecapital.co>"
_DASHBOARD_URL   = "https://sentinel.afterlifecapital.co"
_REQUEST_TIMEOUT = 10.0   # segundos


# ---------------------------------------------------------------------------
# Templates HTML — tablas + inline CSS para compatibilidad con clientes de
# email (Gmail, Outlook, Apple Mail). NO usar flexbox/grid: muchos clientes
# los ignoran o renderean mal.
# ---------------------------------------------------------------------------

def _shared_styles() -> str:
    return (
        "background-color:#030610;color:#eaeefb;"
        "font-family:'Share Tech Mono',ui-monospace,monospace;"
    )


def _welcome_html(to_email: str, role: str) -> str:
    role_color = "#00f5ff" if role == "ADMIN" else "#00ff88"
    role_label = "ADMINISTRADOR" if role == "ADMIN" else "OBSERVADOR"
    return f"""<!doctype html>
<html lang="es"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Bienvenido a SENTINEL CONTROL</title>
</head>
<body style="{_shared_styles()}margin:0;padding:0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:#030610;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0"
             style="max-width:560px;background-color:#0a1220;border:1px solid rgba(0,245,255,0.25);
                    border-radius:6px;">
        <tr><td style="padding:24px 32px 8px 32px;">
          <div style="font-family:'Orbitron',sans-serif;letter-spacing:6px;color:#00f5ff;
                      font-size:14px;font-weight:700;">AFTERLIFE CAPITAL</div>
          <div style="height:1px;background:linear-gradient(90deg,#00f5ff,transparent);
                      margin:12px 0 4px 0;"></div>
        </td></tr>
        <tr><td style="padding:8px 32px 0 32px;">
          <h1 style="font-family:'Orbitron',sans-serif;color:#ff00ff;letter-spacing:3px;
                     font-size:20px;margin:8px 0 4px 0;">+ BIENVENIDO A SENTINEL CONTROL</h1>
          <div style="color:#aab2c8;font-size:12px;letter-spacing:1px;margin-bottom:16px;">
            // ACCESO AUTORIZADO
          </div>
        </td></tr>
        <tr><td style="padding:0 32px 16px 32px;color:#eaeefb;font-size:14px;line-height:1.6;">
          <p style="margin:0 0 14px 0;">Hola <span style="color:#00f5ff;">{to_email}</span>,</p>
          <p style="margin:0 0 14px 0;">
            Tu cuenta fue habilitada en SENTINEL, la plataforma de trading algorítmico de
            Afterlife Capital. Tu rol asignado es:
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0"
                 style="margin:16px 0;">
            <tr><td style="border:1px solid {role_color};color:{role_color};
                          padding:8px 16px;letter-spacing:3px;font-weight:700;
                          font-family:'Orbitron',sans-serif;font-size:13px;">
              {role_label}
            </td></tr>
          </table>
          <p style="margin:0 0 14px 0;">
            Para ingresar usá tu cuenta de Google asociada a este email:
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0"
                 style="margin:16px 0;">
            <tr><td style="background:#00f5ff;border-radius:4px;">
              <a href="{_DASHBOARD_URL}"
                 style="display:inline-block;padding:12px 28px;color:#030610;
                        text-decoration:none;font-family:'Orbitron',sans-serif;
                        font-size:13px;letter-spacing:3px;font-weight:700;">
                ACCEDER AL DASHBOARD
              </a>
            </td></tr>
          </table>
          <p style="margin:14px 0 0 0;color:#aab2c8;font-size:13px;">
            Plataforma privada de trading algorítmico en fase de pruebas. Esperá nuevas
            funciones en próximas versiones.
          </p>
        </td></tr>
        <tr><td style="padding:16px 32px 24px 32px;
                      border-top:1px solid rgba(0,245,255,0.15);
                      color:#5a6280;font-size:11px;letter-spacing:1px;">
          Afterlife Capital &mdash; Sentinel v0.5 &middot; Correo automático, no responder.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _removal_html(to_email: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Acceso revocado a Sentinel</title>
</head>
<body style="{_shared_styles()}margin:0;padding:0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:#030610;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0"
             style="max-width:560px;background-color:#0a1220;
                    border:1px solid rgba(255,68,102,0.35);border-radius:6px;">
        <tr><td style="padding:24px 32px 8px 32px;">
          <div style="font-family:'Orbitron',sans-serif;letter-spacing:6px;color:#00f5ff;
                      font-size:14px;font-weight:700;">AFTERLIFE CAPITAL</div>
          <div style="height:1px;background:linear-gradient(90deg,#ff4466,transparent);
                      margin:12px 0 4px 0;"></div>
        </td></tr>
        <tr><td style="padding:8px 32px 0 32px;">
          <h1 style="font-family:'Orbitron',sans-serif;color:#ff4466;letter-spacing:3px;
                     font-size:20px;margin:8px 0 4px 0;">+ ACCESO REVOCADO</h1>
          <div style="color:#aab2c8;font-size:12px;letter-spacing:1px;margin-bottom:16px;">
            // CUENTA DESHABILITADA
          </div>
        </td></tr>
        <tr><td style="padding:0 32px 16px 32px;color:#eaeefb;font-size:14px;line-height:1.6;">
          <p style="margin:0 0 14px 0;">Hola <span style="color:#00f5ff;">{to_email}</span>,</p>
          <p style="margin:0 0 14px 0;">
            Tu acceso a Sentinel Control fue revocado por el administrador. Si creés
            que es un error, contactanos respondiendo al admin que te dio acceso
            originalmente.
          </p>
        </td></tr>
        <tr><td style="padding:16px 32px 24px 32px;
                      border-top:1px solid rgba(255,68,102,0.2);
                      color:#5a6280;font-size:11px;letter-spacing:1px;">
          Afterlife Capital &mdash; Sentinel v0.5 &middot; Correo automático, no responder.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------

async def _send(to_email: str, subject: str, html: str) -> bool:
    if not RESEND_API_KEY:
        logger.warning(f"RESEND_API_KEY no configurada — email a {to_email} NO enviado.")
        return False

    payload = {
        "from":    _FROM_ADDRESS,
        "to":      [to_email],
        "subject": subject,
        "html":    html,
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type":  "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            r = await client.post(_RESEND_ENDPOINT, json=payload, headers=headers)
        if r.status_code in (200, 202):
            data = _safe_json(r)
            logger.info(f"Email enviado a {to_email} | id={data.get('id') if data else '?'}")
            return True
        logger.error(
            f"Resend rechazó el email a {to_email}: {r.status_code} {r.text[:200]}"
        )
        return False
    except Exception as e:
        logger.error(f"Error al enviar email a {to_email}: {e}")
        return False


def _safe_json(response) -> Optional[dict]:
    try:
        return response.json()
    except Exception:
        return None


async def send_welcome_email(to_email: str, role: str) -> bool:
    """
    Envía el email de bienvenida. role es 'ADMIN' o 'VIEWER'. Retorna True
    si Resend aceptó el envío (status 200/202), False en cualquier error.
    """
    subject = "Bienvenido a SENTINEL CONTROL — acceso autorizado"
    return await _send(to_email, subject, _welcome_html(to_email, role))


async def send_removal_email(to_email: str) -> bool:
    """
    Notifica al usuario que su acceso fue revocado. No bloquea la eliminación
    en DB si Resend falla — solo loggea.
    """
    subject = "Acceso a SENTINEL CONTROL revocado"
    return await _send(to_email, subject, _removal_html(to_email))
