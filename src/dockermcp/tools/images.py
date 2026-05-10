"""Outils MCP pour gérer les images Docker."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from dockermcp.auth import Role
from dockermcp.docker_client import get_client
from dockermcp.models import ConfirmDestructive
from dockermcp.tools._common import ok, to_thread, tool


class ListImagesParams(BaseModel):
    name: str | None = Field(default=None, description="Filtre sur le nom (`repo` ou `repo:tag`).")
    dangling: bool | None = None


class ImageRef(BaseModel):
    image: str = Field(description="Nom (avec ou sans tag) ou ID d'image.")


class PullImageParams(BaseModel):
    repository: str
    tag: str = "latest"


class RemoveImageParams(ImageRef, ConfirmDestructive):
    force: bool = False


def _summarize_image(img: Any) -> dict[str, Any]:
    return {
        "id": img.short_id,
        "tags": img.tags,
        "size_mb": round((img.attrs.get("Size") or 0) / 1_048_576, 2),
        "created": img.attrs.get("Created"),
    }


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def list_images(params: ListImagesParams) -> dict[str, Any]:
        """Liste les images locales."""
        filters: dict[str, Any] = {}
        if params.dangling is not None:
            filters["dangling"] = params.dangling
        client = get_client()
        images = await to_thread(client.images.list, name=params.name, filters=filters or None)
        return ok([_summarize_image(i) for i in images], count=len(images))

    @tool(mcp, role=Role.OPERATOR)
    async def pull_image(params: PullImageParams) -> dict[str, Any]:
        """Télécharge une image depuis un registre."""
        client = get_client()
        image = await to_thread(client.images.pull, params.repository, tag=params.tag)
        return ok(_summarize_image(image))

    @tool(mcp, role=Role.ADMIN)
    async def remove_image(params: RemoveImageParams) -> dict[str, Any]:
        """Supprime une image. Opération destructive : `confirm=True` requis."""
        if not params.confirm:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Passez confirm=True pour supprimer l'image.",
            }
        client = get_client()
        await to_thread(client.images.remove, image=params.image, force=params.force)
        return ok({"removed": params.image})
