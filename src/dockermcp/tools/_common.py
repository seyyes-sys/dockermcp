"""Helpers internes pour les modules d'outils.

`tool(mcp, role=...)` est le décorateur composite à utiliser sur chaque
outil. Il combine, dans cet ordre :

    @mcp.tool()
    @audit(name)      # journalisation de l'appel
    @require(role)    # RBAC : refuse si rôle insuffisant
    @safe_tool        # capture des exceptions Docker → payload structuré
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from docker.errors import DockerException
from mcp.server.fastmcp import FastMCP

from dockermcp.audit import audit
from dockermcp.auth import Role, require
from dockermcp.docker_client import DockerUnavailableError, format_docker_error

P = ParamSpec("P")
T = TypeVar("T")


def safe_tool(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[Any]]:
    """Capture les exceptions Docker et retourne un payload structuré."""

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except (DockerException, DockerUnavailableError) as exc:
            return format_docker_error(exc)
        except ValueError as exc:
            return {"ok": False, "error": "invalid_argument", "message": str(exc)}

    return wrapper


async def to_thread(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Wrapper court pour les appels bloquants du SDK Docker."""
    return await asyncio.to_thread(func, *args, **kwargs)


def ok(data: Any = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def tool(
    mcp: FastMCP, *, role: Role
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Any]]]:
    """Enregistre une fonction comme outil MCP avec audit + RBAC + safe_tool."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[Any]]:
        wrapped = audit(func.__name__)(require(role)(safe_tool(func)))
        wrapped.__doc__ = func.__doc__
        wrapped.__name__ = func.__name__
        return mcp.tool()(wrapped)

    return decorator
