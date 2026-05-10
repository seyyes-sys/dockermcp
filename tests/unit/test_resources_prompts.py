"""Smoke tests pour les ressources et prompts MCP."""

from __future__ import annotations

import pytest

from dockermcp.auth import Role, set_current_role
from dockermcp.server import build_server


@pytest.mark.asyncio
async def test_server_lists_expected_resources() -> None:
    set_current_role(Role.VIEWER)
    server = build_server()
    static = await server.list_resources()
    templates = await server.list_resource_templates()
    static_uris = {str(r.uri) for r in static}
    template_uris = {t.uriTemplate for t in templates}
    assert "docker://containers" in static_uris
    assert "docker://system/info" in static_uris
    assert "docker://system/disk" in static_uris
    assert "docker://health" in static_uris
    assert "docker://containers/{name}" in template_uris
    assert "docker://containers/{name}/logs" in template_uris


@pytest.mark.asyncio
async def test_server_lists_expected_prompts() -> None:
    server = build_server()
    prompts = await server.list_prompts()
    names = {p.name for p in prompts}
    assert {
        "diagnose_container",
        "triage_health",
        "incident_postmortem",
        "explain_compose",
    } <= names


@pytest.mark.asyncio
async def test_diagnose_prompt_renders() -> None:
    server = build_server()
    result = await server.get_prompt("diagnose_container", {"name": "api-prod"})
    assert result.messages, "le prompt doit produire au moins un message"
    rendered = "".join(
        m.content.text  # type: ignore[union-attr]
        for m in result.messages
        if hasattr(m.content, "text")
    )
    assert "api-prod" in rendered
    assert "diagnostique" in rendered.lower()
