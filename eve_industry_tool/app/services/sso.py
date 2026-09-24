"""
EVE SSO — montagem da URL de login com PKCE (RFC 7636).

O code_verifier fica guardado em app.storage.general até o callback
trocar o authorization code pelos tokens.
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

from nicegui import app as nicegui_app

from app.config import settings


def start_login() -> str:
    """Gera state + code_verifier, guarda na sessão e devolve a URL de autorização."""
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")

    nicegui_app.storage.general["oauth_state"] = state
    nicegui_app.storage.general["oauth_verifier"] = verifier

    params = {
        "response_type":         "code",
        "redirect_uri":          settings.EVE_CALLBACK_URL,
        "client_id":             settings.EVE_CLIENT_ID,
        "scope":                 settings.SSO_SCOPES,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    }
    return f"{settings.SSO_BASE_URL}/v2/oauth/authorize?{urlencode(params)}"


def pop_verifier(state: str | None) -> str | None:
    """Confere o state do callback e devolve (e consome) o code_verifier."""
    expected = nicegui_app.storage.general.pop("oauth_state", None)
    verifier = nicegui_app.storage.general.pop("oauth_verifier", None)
    if not state or state != expected:
        return None
    return verifier
