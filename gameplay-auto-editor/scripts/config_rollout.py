"""Stable feature rollout defaults merged into user config."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_ROLLOUT: dict[str, Any] = {
    "stable_features": {
        "min_clip_duration": True,
        "adaptive_padding": True,
        "platform_presets": True,
        "viral_polish_always_on": True,
        "burn_captions_on_overlay_fail": True,
        "game_profiles": True,
        "quality_tiers": True,
        "enhancement_badges": True,
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


def apply_rollout_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """Merge rollout defaults without overriding explicit user settings."""
    merged = deepcopy(config)

    rollout = dict(DEFAULT_ROLLOUT)
    rollout.update(dict(merged.get("rollout") or {}))
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
    merged["highlight_detection"] = highlight

    rendering = dict(merged.get("rendering") or {})
    viral = dict(rendering.get("viral_enhancements") or {})
    smart = dict(rendering.get("smart_reframe") or {})

    if rollout["stable_features"].get("viral_polish_always_on", True):
        viral.setdefault("always_apply_polish", True)
    if rollout["stable_features"].get("burn_captions_on_overlay_fail", True):
        viral.setdefault("burn_captions_when_overlay_missing", True)
    if not rollout["optional_features"].get("smart_reframe", False):
        smart["enabled"] = bool(smart.get("enabled", False))
    if not rollout["optional_features"].get("sound_effects", False):
        viral["sound_effects_enabled"] = bool(viral.get("sound_effects_enabled", False))
    if not rollout["optional_features"].get("styled_ass_captions", False):
        viral["styled_ass_captions_enabled"] = bool(viral.get("styled_ass_captions_enabled", False))
        viral["ass_karaoke_enabled"] = bool(viral.get("ass_karaoke_enabled", False))

    rendering["viral_enhancements"] = viral
    rendering["smart_reframe"] = smart
    merged["rendering"] = rendering

    if not rollout["optional_features"].get("chat_signals", False):
        merged["chat_signals"]["enabled"] = bool(merged["chat_signals"].get("enabled", False))
    if not rollout["optional_features"].get("whisper_transcription", False):
        merged["transcription"]["enabled"] = bool(merged["transcription"].get("enabled", False))

    social = dict(DEFAULT_SOCIAL_PUBLISH)
    social.update(dict(merged.get("social_publish") or {}))
    if not rollout["optional_features"].get("direct_publish", False):
        social["enabled"] = bool(social.get("enabled", False))
    merged["social_publish"] = social

    agent = dict(DEFAULT_EMBEDDED_AGENT)
    agent.update(dict(merged.get("embedded_agent") or {}))
    if not rollout["optional_features"].get("embedded_agent", False):
        agent["enabled"] = bool(agent.get("enabled", False))
        agent["allow_caption_rewrite"] = bool(agent.get("allow_caption_rewrite", False))
    merged["embedded_agent"] = agent

    return merged


def build_features_applied(config: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, bool]:
    """Summarize which rollout features were active for a run."""
    rollout = dict(config.get("rollout") or {})
    stable = dict(rollout.get("stable_features") or {})
    optional = dict(rollout.get("optional_features") or {})
    rendering = dict(config.get("rendering") or {})
    viral = dict(rendering.get("viral_enhancements") or {})
    smart = dict(rendering.get("smart_reframe") or {})
    chat = dict(config.get("chat_signals") or {})
    enhancements = dict((report or {}).get("enhancements_summary") or {})

    return {
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
        "direct_publish": bool((config.get("social_publish") or {}).get("enabled", False))
        and bool(optional.get("direct_publish", False)),
        "embedded_agent": bool((config.get("embedded_agent") or {}).get("enabled", False))
        and bool(optional.get("embedded_agent", False)),
    }
