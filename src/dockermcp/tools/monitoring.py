"""Monitoring proactif des conteneurs Docker."""

from __future__ import annotations

import contextlib
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from dockermcp.auth import Role
from dockermcp.config import get_settings
from dockermcp.docker_client import get_client
from dockermcp.models import Alert, HealthReportParams
from dockermcp.tools._common import ok, to_thread, tool


def _cpu_percent(stats: dict[str, Any]) -> float:
    cpu = stats.get("cpu_stats") or {}
    pre = stats.get("precpu_stats") or {}
    cpu_total = (cpu.get("cpu_usage") or {}).get("total_usage", 0)
    pre_total = (pre.get("cpu_usage") or {}).get("total_usage", 0)
    cpu_delta = cpu_total - pre_total
    sys_delta = (cpu.get("system_cpu_usage") or 0) - (pre.get("system_cpu_usage") or 0)
    online = (
        cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
    )
    if cpu_delta <= 0 or sys_delta <= 0:
        return 0.0
    return round(float(cpu_delta) / float(sys_delta) * online * 100.0, 2)


def _mem(stats: dict[str, Any]) -> tuple[float, float, float]:
    mem = stats.get("memory_stats") or {}
    usage = mem.get("usage", 0) - (mem.get("stats", {}) or {}).get("cache", 0)
    limit = mem.get("limit", 0) or 1
    pct = round((usage / limit) * 100.0, 2) if limit else 0.0
    return round(usage / 1_048_576, 2), round(limit / 1_048_576, 2), pct


async def _container_stats(container: Any) -> dict[str, Any]:
    raw = await to_thread(container.stats, stream=False)
    cpu = _cpu_percent(raw)
    mem_used, mem_limit, mem_pct = _mem(raw)
    return {
        "name": container.name,
        "id": container.short_id,
        "cpu_pct": cpu,
        "mem_used_mb": mem_used,
        "mem_limit_mb": mem_limit,
        "mem_pct": mem_pct,
    }


class TopParams(BaseModel):
    by: str = Field(default="cpu", pattern="^(cpu|mem)$")
    limit: int = Field(default=5, ge=1, le=50)


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def container_stats(params: TopParams) -> dict[str, Any]:
        """Échantillonne CPU/mémoire des conteneurs running et trie."""
        client = get_client()
        containers = await to_thread(client.containers.list)
        samples = []
        for c in containers:
            with contextlib.suppress(Exception):
                samples.append(await _container_stats(c))
        key = "cpu_pct" if params.by == "cpu" else "mem_pct"
        samples.sort(key=lambda s: s.get(key, 0), reverse=True)
        return ok(samples[: params.limit], count=len(samples))

    @tool(mcp, role=Role.VIEWER)
    async def health_report(params: HealthReportParams) -> dict[str, Any]:
        """Rapport de santé synthétique avec liste plate d'alertes typées.

        Détecte : `unhealthy`, `flapping`, `crashed`, `oom`, `high_cpu`, `high_mem`.
        Les seuils peuvent être surchargés par appel (`cpu_threshold`, etc.) ;
        sinon les défauts viennent de `Settings`.

        Le champ ``alerts`` est une liste plate prête à être itérée par un
        orchestrateur (n8n, OpenClaw, …). Les listes catégorisées historiques
        (`unhealthy`, `flapping`…) sont conservées pour rétro-compatibilité.
        """
        settings = get_settings()
        cpu_th = params.cpu_threshold if params.cpu_threshold is not None else settings.cpu_warn_pct
        mem_th = params.mem_threshold if params.mem_threshold is not None else settings.mem_warn_pct
        restart_th = (
            params.restart_threshold
            if params.restart_threshold is not None
            else settings.restart_warn_count
        )

        client = get_client()
        all_c = await to_thread(client.containers.list, all=params.include_stopped)
        if params.name_filter:
            needle = params.name_filter.lower()
            all_c = [c for c in all_c if needle in (c.name or "").lower()]

        unhealthy: list[dict[str, Any]] = []
        flapping: list[dict[str, Any]] = []
        crashed: list[dict[str, Any]] = []
        high_cpu: list[dict[str, Any]] = []
        high_mem: list[dict[str, Any]] = []
        alerts: list[Alert] = []

        for c in all_c:
            attrs = c.attrs
            state = attrs.get("State", {}) or {}
            health = (state.get("Health") or {}).get("Status")
            restart_count = attrs.get("RestartCount", 0)
            exit_code = state.get("ExitCode")
            oom_killed = bool(state.get("OOMKilled"))
            base = {
                "name": c.name,
                "id": c.short_id,
                "status": c.status,
                "restart_count": restart_count,
                "health": health,
            }

            if health == "unhealthy":
                unhealthy.append(base)
                alerts.append(
                    Alert(
                        severity="critical",
                        kind="unhealthy",
                        container=c.name or "",
                        container_id=c.short_id,
                        message=f"{c.name} est marqué unhealthy par son healthcheck.",
                        metric={"health": health, "restart_count": restart_count},
                    )
                )

            if c.status == "restarting" or restart_count >= restart_th:
                flapping.append(base)
                alerts.append(
                    Alert(
                        severity="warning",
                        kind="flapping",
                        container=c.name or "",
                        container_id=c.short_id,
                        message=(
                            f"{c.name} flappe : restart_count={restart_count} (seuil={restart_th})."
                        ),
                        metric={"restart_count": restart_count, "threshold": restart_th},
                    )
                )

            if oom_killed:
                alerts.append(
                    Alert(
                        severity="critical",
                        kind="oom",
                        container=c.name or "",
                        container_id=c.short_id,
                        message=f"{c.name} a été OOMKilled.",
                        metric={"exit_code": exit_code, "restart_count": restart_count},
                    )
                )

            if c.status == "exited" and exit_code not in (0, None):
                crashed.append({**base, "exit_code": exit_code})
                alerts.append(
                    Alert(
                        severity="critical",
                        kind="crashed",
                        container=c.name or "",
                        container_id=c.short_id,
                        message=f"{c.name} s'est arrêté avec exit_code={exit_code}.",
                        metric={"exit_code": exit_code, "restart_count": restart_count},
                    )
                )

            if c.status == "running":
                sample = None
                with contextlib.suppress(Exception):
                    sample = await _container_stats(c)
                if sample is None:
                    continue
                if sample["cpu_pct"] >= cpu_th:
                    high_cpu.append(sample)
                    alerts.append(
                        Alert(
                            severity="warning",
                            kind="high_cpu",
                            container=c.name or "",
                            container_id=c.short_id,
                            message=(
                                f"{c.name} consomme {sample['cpu_pct']}% CPU (seuil={cpu_th}%)."
                            ),
                            metric={"cpu_pct": sample["cpu_pct"], "threshold": cpu_th},
                        )
                    )
                if sample["mem_pct"] >= mem_th:
                    high_mem.append(sample)
                    alerts.append(
                        Alert(
                            severity="warning",
                            kind="high_mem",
                            container=c.name or "",
                            container_id=c.short_id,
                            message=(
                                f"{c.name} consomme {sample['mem_pct']}% mémoire "
                                f"({sample['mem_used_mb']}/{sample['mem_limit_mb']} Mo, "
                                f"seuil={mem_th}%)."
                            ),
                            metric={
                                "mem_pct": sample["mem_pct"],
                                "mem_used_mb": sample["mem_used_mb"],
                                "mem_limit_mb": sample["mem_limit_mb"],
                                "threshold": mem_th,
                            },
                        )
                    )

        critical_count = sum(1 for a in alerts if a.severity == "critical")
        warning_count = sum(1 for a in alerts if a.severity == "warning")

        return ok(
            {
                "summary": {
                    "containers_total": len(all_c),
                    "alerts_total": len(alerts),
                    "critical_count": critical_count,
                    "warning_count": warning_count,
                    "thresholds": {
                        "cpu_pct": cpu_th,
                        "mem_pct": mem_th,
                        "restart_count": restart_th,
                    },
                },
                "alerts": [a.model_dump() for a in alerts],
                "unhealthy": unhealthy,
                "flapping": flapping,
                "crashed": crashed,
                "high_cpu": high_cpu,
                "high_mem": high_mem,
            }
        )

    @tool(mcp, role=Role.VIEWER)
    async def recent_events() -> dict[str, Any]:
        """Retourne les 50 derniers événements Docker (1 h glissante)."""
        import json
        import time

        client = get_client()
        since = int(time.time()) - 3600
        until = int(time.time())

        def _collect() -> list[dict[str, Any]]:
            events: list[dict[str, Any]] = []
            for raw in client.events(since=since, until=until, decode=False):
                try:
                    events.append(json.loads(raw) if isinstance(raw, (bytes, str)) else raw)
                except json.JSONDecodeError:
                    continue
            return events

        events = await to_thread(_collect)
        compact = [
            {
                "time": e.get("time"),
                "type": e.get("Type") or e.get("type"),
                "action": e.get("Action") or e.get("action"),
                "actor": (e.get("Actor") or {}).get("Attributes", {}).get("name"),
                "status": e.get("status"),
            }
            for e in events
        ]
        return ok(compact[-50:], count=len(compact))
