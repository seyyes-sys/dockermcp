"""Tests des gardes : RBAC + confirm=True sur opérations destructives."""

from __future__ import annotations

import pytest

from dockermcp.auth import Role, set_current_role
from dockermcp.server import build_server


@pytest.mark.asyncio
async def test_remove_container_forbidden_for_operator() -> None:
    set_current_role(Role.OPERATOR)
    server = build_server()
    result = await server.call_tool(
        "remove_container",
        {"params": {"container": "ghost", "confirm": True}},
    )
    text = str(result)
    assert "forbidden" in text
    assert "admin" in text


@pytest.mark.asyncio
async def test_remove_container_requires_confirm_when_admin() -> None:
    set_current_role(Role.ADMIN)
    server = build_server()
    result = await server.call_tool(
        "remove_container",
        {"params": {"container": "ghost", "confirm": False}},
    )
    text = str(result)
    assert "confirmation_required" in text


@pytest.mark.asyncio
async def test_start_container_forbidden_for_viewer() -> None:
    set_current_role(Role.VIEWER)
    server = build_server()
    result = await server.call_tool(
        "start_container",
        {"params": {"container": "ghost"}},
    )
    text = str(result)
    assert "forbidden" in text
    assert "operator" in text
