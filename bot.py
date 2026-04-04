"""
Bot de Telegram para generación de certificados.
Punto de entrada principal del bot.
"""

import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.certificador import Certificador
from app.exceptions import CanvaError, CanvaJobFailedError, CanvaPendingLongError
from app.email_sender import enviar_certificado_por_email

# ---------------------------------------------------------------------------
# Carga de variables de entorno
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Estados de la conversación
# ---------------------------------------------------------------------------
ESPERANDO_NOMBRE = 1
ESPERANDO_TIPO = 2
ESPERANDO_EMAIL = 3

# Tipos válidos aceptados (normalización → valor interno)
TIPOS_VALIDOS = {
    "real": "real",
    "pase": "pase de fase",
    "pase de fase": "pase de fase",
    "pase fase": "pase de fase",
}

# Patrón simple de validación de email
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# ---------------------------------------------------------------------------
# Logging básico
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _crear_certificador() -> Certificador:
    """Instancia un Certificador listo para usar."""
    return Certificador()


def _normalizar_tipo(tipo_raw: str) -> str | None:
    """Normaliza el tipo ingresado. Retorna el tipo canónico o None si es inválido."""
    limpio = tipo_raw.strip().lower()
    return TIPOS_VALIDOS.get(limpio)


def _email_valido(email: str) -> bool:
    """Validación razonable de formato de email."""
    return bool(EMAIL_RE.match(email.strip()))


# ---------------------------------------------------------------------------
# Handlers de comandos
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los comandos disponibles al usuario."""
    mensaje = (
        "¡Hola! Soy el bot de certificados. 🎓\n\n"
        "Comandos disponibles:\n"
        "/certificado - Solicitar un nuevo certificado\n"
        "/cancel - Cancelar la operación en curso\n\n"
        "Usa /certificado para comenzar."
    )
    await update.message.reply_text(mensaje)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación actual."""
    await update.message.reply_text("Operación cancelada. Si necesitas algo, usa /certificado.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Handlers del flujo de conversación
# ---------------------------------------------------------------------------
async def iniciar_certificado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de solicitud de certificado y pide el nombre."""
    await update.message.reply_text(
        "Vamos a generar tu certificado. 📝\n\n"
        "Por favor, escribe el **nombre del usuario**:"
    )
    return ESPERANDO_NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre y pide el tipo de certificado."""
    nombre = update.message.text.strip()
    if not nombre:
        await update.message.reply_text("El nombre no puede estar vacío. Por favor, escríbelo de nuevo:")
        return ESPERANDO_NOMBRE

    context.user_data["nombre"] = nombre
    await update.message.reply_text(
        f"Nombre registrado: *{nombre}*\n\n"
        "Ahora escribe el **tipo de certificado**:\n"
        "• `real`\n"
        "• `pase de fase` (o simplemente `pase`)"
    )
    return ESPERANDO_TIPO


async def recibir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el tipo, valida, genera el certificado y lo envía al chat."""
    tipo_raw = update.message.text.strip()
    if not tipo_raw:
        await update.message.reply_text("El tipo no puede estar vacío. Por favor, escríbelo de nuevo:")
        return ESPERANDO_TIPO

    tipo_normalizado = _normalizar_tipo(tipo_raw)
    if tipo_normalizado is None:
        await update.message.reply_text(
            f"Tipo *'{tipo_raw}'* no reconocido.\n"
            "Por favor, responde con uno de estos:\n"
            "• `real`\n"
            "• `pase de fase` (o `pase`)"
        )
        return ESPERANDO_TIPO

    nombre = context.user_data.get("nombre", "desconocido")

    # --- Generación real del certificado ---
    msg_generando = await update.message.reply_text("⏳ Generando certificado, esto puede tardar unos segundos…")

    cert = None
    try:
        cert = _crear_certificador()
        resultado = await cert.crear_certificado(nombre, tipo_normalizado)
    except ValueError as e:
        await msg_generando.edit_text(f"❌ Error de configuración: {e}")
        context.user_data.clear()
        return ConversationHandler.END
    except RuntimeError as e:
        await msg_generando.edit_text(f"❌ Error de autenticación con Canva: {e}")
        context.user_data.clear()
        return ConversationHandler.END
    except CanvaPendingLongError as e:
        await msg_generando.edit_text(
            f"⚠️ El certificado está tardando más de lo esperado en Canva.\n"
            f"Detalle: {e}\n"
            f"Intenta de nuevo en unos minutos."
        )
        context.user_data.clear()
        return ConversationHandler.END
    except CanvaJobFailedError as e:
        await msg_generando.edit_text(
            f"❌ El proceso falló en Canva:\n{e}"
        )
        context.user_data.clear()
        return ConversationHandler.END
    except CanvaError as e:
        await msg_generando.edit_text(
            f"❌ Error comunicándose con Canva:\n{e}"
        )
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await msg_generando.edit_text(
            f"❌ Ocurrió un error inesperado:\n{e}"
        )
        logger.exception("Error inesperado generando certificado")
        context.user_data.clear()
        return ConversationHandler.END
    finally:
        if cert:
            await cert.close()

    # Verificar resultado
    if resultado.get("status") != "success":
        error_info = resultado.get("error", {})
        error_msg = error_info.get("message", "Error desconocido")
        await msg_generando.edit_text(f"❌ No se pudo generar el certificado:\n{error_msg}")
        context.user_data.clear()
        return ConversationHandler.END

    output_path = resultado.get("output_path")
    if not output_path or not Path(output_path).exists():
        await msg_generando.edit_text(
            "❌ El certificado se generó pero no se encontró el archivo en disco."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Guardar datos para el paso de email
    context.user_data["output_path"] = str(output_path)
    context.user_data["tipo_certificado"] = resultado.get("tipo", tipo_normalizado)

    # Actualizar mensaje de progreso
    await msg_generando.edit_text("✅ Certificado generado. Enviando archivo…")

    # Enviar como documento (no como foto)
    try:
        with open(output_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=Path(output_path).name,
                caption=f"🎓 Certificado *{resultado.get('tipo', '')}* para *{nombre}*",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Error enviando documento: {e}")
        await update.message.reply_text(
            f"✅ Certificado generado correctamente, pero no se pudo enviar automáticamente.\n"
            f"Ruta: `{output_path}`",
            parse_mode="Markdown",
        )

    # Pedir email para envío por correo
    await update.message.reply_text(
        "📧 Ahora escribe el **email** al que deseas enviar el certificado.\n\n"
        "Si no deseas enviarlo por correo, escribe `/cancel`."
    )
    return ESPERANDO_EMAIL


async def recibir_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el email, valida, envía el correo por Resend y cierra la conversación."""
    email = update.message.text.strip()

    if not _email_valido(email):
        await update.message.reply_text(
            "Ese formato de email no parece válido. Por favor, escribe un email correcto:"
        )
        return ESPERANDO_EMAIL

    nombre = context.user_data.get("nombre", "desconocido")
    output_path = context.user_data.get("output_path")
    tipo_certificado = context.user_data.get("tipo_certificado", "")
    chat_id = update.effective_chat.id if update.effective_chat else None

    if not output_path or not Path(output_path).exists():
        await update.message.reply_text(
            "❌ No se encontró el archivo del certificado para enviar por correo."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Enviar correo
    msg_enviando = await update.message.reply_text("📤 Enviando certificado por correo…")

    resultado_email = enviar_certificado_por_email(
        destinatario=email,
        archivo_png=Path(output_path),
        nombre_usuario=nombre,
        tipo_certificado=tipo_certificado,
        telegram_chat_id=chat_id,
    )

    if resultado_email["success"]:
        email_id = resultado_email.get("email_id")
        respuesta = f"✅ Correo enviado correctamente a *{email}*."
        if email_id:
            respuesta += f"\nID de envío: `{email_id}`"
        await msg_enviando.edit_text(respuesta, parse_mode="Markdown")
    else:
        error_msg = resultado_email.get("error", "Error desconocido")
        await msg_enviando.edit_text(
            f"❌ No se pudo enviar el correo:\n{error_msg}\n\n"
            f"El certificado está disponible localmente en:\n`{output_path}`",
            parse_mode="Markdown",
        )

    await update.message.reply_text("🎉 ¡Listo! Si necesitas otro, usa /certificado.")

    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Construcción de la aplicación
# ---------------------------------------------------------------------------
def build_application() -> Application:
    """Construye y retorna la Application del bot con todos los handlers."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("No se encontró TELEGRAM_BOT_TOKEN en las variables de entorno.")

    app = Application.builder().token(token).build()

    # Conversación principal
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("certificado", iniciar_certificado)],
        states={
            ESPERANDO_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            ESPERANDO_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tipo)],
            ESPERANDO_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    return app


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def main() -> None:
    """Ejecuta el bot."""
    app = build_application()
    logger.info("🤖 Bot de certificados iniciado. Presiona Ctrl+C para detener.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
