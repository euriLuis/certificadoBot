"""
Modulo de envio de correos via Resend.
Encapsula la logica de envio del certificado por email con diseno profesional.
"""

import base64
import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, Optional

import resend

logger = logging.getLogger(__name__)

COLOR_ACCENT = "#19BDF7"
COLOR_DARK = "#070A2D"
MARCA = "Qvafunded"
WEB_URL = "https://www.qvafunded.live"

FRASES = [
    "En trading, la disciplina pesa mas que la prisa.",
    "La paciencia tambien genera ganancias.",
    "Cada operacion bien ejecutada fortalece al trader correcto.",
    "Proteger el capital es parte de avanzar.",
    "La consistencia vale mas que una victoria impulsiva.",
    "Un trader solido piensa primero en el riesgo.",
    "La confianza real nace de un proceso repetible.",
    "El mercado premia la preparacion, no la improvisacion.",
    "Cada fase superada demuestra evolucion mental y tecnica.",
    "La ventaja esta en ejecutar con claridad, no con emocion.",
    "No se trata de operar mas, sino de operar mejor.",
    "Toda gran cuenta se construye con decisiones pequenas y firmes.",
    "La constancia convierte el esfuerzo en resultados.",
    "La mejor operacion muchas veces empieza con esperar.",
    "El progreso en trading se mide en control, no solo en ganancias.",
    "Seguir tu plan tambien es una forma de ganar.",
    "Un buen trader no persigue el mercado: lo entiende.",
    "La precision nace de la practica y la disciplina.",
    "Avanzar de fase es una senal de crecimiento real.",
    "Tu evolucion como trader se construye trade a trade.",
]

TIPO_EMAIL_CONFIG = {
    "real": {
        "label": "Real",
        "asunto": "Certificado pase a Real",
        "mensaje": "Nos complace entregarte tu certificado pase a Real.",
        "reconocimiento": "Este logro refleja tu disciplina, constancia y compromiso con tu desarrollo como trader.",
    },
    "pase de fase": {
        "label": "Pase de Fase",
        "asunto": "Certificado de Pase de Fase",
        "mensaje": "Nos complace entregarte tu certificado de pase de fase.",
        "reconocimiento": "Este avance confirma que estas sosteniendo un proceso consistente y bien ejecutado.",
    },
    "elite": {
        "label": "Elite",
        "asunto": "Certificado Elite Qvafunded",
        "mensaje": "Nos complace entregarte tu certificado Elite.",
        "reconocimiento": "Este reconocimiento distingue un nivel superior de consistencia, criterio y control en tu operativa.",
    },
}


def _obtener_frase_aleatoria() -> str:
    """Selecciona una frase motivacional aleatoria de la lista fija."""
    return random.choice(FRASES)


def _normalizar_tipo_certificado(tipo_certificado: str) -> str:
    tipo = (tipo_certificado or "").lower().strip().replace("-", " ")
    if tipo in ("pase fase", "pase"):
        return "pase de fase"
    return tipo


def _get_tipo_email_config(tipo_certificado: str) -> Dict[str, str]:
    tipo = _normalizar_tipo_certificado(tipo_certificado)
    return TIPO_EMAIL_CONFIG.get(
        tipo,
        {
            "label": tipo_certificado.replace("-", " ").title() or "Certificado",
            "asunto": "Tu certificado de Qvafunded",
            "mensaje": "Nos complace entregarte tu certificado.",
            "reconocimiento": "Gracias por confiar en nuestro proceso.",
        },
    )


def _construir_html(nombre: str, tipo_certificado: str, frase: str) -> str:
    """Construye el HTML del correo con diseno profesional."""
    tipo_config = _get_tipo_email_config(tipo_certificado)
    tipo_label = tipo_config["label"]
    mensaje_principal = tipo_config["mensaje"]
    mensaje_reconocimiento = tipo_config["reconocimiento"]

    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background-color:#EEF4F8; font-family:'Segoe UI', Arial, Helvetica, sans-serif; color:#333333;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#EEF4F8;">
<tr><td align="center" style="padding:28px 12px;">

<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background-color:#FFFFFF; border-radius:14px; overflow:hidden; box-shadow:0 4px 20px rgba(25,189,247,0.12);">

  <tr>
    <td style="background:linear-gradient(135deg, {COLOR_ACCENT} 0%, #0EA5E9 100%); padding:36px 32px 30px 32px; text-align:center;">
      <p style="margin:0 0 2px 0; font-size:32px; font-weight:800; letter-spacing:3px; color:#FFFFFF;">
        {MARCA}
      </p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
        <tr>
          <td style="width:50px; height:3px; background-color:rgba(255,255,255,0.6); border-radius:2px;"></td>
        </tr>
      </table>
      <h1 style="margin:14px 0 0 0; font-size:22px; font-weight:600; color:rgba(255,255,255,0.92); letter-spacing:0.5px;">
        Felicidades
      </h1>
    </td>
  </tr>

  <tr>
    <td style="padding:28px 32px 0 32px;">

      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 20px auto;">
        <tr>
          <td style="background-color:#E8F7FD; border:1px solid {COLOR_ACCENT}; border-radius:20px; padding:6px 20px;">
            <span style="font-size:12px; font-weight:600; color:{COLOR_ACCENT}; letter-spacing:0.5px; text-transform:uppercase;">
              {tipo_label}
            </span>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 14px 0; font-size:16px; color:#333333;">
        Hola <strong style="color:{COLOR_DARK};">{nombre}</strong>,
      </p>

      <p style="margin:0 0 8px 0; font-size:15px; color:#4A4A5A; line-height:1.6;">
        {mensaje_principal}
      </p>

      <p style="margin:0 0 24px 0; font-size:15px; color:#4A4A5A; line-height:1.6;">
        {mensaje_reconocimiento}
      </p>

      <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td style="width:60px; height:3px; background-color:{COLOR_ACCENT}; border-radius:2px;"></td>
        </tr>
      </table>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td style="background:linear-gradient(135deg, #E8F7FD 0%, #F0FBFF 100%); border-radius:10px; padding:20px 24px; border-left:4px solid {COLOR_ACCENT};">
            <p style="margin:0 0 6px 0; font-size:11px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:{COLOR_ACCENT};">
              FRASE DEL DIA
            </p>
            <p style="margin:0; font-size:15px; font-style:italic; color:{COLOR_DARK}; line-height:1.7;">
              &ldquo;{frase}&rdquo;
            </p>
          </td>
        </tr>
      </table>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
        <tr>
          <td style="background-color:#F8FAFB; border-radius:8px; padding:14px 18px; text-align:center;">
            <p style="margin:0; font-size:14px; color:#555555;">
              Tu certificado se encuentra adjunto en este correo.
            </p>
          </td>
        </tr>
      </table>

    </td>
  </tr>

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

  <tr>
    <td style="background-color:{COLOR_DARK}; padding:22px 32px; text-align:center;">
      <p style="margin:0 0 4px 0; font-size:13px; color:rgba(255,255,255,0.7);">
        Enviado por <strong style="color:{COLOR_ACCENT};">{MARCA}</strong>
      </p>
      <p style="margin:0; font-size:11px; color:rgba(255,255,255,0.4);">
        &copy; {MARCA} - Todos los derechos reservados.
      </p>
    </td>
  </tr>

</table>

</td></tr>
</table>

</body>
</html>"""


def _init_resend(api_key: Optional[str] = None) -> None:
    """Inicializa la API key de Resend."""
    key = api_key or os.getenv("RESEND_API_KEY")
    if not key:
        raise RuntimeError("No se encontro RESEND_API_KEY en las variables de entorno.")
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
    Envia el certificado PNG por correo electronico usando Resend.

    Retorna un dict con:
      - success: bool
      - email_id: str (ID del envio devuelto por Resend)
      - error: str (solo si falla)
    """
    try:
        _init_resend(api_key)
    except RuntimeError as e:
        return {"success": False, "email_id": None, "error": str(e)}

    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    try:
        contenido = archivo_png.read_bytes()
        contenido_b64 = base64.b64encode(contenido).decode("utf-8")
    except Exception as e:
        logger.error("Error leyendo archivo PNG para adjuntar: %s", e)
        return {"success": False, "email_id": None, "error": f"No se pudo leer el archivo: {e}"}

    tipo_config = _get_tipo_email_config(tipo_certificado)
    asunto = tipo_config["asunto"]
    frase = _obtener_frase_aleatoria()
    cuerpo_html = _construir_html(nombre_usuario, tipo_certificado, frase)
    tipo_tag_value = _normalizar_tipo_certificado(tipo_certificado).replace(" ", "_")

    tags = [
        {"name": "source", "value": "telegram_bot"},
        {"name": "certificate_type", "value": tipo_tag_value},
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
        logger.info("Correo enviado a %s - email_id: %s", destinatario, email_id)
        return {"success": True, "email_id": email_id, "error": None}
    except Exception as e:
        logger.error("Error enviando correo a %s: %s", destinatario, e)
        return {"success": False, "email_id": None, "error": str(e)}
