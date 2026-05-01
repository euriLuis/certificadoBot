import asyncio
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .canva_client import CanvaClient
from .exceptions import CanvaJobFailedError, CanvaPendingLongError
from .token_store import TokenStore

# Configuracion de logging para produccion
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "certificador.log"

logger = logging.getLogger("Certificador")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

AUTOFILL_FIELD_MAPS = {
    "real": {
        "nombre": "nombre",
        "fecha": "fecha",
    },
    "pase de fase": {
        "nombre": "nombre",
        "fecha": "fecha",
    },
    "elite": {
        "nombre": "Nombre",
        "fecha": "fecha",
    },
}


class Certificador:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_store_path: Optional[str] = None,
        template_real: Optional[str] = None,
        template_pase: Optional[str] = None,
        template_elite: Optional[str] = None,
        output_dir_real: Optional[str] = None,
        output_dir_pase: Optional[str] = None,
        output_dir_elite: Optional[str] = None,
        load_env: bool = True,
    ):
        root_dir = Path(__file__).parent.parent

        if load_env:
            from dotenv import load_dotenv

            env_path = root_dir / ".env"
            if env_path.exists():
                load_dotenv(env_path)

        self.client_id = client_id or os.getenv("CANVA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CANVA_CLIENT_SECRET")
        self.token_store_path = token_store_path or os.getenv(
            "TOKEN_STORE_PATH",
            str(root_dir / "token_store.json"),
        )

        if not self.client_id or not self.client_secret:
            logger.error("Faltan CANVA_CLIENT_ID o CANVA_CLIENT_SECRET para inicializar el Certificador.")
            raise ValueError("Configuracion incompleta: faltan credenciales de Canva.")

        self.template_real = template_real or os.getenv("TEMPLATE_ID_REAL", "EAG9oQeIKrE")
        self.template_pase = template_pase or os.getenv("TEMPLATE_ID_PASE", "EAG9_4kr7_A")
        self.template_elite = template_elite or os.getenv("TEMPLATE_ID_ELITE", "")

        self.token_store = TokenStore(self.token_store_path, self.client_id, self.client_secret)

        self.dir_real = Path(output_dir_real) if output_dir_real else root_dir / "certificados_real"
        self.dir_pase = Path(output_dir_pase) if output_dir_pase else root_dir / "pases_de_fase"
        self.dir_elite = Path(output_dir_elite) if output_dir_elite else root_dir / "certificados_elite"

        self.dir_real.mkdir(exist_ok=True, parents=True)
        self.dir_pase.mkdir(exist_ok=True, parents=True)
        self.dir_elite.mkdir(exist_ok=True, parents=True)

        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=10),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

        self.poll_max_wait = int(os.getenv("POLL_MAX_WAIT", "300"))
        self.poll_interval_min = int(os.getenv("POLL_INTERVAL_MIN", "2"))
        self.poll_interval_max = int(os.getenv("POLL_INTERVAL_MAX", "15"))

        logger.info("Certificador inicializado. Polling maximo: %ss", self.poll_max_wait)

    async def close(self):
        """Cierra el cliente HTTP y libera recursos."""
        await self.http.aclose()
        logger.info("Certificador: cliente HTTP cerrado.")

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _build_response(
        self,
        status: str,
        tipo: str,
        nombre: str,
        t0: float,
        autofill_id: str = None,
        design_id: str = None,
        export_id: str = None,
        output_path: Path = None,
        error: Exception = None,
        request_id: str = None,
    ) -> Dict[str, Any]:
        finished_at = self._utc_now_iso()
        elapsed = time.time() - t0

        response = {
            "status": "success" if status == "success" else "failed",
            "tipo": tipo,
            "nombre": nombre,
            "elapsed_s": round(elapsed, 3),
            "canva": {
                "autofill_job_id": autofill_id,
                "design_id": design_id,
                "export_job_id": export_id,
            },
            "meta": {
                "started_at": datetime.fromtimestamp(t0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "finished_at": finished_at,
            },
        }

        if request_id:
            response["request_id"] = request_id

        if status == "success" and output_path:
            response["output_path"] = str(output_path)
            response["format"] = output_path.suffix.lower().replace(".", "")
            response["result"] = str(output_path)
        elif error:
            response["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
                "details": getattr(error, "details", None),
            }

        return response

    def _safe_filename(self, text: str) -> str:
        """Sanitiza una cadena para usarla como nombre de archivo."""
        sanitized = re.sub(r'[\\/*?:"<>|]', "", text)
        sanitized = re.sub(r"[\s_-]+", "_", sanitized)
        sanitized = sanitized.strip("_")
        return sanitized[:100]

    async def _get_client(self) -> CanvaClient:
        access = await self.token_store.get_valid_access_token()
        return CanvaClient(access, self.http)

    def _get_fecha_actual(self) -> str:
        hoy = datetime.now()
        return f"{hoy.day} de {MESES_ES[hoy.month]} de {hoy.year}"

    def _resolver_tipo_config(self, tipo: str):
        tipo_normalized = tipo.lower().strip().replace("-", " ")

        if tipo_normalized == "real":
            template_id = self.template_real
            cert_tipo_str = "Real"
            output_dir = self.dir_real
            standard_tipo = "real"
            env_name = "TEMPLATE_ID_REAL"
        elif tipo_normalized in ("pase de fase", "pase fase"):
            template_id = self.template_pase
            cert_tipo_str = "Pase de Fase"
            output_dir = self.dir_pase
            standard_tipo = "pase de fase"
            env_name = "TEMPLATE_ID_PASE"
        elif tipo_normalized == "elite":
            template_id = self.template_elite
            cert_tipo_str = "Elite"
            output_dir = self.dir_elite
            standard_tipo = "elite"
            env_name = "TEMPLATE_ID_ELITE"
        else:
            raise ValueError("Tipo de certificado no valido. Usa 'real', 'pase de fase' o 'elite'.")

        if not template_id:
            raise ValueError(f"No se configuro {env_name} para generar certificados de tipo '{standard_tipo}'.")

        return template_id, cert_tipo_str, output_dir, standard_tipo

    def _build_autofill_payload(self, tipo: str, nombre: str, fecha: str):
        """
        Construye el payload autofill usando el mapeo fijo ya validado para cada tipo.
        """
        field_map = AUTOFILL_FIELD_MAPS.get(tipo)
        if not field_map:
            raise ValueError(f"No hay mapeo autofill configurado para el tipo '{tipo}'.")

        data = {
            field_map["nombre"]: {
                "type": "text",
                "text": nombre,
            },
            field_map["fecha"]: {
                "type": "text",
                "text": fecha,
            },
        }

        logger.info("Payload autofill fijo aplicado para tipo %s: %s", tipo, field_map)
        return data

    async def _poll_con_backoff(self, client: CanvaClient, job_id: str, tipo_job: str):
        """
        Polling con backoff incremental + jitter para evitar saturacion.
        """
        start_poll = time.time()
        current_delay = self.poll_interval_min
        intentos = 0

        while (time.time() - start_poll) < self.poll_max_wait:
            intentos += 1

            if tipo_job == "autofill":
                resp_canva = await client.get_autofill_job(job_id)
            else:
                resp_canva = await client.get_export_job(job_id)

            job_data = resp_canva.get("job") or resp_canva
            status = job_data["status"]

            if status == "success":
                return job_data

            if status == "failed":
                error_msg = f"El trabajo de {tipo_job} fallo en Canva."
                reason = job_data.get("error", {}).get("message")
                if reason:
                    error_msg += f" Razon: {reason}"
                logger.error("[%s] %s", job_id, error_msg)
                raise CanvaJobFailedError(error_msg, details=job_data)

            logger.info("[%s] Polling %s (intento %s): %s", job_id, tipo_job, intentos, status)

            jitter = random.uniform(0, 1)
            sleep_time = min(current_delay + jitter, self.poll_interval_max)
            await asyncio.sleep(sleep_time)
            current_delay = min(current_delay + 2, self.poll_interval_max)

        raise CanvaPendingLongError(
            f"El trabajo de {tipo_job} ({job_id}) esta tomando mas de {self.poll_max_wait}s."
        )

    async def crear_certificado(self, nombre: str, tipo: str, internal_job_id: str = None) -> Dict[str, Any]:
        """
        Ejecuta el pipeline completo de generacion de certificado.
        Retorna un diccionario con el contrato de produccion.
        """
        t0 = time.time()
        autofill_id = None
        design_id = None
        export_id = None

        try:
            template_id, cert_tipo_str, output_dir, standard_tipo = self._resolver_tipo_config(tipo)
        except Exception as e:
            return self._build_response("failed", tipo, nombre, t0, error=e, request_id=internal_job_id)

        logger.info(
            "[%s] PROCESO INICIADO - Trader: %s | Tipo: %s",
            internal_job_id or "N/A",
            nombre,
            cert_tipo_str,
        )

        try:
            client = await self._get_client()
            fecha = self._get_fecha_actual()
            autofill_data = self._build_autofill_payload(standard_tipo, nombre, fecha)

            resp = await client.create_autofill_job(
                brand_template_id=template_id,
                data=autofill_data,
                title=f"Certificado {cert_tipo_str} {nombre}",
            )
            autofill_id = resp["job"]["id"]

            job_data = await self._poll_con_backoff(client, autofill_id, "autofill")

            job_result = job_data.get("result", {})
            design = job_result.get("design", {})
            design_id = design.get("id") or job_result.get("design_id") or design.get("design_id")

            if not design_id:
                raise CanvaJobFailedError("No se pudo obtener el design_id del trabajo completado.")

            export_resp = await client.create_export_png_job(design_id=design_id)
            export_id = export_resp["job"]["id"]

            ext_job_data = await self._poll_con_backoff(client, export_id, "export")
            urls = ext_job_data.get("urls", [])

            if not urls:
                raise CanvaJobFailedError("La exportacion fue exitosa, pero no devolvio URLs de descarga.")

            download_url = urls[0]
            safe_trader_name = self._safe_filename(nombre)
            safe_type = self._safe_filename(cert_tipo_str)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"Certificado_{safe_type}_{safe_trader_name}_{timestamp}"
            png_path = output_dir / f"{base_filename}.png"

            success_download = False
            last_download_error = None

            for attempt in range(3):
                try:
                    async with self.http.stream("GET", download_url, timeout=60) as response:
                        response.raise_for_status()
                        with png_path.open("wb") as file_handle:
                            async for chunk in response.aiter_bytes():
                                file_handle.write(chunk)

                    if png_path.exists() and png_path.stat().st_size > 1024:
                        success_download = True
                        break

                    raise ValueError("Archivo descargado corrupto o demasiado pequeno.")
                except Exception as e:
                    last_download_error = e
                    logger.warning(
                        "Fallo descargando certificado (%s/3): %s",
                        attempt + 1,
                        e,
                    )
                    if png_path.exists():
                        png_path.unlink()
                    await asyncio.sleep(1.5 * (attempt + 1))

            if not success_download:
                raise RuntimeError(f"Fallo en la descarga tras reintentos: {last_download_error}")

            return self._build_response(
                "success",
                standard_tipo,
                nombre,
                t0,
                autofill_id,
                design_id,
                export_id,
                output_path=png_path,
                request_id=internal_job_id,
            )

        except Exception as e:
            return self._build_response(
                "failed",
                standard_tipo,
                nombre,
                t0,
                autofill_id,
                design_id,
                export_id,
                error=e,
                request_id=internal_job_id,
            )
