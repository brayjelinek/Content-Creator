"""Unit checks for phased rollout presets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.config_rollout import (  # noqa: E402
    apply_rollout_defaults,
    describe_rollout_phase,
    resolve_rollout_phase,
)


def _base_config() -> dict:
    path = ROOT / "config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_stable_phase_disables_optional_features() -> None:
    config = _base_config()
    config["rollout"] = {"phase": "stable"}
    merged = apply_rollout_defaults(config)
    optional = merged["rollout"]["optional_features"]
    assert optional["smart_reframe"] is False
    assert merged["rendering"]["smart_reframe"]["enabled"] is False
    assert merged["rendering"]["viral_enhancements"]["sound_effects_enabled"] is False


def test_phase_one_enables_visual_polish() -> None:
    config = _base_config()
    config["rollout"] = {"phase": "phase_1"}
    merged = apply_rollout_defaults(config)
    optional = merged["rollout"]["optional_features"]
    viral = merged["rendering"]["viral_enhancements"]
    assert optional["smart_reframe"] is True
    assert optional["styled_ass_captions"] is True
    assert optional["sound_effects"] is True
    assert merged["rendering"]["smart_reframe"]["enabled"] is True
    assert viral["styled_ass_captions_enabled"] is True
    assert viral["sound_effects_enabled"] is True


def test_phase_two_enables_whisper_and_auto_vision() -> None:
    config = _base_config()
    config["rollout"] = {"phase": "phase_2"}
    merged = apply_rollout_defaults(config)
    assert merged["rollout"]["optional_features"]["whisper_transcription"] is True
    assert merged["transcription"]["enabled"] is True
    assert merged["transcription"]["use_for_hooks"] is True
    assert merged["vision"]["provider"] == "auto"


def test_phase_three_requires_chat_path_for_chat_signals() -> None:
    config = _base_config()
    config["rollout"] = {"phase": "phase_3"}
    config["chat_signals"] = {"chat_log_path": ""}
    merged = apply_rollout_defaults(config)
    assert merged["rollout"]["optional_features"]["chat_signals"] is True
    assert merged["chat_signals"]["enabled"] is False
    assert merged["embedded_agent"]["enabled"] is True
    assert merged["rendering"]["viral_enhancements"]["screen_shake"] is True

    config["chat_signals"] = {"chat_log_path": str(ROOT / "logs" / "chat.json")}
    merged = apply_rollout_defaults(config)
    assert merged["chat_signals"]["enabled"] is True


def test_custom_phase_respects_manual_optional_flags() -> None:
    config = _base_config()
    config["rollout"] = {
        "phase": "custom",
        "optional_features": {
            "sound_effects": True,
            "smart_reframe": False,
        },
    }
    merged = apply_rollout_defaults(config)
    assert merged["rollout"]["optional_features"]["sound_effects"] is True
    assert merged["rendering"]["smart_reframe"]["enabled"] is False
    assert merged["rendering"]["viral_enhancements"]["sound_effects_enabled"] is True


def test_default_config_loads_phase_three() -> None:
    merged = apply_rollout_defaults(_base_config())
    assert merged["rollout"]["phase"] == "phase_3"
    assert merged["transcription"]["enabled"] is True
    assert merged["vision"]["provider"] == "auto"
    assert merged["embedded_agent"]["enabled"] is True
    assert merged["rendering"]["viral_enhancements"]["screen_shake"] is True


def test_describe_rollout_phase() -> None:
    assert resolve_rollout_phase("unknown") == "stable"
    meta = describe_rollout_phase("phase_1")
    assert meta["id"] == "phase_1"
    assert "Visual polish" in meta["label"]


def main() -> int:
    tests = [
        test_stable_phase_disables_optional_features,
        test_phase_one_enables_visual_polish,
        test_phase_two_enables_whisper_and_auto_vision,
        test_phase_three_requires_chat_path_for_chat_signals,
        test_custom_phase_respects_manual_optional_flags,
        test_default_config_loads_phase_three,
        test_describe_rollout_phase,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"All {len(tests)} rollout tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
