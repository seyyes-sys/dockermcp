#!/usr/bin/env bash
#
# preflight.sh — Diagnostic read-only avant déploiement de DockerMCP Suite.
# N'effectue AUCUNE modification sur le serveur.
#
# Usage (sur le serveur cible) :
#   curl -fsSL https://raw.githubusercontent.com/seyyes-sys/dockermcp/main/deploy/scripts/preflight.sh | bash
# Ou, après clone :
#   bash deploy/scripts/preflight.sh
#
# Partage la sortie complète à l'opérateur DockerMCP.

set -u
LC_ALL=C

CADDY_NET_GUESS="${CADDY_NET_GUESS:-compose_airsoft-network}"

section() { printf "\n\n========== %s ==========\n" "$1"; }
run()     { printf "\n$ %s\n" "$*"; eval "$@" 2>&1 | sed 's/^/  /' || true; }

section "Identité système"
run "uname -a"
run "cat /etc/os-release | head -n 5"
run "uptime"

section "Ressources"
run "free -h"
run "df -h /var/lib/docker / 2>/dev/null"
run "nproc"

section "Versions outils"
run "docker --version"
run "docker compose version"
run "ssh -V 2>&1"
run "git --version"

section "Daemon Docker"
run "docker info --format 'Containers: {{.Containers}} (running={{.ContainersRunning}}) | Images: {{.Images}} | Storage: {{.Driver}} | Cgroup: {{.CgroupDriver}}'"
run "docker system df"

section "Conteneurs en cours"
run "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"

section "Tous les conteneurs (y compris stoppés)"
run "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'"

section "Réseaux Docker"
run "docker network ls"
printf "\n--- Détail du réseau Caddy supposé (%s) ---\n" "$CADDY_NET_GUESS"
if docker network inspect "$CADDY_NET_GUESS" >/dev/null 2>&1; then
    run "docker network inspect $CADDY_NET_GUESS --format '{{.Name}} ({{.Driver}}) — containers: {{range .Containers}}{{.Name}} {{end}}'"
else
    echo "  ⚠️  Réseau '$CADDY_NET_GUESS' INTROUVABLE. Cherche ci-dessous le bon nom."
fi
printf "\n--- Réseaux contenant 'caddy' ou 'proxy' ---\n"
run "docker network ls --format '{{.Name}}' | grep -iE 'caddy|proxy' || echo '(aucun)'"

section "Volumes Docker (nommés)"
run "docker volume ls"

section "Ports TCP en écoute sur l'hôte"
if command -v ss >/dev/null 2>&1; then
    run "ss -tlnp 2>/dev/null | head -n 30"
else
    run "netstat -tlnp 2>/dev/null | head -n 30"
fi

section "Conflits potentiels"
echo "--- Conteneurs susceptibles d'entrer en collision (noms 'dockermcp*' ou ports 8765/5678) ---"
run "docker ps -a --filter 'name=dockermcp' --format '{{.Names}} ({{.Status}})' || echo '(aucun)'"
run "docker ps --format '{{.Names}} {{.Ports}}' | grep -E ':(8765|5678|2375)->' || echo '(aucun port en collision)'"

section "Caddy"
echo "--- Conteneur Caddy détecté ---"
caddy_ctn="$(docker ps --format '{{.Names}}' | grep -iE '^caddy|caddy$' | head -n1 || true)"
if [ -n "$caddy_ctn" ]; then
    echo "  → $caddy_ctn"
    run "docker inspect $caddy_ctn --format '{{range .Mounts}}{{.Source}} → {{.Destination}} ({{.Mode}}){{println}}{{end}}'"
    run "docker exec $caddy_ctn caddy version 2>/dev/null || echo '(caddy CLI indisponible dans le conteneur)'"
    echo "--- Liste des sites configurés dans le Caddyfile (extraits 'xxx.hexotik.ovh') ---"
    run "docker exec $caddy_ctn sh -c 'grep -hE \"^[a-z0-9.-]+\\.hexotik\\.ovh\" /etc/caddy/*.conf /etc/caddy/Caddyfile 2>/dev/null | sort -u' || echo '(introuvable)'"
else
    echo "  ⚠️  Aucun conteneur nommé 'caddy*' détecté. Indique son nom à l'opérateur."
fi

section "DNS — résolution des futurs domaines DockerMCP"
for host in dockermcp.hexotik.ovh n8n-it.hexotik.ovh; do
    printf "\n--- %s ---\n" "$host"
    if command -v dig >/dev/null 2>&1; then
        run "dig +short $host"
    else
        run "getent hosts $host"
    fi
done

section "Stack ai2cook (à NE PAS perturber)"
run "docker ps --filter 'name=ai2cook' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'"
run "docker volume ls | grep ai2cook || echo '(aucun)'"

section "Image GHCR DockerMCP — test de tirage"
echo "(ne pull pas réellement, vérifie juste la résolution du manifest)"
run "docker manifest inspect ghcr.io/seyyes-sys/dockermcp:latest 2>&1 | head -n 10 || true"

section "Fin du preflight"
echo "Copie l'intégralité de cette sortie à l'opérateur DockerMCP."
