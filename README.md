# DockerMCP

Serveur **Model Context Protocol (MCP)** en Python pour permettre à un LLM
(Claude Desktop, Copilot, agent custom…) d'administrer et **monitorer
proactivement** un daemon Docker en langage naturel.

## Cas d'usage

- « Liste les conteneurs qui consomment plus de 80% de CPU. »
- « Pourquoi `api-prod` a-t-il redémarré ? Montre les derniers events. »
- « Donne-moi un rapport de santé de tous mes conteneurs. »
- « Récupère les 200 dernières lignes de logs de `nginx` et résume les erreurs. »
- « Redémarre le conteneur `worker-1`. »

## Installation

```powershell
# avec uv (recommandé)
uv sync

# ou avec pip
pip install -e ".[dev]"
```

## Lancer le serveur (stdio)

```powershell
python -m dockermcp
```

## Lancer le serveur en HTTP (production)

```powershell
$env:DOCKERMCP_TRANSPORT = "streamable-http"
$env:DOCKERMCP_TOKENS    = "$(New-Guid):admin,$(New-Guid):viewer"
$env:DOCKERMCP_HTTP_HOST = "127.0.0.1"
python -m dockermcp
```

> Toujours placer le port HTTP derrière un reverse proxy TLS. Ne jamais
> binder `0.0.0.0` sans authentification réseau supplémentaire.

## Outils exposés

| Domaine     | Outils                                                                                          | Rôle min |
| ----------- | ----------------------------------------------------------------------------------------------- | -------- |
| Conteneurs  | `list_containers`, `inspect_container`, `container_logs`                                        | viewer   |
| Conteneurs  | `start_container`, `stop_container`, `restart_container`, `exec_in_container`, `run_container`  | operator |
| Conteneurs  | `remove_container`                                                                              | admin    |
| Images      | `list_images`                                                                                   | viewer   |
| Images      | `pull_image`                                                                                    | operator |
| Images      | `remove_image`                                                                                  | admin    |
| Volumes     | `list_volumes` / `create_volume` / `remove_volume`                                              | viewer / operator / admin |
| Réseaux     | `list_networks` / `create_network` / `remove_network`                                           | viewer / operator / admin |
| Système     | `docker_version`, `docker_info`, `disk_usage`                                                   | viewer   |
| Monitoring  | `container_stats`, `health_report`, `recent_events`                                             | viewer   |
| Compose     | `compose_ps`, `compose_logs`                                                                    | viewer   |
| Compose     | `compose_up`, `compose_restart`, `compose_build`, `compose_pull`                                | operator |
| Compose     | `compose_down` (avec ou sans `volumes=true`)                                                    | admin    |

## Ressources MCP (lecture seule)

Le serveur expose aussi des ressources que le LLM peut lire sans appeler
explicitement un outil :

| URI                                       | Contenu                                |
| ----------------------------------------- | -------------------------------------- |
| `docker://containers`                     | Liste de tous les conteneurs (JSON)    |
| `docker://containers/{name}`              | `docker inspect` complet               |
| `docker://containers/{name}/logs`         | 200 dernières lignes de logs           |
| `docker://system/info`                    | `docker info`                          |
| `docker://system/disk`                    | Utilisation disque                     |
| `docker://health`                         | Rapport de santé synthétique           |

## Prompts MCP

Modèles de conversation pré-construits (apparaissent en tant que
*slash commands* dans Claude Desktop) :

| Prompt                  | Paramètres   | Rôle                                                |
| ----------------------- | ------------ | --------------------------------------------------- |
| `diagnose_container`    | `name`       | Diagnostic complet d'un conteneur (inspect+logs+events) |
| `triage_health`         | _aucun_      | Triage santé globale, classement par criticité      |
| `incident_postmortem`   | `name`       | Post-mortem au format Google SRE                    |
| `explain_compose`       | `file`       | Explique architecture + risques d'une stack Compose |

Les opérations destructives (`remove_*`) refusent l'exécution sans
`confirm=True`, **en plus** de la vérification RBAC.

## Sécurité — accès au serveur

DockerMCP gère un daemon avec accès root équivalent : l'accès doit être
strictement contrôlé.

### Rôles

| Rôle       | Accès                                                                       |
| ---------- | --------------------------------------------------------------------------- |
| `viewer`   | Lecture seule : list, inspect, logs, stats, health report, events           |
| `operator` | viewer + start / stop / restart / exec / run / pull / create_*              |
| `admin`    | operator + suppressions (`remove_*`)                                        |

### Modes d'exécution

- **stdio (local)** : le rôle est fixé par `DOCKERMCP_STDIO_ROLE`
  (défaut : `operator`). Personne d'autre que l'utilisateur qui lance le
  process ne peut s'y connecter. Convient pour Claude Desktop / Copilot.
- **HTTP / SSE (réseau)** : le serveur exige un header
  `Authorization: Bearer <token>`. Le mapping
  `DOCKERMCP_TOKENS=token1:admin,token2:viewer` associe chaque token à
  un rôle. Bind par défaut sur `127.0.0.1` — **toujours** placer derrière
  un reverse proxy TLS (nginx / Traefik / Caddy).

### Mode lecture seule

`DOCKERMCP_READ_ONLY=true` rétrograde tous les rôles à `viewer` quel que
soit le token : utile pour donner accès à un LLM en production sans
risque, ou pendant un incident.

### Audit

Chaque appel d'outil émet une ligne JSON sur le logger `dockermcp.audit`
(stderr) : outil, rôle, statut (`ok` / `denied` / `error`), durée et
paramètres avec **redaction automatique** des clés sensibles
(`token`, `password`, `secret`, `key`, `authorization`).

#### Audit fichier rotatif

Pour conserver une trace persistante, définir `DOCKERMCP_AUDIT_FILE` :

```bash
export DOCKERMCP_AUDIT_FILE=/var/log/dockermcp/audit.log
export DOCKERMCP_AUDIT_MAX_BYTES=10485760   # 10 Mo (défaut)
export DOCKERMCP_AUDIT_BACKUPS=7            # conserve audit.log.1..7
```

Le fichier est géré par `RotatingFileHandler` (rotation par taille).
Recommandations :

- Permissions restrictives : `chmod 640` et propriétaire = utilisateur du serveur.
- Un seul worker (uvicorn `--workers 1`) — le handler n'est pas multi-process.
- Pour une rotation par date ou un envoi vers un SIEM, brancher un agent
  externe (logrotate, Vector, Fluent Bit) sur le fichier ou rediriger
  stderr.

## Configuration

Variables d'environnement :

| Variable                          | Défaut         | Rôle                                                                       |
| --------------------------------- | -------------- | -------------------------------------------------------------------------- |
| `DOCKERMCP_TRANSPORT`             | `stdio`        | `stdio`, `sse`, `streamable-http` (alias `http`).                          |
| `DOCKERMCP_HTTP_HOST`             | `127.0.0.1`    | Interface d'écoute HTTP.                                                   |
| `DOCKERMCP_HTTP_PORT`             | `8765`         | Port d'écoute HTTP.                                                        |
| `DOCKERMCP_TOKENS`                | _vide_         | Mapping `token:role,token2:role2`. **Obligatoire** en HTTP.                |
| `DOCKERMCP_STDIO_ROLE`            | `operator`     | Rôle accordé sur transport stdio.                                          |
| `DOCKERMCP_READ_ONLY`             | `false`        | Rétrograde tous les rôles à `viewer`.                                      |
| `DOCKERMCP_NAME_PREFIX`           | _vide_         | Restreint les opérations aux conteneurs préfixés.                          |
| `DOCKERMCP_ALLOWED_BIND_ROOTS`    | _vide_         | Chemins autorisés pour les bind-mounts (séparateur OS).                    |
| `DOCKERMCP_ALLOWED_COMPOSE_ROOTS` | _vide_         | Répertoires contenant les fichiers `docker-compose.yml` autorisés.         |
| `DOCKERMCP_COMPOSE_TIMEOUT_S`     | `120`          | Timeout des commandes `docker compose`.                                    |
| `DOCKERMCP_CPU_WARN_PCT`          | `80`           | Seuil CPU pour `health_report`.                                            |
| `DOCKERMCP_MEM_WARN_PCT`          | `85`           | Seuil mémoire pour `health_report`.                                        |
| `DOCKERMCP_RESTART_WARN_COUNT`    | `3`            | Seuil de redémarrages pour le statut `flapping`.                           |
| `DOCKERMCP_LOG_LEVEL`             | `INFO`         | Niveau du logger racine.                                                   |
| `DOCKERMCP_AUDIT_FILE`            | _vide_         | Si défini, journalise l'audit dans ce fichier (rotation automatique).      |
| `DOCKERMCP_AUDIT_MAX_BYTES`       | `10485760`     | Taille max d'un fichier d'audit avant rotation (10 Mo par défaut).         |
| `DOCKERMCP_AUDIT_BACKUPS`         | `7`            | Nombre d'archives d'audit conservées (`audit.log.1` … `audit.log.N`).      |

## Intégration Claude Desktop

```json
{
  "mcpServers": {
    "dockermcp": {
      "command": "python",
      "args": ["-m", "dockermcp"],
      "env": {
        "DOCKERMCP_ALLOWED_BIND_ROOTS": "C:/srv/data"
      }
    }
  }
}
```

## Développement

```powershell
ruff format . && ruff check --fix .
mypy src
pytest -m "not integration"   # tests rapides (mocks)
pytest -m integration         # nécessite Docker Desktop démarré
```

### Tests d'intégration

Les tests sous [tests/integration](tests/integration) parlent à un **vrai
daemon Docker** : ils créent un conteneur `alpine:3.20` éphémère préfixé
`dockermcp-it-` et le détruisent après chaque test. Si Docker n'est pas
joignable, ils sont **skippés automatiquement** (via
`pytest.importorskip` + `client.ping()`).

Les tests créent et suppriment leurs propres ressources, mais en cas de
crash, un nettoyage manuel reste possible :

```powershell
docker ps -a --filter "label=dockermcp.test=1" -q | ForEach-Object { docker rm -f $_ }
```

## Sécurité

- Pas d'exécution shell concaténée : `subprocess.run([...], shell=False)`.
- Bind-mounts whitelistés via `DOCKERMCP_ALLOWED_BIND_ROOTS`.
- Logs uniquement vers `stderr` (le stdout est réservé au transport MCP).

## Monitoring proactif

`health_report` retourne un champ **`alerts`** : liste plate d'alertes typées
prêtes à être consommées par un orchestrateur (n8n, OpenClaw, SIEM…).
Schéma de chaque alerte :

```json
{
  "severity": "critical | warning",
  "kind": "unhealthy | flapping | crashed | oom | high_cpu | high_mem",
  "container": "api-prod",
  "container_id": "a1b2c3d4e5f6",
  "message": "api-prod consomme 92.4% CPU (seuil=80%).",
  "metric": { "cpu_pct": 92.4, "threshold": 80 }
}
```

Les seuils peuvent être surchargés à l'appel
(`cpu_threshold`, `mem_threshold`, `restart_threshold`) ou globalement via les
env vars `DOCKERMCP_CPU_WARN_PCT`, `DOCKERMCP_MEM_WARN_PCT`,
`DOCKERMCP_RESTART_WARN_COUNT`. Filtre par nom : `name_filter="api-"`.

### Workflow n8n type

```
[Cron: */5 * * * *]
       │
       ▼
[MCP Client Tool] ── tool=health_report ──► DockerMCP (HTTP + token)
       │
       ▼
[IF: $json.data.summary.alerts_total > 0]
       │
       ▼
[Split In Batches] sur $json.data.alerts
       │
       ▼
[Switch: $json.severity]
   ├─ critical → [Telegram / OpenClaw webhook]
   └─ warning  → [Slack channel]
```

Cette architecture **ne nécessite aucun streaming** : un polling toutes les
5 minutes suffit pour 95 % des besoins SRE. Pour du temps réel sub-seconde,
brancher un side-car sur `docker events` qui POST vers un webhook n8n.

Voir [.github/copilot-instructions.md](.github/copilot-instructions.md) pour
les conventions internes.
