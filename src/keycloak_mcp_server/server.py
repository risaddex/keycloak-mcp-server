import argparse
import asyncio
import hmac
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from keycloak_mcp_server.client import KeycloakClient
from keycloak_mcp_server.config import KeycloakConfig
from keycloak_mcp_server.endpoints import EndpointDef

from keycloak_mcp_server.endpoints.attack_detection import ENDPOINTS as ATTACK_DETECTION
from keycloak_mcp_server.endpoints.authentication import ENDPOINTS as AUTHENTICATION
from keycloak_mcp_server.endpoints.certificates import ENDPOINTS as CERTIFICATES
from keycloak_mcp_server.endpoints.client_initial_access import (
    ENDPOINTS as CLIENT_INITIAL_ACCESS,
)
from keycloak_mcp_server.endpoints.client_registration_policy import (
    ENDPOINTS as CLIENT_REG_POLICY,
)
from keycloak_mcp_server.endpoints.client_role_mappings import (
    ENDPOINTS as CLIENT_ROLE_MAPPINGS,
)
from keycloak_mcp_server.endpoints.client_scopes import ENDPOINTS as CLIENT_SCOPES
from keycloak_mcp_server.endpoints.clients import ENDPOINTS as CLIENTS
from keycloak_mcp_server.endpoints.component import ENDPOINTS as COMPONENT
from keycloak_mcp_server.endpoints.groups import ENDPOINTS as GROUPS
from keycloak_mcp_server.endpoints.identity_providers import (
    ENDPOINTS as IDENTITY_PROVIDERS,
)
from keycloak_mcp_server.endpoints.key import ENDPOINTS as KEY
from keycloak_mcp_server.endpoints.organizations import ENDPOINTS as ORGANIZATIONS
from keycloak_mcp_server.endpoints.protocol_mappers import ENDPOINTS as PROTOCOL_MAPPERS
from keycloak_mcp_server.endpoints.realms import ENDPOINTS as REALMS
from keycloak_mcp_server.endpoints.roles import ENDPOINTS as ROLES
from keycloak_mcp_server.endpoints.roles_by_id import ENDPOINTS as ROLES_BY_ID
from keycloak_mcp_server.endpoints.scope_mappings import ENDPOINTS as SCOPE_MAPPINGS
from keycloak_mcp_server.endpoints.users import ENDPOINTS as USERS

logger = logging.getLogger(__name__)

ALL_ENDPOINTS: list[EndpointDef] = [
    *ATTACK_DETECTION,
    *AUTHENTICATION,
    *CERTIFICATES,
    *CLIENT_INITIAL_ACCESS,
    *CLIENT_REG_POLICY,
    *CLIENT_ROLE_MAPPINGS,
    *CLIENT_SCOPES,
    *CLIENTS,
    *COMPONENT,
    *GROUPS,
    *IDENTITY_PROVIDERS,
    *KEY,
    *ORGANIZATIONS,
    *PROTOCOL_MAPPERS,
    *REALMS,
    *ROLES,
    *ROLES_BY_ID,
    *SCOPE_MAPPINGS,
    *USERS,
]

ENDPOINTS_BY_NAME: dict[str, EndpointDef] = {ep.name: ep for ep in ALL_ENDPOINTS}


def create_server() -> tuple[Server, KeycloakClient]:
    config = KeycloakConfig()
    client = KeycloakClient(config)
    server = Server("keycloak-admin")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=ep.name, description=ep.description, inputSchema=ep.input_schema()
            )
            for ep in ALL_ENDPOINTS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        ep = ENDPOINTS_BY_NAME.get(name)
        if not ep:
            return [
                TextContent(
                    type="text", text=json.dumps({"error": f"Unknown tool: {name}"})
                )
            ]

        try:
            path_params, query_params, body = ep.extract_args(arguments)
            result = await client.request(
                method=ep.method,
                path=ep.path,
                path_params=path_params,
                query_params=query_params,
                body=body,
            )
            text = (
                json.dumps(result, indent=2, default=str)
                if not isinstance(result, str)
                else result
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.error(f"Error calling tool {name}: {str(e)}", exc_info=True)
            error_msg = json.dumps({"error": str(e), "type": type(e).__name__})
            return [TextContent(type="text", text=error_msg)]

    return server, client


def main() -> None:
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Keycloak MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio", help="Transport type"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE transport (default: 127.0.0.1, loopback-only)",
    )
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE transport")
    args = parser.parse_args()

    server, client = create_server()

    if args.transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import PlainTextResponse
        from starlette.routing import Mount, Route

        api_key = client._config.sse_api_key
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}

        # The SSE transport exposes every admin tool over HTTP. Refuse to bind a
        # non-loopback interface without an API key so it cannot be published
        # unauthenticated by accident.
        if not api_key and args.host not in loopback_hosts:
            raise SystemExit(
                f"Refusing to start SSE transport on non-loopback host {args.host!r} "
                "without authentication. Set KEYCLOAK_MCP_SSE_API_KEY to require a "
                "bearer token, or bind to 127.0.0.1 for local-only access."
            )
        if not api_key:
            logger.warning(
                "SSE transport starting WITHOUT authentication (bound to %s). "
                "Set KEYCLOAK_MCP_SSE_API_KEY to require a bearer token.",
                args.host,
            )

        class BearerAuthMiddleware:
            """Pure-ASGI middleware enforcing a bearer token on HTTP requests.

            Implemented as raw ASGI (not BaseHTTPMiddleware) so it does not
            buffer or break the SSE streaming response.
            """

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
                    response = PlainTextResponse("Unauthorized", status_code=401)
                    await response(scope, receive, send)
                    return
                await self.app(scope, receive, send)

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        middleware = (
            [Middleware(BearerAuthMiddleware, api_key=api_key)] if api_key else []
        )

        app = Starlette(
            middleware=middleware,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        import uvicorn

        uvicorn.run(app, host=args.host, port=args.port)
    else:

        async def run_stdio():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream, write_stream, server.create_initialization_options()
                )

        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
