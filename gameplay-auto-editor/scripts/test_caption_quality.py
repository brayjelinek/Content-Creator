"""Tests for signal-driven captions and clip timing quality updates."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.caption_generator import generate_captions  # noqa: E402
from scripts.clip_timing import compute_clip_range  # noqa: E402
from scripts.viral_clip_enhancer import _apply_tiered_viral_settings, merge_viral_config  # noqa: E402


def test_signal_driven_hook_from_killfeed() -> None:
    highlights = [
        {
            "timestamp": 42.0,
            "score": 72,
            "categories": ["kills"],
            "summary": "Lower-intensity gameplay microclip.",
            "raw_analysis": {"gameplay_signals": {"killfeed_ocr_keyword": "headshot"}},
        }
    ]
    result = generate_captions(highlights, "test_video", game_profile="valorant")
    assert result[0]["hook_text"] == "Headshot confirmed"


def test_hook_dedupe_within_run() -> None:
    highlights = [
        {
            "timestamp": 10.0,
            "score": 50,
            "categories": ["setup moment"],
            "summary": "Lower-intensity gameplay microclip.",
        },
        {
            "timestamp": 11.0,
            "score": 50,
            "categories": ["setup moment"],
            "summary": "Lower-intensity gameplay microclip.",
        },
    ]
    result = generate_captions(highlights, "test_video")
    assert result[0]["hook_text"] != result[1]["hook_text"]


def test_signal_caption_body_not_generic_summary() -> None:
    highlights = [
        {
            "timestamp": 5.0,
            "score": 55,
            "categories": ["clutch plays"],
            "summary": "High-action microclip with strong gameplay signals.",
            "raw_analysis": {
                "gameplay_signals": {
                    "low_health_detected": True,
                    "hitmarker_detected": True,
                }
            },
            "score_breakdown": {"low_health_detected": True, "hitmarker_detected": True},
        }
    ]
    result = generate_captions(highlights, "test_video")
    body = result[0]["caption_text"].lower()
    assert "hitmarker" in body or "clutch" in body or "health" in body
    assert "viral score" not in result[0]["social_caption"].lower()


def test_shorts_length_bias_trims_long_clips() -> None:
    config = {
        "shorts_length_bias_enabled": True,
        "shorts_target_seconds": 28,
        "shorts_min_seconds": 15,
        "shorts_max_seconds": 35,
        "clip_seconds_before": 2.0,
        "clip_seconds_after": 4.0,
        "min_clip_seconds": 5,
        "max_clip_seconds": 60,
        "adaptive_padding_enabled": False,
    }
    start, end = compute_clip_range(120.0, 600.0, config)
    assert end - start <= 35


def test_tiered_effects_reduce_polish_on_low_score() -> None:
    viral = merge_viral_config({"viral_enhancements": {"tiered_effects": True}})
    highlight = {"score": 35, "quality_tier": "fallback", "categories": ["kills"]}
    tuned = _apply_tiered_viral_settings(highlight, viral)
    assert tuned["slowmo_enabled"] is False
    assert tuned["zoom_enabled"] is False


def main() -> int:
    tests = [
        test_signal_driven_hook_from_killfeed,
        test_hook_dedupe_within_run,
        test_signal_caption_body_not_generic_summary,
        test_shorts_length_bias_trims_long_clips,
        test_tiered_effects_reduce_polish_on_low_score,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"All {len(tests)} quality tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
