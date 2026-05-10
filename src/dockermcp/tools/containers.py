"""Outils MCP pour gérer les conteneurs Docker."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from dockermcp.auth import Role
from dockermcp.config import get_settings
from dockermcp.docker_client import get_client
from dockermcp.models import (
    ContainerRef,
    ExecParams,
    ListContainersParams,
    LogsParams,
    RemoveContainerParams,
    RunContainerParams,
)
from dockermcp.tools._common import ok, to_thread, tool


def _summarize(container: Any) -> dict[str, Any]:
    attrs = container.attrs
    state = attrs.get("State", {})
    image_name: str | None = None
    if container.image and container.image.tags:
        image_name = container.image.tags[0]
    else:
        image_name = attrs.get("Config", {}).get("Image")
    return {
        "id": container.short_id,
        "name": container.name,
        "image": image_name,
        "status": container.status,
        "health": state.get("Health", {}).get("Status"),
        "started_at": state.get("StartedAt"),
        "restart_count": attrs.get("RestartCount", 0),
        "ports": attrs.get("NetworkSettings", {}).get("Ports", {}),
        "labels": attrs.get("Config", {}).get("Labels") or {},
    }


def _matches_prefix(name: str) -> bool:
    prefix = get_settings().name_prefix
    return prefix is None or name.startswith(prefix)


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def list_containers(params: ListContainersParams) -> dict[str, Any]:
        """Liste les conteneurs Docker avec filtres optionnels."""
        filters: dict[str, Any] = {}
        if params.label:
            filters["label"] = params.label
        client = get_client()
        containers = await to_thread(
            client.containers.list, all=params.all, filters=filters or None
        )
        result = []
        for c in containers:
            name = c.name or ""
            if not _matches_prefix(name):
                continue
            if params.name_contains and params.name_contains.lower() not in name.lower():
                continue
            result.append(_summarize(c))
            if len(result) >= params.limit:
                break
        return ok(result, count=len(result))

    @tool(mcp, role=Role.VIEWER)
    async def inspect_container(params: ContainerRef) -> dict[str, Any]:
        """Retourne les attributs détaillés (`docker inspect`) d'un conteneur."""
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        return ok(container.attrs)

    @tool(mcp, role=Role.VIEWER)
    async def container_logs(params: LogsParams) -> dict[str, Any]:
        """Récupère les dernières lignes de logs d'un conteneur."""
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        kwargs: dict[str, Any] = {
            "tail": params.tail,
            "timestamps": params.timestamps,
            "stdout": True,
            "stderr": True,
        }
        if params.since_seconds:
            import time

            kwargs["since"] = int(time.time()) - params.since_seconds
        raw = await to_thread(container.logs, **kwargs)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return ok({"container": container.name, "logs": text})

    @tool(mcp, role=Role.OPERATOR)
    async def start_container(params: ContainerRef) -> dict[str, Any]:
        """Démarre un conteneur arrêté."""
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        await to_thread(container.start)
        await to_thread(container.reload)
        return ok(_summarize(container))

    @tool(mcp, role=Role.OPERATOR)
    async def stop_container(params: ContainerRef) -> dict[str, Any]:
        """Arrête proprement un conteneur (SIGTERM puis SIGKILL après timeout)."""
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        await to_thread(container.stop)
        await to_thread(container.reload)
        return ok(_summarize(container))

    @tool(mcp, role=Role.OPERATOR)
    async def restart_container(params: ContainerRef) -> dict[str, Any]:
        """Redémarre un conteneur."""
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        await to_thread(container.restart)
        await to_thread(container.reload)
        return ok(_summarize(container))

    @tool(mcp, role=Role.ADMIN)
    async def remove_container(params: RemoveContainerParams) -> dict[str, Any]:
        """Supprime un conteneur. Opération destructive : `confirm=True` requis."""
        if not params.confirm:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Passez confirm=True pour supprimer le conteneur.",
            }
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        await to_thread(container.remove, force=params.force, v=params.volumes)
        return ok({"removed": params.container})

    @tool(mcp, role=Role.OPERATOR)
    async def exec_in_container(params: ExecParams) -> dict[str, Any]:
        """Exécute une commande dans un conteneur (sans shell, liste d'arguments)."""
        client = get_client()
        container = await to_thread(client.containers.get, params.container)
        exec_kwargs: dict[str, Any] = {"cmd": params.cmd, "demux": True}
        if params.workdir:
            exec_kwargs["workdir"] = params.workdir
        if params.user:
            exec_kwargs["user"] = params.user
        result = await to_thread(container.exec_run, **exec_kwargs)
        out = result.output
        if isinstance(out, tuple):
            stdout_b, stderr_b = out
        elif isinstance(out, (bytes, bytearray)):
            stdout_b, stderr_b = bytes(out), b""
        else:
            stdout_b, stderr_b = b"", b""
        return ok(
            {
                "exit_code": result.exit_code,
                "stdout": (stdout_b or b"").decode("utf-8", errors="replace"),
                "stderr": (stderr_b or b"").decode("utf-8", errors="replace"),
            }
        )

    @tool(mcp, role=Role.OPERATOR)
    async def run_container(params: RunContainerParams) -> dict[str, Any]:
        """Crée et démarre un nouveau conteneur.

        Les bind-mounts sont validés contre la whitelist
        `DOCKERMCP_ALLOWED_BIND_ROOTS`.
        """
        settings = get_settings()
        for host_path in params.binds:
            if not settings.is_bind_path_allowed(host_path):
                return {
                    "ok": False,
                    "error": "bind_not_allowed",
                    "message": (
                        f"Chemin {host_path!r} hors de la whitelist DOCKERMCP_ALLOWED_BIND_ROOTS."
                    ),
                }
        volumes = {h: {"bind": c, "mode": "rw"} for h, c in params.binds.items()}
        client = get_client()
        container = await to_thread(
            client.containers.run,
            image=params.image,
            name=params.name,
            command=params.command,
            environment=params.env or None,
            ports=params.ports or None,
            volumes=volumes or None,
            network=params.network,
            restart_policy={"Name": params.restart_policy},
            detach=params.detach,
            remove=params.remove,
        )
        if params.detach:
            assert not isinstance(container, bytes)
            await to_thread(container.reload)
            return ok(_summarize(container))
        output = (
            container.decode("utf-8", errors="replace")
            if isinstance(container, bytes)
            else str(container)
        )
        return ok({"output": output})
