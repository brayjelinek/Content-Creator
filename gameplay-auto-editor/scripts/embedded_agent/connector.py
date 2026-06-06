"""Mediate agent tool calls with risk checks, audit trail, and approval gates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from scripts.embedded_agent.audit import append_audit
from scripts.embedded_agent.tools import ToolRisk, get_tool_registry

logger = logging.getLogger(__name__)

ApprovalCallback = Callable[[str, dict[str, Any]], bool]


class AgentConnector:
    """Least-privilege gateway for all agent tool invocations."""

    def __init__(
        self,
        *,
        project_root: Path,
        require_approval: bool = True,
        approval_callback: ApprovalCallback | None = None,
    ):
        self.project_root = project_root
        self.require_approval = require_approval
        self.approval_callback = approval_callback
        self._registry = get_tool_registry()

    def execute(
        self,
        tool_name: str,
        *,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool = self._registry.get(tool_name)
        if not tool:
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}

        if tool.risk == ToolRisk.BLOCKED:
            append_audit(
                self.project_root,
                {"action": "tool_blocked", "tool": tool_name, "risk": tool.risk.value},
            )
            return {"ok": False, "error": f"Tool {tool_name} is blocked by policy."}

        if tool.risk == ToolRisk.REVIEW and self.require_approval:
            approved = True
            if self.approval_callback:
                approved = bool(self.approval_callback(tool_name, arguments or {}))
            append_audit(
                self.project_root,
                {
                    "action": "tool_review",
                    "tool": tool_name,
                    "approved": approved,
                    "arguments": _safe_args(arguments),
                },
            )
            if not approved:
                return {"ok": False, "error": "User declined tool execution."}

        try:
            merged = dict(context or {})
            merged.update(arguments or {})
            result = tool.handler(**merged)
            append_audit(
                self.project_root,
                {
                    "action": "tool_executed",
                    "tool": tool_name,
                    "risk": tool.risk.value,
                    "ok": bool(result.get("ok", True)),
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("[AgentConnector] Tool %s failed", tool_name)
            append_audit(
                self.project_root,
                {"action": "tool_error", "tool": tool_name, "error": str(exc)},
            )
            return {"ok": False, "error": str(exc)}


def _safe_args(arguments: dict[str, Any] | None) -> dict[str, Any]:
    if not arguments:
        return {}
    return {key: str(value)[:200] for key, value in arguments.items()}
