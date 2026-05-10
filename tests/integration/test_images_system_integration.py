"""Tests d'intégration : opérations sur les images via le serveur MCP."""

from __future__ import annotations

from typing import Any

from ._helpers import IT_IMAGE, call_tool_payload


async def test_list_images_includes_alpine(mcp_server: Any) -> None:
    result = await mcp_server.call_tool("list_images", {"params": {}})
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    tags = [tag for img in payload["data"] for tag in (img.get("tags") or [])]
    assert IT_IMAGE in tags


async def test_docker_version(mcp_server: Any) -> None:
    result = await mcp_server.call_tool("docker_version", {})
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    assert "Version" in payload["data"] or "ApiVersion" in payload["data"]


async def test_docker_info(mcp_server: Any) -> None:
    result = await mcp_server.call_tool("docker_info", {})
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    assert "ServerVersion" in payload["data"]
