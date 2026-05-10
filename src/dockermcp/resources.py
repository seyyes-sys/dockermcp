"""Ressources MCP exposées par DockerMCP.

Une ressource est un endpoint en lecture seule identifié par une URI. Le
LLM peut s'y abonner ou les lire à la demande sans appeler explicitement
un outil. Toutes les ressources requièrent le rôle ``viewer`` (qui est le
niveau le plus bas et est donc accessible à tous les rôles).

URIs exposées :

- ``docker://containers``                — liste JSON de tous les conteneurs
- ``docker://containers/{id_or_name}``   — `docker inspect` complet
- ``docker://containers/{id_or_name}/logs`` — 200 dernières lignes de logs
- ``docker://system/info``               — info synthétique du daemon
- ``docker://system/disk``               — utilisation disque
- ``docker://health``                    — rapport de santé synthétique
"""

from __future__ import annotations

import json
import logging
from typing import Any

from docker.errors import DockerException
from mcp.server.fastmcp import FastMCP

from dockermcp.auth import Role, effective_role, get_current_role
from dockermcp.docker_client import DockerUnavailableError, format_docker_error, get_client
from dockermcp.tools._common import to_thread

logger = logging.getLogger(__name__)


def _check_role() -> dict[str, Any] | None:
    """Vérifie que le rôle courant a au moins le niveau viewer."""
    if effective_role(get_current_role()) < Role.VIEWER:
        return {"ok": False, "error": "forbidden", "message": "Ressource réservée."}
    return None


def _safe(payload: Any) -> str:
    """Sérialise un payload en JSON et capture les erreurs Docker."""
    try:
        return json.dumps(payload, default=str, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "error": "serialization", "message": str(exc)})


async def _safe_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await to_thread(func, *args, **kwargs)
    except (DockerException, DockerUnavailableError) as exc:
        return format_docker_error(exc)


def register(mcp: FastMCP) -> None:
    @mcp.resource("docker://containers", mime_type="application/json")
    async def list_containers_resource() -> str:
        """Liste de tous les conteneurs (running et arrêtés)."""
        if err := _check_role():
            return _safe(err)
        client = get_client()
        containers = await _safe_call(client.containers.list, all=True)
        if isinstance(containers, dict):
            return _safe(containers)
        data = [
            {
                "id": c.short_id,
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image and c.image.tags else None,
            }
            for c in containers
        ]
        return _safe({"ok": True, "data": data, "count": len(data)})

    @mcp.resource(
        "docker://containers/{name}",
        mime_type="application/json",
    )
    async def container_inspect_resource(name: str) -> str:
        """Attributs détaillés d'un conteneur (`docker inspect`)."""
        if err := _check_role():
            return _safe(err)
        client = get_client()
        container = await _safe_call(client.containers.get, name)
        if isinstance(container, dict):
            return _safe(container)
        return _safe({"ok": True, "data": container.attrs})

    @mcp.resource(
        "docker://containers/{name}/logs",
        mime_type="text/plain",
    )
    async def container_logs_resource(name: str) -> str:
        """200 dernières lignes de logs d'un conteneur."""
        if err := _check_role():
            return _safe(err)
        client = get_client()
        container = await _safe_call(client.containers.get, name)
        if isinstance(container, dict):
            return _safe(container)
        raw = await _safe_call(container.logs, tail=200, timestamps=True, stdout=True, stderr=True)
        if isinstance(raw, dict):
            return _safe(raw)
        return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

    @mcp.resource("docker://system/info", mime_type="application/json")
    async def system_info_resource() -> str:
        """`docker info` synthétique."""
        if err := _check_role():
            return _safe(err)
        client = get_client()
        info = await _safe_call(client.info)
        return _safe(info)

    @mcp.resource("docker://system/disk", mime_type="application/json")
    async def system_disk_resource() -> str:
        """Utilisation disque Docker (`docker system df`)."""
        if err := _check_role():
            return _safe(err)
        client = get_client()
        df = await _safe_call(client.df)
        return _safe(df)

    @mcp.resource("docker://health", mime_type="application/json")
    async def health_resource() -> str:
        """Rapport de santé synthétique (raccourci pour `health_report`)."""
        if err := _check_role():
            return _safe(err)
        # Réutilise la logique de l'outil monitoring.health_report directement.
        from dockermcp.config import get_settings

        settings = get_settings()
        client = get_client()
        all_c = await _safe_call(client.containers.list, all=True)
        if isinstance(all_c, dict):
            return _safe(all_c)
        unhealthy = [
            {"name": c.name, "id": c.short_id}
            for c in all_c
            if (c.attrs.get("State", {}).get("Health") or {}).get("Status") == "unhealthy"
        ]
        flapping = [
            {
                "name": c.name,
                "id": c.short_id,
                "restart_count": c.attrs.get("RestartCount", 0),
            }
            for c in all_c
            if c.status == "restarting"
            or c.attrs.get("RestartCount", 0) >= settings.restart_warn_count
        ]
        crashed = [
            {
                "name": c.name,
                "id": c.short_id,
                "exit_code": c.attrs.get("State", {}).get("ExitCode"),
            }
            for c in all_c
            if c.status == "exited" and c.attrs.get("State", {}).get("ExitCode", 0) not in (0, None)
        ]
        return _safe(
            {
                "ok": True,
                "data": {
                    "containers_total": len(all_c),
                    "unhealthy": unhealthy,
                    "flapping": flapping,
                    "crashed": crashed,
                },
            }
        )
