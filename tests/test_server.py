import json
from typing import Any, cast

import mcp.types as t
import pytest

from keycloak_mcp_server.server import ALL_ENDPOINTS, create_server


def test_import():
    import keycloak_mcp_server

    assert keycloak_mcp_server is not None


# ── list_tools ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_tools_returns_all_endpoints():
    server, client = create_server()
    try:
        handler = server.request_handlers[t.ListToolsRequest]
        res = await handler(t.ListToolsRequest(method="tools/list"))
        result = cast(t.ListToolsResult, getattr(res, "root", res))
        assert len(result.tools) == len(ALL_ENDPOINTS) == 299
        names = {tool.name for tool in result.tools}
        assert "list_realms" in names
        assert "impersonate_user" in names
    finally:
        await client.close()


# ── call_tool dispatch ──────────────────────────────────────────────────────
async def _call(server, name: str, arguments: dict[str, Any]):
    handler = server.request_handlers[t.CallToolRequest]
    req = t.CallToolRequest(
        method="tools/call",
        params=t.CallToolRequestParams(name=name, arguments=arguments),
    )
    res = await handler(req)
    tool_result = cast(t.CallToolResult, getattr(res, "root", res))
    content = tool_result.content[0]
    assert content.type == "text"
    return json.loads(content.text)


@pytest.mark.asyncio
async def test_call_tool_unknown_returns_error():
    server, client = create_server()
    try:
        data = await _call(server, "does_not_exist", {})
        assert data["error"] == "Unknown tool: does_not_exist"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_call_tool_dispatches_to_client():
    server, client = create_server()
    calls: dict[str, Any] = {}

    async def fake_request(
        method, path, path_params=None, query_params=None, body=None
    ):
        calls.update(
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            body=body,
        )
        return [{"id": "abc"}]

    setattr(client, "request", fake_request)
    try:
        data = await _call(server, "get_user", {"realm": "master", "user_id": "abc"})
        assert data == [{"id": "abc"}]
        assert calls["method"] == "GET"
        assert calls["path"] == "/admin/realms/{realm}/users/{user_id}"
        assert calls["path_params"] == {"realm": "master", "user_id": "abc"}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_call_tool_serializes_exceptions():
    server, client = create_server()

    async def boom(*args, **kwargs):
        raise ValueError("kaboom")

    setattr(client, "request", boom)
    try:
        data = await _call(server, "list_realms", {})
        assert data["type"] == "ValueError"
        assert "kaboom" in data["error"]
    finally:
        await client.close()


# ── SSE bearer-token middleware ─────────────────────────────────────────────
def test_bearer_auth_middleware_rejects_and_allows():
    """The SSE bearer-token middleware must 401 bad tokens and pass good ones."""
    import hmac

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

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
