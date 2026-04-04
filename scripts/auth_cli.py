import base64
import hashlib
import os
import sys
import secrets
import urllib.parse as up
from pathlib import Path

import asyncio
from dotenv import load_dotenv

# Add parent directory to path to import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.token_store import TokenStore

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

CLIENT_ID = os.getenv("CANVA_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("CANVA_REDIRECT_URI", "")
SCOPES = os.getenv(
    "CANVA_SCOPES",
    "design:content:write design:meta:read design:content:read brandtemplate:content:read brandtemplate:meta:read asset:read asset:write",
)
TOKEN_STORE_PATH = os.getenv("TOKEN_STORE_PATH", "./token_store.json")

AUTH_BASE = "https://www.canva.com/api/oauth/authorize"  # tu URL base (la misma que te da Canva)

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def make_pkce():
    # Canva muestra ejemplo con randomBytes(96) base64url (equivalente) :contentReference[oaicite:14]{index=14}
    verifier = b64url(secrets.token_bytes(96))
    challenge = b64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge

def build_auth_url(client_id: str, redirect_uri: str, scopes: str, challenge: str, state: str) -> str:
    q = {
        "code_challenge_method": "s256",
        "response_type": "code",
        "client_id": client_id,
        "scope": " ".join(scopes.split()),  # espacios
        "code_challenge": challenge,
        "state": state,
    }
    # redirect_uri es opcional si solo tienes 1 configurado, pero lo pongo para que sea explícito :contentReference[oaicite:15]{index=15}
    if redirect_uri:
        q["redirect_uri"] = redirect_uri

    return AUTH_BASE + "?" + up.urlencode(q, quote_via=up.quote)

async def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise SystemExit("Faltan CANVA_CLIENT_ID / CANVA_CLIENT_SECRET en .env")

    verifier, challenge = make_pkce()
    state = b64url(secrets.token_bytes(48))

    auth_url = build_auth_url(CLIENT_ID, REDIRECT_URI, SCOPES, challenge, state)

    print("\n1) Abre este URL y autoriza:\n")
    print(auth_url)
    print("\n2) Cuando Canva te redirija a tu redirect_uri, copia y pega AQUÍ el URL completo:\n")

    redirected = input("Redirected URL: ").strip()
    parsed = up.urlparse(redirected)
    qs = up.parse_qs(parsed.query)

    code = (qs.get("code") or [None])[0]
    returned_state = (qs.get("state") or [None])[0]

    if not code:
        raise SystemExit("No encontré ?code= en el URL pegado.")
    if returned_state and returned_state != state:
        raise SystemExit("STATE no coincide. Abortando (protección CSRF).")

    store = TokenStore(TOKEN_STORE_PATH, CLIENT_ID, CLIENT_SECRET)
    token = await store.exchange_authorization_code(code=code, code_verifier=verifier, redirect_uri=REDIRECT_URI)

    print("\n✅ Tokens guardados en:", TOKEN_STORE_PATH)
    print("expires_in:", token.expires_in, "seconds\n")

if __name__ == "__main__":
    asyncio.run(main())
