"""
Async ESI (EVE Swagger Interface) client.

All public methods that require authentication accept an access_token string.
Token refresh is handled transparently when a 401 is returned.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings, sso_token_auth

logger = logging.getLogger(__name__)

# How many seconds before expiry we proactively refresh
TOKEN_REFRESH_MARGIN_SECONDS = 60


class ESIError(Exception):
    """Raised when an ESI request fails."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"ESI error {status_code}: {message}")


class ESIClient:
    """Thin async wrapper around ESI and EVE SSO endpoints."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": "EVE Industry Profit Tool/1.0"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, url: str, token: str | None = None, params: dict | None = None) -> Any:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await self.client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ESIError(exc.response.status_code, exc.response.text) from exc
        except httpx.RequestError as exc:
            raise ESIError(0, str(exc)) from exc

    async def _get_paginated(
        self, url: str, token: str | None = None, params: dict | None = None
    ) -> list:
        """
        Fetch all pages of a paginated ESI endpoint.

        Estratégia:
          1. Busca a página 1 para obter X-Pages
          2. Busca as páginas 2..N concorrentemente com Semaphore(5)
        """
        import asyncio

        base_params = dict(params or {})
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Página 1 — síncrona para obter X-Pages
        p1_params = {**base_params, "page": 1}
        try:
            response = await self.client.get(url, headers=headers, params=p1_params)
            response.raise_for_status()
            total_pages = int(response.headers.get("X-Pages", 1))
            page1_data: list = response.json() or []
        except httpx.HTTPStatusError as exc:
            raise ESIError(exc.response.status_code, exc.response.text) from exc
        except httpx.RequestError as exc:
            raise ESIError(0, str(exc)) from exc

        if total_pages <= 1:
            return page1_data

        # Páginas 2..N — concorrentes, máximo 5 simultâneos
        sem = asyncio.Semaphore(5)

        async def _fetch_page(page: int) -> list:
            async with sem:
                p_params = {**base_params, "page": page}
                try:
                    resp = await self.client.get(url, headers=headers, params=p_params)
                    resp.raise_for_status()
                    return resp.json() or []
                except httpx.HTTPStatusError as exc:
                    raise ESIError(exc.response.status_code, exc.response.text) from exc
                except httpx.RequestError as exc:
                    raise ESIError(0, str(exc)) from exc

        rest = await asyncio.gather(*[_fetch_page(p) for p in range(2, total_pages + 1)])

        results = page1_data[:]
        for page_data in rest:
            results.extend(page_data)
        return results

    # ------------------------------------------------------------------
    # Character
    # ------------------------------------------------------------------

    async def get_character_info(self, character_id: int) -> dict:
        """Public character information."""
        url = f"{settings.ESI_BASE_URL}/characters/{character_id}/"
        return await self._get(url)

    async def get_character_skills(self, character_id: int, token: str) -> dict:
        """Character skills (requires auth)."""
        url = f"{settings.ESI_BASE_URL}/characters/{character_id}/skills/"
        return await self._get(url, token=token)

    async def get_character_blueprints(self, character_id: int, token: str) -> list:
        """Character blueprints (requires auth, paginated)."""
        url = f"{settings.ESI_BASE_URL}/characters/{character_id}/blueprints/"
        return await self._get_paginated(url, token=token)

    # ------------------------------------------------------------------
    # Market
    # ------------------------------------------------------------------

    async def get_market_orders(
        self, region_id: int, type_id: int, order_type: str = "all"
    ) -> list:
        """Public market orders for a region/type."""
        url = f"{settings.ESI_BASE_URL}/markets/{region_id}/orders/"
        params = {"type_id": type_id, "order_type": order_type}
        return await self._get_paginated(url, params=params)

    async def get_character_assets(self, character_id: int, token: str) -> list:
        """
        GET /characters/{character_id}/assets/  (paginado)
        Requer esi-assets.read_assets.v1.
        Retorna todos os assets do personagem, incluindo location_id de estruturas Upwell.
        """
        url = f"{settings.ESI_BASE_URL}/characters/{character_id}/assets/"
        return await self._get_paginated(url, token=token)

    async def get_all_region_orders(self, region_id: int) -> list:
        """Fetch ALL market orders for a region without type filter (paginated)."""
        url = f"{settings.ESI_BASE_URL}/markets/{region_id}/orders/"
        return await self._get_paginated(url, params={"order_type": "all"})

    async def get_market_history(self, region_id: int, type_id: int) -> list:
        """
        GET /markets/{region_id}/history/?type_id={type_id}
        Retorna histórico diário de mercado (volume, preço médio, etc.).
        Endpoint público, sem autenticação.
        """
        url = f"{settings.ESI_BASE_URL}/markets/{region_id}/history/"
        return await self._get(url, params={"type_id": type_id})

    async def get_structure_market(self, structure_id: int, token: str) -> list:
        """Market orders in a player-owned structure (requires auth, paginated)."""
        url = f"{settings.ESI_BASE_URL}/markets/structures/{structure_id}/"
        return await self._get_paginated(url, token=token)

    async def get_structure_market_page(
        self, structure_id: int, token: str, page: int = 1
    ) -> tuple[list, int]:
        """
        Busca uma página específica de /markets/structures/{id}/.
        Retorna (dados, total_de_páginas).
        Levanta ESIError em erros HTTP, incluindo 403.
        """
        url = f"{settings.ESI_BASE_URL}/markets/structures/{structure_id}/"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = await self.client.get(url, headers=headers, params={"page": page})
            response.raise_for_status()
            total_pages = int(response.headers.get("X-Pages", 1))
            return response.json(), total_pages
        except httpx.HTTPStatusError as exc:
            raise ESIError(exc.response.status_code, exc.response.text) from exc
        except httpx.RequestError as exc:
            raise ESIError(0, str(exc)) from exc

    async def get_accessible_market_structures(self, token: str) -> list[int]:
        """
        List of structure IDs with markets accessible to the character.
        Requires esi-universe.read_structures.v1.
        Returns only the first page (~max 1000 IDs from ESI).
        """
        url = f"{settings.ESI_BASE_URL}/universe/structures/"
        try:
            return await self._get(url, token=token, params={"filter": "market"})
        except ESIError:
            return []

    async def get_structure_info(self, structure_id: int, token: str) -> dict:
        """
        Structure name, solar_system_id, type_id.
        Requires esi-universe.read_structures.v1.
        """
        url = f"{settings.ESI_BASE_URL}/universe/structures/{structure_id}/"
        return await self._get(url, token=token)

    async def get_system_name(self, system_id: int) -> str:
        """Solar system name from universe endpoint (public)."""
        url = f"{settings.ESI_BASE_URL}/universe/systems/{system_id}/"
        try:
            data = await self._get(url)
            return data.get("name", str(system_id))
        except ESIError:
            return str(system_id)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Exchange a refresh token for a new access token.

        Returns a dict with keys: access_token, refresh_token, expires_in.
        """
        url = f"{settings.SSO_BASE_URL}/v2/oauth/token"
        headers, auth_data = sso_token_auth()

        try:
            response = await self.client.post(
                url,
                headers=headers,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    **auth_data,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ESIError(exc.response.status_code, exc.response.text) from exc

    async def exchange_code_for_token(self, code: str, code_verifier: str) -> dict:
        """
        Exchange an authorization code for tokens (PKCE).

        Returns a dict with: access_token, refresh_token, expires_in, token_type.
        """
        url = f"{settings.SSO_BASE_URL}/v2/oauth/token"
        headers, auth_data = sso_token_auth()

        try:
            response = await self.client.post(
                url,
                headers=headers,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    **auth_data,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ESIError(exc.response.status_code, exc.response.text) from exc

    async def verify_token(self, access_token: str) -> dict:
        """
        Verify an access token and retrieve character info from EVE SSO.

        Returns a dict with: CharacterID, CharacterName, ExpiresOn, Scopes, etc.
        """
        url = "https://login.eveonline.com/v2/oauth/verify"
        return await self._get(url, token=access_token)

    def compute_expiry(self, expires_in: int) -> datetime:
        """Return the datetime when the token will expire."""
        return datetime.utcnow() + timedelta(seconds=expires_in)


# Singleton instance reused across the application lifetime
esi_client = ESIClient()
