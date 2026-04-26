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
