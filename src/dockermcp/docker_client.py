"""Wrapper unique autour du SDK Docker.

Tout accès au daemon doit passer par `get_client()`. Aucun appel direct à
`docker.from_env()` ailleurs dans le projet.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import docker
from docker import DockerClient
from docker.errors import APIError, DockerException, NotFound

logger = logging.getLogger(__name__)


class DockerUnavailableError(RuntimeError):
    """Daemon Docker injoignable."""


@lru_cache(maxsize=1)
def get_client() -> DockerClient:
    """Retourne un `DockerClient` partagé. Lève `DockerUnavailableError` si KO."""
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:  # inclut APIError, ConnectionError, etc.
        logger.error("Docker daemon unreachable: %s", exc)
        raise DockerUnavailableError(
            "Le daemon Docker est injoignable. Vérifiez qu'il est démarré "
            "et que l'utilisateur a les droits requis."
        ) from exc
    return client


def reset_client() -> None:
    """Invalide le client en cache (utile pour les tests)."""
    get_client.cache_clear()


def format_docker_error(exc: Exception) -> dict[str, Any]:
    """Convertit une exception Docker en payload structuré."""
    if isinstance(exc, NotFound):
        return {"ok": False, "error": "not_found", "message": str(exc)}
    if isinstance(exc, APIError):
        return {
            "ok": False,
            "error": "api_error",
            "status": getattr(exc, "status_code", None),
            "message": exc.explanation or str(exc),
        }
    if isinstance(exc, DockerUnavailableError):
        return {"ok": False, "error": "daemon_unavailable", "message": str(exc)}
    return {"ok": False, "error": "unexpected", "message": str(exc)}
