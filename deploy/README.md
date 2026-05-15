# Déploiement — DockerMCP Suite

Stack isolée (Option B) à déployer **à côté** d'`ai2cook` sur le serveur Hexotik.

## Composants

| Service | Image | Port interne | Exposition |
|---|---|---|---|
| `docker-socket-proxy` | `tecnativa/docker-socket-proxy` | 2375 | Réseau `docker_api` (internal) |
| `dockermcp` | `dockermcp:local` (build local) | 8765 | `dockermcp.hexotik.ovh` via Caddy |
| `n8n-itops` | `n8nio/n8n:latest` | 5678 | `n8n-it.hexotik.ovh` via Caddy |
| `openclaw-itops` | `openclaw:local` (profile) | — | Bot Telegram IT-Ops dédié |
| `watchtower` | `containrrr/watchtower` | — | Scope `dockermcp-suite` |

## Réseaux

- `dockermcp_docker_api` — **internal** (pas d'Internet). Seuls `socket-proxy` et `dockermcp` y sont.
- `dockermcp_suite` — communication interne (`dockermcp` ↔ `n8n` ↔ `openclaw`).
- `compose_airsoft-network` — externe, partagé avec Caddy (déjà créé par ta stack Caddy).

## Procédure de déploiement

```bash
# 1) Sur ta machine : pousser le code (déjà sur GitHub)
git push origin main

# 2) Sur le serveur, première fois :
ssh user@51.38.209.215
git clone https://github.com/seyyes-sys/dockermcp.git
cd dockermcp/deploy
cp .env.example .env
# Générer des tokens forts :
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Éditer .env avec : DOCKERMCP_TOKENS, N8N_PASSWORD, etc.
nano .env
chmod 600 .env

# 3) Vérifier que le réseau Caddy existe
docker network ls | grep compose_airsoft-network

# 4) Build + démarrage (sans OpenClaw au début)
docker compose up -d --build

# 5) Vérifier
docker compose ps
docker compose logs -f dockermcp
# Le serveur MCP n'expose pas de /health REST — utilise le healthcheck Docker :
docker inspect --format '{{.State.Health.Status}}' dockermcp

# 6) Ajouter le snippet Caddy
cat caddy-snippet.txt >> /chemin/vers/Caddyfile
docker exec <caddy_container> caddy reload --config /etc/caddy/Caddyfile

# 7) Activer OpenClaw IT-Ops plus tard (quand bot Telegram créé) :
docker compose --profile openclaw up -d
```

## Mises à jour

```bash
cd ~/dockermcp
git pull
cd deploy
docker compose build dockermcp
docker compose up -d dockermcp
```

Watchtower met à jour automatiquement `n8n` et `socket-proxy` chaque nuit à 04:00 (scope `dockermcp-suite` — n'affecte pas `ai2cook`).

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
