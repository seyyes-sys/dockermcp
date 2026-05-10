"""Point d'entrée CLI : `python -m dockermcp`."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from dockermcp.auth import get_token_map, is_read_only
from dockermcp.server import run, transport_from_env


def _setup_logging() -> None:
    # Logs sur stderr uniquement — stdout est réservé au transport MCP stdio.
    logging.basicConfig(
        level=os.getenv("DOCKERMCP_LOG_LEVEL", "INFO").upper(),
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _setup_audit_file()


def _setup_audit_file() -> None:
    """Configure un RotatingFileHandler dédié au logger `dockermcp.audit`.

    Activé uniquement si ``DOCKERMCP_AUDIT_FILE`` est défini. Le logger
    audit reste également visible sur stderr (propagate) pour faciliter
    le debug en dev.
    """
    audit_path = os.getenv("DOCKERMCP_AUDIT_FILE")
    if not audit_path:
        return

    max_bytes = int(os.getenv("DOCKERMCP_AUDIT_MAX_BYTES", str(10 * 1024 * 1024)))
    backups = int(os.getenv("DOCKERMCP_AUDIT_BACKUPS", "7"))

    path = Path(audit_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backups,
        encoding="utf-8",
    )
    # Format : timestamp ISO + payload JSON déjà produit par audit.py
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

    audit_logger = logging.getLogger("dockermcp.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(handler)

    logging.getLogger("dockermcp").info(
        "Audit fichier activé : %s (maxBytes=%d, backups=%d)",
        path,
        max_bytes,
        backups,
    )


def main() -> None:
    _setup_logging()
    log = logging.getLogger("dockermcp")

    transport = transport_from_env()
    host = os.getenv("DOCKERMCP_HTTP_HOST", "127.0.0.1")
    port = int(os.getenv("DOCKERMCP_HTTP_PORT", "8765"))

    if transport != "stdio" and not get_token_map():
        log.error(
            "Transport=%s requiert DOCKERMCP_TOKENS (mapping token:role). Abandon.",
            transport,
        )
        sys.exit(2)

    if is_read_only():
        log.warning("Mode lecture seule activé (DOCKERMCP_READ_ONLY).")

    run(transport, host=host, port=port)


if __name__ == "__main__":
    main()
