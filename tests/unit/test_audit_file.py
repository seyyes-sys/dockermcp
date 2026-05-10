"""Tests pour l'audit fichier rotatif."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from dockermcp.__main__ import _setup_audit_file
from dockermcp.audit import audit
from dockermcp.auth import Role, set_current_role


@pytest.fixture
def _isolate_audit_logger() -> None:
    """Détache les handlers fichier après le test pour éviter les fuites."""
    yield
    audit_logger = logging.getLogger("dockermcp.audit")
    for h in list(audit_logger.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):  # type: ignore[attr-defined]
            audit_logger.removeHandler(h)
            h.close()


@pytest.mark.asyncio
async def test_audit_file_writes_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _isolate_audit_logger: None
) -> None:
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("DOCKERMCP_AUDIT_FILE", str(log_path))
    monkeypatch.delenv("DOCKERMCP_AUDIT_MAX_BYTES", raising=False)
    monkeypatch.delenv("DOCKERMCP_AUDIT_BACKUPS", raising=False)

    _setup_audit_file()
    set_current_role(Role.OPERATOR)

    @audit("dummy")
    async def call() -> dict[str, bool]:
        return {"ok": True}

    for _ in range(3):
        await call()

    # Force le flush.
    for h in logging.getLogger("dockermcp.audit").handlers:
        h.flush()

    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 3
    # Chaque ligne contient un timestamp suivi du payload JSON.
    payload = json.loads(lines[0].split(" ", 2)[2])
    assert payload["tool"] == "dummy"
    assert payload["role"] == "operator"
    assert payload["status"] == "ok"


@pytest.mark.asyncio
async def test_audit_file_rotates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _isolate_audit_logger: None
) -> None:
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("DOCKERMCP_AUDIT_FILE", str(log_path))
    monkeypatch.setenv("DOCKERMCP_AUDIT_MAX_BYTES", "256")  # rotation très rapide
    monkeypatch.setenv("DOCKERMCP_AUDIT_BACKUPS", "2")

    _setup_audit_file()
    set_current_role(Role.OPERATOR)

    @audit("dummy")
    async def call() -> dict[str, bool]:
        return {"ok": True}

    for _ in range(20):
        await call()
    for h in logging.getLogger("dockermcp.audit").handlers:
        h.flush()

    # Au moins un fichier de backup doit exister.
    backups = sorted(tmp_path.glob("audit.log*"))
    assert len(backups) >= 2, f"Pas assez de fichiers : {backups}"
    # Le nombre total ne dépasse pas backupCount + 1.
    assert len(backups) <= 3
