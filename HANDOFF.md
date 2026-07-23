# Handoff — Keycloak MCP Server (fork `risaddex`)

Context handoff so this work can be continued in a **local** Claude Code session
(or by hand) without the original web-session conversation. If you're a fresh
Claude session: read this file, then `deploy/homelab/README.md`, and continue
from **"Remaining work"** below.

## TL;DR

A security audit of this Keycloak MCP fork was done and it's **safe to adopt**.
Two PRs were opened and **both are merged into `master`**:

- **PR #1** — security hardening + test suite. https://github.com/risaddex/keycloak-mcp-server/pull/1
- **PR #2** — Dockerfile + homelab k3s deploy manifests. https://github.com/risaddex/keycloak-mcp-server/pull/2

CI (`test-and-lint`: ruff + pyright + pytest) is **green** on `master`.

The only thing left is **operational and must run on a machine with cluster
access** (the web sandbox couldn't reach the homelab LAN): build the image and
apply the manifests.

## Audit verdict (summary)

- No fork tampering — all upstream commits (from `paoloamato2`); no malicious code.
- No dangerous patterns (`eval`/`exec`/`subprocess`/`base64`/exfil); no committed secrets.
- Dependencies current, no known CVEs (`h11 0.16.0` fixes CVE-2025-43859).
- Endpoints are 100% declarative (299 tools; 50 destructive).

## What was changed (already on `master`)

Security hardening (PR #1):
- **SSE transport now requires auth.** Default `--host` is `127.0.0.1`; a bearer
  token (`KEYCLOAK_MCP_SSE_API_KEY`) can be required; the server **refuses to
  bind a non-loopback host without a key**. Middleware is pure-ASGI +
  `hmac.compare_digest`. (`src/keycloak_mcp_server/server.py`, `config.py`)
- **Path params URL-encoded** (`quote(..., safe="")`) to stop path traversal /
  injection. (`src/keycloak_mcp_server/client.py`)
- Test suite grew 3 → 40 (config, endpoints/registry, client, server dispatch,
  middleware). All no-Docker except the pre-existing e2e.

Deploy artifacts (PR #2):
- `Dockerfile` (multi-stage, uv, non-root) + `.dockerignore`
- `deploy/homelab/manifests.yaml` — Traefik `Deployment`/`Service`/`IngressRoute`
  in namespace `mcp`, hardened securityContext, tcpSocket probes.
- `deploy/homelab/secret.example.yaml` — expected keys only (no real values).
- `deploy/homelab/README.md` — build/secret/apply/verify steps.
- `.github/workflows/docker-publish.yml` — build+push image to GHCR.

## Remaining work (do this locally)

```bash
# 0. fresh clone (everything is on master)
git clone https://github.com/risaddex/keycloak-mcp-server
cd keycloak-mcp-server

# 1. build & push the image (or enable the GH Actions workflow)
IMAGE=ghcr.io/risaddex/keycloak-mcp-server:0.1.0     # or your Gitea registry
docker build -t "$IMAGE" .
docker push "$IMAGE"
# if you changed the registry/tag, update image: in deploy/homelab/manifests.yaml

# 2. create the secret (prefer Bitwarden/ExternalSecret; example for a quick test)
kubectl create namespace mcp --dry-run=client -o yaml | kubectl apply -f -
#   set KEYCLOAK_CLIENT_SECRET and KEYCLOAK_MCP_SSE_API_KEY ($(openssl rand -hex 32))
cp deploy/homelab/secret.example.yaml /tmp/kc-mcp-secret.yaml && $EDITOR /tmp/kc-mcp-secret.yaml
kubectl apply -f /tmp/kc-mcp-secret.yaml

# 3. apply
kubectl apply -f deploy/homelab/manifests.yaml
kubectl -n mcp rollout status deploy/keycloak-mcp

# 4. verify (401 without key, stream with key)
curl -sS -o /dev/null -w '%{http_code}\n' https://keycloak-mcp.daniloromano.dev/sse
curl -sS -H "Authorization: Bearer $KEY" https://keycloak-mcp.daniloromano.dev/sse
```

MCP client config:
```json
{"mcpServers":{"keycloak":{"type":"sse",
  "url":"https://keycloak-mcp.daniloromano.dev/sse",
  "headers":{"Authorization":"Bearer <KEYCLOAK_MCP_SSE_API_KEY>"}}}}
```

## Decisions to validate (I picked sensible defaults)

1. **Registry = GHCR** (`ghcr.io/risaddex/keycloak-mcp-server`). Switch the
   `image:` in `manifests.yaml` if you prefer your Gitea registry.
2. **Host-based routing** (`keycloak-mcp.daniloromano.dev`) instead of
   `mcp.daniloromano.dev/keycloak`. Reason: the MCP **SSE transport advertises
   an absolute `/messages/` path**, which breaks under path-prefix + StripPrefix.
   A path-based variant is included **commented** in `manifests.yaml` if you
   still want the shared domain — but test the `/messages/` POST if you use it.
3. **Least privilege**: create a **per-realm** service-account client (inside the
   target realm, not `master`) granted only the roles it needs from that realm's
   `realm-management` client (`view-*` read-only, `manage-users` max). Set
   `KEYCLOAK_ADMIN_REALM` to that realm. Use `master` only for cross-realm /
   realm-creation needs — and even then scope the roles, never the super-admin.
   See `deploy/homelab/README.md` step 2 for the exact console steps.

## Optional security follow-ups (NOT done — low severity)

- `server.py` returns raw `str(e)` in tool errors → leaks the internal Keycloak
  URL (not credentials). Consider sanitizing.
- No audit logging of mutating admin actions (delete/reset/impersonate).

## Key files

| Path | What |
|---|---|
| `src/keycloak_mcp_server/server.py` | MCP server, SSE transport + bearer middleware |
| `src/keycloak_mcp_server/client.py` | HTTP client, auth, path-encoding |
| `src/keycloak_mcp_server/config.py` | env config incl. `sse_api_key` |
| `deploy/homelab/` | Dockerfile usage + k8s manifests + README |
| `tests/` | 40 unit/regression tests (`uv run pytest`) |

## Branch

Work branch: `claude/keycloak-mcp-security-audit-qc14zt` (kept in sync with
`master`). Both PRs merged; new work should branch from latest `master`.
