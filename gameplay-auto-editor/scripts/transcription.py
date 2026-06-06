"""Optional speech transcription for context-aware captions and karaoke ASS."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from scripts.subprocess_utils import run_quiet

logger = logging.getLogger(__name__)

DEFAULT_TRANSCRIPTION_CONFIG: dict[str, Any] = {
    "enabled": False,
    "provider": "whisper_cli",
    "model": "tiny",
    "language": "",
    "use_for_captions": True,
    "use_for_hooks": False,
    "max_segment_seconds": 30,
    "openai_model": "whisper-1",
}


def merge_transcription_config(config: dict | None) -> dict[str, Any]:
    merged = dict(DEFAULT_TRANSCRIPTION_CONFIG)
    merged.update(dict(config or {}))
    return merged


def enrich_highlights_with_transcription(
    highlights: list[dict],
    video_path: str | Path,
    config: dict | None = None,
    vision_config: dict | None = None,
) -> None:
    """Attach transcript snippets to highlights when transcription is enabled."""
    cfg = merge_transcription_config(config)
    if not cfg.get("enabled"):
        return

    video_path = Path(video_path)
    if not video_path.exists():
        return

    for highlight in highlights:
        try:
            result = transcribe_highlight_segment(video_path, highlight, cfg, vision_config)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[Transcription] Skipped %s: %s", highlight.get("id"), exc)
            continue
        if not result:
            continue

        text = str(result.get("text") or "").strip()
        if text and cfg.get("use_for_captions", True):
            highlight["transcript_snippet"] = text[:240]
            highlight["caption_lines"] = None
        if text and cfg.get("use_for_hooks", False):
            highlight["custom_hook_text"] = _hook_from_transcript(text)
        words = result.get("words") or []
        if words:
            highlight["transcript_words"] = words
        highlight["transcription_provider"] = result.get("provider")
        logger.info("[Transcription] Attached snippet to %s (%s chars)", highlight.get("id"), len(text))


def transcribe_highlight_segment(
    video_path: Path,
    highlight: dict,
    config: dict | None = None,
    vision_config: dict | None = None,
) -> dict[str, Any] | None:
    """Transcribe one highlight segment from the source video."""
    cfg = merge_transcription_config(config)
    start = max(0.0, float(highlight.get("start", 0)))
    duration = min(float(highlight.get("duration", 5)), float(cfg.get("max_segment_seconds", 30)))
    duration = max(0.5, duration)

    with tempfile.TemporaryDirectory(prefix="gae_transcribe_") as temp_dir:
        audio_path = Path(temp_dir) / "segment.wav"
        if not _extract_audio_segment(video_path, audio_path, start, duration):
            return None

        provider = str(cfg.get("provider", "whisper_cli")).lower()
        if provider == "openai":
            return _transcribe_openai(audio_path, cfg, vision_config)
        return _transcribe_whisper_cli(audio_path, cfg)


def _extract_audio_segment(video_path: Path, output_path: Path, start: float, duration: float) -> bool:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video_path),
        "-t",
        f"{duration:.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    result = run_quiet(command)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def _transcribe_whisper_cli(audio_path: Path, config: dict) -> dict[str, Any] | None:
    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        logger.info("[Transcription] whisper CLI not found — skipping")
        return None

    with tempfile.TemporaryDirectory(prefix="gae_whisper_") as temp_dir:
        command = [
            whisper_bin,
            str(audio_path),
            "--model",
            str(config.get("model", "tiny")),
            "--output_format",
            "json",
            "--output_dir",
            temp_dir,
            "--fp16",
            "False",
        ]
        language = str(config.get("language") or "").strip()
        if language:
            command.extend(["--language", language])

        result = run_quiet(command)
        if result.returncode != 0:
            logger.info("[Transcription] whisper CLI failed — skipping")
            return None

        json_files = list(Path(temp_dir).glob("*.json"))
        if not json_files:
            return None
        payload = json.loads(json_files[0].read_text(encoding="utf-8"))
        return {
            "text": str(payload.get("text") or "").strip(),
            "words": _normalize_words(payload.get("segments") or []),
            "provider": "whisper_cli",
        }


def _transcribe_openai(audio_path: Path, config: dict, vision_config: dict | None = None) -> dict[str, Any] | None:
    try:
        from scripts.api_usage_guard import can_make_api_call, disable_for_run, handle_quota_error, record_api_call
    except ImportError:
        return None

    vision_cfg = dict(vision_config or {})
    api_key = str(vision_cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.info("[Transcription] OpenAI key missing — skipping transcription")
        return None

    allowed, _reason = can_make_api_call(vision_cfg)
    if not allowed:
        logger.info("[Transcription] API budget exhausted — skipping transcription")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        with audio_path.open("rb") as handle:
            response = client.audio.transcriptions.create(
                model=str(config.get("openai_model", "whisper-1")),
                file=handle,
                response_format="verbose_json",
            )
        record_api_call(vision_cfg)
        text = str(getattr(response, "text", "") or "").strip()
        words = []
        for segment in getattr(response, "words", []) or []:
            words.append(
                {
                    "word": getattr(segment, "word", ""),
                    "start": float(getattr(segment, "start", 0)),
                    "end": float(getattr(segment, "end", 0)),
                }
            )
        return {"text": text, "words": words, "provider": "openai_whisper"}
    except Exception as exc:  # noqa: BLE001
        if "insufficient_quota" in str(exc).lower() or "rate_limit" in str(exc).lower():
            handle_quota_error(exc, vision_cfg)
            disable_for_run()
        logger.info("[Transcription] OpenAI transcription unavailable — skipping")
        return None


def _normalize_words(segments: list[dict]) -> list[dict]:
    words: list[dict] = []
    for segment in segments:
        for item in segment.get("words") or []:
            word = str(item.get("word") or "").strip()
            if not word:
                continue
            words.append(
                {
                    "word": word,
                    "start": float(item.get("start", 0)),
                    "end": float(item.get("end", 0)),
                }
            )
    return words


def _hook_from_transcript(text: str) -> str:
    snippet = " ".join(text.split())
    if len(snippet) <= 22:
        return snippet
    return snippet[:19].rstrip() + "..."
