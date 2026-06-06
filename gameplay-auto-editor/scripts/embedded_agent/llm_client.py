"""LLM client for the embedded advisor with fail-open local fallback."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from scripts.embedded_agent.context_builder import build_setup_help, sanitize_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the embedded advisor for Gameplay Auto Editor, a desktop tool that turns gameplay footage into vertical short-form clips.

Rules:
- Answer using ONLY the provided app context and tool results. If context is missing, say so.
- Never invent clip scores, file paths, or features not in the context.
- Never request, repeat, or expose API keys, OAuth tokens, or secrets.
- Prefer actionable, concise guidance for clip quality, settings, setup, and posting strategy.
- When suggesting config changes, explain why and remind the user they must approve changes.
- You cannot run FFmpeg, modify files, or post to social platforms directly — you advise only.
"""


def chat_completion(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Call remote LLM or return a local fallback response."""
    provider = provider.lower()
    if provider == "openai" and openai_api_key:
        return _openai_chat(model, messages, openai_api_key, timeout_seconds)
    if provider == "anthropic" and anthropic_api_key:
        return _anthropic_chat(model, messages, anthropic_api_key, timeout_seconds)
    if provider == "auto":
        if openai_api_key:
            return _openai_chat(model, messages, openai_api_key, timeout_seconds)
        if anthropic_api_key:
            return _anthropic_chat(model, messages, anthropic_api_key, timeout_seconds)
    return _local_fallback(messages)


def _openai_chat(model: str, messages: list[dict[str, str]], api_key: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model or "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 800,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        return {"ok": True, "content": sanitize_text(content), "provider": "openai"}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning("[AgentLLM] OpenAI error: %s", detail)
        return {"ok": False, "error": f"OpenAI request failed: {exc.code}", "fallback": _local_fallback(messages)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AgentLLM] OpenAI request failed: %s", exc)
        fallback = _local_fallback(messages)
        fallback["error"] = str(exc)
        return fallback


def _anthropic_chat(model: str, messages: list[dict[str, str]], api_key: str, timeout: int) -> dict[str, Any]:
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    convo = [m for m in messages if m.get("role") != "system"]
    payload = {
        "model": model or "claude-3-5-haiku-latest",
        "max_tokens": 800,
        "system": "\n\n".join(system_parts) or SYSTEM_PROMPT,
        "messages": [{"role": m["role"], "content": m["content"]} for m in convo if m["role"] in {"user", "assistant"}],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        blocks = data.get("content") or []
        content = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        return {"ok": True, "content": sanitize_text(content), "provider": "anthropic"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AgentLLM] Anthropic request failed: %s", exc)
        fallback = _local_fallback(messages)
        fallback["error"] = str(exc)
        return fallback


def _local_fallback(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Rule-based responses when no LLM API is configured."""
    last_user = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            last_user = message.get("content", "").lower()
            break

    if any(word in last_user for word in ("setup", "install", "configure", "help", "start")):
        return {
            "ok": True,
            "content": build_setup_help()
            + "\n\nAdd OPENAI_API_KEY to .env for richer AI-assisted answers.",
            "provider": "local_fallback",
        }
    if any(word in last_user for word in ("clip", "score", "highlight", "explain", "why")):
        return {
            "ok": True,
            "content": (
                "I can explain clip selection using your latest run report. "
                "Generate clips first, then ask 'Why was clip 1 selected?' or use the Explain clips quick action. "
                "Without an API key I use local tool data only."
            ),
            "provider": "local_fallback",
        }
    if any(word in last_user for word in ("setting", "config", "improve", "better")):
        return {
            "ok": True,
            "content": (
                "Try these safe improvements:\n"
                "- Match game profile to your footage (valorant, cod, fortnite)\n"
                "- Lower min score if you get fallback clips\n"
                "- Enable AI vision (openai/auto) if you have an API key\n"
                "- Use platform presets: tiktok, youtube_shorts, instagram_reels\n"
                "Use 'Suggest settings' for tailored recommendations after a run."
            ),
            "provider": "local_fallback",
        }
    return {
        "ok": True,
        "content": (
            "I'm the Gameplay Auto Editor advisor. Ask me to explain clips, help with setup, "
            "suggest settings, or plan posting strategy. Add OPENAI_API_KEY for full AI responses."
        ),
        "provider": "local_fallback",
    }
