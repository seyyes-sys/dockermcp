"""Test de smoke : le serveur se construit et expose les outils attendus."""

from __future__ import annotations

import pytest

from dockermcp.server import build_server


@pytest.mark.asyncio
async def test_server_builds_and_lists_tools() -> None:
    server = build_server()
    tools = await server.list_tools()
    names = {t.name for t in tools}
    expected = {
        "list_containers",
        "inspect_container",
        "container_logs",
        "start_container",
        "stop_container",
        "restart_container",
        "remove_container",
        "exec_in_container",
        "run_container",
        "list_images",
        "pull_image",
        "remove_image",
        "list_volumes",
        "create_volume",
        "remove_volume",
        "list_networks",
        "create_network",
        "remove_network",
        "docker_version",
        "docker_info",
        "disk_usage",
        "container_stats",
        "health_report",
        "recent_events",
        "compose_ps",
        "compose_up",
        "compose_down",
        "compose_logs",
        "compose_restart",
        "compose_build",
        "compose_pull",
    }
    missing = expected - names
    assert not missing, f"Outils manquants : {missing}"
