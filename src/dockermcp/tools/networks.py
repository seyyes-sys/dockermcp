"""Outils MCP pour gérer les réseaux Docker."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from dockermcp.auth import Role
from dockermcp.docker_client import get_client
from dockermcp.models import ConfirmDestructive
from dockermcp.tools._common import ok, to_thread, tool


class NetworkRef(BaseModel):
    network: str = Field(description="Nom ou ID du réseau.")


class CreateNetworkParams(BaseModel):
    name: str
    driver: str = "bridge"
    internal: bool = False
    labels: dict[str, str] = Field(default_factory=dict)


class RemoveNetworkParams(NetworkRef, ConfirmDestructive):
    pass


def _summarize_network(n: Any) -> dict[str, Any]:
    return {
        "id": n.short_id,
        "name": n.name,
        "driver": n.attrs.get("Driver"),
        "scope": n.attrs.get("Scope"),
        "containers": list((n.attrs.get("Containers") or {}).keys()),
    }


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def list_networks() -> dict[str, Any]:
        """Liste les réseaux Docker."""
        client = get_client()
        nets = await to_thread(client.networks.list)
        return ok([_summarize_network(n) for n in nets], count=len(nets))

    @tool(mcp, role=Role.OPERATOR)
    async def create_network(params: CreateNetworkParams) -> dict[str, Any]:
        """Crée un réseau Docker."""
        client = get_client()
        net = await to_thread(
            client.networks.create,
            name=params.name,
            driver=params.driver,
            internal=params.internal,
            labels=params.labels or None,
        )
        return ok(_summarize_network(net))

    @tool(mcp, role=Role.ADMIN)
    async def remove_network(params: RemoveNetworkParams) -> dict[str, Any]:
        """Supprime un réseau. Opération destructive : `confirm=True` requis."""
        if not params.confirm:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Passez confirm=True pour supprimer le réseau.",
            }
        client = get_client()
        net = await to_thread(client.networks.get, params.network)
        await to_thread(net.remove)
        return ok({"removed": params.network})
