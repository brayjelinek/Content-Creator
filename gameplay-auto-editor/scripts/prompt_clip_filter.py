"""ClipAnything-style keyword prompt filtering for highlight selection."""

from __future__ import annotations

import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)


def normalize_prompt(prompt: str | None) -> str:
    return " ".join(str(prompt or "").strip().split())


def prompt_terms(prompt: str | None) -> list[str]:
    normalized = normalize_prompt(prompt).lower()
    if not normalized:
        return []
    return [term for term in re.split(r"[\s,;|]+", normalized) if term]


def highlight_matches_prompt(highlight: dict, prompt: str | None) -> bool:
    terms = prompt_terms(prompt)
    if not terms:
        return True

    haystack = " ".join(
        [
            str(highlight.get("summary", "")),
            str(highlight.get("reason", "")),
            str(highlight.get("hook_text", "")),
            str(highlight.get("caption_text", "")),
            " ".join(str(item) for item in highlight.get("categories", [])),
            str((highlight.get("raw_analysis") or {}).get("summary", "")),
            str((highlight.get("raw_analysis") or {}).get("transcript", "")),
        ]
    ).lower()
    return any(term in haystack for term in terms)


def filter_highlights_by_prompt(highlights: Iterable[dict], prompt: str | None) -> list[dict]:
    """Keep highlights that match the prompt, fail-open to at least one clip."""
    items = list(highlights)
    if not items or not prompt_terms(prompt):
        return items

    matched = [item for item in items if highlight_matches_prompt(item, prompt)]
    if matched:
        logger.info("[PromptFilter] Matched %s/%s highlight(s) for prompt %r", len(matched), len(items), normalize_prompt(prompt))
        return matched

    best = max(items, key=lambda item: float(item.get("score", 0)))
    logger.info(
        "[PromptFilter] No prompt matches for %r — keeping best highlight %s (score %.1f)",
        normalize_prompt(prompt),
        best.get("id"),
        float(best.get("score", 0)),
    )
    return [best]
