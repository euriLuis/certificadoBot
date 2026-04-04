"""
Módulo de envío de correos vía Resend.
Encapsula la lógica de envío del certificado por email con diseño profesional.
"""

import os
import base64
import random
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import resend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identidad visual
# ---------------------------------------------------------------------------
COLOR_ACCENT = "#19BDF7"     # azul claro — color dominante
COLOR_DARK = "#070A2D"       # oscuro — soporte / contraste
MARCA = "Qvafunded"
WEB_URL = "https://www.qvafunded.live"

# ---------------------------------------------------------------------------
# Frases motivacionales (exactamente 20)
# ---------------------------------------------------------------------------
FRASES = [
    "En trading, la disciplina pesa más que la prisa.",
    "La paciencia también genera ganancias.",
    "Cada operación bien ejecutada fortalece al trader correcto.",
    "Proteger el capital es parte de avanzar.",
    "La consistencia vale más que una victoria impulsiva.",
    "Un trader sólido piensa primero en el riesgo.",
    "La confianza real nace de un proceso repetible.",
    "El mercado premia la preparación, no la improvisación.",
    "Cada fase superada demuestra evolución mental y técnica.",
    "La ventaja está en ejecutar con claridad, no con emoción.",
    "No se trata de operar más, sino de operar mejor.",
    "Toda gran cuenta se construye con decisiones pequeñas y firmes.",
    "La constancia convierte el esfuerzo en resultados.",
    "La mejor operación muchas veces empieza con esperar.",
    "El progreso en trading se mide en control, no solo en ganancias.",
    "Seguir tu plan también es una forma de ganar.",
    "Un buen trader no persigue el mercado: lo entiende.",
    "La precisión nace de la práctica y la disciplina.",
    "Avanzar de fase es una señal de crecimiento real.",
    "Tu evolución como trader se construye trade a trade.",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _obtener_frase_aleatoria() -> str:
    """Selecciona una frase motivacional aleatoria de la lista fija."""
    return random.choice(FRASES)


def _obtener_asunto(tipo_certificado: str) -> str:
    """Devuelve el asunto según el tipo de certificado."""
    tipo = tipo_certificado.lower().strip().replace("-", " ")
    if tipo == "real":
        return "Certificado pase a Real"
    elif tipo in ("pase de fase", "pase fase"):
        return "Certificado de Pase de Fase"
    return "Tu certificado de Qvafunded"


def _obtener_mensaje_principal(tipo_certificado: str) -> str:
    """Devuelve el mensaje principal según el tipo de certificado."""
    tipo = tipo_certificado.lower().strip().replace("-", " ")
    if tipo == "real":
        return "Nos complace entregarte tu certificado pase a Real."
    elif tipo in ("pase de fase", "pase fase"):
        return "Nos complace entregarte tu certificado de pase de fase."
    return "Nos complace entregarte tu certificado."


def _construir_html(
    nombre: str,
    tipo_certificado: str,
    frase: str,
) -> str:
    """Construye el HTML del correo con diseño profesional."""
    mensaje_principal = _obtener_mensaje_principal(tipo_certificado)

    # Badge del tipo de certificado
    tipo_label = tipo_certificado.replace("-", " ").title()

    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background-color:#EEF4F8; font-family: 'Segoe UI', Arial, Helvetica, sans-serif; color:#333333;">

<!-- Contenedor general -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#EEF4F8;">
<tr><td align="center" style="padding:28px 12px;">

<!-- Tarjeta principal -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background-color:#FFFFFF; border-radius:14px; overflow:hidden; box-shadow:0 4px 20px rgba(25,189,247,0.12);">

  <!-- Header con fondo azul claro -->
  <tr>
    <td style="background: linear-gradient(135deg, {COLOR_ACCENT} 0%, #0EA5E9 100%); padding:36px 32px 30px 32px; text-align:center;">
      <!-- Marca grande -->
      <p style="margin:0 0 2px 0; font-size:32px; font-weight:800; letter-spacing:3px; color:#FFFFFF;">
        {MARCA}
      </p>
      <!-- Línea decorativa -->
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
        <tr>
          <td style="width:50px; height:3px; background-color:rgba(255,255,255,0.6); border-radius:2px;"></td>
        </tr>
      </table>
      <!-- Título -->
      <h1 style="margin:14px 0 0 0; font-size:22px; font-weight:600; color:rgba(255,255,255,0.92); letter-spacing:0.5px;">
        ¡Felicidades!
      </h1>
    </td>
  </tr>

  <!-- Cuerpo -->
  <tr>
    <td style="padding:28px 32px 0 32px;">

      <!-- Badge tipo de certificado (centrado) -->
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 20px auto;">
        <tr>
          <td style="background-color:#E8F7FD; border:1px solid {COLOR_ACCENT}; border-radius:20px; padding:6px 20px;">
            <span style="font-size:12px; font-weight:600; color:{COLOR_ACCENT}; letter-spacing:0.5px; text-transform:uppercase;">
              {tipo_label}
            </span>
          </td>
        </tr>
      </table>

      <!-- Saludo personalizado -->
      <p style="margin:0 0 14px 0; font-size:16px; color:#333333;">
        Hola <strong style="color:{COLOR_DARK};">{nombre}</strong>,
      </p>

      <!-- Mensaje principal según tipo -->
      <p style="margin:0 0 8px 0; font-size:15px; color:#4A4A5A; line-height:1.6;">
        {mensaje_principal}
      </p>

      <!-- Texto de reconocimiento -->
      <p style="margin:0 0 24px 0; font-size:15px; color:#4A4A5A; line-height:1.6;">
        Este logro refleja tu disciplina, constancia y compromiso con tu desarrollo como trader.
      </p>

      <!-- Línea decorativa -->
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td style="width:60px; height:3px; background-color:{COLOR_ACCENT}; border-radius:2px;"></td>
        </tr>
      </table>

      <!-- Frase motivacional destacada -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td style="background: linear-gradient(135deg, #E8F7FD 0%, #F0FBFF 100%); border-radius:10px; padding:20px 24px; border-left:4px solid {COLOR_ACCENT};">
            <p style="margin:0 0 6px 0; font-size:11px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:{COLOR_ACCENT};">
              &#9733; FRASE DEL D&Iacute;A
            </p>
            <p style="margin:0; font-size:15px; font-style:italic; color:{COLOR_DARK}; line-height:1.7;">
              &ldquo;{frase}&rdquo;
            </p>
          </td>
        </tr>
      </table>

      <!-- Nota sobre adjunto -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
        <tr>
          <td style="background-color:#F8FAFB; border-radius:8px; padding:14px 18px; text-align:center;">
            <p style="margin:0; font-size:14px; color:#555555;">
              &#128206; Tu certificado se encuentra adjunto en este correo.
            </p>
          </td>
        </tr>
      </table>

    </td>
  </tr>

  <!-- CTA - Sección web -->
  <tr>
    <td style="padding:0 32px 28px 32px; text-align:center;">
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
        <tr>
          <td style="background-color:{COLOR_ACCENT}; border-radius:10px; padding:14px 32px;">
            <a href="{WEB_URL}" target="_blank" style="color:#FFFFFF; font-size:14px; font-weight:700; text-decoration:none; letter-spacing:0.5px;">
              Visita nuestra web &rarr;
            </a>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background-color:{COLOR_DARK}; padding:22px 32px; text-align:center;">
      <p style="margin:0 0 4px 0; font-size:13px; color:rgba(255,255,255,0.7);">
        Enviado por <strong style="color:{COLOR_ACCENT};">{MARCA}</strong>
      </p>
      <p style="margin:0; font-size:11px; color:rgba(255,255,255,0.4);">
        &copy; {MARCA} &mdash; Todos los derechos reservados.
      </p>
    </td>
  </tr>

</table>
<!-- Fin tarjeta principal -->

</td></tr>
</table>
<!-- Fin contenedor general -->

</body>
</html>"""


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------
def _init_resend(api_key: Optional[str] = None) -> None:
    """Inicializa la API key de Resend."""
    key = api_key or os.getenv("RESEND_API_KEY")
    if not key:
        raise RuntimeError("No se encontró RESEND_API_KEY en las variables de entorno.")
    resend.api_key = key


def enviar_certificado_por_email(
    destinatario: str,
    archivo_png: Path,
    nombre_usuario: str,
    tipo_certificado: str,
    telegram_chat_id: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envía el certificado PNG por correo electrónico usando Resend.

    Retorna un dict con:
      - success: bool
      - email_id: str (ID del envío devuelto por Resend)
      - error: str (solo si falla)
    """
    try:
        _init_resend(api_key)
    except RuntimeError as e:
        return {"success": False, "email_id": None, "error": str(e)}

    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    # Leer el archivo PNG y codificarlo en base64
    try:
        contenido = archivo_png.read_bytes()
        contenido_b64 = base64.b64encode(contenido).decode("utf-8")
    except Exception as e:
        logger.error(f"Error leyendo archivo PNG para adjuntar: {e}")
        return {"success": False, "email_id": None, "error": f"No se pudo leer el archivo: {e}"}

    # Asunto dinámico según tipo
    asunto = _obtener_asunto(tipo_certificado)

    # Frase aleatoria
    frase = _obtener_frase_aleatoria()

    # HTML del correo
    cuerpo_html = _construir_html(nombre_usuario, tipo_certificado, frase)

    # Tags de metadatos
    tags = [
        {"name": "source", "value": "telegram_bot"},
        {"name": "certificate_type", "value": tipo_certificado.replace("-", "_")},
    ]
    if telegram_chat_id is not None:
        tags.append({"name": "telegram_chat_id", "value": str(telegram_chat_id)})

    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [destinatario],
        "subject": asunto,
        "html": cuerpo_html,
        "attachments": [
            {
                "content": contenido_b64,
                "filename": archivo_png.name,
            }
        ],
        "tags": tags,
    }

    try:
        resultado = resend.Emails.send(params)
        email_id = resultado.get("id") if isinstance(resultado, dict) else getattr(resultado, "id", None)
        logger.info(f"Correo enviado a {destinatario} — email_id: {email_id}")
        return {"success": True, "email_id": email_id, "error": None}
    except Exception as e:
        logger.error(f"Error enviando correo a {destinatario}: {e}")
        return {"success": False, "email_id": None, "error": str(e)}
