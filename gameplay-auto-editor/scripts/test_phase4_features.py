"""Unit checks for Phase 4 performance and control features."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.clip_metadata import format_virality_subscores  # noqa: E402
from scripts.config_rollout import apply_rollout_defaults  # noqa: E402
from scripts.pipeline_control import PipelineCancelled, reset_pipeline_control  # noqa: E402
from scripts.prompt_clip_filter import filter_highlights_by_prompt  # noqa: E402
from scripts.streak_scoring import apply_streak_bonuses  # noqa: E402


def _base_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def test_pipeline_cancel_raises() -> None:
    control = reset_pipeline_control()
    control.check("loading")
    control.cancel()
    try:
        control.check("rendering")
        raise AssertionError("Expected PipelineCancelled")
    except PipelineCancelled as exc:
        assert "rendering" in str(exc)


def test_streak_bonus_for_nearby_kills() -> None:
    analyses = [
        {
            "timestamp": 10.0,
            "final_score": 70.0,
            "score_breakdown": {"final_score": 70.0},
            "gameplay_signals": {"killfeed_ocr_match": True},
        },
        {
            "timestamp": 12.0,
            "final_score": 68.0,
            "score_breakdown": {"final_score": 68.0},
            "gameplay_signals": {"killfeed_ocr_match": True, "killfeed_ocr_keyword": "double kill"},
        },
    ]
    boosted = apply_streak_bonuses(analyses, {"enabled": True})
    assert (boosted[1]["score_breakdown"].get("streak_bonus") or 0) > 0


def test_prompt_filter_fail_open() -> None:
    highlights = [
        {"id": "highlight_01", "score": 90, "summary": "clutch ace"},
        {"id": "highlight_02", "score": 80, "summary": "funny fail"},
    ]
    filtered = filter_highlights_by_prompt(highlights, "nonexistent-keyword")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "highlight_01"


def test_prompt_filter_matches_keyword() -> None:
    highlights = [
        {"id": "highlight_01", "score": 90, "summary": "clutch ace"},
        {"id": "highlight_02", "score": 80, "summary": "funny fail"},
    ]
    filtered = filter_highlights_by_prompt(highlights, "fail")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "highlight_02"


def test_phase_four_enables_performance_flags() -> None:
    config = _base_config()
    config["rollout"] = {"phase": "phase_4"}
    merged = apply_rollout_defaults(config)
    optional = merged["rollout"]["optional_features"]
    assert optional["parallel_sampling"] is True
    assert optional["parallel_render"] is True
    assert optional["single_pass_render"] is True
    assert optional["streak_scoring"] is True
    assert merged["rendering"]["single_pass_render"] is True
    assert int(merged["performance"]["parallel_render_workers"]) >= 2
    assert merged["highlight_detection"]["streak_scoring"]["enabled"] is True


def test_format_virality_subscores() -> None:
    text = format_virality_subscores(
        {
            "score_breakdown": {
                "ai_score": 72,
                "motion_component": 8,
                "audio_component": 6,
                "bonus_points": 20,
                "streak_bonus": 24,
                "hitmarker_detected": True,
            }
        }
    )
    assert "AI 72" in text
    assert "Streak 24" in text
    assert "hitmarker" in text


def test_ass_captions_skipped_when_overlay_applied() -> None:
    from scripts.viral_clip_enhancer import _should_apply_ass_captions

    viral = {"styled_ass_captions_enabled": True}
    assert _should_apply_ass_captions({"overlay_applied": True}, viral) is False
    assert _should_apply_ass_captions({"overlay_applied": False}, viral) is True
    assert _should_apply_ass_captions({"overlay_applied": True}, {"styled_ass_captions_enabled": False}) is False


def main() -> int:
    tests = [
        test_pipeline_cancel_raises,
        test_streak_bonus_for_nearby_kills,
        test_prompt_filter_fail_open,
        test_prompt_filter_matches_keyword,
        test_phase_four_enables_performance_flags,
        test_format_virality_subscores,
        test_ass_captions_skipped_when_overlay_applied,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"All {len(tests)} Phase 4 tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
