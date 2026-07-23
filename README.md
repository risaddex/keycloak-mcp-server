# Keycloak MCP Server

<p align="center">
  <img src="https://img.shields.io/badge/Keycloak-REST_API-00B2B2?style=for-the-badge&logo=keycloak&logoColor=white" alt="Keycloak version">
  <img src="https://img.shields.io/badge/MCP-Model_Context_Protocol-5A67D8?style=for-the-badge" alt="MCP">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/github/license/paoloamato2/keycloak-mcp-server?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/github/stars/paoloamato2/keycloak-mcp-server?style=for-the-badge" alt="Stars">
</p>

<p align="center">
  <strong>A comprehensive <a href="https://modelcontextprotocol.io">Model Context Protocol (MCP)</a> server that exposes the <a href="https://www.keycloak.org/docs-api/latest/rest-api/index.html">Keycloak Admin REST API</a> as typed MCP tools. 299 tools covering all API categories.</strong>
</p>

---

## Features

- **Complete API coverage**: All 299 Keycloak Admin REST API endpoints
- **Dual transport**: stdio (Claude Code) and SSE (GitHub Copilot, other MCP clients)
- **Auto-authentication**: Supports both password and client credentials flows with automatic token refresh
- **Zero configuration tools**: Each tool is self-describing with full input schemas

### API Categories

| Category | Tools |
|---|---|
| Attack Detection | 3 |
| Authentication Management | 38 |
| Client Certificates | 6 |
| Client Initial Access | 3 |
| Client Registration Policy | 1 |
| Client Role Mappings | 10 |
| Client Scopes | 10 |
| Clients | 33 |
| Components | 6 |
| Groups | 11 |
| Identity Providers | 15 |
| Keys | 2 |
| Organizations | 13 |
| Protocol Mappers | 14 |
| Realms Admin | 37 |
| Roles | 28 |
| Roles by ID | 10 |
| Scope Mappings | 29 |
| Users | 30 |
| **Total** | **299** |


## Demo

*(Add a GIF or screenshot here demonstrating 3 real prompts and their executed tools!)*

## Installation

### Option 1: Run directly with `uvx` (Recommended)
You can run the server directly without manual installation using astral's `uv`:
```bash
uvx keycloak-mcp-server
```
*(When using `uvx`, you can pass environment variables inline or keep them in your MCP config file.)*

### Option 2: Install via pip
If you prefer a global or virtual environment installation:
```bash
pip install git+https://github.com/paoloamato2/keycloak-mcp-server.git
```

### Option 3: Install from source (For development)
```bash
git clone https://github.com/paoloamato2/keycloak-mcp-server.git
cd keycloak-mcp-server
uv pip install -e .
```

## Configuration

Set environment variables (or create a `.env` file based on `.env.example`):

```bash
# Required
export KEYCLOAK_URL=http://localhost:8080

# Authentication - Option A: Password flow
export KEYCLOAK_ADMIN_USERNAME=admin
export KEYCLOAK_ADMIN_PASSWORD=admin

# Authentication - Option B: Client credentials flow
export KEYCLOAK_CLIENT_ID=my-client
export KEYCLOAK_CLIENT_SECRET=my-secret

# Optional
export KEYCLOAK_ADMIN_REALM=master    # default: master
export KEYCLOAK_VERIFY_SSL=true       # default: true
```

## Usage

### Claude Code (stdio)

Add to your Claude Code MCP configuration (`~/.claude/claude_desktop_config.json` or project-level):

```json
{
  "mcpServers": {
    "keycloak": {
      "command": "python",
      "args": ["-m", "keycloak_mcp_server"],
      "env": {
        "KEYCLOAK_URL": "http://localhost:8080",
        "KEYCLOAK_ADMIN_USERNAME": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "admin"
      }
    }
  }
}
```

Or if installed with uv:

```json
{
  "mcpServers": {
    "keycloak": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/keycloak-mcp-server", "python", "-m", "keycloak_mcp_server"],
      "env": {
        "KEYCLOAK_URL": "http://localhost:8080",
        "KEYCLOAK_ADMIN_USERNAME": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "admin"
      }
    }
  }
}
```

### GitHub Copilot (SSE)

Start the server with SSE transport:

```bash
python -m keycloak_mcp_server --transport sse --port 8080
```

> ⚠️ **The SSE transport exposes every admin tool over HTTP.** It binds to
> `127.0.0.1` (loopback) by default. To bind any other interface you **must**
> set an API key — the server refuses to start on a non-loopback host without
> one:
>
> ```bash
> export KEYCLOAK_MCP_SSE_API_KEY="$(openssl rand -hex 32)"
> python -m keycloak_mcp_server --transport sse --host 0.0.0.0 --port 8080
> ```
>
> Clients must then send `Authorization: Bearer <key>` on every request. Even
> with a key, prefer keeping the port behind a reverse proxy / VPN rather than
> exposing it directly to the internet.

Then configure in your GitHub Copilot MCP settings (VS Code `settings.json`):

```json
{
  "github.copilot.chat.mcpServers": {
    "keycloak": {
      "type": "sse",
      "url": "http://localhost:8080/sse"
    }
  }
}
```

### Command Line

```bash
# stdio mode (default)
python -m keycloak_mcp_server

# SSE mode (loopback-only by default)
python -m keycloak_mcp_server --transport sse --port 8080

# SSE mode on all interfaces (requires KEYCLOAK_MCP_SSE_API_KEY)
KEYCLOAK_MCP_SSE_API_KEY="$(openssl rand -hex 32)" \
  python -m keycloak_mcp_server --transport sse --host 0.0.0.0 --port 8080

# Using the entry point
keycloak-mcp-server --transport sse --port 8080
```

## Security & Production Recommendations

⚠️ **SECURITY WARNING:** This MCP Server registers **all** Keycloak Admin REST API endpoints (299 tools), including sensitive write operations (like creating/deleting users, resetting passwords, and managing realms). **Do not use your master realm super-admin credentials in a production environment.**

When attaching this MCP server to your AI Assistants, please strictly follow the **Principle of Least Privilege**:

1. **Use Service Accounts (Client Credentials Flow)**:
   Avoid using the Password flow (`KEYCLOAK_ADMIN_USERNAME` / `KEYCLOAK_ADMIN_PASSWORD`). Instead, create a dedicated Keycloak Client with Service Accounts Enabled, and use the `KEYCLOAK_CLIENT_ID` and `KEYCLOAK_CLIENT_SECRET`.

2. **Limit Target Realms**:
   Do not attach the server to the `master` realm unless specifically necessary. Point `KEYCLOAK_ADMIN_REALM` to the exact realm your AI assistant should manage.

3. **Grant Only Required Roles**:
   Only assign the minimum necessary roles to your MCP Service Account.
   * If your LLM only needs to **read** data: Assign only `view-users`, `view-clients`, or `view-realm`.
   * If your LLM needs to **manage** users: Assign only `manage-users`.
   * *Never* assign `admin` or `realm-admin` roles to the AI unless you are fully aware of the risks.

4. **Always Verify SSL**:
   Keep `KEYCLOAK_VERIFY_SSL=true` enabled in production to prevent Man-in-the-Middle (MITM) attacks. Setting it to `false` is only acceptable for local development.

5. **Protect the SSE transport**:
   Prefer `stdio` when possible. If you use `--transport sse`, set `KEYCLOAK_MCP_SSE_API_KEY` (required to bind any non-loopback host) so clients must present `Authorization: Bearer <key>`, and keep the port behind a reverse proxy or VPN — never expose it directly.

## Examples

Once connected, you can use natural language to interact with Keycloak:

- *"List all realms"* → calls `list_realms`
- *"Create a user called john in the master realm"* → calls `create_user`
- *"Show me all clients in the production realm"* → calls `list_clients`
- *"What roles does user X have?"* → calls `get_user_role_mappings`
- *"Add the admin role to the developers group"* → calls `add_group_realm_role_mappings`

## Project Structure

```
src/keycloak_mcp_server/
├── __init__.py          # Package entry point
├── __main__.py          # CLI entry point
├── config.py            # Environment-based configuration
├── client.py            # Async HTTP client with auto-auth
├── server.py            # MCP server setup and tool registration
└── endpoints/           # Endpoint definitions by category
    ├── __init__.py      # Base classes (EndpointDef, Param)
    ├── attack_detection.py
    ├── authentication.py
    ├── certificates.py
    ├── client_initial_access.py
    ├── client_registration_policy.py
    ├── client_role_mappings.py
    ├── client_scopes.py
    ├── clients.py
    ├── component.py
    ├── groups.py
    ├── identity_providers.py
    ├── key.py
    ├── organizations.py
    ├── protocol_mappers.py
    ├── realms.py
    ├── roles.py
    ├── roles_by_id.py
    ├── scope_mappings.py
    └── users.py
```

## License

MIT
