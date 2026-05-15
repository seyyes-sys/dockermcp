# Déploiement — DockerMCP Suite

Stack isolée (Option B) à déployer **à côté** d'`ai2cook` sur le serveur Hexotik.

## Composants

| Service | Image | Port interne | Exposition |
|---|---|---|---|
| `docker-socket-proxy` | `tecnativa/docker-socket-proxy` | 2375 | Réseau `docker_api` (internal) |
| `dockermcp` | `ghcr.io/seyyes-sys/dockermcp:latest` | 8765 | `dockermcp.hexotik.ovh` via Caddy |
| `n8n-itops` | `n8nio/n8n:latest` | 5678 | `n8n-it.hexotik.ovh` via Caddy |
| `openclaw-itops` | `openclaw:local` (profile) | — | Bot Telegram IT-Ops dédié |
| `watchtower` | `containrrr/watchtower` | — | Scope `dockermcp-suite` |

## Réseaux

- `dockermcp_docker_api` — **internal** (pas d'Internet). Seuls `socket-proxy` et `dockermcp` y sont.
- `dockermcp_suite` — communication interne (`dockermcp` ↔ `n8n` ↔ `openclaw`).
- `compose_airsoft-network` — externe, partagé avec Caddy (déjà créé par ta stack Caddy).

## Procédure de déploiement

```bash
# 1) Sur le serveur, première fois :
ssh <user>@<serveur>
git clone https://github.com/seyyes-sys/dockermcp.git
cd dockermcp/deploy
cp .env.example .env
# Générer des tokens forts :
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Éditer .env avec : DOCKERMCP_TOKENS, N8N_PASSWORD, etc.
nano .env
chmod 600 .env

# 2) Vérifier que le réseau Caddy existe
docker network ls | grep compose_airsoft-network

# 3) Pull + démarrage (sans OpenClaw au début)
docker compose pull
docker compose up -d

# 4) Vérifier
docker compose ps
docker compose logs -f dockermcp
# Le serveur MCP n'expose pas de /health REST — utilise le healthcheck Docker :
docker inspect --format '{{.State.Health.Status}}' dockermcp

# 5) Ajouter le snippet Caddy
cat caddy-snippet.txt >> /chemin/vers/Caddyfile
docker exec <caddy_container> caddy reload --config /etc/caddy/Caddyfile

# 6) Activer OpenClaw IT-Ops plus tard (quand bot Telegram créé) :
docker compose --profile openclaw up -d
```

## Mises à jour

```bash
cd ~/dockermcp/deploy
docker compose pull dockermcp
docker compose up -d dockermcp
```

Pour épingler une version précise, éditer `.env` :
```
DOCKERMCP_IMAGE_TAG=v0.1.0
```

Watchtower met à jour automatiquement `n8n` et `socket-proxy` chaque nuit à 04:00 (scope `dockermcp-suite` — n'affecte pas `ai2cook`).

## Image Docker (GHCR)

L'image `ghcr.io/seyyes-sys/dockermcp` est build/push automatiquement par
[`.github/workflows/release.yml`](../.github/workflows/release.yml) :

| Trigger | Tags produits |
|---|---|
| Push sur `main` | `latest`, `main`, `sha-<short>` |
| Tag `v1.2.3` | `1.2.3`, `1.2`, `latest`, `sha-<short>` |
| Manuel (`workflow_dispatch`) | idem branche/tag courant |

Architectures : `linux/amd64` + `linux/arm64`.

### Visibilité du package

Par défaut le package GHCR est **privé**. Deux options :

1. **Rendre public** (recommandé pour un projet open-source) :
   `https://github.com/users/seyyes-sys/packages/container/dockermcp/settings` → *Change visibility* → Public.
2. **Garder privé** : sur le serveur, `docker login ghcr.io` avec un PAT
   classique scope `read:packages`, puis stocker dans `~/.docker/config.json`.

## Vérifications post-déploiement

```bash
# DockerMCP joint le socket-proxy
docker compose exec dockermcp python -c "import docker; print(docker.from_env().version())"

# socket-proxy refuse bien /build (sécurité)
docker compose exec dockermcp \
  python -c "import urllib.request as r; \
             print(r.urlopen('http://docker-socket-proxy:2375/v1.41/build').status)" \
  || echo "OK : /build refusé"

# Audit log
docker compose exec dockermcp tail -n 20 /var/log/dockermcp/audit.log
```

## Sécurité — points clés

- **Aucun service n'expose de port sur l'hôte** : tout passe par Caddy (TLS + WAF possible).
- **Pas de bind-mount du socket Docker** dans `dockermcp` : on passe par le proxy filtré.
- **`DOCKERMCP_TOKENS` obligatoire** : le serveur refuse le démarrage HTTP sans token.
- **`.env` en `chmod 600`** + `.gitignore`.
- **Watchtower scopé** : ne touche pas `ai2cook-*`.
- **Réseau `docker_api` `internal: true`** : socket-proxy ne peut pas exfiltrer vers Internet.

## Rollback

```bash
cd ~/dockermcp/deploy
docker compose down              # garde les volumes (audit, n8n_data)
docker compose down -v           # ⚠️  supprime aussi les volumes (perte données n8n)
```
