"""Fixtures partagées pour les tests d'intégration Docker.

Tous les tests de ce dossier sont marqués automatiquement `integration`
et skippés si :
  - le module `docker` est absent ;
  - le daemon Docker n'est pas joignable (`client.ping()` échoue).

Les tests créent des conteneurs préfixés par ``dockermcp-it-`` pour
faciliter le nettoyage en cas d'échec.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest

docker = pytest.importorskip("docker")
from docker.errors import DockerException, NotFound  # noqa: E402

from dockermcp.auth import Role, set_current_role  # noqa: E402
from dockermcp.server import build_server  # noqa: E402

from ._helpers import IT_IMAGE, IT_PREFIX  # noqa: E402


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Marque automatiquement les tests de ce dossier comme `integration`."""
    here = str(Path(__file__).parent)
    for item in items:
        if str(item.path).startswith(here):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def docker_client() -> Any:
    try:
        client = docker.from_env()
        client.ping()
    except (DockerException, OSError) as exc:
        pytest.skip(f"Daemon Docker indisponible : {exc}")
    return client


@pytest.fixture(scope="session", autouse=True)
def _ensure_image(docker_client: Any) -> None:
    """Pré-tire l'image alpine pour éviter le coût dans chaque test."""
    try:
        docker_client.images.get(IT_IMAGE)
    except NotFound:
        docker_client.images.pull(IT_IMAGE)


@pytest.fixture
def alpine_container(docker_client: Any) -> Iterator[Any]:
    """Crée un conteneur alpine éphémère qui boucle, et le détruit à la fin."""
    name = f"{IT_PREFIX}{uuid.uuid4().hex[:8]}"
    container = docker_client.containers.run(
        IT_IMAGE,
        name=name,
        command=["sh", "-c", "while true; do echo tick; sleep 1; done"],
        detach=True,
        labels={"dockermcp.test": "1"},
    )
    try:
        yield container
    finally:
        try:
            container.reload()
            container.remove(force=True)
        except NotFound:
            pass
        except DockerException:
            pass


@pytest.fixture(autouse=True)
def _operator_role() -> None:
    """Donne le rôle OPERATOR à chaque test (suffisant pour list/exec/start/stop)."""
    set_current_role(Role.OPERATOR)


@pytest.fixture
def admin_role() -> None:
    """À demander explicitement pour les tests qui suppriment des ressources."""
    set_current_role(Role.ADMIN)


@pytest.fixture
async def mcp_server() -> AsyncIterator[Any]:
    """Instancie un serveur MCP avec tous les outils enregistrés."""
    yield build_server()
