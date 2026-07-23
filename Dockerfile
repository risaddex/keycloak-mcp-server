# syntax=docker/dockerfile:1

# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install into /app/.venv using the locked dependencies (with the "sse" extra so
# the HTTP transport / uvicorn / starlette are available).
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra sse

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user.
RUN groupadd -r app && useradd -r -g app -u 10001 app

WORKDIR /app
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

USER app
EXPOSE 8080

# SSE transport bound to all interfaces so k8s can route to it. Our server
# REFUSES to start on a non-loopback host unless KEYCLOAK_MCP_SSE_API_KEY is set,
# so the deployment must provide that key (see deploy/homelab/).
ENTRYPOINT ["keycloak-mcp-server"]
CMD ["--transport", "sse", "--host", "0.0.0.0", "--port", "8080"]
