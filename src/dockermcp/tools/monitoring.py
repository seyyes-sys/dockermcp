"""Monitoring proactif des conteneurs Docker."""

from __future__ import annotations

import contextlib
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from dockermcp.auth import Role
from dockermcp.config import get_settings
from dockermcp.docker_client import get_client
from dockermcp.models import HealthReportParams
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
        """Rapport de santé synthétique : unhealthy, flapping, crashed, high CPU/mém."""
        settings = get_settings()
        client = get_client()
        all_c = await to_thread(client.containers.list, all=params.include_stopped)
        unhealthy: list[dict[str, Any]] = []
        flapping: list[dict[str, Any]] = []
        crashed: list[dict[str, Any]] = []
        high_cpu: list[dict[str, Any]] = []
        high_mem: list[dict[str, Any]] = []

        for c in all_c:
            attrs = c.attrs
            state = attrs.get("State", {}) or {}
            health = (state.get("Health") or {}).get("Status")
            restart_count = attrs.get("RestartCount", 0)
            base = {
                "name": c.name,
                "id": c.short_id,
                "status": c.status,
                "restart_count": restart_count,
                "health": health,
            }
            if health == "unhealthy":
                unhealthy.append(base)
            if c.status == "restarting" or restart_count >= settings.restart_warn_count:
                flapping.append(base)
            if c.status == "exited" and state.get("ExitCode", 0) not in (0, None):
                crashed.append({**base, "exit_code": state.get("ExitCode")})
            if c.status == "running":
                sample = None
                with contextlib.suppress(Exception):
                    sample = await _container_stats(c)
                if sample is None:
                    continue
                if sample["cpu_pct"] >= settings.cpu_warn_pct:
                    high_cpu.append(sample)
                if sample["mem_pct"] >= settings.mem_warn_pct:
                    high_mem.append(sample)

        alerts_total = sum(map(len, (unhealthy, flapping, crashed, high_cpu, high_mem)))
        return ok(
            {
                "summary": {
                    "containers_total": len(all_c),
                    "alerts_total": alerts_total,
                    "thresholds": {
                        "cpu_warn_pct": settings.cpu_warn_pct,
                        "mem_warn_pct": settings.mem_warn_pct,
                        "restart_warn_count": settings.restart_warn_count,
                    },
                },
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
