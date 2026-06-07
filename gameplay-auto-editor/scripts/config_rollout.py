"""Stable feature rollout defaults and phased quality presets merged into user config."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from scripts.clip_timing import INDUSTRY_TIMING_DEFAULTS

DEFAULT_ROLLOUT: dict[str, Any] = {
    "phase": "phase_2",
    "stable_features": {
        "min_clip_duration": True,
        "adaptive_padding": True,
        "platform_presets": True,
        "viral_polish_always_on": True,
        "burn_captions_on_overlay_fail": True,
        "game_profiles": True,
        "quality_tiers": True,
        "enhancement_badges": True,
        "industry_timing": True,
    },
    "optional_features": {
        "smart_reframe": False,
        "sound_effects": False,
        "chat_signals": False,
        "styled_ass_captions": False,
        "whisper_transcription": False,
        "batch_queue": True,
        "direct_publish": False,
        "embedded_agent": False,
    },
}

ROLLOUT_PHASES: dict[str, dict[str, Any]] = {
    "stable": {
        "label": "Stable",
        "summary": "Proven defaults only — slow-mo, zoom, and static hook captions.",
        "config": {},
    },
    "phase_1": {
        "label": "Phase 1 · Visual polish",
        "summary": "Facecam split, styled ASS captions, and impact sound effects.",
        "config": {
            "rollout": {
                "optional_features": {
                    "smart_reframe": True,
                    "styled_ass_captions": True,
                    "sound_effects": True,
                },
            },
            "rendering": {
                "smart_reframe": {"enabled": True},
                "viral_enhancements": {
                    "styled_ass_captions_enabled": True,
                    "ass_karaoke_enabled": True,
                    "sound_effects_enabled": True,
                },
            },
        },
    },
    "phase_2": {
        "label": "Phase 2 · Smarter clips",
        "summary": "Phase 1 plus Whisper speech captions and hybrid vision scoring.",
        "config": {
            "rollout": {
                "optional_features": {
                    "smart_reframe": True,
                    "styled_ass_captions": True,
                    "sound_effects": True,
                    "whisper_transcription": True,
                },
            },
            "vision": {"provider": "auto"},
            "transcription": {
                "enabled": True,
                "use_for_captions": True,
                "use_for_hooks": True,
            },
            "rendering": {
                "smart_reframe": {"enabled": True},
                "viral_enhancements": {
                    "styled_ass_captions_enabled": True,
                    "ass_karaoke_enabled": True,
                    "sound_effects_enabled": True,
                },
            },
        },
    },
    "phase_3": {
        "label": "Phase 3 · Full quality",
        "summary": "Phase 2 plus chat spike scoring, screen shake, and embedded assistant.",
        "config": {
            "rollout": {
                "optional_features": {
                    "smart_reframe": True,
                    "styled_ass_captions": True,
                    "sound_effects": True,
                    "whisper_transcription": True,
                    "chat_signals": True,
                    "embedded_agent": True,
                },
            },
            "vision": {"provider": "auto"},
            "transcription": {
                "enabled": True,
                "use_for_captions": True,
                "use_for_hooks": True,
            },
            "embedded_agent": {
                "enabled": True,
                "allow_caption_rewrite": True,
            },
            "rendering": {
                "smart_reframe": {"enabled": True},
                "viral_enhancements": {
                    "styled_ass_captions_enabled": True,
                    "ass_karaoke_enabled": True,
                    "sound_effects_enabled": True,
                    "screen_shake": True,
                },
            },
        },
    },
    "custom": {
        "label": "Custom",
        "summary": "Manual control via config.json optional_features only.",
        "config": {},
    },
}

DEFAULT_TRANSCRIPTION: dict[str, Any] = {
    "enabled": False,
    "provider": "whisper_cli",
    "model": "tiny",
    "language": "",
    "use_for_captions": True,
    "use_for_hooks": False,
    "max_segment_seconds": 30,
    "openai_model": "whisper-1",
}

DEFAULT_CHAT_SIGNALS: dict[str, Any] = {
    "enabled": False,
    "chat_log_path": "",
    "window_seconds": 2.0,
    "min_messages_per_window": 5,
    "match_window_seconds": 2.5,
    "score_bonus": 15,
}

DEFAULT_SOCIAL_PUBLISH: dict[str, Any] = {
    "enabled": False,
    "require_confirm": True,
    "max_posts_per_session": 10,
    "default_privacy": "private",
}

DEFAULT_EMBEDDED_AGENT: dict[str, Any] = {
    "enabled": False,
    "mode": "advisor",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "max_turns_per_session": 50,
    "max_tool_calls_per_turn": 3,
    "max_context_clips": 5,
    "allow_caption_rewrite": False,
    "allow_settings_suggestions": True,
    "require_tool_approval": True,
}


def list_rollout_phases() -> list[dict[str, str]]:
    """Return rollout phase metadata for UI selectors."""
    return [
        {
            "id": phase_id,
            "label": meta["label"],
            "summary": meta["summary"],
        }
        for phase_id, meta in ROLLOUT_PHASES.items()
    ]


def resolve_rollout_phase(phase: str | None) -> str:
    """Normalize a rollout phase id."""
    normalized = str(phase or DEFAULT_ROLLOUT["phase"]).strip().lower()
    if normalized not in ROLLOUT_PHASES:
        return "stable"
    return normalized


def describe_rollout_phase(phase: str | None) -> dict[str, str]:
    """Return label and summary text for a rollout phase."""
    phase_id = resolve_rollout_phase(phase)
    meta = ROLLOUT_PHASES[phase_id]
    return {
        "id": phase_id,
        "label": str(meta["label"]),
        "summary": str(meta["summary"]),
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_phase_preset(config: dict[str, Any], phase: str) -> dict[str, Any]:
    """Layer phased defaults on top of user config so presets can enable optional features."""
    if phase == "custom":
        return deepcopy(config)

    preset = dict(ROLLOUT_PHASES[phase].get("config") or {})
    merged = _deep_merge(deepcopy(config), preset)
    merged.setdefault("rollout", {})["phase"] = phase
    return merged


def apply_rollout_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """Merge rollout defaults and phased presets without overriding explicit user settings."""
    phase = resolve_rollout_phase((config.get("rollout") or {}).get("phase"))
    merged = _apply_phase_preset(config, phase)

    rollout = dict(DEFAULT_ROLLOUT)
    rollout.update(dict(merged.get("rollout") or {}))
    rollout["phase"] = phase
    rollout["stable_features"] = {
        **DEFAULT_ROLLOUT["stable_features"],
        **dict((merged.get("rollout") or {}).get("stable_features") or {}),
    }
    rollout["optional_features"] = {
        **DEFAULT_ROLLOUT["optional_features"],
        **dict((merged.get("rollout") or {}).get("optional_features") or {}),
    }
    merged["rollout"] = rollout

    chat = dict(DEFAULT_CHAT_SIGNALS)
    chat.update(dict(merged.get("chat_signals") or {}))
    merged["chat_signals"] = chat

    transcription = dict(DEFAULT_TRANSCRIPTION)
    transcription.update(dict(merged.get("transcription") or {}))
    merged["transcription"] = transcription

    highlight = dict(merged.get("highlight_detection") or {})
    weights = dict(highlight.get("weighted_scoring") or {})
    weights.setdefault("audio_spike_bonus", 10)
    weights.setdefault("audio_spike_threshold", 12)
    weights.setdefault("chat_spike_bonus", chat["score_bonus"])
    highlight["weighted_scoring"] = weights
    stable = dict(rollout.get("stable_features") or {})
    if stable.get("industry_timing", True):
        timing = dict(INDUSTRY_TIMING_DEFAULTS)
        timing["industry_timing_enabled"] = bool(highlight.get("industry_timing_enabled", True))
        timing.update({k: v for k, v in highlight.items() if k in timing or k == "timestamp_smoothing"})
        highlight.update(timing)
    merged["highlight_detection"] = highlight

    rendering = dict(merged.get("rendering") or {})
    viral = dict(rendering.get("viral_enhancements") or {})
    smart = dict(rendering.get("smart_reframe") or {})
    optional = dict(rollout.get("optional_features") or {})

    if rollout["stable_features"].get("viral_polish_always_on", True):
        viral.setdefault("always_apply_polish", True)
        viral.setdefault("require_validation_for_slowmo", False)
        viral.setdefault("require_validation_for_effects", False)
    if rollout["stable_features"].get("burn_captions_on_overlay_fail", True):
        viral.setdefault("burn_captions_when_overlay_missing", True)

    if optional.get("smart_reframe", False):
        smart["enabled"] = True
    else:
        smart["enabled"] = False

    if optional.get("sound_effects", False):
        viral["sound_effects_enabled"] = True
    else:
        viral["sound_effects_enabled"] = False

    if optional.get("styled_ass_captions", False):
        viral["styled_ass_captions_enabled"] = True
        viral["ass_karaoke_enabled"] = True
    else:
        viral["styled_ass_captions_enabled"] = False
        viral["ass_karaoke_enabled"] = False

    rendering["viral_enhancements"] = viral
    rendering["smart_reframe"] = smart
    merged["rendering"] = rendering

    if optional.get("chat_signals", False) and str(chat.get("chat_log_path", "")).strip():
        chat["enabled"] = True
    else:
        chat["enabled"] = False
    merged["chat_signals"] = chat

    if optional.get("whisper_transcription", False):
        transcription["enabled"] = True
    else:
        transcription["enabled"] = False
    merged["transcription"] = transcription

    social = dict(DEFAULT_SOCIAL_PUBLISH)
    social.update(dict(merged.get("social_publish") or {}))
    if not optional.get("direct_publish", False):
        social["enabled"] = False
    merged["social_publish"] = social

    agent = dict(DEFAULT_EMBEDDED_AGENT)
    agent.update(dict(merged.get("embedded_agent") or {}))
    if not optional.get("embedded_agent", False):
        agent["enabled"] = False
        agent["allow_caption_rewrite"] = False
    merged["embedded_agent"] = agent

    return merged


def build_features_applied(config: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize which rollout features were active for a run."""
    rollout = dict(config.get("rollout") or {})
    stable = dict(rollout.get("stable_features") or {})
    optional = dict(rollout.get("optional_features") or {})
    rendering = dict(config.get("rendering") or {})
    viral = dict(rendering.get("viral_enhancements") or {})
    smart = dict(rendering.get("smart_reframe") or {})
    chat = dict(config.get("chat_signals") or {})
    enhancements = dict((report or {}).get("enhancements_summary") or {})
    phase = describe_rollout_phase(rollout.get("phase"))

    flags = {
        "rollout_phase": phase["id"],
        "rollout_phase_label": phase["label"],
        "min_clip_duration": bool(stable.get("min_clip_duration", True)),
        "platform_presets": bool(stable.get("platform_presets", True)),
        "game_profiles": bool(stable.get("game_profiles", True)),
        "quality_tiers": bool(stable.get("quality_tiers", True)),
        "viral_polish": bool(enhancements.get("viral_enhanced", 0)) or bool(viral.get("always_apply_polish", True)),
        "smart_reframe": bool(enhancements.get("smart_reframe_applied", 0)) or bool(smart.get("enabled", False)),
        "chat_signals": bool(chat.get("enabled", False)),
        "sound_effects": bool(viral.get("sound_effects_enabled", False)),
        "styled_ass_captions": bool(enhancements.get("viral_ass_captions_applied", 0))
        or bool(viral.get("styled_ass_captions_enabled", False)),
        "whisper_transcription": bool((config.get("transcription") or {}).get("enabled", False)),
        "batch_queue": bool(optional.get("batch_queue", True)),
        "industry_timing": bool((config.get("highlight_detection") or {}).get("industry_timing_enabled", False)),
        "direct_publish": bool((config.get("social_publish") or {}).get("enabled", False))
        and bool(optional.get("direct_publish", False)),
        "embedded_agent": bool((config.get("embedded_agent") or {}).get("enabled", False))
        and bool(optional.get("embedded_agent", False)),
        "screen_shake": bool(viral.get("screen_shake", False)),
        "vision_hybrid": str((config.get("vision") or {}).get("provider", "heuristic")).lower() in {"auto", "openai", "anthropic"},
    }
    return flags
