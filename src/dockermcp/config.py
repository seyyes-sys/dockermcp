"""Configuration runtime du serveur.

Toutes les valeurs sont lues depuis l'environnement au premier accès.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _split_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    return [Path(p).expanduser().resolve() for p in value.split(os.pathsep) if p.strip()]


@dataclass(frozen=True)
class Settings:
    """Paramètres du serveur DockerMCP."""

    # Whitelist de répertoires autorisés pour les bind-mounts.
    # Vide = aucun bind-mount autorisé via le serveur.
    allowed_bind_roots: list[Path] = field(default_factory=list)

    # Seuils d'alerte pour le monitoring proactif.
    cpu_warn_pct: float = 80.0
    mem_warn_pct: float = 85.0
    restart_warn_count: int = 3

    # Préfixe optionnel : ne gérer que les conteneurs dont le nom commence par ce préfixe.
    name_prefix: str | None = None

    # Whitelist de répertoires contenant des fichiers docker-compose autorisés.
    allowed_compose_roots: list[Path] = field(default_factory=list)

    # Timeout (secondes) pour les commandes `docker compose`.
    compose_timeout_s: int = 120

    def is_bind_path_allowed(self, path: str | Path) -> bool:
        """Retourne True si `path` est dans un répertoire whitelisté."""
        if not self.allowed_bind_roots:
            return False
        try:
            target = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        return any(target == root or root in target.parents for root in self.allowed_bind_roots)

    def is_compose_path_allowed(self, path: str | Path) -> bool:
        """Retourne True si `path` (fichier compose) est dans la whitelist."""
        if not self.allowed_compose_roots:
            return False
        try:
            target = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        return any(target == root or root in target.parents for root in self.allowed_compose_roots)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        allowed_bind_roots=_split_paths(os.getenv("DOCKERMCP_ALLOWED_BIND_ROOTS")),
        cpu_warn_pct=float(os.getenv("DOCKERMCP_CPU_WARN_PCT", "80")),
        mem_warn_pct=float(os.getenv("DOCKERMCP_MEM_WARN_PCT", "85")),
        restart_warn_count=int(os.getenv("DOCKERMCP_RESTART_WARN_COUNT", "3")),
        name_prefix=os.getenv("DOCKERMCP_NAME_PREFIX") or None,
        allowed_compose_roots=_split_paths(os.getenv("DOCKERMCP_ALLOWED_COMPOSE_ROOTS")),
        compose_timeout_s=int(os.getenv("DOCKERMCP_COMPOSE_TIMEOUT_S", "120")),
    )
