import pytest

from keycloak_mcp_server.config import KeycloakConfig

ENV_KEYS = [
    "KEYCLOAK_URL",
    "KEYCLOAK_ADMIN_REALM",
    "KEYCLOAK_CLIENT_ID",
    "KEYCLOAK_CLIENT_SECRET",
    "KEYCLOAK_ADMIN_USERNAME",
    "KEYCLOAK_ADMIN_PASSWORD",
    "KEYCLOAK_VERIFY_SSL",
    "KEYCLOAK_MCP_SSE_API_KEY",
]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults(clean_env):
    cfg = KeycloakConfig()
    assert cfg.base_url == "http://localhost:8080"
    assert cfg.admin_realm == "master"
    assert cfg.client_id == "admin-cli"
    assert cfg.client_secret == ""
    assert cfg.username == ""
    assert cfg.password == ""
    assert cfg.verify_ssl is True
    assert cfg.sse_api_key == ""


def test_env_override(clean_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KEYCLOAK_URL", "https://kc.example.com")
    monkeypatch.setenv("KEYCLOAK_ADMIN_REALM", "myrealm")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "my-client")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("KEYCLOAK_MCP_SSE_API_KEY", "api-key")

    cfg = KeycloakConfig()
    assert cfg.base_url == "https://kc.example.com"
    assert cfg.admin_realm == "myrealm"
    assert cfg.client_id == "my-client"
    assert cfg.client_secret == "s3cret"
    assert cfg.sse_api_key == "api-key"


def test_token_url(clean_env):
    cfg = KeycloakConfig(base_url="https://kc.example.com", admin_realm="master")
    assert (
        cfg.token_url
        == "https://kc.example.com/realms/master/protocol/openid-connect/token"
    )


def test_use_client_credentials_true_when_secret_set(clean_env):
    assert KeycloakConfig(client_secret="x").use_client_credentials is True


def test_use_client_credentials_false_without_secret(clean_env):
    assert KeycloakConfig(client_secret="").use_client_credentials is False


@pytest.mark.parametrize(
    "value,expected",
    [("true", True), ("TRUE", True), ("false", False), ("0", False), ("no", False)],
)
def test_verify_ssl_parsing(
    clean_env, monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
):
    monkeypatch.setenv("KEYCLOAK_VERIFY_SSL", value)
    assert KeycloakConfig().verify_ssl is expected
