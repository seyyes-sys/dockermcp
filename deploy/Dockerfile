# syntax=docker/dockerfile:1.7

# ─── Builder ────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Copie minimale pour bénéficier du cache de couche
COPY pyproject.toml README.md ./
COPY src ./src

# Wheel + install dans un préfixe isolé
RUN pip install --upgrade pip build && \
    pip wheel --wheel-dir /wheels ".[http]"

# ─── Runtime ────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DOCKERMCP_TRANSPORT=http \
    DOCKERMCP_HTTP_HOST=0.0.0.0 \
    DOCKERMCP_HTTP_PORT=8765 \
    DOCKERMCP_AUDIT_FILE=/var/log/dockermcp/audit.log

# Utilisateur non-root (gid/uid arbitraire, ajusté via env si besoin)
RUN groupadd --system --gid 10001 dockermcp && \
    useradd --system --uid 10001 --gid 10001 --home /home/dockermcp --create-home dockermcp && \
    mkdir -p /var/log/dockermcp && \
    chown -R dockermcp:dockermcp /var/log/dockermcp

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels dockermcp[http] && rm -rf /wheels

USER dockermcp
WORKDIR /home/dockermcp

EXPOSE 8765

# Healthcheck minimal : vérifie que le module charge et que le client Docker répond
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, docker; docker.DockerClient(base_url=os.environ.get('DOCKER_HOST','unix:///var/run/docker.sock')).ping()" || exit 1

ENTRYPOINT ["python", "-m", "dockermcp"]
