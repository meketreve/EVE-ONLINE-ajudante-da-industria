import base64
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Client ID da aplicação EVE registrada pelo projeto (fluxo PKCE, sem secret).
# Em PKCE o Client ID é público — pode ficar no código. Com ele preenchido,
# o usuário final não precisa criar aplicação nem arquivo .env.
# Registre em https://developers.eveonline.com com callback
# http://localhost:8765/auth/callback e os escopos de SSO_SCOPES.
DEFAULT_EVE_CLIENT_ID = "bba140b640f546e38673d56ef5f171f2"

APP_PORT = 8765

_SECRET_KEY_FILE = Path(".secret_key")


def _load_or_create_secret_key() -> str:
    """Usa SECRET_KEY do .env; senão gera uma chave aleatória e guarda em disco."""
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key
    try:
        if _SECRET_KEY_FILE.exists():
            key = _SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if key:
                return key
        key = secrets.token_urlsafe(48)
        _SECRET_KEY_FILE.write_text(key, encoding="utf-8")
        return key
    except OSError:
        return secrets.token_urlsafe(48)


class Settings:
    EVE_CLIENT_ID: str = os.getenv("EVE_CLIENT_ID") or DEFAULT_EVE_CLIENT_ID
    # Opcional: só necessário para quem usa a própria aplicação no modo "confidential"
    EVE_CLIENT_SECRET: str = os.getenv("EVE_CLIENT_SECRET", "")
    EVE_CALLBACK_URL: str = os.getenv(
        "EVE_CALLBACK_URL", f"http://localhost:{APP_PORT}/auth/callback"
    )
    SECRET_KEY: str = _load_or_create_secret_key()

    ESI_BASE_URL: str = "https://esi.evetech.net/latest"
    SSO_BASE_URL: str = "https://login.eveonline.com"

    DATABASE_URL: str = "sqlite+aiosqlite:///./database.db"

    # EVE SSO scopes required
    SSO_SCOPES: str = (
        "esi-skills.read_skills.v1 "
        "esi-characters.read_blueprints.v1 "
        "esi-markets.structure_markets.v1 "
        "esi-universe.read_structures.v1 "
        "esi-corporations.read_structures.v1 "
        "esi-assets.read_assets.v1"            # descoberta via personal assets
    )


settings = Settings()


def sso_token_auth() -> tuple[dict, dict]:
    """
    Autenticação para POST em /v2/oauth/token.

    Retorna (headers, data_extra). Com EVE_CLIENT_SECRET usa Basic auth
    (aplicação confidential); sem ele usa o fluxo PKCE, que envia só o client_id.
    """
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if settings.EVE_CLIENT_SECRET:
        creds = f"{settings.EVE_CLIENT_ID}:{settings.EVE_CLIENT_SECRET}"
        headers["Authorization"] = "Basic " + base64.b64encode(creds.encode()).decode()
        return headers, {}
    return headers, {"client_id": settings.EVE_CLIENT_ID}
