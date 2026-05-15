---
name: dockermcp
description: Gère les conteneurs Docker (lister, inspecter, démarrer, arrêter, redémarrer, logs, stats, santé) via le serveur DockerMCP en passant par un proxy n8n. À utiliser dès que l'utilisateur demande quoi que ce soit sur l'état ou la gestion des conteneurs Docker, images, volumes, réseaux ou stacks compose.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - curl
    primaryEnv: DOCKERMCP_PROXY_URL
    envVars:
      - name: DOCKERMCP_PROXY_URL
        required: true
        description: URL du webhook n8n proxy (ex http://dockermcp-n8n:5678/webhook/dockermcp).
    emoji: "🐳"
---

# Skill : DockerMCP via n8n proxy

Tu peux gérer la stack Docker locale (conteneurs, images, volumes, réseaux,
stacks compose, santé) en appelant le **proxy n8n** qui relaie vers DockerMCP.
Tu n'as **jamais** besoin d'utiliser `docker`, `podman`, `nerdctl` ou
`docker-compose` en ligne de commande — ils ne sont pas installés et tu n'as
pas les droits sur le socket Docker.

## Comment appeler le proxy

Utilise systématiquement l'outil `exec` avec `curl` :

```bash
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -m 30 \
  -d '{"tool":"<nom_du_tool>","params":{<json_params>}}'
```

La réponse est toujours un JSON de la forme :

```json
{ "ok": true, "tool": "<nom>", "data": { ... } }
```

ou en cas d'erreur :

```json
{ "ok": false, "error": "<code>", "message": "<détail>" }
```

Présente toujours à l'utilisateur un résumé clair en français (et pas le JSON
brut, sauf s'il le demande explicitement).

## Catalogue minimal des tools DockerMCP

Catégorie « lecture » (`Role.VIEWER`, sans confirmation) :

| Tool                 | Params (clés)                                  | Usage                                              |
| -------------------- | ---------------------------------------------- | -------------------------------------------------- |
| `containers_list`    | `all` (bool, défaut false)                     | Liste les conteneurs                               |
| `container_inspect`  | `name_or_id` (str)                             | Détails d'un conteneur                             |
| `container_logs`     | `name_or_id` (str), `tail` (int, défaut 100)   | Récupère les dernières lignes de logs              |
| `container_stats`    | `name_or_id` (str)                             | CPU/mémoire/réseau instantanés                     |
| `images_list`        | aucun                                          | Liste les images                                   |
| `volumes_list`       | aucun                                          | Liste les volumes                                  |
| `networks_list`      | aucun                                          | Liste les réseaux                                  |
| `health_report`      | `cpu_threshold`, `mem_threshold`, `restart_threshold` (ints, optionnels) | Rapport global de santé        |

Catégorie « actions » (`Role.OPERATOR`) :

| Tool                  | Params                                                                                |
| --------------------- | ------------------------------------------------------------------------------------- |
| `container_start`     | `name_or_id` (str)                                                                    |
| `container_stop`      | `name_or_id` (str), `timeout` (int, défaut 10)                                        |
| `container_restart`   | `name_or_id` (str), `timeout` (int, défaut 10)                                        |
| `container_pause`     | `name_or_id` (str)                                                                    |
| `container_unpause`   | `name_or_id` (str)                                                                    |
| `image_pull`          | `repository` (str), `tag` (str, défaut "latest")                                      |

Catégorie « destructive » (`Role.ADMIN`, exige `confirm: true`) :

| Tool                  | Params                                                                                |
| --------------------- | ------------------------------------------------------------------------------------- |
| `container_remove`    | `name_or_id` (str), `force` (bool), `confirm` (bool, **obligatoire = true**)          |
| `container_kill`      | `name_or_id` (str), `confirm` (bool, **obligatoire = true**)                          |
| `image_remove`        | `name_or_id` (str), `force` (bool), `confirm` (bool, **obligatoire = true**)          |
| `volume_remove`       | `name` (str), `confirm` (bool, **obligatoire = true**)                                |
| `network_remove`      | `name_or_id` (str), `confirm` (bool, **obligatoire = true**)                          |
| `prune_*`             | `confirm` (bool, **obligatoire = true**)                                              |

## Règles de sécurité

1. **Toujours demander confirmation explicite à l'utilisateur** avant tout appel
   destructif (`remove`, `kill`, `prune`). Reformule l'action et attends « oui »
   ou « confirme » avant d'envoyer `"confirm": true`.
2. Ne **jamais** supposer le `name_or_id` — si ambigu, appelle d'abord
   `containers_list` et propose les choix.
3. Limite `tail` à 200 lignes max par défaut pour `container_logs` (sinon la
   réponse explose le contexte).
4. Si la réponse `ok` est `false`, transmets le message d'erreur tel quel,
   n'essaie pas de bypasser via `exec` direct.

## Exemples d'appels

```bash
# Lister tous les conteneurs (y compris arrêtés)
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"containers_list","params":{"all":true}}'

# Rapport de santé
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"health_report","params":{"cpu_threshold":80,"mem_threshold":85}}'

# Redémarrer un conteneur
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"container_restart","params":{"name_or_id":"dockermcp-n8n","timeout":15}}'

# Supprimer un conteneur (action destructive — exige confirmation utilisateur)
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"container_remove","params":{"name_or_id":"test-old","force":false,"confirm":true}}'
```
