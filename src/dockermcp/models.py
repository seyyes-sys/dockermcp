"""Modèles Pydantic partagés (paramètres et retours d'outils MCP)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------- Paramètres ----------


class ConfirmDestructive(BaseModel):
    """Mixin pour les opérations destructives."""

    confirm: bool = Field(
        default=False,
        description="DOIT être True pour exécuter une opération destructive.",
    )


class ContainerRef(BaseModel):
    container: str = Field(description="ID ou nom du conteneur.")


class ListContainersParams(BaseModel):
    all: bool = Field(default=False, description="Inclure les conteneurs arrêtés.")
    name_contains: str | None = Field(
        default=None, description="Filtre sous-chaîne sur le nom du conteneur."
    )
    label: str | None = Field(default=None, description="Filtre par label `clé=valeur`.")
    limit: int = Field(default=50, ge=1, le=500)


class LogsParams(ContainerRef):
    tail: int = Field(default=200, ge=1, le=10_000, description="Nombre de lignes en queue.")
    since_seconds: int | None = Field(
        default=None, ge=1, description="Limiter aux logs des N dernières secondes."
    )
    timestamps: bool = False


class ExecParams(ContainerRef):
    cmd: list[str] = Field(min_length=1, description="Commande sous forme de liste d'arguments.")
    workdir: str | None = None
    user: str | None = None
    timeout_s: int = Field(default=30, ge=1, le=600)


class RunContainerParams(BaseModel):
    image: str
    name: str | None = None
    command: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)
    ports: dict[str, int] = Field(
        default_factory=dict,
        description="Mapping `'80/tcp': 8080` (port_conteneur -> port_hôte).",
    )
    binds: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping `chemin_hôte: chemin_conteneur`. Soumis à la whitelist.",
    )
    network: str | None = None
    restart_policy: Literal["no", "on-failure", "always", "unless-stopped"] = "unless-stopped"
    detach: bool = True
    remove: bool = False


class RemoveContainerParams(ContainerRef, ConfirmDestructive):
    force: bool = False
    volumes: bool = False


class PruneParams(ConfirmDestructive):
    pass


class HealthReportParams(BaseModel):
    include_stopped: bool = Field(
        default=True, description="Inclure les conteneurs arrêtés dans le rapport."
    )


# ---------- Retours ----------


class ToolError(BaseModel):
    ok: Literal[False] = False
    error: str
    message: str
    status: int | None = None


class ToolOk(BaseModel):
    ok: Literal[True] = True
    data: Any = None
