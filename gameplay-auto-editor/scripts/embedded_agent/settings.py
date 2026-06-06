"""Embedded agent configuration (no secrets stored here)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class EmbeddedAgentSettings:
    enabled: bool
    mode: str
    provider: str
    model: str
    max_turns_per_session: int
    max_tool_calls_per_turn: int
    max_context_clips: int
    allow_caption_rewrite: bool
    allow_settings_suggestions: bool
    require_tool_approval: bool
    openai_api_key: str
    anthropic_api_key: str


def load_agent_settings(config: dict | None = None) -> EmbeddedAgentSettings:
    cfg = dict(config or {})
    agent = dict(cfg.get("embedded_agent") or {})
    vision = dict(cfg.get("vision") or {})
    return EmbeddedAgentSettings(
        enabled=bool(agent.get("enabled", False)),
        mode=str(agent.get("mode", "advisor")),
        provider=str(agent.get("provider", "openai")).lower(),
        model=str(agent.get("model") or vision.get("openai_model") or "gpt-4o-mini"),
        max_turns_per_session=max(1, int(agent.get("max_turns_per_session", 50))),
        max_tool_calls_per_turn=max(1, int(agent.get("max_tool_calls_per_turn", 3))),
        max_context_clips=max(1, int(agent.get("max_context_clips", 5))),
        allow_caption_rewrite=bool(agent.get("allow_caption_rewrite", False)),
        allow_settings_suggestions=bool(agent.get("allow_settings_suggestions", True)),
        require_tool_approval=bool(agent.get("require_tool_approval", True)),
        openai_api_key=str(vision.get("openai_api_key") or os.getenv("OPENAI_API_KEY") or "").strip(),
        anthropic_api_key=str(vision.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY") or "").strip(),
    )
