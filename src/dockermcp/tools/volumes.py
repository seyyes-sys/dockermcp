"""Outils MCP pour gérer les volumes Docker."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from dockermcp.auth import Role
from dockermcp.docker_client import get_client
from dockermcp.models import ConfirmDestructive
from dockermcp.tools._common import ok, to_thread, tool


class VolumeRef(BaseModel):
    name: str = Field(description="Nom du volume.")


class CreateVolumeParams(BaseModel):
    name: str
    driver: str = "local"
    labels: dict[str, str] = Field(default_factory=dict)


class RemoveVolumeParams(VolumeRef, ConfirmDestructive):
    force: bool = False


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def list_volumes() -> dict[str, Any]:
        """Liste tous les volumes Docker."""
        client = get_client()
        result = await to_thread(client.volumes.list)
        return ok(
            [
                {
                    "name": v.name,
                    "driver": v.attrs.get("Driver"),
                    "mountpoint": v.attrs.get("Mountpoint"),
                }
                for v in result
            ],
            count=len(result),
        )

    @tool(mcp, role=Role.OPERATOR)
    async def create_volume(params: CreateVolumeParams) -> dict[str, Any]:
        """Crée un volume Docker nommé."""
        client = get_client()
        vol = await to_thread(
            client.volumes.create,
            name=params.name,
            driver=params.driver,
            labels=params.labels or None,
        )
        return ok({"name": vol.name, "driver": vol.attrs.get("Driver")})

    @tool(mcp, role=Role.ADMIN)
    async def remove_volume(params: RemoveVolumeParams) -> dict[str, Any]:
        """Supprime un volume. Opération destructive : `confirm=True` requis."""
        if not params.confirm:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Passez confirm=True pour supprimer le volume.",
            }
        client = get_client()
        vol = await to_thread(client.volumes.get, params.name)
        await to_thread(vol.remove, force=params.force)
        return ok({"removed": params.name})
