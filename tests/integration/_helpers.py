"""Constantes et helpers partagés pour les tests d'intégration.

Distincts de ``conftest.py`` car celui-ci n'est pas importable comme
module standard (pytest l'ajoute au sys.path automatiquement, mais pas
d'import direct).
"""

from __future__ import annotations

import json
from typing import Any

IT_PREFIX = "dockermcp-it-"
IT_IMAGE = "alpine:3.20"


def call_tool_payload(result: Any) -> dict[str, Any]:
    """Extrait le payload JSON d'un résultat ``call_tool``."""
    if isinstance(result, tuple) and len(result) == 2:
        _content, structured = result
        if isinstance(structured, dict):
            return structured
        result = _content
    if isinstance(result, list) and result:
        first = result[0]
        text = getattr(first, "text", None)
        if text is not None:
            return json.loads(text)
    if isinstance(result, dict):
        return result
    raise AssertionError(f"Format de résultat call_tool inattendu : {result!r}")
