"""Tests d'audit : redaction des secrets dans le journal."""

from __future__ import annotations

import json
import logging

import pytest

from dockermcp.audit import audit
from dockermcp.auth import Role, set_current_role


@pytest.mark.asyncio
async def test_audit_redacts_secrets(caplog: pytest.LogCaptureFixture) -> None:
    set_current_role(Role.OPERATOR)

    @audit("dummy_tool")
    async def dummy(params: dict[str, str]) -> dict[str, bool]:
        return {"ok": True}

    with caplog.at_level(logging.INFO, logger="dockermcp.audit"):
        await dummy({"token": "shh", "harmless": "ok", "Password": "x"})

    records = [json.loads(r.message) for r in caplog.records if r.name == "dockermcp.audit"]
    assert records, "aucun log d'audit produit"
    entry = records[-1]
    assert entry["tool"] == "dummy_tool"
    assert entry["role"] == "operator"
    assert entry["status"] == "ok"
    # params est une liste : [args..., kwargs] ou juste args.
    flat = json.dumps(entry["params"])
    assert "shh" not in flat
    assert "***" in flat
    assert "ok" in flat  # harmless conservé


@pytest.mark.asyncio
async def test_audit_marks_denied(caplog: pytest.LogCaptureFixture) -> None:
    @audit("forbidden_tool")
    async def denied() -> dict[str, object]:
        return {"ok": False, "error": "forbidden"}

    with caplog.at_level(logging.INFO, logger="dockermcp.audit"):
        await denied()
    entry = json.loads(caplog.records[-1].message)
    assert entry["status"] == "denied"
    assert entry["error"] == "forbidden"
