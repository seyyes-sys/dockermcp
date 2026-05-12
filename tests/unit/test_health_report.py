"""Tests unitaires du `health_report` enrichi (alertes plates + seuils)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from dockermcp.auth import Role, set_current_role
from dockermcp.server import build_server


def _payload(result: Any) -> dict[str, Any]:
    if isinstance(result, tuple) and len(result) == 2:
        content, structured = result
        if isinstance(structured, dict):
            return structured
        result = content
    if isinstance(result, list) and result:
        text = getattr(result[0], "text", None)
        if text is not None:
            return json.loads(text)
    raise AssertionError(f"Format inattendu : {result!r}")


class _FakeContainer:
    def __init__(
        self,
        name: str,
        status: str = "running",
        health: str | None = None,
        restart_count: int = 0,
        exit_code: int | None = 0,
        oom: bool = False,
    ) -> None:
        self.name = name
        self.short_id = name[:12]
        self.status = status
        self.attrs = {
            "State": {
                "Health": {"Status": health} if health else {},
                "ExitCode": exit_code,
                "OOMKilled": oom,
            },
            "RestartCount": restart_count,
        }

    def stats(self, stream: bool = False) -> dict[str, Any]:  # pragma: no cover - non utilisé ici
        return {}


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> list[_FakeContainer]:
    containers = [
        _FakeContainer("ok-app", status="running", health="healthy"),
        _FakeContainer("sick-app", status="running", health="unhealthy"),
        _FakeContainer("flap-app", status="restarting", restart_count=5),
        _FakeContainer("dead-app", status="exited", exit_code=137, oom=True),
    ]

    class _Client:
        class containers:
            @staticmethod
            def list(all: bool = False) -> list[_FakeContainer]:
                return containers

    monkeypatch.setattr("dockermcp.tools.monitoring.get_client", lambda: _Client())
    # Court-circuite la collecte de stats live (sinon ouvre le socket Docker).
    monkeypatch.setattr(
        "dockermcp.tools.monitoring._container_stats",
        _stats_stub,
    )
    return containers


async def _stats_stub(container: Any) -> dict[str, Any]:
    return {
        "name": container.name,
        "id": container.short_id,
        "cpu_pct": 5.0,
        "mem_used_mb": 50.0,
        "mem_limit_mb": 1024.0,
        "mem_pct": 5.0,
    }


@pytest.mark.asyncio
async def test_health_report_emits_typed_alerts(fake_client: list[_FakeContainer]) -> None:
    set_current_role(Role.VIEWER)
    server = build_server()
    result = await server.call_tool("health_report", {"params": {}})
    payload = _payload(result)

    assert payload["ok"] is True
    data = payload["data"]
    alerts = data["alerts"]
    kinds = {a["kind"] for a in alerts}

    # On attend au minimum : unhealthy, flapping, crashed, oom.
    assert {"unhealthy", "flapping", "crashed", "oom"}.issubset(kinds)

    # Toutes les alertes ont la structure attendue.
    for alert in alerts:
        assert alert["severity"] in {"warning", "critical"}
        assert alert["container"]
        assert alert["message"]
        assert isinstance(alert["metric"], dict)

    summary = data["summary"]
    assert summary["alerts_total"] == len(alerts)
    assert summary["critical_count"] >= 3  # unhealthy, crashed, oom
    assert summary["warning_count"] >= 1  # flapping


@pytest.mark.asyncio
async def test_health_report_threshold_overrides(fake_client: list[_FakeContainer]) -> None:
    set_current_role(Role.VIEWER)
    server = build_server()

    # restart_threshold=10 → flap-app (restart=5) ne doit plus être flapping
    # (mais reste détecté à cause de status="restarting").
    result = await server.call_tool(
        "health_report",
        {"params": {"restart_threshold": 10}},
    )
    payload = _payload(result)
    flapping_alerts = [a for a in payload["data"]["alerts"] if a["kind"] == "flapping"]
    # status=restarting remonte toujours, mais le seuil utilisé doit être 10.
    assert all(a["metric"]["threshold"] == 10 for a in flapping_alerts)
    assert payload["data"]["summary"]["thresholds"]["restart_count"] == 10


@pytest.mark.asyncio
async def test_health_report_name_filter(fake_client: list[_FakeContainer]) -> None:
    set_current_role(Role.VIEWER)
    server = build_server()
    result = await server.call_tool(
        "health_report",
        {"params": {"name_filter": "sick"}},
    )
    payload = _payload(result)
    assert payload["data"]["summary"]["containers_total"] == 1
    assert all("sick" in a["container"] for a in payload["data"]["alerts"])
