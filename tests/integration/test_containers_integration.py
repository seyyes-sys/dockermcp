"""Tests d'intégration : opérations sur les conteneurs via le serveur MCP.

Ces tests créent un vrai conteneur alpine et vérifient le cycle de vie
complet : list → inspect → exec → logs → stop → start → remove.
"""

from __future__ import annotations

from typing import Any

import pytest

from ._helpers import IT_PREFIX, call_tool_payload


async def test_list_containers_finds_alpine(mcp_server: Any, alpine_container: Any) -> None:
    result = await mcp_server.call_tool(
        "list_containers",
        {"params": {"all": True, "name_contains": IT_PREFIX}},
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    names = [c["name"] for c in payload["data"]]
    assert alpine_container.name in names


async def test_inspect_container(mcp_server: Any, alpine_container: Any) -> None:
    result = await mcp_server.call_tool(
        "inspect_container",
        {"params": {"container": alpine_container.name}},
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    assert payload["data"]["Name"].lstrip("/") == alpine_container.name
    assert payload["data"]["State"]["Running"] is True


async def test_container_logs(mcp_server: Any, alpine_container: Any) -> None:
    # Laisse au conteneur le temps d'émettre quelques lignes.
    import asyncio

    await asyncio.sleep(2)
    result = await mcp_server.call_tool(
        "container_logs",
        {"params": {"container": alpine_container.name, "tail": 5}},
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    assert "tick" in payload["data"]["logs"]


async def test_exec_in_container(mcp_server: Any, alpine_container: Any) -> None:
    result = await mcp_server.call_tool(
        "exec_in_container",
        {
            "params": {
                "container": alpine_container.name,
                "cmd": ["sh", "-c", "echo hello-mcp"],
            }
        },
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    assert payload["data"]["exit_code"] == 0
    assert "hello-mcp" in payload["data"]["stdout"]


async def test_stop_then_start(mcp_server: Any, alpine_container: Any) -> None:
    stop_result = await mcp_server.call_tool(
        "stop_container",
        {"params": {"container": alpine_container.name}},
    )
    payload = call_tool_payload(stop_result)
    assert payload["ok"] is True
    assert payload["data"]["status"] in {"exited", "stopped"}

    start_result = await mcp_server.call_tool(
        "start_container",
        {"params": {"container": alpine_container.name}},
    )
    payload = call_tool_payload(start_result)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "running"


async def test_remove_requires_admin_and_confirm(
    mcp_server: Any, alpine_container: Any, admin_role: None
) -> None:
    # 1. Sans confirm → refusé.
    result = await mcp_server.call_tool(
        "remove_container",
        {"params": {"container": alpine_container.name, "confirm": False, "force": True}},
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is False
    assert payload["error"] == "confirmation_required"

    # 2. Avec confirm=True → suppression OK.
    result = await mcp_server.call_tool(
        "remove_container",
        {"params": {"container": alpine_container.name, "confirm": True, "force": True}},
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is True
    assert payload["data"]["removed"] == alpine_container.name


@pytest.mark.parametrize("bad_path", ["/etc", "C:\\Windows"])
async def test_run_container_rejects_unwhitelisted_bind(mcp_server: Any, bad_path: str) -> None:
    """Garde de sécurité : un bind hors whitelist doit être refusé."""
    result = await mcp_server.call_tool(
        "run_container",
        {
            "params": {
                "image": "alpine:3.20",
                "name": f"{IT_PREFIX}should-not-exist",
                "binds": {bad_path: "/mnt"},
                "detach": True,
            }
        },
    )
    payload = call_tool_payload(result)
    assert payload["ok"] is False
    assert payload["error"] == "bind_not_allowed"
