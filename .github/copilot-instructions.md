# DockerMCP — Instructions Copilot

Serveur **MCP (Model Context Protocol)** en Python permettant à un agent IA de gérer Docker (conteneurs, images, volumes, réseaux, compose).

> Ce fichier guide les agents IA travaillant sur ce dépôt. Soyez bref, factuel, et préférez modifier le code existant à dupliquer la documentation.

## Organisation des personnalisations agent

Toutes les personnalisations Copilot vivent sous `.github/` :

```
.github/
  copilot-instructions.md   # ce fichier — instructions globales
  instructions/             # *.instructions.md ciblés via `applyTo`
  prompts/                  # *.prompt.md (commandes /slash)
  agents/                   # *.agent.md (modes d'agent personnalisés)
  skills/                   # SKILL.md par domaine
```

Créer ces sous-dossiers **à la demande**, au fur et à mesure que le besoin apparaît — ne pas pré-créer de dossiers vides.

## État du projet

Le dépôt est en **phase d'initialisation**. La structure cible et les conventions ci-dessous doivent être appliquées dès les premiers commits.

## Stack & dépendances

- **Langage** : Python ≥ 3.11
- **SDK MCP** : [`mcp`](https://github.com/modelcontextprotocol/python-sdk) (utiliser `FastMCP` pour exposer outils, ressources, prompts)
- **Client Docker** : [`docker`](https://docker-py.readthedocs.io/) (SDK officiel Python)
- **Gestion d'env** : `uv` (préféré) ou `pip` + `venv`
- **Lint/format** : `ruff` (lint + format)
- **Types** : `mypy --strict` sur `src/`
- **Tests** : `pytest` + `pytest-asyncio`

## Structure cible

```
src/dockermcp/
  __init__.py
  server.py          # entrée FastMCP + enregistrement des tools
  tools/             # 1 module par domaine : containers, images, volumes, networks, compose
  docker_client.py   # wrapper unique autour de docker.from_env()
  models.py          # schémas Pydantic pour les paramètres/retours d'outils
tests/
  unit/              # mocks du client Docker
  integration/       # nécessite un daemon Docker (marquer @pytest.mark.integration)
pyproject.toml
README.md
```

## Commandes essentielles

| But            | Commande                                |
| -------------- | --------------------------------------- |
| Installer      | `uv sync` (ou `pip install -e .[dev]`)  |
| Lancer serveur | `python -m dockermcp`                   |
| Tests rapides  | `pytest -m "not integration"`           |
| Tous les tests | `pytest`                                |
| Lint           | `ruff check . && ruff format --check .` |
| Types          | `mypy src`                              |

Avant tout commit : `ruff format . && ruff check --fix . && mypy src && pytest -m "not integration"`.

## Conventions spécifiques

- **Un seul `DockerClient`** : instancié paresseusement dans `docker_client.py`. Ne jamais appeler `docker.from_env()` ailleurs.
- **Outils MCP** : un outil = fonction async **décorée par `tool(mcp, role=Role.X)`** (cf. `tools/_common.py`) qui combine `@mcp.tool()` + audit + RBAC + `safe_tool`. Paramètres typés via Pydantic, docstring claire (devient la description vue par le LLM).
- **Choix du rôle** : `Role.VIEWER` pour la lecture, `Role.OPERATOR` pour les actions non destructives, `Role.ADMIN` pour les destructives (`remove_*`, `prune`).
- **Erreurs** : capturer `docker.errors.APIError` / `NotFound` et renvoyer un message structuré ; ne jamais laisser remonter une stacktrace brute au client MCP.
- **Opérations destructives** (`remove`, `prune`, `kill`, `down -v`) : exiger un paramètre explicite `confirm: bool = False` et refuser sinon — **en plus** du contrôle RBAC.
- **Sortie** : retourner des dicts/objets Pydantic sérialisables — pas de `print`, pas de logs sur stdout (stdout = transport MCP).
- **Logs** : `logging` vers stderr uniquement. Le logger `dockermcp.audit` est réservé à l'audit JSON ligne-par-ligne — ne pas y écrire ailleurs.
- **Async** : préférer `asyncio.to_thread(...)` (helper `to_thread` dans `tools/_common.py`) pour wrapper les appels bloquants du SDK Docker.
- **Secrets** : ne jamais les logger ni les retourner. L'audit redact automatiquement les clés `token`, `password`, `secret`, `key`, `authorization`.

## Pièges à éviter

- Sur **Windows**, `docker.from_env()` requiert que Docker Desktop soit démarré ; les tests d'intégration doivent être skippés sinon (`pytest.importorskip` + ping du daemon).
- Le transport **stdio** MCP interdit toute écriture sur stdout hors protocole — vérifier qu'aucune dépendance ne pollue stdout.
- Les noms de conteneurs/images peuvent contenir `/` (registry) ; ne pas naïvement splitter.
- `docker compose` (v2) ≠ `docker-compose` (v1) : utiliser `docker compose` via subprocess uniquement si le SDK ne couvre pas le besoin.

## Sécurité

- Ne jamais exécuter de commande shell construite par concaténation de chaînes utilisateur. Utiliser `subprocess.run([...], shell=False)` avec listes d'arguments.
- Refuser les chemins de bind-mount pointant hors d'un répertoire whitelisté (`Settings.is_bind_path_allowed`).
- Ne pas exposer de variables d'environnement contenant des secrets dans les retours d'outils.
- **Transport HTTP** : toujours bind sur `127.0.0.1` derrière un reverse proxy TLS. Token bearer obligatoire (`DOCKERMCP_TOKENS`). Refuser le démarrage HTTP si aucun token n'est défini (cf. `__main__.py`).
- **RBAC** : le rôle minimum d'un nouvel outil doit être choisi de façon conservatrice — préférer `OPERATOR` ou `ADMIN` au moindre doute.
- **Read-only mode** (`DOCKERMCP_READ_ONLY=true`) doit toujours rester respecté : ne jamais court-circuiter `effective_role()`.

## Pour aller plus loin

- Spécification MCP : <https://modelcontextprotocol.io>
- Docker SDK Python : <https://docker-py.readthedocs.io>
