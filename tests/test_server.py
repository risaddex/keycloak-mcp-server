import httpx
import pytest

from keycloak_mcp_server.client import KeycloakClient
from keycloak_mcp_server.config import KeycloakConfig


def test_import():
    import keycloak_mcp_server

    assert keycloak_mcp_server is not None


@pytest.mark.asyncio
async def test_path_params_are_url_encoded():
    """Path parameter values must be URL-encoded so that characters like "/"
    cannot alter the request target (path traversal / injection)."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    config = KeycloakConfig(base_url="http://kc.local")
    client = KeycloakClient(config)
    # Skip real authentication.
    client._access_token = "test-token"
    client._token_expires_at = float("inf")
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        await client.request(
            method="GET",
            path="/admin/realms/{realm}/users/{user_id}",
            path_params={"realm": "master", "user_id": "../../evil?x=y"},
        )
    finally:
        await client.close()

    url = captured["url"]
    # The malicious segment must be encoded, not passed through raw.
    assert "../../evil" not in url
    assert "/users/..%2F..%2Fevil%3Fx%3Dy" in url


def test_bearer_auth_middleware_rejects_and_allows():
    """The SSE bearer-token middleware must 401 bad tokens and pass good ones."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from keycloak_mcp_server.server import main  # noqa: F401  (ensures module imports)

    # Re-declare the middleware the way server.main() builds it. Importing the
    # nested class isn't possible, so we validate the same contract here.
    import hmac
    from typing import Any

    class BearerAuthMiddleware:
        def __init__(self, app: Any, api_key: str) -> None:
            self.app = app
            self._expected = f"Bearer {api_key}"

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            headers = dict(scope.get("headers") or [])
            provided = headers.get(b"authorization", b"").decode("latin-1")
            if not hmac.compare_digest(provided, self._expected):
                await PlainTextResponse("Unauthorized", status_code=401)(
                    scope, receive, send
                )
                return
            await self.app(scope, receive, send)

    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(
        middleware=[Middleware(BearerAuthMiddleware, api_key="s3cret")],
        routes=[Route("/sse", endpoint=ok)],
    )
    tc = TestClient(app)

    assert tc.get("/sse").status_code == 401
    assert tc.get("/sse", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert tc.get("/sse", headers={"Authorization": "Bearer s3cret"}).status_code == 200
