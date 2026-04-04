from typing import Any, Dict
import httpx
import logging
import asyncio
import random
from .exceptions import (
    CanvaError, CanvaAuthError, CanvaRateLimitError, 
    CanvaConfigError, CanvaTransientError
)
from .observability import metrics

logger = logging.getLogger("Certificador.Client")

CANVA_AUTOFILL_URL = "https://api.canva.com/rest/v1/autofills"
CANVA_EXPORTS_URL = "https://api.canva.com/rest/v1/exports"


class CanvaClient:
    def __init__(self, access_token: str, http_client: httpx.AsyncClient):
        self.access_token = access_token
        self.http_client = http_client

    def _headers_json(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _headers_auth(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        max_retries = 3
        base_delay = 2  # segundos
        
        for attempt in range(max_retries + 1):
            try:
                r = await self.http_client.request(method, url, **kwargs)
                
                # Log diagnóstico útil
                logger.debug(f"API Request: {method} {url} | Status: {r.status_code}")
                
                try:
                    data = r.json()
                except Exception:
                    data = {"raw": r.text}

                if r.status_code < 400:
                    return data

                # Categorización de errores
                error_msg = data.get("message") or data.get("error_description") or "Error desconocido de Canva"
                error_code = data.get("error") or data.get("errorCode")
                
                if r.status_code == 401:
                    raise CanvaAuthError(f"Error de Autenticación: {error_msg}", r.status_code, error_code, data)
                elif r.status_code == 403:
                    raise CanvaAuthError(f"Permisos insuficientes: {error_msg}", r.status_code, error_code, data)
                elif r.status_code == 429:
                    metrics.increment("rate_limit_429")
                    retry_after = r.headers.get("Retry-After")
                    try:
                        wait_sec = int(retry_after) if retry_after else None
                    except ValueError:
                        wait_sec = None
                    
                    if attempt < max_retries:
                        # Si no hay Retry-After, usamos backoff incremental
                        sleep_time = wait_sec if wait_sec is not None else (base_delay * (2 ** attempt))
                        jitter = random.uniform(0, 1)
                        final_sleep = sleep_time + jitter
                        logger.warning(f"Rate Limit (429) detectado. Reintentando en {final_sleep:.2f}s... (Intento {attempt+1}/{max_retries})")
                        await asyncio.sleep(final_sleep)
                        continue
                    
                    raise CanvaRateLimitError(f"Rate Limit excedido tras reintentos: {error_msg}", r.status_code, error_code, data, wait_sec)
                
                elif r.status_code == 400:
                    raise CanvaConfigError(f"Error de Solicitud (Cliente): {error_msg}", r.status_code, error_code, data)
                
                elif r.status_code >= 500:
                    if attempt < max_retries:
                        sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
                        logger.warning(f"Error de servidor ({r.status_code}). Reintentando en {sleep_time:.2f}s... (Intento {attempt+1}/{max_retries})")
                        await asyncio.sleep(sleep_time)
                        continue
                    raise CanvaTransientError(f"Error temporal del servidor de Canva tras reintentos: {error_msg}", r.status_code, error_code, data)
                
                else:
                    raise CanvaError(f"API Error: {error_msg}", r.status_code, error_code, data)

            except httpx.TimeoutException:
                if attempt < max_retries:
                    sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
                    logger.warning(f"Timeout en API. Reintentando en {sleep_time:.2f}s... (Intento {attempt+1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue
                raise CanvaTransientError("Timeout en la conexión con la API de Canva tras reintentos", 408)
            
            except httpx.RequestError as e:
                if attempt < max_retries:
                    sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
                    logger.warning(f"Error de red ({type(e).__name__}). Reintentando en {sleep_time:.2f}s... (Intento {attempt+1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue
                raise CanvaTransientError(f"Error de red tras reintentos: {str(e)}")

    async def create_autofill_job(
        self,
        brand_template_id: str,
        cert_tipo: str,
        nombre: str,
        fecha: str
    ) -> Dict[str, Any]:
        payload = {
            "brand_template_id": brand_template_id,
            "title": f"Certificado {cert_tipo} {nombre}",
            "data": {
                "nombre": {"type": "text", "text": nombre},
                "fecha": {"type": "text", "text": fecha},
            },
        }
        return await self._request("POST", CANVA_AUTOFILL_URL, headers=self._headers_json(), json=payload)

    async def get_autofill_job(self, job_id: str) -> Dict[str, Any]:
        url = f"{CANVA_AUTOFILL_URL}/{job_id}"
        return await self._request("GET", url, headers=self._headers_auth())

    async def create_export_png_job(self, design_id: str, width: int = 0, height: int = 0) -> Dict[str, Any]:
        format_spec: Dict[str, Any] = {"type": "png"}
        if width and width > 0:
            format_spec["width"] = width
        if height and height > 0:
            format_spec["height"] = height
        
        payload = {
            "design_id": design_id,
            "format": format_spec
        }
        return await self._request("POST", CANVA_EXPORTS_URL, headers=self._headers_json(), json=payload)

    async def get_export_job(self, export_id: str) -> Dict[str, Any]:
        url = f"{CANVA_EXPORTS_URL}/{export_id}"
        return await self._request("GET", url, headers=self._headers_auth())
