import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from .observability import metrics

CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_in: int
    obtained_at: int  # unix seconds

    @property
    def expires_at(self) -> int:
        return self.obtained_at + int(self.expires_in)

    def is_expired(self, skew_seconds: int = 60) -> bool:
        # refresh 60s antes por seguridad
        return int(time.time()) >= (self.expires_at - skew_seconds)


import asyncio

class TokenStore:
    def __init__(self, path: str, client_id: str, client_secret: str):
        self.path = path
        self.client_id = client_id
        self.client_secret = client_secret
        self._lock = asyncio.Lock()

    def _basic_auth_header(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("utf-8")

    def load(self) -> Optional[TokenData]:
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            return TokenData(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_in=int(data["expires_in"]),
                obtained_at=int(data["obtained_at"]),
            )
        except Exception:
            return None

    def save(self, token: TokenData) -> None:
        tmp_dict = {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_in": token.expires_in,
            "obtained_at": token.obtained_at,
        }
        
        # Escritura atómica: Guardar en .tmp y renombrar
        tmp_path = self.path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(tmp_dict, f, ensure_ascii=False, indent=2)
            
            # Reemplazar el archivo original de forma atómica
            if os.path.exists(self.path):
                os.replace(tmp_path, self.path)
            else:
                os.rename(tmp_path, self.path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"Error guardando tokens: {e}")

    async def exchange_authorization_code(
        self, code: str, code_verifier: str, redirect_uri: Optional[str] = None
    ) -> TokenData:
        headers = {
            "Authorization": self._basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
        }
        if redirect_uri:
            form["redirect_uri"] = redirect_uri

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(CANVA_TOKEN_URL, headers=headers, data=form)
        r.raise_for_status()
        payload = r.json()

        token = TokenData(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_in=int(payload["expires_in"]),
            obtained_at=int(time.time()),
        )
        self.save(token)
        return token

    async def refresh(self, refresh_token: str) -> TokenData:
        # Los refresh tokens de Canva son de un solo uso.
        # Al refrescar, se invalida el anterior y se recibe uno nuevo.
        headers = {
            "Authorization": self._basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        form = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                r = await client.post(CANVA_TOKEN_URL, headers=headers, data=form)
                r.raise_for_status()
                payload = r.json()
                metrics.increment("token_refresh_success")
            except httpx.HTTPStatusError as e:
                metrics.increment("token_refresh_failed")
                # Si el error es invalid_grant (token revocado o ya usado)
                if e.response.status_code == 400:
                    err_data = e.response.json()
                    if err_data.get("error") == "invalid_grant":
                        raise RuntimeError(
                            "❌ El token de refresco ha expirado o ya no es válido. "
                            "Debes re-autenticarte manualmente ejecutando: scripts/auth_cli.py"
                        ) from e
                raise RuntimeError(f"Error de API al refrescar token: {e}") from e

        token = TokenData(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_in=int(payload["expires_in"]),
            obtained_at=int(time.time()),
        )
        self.save(token)
        return token

    async def get_valid_access_token(self) -> str:
        async with self._lock:
            token = self.load()
            if not token:
                raise RuntimeError(
                    f"No hay tokens. Ejecuta primero auth_cli.py para crear {self.path}"
                )
            if token.is_expired():
                # Al estar dentro del lock, evitamos que múltiples llamadas refresquen al mismo tiempo
                token = await self.refresh(token.refresh_token)
            return token.access_token
