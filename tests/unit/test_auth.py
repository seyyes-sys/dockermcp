"""Tests RBAC / read-only / résolution de tokens."""

from __future__ import annotations

import pytest

from dockermcp import auth
from dockermcp.auth import (
    Role,
    effective_role,
    get_current_role,
    require,
    reset_current_role,
    reset_security_cache,
    resolve_token,
    set_current_role,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKERMCP_TOKENS", raising=False)
    monkeypatch.delenv("DOCKERMCP_READ_ONLY", raising=False)
    monkeypatch.delenv("DOCKERMCP_STDIO_ROLE", raising=False)
    reset_security_cache()
    tok = set_current_role(Role.VIEWER)
    yield
    reset_current_role(tok)
    reset_security_cache()


def test_role_ordering() -> None:
    assert Role.VIEWER < Role.OPERATOR < Role.ADMIN


def test_resolve_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKERMCP_TOKENS", "abc:viewer, def:admin")
    reset_security_cache()
    assert resolve_token("abc") is Role.VIEWER
    assert resolve_token("def") is Role.ADMIN
    assert resolve_token("nope") is None
    assert resolve_token(None) is None


def test_read_only_downgrades_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKERMCP_READ_ONLY", "true")
    reset_security_cache()
    assert effective_role(Role.ADMIN) is Role.VIEWER
    assert effective_role(Role.VIEWER) is Role.VIEWER


@pytest.mark.asyncio
async def test_require_denies_when_role_too_low() -> None:
    @require(Role.ADMIN)
    async def destructive() -> dict[str, str]:
        return {"ok": "yes"}  # type: ignore[return-value]

    set_current_role(Role.OPERATOR)
    result = await destructive()
    assert result["ok"] is False  # type: ignore[index]
    assert result["error"] == "forbidden"  # type: ignore[index]
    assert result["required_role"] == "admin"  # type: ignore[index]


@pytest.mark.asyncio
async def test_require_allows_when_role_sufficient() -> None:
    @require(Role.OPERATOR)
    async def action() -> dict[str, str]:
        return {"ok": "yes"}

    set_current_role(Role.ADMIN)
    result = await action()
    assert result == {"ok": "yes"}


@pytest.mark.asyncio
async def test_read_only_blocks_operator_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKERMCP_READ_ONLY", "1")
    reset_security_cache()

    @require(Role.OPERATOR)
    async def action() -> dict[str, str]:
        return {"ok": "yes"}

    set_current_role(Role.ADMIN)  # rétrogradé à VIEWER par read-only
    result = await action()
    assert result["ok"] is False  # type: ignore[index]
    assert result["error"] == "forbidden"  # type: ignore[index]


def test_get_current_role_default_after_reset() -> None:
    assert get_current_role() in (Role.VIEWER, Role.OPERATOR, Role.ADMIN)
    assert auth.Role.parse("admin") is Role.ADMIN
    with pytest.raises(ValueError):
        Role.parse("super-admin")
