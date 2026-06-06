"""Optional LLM caption polish hook for the pipeline (fail-open)."""

from __future__ import annotations

import logging
from typing import Any

from scripts.embedded_agent.llm_client import chat_completion
from scripts.embedded_agent.settings import load_agent_settings

logger = logging.getLogger(__name__)


def maybe_rewrite_captions(
    highlights: list[dict],
    *,
    config: dict[str, Any],
    video_name: str = "",
) -> list[dict]:
    """
    Optionally rewrite hooks/captions with an LLM before rendering.

    Fail-open: returns original highlights on any error or when disabled.
    """
    settings = load_agent_settings(config)
    rollout = dict(config.get("rollout") or {}).get("optional_features") or {}
    if not settings.enabled or not rollout.get("embedded_agent"):
        return highlights
    if not settings.allow_caption_rewrite:
        return highlights
    if not settings.openai_api_key and not settings.anthropic_api_key:
        return highlights

    updated: list[dict] = []
    for index, highlight in enumerate(highlights, start=1):
        try:
            polished = _rewrite_single(highlight, settings=settings, index=index, video_name=video_name)
            updated.append(polished)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CaptionRewrite] Skipped clip %s: %s", index, exc)
            updated.append(highlight)
    return updated


def _rewrite_single(
    highlight: dict,
    *,
    settings,
    index: int,
    video_name: str,
) -> dict:
    categories = ", ".join(highlight.get("categories") or []) or "gameplay"
    score = highlight.get("score", 0)
    prompt = (
        f"Rewrite this short-form clip overlay for vertical video.\n"
        f"Video: {video_name}\nClip: {index}\nScore: {score}\nCategories: {categories}\n"
        f"Current hook: {highlight.get('hook_text', '')}\n"
        f"Current caption: {highlight.get('caption_text', '')}\n\n"
        "Return JSON with keys hook_text (max 22 chars), caption_text (max 120 chars), "
        "social_caption (max 200 chars). Keep tone punchy for TikTok/Shorts. No hashtags in hook."
    )
    response = chat_completion(
        provider=settings.provider,
        model=settings.model,
        messages=[
            {"role": "system", "content": "You rewrite short-form gaming clip captions. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        openai_api_key=settings.openai_api_key,
        anthropic_api_key=settings.anthropic_api_key,
    )
    content = str(response.get("content") or "")
    parsed = _parse_json_fields(content)
    if not parsed:
        return highlight

    result = dict(highlight)
    if parsed.get("hook_text"):
        result["hook_text"] = str(parsed["hook_text"])[:22]
    if parsed.get("caption_text"):
        result["caption_text"] = str(parsed["caption_text"])[:120]
        result["caption_lines"] = [result["caption_text"]]
    if parsed.get("social_caption"):
        result["social_caption"] = str(parsed["social_caption"])[:200]
    result["caption_rewritten_by_agent"] = True
    logger.info("[CaptionRewrite] Polished captions for clip %s", index)
    return result


def _parse_json_fields(content: str) -> dict[str, str]:
    import json
    import re

    content = content.strip()
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items() if k in {"hook_text", "caption_text", "social_caption"}}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[^{}]+\}", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return {k: str(v) for k, v in data.items() if k in {"hook_text", "caption_text", "social_caption"}}
        except json.JSONDecodeError:
            return {}
    return {}
