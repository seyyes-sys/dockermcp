"""Sécurité : rôles RBAC, tokens, mode lecture seule.

Le serveur DockerMCP donne accès à des opérations destructives sur Docker.
L'accès est contrôlé selon trois rôles :

- ``viewer``   → lecture seule (list, inspect, logs, stats, health, info)
- ``operator`` → viewer + actions non destructives (start/stop/restart/exec,
                 run_container, pull_image, create_volume/network)
- ``admin``    → operator + actions destructives (remove_*)

Mécanismes :

1. **stdio** (transport local) : le rôle est fixé au démarrage par
   ``DOCKERMCP_STDIO_ROLE`` (défaut ``operator``). Personne d'autre que
   l'utilisateur qui lance le process ne peut s'y connecter.
2. **HTTP / SSE** : un middleware exige un header
   ``Authorization: Bearer <token>``. Le mapping
   ``DOCKERMCP_TOKENS=token1:admin,token2:viewer`` associe chaque token
   à un rôle.
3. **Read-only global** : ``DOCKERMCP_READ_ONLY=true`` rétrograde
   silencieusement tous les rôles à ``viewer``.
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from enum import IntEnum
from functools import lru_cache, wraps
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)


class Role(IntEnum):
    """Rôles ordonnés par niveau de privilège."""

    VIEWER = 10
    OPERATOR = 20
    ADMIN = 30

    @classmethod
    def parse(cls, value: str) -> Role:
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:  # pragma: no cover - validation triviale
            raise ValueError(f"Rôle inconnu: {value!r}") from exc


# ContextVar : rôle effectif pour la requête courante.
_current_role: ContextVar[Role] = ContextVar("dockermcp_role", default=Role.VIEWER)


def get_current_role() -> Role:
    return _current_role.get()


def set_current_role(role: Role) -> Any:  # token contextuel
    return _current_role.set(role)


def reset_current_role(token: Any) -> None:
    _current_role.reset(token)


# ---------- configuration ----------


def _parse_tokens(raw: str | None) -> dict[str, Role]:
    """Parse ``token1:admin,token2:viewer`` en mapping {token: Role}."""
    if not raw:
        return {}
    out: dict[str, Role] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.warning("Token mal formé ignoré (attendu 'token:role').")
            continue
        token, role_name = entry.split(":", 1)
        token = token.strip()
        if not token:
            continue
        try:
            out[token] = Role.parse(role_name)
        except ValueError:
            logger.warning("Rôle inconnu pour un token, ignoré.")
    return out


@lru_cache(maxsize=1)
def get_token_map() -> dict[str, Role]:
    return _parse_tokens(os.getenv("DOCKERMCP_TOKENS"))


@lru_cache(maxsize=1)
def is_read_only() -> bool:
    return os.getenv("DOCKERMCP_READ_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_stdio_role() -> Role:
    raw = os.getenv("DOCKERMCP_STDIO_ROLE", "operator")
    try:
        return Role.parse(raw)
    except ValueError:
        logger.warning("DOCKERMCP_STDIO_ROLE invalide (%r), repli sur 'viewer'.", raw)
        return Role.VIEWER


def reset_security_cache() -> None:
    """Réinitialise les caches (utile pour les tests)."""
    get_token_map.cache_clear()
    is_read_only.cache_clear()
    get_stdio_role.cache_clear()


# ---------- résolution token → rôle (HTTP) ----------


def resolve_token(token: str | None) -> Role | None:
    """Retourne le rôle pour un token donné, ou None si invalide."""
    if not token:
        return None
    mapping = get_token_map()
    # Comparaison à temps constant pour éviter le timing attack.
    for known, role in mapping.items():
        if secrets.compare_digest(token, known):
            return role
    return None


def effective_role(role: Role) -> Role:
    """Applique le mode lecture seule si activé."""
    if is_read_only() and role > Role.VIEWER:
        return Role.VIEWER
    return role


# ---------- décorateur RBAC ----------

P = ParamSpec("P")
T = TypeVar("T")


def require(min_role: Role) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[Any]]]:
    """Refuse l'appel d'un outil si le rôle courant est insuffisant.

    À placer **après** ``@safe_tool`` afin que la valeur d'erreur structurée
    soit retournée au client MCP.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            current = effective_role(get_current_role())
            if current < min_role:
                logger.warning(
                    "Accès refusé à %s (rôle=%s, requis=%s).",
                    func.__name__,
                    current.name.lower(),
                    min_role.name.lower(),
                )
                return {
                    "ok": False,
                    "error": "forbidden",
                    "message": (
                        f"Outil '{func.__name__}' réservé au rôle "
                        f"'{min_role.name.lower()}' (rôle courant: "
                        f"'{current.name.lower()}')."
                    ),
                    "required_role": min_role.name.lower(),
                    "current_role": current.name.lower(),
                }
            return await func(*args, **kwargs)

        # Marqueur introspectable (utile pour la doc / les tests).
        wrapper.__dockermcp_required_role__ = min_role  # type: ignore[attr-defined]
        return wrapper

    return decorator
