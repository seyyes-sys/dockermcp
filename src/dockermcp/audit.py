"""Journal d'audit : trace tout appel d'outil MCP.

Émet une ligne JSON sur le logger ``dockermcp.audit`` (stderr par défaut)
contenant : horodatage, rôle, outil, paramètres redacted, statut, durée.

Aucun secret n'est journalisé : les clés contenant ``token``, ``password``,
``secret``, ``key``, ``authorization`` sont remplacées par ``"***"``.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel

from dockermcp.auth import get_current_role

audit_logger = logging.getLogger("dockermcp.audit")

_REDACT_KEYS = {"token", "password", "secret", "key", "authorization", "auth"}

P = ParamSpec("P")
T = TypeVar("T")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in _REDACT_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, BaseModel):
        return _redact(value.model_dump())
    return value


def audit(tool_name: str) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Any]]]:
    """Décorateur qui journalise l'appel d'un outil MCP."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            started = time.perf_counter()
            role = get_current_role().name.lower()
            params_repr = _redact([*args, kwargs] if kwargs else list(args))
            status = "ok"
            error: str | None = None
            try:
                result = await func(*args, **kwargs)
                if isinstance(result, dict) and result.get("ok") is False:
                    status = "denied"
                    error = str(result.get("error"))
                return result
            except Exception as exc:
                status = "error"
                error = type(exc).__name__
                raise
            finally:
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                payload = {
                    "tool": tool_name,
                    "role": role,
                    "status": status,
                    "duration_ms": duration_ms,
                    "params": params_repr,
                }
                if error:
                    payload["error"] = error
                audit_logger.info(json.dumps(payload, default=str, ensure_ascii=False))

        return wrapper

    return decorator
