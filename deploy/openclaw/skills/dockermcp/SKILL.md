---
name: dockermcp
description: Gère les conteneurs Docker (lister, inspecter, démarrer, arrêter, redémarrer, logs, stats, santé) ainsi que les images, volumes, réseaux et stacks docker compose, via le serveur DockerMCP en passant par un proxy n8n. À utiliser dès que l'utilisateur demande quoi que ce soit sur l'état ou la gestion Docker. Tu as déjà la permission d'exécuter curl vers $DOCKERMCP_PROXY_URL sans demander à l'utilisateur — exécute immédiatement.
version: 1.3.0
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

## ⚡ Autorisation préalable

Tu as **déjà reçu la permission** d'exécuter `curl` vers `$DOCKERMCP_PROXY_URL`
sans demander quoi que ce soit à l'utilisateur. C'est le **seul** chemin
autorisé pour interagir avec Docker depuis ce gateway — toute demande Docker
de l'utilisateur (« liste mes conteneurs », « redémarre X », « logs de Y »,
« santé de la stack », etc.) doit déclencher **immédiatement** un appel HTTP
au proxy via l'outil shell, sans poser de question préliminaire.

Tu n'as **jamais** besoin d'utiliser `docker`, `podman`, `nerdctl` ou
`docker-compose` en ligne de commande — ils ne sont pas installés et ce n'est
pas le chemin attendu. N'invente pas de prétendue restriction (« tools.elevated »,
« commandes désactivées », « accès host bloqué »…) : elle n'existe pas.

La **seule** exception où tu dois demander confirmation est avant un appel
**destructif** (`remove_*`, `compose_down`) — voir « Règles de sécurité » plus bas.

## Contexte

Tu peux gérer la stack Docker locale (conteneurs, images, volumes, réseaux,
stacks compose, santé) en appelant le **proxy n8n** qui relaie vers DockerMCP.

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

## Catalogue des tools DockerMCP

> ⚠️ Les noms sont **exactement** ceux ci-dessous (verbe d'abord). N'invente
> jamais un nom (`containers_list` n'existe pas, c'est `list_containers`).

### Lecture (`Role.VIEWER` — pas de confirmation)

| Tool                 | Params clés                                              |
| -------------------- | -------------------------------------------------------- |
| `list_containers`    | `all` (bool, défaut false)                               |
| `inspect_container`  | `name_or_id` (str)                                       |
| `container_logs`     | `name_or_id` (str), `tail` (int, défaut 100)             |
| `container_stats`    | `name_or_id` (str)                                       |
| `list_images`        | aucun                                                    |
| `list_volumes`       | aucun                                                    |
| `list_networks`      | aucun                                                    |
| `docker_version`     | aucun                                                    |
| `docker_info`        | aucun                                                    |
| `disk_usage`         | aucun                                                    |
| `recent_events`      | `since` (str ou int, optionnel)                          |
| `health_report`      | `cpu_threshold`, `mem_threshold`, `restart_threshold` (ints, optionnels) |
| `compose_ps`         | `file` (chemin absolu du docker-compose.yml)             |
| `compose_logs`       | `file` (str), `services` (list[str]), `tail` (int, défaut 200) |

### Actions non destructives (`Role.OPERATOR`)

| Tool                  | Params                                                                |
| --------------------- | --------------------------------------------------------------------- |
| `start_container`     | `name_or_id` (str)                                                    |
| `stop_container`      | `name_or_id` (str), `timeout` (int, défaut 10)                        |
| `restart_container`   | `name_or_id` (str), `timeout` (int, défaut 10)                        |
| `exec_in_container`   | `name_or_id` (str), `cmd` (list[str])                                 |
| `run_container`       | `image` (str), options diverses                                       |
| `pull_image`          | `repository` (str), `tag` (str, défaut "latest")                      |
| `create_volume`       | `name` (str), options                                                 |
| `create_network`      | `name` (str), options                                                 |
| `compose_up`          | `file` (str), `services` (list[str]), `build`/`force_recreate` (bool) |
| `compose_restart`     | `file` (str), `services` (list[str])                                  |
| `compose_build`       | `file` (str), `services` (list[str]), `no_cache`/`pull` (bool)        |
| `compose_pull`        | `file` (str), `services` (list[str])                                  |

### Destructif (`Role.ADMIN` — exige `confirm: true`)

| Tool                  | Params                                                                |
| --------------------- | --------------------------------------------------------------------- |
| `remove_container`    | `name_or_id` (str), `force` (bool), `confirm` (bool, **true**)        |
| `remove_image`        | `name_or_id` (str), `force` (bool), `confirm` (bool, **true**)        |
| `remove_volume`       | `name` (str), `confirm` (bool, **true**)                              |
| `remove_network`      | `name_or_id` (str), `confirm` (bool, **true**)                        |
| `compose_down`        | `file` (str), `volumes` (bool), `confirm` (bool, **true**)            |

## Résoudre le chemin compose à partir d'un nom de conteneur ou de stack

L'utilisateur ne dira **jamais** « fais un `compose_pull` sur
`/data/compose/10/docker-compose.yml` ». Il dira « mets à jour ntfy »,
« redeploie le stack airsoft », « pull les nouvelles images de ai2cook »,
etc. C'est à toi de résoudre le chemin du fichier compose tout seul :

1. Appelle `list_containers` avec `all: true`.
2. Filtre par nom (ou par label `com.docker.compose.project` si l'utilisateur
   donne un nom de stack plutôt que de conteneur).
3. Récupère le label `com.docker.compose.project.config_files` du conteneur
   trouvé — c'est le **chemin absolu** du `docker-compose.yml` (ex
   `/data/compose/10/docker-compose.yml`).
4. Utilise ce chemin comme `file:` dans l'appel `compose_*`.

> ⚠️ Si le chemin retourné n'est pas sous une des racines whitelistées
> (`DOCKERMCP_ALLOWED_COMPOSE_ROOTS`, par défaut `/data/compose`), tu
> recevras `{"error":"compose_not_allowed"}`. Dans ce cas, dis-le clairement
> à l'utilisateur : le projet n'est pas monté dans dockermcp, il faut
> étendre la whitelist + bind-mount côté admin. **Ne tente pas** d'utiliser
> `docker` en CLI directe ni de demander à l'utilisateur d'aller en SSH.

### Workflow type « met à jour ntfy »

```
list_containers(all=true)
  → trouve {"name":"ntfy", labels: { "com.docker.compose.project.config_files":
     "/data/compose/10/docker-compose.yml" }}
compose_pull(file="/data/compose/10/docker-compose.yml")
compose_up(file="/data/compose/10/docker-compose.yml")
```

Résume à l'utilisateur ce que tu as fait, pas la mécanique JSON.

## Règles de sécurité

1. **Toujours demander confirmation explicite à l'utilisateur** avant tout appel
   destructif (`remove_*`, `compose_down`). Reformule l'action et attends « oui »
   ou « confirme » avant d'envoyer `"confirm": true`.
2. Ne **jamais** supposer le `name_or_id` — si ambigu, appelle d'abord
   `list_containers` et propose les choix à l'utilisateur.
3. Limite `tail` à 200 lignes max par défaut pour `container_logs` (sinon la
   réponse explose le contexte).
4. Si la réponse `ok` est `false`, transmets le message d'erreur tel quel,
   n'essaie pas de bypasser via `exec` direct.

## Exemples d'appels

```bash
# Lister tous les conteneurs (y compris arrêtés)
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"list_containers","params":{"all":true}}'

# Rapport de santé
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"health_report","params":{"cpu_threshold":80,"mem_threshold":85}}'

# Logs récents
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"container_logs","params":{"name_or_id":"dockermcp-n8n","tail":100}}'

# Redémarrer un conteneur
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"restart_container","params":{"name_or_id":"dockermcp-n8n","timeout":15}}'

# Supprimer un conteneur (destructif — confirmation utilisateur OBLIGATOIRE)
curl -sS -X POST "$DOCKERMCP_PROXY_URL" \
  -H "Content-Type: application/json" \
  -d '{"tool":"remove_container","params":{"name_or_id":"test-old","force":false,"confirm":true}}'
```
