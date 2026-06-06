"""Immutable audit trail for agent tool calls and user approvals."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AUDIT_FILENAME = "agent_audit.jsonl"


def append_audit(project_root: Path, entry: dict[str, Any]) -> None:
    """Append a non-secret audit entry."""
    try:
        path = project_root / "logs" / AUDIT_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **entry,
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError as exc:
        logger.warning("[AgentAudit] Could not write audit entry: %s", exc)
