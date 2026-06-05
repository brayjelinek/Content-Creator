"""Analyze sampled gameplay frames with a vision model or local fallback."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List


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
    """Small wrapper around optional vision APIs with a deterministic fallback."""

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

    def analyze_frames(self, frame_samples: Iterable[dict]) -> List[dict]:
        analyses = []
        for sample in frame_samples:
            analyses.append(self.analyze_frame(sample))
        return analyses

    def analyze_frame(self, sample: dict) -> dict:
        if self.provider == "openai" and self.openai_api_key:
            try:
                return self._analyze_with_openai(sample)
            except Exception as exc:  # noqa: BLE001 - keep pipeline usable if API fails.
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = f"openai failed: {exc}"
                return fallback

        if self.provider == "anthropic" and self.anthropic_api_key:
            try:
                return self._analyze_with_anthropic(sample)
            except Exception as exc:  # noqa: BLE001
                fallback = self._heuristic_analysis(sample)
                fallback["provider_error"] = f"anthropic failed: {exc}"
                return fallback

        return self._heuristic_analysis(sample)

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
        motion = float(sample.get("motion_score", 0))
        brightness = float(sample.get("brightness", 0))
        sharpness = float(sample.get("sharpness", 0))

        action_intensity = min(100, motion * 4)
        clarity = max(0, min(100, (sharpness / 8) + (100 - abs(brightness - 115)) * 0.25))
        pacing = min(100, motion * 3.2)
        uniqueness = 35 + min(45, motion * 1.8)
        emotional_impact = 25 + min(50, motion * 1.5)
        meme_potential = 25 + min(55, motion * 1.7)
        viral_score = (
            action_intensity * 0.30
            + uniqueness * 0.15
            + emotional_impact * 0.18
            + meme_potential * 0.14
            + pacing * 0.13
            + clarity * 0.10
        )

        categories = []
        if motion >= 18:
            categories.extend(["high-action sequences", "fast movement or chaos"])
        if motion >= 28:
            categories.append("clutch plays")
        if brightness > 170 and motion >= 15:
            categories.append("explosions")
        if motion < 5 and sharpness < 80:
            categories.append("fails")
        if not categories:
            categories.append("setup moment")

        summary = (
            "High-motion gameplay moment detected."
            if motion >= 18
            else "Lower-action gameplay moment; useful as context if no stronger highlight appears."
        )

        return _normalize_analysis(
            sample,
            {
                "summary": summary,
                "categories": categories,
                "scores": {
                    "action_intensity": action_intensity,
                    "uniqueness": uniqueness,
                    "emotional_impact": emotional_impact,
                    "meme_potential": meme_potential,
                    "pacing": pacing,
                    "clarity": clarity,
                },
                "viral_score": viral_score,
                "reason": "Local motion, brightness, and sharpness heuristics.",
            },
            "heuristic",
        )


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
    normalized_scores = {
        "action_intensity": _score(scores.get("action_intensity")),
        "uniqueness": _score(scores.get("uniqueness")),
        "emotional_impact": _score(scores.get("emotional_impact")),
        "meme_potential": _score(scores.get("meme_potential")),
        "pacing": _score(scores.get("pacing")),
        "clarity": _score(scores.get("clarity")),
    }
    viral_score = parsed.get("viral_score")
    if viral_score is None:
        viral_score = sum(normalized_scores.values()) / len(normalized_scores)

    categories = parsed.get("categories") or []
    if isinstance(categories, str):
        categories = [categories]

    return {
        "timestamp": float(sample.get("timestamp", 0)),
        "frame_path": sample.get("frame_path"),
        "frame_index": sample.get("frame_index"),
        "provider": provider,
        "summary": str(parsed.get("summary") or "Gameplay moment analyzed."),
        "categories": [str(category) for category in categories],
        "scores": normalized_scores,
        "viral_score": _score(viral_score),
        "reason": str(parsed.get("reason") or ""),
        "signals": {
            "motion_score": sample.get("motion_score", 0),
            "brightness": sample.get("brightness", 0),
            "sharpness": sample.get("sharpness", 0),
        },
    }


def _score(value: object) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 2)
    except (TypeError, ValueError):
        return 0.0
