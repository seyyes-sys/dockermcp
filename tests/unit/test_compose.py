"""Tests pour les outils Compose."""

from __future__ import annotations

from pathlib import Path

import pytest

from dockermcp.auth import Role, set_current_role
from dockermcp.config import get_settings
from dockermcp.server import build_server


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_compose_up_rejects_unwhitelisted_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DOCKERMCP_ALLOWED_COMPOSE_ROOTS", raising=False)
    get_settings.cache_clear()
    set_current_role(Role.OPERATOR)
    server = build_server()
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    result = await server.call_tool(
        "compose_up",
        {"params": {"file": str(compose_file)}},
    )
    assert "compose_not_allowed" in str(result)


@pytest.mark.asyncio
async def test_compose_down_requires_confirm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DOCKERMCP_ALLOWED_COMPOSE_ROOTS", str(tmp_path))
    get_settings.cache_clear()
    set_current_role(Role.ADMIN)
    server = build_server()
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    result = await server.call_tool(
        "compose_down",
        {"params": {"file": str(compose_file), "confirm": False}},
    )
    assert "confirmation_required" in str(result)


@pytest.mark.asyncio
async def test_compose_up_forbidden_for_viewer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DOCKERMCP_ALLOWED_COMPOSE_ROOTS", str(tmp_path))
    get_settings.cache_clear()
    set_current_role(Role.VIEWER)
    server = build_server()
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    result = await server.call_tool(
        "compose_up",
        {"params": {"file": str(compose_file)}},
    )
    text = str(result)
    assert "forbidden" in text
    assert "operator" in text
