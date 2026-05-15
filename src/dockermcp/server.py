"""Construction et lancement du serveur FastMCP DockerMCP."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from dockermcp import __version__, prompts, resources
from dockermcp.auth import get_stdio_role, reset_current_role, resolve_token, set_current_role
from dockermcp.tools import (
    compose,
    containers,
    images,
    monitoring,
    networks,
    system,
    volumes,
)

logger = logging.getLogger(__name__)

Transport = Literal["stdio", "sse", "streamable-http"]


def _transport_security() -> Any:
    """Construit ``TransportSecuritySettings`` depuis l'environnement.

    Variables :
      - ``DOCKERMCP_ALLOWED_HOSTS`` : CSV de Host autorisés (ex:
        ``dockermcp.hexotik.ovh,dockermcp.local``). En sus de localhost.
      - ``DOCKERMCP_ALLOWED_ORIGINS`` : CSV d'Origin autorisés (CORS).
      - ``DOCKERMCP_DISABLE_DNS_REBIND`` : ``true`` pour désactiver complètement
        la protection (déconseillé sauf reverse-proxy strict).

    Retourne ``None`` si rien n'est configuré (défaut SDK).
    """
    hosts = [h.strip() for h in os.getenv("DOCKERMCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    origins = [
        o.strip() for o in os.getenv("DOCKERMCP_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]
    disable = os.getenv("DOCKERMCP_DISABLE_DNS_REBIND", "").lower() in ("1", "true", "yes")
    if not hosts and not origins and not disable:
        return None

    from mcp.server.transport_security import TransportSecuritySettings

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=not disable,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


def build_server() -> FastMCP:
    """Crée le serveur FastMCP avec tous les outils enregistrés."""
    mcp = FastMCP(
        name="dockermcp",
        instructions=(
            "Serveur MCP pour administrer et monitorer un daemon Docker. "
            "Accès soumis à RBAC : viewer (lecture), operator (actions), "
            "admin (destructives). Les opérations destructives exigent confirm=True."
        ),
        transport_security=_transport_security(),
    )
    for module in (containers, images, volumes, networks, system, monitoring, compose):
        module.register(mcp)
    resources.register(mcp)
    prompts.register(mcp)
    logger.info("DockerMCP v%s prêt.", __version__)
    return mcp


def run(
    transport: Transport = "stdio",
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Lance le serveur dans le transport demandé.

    - ``stdio`` (défaut) : transport local, rôle fixé par ``DOCKERMCP_STDIO_ROLE``.
    - ``streamable-http`` / ``sse`` : expose une API HTTP protégée par token
      bearer (cf. ``DOCKERMCP_TOKENS``). Bind par défaut sur ``127.0.0.1`` —
      à exposer uniquement derrière un reverse proxy TLS.
    """
    mcp = build_server()

    if transport == "stdio":
        role = get_stdio_role()
        set_current_role(role)
        logger.info("Transport=stdio, rôle=%s", role.name.lower())
        mcp.run()
        return

    _run_http(mcp, transport=transport, host=host, port=port)


def _run_http(mcp: FastMCP, *, transport: str, host: str, port: int) -> None:
    """Lance le serveur HTTP avec middleware bearer token."""
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import JSONResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Dépendances HTTP manquantes. Installez-les avec `pip install dockermcp[http]`."
        ) from exc

    class TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Any:
            auth_header = request.headers.get("authorization", "")
            token: str | None = None
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            role = resolve_token(token)
            if role is None:
                client_ip = request.client.host if request.client else "?"
                logger.warning(
                    "Auth refusée pour %s %s (IP=%s)",
                    request.method,
                    request.url.path,
                    client_ip,
                )
                return JSONResponse(
                    {
                        "error": "unauthorized",
                        "message": "Token bearer invalide ou manquant.",
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            ctx_token = set_current_role(role)
            try:
                return await call_next(request)
            finally:
                reset_current_role(ctx_token)

    sub_app = mcp.sse_app() if transport == "sse" else mcp.streamable_http_app()

    app = Starlette(
        middleware=[Middleware(TokenAuthMiddleware)],
        routes=sub_app.routes,
        lifespan=sub_app.router.lifespan_context,
    )

    logger.info("Transport=%s, écoute sur %s:%s", transport, host, port)
    uvicorn.run(app, host=host, port=port, log_config=None)


def parse_transport(value: str | None) -> Transport:
    v = (value or "stdio").strip().lower()
    if v == "http":
        return "streamable-http"
    if v in ("stdio", "sse", "streamable-http"):
        return v  # type: ignore[return-value]
    raise ValueError(f"Transport inconnu: {value!r}")


def transport_from_env() -> Transport:
    return parse_transport(os.getenv("DOCKERMCP_TRANSPORT"))
