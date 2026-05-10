"""Tests unitaires pour la configuration."""

from __future__ import annotations

from pathlib import Path

from dockermcp.config import Settings


def test_bind_path_disallowed_when_no_whitelist() -> None:
    s = Settings(allowed_bind_roots=[])
    assert s.is_bind_path_allowed("/var/data") is False


def test_bind_path_allowed_inside_whitelist(tmp_path: Path) -> None:
    s = Settings(allowed_bind_roots=[tmp_path])
    sub = tmp_path / "sub"
    sub.mkdir()
    assert s.is_bind_path_allowed(sub) is True
    assert s.is_bind_path_allowed(tmp_path) is True


def test_bind_path_outside_whitelist(tmp_path: Path) -> None:
    s = Settings(allowed_bind_roots=[tmp_path / "ok"])
    (tmp_path / "ok").mkdir()
    assert s.is_bind_path_allowed(tmp_path / "other") is False
