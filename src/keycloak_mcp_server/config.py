import os
from dataclasses import dataclass, field


@dataclass
class KeycloakConfig:
    base_url: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
    )
    admin_realm: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_ADMIN_REALM", "master")
    )
    client_id: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_CLIENT_ID", "admin-cli")
    )
    client_secret: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
    )
    username: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_ADMIN_USERNAME", "")
    )
    password: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
    )
    verify_ssl: bool = field(
        default_factory=lambda: (
            os.environ.get("KEYCLOAK_VERIFY_SSL", "true").lower() == "true"
        )
    )
    sse_api_key: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_MCP_SSE_API_KEY", "")
    )

    @property
    def token_url(self) -> str:
        return (
            f"{self.base_url}/realms/{self.admin_realm}/protocol/openid-connect/token"
        )

    @property
    def use_client_credentials(self) -> bool:
        return bool(self.client_secret)
