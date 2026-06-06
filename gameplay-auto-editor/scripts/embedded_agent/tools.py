"""Agent tools with risk classification (least-privilege connector pattern)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from scripts.clip_metadata import quality_tier, summarize_enhancements
from scripts.embedded_agent.context_builder import build_app_context, build_setup_help


class ToolRisk(str, Enum):
    SAFE = "safe"
    REVIEW = "review"
    BLOCKED = "blocked"


@dataclass
class ToolDefinition:
    name: str
    description: str
    risk: ToolRisk
    handler: Callable[..., dict[str, Any]]


def get_tool_registry() -> dict[str, ToolDefinition]:
    return {tool.name: tool for tool in _ALL_TOOLS}


def list_tool_schemas() -> list[dict[str, str]]:
    return [
        {"name": tool.name, "description": tool.description, "risk": tool.risk.value}
        for tool in _ALL_TOOLS
    ]


def _tool_get_run_summary(*, report: dict | None = None, **_: Any) -> dict[str, Any]:
    if not report:
        return {"ok": False, "message": "No run report available yet. Generate clips first."}
    return {
        "ok": True,
        "clips_created": report.get("clips_created", 0),
        "detection_mode": report.get("detection_mode"),
        "used_fallback": bool(report.get("used_fallback")),
        "quality_tier_counts": report.get("quality_tier_counts"),
        "features_applied": report.get("features_applied"),
        "failure_reason": report.get("failure_reason"),
    }


def _tool_get_clip_details(*, report: dict | None = None, clip_index: int = 1, **_: Any) -> dict[str, Any]:
    if not report:
        return {"ok": False, "message": "No run report available."}
    clips = list(report.get("clips") or [])
    if not clips:
        return {"ok": False, "message": "No clips in the latest run."}
    idx = max(1, min(int(clip_index), len(clips))) - 1
    clip = clips[idx]
    return {
        "ok": True,
        "clip_index": idx + 1,
        "score": clip.get("score"),
        "quality_tier": clip.get("quality_tier") or quality_tier(clip),
        "hook_text": clip.get("hook_text"),
        "caption_text": clip.get("caption_text"),
        "social_caption": clip.get("social_caption"),
        "categories": clip.get("categories"),
        "selection_mode": clip.get("selection_mode"),
        "enhancements": summarize_enhancements(clip),
        "start": clip.get("start"),
        "end": clip.get("end"),
    }


def _tool_get_config_status(*, config: dict | None = None, **_: Any) -> dict[str, Any]:
    cfg = dict(config or {})
    rollout = dict(cfg.get("rollout") or {}).get("optional_features") or {}
    vision = dict(cfg.get("vision") or {})
    return {
        "ok": True,
        "vision_provider": vision.get("provider", "heuristic"),
        "game_profile": (cfg.get("highlight_detection") or {}).get("game_profile", "generic"),
        "platform_preset": (cfg.get("rendering") or {}).get("platform_preset", "tiktok"),
        "optional_features": rollout,
        "embedded_agent_enabled": bool((cfg.get("embedded_agent") or {}).get("enabled")),
    }


def _tool_get_setup_help(**_: Any) -> dict[str, Any]:
    return {"ok": True, "help": build_setup_help()}


def _tool_suggest_settings(*, report: dict | None = None, config: dict | None = None, **_: Any) -> dict[str, Any]:
    suggestions: list[dict[str, str]] = []
    cfg = dict(config or {})
    highlight = dict(cfg.get("highlight_detection") or {})
    report = dict(report or {})

    if report.get("used_fallback"):
        suggestions.append(
            {
                "setting": "highlight_detection.min_score",
                "current": str(highlight.get("min_score", 60)),
                "suggested": "25",
                "reason": "Fallback clips were used — lower min score to capture more moments.",
            }
        )
    if int(report.get("clips_created") or 0) <= 1 and int(highlight.get("max_clips") or 5) > 1:
        suggestions.append(
            {
                "setting": "highlight_detection.max_clips",
                "current": str(highlight.get("max_clips", 5)),
                "suggested": str(max(3, int(highlight.get("max_clips", 5)))),
                "reason": "Few clips were produced — verify min score and game profile match your footage.",
            }
        )
    if str(highlight.get("game_profile", "generic")) == "generic":
        suggestions.append(
            {
                "setting": "highlight_detection.game_profile",
                "current": "generic",
                "suggested": "valorant / cod / fortnite",
                "reason": "A game-specific profile improves OCR regions and scoring weights.",
            }
        )
    vision = dict(cfg.get("vision") or {})
    if vision.get("provider") == "heuristic":
        suggestions.append(
            {
                "setting": "vision.provider",
                "current": "heuristic",
                "suggested": "auto or openai",
                "reason": "AI vision can improve highlight detection when an API key is configured.",
            }
        )
    return {"ok": True, "suggestions": suggestions}


def _tool_explain_clip_selection(*, report: dict | None = None, clip_index: int = 1, **_: Any) -> dict[str, Any]:
    result = _tool_get_clip_details(report=report, clip_index=clip_index)
    if not result.get("ok"):
        return result
    tier = result.get("quality_tier")
    mode = result.get("selection_mode") or "normal"
    score = result.get("score")
    categories = result.get("categories") or []
    explanation_parts = [f"Clip {clip_index} scored {score}/100 with tier '{tier}'."]
    if mode.startswith("fallback"):
        explanation_parts.append("This was selected by fallback logic when no strong highlights were found.")
    elif tier == "review_recommended":
        explanation_parts.append("Confidence is moderate — review before posting.")
    if categories:
        explanation_parts.append(f"Detected categories: {', '.join(categories)}.")
    enhancements = result.get("enhancements") or []
    if enhancements:
        explanation_parts.append(f"Applied enhancements: {', '.join(enhancements)}.")
    return {"ok": True, "explanation": " ".join(explanation_parts), **result}


_ALL_TOOLS = [
    ToolDefinition("get_run_summary", "Summarize the latest clip generation run.", ToolRisk.SAFE, _tool_get_run_summary),
    ToolDefinition("get_clip_details", "Get metadata for a specific clip by index.", ToolRisk.SAFE, _tool_get_clip_details),
    ToolDefinition("get_config_status", "Show current app configuration status.", ToolRisk.SAFE, _tool_get_config_status),
    ToolDefinition("get_setup_help", "Return setup and troubleshooting checklist.", ToolRisk.SAFE, _tool_get_setup_help),
    ToolDefinition(
        "suggest_settings",
        "Propose config changes (user must approve before applying).",
        ToolRisk.REVIEW,
        _tool_suggest_settings,
    ),
    ToolDefinition(
        "explain_clip_selection",
        "Explain why a clip was selected and scored.",
        ToolRisk.SAFE,
        _tool_explain_clip_selection,
    ),
]
