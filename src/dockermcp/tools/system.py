"""Informations système Docker (version, info, disk usage)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from dockermcp.auth import Role
from dockermcp.docker_client import get_client
from dockermcp.tools._common import ok, to_thread, tool


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def docker_version() -> dict[str, Any]:
        """Retourne la version du daemon et du SDK."""
        client = get_client()
        version = await to_thread(client.version)
        return ok(version)

    @tool(mcp, role=Role.VIEWER)
    async def docker_info() -> dict[str, Any]:
        """Retourne `docker info` (conteneurs, images, ressources, kernel)."""
        client = get_client()
        info = await to_thread(client.info)
        keys = (
            "Containers",
            "ContainersRunning",
            "ContainersPaused",
            "ContainersStopped",
            "Images",
            "ServerVersion",
            "OperatingSystem",
            "OSType",
            "Architecture",
            "NCPU",
            "MemTotal",
            "KernelVersion",
            "DockerRootDir",
            "Driver",
        )
        return ok({k: info.get(k) for k in keys})

    @tool(mcp, role=Role.VIEWER)
    async def disk_usage() -> dict[str, Any]:
        """Retourne l'utilisation disque Docker (`docker system df`)."""
        client = get_client()
        df = await to_thread(client.df)
        summary: dict[str, Any] = {}
        for kind in ("Images", "Containers", "Volumes"):
            items = df.get(kind) or []
            total_size = sum((it.get("Size") or 0) for it in items)
            reclaimable = sum(
                (it.get("Reclaimable") or 0)
                for it in items
                if isinstance(it.get("Reclaimable"), int)
            )
            summary[kind.lower()] = {
                "count": len(items),
                "size_mb": round(total_size / 1_048_576, 2),
                "reclaimable_mb": round(reclaimable / 1_048_576, 2),
            }
        return ok(summary)
