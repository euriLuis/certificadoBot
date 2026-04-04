import os
import re
import asyncio
import random
import httpx
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .canva_client import CanvaClient
from .token_store import TokenStore
from .exceptions import CanvaError, CanvaJobFailedError, CanvaPendingLongError

# Configuración de logging para producción
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "certificador.log"

# Configuramos un logger específico para no afectar la configuración global si se importa en otros módulos
logger = logging.getLogger("Certificador")
logger.setLevel(logging.INFO)

# Evitar duplicados si el logger ya tiene manejadores
if not logger.handlers:
    # Handler para archivo con rotación (10MB por archivo, hasta 5 archivos de backup)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

class Certificador:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_store_path: Optional[str] = None,
        template_real: Optional[str] = None,
        template_pase: Optional[str] = None,
        output_dir_real: Optional[str] = None,
        output_dir_pase: Optional[str] = None,
        load_env: bool = True
    ):
        root_dir = Path(__file__).parent.parent

        if load_env:
            from dotenv import load_dotenv
            env_path = root_dir / ".env"
            if env_path.exists():
                load_dotenv(env_path)

        self.client_id = client_id or os.getenv("CANVA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CANVA_CLIENT_SECRET")
        self.token_store_path = token_store_path or os.getenv("TOKEN_STORE_PATH", str(root_dir / "token_store.json"))

        if not self.client_id or not self.client_secret:
            logger.error("❌ Faltan CANVA_CLIENT_ID o CANVA_CLIENT_SECRET para inicializar el Certificador.")
            raise ValueError("Configuración incompleta: Faltan credenciales de Canva.")

        self.template_real = template_real or os.getenv("TEMPLATE_ID_REAL", "EAG9oQeIKrE")
        self.template_pase = template_pase or os.getenv("TEMPLATE_ID_PASE", "EAG9_4kr7_A")

        self.token_store = TokenStore(self.token_store_path, self.client_id, self.client_secret)

        # Directorios de salida
        self.dir_real = Path(output_dir_real) if output_dir_real else root_dir / "certificados_real"
        self.dir_pase = Path(output_dir_pase) if output_dir_pase else root_dir / "pases_de_fase"
        self.dir_real.mkdir(exist_ok=True, parents=True)
        self.dir_pase.mkdir(exist_ok=True, parents=True)

        # Cliente HTTP persistente
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=10),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )

        # Configuración de Polling
        self.poll_max_wait = int(os.getenv("POLL_MAX_WAIT", "300"))
        self.poll_interval_min = int(os.getenv("POLL_INTERVAL_MIN", "2"))
        self.poll_interval_max = int(os.getenv("POLL_INTERVAL_MAX", "15"))

        logger.info(f"Certificador inicializado. Polling: {self.poll_max_wait}s")

    async def close(self):
        """Cierra el cliente HTTP y libera recursos."""
        await self.http.aclose()
        logger.info("Certificador: Cliente HTTP cerrado.")

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
        request_id: str = None
    ) -> Dict[str, Any]:
        finished_at = self._utc_now_iso()
        elapsed = time.time() - t0

        res = {
            "status": "success" if status == "success" else "failed",
            "tipo": tipo,
            "nombre": nombre,
            "elapsed_s": round(elapsed, 3),
            "canva": {
                "autofill_job_id": autofill_id,
                "design_id": design_id,
                "export_job_id": export_id
            },
            "meta": {
                "started_at": datetime.fromtimestamp(t0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "finished_at": finished_at
            }
        }

        if request_id:
            res["request_id"] = request_id

        if status == "success" and output_path:
            res["output_path"] = str(output_path)
            res["format"] = output_path.suffix.lower().replace(".", "")
            res["result"] = str(output_path)
        elif error:
            res["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
                "details": getattr(error, 'details', None) if hasattr(error, 'details') else None
            }

        return res

    def _safe_filename(self, text: str) -> str:
        """
        Sanitiza una cadena para ser usada de forma segura como nombre de archivo.
        - Elimina caracteres inválidos para Windows/Linux.
        - Normaliza espacios.
        - Trunca la longitud.
        """
        s = re.sub(r'[\\/*?:"<>|]', "", text)
        s = re.sub(r'[\s_-]+', "_", s)
        s = s.strip("_")
        return s[:100]

    async def _get_client(self) -> CanvaClient:
        access = await self.token_store.get_valid_access_token()
        return CanvaClient(access, self.http)

    def _get_fecha_actual(self) -> str:
        hoy = datetime.now()
        dia = hoy.day
        mes = MESES_ES[hoy.month]
        anio = hoy.year
        return f"{dia} de {mes} de {anio}"

    async def _poll_con_backoff(self, client: CanvaClient, job_id: str, tipo_job: str):
        """
        Polling con backoff incremental + jitter para evitar saturación.
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
            elif status == "failed":
                error_msg = f"El trabajo de {tipo_job} falló en Canva."
                reason = job_data.get("error", {}).get("message")
                if reason:
                    error_msg += f" Razón: {reason}"
                logger.error(f"[{job_id}] {error_msg}")
                raise CanvaJobFailedError(error_msg, details=job_data)

            logger.info(f"[{job_id}] Polling {tipo_job} (Intento {intentos}): {status}")

            jitter = random.uniform(0, 1)
            sleep_time = min(current_delay + jitter, self.poll_interval_max)
            await asyncio.sleep(sleep_time)
            current_delay = min(current_delay + 2, self.poll_interval_max)

        error_msg = f"El trabajo de {tipo_job} ({job_id}) está tomando más de {self.poll_max_wait}s."
        raise CanvaPendingLongError(error_msg)

    async def crear_certificado(self, nombre: str, tipo: str, internal_job_id: str = None) -> Dict[str, Any]:
        """
        Ejecuta el pipeline completo de generación de certificado.
        Retorna un diccionario con el contrato de producción.
        """
        t0 = time.time()
        autofill_id = None
        design_id = None
        export_id = None

        tipo_normalized = tipo.lower().strip().replace("-", " ")

        if tipo_normalized == 'real':
            template_id = self.template_real
            cert_tipo_str = "Real"
            output_dir = self.dir_real
            standard_tipo = "real"
        elif tipo_normalized in ('pase de fase', 'pase fase'):
            template_id = self.template_pase
            cert_tipo_str = "Pase de Fase"
            output_dir = self.dir_pase
            standard_tipo = "pase-fase"
        else:
            error_msg = f"Tipo de certificado no válido: '{tipo}'. Use 'real' o 'pase de fase'."
            err = ValueError(error_msg)
            return self._build_response("failed", tipo, nombre, t0, error=err, request_id=internal_job_id)

        logger.info(f"[{internal_job_id or 'N/A'}] PROCESO INICIADO - Trader: {nombre} | Tipo: {cert_tipo_str}")

        try:
            client = await self._get_client()
            fecha = self._get_fecha_actual()

            # 1. Crear Autofill Job
            resp = await client.create_autofill_job(
                brand_template_id=template_id,
                cert_tipo=cert_tipo_str,
                nombre=nombre,
                fecha=fecha
            )
            autofill_id = resp["job"]["id"]

            # 2. Polling Autofill
            job_data = await self._poll_con_backoff(client, autofill_id, "autofill")

            job_result = job_data.get("result", {})
            design = job_result.get("design", {})
            design_id = design.get("id") or job_result.get("design_id") or design.get("design_id")

            if not design_id:
                raise CanvaJobFailedError("No se pudo obtener el Design ID del trabajo completado.")

            # 3. Crear Export Job
            export_resp = await client.create_export_png_job(design_id=design_id)
            export_id = export_resp["job"]["id"]

            # 4. Polling Export
            ext_job_data = await self._poll_con_backoff(client, export_id, "export")
            urls = ext_job_data.get("urls", [])

            if not urls:
                raise CanvaJobFailedError("La exportación fue 'success' pero no devolvió URLs de descarga.")

            download_url = urls[0]

            # 5. Descargar PNG
            safe_trader_name = self._safe_filename(nombre)
            safe_type = self._safe_filename(cert_tipo_str)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            base_filename = f"Certificado_{safe_type}_{safe_trader_name}_{timestamp}"
            png_path = output_dir / f"{base_filename}.png"

            success_download = False
            for attempt in range(3):
                try:
                    async with self.http.stream("GET", download_url, timeout=60) as r:
                        r.raise_for_status()
                        with open(png_path, "wb") as f:
                            async for chunk in r.aiter_bytes():
                                f.write(chunk)

                    if png_path.exists() and png_path.stat().st_size > 1024:
                        success_download = True
                        break
                    else:
                        raise ValueError("Archivo descargado corrupto o demasiado pequeño.")
                except Exception as e:
                    if png_path.exists():
                        os.remove(png_path)
                    await asyncio.sleep(1.5 * (attempt + 1))

            if not success_download:
                raise Exception("Fallo en la descarga tras reintentos.")

            return self._build_response(
                "success", standard_tipo, nombre, t0,
                autofill_id, design_id, export_id,
                output_path=png_path, request_id=internal_job_id
            )

        except Exception as e:
            return self._build_response(
                "failed", standard_tipo if 'standard_tipo' in locals() else tipo,
                nombre, t0, autofill_id, design_id, export_id,
                error=e, request_id=internal_job_id
            )
