"""Prompts MCP pré-construits pour DockerMCP.

Un prompt est un modèle de conversation paramétré que le client MCP peut
sélectionner dans une UI (ex. Claude Desktop : « slash commands »). Cela
évite à l'utilisateur de formuler manuellement la requête « regarde
l'inspect, les logs et les events de mon conteneur X et explique-moi
pourquoi il flappe ».

Prompts exposés :

- ``diagnose_container(name)``     — diagnostic d'un conteneur précis
- ``triage_health()``              — rapport de santé global commenté
- ``incident_postmortem(name)``    — rédaction d'un post-mortem
- ``explain_compose(file)``        — explication d'un fichier compose
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base


def register(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="diagnose_container",
        title="Diagnostiquer un conteneur",
        description="Analyse inspect + logs + events d'un conteneur et propose un diagnostic.",
    )
    def diagnose_container(name: str) -> list[base.Message]:
        return [
            base.UserMessage(
                "Tu es un SRE expert Docker. Diagnostique le conteneur "
                f"`{name}` en suivant cette procédure :\n"
                f"1. Lis la ressource `docker://containers/{name}` (inspect).\n"
                f"2. Lis la ressource `docker://containers/{name}/logs` "
                "(200 dernières lignes).\n"
                "3. Appelle l'outil `recent_events` pour voir les événements "
                "Docker récents (kill, OOM, restart, …).\n"
                "4. Si pertinent, appelle `container_stats` pour voir CPU/mém.\n\n"
                "Synthétise ensuite :\n"
                "- **État courant** (healthy / unhealthy / restarting / exited).\n"
                "- **Symptômes** observés dans les logs (erreurs récurrentes).\n"
                "- **Cause probable** avec niveau de confiance.\n"
                "- **Actions recommandées**, classées par ordre d'impact.\n"
                "Si une action est destructive, propose-la sans l'exécuter."
            )
        ]

    @mcp.prompt(
        name="triage_health",
        title="Triage santé globale",
        description="Synthétise le rapport de santé de tous les conteneurs.",
    )
    def triage_health() -> list[base.Message]:
        return [
            base.UserMessage(
                "Tu es un SRE de garde. Évalue la santé globale des conteneurs :\n"
                "1. Lis la ressource `docker://health` ou appelle l'outil "
                "`health_report`.\n"
                "2. Pour chaque catégorie (`unhealthy`, `flapping`, `crashed`, "
                "`high_cpu`, `high_mem`), classe les conteneurs par criticité.\n"
                "3. Indique pour chacun si une investigation `diagnose_container` "
                "est nécessaire.\n"
                "4. Termine par un **résumé exécutif** (3 lignes max) "
                "indiquant la priorité globale : OK / WARN / CRIT."
            )
        ]

    @mcp.prompt(
        name="incident_postmortem",
        title="Post-mortem d'incident",
        description="Rédige un post-mortem structuré pour un conteneur ayant eu un incident.",
    )
    def incident_postmortem(name: str) -> list[base.Message]:
        return [
            base.UserMessage(
                f"Rédige un post-mortem pour l'incident sur le conteneur `{name}` "
                "en suivant le format Google SRE :\n\n"
                f"1. Collecte les données : `docker://containers/{name}`, "
                f"`docker://containers/{name}/logs`, et `recent_events`.\n"
                "2. Rédige les sections suivantes :\n"
                "   - **Résumé** (1 phrase).\n"
                "   - **Impact** (services touchés, durée).\n"
                "   - **Chronologie** (timestamps des évènements clés).\n"
                "   - **Cause racine** (avec preuves issues des logs).\n"
                "   - **Actions correctives** (immédiates / moyen terme).\n"
                "   - **Actions préventives** (à proposer, non exécuter).\n\n"
                "Pas de blame. Reste factuel."
            )
        ]

    @mcp.prompt(
        name="explain_compose",
        title="Expliquer une stack Compose",
        description="Décrit le fonctionnement d'un projet Compose et liste les risques.",
    )
    def explain_compose(file: str) -> list[base.Message]:
        return [
            base.UserMessage(
                f"Analyse le projet Compose au chemin `{file}` :\n"
                f"1. Appelle `compose_ps` (file=`{file}`) pour voir l'état "
                "actuel des services.\n"
                "2. Décris l'architecture : services, dépendances, ports exposés, "
                "volumes montés.\n"
                "3. Identifie les **risques de sécurité** "
                "(ports publics, bind-mounts sensibles, images non pinnées, "
                "variables d'environnement contenant des secrets potentiels).\n"
                "4. Suggère des améliorations sans appliquer de modification."
            )
        ]
