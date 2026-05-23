# email_service.py
# Integración con Resend (https://resend.com) para emails transaccionales.
# Sender autorizado: noreply@afterlifecapital.co (dominio verificado).
#
# Templates HTML provistos por Claude Design (handoff 2026-04-26):
#   - Welcome bilingüe ES/EN con bloque condicional de permisos para ADMIN.
#   - Revoked bilingüe ES/EN.
# Layout 100% con <table> + CSS inline para compatibilidad cross-client
# (Outlook 2007+, Gmail, Apple Mail, Yahoo, ProtonMail). Sin webfonts —
# usa Courier New que renderiza idéntica en todos los clientes.
#
# Las funciones nunca lanzan excepciones hacia el caller — retornan True/False
# y loggean los errores. Un fallo de Resend NO bloquea la creación del usuario
# en DB; el admin puede reenviar manualmente.

import logging
from typing import Optional

import httpx

from config import RESEND_API_KEY

logger = logging.getLogger("sentinel.email")


_RESEND_ENDPOINT  = "https://api.resend.com/emails"
_FROM_ADDRESS     = "Afterlife Capital <noreply@afterlifecapital.co>"
_REQUEST_TIMEOUT  = 10.0   # segundos


# ---------------------------------------------------------------------------
# Bloques HTML para permisos extra de ADMIN — se inyectan en el template
# welcome cuando role == "ADMIN", quedan vacíos para VIEWER.
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
# Templates HTML — strings con placeholders para .format().
# Sin otros `{}` en el HTML (todo el CSS es inline en style="..."), así que
# .format() no rompe.
# ---------------------------------------------------------------------------

_WELCOME_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>Bienvenido a Sentinel Control</title>
</head>
<body style="margin:0;padding:0;background-color:#030610;font-family:'Courier New',Courier,monospace;color:#d8e6f5;-webkit-font-smoothing:antialiased;">
<!-- Preheader -->
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#030610;">
Acceso autorizado a Sentinel Control · Access granted to Sentinel Control
</div>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#030610;">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <!-- Container -->
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#07091a;border:1px solid rgba(0,245,255,0.18);">

        <!-- Brand bar -->
        <tr>
          <td style="padding:18px 28px;border-bottom:1px solid rgba(0,245,255,0.14);background-color:#060a18;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="left" style="font-family:'Courier New',Courier,monospace;font-size:13px;font-weight:bold;letter-spacing:3px;color:#d8e6f5;">
                  AFTER<span style="color:#00f5ff;">LIFE</span> CAPITAL
                </td>
                <td align="right" style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;">
                  SENTINEL · v0.5
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Tag line -->
        <tr>
          <td style="padding:28px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#00f5ff;">
            // ACCESO AUTORIZADO
          </td>
        </tr>

        <!-- Title -->
        <tr>
          <td style="padding:8px 28px 4px 28px;font-family:'Courier New',Courier,monospace;font-size:28px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#00f5ff;">
            BIENVENIDO A
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:28px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#ff00d4;">
            SENTINEL CONTROL
          </td>
        </tr>

        <!-- ES body -->
        <tr>
          <td style="padding:0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            El administrador habilitó tu cuenta para operar el panel de control de Sentinel.
          </td>
        </tr>

        <!-- Credential block ES -->
        <tr>
          <td style="padding:18px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border:1px solid rgba(0,245,255,0.18);">
              <tr>
                <td style="padding:14px 18px;border-bottom:1px solid rgba(0,245,255,0.08);">
                  <div style="font-family:'Courier New',Courier,monospace;font-size:9px;letter-spacing:3px;color:#3a4660;margin-bottom:4px;">CUENTA</div>
                  <div style="font-family:'Courier New',Courier,monospace;font-size:14px;color:#d8e6f5;word-break:break-all;">{email}</div>
                </td>
              </tr>
              <tr>
                <td style="padding:14px 18px;">
                  <div style="font-family:'Courier New',Courier,monospace;font-size:9px;letter-spacing:3px;color:#3a4660;margin-bottom:4px;">ROL ASIGNADO</div>
                  <div style="font-family:'Courier New',Courier,monospace;font-size:14px;font-weight:bold;letter-spacing:2px;color:#00f5ff;">{role}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Permissions ES -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#00f5ff;">
            // PERMISOS DE TU ROL
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td style="padding:6px 0;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;">
                  <span style="color:#00ff88;">›</span>&nbsp; Ver el estado del sistema en tiempo real
                </td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;">
                  <span style="color:#00ff88;">›</span>&nbsp; Monitorear los 9 Sentinels
                </td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;">
                  <span style="color:#00ff88;">›</span>&nbsp; Consultar operaciones ejecutadas
                </td>
              </tr>
              {admin_permissions_es}
            </table>
          </td>
        </tr>

        <!-- Login note ES -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;">
            Ingresa con tu cuenta de Google asociada a <span style="color:#00f5ff;">{email}</span>.
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td align="center" style="padding:28px 28px 8px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background-color:#00f5ff;border:1px solid #00f5ff;">
                  <a href="https://sentinel.afterlifecapital.co" target="_blank" style="display:inline-block;padding:14px 32px;font-family:'Courier New',Courier,monospace;font-size:12px;font-weight:bold;letter-spacing:3px;color:#000000;text-decoration:none;">
                    + ABRIR DASHBOARD
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;word-break:break-all;">
            sentinel.afterlifecapital.co
          </td>
        </tr>

        <!-- Beta notice ES -->
        <tr>
          <td style="padding:0 28px 28px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #ffe000;">
              <tr>
                <td style="padding:12px 16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.6;color:#d8e6f5;">
                  <span style="color:#ffe000;letter-spacing:2px;font-size:10px;">[ BETA ]</span>&nbsp; Estamos en fase de pruebas. Espera nuevas funciones próximamente.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Divider ES / EN -->
        <tr>
          <td style="padding:0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td height="1" style="background-color:rgba(255,0,212,0.18);font-size:0;line-height:0;">&nbsp;</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#ff00d4;">
            // EN ENGLISH
          </td>
        </tr>

        <!-- EN body -->
        <tr>
          <td style="padding:14px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.7;color:#d8e6f5;">
            The administrator has enabled your account on the Sentinel control panel.
          </td>
        </tr>
        <tr>
          <td style="padding:14px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.7;color:#d8e6f5;">
            <span style="color:#6a7a96;">Account:</span> <span style="color:#00f5ff;">{email}</span><br>
            <span style="color:#6a7a96;">Role:</span> <span style="color:#00f5ff;font-weight:bold;letter-spacing:2px;">{role}</span>
          </td>
        </tr>

        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#ff00d4;">
            // ROLE PERMISSIONS
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr><td style="padding:6px 0;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;"><span style="color:#00ff88;">›</span>&nbsp; View real-time system status</td></tr>
              <tr><td style="padding:6px 0;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;"><span style="color:#00ff88;">›</span>&nbsp; Monitor the 9 Sentinels</td></tr>
              <tr><td style="padding:6px 0;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;"><span style="color:#00ff88;">›</span>&nbsp; Review executed operations</td></tr>
              {admin_permissions_en}
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.6;color:#d8e6f5;">
            Sign in with your Google account linked to <span style="color:#00f5ff;">{email}</span>, then open the dashboard at <a href="https://sentinel.afterlifecapital.co" style="color:#00f5ff;text-decoration:none;">sentinel.afterlifecapital.co</a>.
          </td>
        </tr>

        <tr>
          <td style="padding:18px 28px 28px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #ffe000;">
              <tr>
                <td style="padding:12px 16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.6;color:#d8e6f5;">
                  <span style="color:#ffe000;letter-spacing:2px;font-size:10px;">[ BETA ]</span>&nbsp; We're in testing phase. Expect new features soon.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 28px;border-top:1px solid rgba(0,245,255,0.14);background-color:#060a18;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;line-height:1.6;">
            Afterlife Capital · Sentinel v0.5 · Correo automático, no responder.
          </td>
        </tr>

      </table>
      <!-- /Container -->

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;">
        <tr>
          <td align="center" style="padding:14px 8px;font-family:'Courier New',Courier,monospace;font-size:9px;letter-spacing:2px;color:#3a4660;">
            noreply@afterlifecapital.co
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>
</body>
</html>"""


_REVOKED_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>Acceso revocado · Access revoked</title>
</head>
<body style="margin:0;padding:0;background-color:#030610;font-family:'Courier New',Courier,monospace;color:#d8e6f5;-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#030610;">
Tu acceso a Sentinel Control fue revocado · Your access to Sentinel Control has been revoked
</div>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#030610;">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#07091a;border:1px solid rgba(255,32,96,0.28);">

        <!-- Brand bar -->
        <tr>
          <td style="padding:18px 28px;border-bottom:1px solid rgba(255,32,96,0.22);background-color:#060a18;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="left" style="font-family:'Courier New',Courier,monospace;font-size:13px;font-weight:bold;letter-spacing:3px;color:#d8e6f5;">
                  AFTER<span style="color:#00f5ff;">LIFE</span> CAPITAL
                </td>
                <td align="right" style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;">
                  SENTINEL · v0.5
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Tag -->
        <tr>
          <td style="padding:28px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#ff2060;">
            // SESIÓN TERMINADA
          </td>
        </tr>

        <!-- Title -->
        <tr>
          <td style="padding:8px 28px 4px 28px;font-family:'Courier New',Courier,monospace;font-size:28px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#ff2060;">
            ACCESO REVOCADO
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:14px;letter-spacing:2px;color:#6a7a96;">
            ACCESS REVOKED
          </td>
        </tr>

        <!-- Status block -->
        <tr>
          <td style="padding:0 28px 4px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border:1px solid rgba(255,32,96,0.22);">
              <tr>
                <td style="padding:18px;font-family:'Courier New',Courier,monospace;">
                  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td style="font-size:9px;letter-spacing:3px;color:#3a4660;padding-bottom:4px;">ESTADO · STATUS</td>
                    </tr>
                    <tr>
                      <td style="font-size:14px;font-weight:bold;letter-spacing:2px;color:#ff2060;padding-bottom:14px;">
                        ● REVOKED
                      </td>
                    </tr>
                    <tr>
                      <td style="font-size:9px;letter-spacing:3px;color:#3a4660;padding-bottom:4px;">CUENTA · ACCOUNT</td>
                    </tr>
                    <tr>
                      <td style="font-size:13px;color:#d8e6f5;word-break:break-all;">{email}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ES body -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#00f5ff;">
            // ESPAÑOL
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Tu acceso a <span style="color:#00f5ff;">Sentinel Control</span> ha sido revocado por el administrador. A partir de este momento ya no podrás iniciar sesión en el panel.
          </td>
        </tr>
        <tr>
          <td style="padding:14px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #00f5ff;">
              <tr>
                <td style="padding:12px 16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.6;color:#d8e6f5;">
                  Si crees que esto es un error, contacta al administrador.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Divider -->
        <tr>
          <td style="padding:24px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td height="1" style="background-color:rgba(255,0,212,0.18);font-size:0;line-height:0;">&nbsp;</td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- EN -->
        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#ff00d4;">
            // ENGLISH
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Your access to <span style="color:#00f5ff;">Sentinel Control</span> has been revoked by the administrator. You can no longer sign in to the panel.
          </td>
        </tr>
        <tr>
          <td style="padding:14px 28px 28px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #00f5ff;">
              <tr>
                <td style="padding:12px 16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.6;color:#d8e6f5;">
                  If you believe this is a mistake, please contact the administrator.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 28px;border-top:1px solid rgba(255,32,96,0.22);background-color:#060a18;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;line-height:1.6;">
            Afterlife Capital · Sentinel v0.5 · Correo automático, no responder.
          </td>
        </tr>

      </table>

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;">
        <tr>
          <td align="center" style="padding:14px 8px;font-family:'Courier New',Courier,monospace;font-size:9px;letter-spacing:2px;color:#3a4660;">
            noreply@afterlifecapital.co
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_welcome_html(email: str, role: str) -> str:
    return _WELCOME_TEMPLATE.format(
        email                = email,
        role                 = role,
        admin_permissions_es = _ADMIN_PERM_ES if role == "ADMIN" else "",
        admin_permissions_en = _ADMIN_PERM_EN if role == "ADMIN" else "",
    )


def _render_revoked_html(email: str) -> str:
    return _REVOKED_TEMPLATE.format(email=email)


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------

async def _send(
    to_email: str,
    subject:  str,
    html:     str,
    ref_id:   Optional[str] = None,
    reply_to: Optional[str] = None,
    text:     Optional[str] = None,
) -> bool:
    if not RESEND_API_KEY:
        logger.warning(f"RESEND_API_KEY no configurada — email a {to_email} NO enviado.")
        return False

    payload: dict = {
        "from":    _FROM_ADDRESS,
        "to":      [to_email],
        "subject": subject,
        "html":    html,
    }
    if text:
        payload["text"] = text          # fallback texto plano (Resend lo usa en clientes sin HTML)
    if reply_to:
        payload["reply_to"] = reply_to   # Resend acepta reply_to a nivel raíz del payload
    if ref_id:
        payload["headers"] = {"X-Entity-Ref-ID": ref_id}

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
    Envía el email de bienvenida bilingüe ES/EN. role es 'ADMIN' o 'VIEWER';
    cuando es ADMIN se inyecta una fila extra de permisos en cada idioma.
    Retorna True si Resend aceptó el envío (status 200/202), False en error.
    """
    subject = "Bienvenido a Sentinel Control / Welcome to Sentinel Control"
    html    = _render_welcome_html(to_email, role)
    return await _send(to_email, subject, html, ref_id=f"sentinel-welcome-{to_email}")


async def send_removal_email(to_email: str) -> bool:
    """
    Notifica al usuario que su acceso fue revocado (template bilingüe ES/EN).
    No bloquea la eliminación en DB si Resend falla — solo loggea.
    """
    subject = "Acceso revocado / Access revoked — Sentinel Control"
    html    = _render_revoked_html(to_email)
    return await _send(to_email, subject, html, ref_id=f"sentinel-revoked-{to_email}")


# ---------------------------------------------------------------------------
# Period close email (#PERIOD-CLOSE 2026-05-23)
# Notifica a los viewers el cierre anticipado del período de observación y la
# pausa del reporte diario. Texto aprobado por Roman (HANDOFF #2). Solo ES.
# Estilo dark/cyberpunk consistente con welcome/revoked/rotation.
# Sin placeholders dinámicos: el cuerpo es fijo, así que no se usa .format().
# ---------------------------------------------------------------------------

_PERIOD_CLOSE_SUBJECT = "Sentinel — Cierre anticipado del período de prueba"
_PERIOD_CLOSE_REPLY_TO = "***REMOVED-EMAIL***"
_PERIOD_CLOSE_REF_ID = "period-close-2026-05-23"

_PERIOD_CLOSE_TEXT = """Hola,

Te cuento: hoy cierro el período de observación de Sentinel, cuatro días antes de la fecha prevista (era el 27 de mayo).

La razón es honesta: durante las cuatro semanas que estuvo corriendo, el sistema no operó como estaba diseñado. Hubo bugs que limitaron cuánto capital se invirtió realmente, estrategias que generaron pocas operaciones, y errores menores no previstos. Acumular cuatro días más de datos imperfectos no aporta — ya está claro qué hay que mejorar.

El bot sigue corriendo en paper trading (no real, eso está previsto para julio). Pero pausamos el reporte diario que venían recibiendo. Lo retomamos cuando arranquemos el próximo período de observación, esta vez con los arreglos aplicados.

Empezamos hoy una fase de análisis y mejoras. El dashboard sigue accesible en sentinel.afterlifecapital.co por si querés ver el estado.

Si tenés preguntas, respondé este email.

Gracias por seguir el proceso.

Roman Olarte
Afterlife Capital"""

_PERIOD_CLOSE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>Sentinel — Cierre anticipado del período de prueba</title>
</head>
<body style="margin:0;padding:0;background-color:#030610;font-family:'Courier New',Courier,monospace;color:#d8e6f5;-webkit-font-smoothing:antialiased;">
<!-- Preheader -->
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#030610;">
Cierre anticipado del período de prueba · El reporte diario queda en pausa
</div>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#030610;">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <!-- Container -->
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#07091a;border:1px solid rgba(0,245,255,0.18);">

        <!-- Brand bar -->
        <tr>
          <td style="padding:18px 28px;border-bottom:1px solid rgba(0,245,255,0.14);background-color:#060a18;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="left" style="font-family:'Courier New',Courier,monospace;font-size:13px;font-weight:bold;letter-spacing:3px;color:#d8e6f5;">
                  AFTER<span style="color:#00f5ff;">LIFE</span> CAPITAL
                </td>
                <td align="right" style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;">
                  SENTINEL · v0.5
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Tag line -->
        <tr>
          <td style="padding:28px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#00f5ff;">
            // AVISO DEL SISTEMA
          </td>
        </tr>

        <!-- Title -->
        <tr>
          <td style="padding:8px 28px 4px 28px;font-family:'Courier New',Courier,monospace;font-size:26px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#00f5ff;">
            CIERRE ANTICIPADO
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:26px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#ff00d4;">
            DEL PERÍODO DE PRUEBA
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Hola,
          </td>
        </tr>
        <tr>
          <td style="padding:14px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Te cuento: hoy cierro el período de observación de Sentinel, cuatro días antes de la fecha prevista (era el 27 de mayo).
          </td>
        </tr>
        <tr>
          <td style="padding:14px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            La razón es honesta: durante las cuatro semanas que estuvo corriendo, el sistema no operó como estaba diseñado. Hubo bugs que limitaron cuánto capital se invirtió realmente, estrategias que generaron pocas operaciones, y errores menores no previstos. Acumular cuatro días más de datos imperfectos no aporta — ya está claro qué hay que mejorar.
          </td>
        </tr>

        <!-- Highlight: pausa del reporte diario -->
        <tr>
          <td style="padding:20px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #ff00d4;">
              <tr>
                <td style="padding:14px 18px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
                  El bot sigue corriendo en paper trading (no real, eso está previsto para julio). Pero <b style="color:#ff00d4;">pausamos el reporte diario</b> que venían recibiendo. Lo retomamos cuando arranquemos el próximo período de observación, esta vez con los arreglos aplicados.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Empezamos hoy una fase de análisis y mejoras. El dashboard sigue accesible en <span style="color:#00f5ff;">sentinel.afterlifecapital.co</span> por si querés ver el estado.
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td align="center" style="padding:28px 28px 8px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background-color:#00f5ff;border:1px solid #00f5ff;">
                  <a href="https://sentinel.afterlifecapital.co" target="_blank" style="display:inline-block;padding:14px 32px;font-family:'Courier New',Courier,monospace;font-size:12px;font-weight:bold;letter-spacing:3px;color:#000000;text-decoration:none;">
                    + ABRIR DASHBOARD
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;word-break:break-all;">
            sentinel.afterlifecapital.co
          </td>
        </tr>

        <tr>
          <td style="padding:0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Si tenés preguntas, respondé este email.
          </td>
        </tr>
        <tr>
          <td style="padding:14px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:14px;line-height:1.7;color:#d8e6f5;">
            Gracias por seguir el proceso.
          </td>
        </tr>

        <!-- Signature -->
        <tr>
          <td style="padding:24px 28px 4px 28px;font-family:'Courier New',Courier,monospace;font-size:14px;font-weight:bold;letter-spacing:1px;color:#00f5ff;">
            Roman Olarte
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 28px 28px;font-family:'Courier New',Courier,monospace;font-size:12px;letter-spacing:2px;color:#6a7a96;">
            Afterlife Capital
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 28px;border-top:1px solid rgba(0,245,255,0.12);background-color:#060a18;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#3a4660;">
            AFTERLIFE CAPITAL · SENTINEL · PAPER TRADING
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _render_period_close_html() -> str:
    """Devuelve el HTML del email de cierre del período (texto fijo aprobado)."""
    return _PERIOD_CLOSE_HTML


async def send_period_close_email(to_email: str) -> bool:
    """
    Envía el aviso de cierre anticipado del período de observación a un viewer.
    Texto aprobado por Roman (HANDOFF #2 2026-05-23). Reply-To al admin.
    Retorna True si Resend aceptó el envío (200/202), False en error.
    """
    return await _send(
        to_email,
        _PERIOD_CLOSE_SUBJECT,
        _PERIOD_CLOSE_HTML,
        ref_id=_PERIOD_CLOSE_REF_ID,
        reply_to=_PERIOD_CLOSE_REPLY_TO,
        text=_PERIOD_CLOSE_TEXT,
    )


# ---------------------------------------------------------------------------
# Rotation email (#UNIVERSE-SELECTION)
# Notifica al admin que el sistema rotó el ticker de un Sentinel
# automáticamente. Incluye razonamiento de Claude resumido y CTA al detalle
# en /admin (con opción de rollback). Estilo cyberpunk consistente con
# welcome/revoked.
# ---------------------------------------------------------------------------

_ROTATION_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>Rotación ejecutada · Rotation executed</title>
</head>
<body style="margin:0;padding:0;background-color:#030610;font-family:'Courier New',Courier,monospace;color:#d8e6f5;-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#030610;">
{sentinel_codename}: {old_ticker} -> {new_ticker} · Universe Selection rotation
</div>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#030610;">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#07091a;border:1px solid rgba(255,0,212,0.28);">

        <!-- Brand bar -->
        <tr>
          <td style="padding:18px 28px;border-bottom:1px solid rgba(255,0,212,0.22);background-color:#060a18;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="left" style="font-family:'Courier New',Courier,monospace;font-size:13px;font-weight:bold;letter-spacing:3px;color:#d8e6f5;">
                  AFTER<span style="color:#00f5ff;">LIFE</span> CAPITAL
                </td>
                <td align="right" style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;">
                  SENTINEL · v0.5
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Tag -->
        <tr>
          <td style="padding:28px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#ff00d4;">
            // ROTACIÓN AUTOMÁTICA EJECUTADA
          </td>
        </tr>

        <!-- Title -->
        <tr>
          <td style="padding:8px 28px 4px 28px;font-family:'Courier New',Courier,monospace;font-size:24px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#ff00d4;">
            {sentinel_codename}
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:14px;letter-spacing:2px;color:#6a7a96;">
            {trigger_reason_label}
          </td>
        </tr>

        <!-- Rotation block -->
        <tr>
          <td style="padding:0 28px 4px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border:1px solid rgba(0,245,255,0.22);">
              <tr>
                <td style="padding:18px;font-family:'Courier New',Courier,monospace;">
                  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="center" style="font-size:10px;letter-spacing:3px;color:#3a4660;padding-bottom:6px;">TICKER ANTERIOR</td>
                      <td></td>
                      <td align="center" style="font-size:10px;letter-spacing:3px;color:#3a4660;padding-bottom:6px;">TICKER NUEVO</td>
                    </tr>
                    <tr>
                      <td align="center" style="font-size:24px;font-weight:bold;letter-spacing:2px;color:#ff2060;">
                        {old_ticker}
                      </td>
                      <td align="center" style="font-size:18px;color:#00f5ff;padding:0 12px;">
                        →
                      </td>
                      <td align="center" style="font-size:24px;font-weight:bold;letter-spacing:2px;color:#00ff88;">
                        {new_ticker}
                      </td>
                    </tr>
                    <tr>
                      <td align="center" style="font-size:10px;color:#6a7a96;padding-top:10px;">win:{old_winrate} sharpe:{old_sharpe}</td>
                      <td></td>
                      <td align="center" style="font-size:10px;color:#6a7a96;padding-top:10px;">conf:{confidence}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Reasoning -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#00f5ff;">
            // RAZONAMIENTO DE CLAUDE
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #00f5ff;">
              <tr>
                <td style="padding:14px 16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.6;color:#d8e6f5;">
                  {reasoning}
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Cost line -->
        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:11px;color:#6a7a96;letter-spacing:1px;">
            modelo: <span style="color:#d8e6f5;">{model}</span> · costo: <span style="color:#d8e6f5;">${cost_usd}</span> · tokens: <span style="color:#d8e6f5;">{tokens_in}/{tokens_out}</span>
          </td>
        </tr>

        <!-- CTAs -->
        <tr>
          <td align="center" style="padding:24px 28px 8px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background-color:#00f5ff;border:1px solid #00f5ff;">
                  <a href="{detail_url}" target="_blank" style="display:inline-block;padding:12px 26px;font-family:'Courier New',Courier,monospace;font-size:11px;font-weight:bold;letter-spacing:3px;color:#000000;text-decoration:none;">
                    + VER DETALLE
                  </a>
                </td>
                <td style="width:10px;"></td>
                <td style="border:1px solid #ff2060;">
                  <a href="{rollback_url}" target="_blank" style="display:inline-block;padding:12px 26px;font-family:'Courier New',Courier,monospace;font-size:11px;font-weight:bold;letter-spacing:3px;color:#ff2060;text-decoration:none;">
                    × ROLLBACK
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Note -->
        <tr>
          <td style="padding:10px 28px 28px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#0a0e1f;border-left:2px solid #ffe000;">
              <tr>
                <td style="padding:12px 16px;font-family:'Courier New',Courier,monospace;font-size:11px;line-height:1.6;color:#d8e6f5;">
                  <span style="color:#ffe000;letter-spacing:2px;font-size:10px;">[ AUTO ]</span>&nbsp; Esta rotación se ejecutó sin aprobación manual (Modo A). Si algo se ve raro, podés revertirla desde el panel admin.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 28px;border-top:1px solid rgba(255,0,212,0.22);background-color:#060a18;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#6a7a96;line-height:1.6;">
            Afterlife Capital · Sentinel v0.5 · Universe Selection · Correo automático.
          </td>
        </tr>

      </table>

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;">
        <tr>
          <td align="center" style="padding:14px 8px;font-family:'Courier New',Courier,monospace;font-size:9px;letter-spacing:2px;color:#3a4660;">
            noreply@afterlifecapital.co
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>
</body>
</html>"""


_TRIGGER_LABELS = {
    "pre_decay_warning": "Anticipación de decay",
    "decay_confirmed":   "Decay confirmado",
    "manual":            "Solicitud manual",
}


def _fmt(v, *, pct: bool = False, default: str = "n/a") -> str:
    if v is None:
        return default
    try:
        return f"{float(v) * 100:.1f}%" if pct else f"{float(v):.2f}"
    except (TypeError, ValueError):
        return default


def _esc(s) -> str:
    """HTML-escape mínimo defensivo (los templates no permiten inyección por
    diseño pero el reasoning viene de Claude — escapamos por las dudas)."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_rotation_html(decision: dict, dashboard_base: str) -> str:
    return _ROTATION_TEMPLATE.format(
        sentinel_codename     = _esc(decision.get("sentinel_name") or "?"),
        trigger_reason_label  = _esc(_TRIGGER_LABELS.get(
            decision.get("trigger_reason"), decision.get("trigger_reason", "?")
        )),
        old_ticker            = _esc(decision.get("old_ticker") or "?"),
        new_ticker            = _esc(decision.get("new_ticker") or "?"),
        old_winrate           = _fmt(decision.get("old_win_rate"), pct=True),
        old_sharpe            = _fmt(decision.get("old_sharpe_ratio")),
        confidence            = _fmt(decision.get("claude_confidence")),
        reasoning             = _esc(decision.get("claude_reasoning") or "(sin razonamiento)"),
        model                 = _esc(decision.get("claude_model") or "?"),
        cost_usd              = _fmt(decision.get("claude_cost_usd")),
        tokens_in             = decision.get("claude_input_tokens") or 0,
        tokens_out            = decision.get("claude_output_tokens") or 0,
        detail_url            = f"{dashboard_base}/admin#rotations",
        rollback_url          = f"{dashboard_base}/admin#rotations",
    )


async def send_rotation_email(
    *,
    to_email: str,
    decision: dict,
    dashboard_base: str = "https://sentinel.afterlifecapital.co",
) -> bool:
    """
    Notifica al admin sobre una rotación ejecutada (#UNIVERSE-SELECTION).
    decision es el dict retornado por historian.get_rotation_decision().
    No bloquea el flujo: si Resend falla solo loggea.
    """
    sentinel = decision.get("sentinel_name") or "Sentinel"
    new      = decision.get("new_ticker") or "?"
    subject  = f"[ROTATION] {sentinel} → {new} · Sentinel Control"
    html     = _render_rotation_html(decision, dashboard_base)
    ref      = f"sentinel-rotation-{decision.get('decision_id','?')}"
    return await _send(to_email, subject, html, ref_id=ref)



# ---------------------------------------------------------------------------
# Daily Report email (#DAILY-REPORT)
# Reporte diario al cierre del mercado (16:30 ET). Tema claro (sober)
# consistente con data-theme="sober" del dashboard. Bilingue ES/EN.
# ---------------------------------------------------------------------------

_DAILY_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>Reporte Diario - Sentinel Control</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f6f8;font-family:'Courier New',Courier,monospace;color:#1a2030;-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#f5f6f8;">
Reporte diario {date_display} | P&amp;L: {pnl_preview}
</div>

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f5f6f8;">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#ffffff;border:1px solid rgba(20,30,50,0.14);">

        <!-- Brand bar -->
        <tr>
          <td style="padding:18px 28px;border-bottom:1px solid rgba(20,30,50,0.10);background-color:#f8f9fb;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="left" style="font-family:'Courier New',Courier,monospace;font-size:13px;font-weight:bold;letter-spacing:3px;color:#1a2030;">
                  AFTER<span style="color:#1d6fb8;">LIFE</span> CAPITAL
                </td>
                <td align="right" style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#8a94a8;">
                  SENTINEL &middot; v0.5
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Tag line -->
        <tr>
          <td style="padding:28px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#1d6fb8;">
            // REPORTE DIARIO &middot; DAILY REPORT
          </td>
        </tr>

        <!-- Date -->
        <tr>
          <td style="padding:8px 28px 4px 28px;font-family:'Courier New',Courier,monospace;font-size:24px;font-weight:900;letter-spacing:2px;line-height:1.15;color:#1a2030;">
            {date_display}
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:12px;letter-spacing:2px;color:#8a94a8;">
            {day_name_es} &middot; {day_name_en} &nbsp;|&nbsp; SESION 09:30 - 16:00 ET
          </td>
        </tr>

        <!-- Observation countdown -->
        <tr>
          <td style="padding:0 28px 18px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8f9fb;border:1px solid rgba(20,30,50,0.10);">
              <tr>
                <td style="padding:14px 18px;">
                  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="left" style="font-family:'Courier New',Courier,monospace;">
                        <div style="font-size:9px;letter-spacing:3px;color:#8a94a8;margin-bottom:4px;">PERIODO DE OBSERVACION</div>
                        <div style="font-size:13px;color:#5a6478;">28 abr - 27 may 2026</div>
                      </td>
                      <td align="right" style="font-family:'Courier New',Courier,monospace;">
                        <div style="font-size:28px;font-weight:900;letter-spacing:2px;color:#1d6fb8;">{obs_days_left}</div>
                        <div style="font-size:9px;letter-spacing:3px;color:#8a94a8;">DIAS RESTANTES</div>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              <tr>
                <td style="padding:0 18px 14px 18px;">
                  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:rgba(20,30,50,0.07);height:4px;">
                    <tr>
                      <td style="width:{obs_pct}%;background-color:#1d6fb8;height:4px;font-size:0;line-height:0;">&nbsp;</td>
                      <td style="height:4px;font-size:0;line-height:0;">&nbsp;</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Summary block -->
        <tr>
          <td style="padding:0 28px 4px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8f9fb;border:1px solid rgba(20,30,50,0.10);">
              <tr>
                <td style="padding:18px;font-family:'Courier New',Courier,monospace;">
                  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td style="font-size:9px;letter-spacing:3px;color:#8a94a8;padding-bottom:4px;">EQUITY</td>
                      <td style="font-size:9px;letter-spacing:3px;color:#8a94a8;padding-bottom:4px;">P&amp;L DEL DIA</td>
                      <td style="font-size:9px;letter-spacing:3px;color:#8a94a8;padding-bottom:4px;">CASH</td>
                    </tr>
                    <tr>
                      <td style="font-size:18px;font-weight:bold;letter-spacing:1px;color:#1a2030;padding-bottom:14px;">{equity}</td>
                      <td style="font-size:18px;font-weight:bold;letter-spacing:1px;color:{pnl_color};padding-bottom:14px;">{pnl_display}<br><span style="font-size:10px;color:#8a94a8;">{pnl_pct}</span></td>
                      <td style="font-size:18px;font-weight:bold;letter-spacing:1px;color:#1a2030;padding-bottom:14px;">{cash}</td>
                    </tr>
                  </table>
                  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-top:1px solid rgba(20,30,50,0.07);">
                    <tr>
                      <td style="padding-top:14px;font-family:'Courier New',Courier,monospace;">
                        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                          <tr>
                            <td>
                              <div style="font-size:9px;letter-spacing:3px;color:#8a94a8;margin-bottom:4px;">TRADES</div>
                              <div style="font-size:14px;color:#1a2030;"><span style="color:#1d8a52;">{filled_count}</span> filled &middot; <span style="color:#c4334a;">{cancelled_count}</span> cancelled{pending_display}</div>
                            </td>
                            <td>
                              <div style="font-size:9px;letter-spacing:3px;color:#8a94a8;margin-bottom:4px;">POSICIONES</div>
                              <div style="font-size:14px;color:#1a2030;"><span style="color:#1d6fb8;">{positions_count}</span> abiertas</div>
                            </td>
                            <td>
                              <div style="font-size:9px;letter-spacing:3px;color:#8a94a8;margin-bottom:4px;">RIESGO</div>
                              <div style="font-size:14px;color:{risk_color};">&bull; {risk_label} <span style="color:#8a94a8;">({risk_score})</span></div>
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Trades section -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#1d6fb8;">
            // OPERACIONES DEL DIA
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8f9fb;border:1px solid rgba(20,30,50,0.10);">
              <tr style="border-bottom:1px solid rgba(20,30,50,0.10);">
                <td style="padding:10px 12px;font-size:9px;letter-spacing:2px;color:#8a94a8;">HORA</td>
                <td style="padding:10px 8px;font-size:9px;letter-spacing:2px;color:#8a94a8;">TICKER</td>
                <td style="padding:10px 8px;font-size:9px;letter-spacing:2px;color:#8a94a8;">LADO</td>
                <td style="padding:10px 8px;font-size:9px;letter-spacing:2px;color:#8a94a8;text-align:right;">QTY</td>
                <td style="padding:10px 8px;font-size:9px;letter-spacing:2px;color:#8a94a8;text-align:right;">PRECIO</td>
                <td style="padding:10px 12px;font-size:9px;letter-spacing:2px;color:#8a94a8;text-align:center;">STATUS</td>
              </tr>
              {trades_rows_html}
            </table>
          </td>
        </tr>

        <!-- P&L by sentinel -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#8a2db5;">
            // P&amp;L POR SENTINEL
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8f9fb;border:1px solid rgba(20,30,50,0.10);">
              <tr><td style="padding:14px 18px;font-family:'Courier New',Courier,monospace;">{pnl_by_sentinel_html}</td></tr>
            </table>
          </td>
        </tr>

        <!-- Open positions -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#1d6fb8;">
            // POSICIONES ABIERTAS AL CIERRE
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8f9fb;border:1px solid rgba(20,30,50,0.10);">
              <tr><td style="padding:14px 18px;font-family:'Courier New',Courier,monospace;">{positions_html}</td></tr>
            </table>
          </td>
        </tr>

        <!-- The Ear events -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#8a2db5;">
            // THE EAR &middot; EVENTOS MACRO
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;font-family:'Courier New',Courier,monospace;">{ear_events_html}</td>
        </tr>

        <!-- Rotations -->
        <tr>
          <td style="padding:24px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#8a2db5;">
            // UNIVERSE SELECTOR &middot; ROTACIONES
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;font-family:'Courier New',Courier,monospace;">{rotations_html}</td>
        </tr>

        <!-- Divider ES / EN -->
        <tr>
          <td style="padding:24px 28px 0 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
              <tr><td height="1" style="background-color:rgba(138,45,181,0.18);font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:18px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:3px;color:#8a2db5;">
            // IN ENGLISH
          </td>
        </tr>
        <tr>
          <td style="padding:10px 28px 0 28px;font-family:'Courier New',Courier,monospace;font-size:13px;line-height:1.7;color:#1a2030;">{english_summary}</td>
        </tr>

        <!-- CTA -->
        <tr>
          <td align="center" style="padding:24px 28px 8px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background-color:#1d6fb8;">
                  <a href="https://sentinel.afterlifecapital.co" target="_blank" style="display:inline-block;padding:14px 32px;font-family:'Courier New',Courier,monospace;font-size:12px;font-weight:bold;letter-spacing:3px;color:#ffffff;text-decoration:none;">
                    + ABRIR DASHBOARD
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:0 28px 24px 28px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#8a94a8;word-break:break-all;">
            sentinel.afterlifecapital.co
          </td>
        </tr>

        <!-- Paper trading notice -->
        <tr>
          <td style="padding:0 28px 28px 28px;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8f9fb;border-left:3px solid #b8861d;">
              <tr>
                <td style="padding:12px 16px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:1.6;color:#5a6478;">
                  <span style="color:#b8861d;letter-spacing:2px;font-size:10px;font-weight:bold;">[ PAPER TRADING ]</span>&nbsp; Periodo de observacion activo. Sin dinero real en riesgo.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 28px;border-top:1px solid rgba(20,30,50,0.10);background-color:#f8f9fb;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:2px;color:#8a94a8;line-height:1.6;">
            Afterlife Capital &middot; Sentinel v0.5 &middot; Correo automatico, no responder.
          </td>
        </tr>

      </table>

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;">
        <tr>
          <td align="center" style="padding:14px 8px;font-family:'Courier New',Courier,monospace;font-size:9px;letter-spacing:2px;color:#8a94a8;">
            noreply@afterlifecapital.co
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Daily Report -- helper builders
# ---------------------------------------------------------------------------

_DAY_NAMES_ES = {
    0: "LUNES",    1: "MARTES",  2: "MIERCOLES", 3: "JUEVES",
    4: "VIERNES",  5: "SABADO",  6: "DOMINGO",
}
_DAY_NAMES_EN = {
    0: "MONDAY", 1: "TUESDAY",  2: "WEDNESDAY", 3: "THURSDAY",
    4: "FRIDAY", 5: "SATURDAY", 6: "SUNDAY",
}

_SOBER_GREEN = "#1d8a52"
_SOBER_RED   = "#c4334a"
_SOBER_BLUE  = "#1d6fb8"
_SOBER_MAG   = "#8a2db5"
_SOBER_YEL   = "#b8861d"


def _build_trade_row(t: dict) -> str:
    ts_raw = t.get("created_at") or t.get("ts") or ""
    if hasattr(ts_raw, "strftime"):
        hora = ts_raw.strftime("%H:%M")
    else:
        hora = str(ts_raw)[11:16] if len(str(ts_raw)) > 16 else str(ts_raw)[:5] if ts_raw else "—"

    ticker = _esc(t.get("ticker", "?"))
    side   = (t.get("side") or "?").upper()
    qty    = t.get("qty", 0)
    px     = t.get("filled_price") or t.get("px") or 0
    status = (t.get("status") or "?").upper()

    side_color   = _SOBER_GREEN if side == "BUY" else _SOBER_RED
    status_color = _SOBER_GREEN if "FILLED" in status else _SOBER_RED

    try:
        px_str = f"${float(px):,.2f}"
    except (TypeError, ValueError):
        px_str = "—"

    try:
        qty_str = str(int(float(qty)))
    except (TypeError, ValueError):
        qty_str = str(qty)

    return (
        '<tr style="border-bottom:1px solid rgba(20,30,50,0.05);">'
        f'<td style="padding:8px 12px;font-family:\'Courier New\',Courier,monospace;font-size:11px;color:#5a6478;">{hora}</td>'
        f'<td style="padding:8px;font-family:\'Courier New\',Courier,monospace;font-size:11px;color:{_SOBER_BLUE};font-weight:bold;">{ticker}</td>'
        f'<td style="padding:8px;font-family:\'Courier New\',Courier,monospace;font-size:11px;color:{side_color};">{side}</td>'
        f'<td style="padding:8px;font-family:\'Courier New\',Courier,monospace;font-size:11px;text-align:right;color:#1a2030;">{qty_str}</td>'
        f'<td style="padding:8px;font-family:\'Courier New\',Courier,monospace;font-size:11px;text-align:right;color:#1a2030;">{px_str}</td>'
        f'<td style="padding:8px 12px;font-family:\'Courier New\',Courier,monospace;font-size:11px;text-align:center;color:{status_color};">&bull; {status}</td>'
        '</tr>'
    )


def _build_sentinel_pnl_row(name: str, pnl: float, is_last: bool = False) -> str:
    color = _SOBER_GREEN if pnl >= 0 else _SOBER_RED
    sign  = "+" if pnl >= 0 else "-"
    border = "" if is_last else "border-bottom:1px solid rgba(20,30,50,0.05);"
    # Split name: first word is the code (S-2), rest is the name
    parts = name.split(" ", 1)
    code = _esc(parts[0])
    label = _esc(parts[1]) if len(parts) > 1 else ""
    return (
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
        f'font-family:\'Courier New\',Courier,monospace;{border}">'
        f'<span style="color:#1a2030;font-size:13px;">'
        f'<span style="color:{_SOBER_BLUE};">{code}</span> {label}</span>'
        f'<span style="color:{color};font-size:13px;font-weight:bold;">{sign}${abs(pnl):,.2f}</span>'
        f'</div>'
    )


def _build_position_row(p: dict, is_last: bool = False) -> str:
    ticker = _esc(p.get("ticker", "?"))
    qty    = p.get("qty", 0)
    upl    = p.get("unrealized_pl", 0)
    try:
        qty_f   = float(qty)
        qty_str = str(int(qty_f)) if qty_f == int(qty_f) else f"{qty_f:.2f}"
    except (TypeError, ValueError):
        qty_str = str(qty)
    side = "LONG" if float(qty or 0) > 0 else "SHORT"
    upl_f = float(upl or 0)
    upl_color = _SOBER_GREEN if upl_f >= 0 else _SOBER_RED
    upl_sign  = "+" if upl_f >= 0 else ""

    entry = float(p.get("avg_entry", 0) or 0)
    if entry > 0 and qty_f != 0:
        pct = (upl_f / (entry * abs(qty_f))) * 100
        pct_str = f" ({upl_sign}{pct:.2f}%)"
    else:
        pct_str = ""

    border = "" if is_last else "border-bottom:1px solid rgba(20,30,50,0.05);"
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:6px 0;font-family:\'Courier New\',Courier,monospace;{border}">'
        f'<span style="color:{_SOBER_BLUE};font-weight:bold;font-size:13px;">{ticker}</span>'
        f'<span style="color:#1a2030;font-size:12px;">{qty_str} shares &middot; '
        f'<span style="color:{_SOBER_GREEN};">{side}</span></span>'
        f'<span style="color:{upl_color};font-size:13px;">{upl_sign}${abs(upl_f):,.2f}{pct_str}</span>'
        f'</div>'
    )


def _build_ear_event(evt: dict) -> str:
    ts_raw = evt.get("timestamp") or evt.get("created_at") or ""
    if hasattr(ts_raw, "strftime"):
        hora = ts_raw.strftime("%H:%M")
    else:
        hora = str(ts_raw)[11:16] if len(str(ts_raw)) > 16 else "—"

    risk = float(evt.get("risk_score", 0) or 0)
    impact = evt.get("impact", "neutral")
    raw_titles = evt.get("titles") or []
    # titles puede ser lista de strings o lista de dicts con clave "title"
    titles = []
    for t in raw_titles[:2]:
        if isinstance(t, dict):
            titles.append(t.get("title", ""))
        elif isinstance(t, str):
            titles.append(t)
    title_str = ", ".join(titles) if titles else ""

    if impact == "circuit_breaker" or risk > 0.7:
        bar_color = _SOBER_YEL
        risk_color = _SOBER_YEL
    else:
        bar_color = _SOBER_BLUE
        risk_color = _SOBER_GREEN

    desc = _esc(title_str) if title_str else ("Risk elevado" if risk > 0.5 else "Risk normalizado")

    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
        f'style="background-color:#f8f9fb;border-left:3px solid {bar_color};margin-bottom:8px;">'
        f'<tr><td style="padding:14px 16px;font-family:\'Courier New\',Courier,monospace;'
        f'font-size:12px;line-height:1.6;color:#1a2030;">'
        f'<span style="color:{bar_color};letter-spacing:2px;font-size:10px;font-weight:bold;">'
        f'[ {hora} ET ]</span>&nbsp; '
        f'{desc}. Risk: <span style="color:{risk_color};font-weight:bold;">{risk:.2f}</span>'
        f'</td></tr></table>'
    )


def _build_rotation_block(rot: dict) -> str:
    sentinel = _esc(rot.get("sentinel_name", "?"))
    old_t    = _esc(rot.get("old_ticker", "?"))
    new_t    = _esc(rot.get("new_ticker", "?"))
    trigger  = _esc(rot.get("trigger_reason", ""))
    conf     = rot.get("claude_confidence")
    conf_str = f" &middot; conf: {float(conf):.2f}" if conf is not None else ""

    trigger_label = _TRIGGER_LABELS.get(trigger, trigger)

    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
        f'style="background-color:#f8f9fb;border-left:3px solid {_SOBER_MAG};margin-bottom:8px;">'
        f'<tr><td style="padding:14px 16px;font-family:\'Courier New\',Courier,monospace;'
        f'font-size:12px;line-height:1.6;color:#1a2030;">'
        f'<span style="color:{_SOBER_MAG};font-weight:bold;">{sentinel}</span>&nbsp;&nbsp;'
        f'<span style="color:{_SOBER_RED};">{old_t}</span> &rarr; '
        f'<span style="color:{_SOBER_GREEN};">{new_t}</span>&nbsp;&nbsp;'
        f'<span style="color:#8a94a8;">({_esc(trigger_label)}{conf_str})</span>'
        f'</td></tr></table>'
    )


def _render_daily_report_html(data: dict) -> str:
    """
    Renderiza el template del reporte diario con los datos provistos.
    """
    from datetime import date as date_type

    report_date = data.get("date") or date_type.today()
    if isinstance(report_date, str):
        report_date = date_type.fromisoformat(report_date)

    # Observation countdown (28 abr - 27 may 2026)
    obs_end = date_type(2026, 5, 27)
    obs_start = date_type(2026, 4, 28)
    obs_total = (obs_end - obs_start).days
    obs_left  = max(0, (obs_end - report_date).days)
    obs_pct   = max(0, min(100, int(((obs_total - obs_left) / obs_total) * 100)))

    date_display = report_date.strftime("%b %d, %Y").upper()
    weekday = report_date.weekday()

    pnl      = float(data.get("pnl", 0) or 0)
    pnl_pct  = float(data.get("pnl_pct", 0) or 0)
    pnl_sign = "+" if pnl >= 0 else "-"
    pnl_color = _SOBER_GREEN if pnl >= 0 else _SOBER_RED

    risk_score = float(data.get("risk_score", 0) or 0)
    if risk_score > 0.7:
        risk_label, risk_color = "ALTO", _SOBER_RED
    elif risk_score > 0.4:
        risk_label, risk_color = "MEDIO", _SOBER_YEL
    else:
        risk_label, risk_color = "BAJO", _SOBER_GREEN

    equity = float(data.get("equity", 0) or 0)
    cash   = float(data.get("cash", 0) or 0)

    trades = data.get("trades") or []
    if trades:
        trades_rows_html = "\n".join(_build_trade_row(t) for t in trades[:50])
    else:
        trades_rows_html = (
            '<tr><td colspan="6" style="padding:14px 12px;font-family:\'Courier New\','
            'Courier,monospace;font-size:12px;color:#8a94a8;text-align:center;">'
            'Sin operaciones hoy / No trades today</td></tr>'
        )

    pnl_by_sentinel = data.get("pnl_by_sentinel") or []
    if pnl_by_sentinel:
        rows = []
        for i, s in enumerate(pnl_by_sentinel):
            rows.append(_build_sentinel_pnl_row(
                s.get("name", "?"),
                float(s.get("pnl", 0) or 0),
                is_last=(i == len(pnl_by_sentinel) - 1),
            ))
        pnl_by_sentinel_html = "\n".join(rows)
    else:
        pnl_by_sentinel_html = (
            '<div style="padding:6px 0;font-family:\'Courier New\',Courier,monospace;'
            'font-size:12px;color:#8a94a8;">Sin datos / No attribution data</div>'
        )

    positions = data.get("positions") or []
    if positions:
        rows = []
        for i, p in enumerate(positions):
            rows.append(_build_position_row(p, is_last=(i == len(positions) - 1)))
        positions_html = "\n".join(rows)
    else:
        positions_html = (
            '<div style="padding:6px 0;font-family:\'Courier New\',Courier,monospace;'
            'font-size:12px;color:#8a94a8;">Sin posiciones abiertas / No open positions</div>'
        )

    ear_events = data.get("ear_events") or []
    if ear_events:
        ear_events_html = "\n".join(_build_ear_event(e) for e in ear_events[:5])
    else:
        ear_events_html = (
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'style="background-color:#f8f9fb;border-left:3px solid #1d6fb8;">'
            '<tr><td style="padding:14px 16px;font-family:\'Courier New\',Courier,monospace;'
            'font-size:12px;color:#8a94a8;">Sin eventos macro hoy / No macro events today'
            '</td></tr></table>'
        )

    rotations = data.get("rotations") or []
    if rotations:
        rotations_html = "\n".join(_build_rotation_block(r) for r in rotations)
    else:
        rotations_html = (
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'style="background-color:#f8f9fb;border-left:3px solid #8a2db5;">'
            '<tr><td style="padding:14px 16px;font-family:\'Courier New\',Courier,monospace;'
            'font-size:12px;color:#8a94a8;">Sin rotaciones hoy / No rotations today'
            '</td></tr></table>'
        )

    filled    = int(data.get("filled_count", 0) or 0)
    cancelled = int(data.get("cancelled_count", 0) or 0)
    pending   = int(data.get("pending_count", 0) or 0)
    pos_count = int(data.get("positions_count", 0) or 0)
    ear_count = len(ear_events)
    rot_count = len(rotations)

    en_parts = [
        f'Trading session closed. <span style="color:{_SOBER_GREEN};">{filled} filled</span>, '
        f'<span style="color:{_SOBER_RED};">{cancelled} cancelled</span>.',
        f'Daily P&amp;L: <span style="color:{pnl_color};font-weight:bold;">'
        f'{pnl_sign}${abs(pnl):,.2f}</span> ({pnl_sign}{abs(pnl_pct):.3f}%).',
        f'Equity: ${equity:,.2f}.',
        f'{pos_count} open position{"s" if pos_count != 1 else ""} at close.',
    ]
    if ear_count:
        peak = max((float(e.get("risk_score", 0) or 0) for e in ear_events), default=0)
        en_parts.append(
            f'The Ear triggered {ear_count} macro event{"s" if ear_count != 1 else ""} '
            f'(risk peaked at {peak:.2f}).'
        )
    else:
        en_parts.append('No macro events triggered.')
    if rot_count:
        rot_sums = []
        for r in rotations:
            rot_sums.append(
                f'{_esc(r.get("sentinel_name","?"))}: '
                f'{_esc(r.get("old_ticker","?"))} &rarr; {_esc(r.get("new_ticker","?"))}'
            )
        en_parts.append(
            f'{rot_count} rotation{"s" if rot_count != 1 else ""} executed '
            f'({"; ".join(rot_sums)}).'
        )
    else:
        en_parts.append('No rotations executed.')
    en_parts.append(
        f'Observation period: <span style="color:{_SOBER_BLUE};font-weight:bold;">'
        f'{obs_left} days remaining</span>.'
    )
    english_summary = " ".join(en_parts)

    return _DAILY_REPORT_TEMPLATE.format(
        date_display         = date_display,
        day_name_es          = _DAY_NAMES_ES.get(weekday, ""),
        day_name_en          = _DAY_NAMES_EN.get(weekday, ""),
        obs_days_left        = obs_left,
        obs_pct              = obs_pct,
        equity               = f"${equity:,.2f}",
        pnl_display          = f"{pnl_sign}${abs(pnl):,.2f}",
        pnl_pct              = f"{pnl_sign}{abs(pnl_pct):.3f}%",
        pnl_color            = pnl_color,
        pnl_preview          = f"{pnl_sign}${abs(pnl):,.2f}",
        cash                 = f"${cash:,.2f}",
        filled_count         = filled,
        cancelled_count      = cancelled,
        pending_display      = f' &middot; <span style="color:#d4a017;">{pending}</span> pending' if pending > 0 else '',
        positions_count      = pos_count,
        risk_score           = f"{risk_score:.2f}",
        risk_label           = risk_label,
        risk_color           = risk_color,
        trades_rows_html     = trades_rows_html,
        pnl_by_sentinel_html = pnl_by_sentinel_html,
        positions_html       = positions_html,
        ear_events_html      = ear_events_html,
        rotations_html       = rotations_html,
        english_summary      = english_summary,
    )


async def send_daily_report(*, to_email: str, data: dict) -> bool:
    """
    Envia el reporte diario al cierre del mercado.
    data es el dict devuelto por collect_daily_report_data() en api.py.
    """
    report_date = data.get("date", "hoy")
    subject = f"[DAILY] {report_date} | Sentinel Control"
    html    = _render_daily_report_html(data)
    return await _send(to_email, subject, html, ref_id=f"sentinel-daily-{report_date}")
