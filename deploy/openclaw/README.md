# Skills OpenClaw — DockerMCP

Skills bind-mountés en lecture seule dans le conteneur `dockermcp-openclaw`
sous `/home/node/.openclaw/skills/`.

## Skill `dockermcp`

Permet à l'agent (Claude via OpenClaw) de gérer Docker sans accès direct au
socket. Le skill instruit le LLM à invoquer `exec` + `curl` vers le **webhook
n8n proxy** (`POST /webhook/dockermcp`), qui relaie ensuite l'appel au serveur
**DockerMCP** via le node `n8n-nodes-mcp.mcpClient`.

### Architecture

```
Telegram → OpenClaw (Claude)
            └── exec(curl) → n8n /webhook/dockermcp
                              └── MCP Client → DockerMCP (FastMCP)
                                                └── docker-socket-proxy → docker.sock
```

### Déploiement

1. **Importer le workflow** `deploy/n8n-workflows/dockermcp-proxy.json` dans
   l'instance n8n et l'**activer**.
2. **Réutiliser** la même credential `MCP Client (HTTP Streamable)` que le
   workflow Health Monitor (token = `OPENCLAW_DOCKERMCP_TOKEN`, rôle
   `OPERATOR` ou plus suivant l'usage).
3. **(Re)démarrer** le service OpenClaw pour qu'il lise le skill bind-mounté :

   ```bash
   cd ~/dockermcp/deploy
   docker compose --profile openclaw up -d --force-recreate openclaw-itops
   docker exec dockermcp-openclaw openclaw skills list
   ```

   La sortie doit lister `dockermcp` parmi les skills chargés.

### Test rapide depuis Telegram

Envoie au bot IT-Ops un message du type :

> Liste les conteneurs Docker en cours.

L'agent doit appeler `containers_list` via le proxy et restituer une liste
formatée — **sans tenter** `docker ps` directement.

### Sécurité

- Le token bearer DockerMCP n'est connu **que** par n8n (pas par l'agent).
- Les actions destructives exigent toujours `confirm: true` côté DockerMCP
  **en plus** d'une confirmation utilisateur exigée par le skill.
- RBAC : le rôle effectif vient du token n8n (`OPENCLAW_DOCKERMCP_TOKEN`).
  Pour limiter encore plus, créer un token dédié dans `DOCKERMCP_TOKENS` et
  l'attribuer à la credential du proxy uniquement.
- Le skill est monté en **lecture seule** (`:ro`).
