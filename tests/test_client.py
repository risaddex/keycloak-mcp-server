import time
from urllib.parse import parse_qs

import httpx
import pytest

from keycloak_mcp_server.client import KeycloakClient
from keycloak_mcp_server.config import KeycloakConfig

TOKEN_SUFFIX = "/protocol/openid-connect/token"


def make_client(handler, **cfg) -> KeycloakClient:
    cfg.setdefault("base_url", "http://kc.local")
    client = KeycloakClient(KeycloakConfig(**cfg))
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def preauth(client: KeycloakClient, token: str = "test-token") -> None:
    client._access_token = token
    client._token_expires_at = time.time() + 3600


# ── request(): URL / params / body handling ─────────────────────────────────
@pytest.mark.asyncio
async def test_path_params_are_url_encoded():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    preauth(client)
    try:
        await client.request(
            method="GET",
            path="/admin/realms/{realm}/users/{user_id}",
            path_params={"realm": "master", "user_id": "../../evil?x=y"},
        )
    finally:
        await client.close()

    assert "../../evil" not in captured["url"]
    assert "/users/..%2F..%2Fevil%3Fx%3Dy" in captured["url"]


@pytest.mark.asyncio
async def test_none_query_params_are_filtered():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.query.decode()
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    preauth(client)
    try:
        await client.request(
            method="GET",
            path="/admin/realms/{realm}/users",
            path_params={"realm": "master"},
            query_params={"search": "john", "email": None, "max": 0},
        )
    finally:
        await client.close()

    q = parse_qs(captured["query"])
    assert q["search"] == ["john"]
    assert "email" not in q  # None dropped
    assert q["max"] == ["0"]  # 0 is not None -> kept


@pytest.mark.asyncio
async def test_dict_body_is_json_encoded_with_content_type():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    preauth(client)
    try:
        await client.request(
            method="POST",
            path="/admin/realms/{realm}/users",
            path_params={"realm": "master"},
            body={"username": "john"},
        )
    finally:
        await client.close()

    assert captured["content_type"] == "application/json"
    assert captured["body"] == '{"username": "john"}'


@pytest.mark.asyncio
async def test_string_body_is_passed_through():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    preauth(client)
    try:
        await client.request(method="POST", path="/x", body="raw-string-body")
    finally:
        await client.close()

    assert captured["body"] == "raw-string-body"


@pytest.mark.asyncio
async def test_authorization_header_is_set():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    preauth(client, token="abc123")
    try:
        await client.request(method="GET", path="/x")
    finally:
        await client.close()

    assert captured["auth"] == "Bearer abc123"


# ── request(): status-code handling ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_204_returns_success_marker():
    client = make_client(lambda r: httpx.Response(204))
    preauth(client)
    try:
        result = await client.request(method="DELETE", path="/x")
    finally:
        await client.close()
    assert result == {"status": "success", "code": 204}


@pytest.mark.asyncio
async def test_201_with_location_adds_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, headers={"Location": "http://kc.local/x/new-id"})

    client = make_client(handler)
    preauth(client)
    try:
        result = await client.request(method="POST", path="/x")
    finally:
        await client.close()
    assert isinstance(result, dict)
    assert result["location"] == "http://kc.local/x/new-id"
    assert result["status"] == "created"


@pytest.mark.asyncio
async def test_201_without_location_returns_body():
    client = make_client(lambda r: httpx.Response(201, json={"id": "x"}))
    preauth(client)
    try:
        result = await client.request(method="POST", path="/x")
    finally:
        await client.close()
    assert result == {"id": "x"}


@pytest.mark.asyncio
async def test_json_response_is_returned():
    client = make_client(lambda r: httpx.Response(200, json=[{"realm": "master"}]))
    preauth(client)
    try:
        result = await client.request(method="GET", path="/x")
    finally:
        await client.close()
    assert result == [{"realm": "master"}]


@pytest.mark.asyncio
async def test_non_json_response_returns_text():
    client = make_client(lambda r: httpx.Response(200, text="plain text"))
    preauth(client)
    try:
        result = await client.request(method="GET", path="/x")
    finally:
        await client.close()
    assert result == "plain text"


@pytest.mark.asyncio
async def test_error_status_raises():
    client = make_client(lambda r: httpx.Response(404, json={"error": "not found"}))
    preauth(client)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.request(method="GET", path="/x")
    finally:
        await client.close()


# ── authentication flows ────────────────────────────────────────────────────
def _auth_handler(token_calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(TOKEN_SUFFIX):
            token_calls.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
        return httpx.Response(200, json={"ok": True})

    return handler


@pytest.mark.asyncio
async def test_password_grant():
    token_calls: list = []
    client = make_client(
        _auth_handler(token_calls), username="admin", password="pw", client_secret=""
    )
    try:
        await client.request(method="GET", path="/x")
    finally:
        await client.close()

    form = token_calls[0]
    assert form["grant_type"] == ["password"]
    assert form["username"] == ["admin"]
    assert form["password"] == ["pw"]
    assert form["client_id"] == ["admin-cli"]


@pytest.mark.asyncio
async def test_client_credentials_grant():
    token_calls: list = []
    client = make_client(
        _auth_handler(token_calls), client_id="svc", client_secret="sekret"
    )
    try:
        await client.request(method="GET", path="/x")
    finally:
        await client.close()

    form = token_calls[0]
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_id"] == ["svc"]
    assert form["client_secret"] == ["sekret"]
    assert "password" not in form


@pytest.mark.asyncio
async def test_token_is_cached_across_requests():
    token_calls: list = []
    client = make_client(_auth_handler(token_calls), username="a", password="b")
    try:
        await client.request(method="GET", path="/x")
        await client.request(method="GET", path="/y")
    finally:
        await client.close()
    assert len(token_calls) == 1


@pytest.mark.asyncio
async def test_token_is_refreshed_when_expired():
    token_calls: list = []
    client = make_client(_auth_handler(token_calls), username="a", password="b")
    try:
        await client.request(method="GET", path="/x")
        client._token_expires_at = time.time() - 1  # force expiry
        await client.request(method="GET", path="/y")
    finally:
        await client.close()
    assert len(token_calls) == 2
