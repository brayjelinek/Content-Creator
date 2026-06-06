"""Analyze sampled gameplay microclips or frames with a vision model or local fallback."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, List

logger = logging.getLogger(__name__)


HIGHLIGHT_CATEGORIES = [
    "kills",
    "deaths",
    "clutch plays",
    "explosions",
    "funny moments",
    "fails",
    "high-action sequences",
    "fast movement or chaos",
    "emotional reactions",
]


class VisionAnalyzer:
    """Wrapper around optional vision APIs with deterministic microclip/heuristic fallback."""

    def __init__(self, config: dict):
        self.config = config
        self.provider = (config.get("provider") or "heuristic").lower()
        self.openai_api_key = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
        self.anthropic_api_key = config.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")

        if self.provider == "auto":
            if self.openai_api_key:
                self.provider = "openai"
            elif self.anthropic_api_key:
                self.provider = "anthropic"
            else:
                self.provider = "heuristic"

        if self.provider == "openai" and not self.openai_api_key:
            logger.warning("[VisionAnalyzer] provider=openai but no API key — using heuristic fallback.")
            self.provider = "heuristic"
        if self.provider == "anthropic" and not self.anthropic_api_key:
            logger.warning("[VisionAnalyzer] provider=anthropic but no API key — using heuristic fallback.")
            self.provider = "heuristic"

    def analyze_frames(self, samples: Iterable[dict]) -> List[dict]:
        """Analyze frame or microclip samples (backward-compatible entry point)."""
        return self.analyze_samples(samples)

    def analyze_samples(self, samples: Iterable[dict]) -> List[dict]:
        sample_list = list(samples)
        total = len(sample_list)
        analyses = []

        for index, sample in enumerate(sample_list, start=1):
            sample_type = "microclip" if sample.get("clip_path") else "frame"
            message = (
                f"Analyzing {sample_type} {index}/{total} at {sample.get('timestamp', 0)}s "
                f"with {self.provider}..."
            )
            print(f"    {message}")
            logger.info("[VisionAnalyzer] %s", message)
            try:
                analyses.append(self.analyze_sample(sample))
            except Exception as exc:  # noqa: BLE001 - never break pipeline
                logger.warning("[VisionAnalyzer] Sample analysis failed at %.2fs: %s", sample.get("timestamp", 0), exc)
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = str(exc)
                analyses.append(fallback)

        provider_errors = [item.get("provider_error") for item in analyses if item.get("provider_error")]
        if provider_errors:
            logger.warning(
                "[VisionAnalyzer] %s sample(s) fell back to heuristic due to errors.",
                len(provider_errors),
            )
        return analyses

    def analyze_sample(self, sample: dict) -> dict:
        if sample.get("clip_path"):
            return self.analyze_microclip(sample)
        return self.analyze_frame(sample)

    def analyze_microclip(self, sample: dict) -> dict:
        if self.provider == "openai" and self.openai_api_key:
            try:
                return self._analyze_microclip_with_openai(sample)
            except Exception as exc:  # noqa: BLE001
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = f"openai failed: {exc}"
                logger.warning("[VisionAnalyzer] OpenAI microclip failed at %.2fs: %s", sample.get("timestamp", 0), exc)
                return fallback

        if self.provider == "anthropic" and self.anthropic_api_key:
            try:
                return self._analyze_microclip_with_anthropic(sample)
            except Exception as exc:  # noqa: BLE001
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = f"anthropic failed: {exc}"
                logger.warning(
                    "[VisionAnalyzer] Anthropic microclip failed at %.2fs: %s",
                    sample.get("timestamp", 0),
                    exc,
                )
                return fallback

        return self._heuristic_analysis(sample)

    def analyze_frame(self, sample: dict) -> dict:
        if self.provider == "openai" and self.openai_api_key:
            try:
                return self._analyze_with_openai(sample)
            except Exception as exc:  # noqa: BLE001
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = f"openai failed: {exc}"
                logger.warning("[VisionAnalyzer] OpenAI failed at %.2fs: %s", sample.get("timestamp", 0), exc)
                return fallback

        if self.provider == "anthropic" and self.anthropic_api_key:
            try:
                return self._analyze_with_anthropic(sample)
            except Exception as exc:  # noqa: BLE001
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = f"anthropic failed: {exc}"
                logger.warning("[VisionAnalyzer] Anthropic failed at %.2fs: %s", sample.get("timestamp", 0), exc)
                return fallback

        return self._heuristic_analysis(sample)

    def _analyze_microclip_with_openai(self, sample: dict) -> dict:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.openai_api_key,
            timeout=float(self.config.get("request_timeout_seconds", 60)),
        )
        content = [{"type": "input_text", "text": _microclip_prompt(sample)}]
        for image_path in _microclip_image_paths(sample):
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{_encode_image(image_path)}",
                }
            )

        response = client.responses.create(
            model=self.config.get("openai_model", "gpt-4o-mini"),
            input=[{"role": "user", "content": content}],
            max_output_tokens=700,
        )
        parsed = _parse_json(response.output_text)
        return _normalize_analysis(sample, parsed, "openai")

    def _analyze_microclip_with_anthropic(self, sample: dict) -> dict:
        from anthropic import Anthropic

        client = Anthropic(
            api_key=self.anthropic_api_key,
            timeout=float(self.config.get("request_timeout_seconds", 60)),
        )
        content: list[dict] = [{"type": "text", "text": _microclip_prompt(sample)}]
        for image_path in _microclip_image_paths(sample):
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": _encode_image(image_path),
                    },
                }
            )

        message = client.messages.create(
            model=self.config.get("anthropic_model", "claude-3-5-haiku-latest"),
            max_tokens=700,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        parsed = _parse_json(text)
        return _normalize_analysis(sample, parsed, "anthropic")

    def _analyze_with_openai(self, sample: dict) -> dict:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.openai_api_key,
            timeout=float(self.config.get("request_timeout_seconds", 60)),
        )
        image_data = _encode_image(sample["frame_path"])
        prompt = _analysis_prompt(sample)

        response = client.responses.create(
            model=self.config.get("openai_model", "gpt-4o-mini"),
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{image_data}",
                        },
                    ],
                }
            ],
            max_output_tokens=600,
        )
        parsed = _parse_json(response.output_text)
        return _normalize_analysis(sample, parsed, "openai")

    def _analyze_with_anthropic(self, sample: dict) -> dict:
        from anthropic import Anthropic

        client = Anthropic(
            api_key=self.anthropic_api_key,
            timeout=float(self.config.get("request_timeout_seconds", 60)),
        )
        image_data = _encode_image(sample["frame_path"])
        prompt = _analysis_prompt(sample)

        message = client.messages.create(
            model=self.config.get("anthropic_model", "claude-3-5-haiku-latest"),
            max_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                    ],
                }
            ],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        parsed = _parse_json(text)
        return _normalize_analysis(sample, parsed, "anthropic")

    def _heuristic_analysis(self, sample: dict) -> dict:
        signals = sample.get("gameplay_signals") or {}
        motion = float(signals.get("motion_intensity", sample.get("motion_score", 0)))
        audio = float(signals.get("audio_spike_score", 0))
        brightness = float(sample.get("brightness", 0))
        sharpness = float(sample.get("sharpness", 0))

        kill_likelihood = min(100.0, motion * 1.8 + (20 if signals.get("hitmarker_detected") else 0))
        clutch_potential = min(100.0, motion * 1.4 + (15 if signals.get("low_health_detected") else 0))
        chaos_hype = min(100.0, motion * 2.0 + audio * 2.5)
        humor_surprise = min(100.0, 20 + abs(motion - 12) * 1.2)
        viral_score = (
            kill_likelihood * 0.28
            + clutch_potential * 0.22
            + chaos_hype * 0.25
            + humor_surprise * 0.10
            + min(100.0, sharpness / 8) * 0.15
        )
        if signals.get("killfeed_ocr_match"):
            viral_score = min(100.0, viral_score + 18)

        categories = []
        if kill_likelihood >= 55 or signals.get("hitmarker_detected"):
            categories.append("kills")
        if clutch_potential >= 55 or signals.get("low_health_detected"):
            categories.append("clutch plays")
        if chaos_hype >= 55:
            categories.extend(["high-action sequences", "fast movement or chaos"])
        if brightness > 170 and motion >= 15:
            categories.append("explosions")
        if humor_surprise >= 60:
            categories.append("funny moments")
        if not categories:
            categories.append("setup moment")

        summary = (
            "High-action microclip with strong gameplay signals."
            if viral_score >= 50
            else "Lower-intensity gameplay microclip."
        )

        return _normalize_analysis(
            sample,
            {
                "summary": summary,
                "categories": categories,
                "scores": {
                    "kill_likelihood": kill_likelihood,
                    "clutch_potential": clutch_potential,
                    "chaos_hype": chaos_hype,
                    "humor_surprise": humor_surprise,
                    "action_intensity": motion,
                    "clarity": min(100.0, sharpness / 8),
                },
                "viral_score": viral_score,
                "reason": "Heuristic microclip scoring from motion, audio, and optional gameplay signals.",
            },
            "heuristic",
        )


def _microclip_image_paths(sample: dict) -> list[str]:
    paths = []
    for key in ("poster_frame_path", "killfeed_crop_path", "health_crop_path", "frame_path"):
        value = sample.get(key)
        if value and Path(value).exists():
            paths.append(str(value))
    return paths[:3]


def _microclip_prompt(sample: dict) -> str:
    signals = sample.get("gameplay_signals") or {}
    return f"""
You are an AI gameplay highlight scout reviewing a short gameplay microclip.

Timestamp center: {sample.get("timestamp")} seconds
Clip duration: {sample.get("duration", 1.5)} seconds
Motion intensity: {signals.get("motion_intensity", sample.get("motion_score", 0))}
Audio spike score (0-20): {signals.get("audio_spike_score", 0)}
Hitmarker flash detected: {signals.get("hitmarker_detected", False)}
Killfeed OCR match: {signals.get("killfeed_ocr_match", False)}
Low health detected: {signals.get("low_health_detected", False)}
Audio summary: {sample.get("audio_summary", "unavailable")}

Images provided:
1) Main gameplay frame from the microclip
2) Optional killfeed crop (top-right HUD)
3) Optional health/ammo crop (bottom-left HUD)

Score this moment for short-form virality. Look for kills, clutches, chaos, humor, and surprise.

Return JSON only:
{{
  "summary": "one sentence",
  "categories": ["one or more of: {", ".join(HIGHLIGHT_CATEGORIES)}"],
  "scores": {{
    "kill_likelihood": 0-100,
    "clutch_potential": 0-100,
    "chaos_hype": 0-100,
    "humor_surprise": 0-100,
    "viral_potential": 0-100
  }},
  "viral_score": 0-100,
  "reason": "short explanation"
}}
""".strip()


def _analysis_prompt(sample: dict) -> str:
    return f"""
You are an AI gameplay clip scout. Analyze this gameplay frame for short-form viral clip potential.

Timestamp: {sample.get("timestamp")} seconds
Motion score from OpenCV: {sample.get("motion_score")}
Brightness: {sample.get("brightness")}
Sharpness: {sample.get("sharpness")}

Look for: {", ".join(HIGHLIGHT_CATEGORIES)}.

Return JSON only with this shape:
{{
  "summary": "one sentence",
  "categories": ["one or more categories"],
  "scores": {{
    "action_intensity": 0-100,
    "uniqueness": 0-100,
    "emotional_impact": 0-100,
    "meme_potential": 0-100,
    "pacing": 0-100,
    "clarity": 0-100
  }},
  "viral_score": 0-100,
  "reason": "short explanation"
}}
""".strip()


def _encode_image(image_path: str | Path) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


def _parse_json(text: str) -> Dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _normalize_analysis(sample: dict, parsed: dict, provider: str) -> dict:
    scores = parsed.get("scores") or {}
    normalized_scores = {key: _score(value) for key, value in scores.items()}
    viral_score = parsed.get("viral_score")
    if viral_score is None:
        viral_score = parsed.get("scores", {}).get("viral_potential")
    if viral_score is None and normalized_scores:
        viral_score = sum(normalized_scores.values()) / len(normalized_scores)

    categories = parsed.get("categories") or []
    if isinstance(categories, str):
        categories = [categories]

    gameplay_signals = sample.get("gameplay_signals") or {}

    return {
        "timestamp": float(sample.get("timestamp", 0)),
        "clip_path": sample.get("clip_path"),
        "poster_frame_path": sample.get("poster_frame_path") or sample.get("frame_path"),
        "frame_path": sample.get("poster_frame_path") or sample.get("frame_path"),
        "frame_index": sample.get("frame_index"),
        "duration": sample.get("duration"),
        "audio_summary": sample.get("audio_summary"),
        "provider": provider,
        "summary": str(parsed.get("summary") or "Gameplay moment analyzed."),
        "categories": [str(category) for category in categories],
        "scores": normalized_scores,
        "viral_score": _score(viral_score),
        "reason": str(parsed.get("reason") or ""),
        "gameplay_signals": gameplay_signals,
        "signals": {
            "motion_score": sample.get("motion_score", gameplay_signals.get("motion_intensity", 0)),
            "brightness": sample.get("brightness", 0),
            "sharpness": sample.get("sharpness", 0),
            "audio_spike_score": gameplay_signals.get("audio_spike_score", 0),
        },
    }


def _score(value: object) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 2)
    except (TypeError, ValueError):
        return 0.0
