import json
import time
from typing import Any
from urllib.parse import quote

import httpx

from keycloak_mcp_server.config import KeycloakConfig


class KeycloakClient:
    def __init__(self, config: KeycloakConfig) -> None:
        self._config = config
        self._http = httpx.AsyncClient(verify=config.verify_ssl, timeout=30.0)
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    async def close(self) -> None:
        await self._http.aclose()

    async def _ensure_token(self) -> None:
        if self._access_token and time.time() < self._token_expires_at - 10:
            return
        await self._authenticate()

    async def _authenticate(self) -> None:
        data: dict[str, str] = {}
        if self._config.use_client_credentials:
            data = {
                "grant_type": "client_credentials",
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
            }
        else:
            data = {
                "grant_type": "password",
                "client_id": self._config.client_id,
                "username": self._config.username,
                "password": self._config.password,
            }
            if self._config.client_secret:
                data["client_secret"] = self._config.client_secret

        resp = await self._http.post(self._config.token_url, data=data)
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        self._token_expires_at = time.time() + body.get("expires_in", 300)

    async def request(
        self,
        method: str,
        path: str,
        path_params: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> dict[str, Any] | list[Any] | str:
        await self._ensure_token()

        url = self._config.base_url + path
        if path_params:
            # URL-encode each path segment value so that characters like "/",
            # "..", "?" or "#" in an argument cannot alter the request target
            # (path traversal / injection). safe="" also encodes "/".
            encoded = {k: quote(str(v), safe="") for k, v in path_params.items()}
            url = url.format(**encoded)

        filtered_query: dict[str, Any] = {}
        if query_params:
            filtered_query = {k: v for k, v in query_params.items() if v is not None}

        headers = {"Authorization": f"Bearer {self._access_token}"}

        kwargs: dict[str, Any] = {"headers": headers, "params": filtered_query or None}
        if body is not None:
            headers["Content-Type"] = "application/json"
            kwargs["content"] = json.dumps(body) if not isinstance(body, str) else body

        resp = await self._http.request(method, url, **kwargs)

        if resp.status_code == 204:
            return {"status": "success", "code": 204}
        if resp.status_code == 201:
            location = resp.headers.get("Location", "")
            try:
                result = resp.json()
            except Exception:
                result = {}
            if location:
                result = result if isinstance(result, dict) else {}
                result["location"] = location
                result["status"] = "created"
            return result or {"status": "created", "code": 201, "location": location}

        resp.raise_for_status()

        try:
            return resp.json()
        except Exception:
            return resp.text or {"status": "success", "code": resp.status_code}
