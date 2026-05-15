# Workflows n8n — DockerMCP

Workflows d'exemple à importer dans l'instance `dockermcp-n8n`.

## Prérequis

### 1. Installer le community node `n8n-nodes-mcp`

Le compose active déjà `N8N_COMMUNITY_PACKAGES_ENABLED=true`. Reste à installer :

1. Ouvrir https://n8n-it.hexotik.ovh (login : `admin` / `$N8N_PASSWORD`).
2. **Settings** (icône en bas à gauche) → **Community Nodes** → **Install**.
3. Champ *npm Package Name* : `n8n-nodes-mcp`
4. Cocher *I understand the risks* → **Install**.
5. Redémarrage automatique du conteneur n8n (~10 s).

### 2. Créer les credentials

#### Credential A — `MCP Client (HTTP Streamable)` pour DockerMCP

- **Credential type** : `MCP Client API`
- **Connection Type** : `HTTP Streamable` (ou `SSE` si le node ne propose pas streamable)
- **HTTP Streamable URL** : `http://dockermcp:8765/mcp`
- **Additional Headers** :
  ```
  Authorization: Bearer <ton token operator>
  ```
  (le même que `N8N_DOCKERMCP_TOKEN` dans le `.env`)

#### Credential B — `Telegram API` pour les alertes

- **Credential type** : `Telegram API`
- **Access Token** : ton `TELEGRAM_ITOPS_BOT_TOKEN`

> Astuce : crée un bot dédié IT-Ops via [@BotFather](https://t.me/BotFather) → `/newbot`. Récupère le `chat_id` en envoyant un message au bot puis :  
> `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq '.result[-1].message.chat.id'`

## Workflows fournis

| Fichier | Trigger | Description |
|---|---|---|
| [`docker-health-monitor.json`](docker-health-monitor.json) | Cron 5 min | Appelle `health_report` → si `critical_count > 0`, envoie un message Telegram formaté en Markdown |
| [`dockermcp-proxy.json`](dockermcp-proxy.json) | Webhook `POST /webhook/dockermcp` | Proxy générique : reçoit `{tool, params}`, exécute via le node MCP Client, renvoie `{ok, tool, data}`. Consommé par le **skill OpenClaw `dockermcp`** (cf. [`../openclaw/skills/dockermcp/SKILL.md`](../openclaw/skills/dockermcp/SKILL.md)). |

## Import d'un workflow

1. Dans n8n : **Workflows** → **Import from File** → choisir le `.json`.
2. Pour chaque nœud rouge (credentials manquantes) :
   - Ouvrir le nœud, sélectionner la credential créée ci-dessus.
3. **Activate** le workflow (toggle en haut à droite).

## Personnalisation rapide

Les seuils du `health_report` sont dans le nœud **DockerMCP — health_report** :

```json
{
  "cpu_threshold": 80,
  "mem_threshold": 85,
  "restart_threshold": 3
}
```

Tu peux aussi ajouter `name_filter: "myapp-"` pour ne surveiller qu'un sous-ensemble de conteneurs.

## Dépannage

- **Workflow rouge à l'import** : credentials manquantes (normal). Re-sélectionner après création.
- **`401 Unauthorized`** : token Bearer incorrect ou rôle insuffisant. `health_report` requiert au minimum `viewer`.
- **`Connection refused`** : depuis n8n, `dockermcp` doit être joignable. Vérifier `docker compose exec dockermcp-n8n wget -qO- http://dockermcp:8765/mcp` (devrait répondre du JSON-RPC, pas 404).
- **Le node MCP n'apparaît pas après installation** : redémarrer `docker compose restart n8n-itops`.
