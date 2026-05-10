"""Outils MCP pour gérer ``docker compose`` (v2).

Le SDK Python ne couvre pas Compose : on s'appuie sur la CLI ``docker compose``
via ``subprocess.run`` (sans shell). Tous les chemins de fichiers compose sont
validés contre la whitelist ``DOCKERMCP_ALLOWED_COMPOSE_ROOTS`` pour éviter
qu'un LLM ne soit amené à exécuter un fichier arbitraire.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from dockermcp.auth import Role
from dockermcp.config import get_settings
from dockermcp.models import ConfirmDestructive
from dockermcp.tools._common import ok, to_thread, tool

# ---------- paramètres ----------


class ComposeRef(BaseModel):
    file: str = Field(description="Chemin absolu vers le fichier docker-compose.yml.")
    project: str | None = Field(
        default=None,
        description="Nom de projet Compose (`-p`). Par défaut, dérivé du dossier.",
    )


class ComposePsParams(ComposeRef):
    pass


class ComposeUpParams(ComposeRef):
    services: list[str] = Field(
        default_factory=list, description="Sous-ensemble de services à démarrer (vide = tous)."
    )
    build: bool = False
    force_recreate: bool = False


class ComposeRestartParams(ComposeRef):
    services: list[str] = Field(default_factory=list)


class ComposeBuildParams(ComposeRef):
    services: list[str] = Field(default_factory=list)
    no_cache: bool = False
    pull: bool = False


class ComposePullParams(ComposeRef):
    services: list[str] = Field(default_factory=list)


class ComposeLogsParams(ComposeRef):
    services: list[str] = Field(default_factory=list)
    tail: int = Field(default=200, ge=1, le=10_000)


class ComposeDownParams(ComposeRef, ConfirmDestructive):
    volumes: bool = Field(
        default=False,
        description="Si True, supprime aussi les volumes (`down -v`). Exige confirm=True.",
    )
    remove_orphans: bool = False


# ---------- helpers ----------


def _validate_compose_file(file: str) -> tuple[Path, dict[str, Any] | None]:
    settings = get_settings()
    if not settings.is_compose_path_allowed(file):
        return Path(file), {
            "ok": False,
            "error": "compose_not_allowed",
            "message": (f"Chemin {file!r} hors de la whitelist DOCKERMCP_ALLOWED_COMPOSE_ROOTS."),
        }
    path = Path(file).expanduser().resolve()
    if not path.is_file():
        return path, {
            "ok": False,
            "error": "compose_not_found",
            "message": f"Fichier compose introuvable : {path}",
        }
    return path, None


def _docker_cmd() -> list[str]:
    """Retourne le chemin de l'exécutable `docker`."""
    exe = shutil.which("docker")
    if not exe:
        raise RuntimeError("L'exécutable `docker` est introuvable dans PATH.")
    return [exe]


def _base_args(path: Path, project: str | None) -> list[str]:
    args = [*_docker_cmd(), "compose", "-f", str(path)]
    if project:
        args += ["-p", project]
    return args


def _run(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    proc = subprocess.run(  # noqa: S603 - shell=False, args en liste
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=settings.compose_timeout_s,
        check=False,
        shell=False,
    )
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-20_000:],  # garde-fou contre des sorties énormes
        "stderr": proc.stderr[-20_000:],
    }


# ---------- registration ----------


def register(mcp: FastMCP) -> None:
    @tool(mcp, role=Role.VIEWER)
    async def compose_ps(params: ComposePsParams) -> dict[str, Any]:
        """Liste les services d'un projet Compose (`docker compose ps`)."""
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [*_base_args(path, params.project), "ps", "--format", "json"]
        result = await to_thread(_run, cmd, path.parent)
        services: list[dict[str, Any]] = []
        # Compose v2 émet une ligne JSON par service.
        for line in (result["stdout"] or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                services.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return ok(services, exit_code=result["exit_code"], stderr=result["stderr"])

    @tool(mcp, role=Role.OPERATOR)
    async def compose_up(params: ComposeUpParams) -> dict[str, Any]:
        """Démarre une stack Compose en mode détaché (`up -d`)."""
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [*_base_args(path, params.project), "up", "-d"]
        if params.build:
            cmd.append("--build")
        if params.force_recreate:
            cmd.append("--force-recreate")
        cmd += list(params.services)
        return ok(await to_thread(_run, cmd, path.parent))

    @tool(mcp, role=Role.OPERATOR)
    async def compose_restart(params: ComposeRestartParams) -> dict[str, Any]:
        """Redémarre les services d'un projet Compose."""
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [*_base_args(path, params.project), "restart", *params.services]
        return ok(await to_thread(_run, cmd, path.parent))

    @tool(mcp, role=Role.OPERATOR)
    async def compose_build(params: ComposeBuildParams) -> dict[str, Any]:
        """Build les images d'un projet Compose."""
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [*_base_args(path, params.project), "build"]
        if params.no_cache:
            cmd.append("--no-cache")
        if params.pull:
            cmd.append("--pull")
        cmd += list(params.services)
        return ok(await to_thread(_run, cmd, path.parent))

    @tool(mcp, role=Role.OPERATOR)
    async def compose_pull(params: ComposePullParams) -> dict[str, Any]:
        """Tire les images du registre pour un projet Compose."""
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [*_base_args(path, params.project), "pull", *params.services]
        return ok(await to_thread(_run, cmd, path.parent))

    @tool(mcp, role=Role.VIEWER)
    async def compose_logs(params: ComposeLogsParams) -> dict[str, Any]:
        """Récupère les logs d'un projet Compose."""
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [
            *_base_args(path, params.project),
            "logs",
            "--no-color",
            "--tail",
            str(params.tail),
            *params.services,
        ]
        return ok(await to_thread(_run, cmd, path.parent))

    @tool(mcp, role=Role.ADMIN)
    async def compose_down(params: ComposeDownParams) -> dict[str, Any]:
        """Arrête une stack Compose. Avec ``volumes=True``, supprime les volumes."""
        if not params.confirm:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Passez confirm=True pour exécuter compose_down.",
            }
        path, err = _validate_compose_file(params.file)
        if err:
            return err
        cmd = [*_base_args(path, params.project), "down"]
        if params.volumes:
            cmd.append("-v")
        if params.remove_orphans:
            cmd.append("--remove-orphans")
        return ok(await to_thread(_run, cmd, path.parent))
