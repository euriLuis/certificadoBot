"""
Bot de Telegram para generacion de certificados.
Punto de entrada principal del bot.
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.certificador import Certificador
from app.email_sender import enviar_certificado_por_email

# ---------------------------------------------------------------------------
# Carga de variables de entorno
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Estados de la conversacion
# ---------------------------------------------------------------------------
ESPERANDO_NOMBRE = 1
ESPERANDO_TIPO = 2
ESPERANDO_EMAIL = 3

CONTEXT_KEYS = ("nombre", "output_path", "tipo_certificado")
TIPOS_VALIDOS = {
    "real": "real",
    "pase": "pase de fase",
    "pase de fase": "pase de fase",
    "pase fase": "pase de fase",
    "elite": "elite",
}
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
MAX_NOMBRE_LEN = 120

# ---------------------------------------------------------------------------
# Logging basico
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_REQUEST_RETRIES = int(os.getenv("TELEGRAM_REQUEST_RETRIES", "3"))
TELEGRAM_RETRY_BASE_DELAY_S = float(os.getenv("TELEGRAM_RETRY_BASE_DELAY_S", "2"))
TELEGRAM_CONNECT_TIMEOUT = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "20"))
TELEGRAM_READ_TIMEOUT = float(os.getenv("TELEGRAM_READ_TIMEOUT", "30"))
TELEGRAM_WRITE_TIMEOUT = float(os.getenv("TELEGRAM_WRITE_TIMEOUT", "30"))
TELEGRAM_POOL_TIMEOUT = float(os.getenv("TELEGRAM_POOL_TIMEOUT", "20"))
TELEGRAM_MEDIA_WRITE_TIMEOUT = float(os.getenv("TELEGRAM_MEDIA_WRITE_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _crear_certificador() -> Certificador:
    """Instancia un Certificador listo para usar."""
    return Certificador()


def _limpiar_contexto_certificado(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Limpia solo las claves del flujo del certificado."""
    for key in CONTEXT_KEYS:
        context.user_data.pop(key, None)


def _normalizar_tipo(tipo_raw: str) -> Optional[str]:
    """Normaliza el tipo ingresado. Retorna el tipo canonico o None si es invalido."""
    limpio = " ".join((tipo_raw or "").strip().lower().split())
    return TIPOS_VALIDOS.get(limpio)


def _normalizar_nombre(nombre_raw: str) -> Optional[str]:
    """Recorta espacios y valida un nombre legible."""
    nombre = " ".join((nombre_raw or "").split())
    if not nombre:
        return None
    if len(nombre) > MAX_NOMBRE_LEN:
        return None
    return nombre


def _email_valido(email: str) -> bool:
    """Validacion razonable de formato de email."""
    return bool(EMAIL_RE.match((email or "").strip()))


def _tipos_disponibles_texto() -> str:
    return "Tipos disponibles:\n- real\n- pase de fase (o pase)\n- elite"


def _texto_mensaje(update: Update) -> str:
    """Extrae texto del mensaje actual o retorna cadena vacia."""
    message = update.effective_message
    return message.text.strip() if message and message.text else ""


async def _ejecutar_operacion_telegram(
    descripcion: str,
    operation: Callable[[], Awaitable[Any]],
):
    """Ejecuta una operacion contra Telegram con reintentos ante fallos transitorios."""
    last_error = None

    for attempt in range(1, TELEGRAM_REQUEST_RETRIES + 1):
        try:
            return await operation()
        except RetryAfter as e:
            last_error = e
            retry_after = float(getattr(e, "retry_after", TELEGRAM_RETRY_BASE_DELAY_S))
            if attempt >= TELEGRAM_REQUEST_RETRIES:
                break
            logger.warning(
                "Telegram pidio esperar antes de %s. Reintentando en %.1fs (%s/%s).",
                descripcion,
                retry_after,
                attempt,
                TELEGRAM_REQUEST_RETRIES,
            )
            await asyncio.sleep(retry_after)
        except (TimedOut, NetworkError) as e:
            last_error = e
            retry_delay = TELEGRAM_RETRY_BASE_DELAY_S * attempt
            if attempt >= TELEGRAM_REQUEST_RETRIES:
                break
            logger.warning(
                "Fallo temporal hablando con Telegram durante %s: %s. Reintentando en %.1fs (%s/%s).",
                descripcion,
                e,
                retry_delay,
                attempt,
                TELEGRAM_REQUEST_RETRIES,
            )
            await asyncio.sleep(retry_delay)
        except TelegramError as e:
            logger.error("Error de Telegram durante %s: %s", descripcion, e, exc_info=True)
            return None
        except Exception as e:
            logger.error("Error inesperado durante %s: %s", descripcion, e, exc_info=True)
            return None

    logger.error(
        "No se pudo completar %s tras %s intentos. Ultimo error: %s",
        descripcion,
        TELEGRAM_REQUEST_RETRIES,
        last_error,
        exc_info=True,
    )
    return None


async def _responder(update: Update, texto: str):
    """Responde al mensaje actual si existe uno utilizable."""
    message = update.effective_message
    if not message:
        logger.warning("No hay effective_message para responder al usuario.")
        return None
    return await _ejecutar_operacion_telegram(
        "enviar mensaje al usuario",
        lambda: message.reply_text(
            texto,
            connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
            read_timeout=TELEGRAM_READ_TIMEOUT,
            write_timeout=TELEGRAM_WRITE_TIMEOUT,
            pool_timeout=TELEGRAM_POOL_TIMEOUT,
        ),
    )


async def _editar_o_responder(update: Update, progreso_msg, texto: str):
    """Intenta editar un mensaje de progreso; si falla, responde con uno nuevo."""
    if progreso_msg is not None:
        result = await _ejecutar_operacion_telegram(
            "editar mensaje de progreso",
            lambda: progreso_msg.edit_text(
                texto,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                read_timeout=TELEGRAM_READ_TIMEOUT,
                write_timeout=TELEGRAM_WRITE_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
            ),
        )
        if result is not None:
            return result
        logger.warning("No se pudo editar el mensaje de progreso; se intentara responder con un mensaje nuevo.")
    return await _responder(update, texto)


async def _enviar_documento(update: Update, output_path: Path, caption: str):
    """Envia un documento a Telegram con reintentos ante fallos de red."""
    message = update.effective_message
    if not message:
        logger.warning("No hay effective_message para enviar documento.")
        return None

    def _build_operation():
        file_handle = output_path.open("rb")

        async def _operation():
            try:
                return await message.reply_document(
                    document=file_handle,
                    filename=output_path.name,
                    caption=caption,
                    connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                    read_timeout=TELEGRAM_READ_TIMEOUT,
                    write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                    pool_timeout=TELEGRAM_POOL_TIMEOUT,
                )
            finally:
                file_handle.close()

        return _operation()

    return await _ejecutar_operacion_telegram(
        f"enviar documento {output_path.name}",
        _build_operation,
    )


def _mensaje_error_generacion(resultado: dict) -> str:
    error_info = resultado.get("error") or {}
    error_msg = error_info.get("message") or "Error desconocido."
    error_type = error_info.get("type") or "Error"
    return f"No se pudo generar el certificado.\n{error_type}: {error_msg}"


# ---------------------------------------------------------------------------
# Handlers de comandos
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los comandos disponibles al usuario."""
    _limpiar_contexto_certificado(context)
    mensaje = (
        "Hola. Soy el bot de certificados de Qvafunded.\n\n"
        "Comandos disponibles:\n"
        "/certificado - Inicia una nueva solicitud\n"
        "/cancel - Cancela la operacion en curso\n\n"
        "Flujo:\n"
        "1. Nombre del trader\n"
        "2. Tipo de certificado\n"
        "3. Email de envio\n\n"
        f"{_tipos_disponibles_texto()}"
    )
    await _responder(update, mensaje)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversacion actual."""
    _limpiar_contexto_certificado(context)
    await _responder(update, "Operacion cancelada. Si necesitas algo mas, usa /certificado.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Handlers del flujo de conversacion
# ---------------------------------------------------------------------------
async def iniciar_certificado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de solicitud de certificado y pide el nombre."""
    _limpiar_contexto_certificado(context)
    await _responder(
        update,
        "Vamos a generar un certificado nuevo.\n\n"
        "Escribe el nombre del trader exactamente como debe aparecer en la plantilla.",
    )
    return ESPERANDO_NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre y pide el tipo de certificado."""
    nombre = _normalizar_nombre(_texto_mensaje(update))
    if nombre is None:
        await _responder(
            update,
            "El nombre no es valido. Verifica que no este vacio y que tenga "
            f"como maximo {MAX_NOMBRE_LEN} caracteres.",
        )
        return ESPERANDO_NOMBRE

    context.user_data["nombre"] = nombre
    await _responder(
        update,
        f"Nombre registrado: {nombre}\n\n"
        "Ahora escribe el tipo de certificado que quieres generar.\n"
        f"{_tipos_disponibles_texto()}",
    )
    return ESPERANDO_TIPO


async def recibir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el tipo, valida, genera el certificado y lo envia al chat."""
    tipo_raw = _texto_mensaje(update)
    if not tipo_raw:
        await _responder(
            update,
            f"Debes escribir un tipo de certificado valido.\n{_tipos_disponibles_texto()}",
        )
        return ESPERANDO_TIPO

    tipo_normalizado = _normalizar_tipo(tipo_raw)
    if tipo_normalizado is None:
        await _responder(
            update,
            f"Tipo no reconocido: {tipo_raw}\n"
            "Usa uno de los tipos soportados.\n"
            f"{_tipos_disponibles_texto()}",
        )
        return ESPERANDO_TIPO

    nombre = context.user_data.get("nombre")
    if not nombre:
        _limpiar_contexto_certificado(context)
        await _responder(update, "Se perdio el estado de la conversacion. Usa /certificado para empezar de nuevo.")
        return ConversationHandler.END

    msg_generando = await _responder(
        update,
        f"Generando certificado de tipo '{tipo_normalizado}' para {nombre}. "
        "Esto puede tardar unos segundos...",
    )
    cert = None

    try:
        cert = _crear_certificador()
        resultado = await cert.crear_certificado(nombre, tipo_normalizado)
    except Exception as e:
        logger.exception("Error inesperado generando certificado")
        _limpiar_contexto_certificado(context)
        await _editar_o_responder(update, msg_generando, f"Ocurrio un error inesperado al generar el certificado.\n{e}")
        return ConversationHandler.END
    finally:
        if cert:
            try:
                await cert.close()
            except Exception:
                logger.warning("No se pudo cerrar limpiamente el Certificador.", exc_info=True)

    if resultado.get("status") != "success":
        _limpiar_contexto_certificado(context)
        await _editar_o_responder(update, msg_generando, _mensaje_error_generacion(resultado))
        return ConversationHandler.END

    output_path = Path(resultado.get("output_path", ""))
    if not output_path.exists():
        _limpiar_contexto_certificado(context)
        await _editar_o_responder(
            update,
            msg_generando,
            "El certificado se genero, pero no se encontro el archivo final en disco. "
            "Revisa la configuracion y vuelve a intentarlo.",
        )
        return ConversationHandler.END

    context.user_data["output_path"] = str(output_path)
    context.user_data["tipo_certificado"] = resultado.get("tipo", tipo_normalizado)

    await _editar_o_responder(
        update,
        msg_generando,
        "Certificado generado correctamente. Intentando enviarlo al chat...",
    )

    document_result = await _enviar_documento(
        update,
        output_path,
        f"Certificado {context.user_data['tipo_certificado']} para {nombre}",
    )
    if document_result is None:
        await _responder(
            update,
            "El certificado se genero correctamente, pero no se pudo adjuntar al chat. "
            f"Ruta local: {output_path}",
        )

    await _responder(
        update,
        "Ahora escribe el email al que deseas enviar el certificado.\n\n"
        "Si quieres cancelar en este punto, usa /cancel.",
    )
    return ESPERANDO_EMAIL


async def recibir_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el email, valida y envia el correo por Resend."""
    email = _texto_mensaje(update)
    if not _email_valido(email):
        await _responder(
            update,
            "Ese email no parece valido. Escribe otro email o usa /cancel.",
        )
        return ESPERANDO_EMAIL

    nombre = context.user_data.get("nombre")
    output_path_raw = context.user_data.get("output_path")
    tipo_certificado = context.user_data.get("tipo_certificado")
    chat_id = update.effective_chat.id if update.effective_chat else None

    if not nombre or not output_path_raw or not tipo_certificado:
        _limpiar_contexto_certificado(context)
        await _responder(update, "Faltan datos de la solicitud. Usa /certificado para comenzar de nuevo.")
        return ConversationHandler.END

    output_path = Path(output_path_raw)
    if not output_path.exists():
        _limpiar_contexto_certificado(context)
        await _responder(
            update,
            "No se encontro el archivo del certificado para enviar por correo. "
            "Usa /certificado para regenerarlo.",
        )
        return ConversationHandler.END

    msg_enviando = await _responder(
        update,
        f"Enviando certificado '{tipo_certificado}' al correo {email}...",
    )

    try:
        resultado_email = enviar_certificado_por_email(
            destinatario=email,
            archivo_png=output_path,
            nombre_usuario=nombre,
            tipo_certificado=tipo_certificado,
            telegram_chat_id=chat_id,
        )
    except Exception as e:
        logger.exception("Error inesperado enviando correo")
        resultado_email = {"success": False, "email_id": None, "error": str(e)}

    if resultado_email.get("success"):
        email_id = resultado_email.get("email_id")
        respuesta = f"Correo enviado correctamente a {email}."
        if email_id:
            respuesta += f"\nID de envio: {email_id}"
        await _editar_o_responder(update, msg_enviando, respuesta)
        await _responder(
            update,
            "Flujo completado. Si necesitas generar otro certificado, usa /certificado.",
        )
        _limpiar_contexto_certificado(context)
        return ConversationHandler.END

    error_msg = resultado_email.get("error") or "Error desconocido."
    await _editar_o_responder(
        update,
        msg_enviando,
        "No se pudo enviar el correo.\n"
        f"Detalle: {error_msg}\n\n"
        "Puedes escribir otro email para reintentar o usar /cancel.\n"
        f"El archivo sigue disponible en: {output_path}",
    )
    return ESPERANDO_EMAIL


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra errores no controlados del dispatcher."""
    logger.exception("Error no controlado en el bot", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        result = await _ejecutar_operacion_telegram(
            "notificar error interno al usuario",
            lambda: update.effective_message.reply_text(
                "Ocurrio un error interno no controlado. "
                "Si el flujo quedo interrumpido, usa /certificado para empezar de nuevo.",
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                read_timeout=TELEGRAM_READ_TIMEOUT,
                write_timeout=TELEGRAM_WRITE_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
            ),
        )
        if result is None:
            logger.warning("No se pudo notificar el error al usuario.")


# ---------------------------------------------------------------------------
# Construccion de la aplicacion
# ---------------------------------------------------------------------------
def build_application() -> Application:
    """Construye y retorna la Application del bot con todos los handlers."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("No se encontro TELEGRAM_BOT_TOKEN en las variables de entorno.")

    app = (
        Application.builder()
        .token(token)
        .concurrent_updates(False)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .media_write_timeout(TELEGRAM_MEDIA_WRITE_TIMEOUT)
        .get_updates_connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .get_updates_read_timeout(TELEGRAM_READ_TIMEOUT)
        .get_updates_write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .get_updates_pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("certificado", iniciar_certificado)],
        states={
            ESPERANDO_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            ESPERANDO_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tipo)],
            ESPERANDO_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_email)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("certificado", iniciar_certificado),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    return app


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def main() -> None:
    """Ejecuta el bot."""
    app = build_application()
    logger.info("Bot de certificados iniciado. Presiona Ctrl+C para detener.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
