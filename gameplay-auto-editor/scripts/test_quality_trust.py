"""Trust, scoring, and adaptive sampling regression checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.adaptive_sampling import build_adaptive_sample_starts  # noqa: E402
from scripts.config_rollout import apply_rollout_defaults  # noqa: E402
from scripts.highlight_scoring import resolve_min_final_score, sync_weighted_threshold  # noqa: E402
from scripts.moment_validator import is_synthetic_fallback_highlight  # noqa: E402
from scripts.prompt_clip_filter import filter_highlights_by_prompt, highlight_matches_prompt  # noqa: E402


def test_min_score_wiring_from_highlight_config() -> None:
    config = {"min_score": 42, "weighted_scoring": {}}
    assert resolve_min_final_score(config, {}) == 42.0
    synced = sync_weighted_threshold(config)
    assert synced["weighted_scoring"]["min_final_score"] == 42.0


def test_rollout_syncs_min_score() -> None:
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["highlight_detection"]["min_score"] = 55
    merged = apply_rollout_defaults(config)
    assert merged["highlight_detection"]["min_score"] == 55
    assert merged["highlight_detection"]["weighted_scoring"]["min_final_score"] == 55


def test_prompt_filter_matches_transcript_snippet() -> None:
    highlight = {
        "summary": "generic gameplay",
        "transcript_snippet": "clutch ace with one hp left",
    }
    assert highlight_matches_prompt(highlight, "clutch")


def test_prompt_filter_runs_after_transcription_fields() -> None:
    highlights = [
        {"id": "highlight_01", "score": 90, "summary": "fight", "transcript_snippet": "insane ace"},
        {"id": "highlight_02", "score": 80, "summary": "fight", "transcript_snippet": "missed every shot"},
    ]
    filtered = filter_highlights_by_prompt(highlights, "ace")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "highlight_01"


def test_weighted_fallback_is_synthetic() -> None:
    assert is_synthetic_fallback_highlight({"selection_mode": "weighted_fallback"})
    assert is_synthetic_fallback_highlight({"selection_mode": "fallback_best_microclip"})


def test_adaptive_sampling_adds_dense_points() -> None:
    peaks = [
        {"timestamp": 12.0, "gameplay_signals": {"motion_intensity": 40, "audio_spike_score": 20}},
        {"timestamp": 30.0, "gameplay_signals": {"motion_intensity": 10, "audio_spike_score": 4}},
    ]
    starts = build_adaptive_sample_starts(
        duration=60.0,
        base_starts=[0.0, 10.0, 20.0, 30.0],
        peak_samples=peaks,
        max_samples=20,
        adaptive_config={"peak_count": 1, "dense_interval_seconds": 0.5, "peak_window_seconds": 1.0},
    )
    assert len(starts) > 4
    assert any(abs(value - 12.0) < 1.0 for value in starts)


def test_user_optional_features_override_phase_preset() -> None:
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["rollout"] = {
        "phase": "phase_4",
        "optional_features": {"smart_reframe": False, "whisper_transcription": False},
    }
    merged = apply_rollout_defaults(config)
    assert merged["rollout"]["optional_features"]["smart_reframe"] is False
    assert merged["rendering"]["smart_reframe"]["enabled"] is False


def main() -> int:
    tests = [
        test_min_score_wiring_from_highlight_config,
        test_rollout_syncs_min_score,
        test_prompt_filter_matches_transcript_snippet,
        test_prompt_filter_runs_after_transcription_fields,
        test_weighted_fallback_is_synthetic,
        test_adaptive_sampling_adds_dense_points,
        test_user_optional_features_override_phase_preset,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"All {len(tests)} quality trust tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
