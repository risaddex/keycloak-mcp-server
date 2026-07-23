import re

from keycloak_mcp_server.endpoints import EndpointDef, Param
from keycloak_mcp_server.server import ALL_ENDPOINTS, ENDPOINTS_BY_NAME

VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
PLACEHOLDER = re.compile(r"{(\w+)}")


# ── EndpointDef.input_schema ────────────────────────────────────────────────
def test_input_schema_path_query_body():
    ep = EndpointDef(
        name="demo",
        description="d",
        method="POST",
        path="/admin/realms/{realm}",
        path_params=[Param("realm", "Realm name")],
        query_params=[Param("max", "Max", required=False, param_type="integer")],
        body_param=Param("payload", "Body", param_type="object"),
    )
    schema = ep.input_schema()

    assert schema["type"] == "object"
    props = schema["properties"]
    assert props["realm"] == {"type": "string", "description": "Realm name"}
    assert props["max"]["type"] == "integer"
    assert props["payload"]["type"] == "object"
    # Required path + body params, optional query param excluded.
    assert set(schema["required"]) == {"realm", "payload"}


def test_input_schema_enum_and_default():
    ep = EndpointDef(
        name="demo",
        description="d",
        method="GET",
        path="/x",
        query_params=[
            Param("kind", "kind", required=False, enum=["a", "b"], default="a"),
        ],
    )
    prop = ep.input_schema()["properties"]["kind"]
    assert prop["enum"] == ["a", "b"]
    assert prop["default"] == "a"
    # No required entry when everything is optional.
    assert "required" not in ep.input_schema()


# ── EndpointDef.extract_args ────────────────────────────────────────────────
def test_extract_args_splits_path_query_body():
    ep = EndpointDef(
        name="demo",
        description="d",
        method="PUT",
        path="/admin/realms/{realm}/users/{user_id}",
        path_params=[Param("realm", "r"), Param("user_id", "u")],
        query_params=[Param("max", "m", required=False)],
        body_param=Param("user_data", "b", param_type="object"),
    )
    path_vals, query_vals, body = ep.extract_args(
        {"realm": "master", "user_id": 42, "max": 10, "user_data": {"k": "v"}}
    )
    # Path values are always coerced to str for URL formatting.
    assert path_vals == {"realm": "master", "user_id": "42"}
    assert query_vals == {"max": 10}
    assert body == {"k": "v"}


def test_extract_args_omits_missing_optional():
    ep = EndpointDef(
        name="demo",
        description="d",
        method="GET",
        path="/admin/realms/{realm}",
        path_params=[Param("realm", "r")],
        query_params=[Param("search", "s", required=False)],
    )
    path_vals, query_vals, body = ep.extract_args({"realm": "master"})
    assert path_vals == {"realm": "master"}
    assert query_vals == {}
    assert body is None


# ── Registry regression tests over all 299 endpoints ────────────────────────
def test_endpoint_count():
    assert len(ALL_ENDPOINTS) == 299


def test_endpoint_names_are_unique():
    names = [ep.name for ep in ALL_ENDPOINTS]
    assert len(names) == len(set(names))
    assert len(ENDPOINTS_BY_NAME) == len(names)


def test_all_methods_valid():
    bad = [ep.name for ep in ALL_ENDPOINTS if ep.method not in VALID_METHODS]
    assert bad == []


def test_path_placeholders_match_declared_path_params():
    """Every {placeholder} in a path must have a matching path_param and vice
    versa — otherwise .format() would raise KeyError at request time."""
    mismatches = []
    for ep in ALL_ENDPOINTS:
        placeholders = set(PLACEHOLDER.findall(ep.path))
        declared = {p.name for p in ep.path_params}
        if placeholders != declared:
            mismatches.append((ep.name, placeholders ^ declared))
    assert mismatches == []


def test_input_schema_is_wellformed_for_every_endpoint():
    for ep in ALL_ENDPOINTS:
        schema = ep.input_schema()
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        # required (if present) must reference declared properties.
        for name in schema.get("required", []):
            assert name in schema["properties"], f"{ep.name}: {name} not in properties"
