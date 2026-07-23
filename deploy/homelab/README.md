# Homelab deploy (k3s + Traefik)

Deploys the Keycloak MCP Server into the `mcp` namespace as an SSE HTTP endpoint,
following the homelab conventions (Traefik ingress, dedicated hostname).

> **This must be applied from a machine with cluster access.** It was prepared in
> a cloud sandbox that cannot reach the homelab LAN, so nothing here was applied
> to the cluster — run the steps below yourself (or wire the manifests into your
> GitOps repo).

## 1. Build & push the image

GitHub Actions is currently disabled on this fork, so either enable the workflow
at `.github/workflows/docker-publish.yml` (Actions → enable, then run it) or
build locally:

```bash
# from the repo root
IMAGE=ghcr.io/risaddex/keycloak-mcp-server:0.1.0   # or your Gitea registry
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

Update the `image:` field in `manifests.yaml` if you use a different registry/tag.
Prefer an immutable tag or digest — k3s/ArgoCD won't redeploy on a moved `latest`.

## 2. Create the secret

Do **not** commit real credentials. Materialize it via Bitwarden/ExternalSecrets
(your convention) or, for a quick test, from the example:

```bash
kubectl create namespace mcp --dry-run=client -o yaml | kubectl apply -f -
cp secret.example.yaml /tmp/keycloak-mcp-secret.yaml
# edit /tmp/keycloak-mcp-secret.yaml: set KEYCLOAK_CLIENT_SECRET and
# KEYCLOAK_MCP_SSE_API_KEY ($(openssl rand -hex 32))
kubectl apply -f /tmp/keycloak-mcp-secret.yaml
```

## 3. Apply the manifests

```bash
kubectl apply -f manifests.yaml
kubectl -n mcp rollout status deploy/keycloak-mcp
```

Add a DNS / Cloudflare-Tunnel entry for `keycloak-mcp.daniloromano.dev` → cluster
Traefik if it doesn't exist yet.

## 4. Verify

```bash
kubectl -n mcp get pods,svc,ingressroute
# 401 without the key (expected), 200-ish SSE stream with it:
curl -sS -o /dev/null -w '%{http_code}\n' https://keycloak-mcp.daniloromano.dev/sse
curl -sS -H "Authorization: Bearer $KEY" https://keycloak-mcp.daniloromano.dev/sse
```

## 5. Point your MCP client at it

```json
{
  "mcpServers": {
    "keycloak": {
      "type": "sse",
      "url": "https://keycloak-mcp.daniloromano.dev/sse",
      "headers": { "Authorization": "Bearer <KEYCLOAK_MCP_SSE_API_KEY>" }
    }
  }
}
```

## Security notes

- **The SSE endpoint exposes all 299 admin tools.** The bearer key
  (`KEYCLOAK_MCP_SSE_API_KEY`) is mandatory — the server refuses to bind
  `0.0.0.0` without it. Keep the endpoint behind Cloudflare/VPN even so.
- **Least privilege**: use a dedicated Keycloak client (service account) with
  only the roles the assistant needs (`view-*` for read-only, `manage-users` at
  most). Never wire the master super-admin.
- **Routing caveat**: this uses a dedicated hostname because the MCP SSE
  transport advertises an absolute `/messages/` path that breaks under
  `mcp.daniloromano.dev/<slug>` + StripPrefix. See the commented path-based
  variant in `manifests.yaml`.
