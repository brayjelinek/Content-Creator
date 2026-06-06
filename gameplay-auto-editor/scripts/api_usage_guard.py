"""Session- and video-level safeguards for OpenAI Vision API usage."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_VIDEO = 10
DEFAULT_MAX_PER_SESSION = 50
DEFAULT_HYBRID_MIN = 3
DEFAULT_HYBRID_MAX = 8

QUOTA_MARKERS = (
    "insufficient_quota",
    "rate_limit_exceeded",
    "billing_hard_limit",
)

_SESSION_CALLS = 0
_VIDEO_CALLS = 0
_SESSION_DISABLED = False
_RUN_DISABLED = False

_logged_session_limit = False
_logged_session_limit = False
_logged_video_limit = False
_logged_run_quota = False
_logged_fallback_limit = False
_logged_partial_ai = False


def reset_video_counter() -> None:
    """Reset per-video counters at the start of each pipeline run."""
    global _VIDEO_CALLS, _RUN_DISABLED
    global _logged_video_limit, _logged_session_limit, _logged_run_quota, _logged_fallback_limit, _logged_partial_ai

    _VIDEO_CALLS = 0
    _RUN_DISABLED = False
    _logged_video_limit = False
    _logged_session_limit = False
    _logged_run_quota = False
    _logged_fallback_limit = False
    _logged_partial_ai = False


def get_limits(config: dict | None) -> dict[str, Any]:
    cfg = dict(config or {})
    return {
        "enabled": bool(cfg.get("api_usage_protection_enabled", True)),
        "max_per_video": max(1, int(cfg.get("max_api_calls_per_video", DEFAULT_MAX_PER_VIDEO))),
        "max_per_session": max(1, int(cfg.get("max_api_calls_per_session", DEFAULT_MAX_PER_SESSION))),
        "hybrid_min": max(1, int(cfg.get("hybrid_ai_clip_min", DEFAULT_HYBRID_MIN))),
        "hybrid_max": max(1, int(cfg.get("hybrid_ai_clip_max", DEFAULT_HYBRID_MAX))),
    }


def remaining_video_budget(config: dict | None) -> int:
    limits = get_limits(config)
    if not limits["enabled"]:
        return limits["max_per_video"]
    if _SESSION_DISABLED or _RUN_DISABLED:
        return 0
    return max(0, limits["max_per_video"] - _VIDEO_CALLS)


def remaining_session_budget(config: dict | None) -> int:
    limits = get_limits(config)
    if not limits["enabled"]:
        return limits["max_per_session"]
    if _SESSION_DISABLED:
        return 0
    return max(0, limits["max_per_session"] - _SESSION_CALLS)


def can_make_api_call(config: dict | None) -> tuple[bool, str]:
    """Return whether another Vision API call is allowed and the blocking reason."""
    limits = get_limits(config)
    if not limits["enabled"]:
        return True, ""

    if _SESSION_DISABLED:
        return False, "session"
    if _RUN_DISABLED:
        return False, "run"
    if _VIDEO_CALLS >= limits["max_per_video"]:
        return False, "video"
    if _SESSION_CALLS >= limits["max_per_session"]:
        disable_for_session()
        return False, "session"
    return True, ""


def record_api_call(config: dict | None) -> tuple[int, int]:
    """Record a successful Vision API call."""
    global _VIDEO_CALLS, _SESSION_CALLS

    _VIDEO_CALLS += 1
    _SESSION_CALLS += 1
    logger.info("[AI] API call #%s for this video", _VIDEO_CALLS)
    logger.info("[AI] API call #%s for this session", _SESSION_CALLS)
    return _VIDEO_CALLS, _SESSION_CALLS


def log_limit_fallback(reason: str) -> None:
    """Log limit-triggered fallback once per reason to avoid spam."""
    global _logged_fallback_limit, _logged_video_limit, _logged_session_limit, _logged_run_quota, _logged_partial_ai

    if reason == "video" and not _logged_video_limit:
        logger.info("[AI] API limit reached — switching to heuristic fallback")
        logger.info("[AI] Fallback triggered due to limit")
        _logged_video_limit = True
        _logged_fallback_limit = True
        return

    if reason == "session" and not _logged_session_limit:
        logger.info("[AI] Session API limit reached — AI disabled until restart")
        logger.info("[AI] API limit reached — switching to heuristic fallback")
        logger.info("[AI] Fallback triggered due to limit")
        _logged_session_limit = True
        _logged_fallback_limit = True
        return

    if reason == "run" and not _logged_run_quota:
        logger.info("[AI] OpenAI quota low — using heuristic fallback")
        logger.info("[AI] Fallback triggered due to limit")
        _logged_run_quota = True
        _logged_fallback_limit = True


def log_partial_ai_completion() -> None:
    global _logged_partial_ai
    if _logged_partial_ai:
        return
    logger.info("[AI] Max API calls reached — finishing with partial AI scoring")
    _logged_partial_ai = True


def disable_for_session() -> None:
    global _SESSION_DISABLED
    if _SESSION_DISABLED:
        return
    _SESSION_DISABLED = True
    log_limit_fallback("session")


def disable_for_run() -> None:
    global _RUN_DISABLED
    if _RUN_DISABLED:
        return
    _RUN_DISABLED = True
    log_limit_fallback("run")


def is_quota_error(exc: Exception) -> bool:
    """Detect OpenAI quota, billing, and hard rate-limit failures."""
    parts: list[str] = [str(exc).lower(), exc.__class__.__name__.lower()]
    for attr in ("code", "type", "message"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value).lower())

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        parts.append(str(body).lower())

    combined = " ".join(parts)
    return any(marker in combined for marker in QUOTA_MARKERS)


def handle_quota_error(exc: Exception, config: dict | None) -> None:
    """Disable AI for the current run when OpenAI quota is exhausted."""
    disable_for_run()
    logger.debug("[AI] Quota error detail: %s", exc)


def select_hybrid_api_candidates(
    sample_count: int,
    heuristic_scores: list[float],
    config: dict | None,
) -> set[int]:
    """Pick 3–8 heuristic front-runners for Hybrid/auto Vision calls."""
    if sample_count <= 0:
        return set()

    limits = get_limits(config)
    hybrid_min = min(limits["hybrid_min"], sample_count)
    hybrid_max = min(limits["hybrid_max"], sample_count)
    budget = min(remaining_video_budget(config), remaining_session_budget(config), hybrid_max)

    if budget <= 0:
        return set()

    target = max(hybrid_min, min(budget, hybrid_max)) if sample_count >= hybrid_min else min(budget, sample_count)
    ranked = sorted(range(sample_count), key=lambda index: heuristic_scores[index], reverse=True)
    return set(ranked[:target])


def get_usage_summary(config: dict | None) -> dict[str, Any]:
    """Return API usage counters for run reports."""
    limits = get_limits(config)
    return {
        "protection_enabled": limits["enabled"],
        "video_calls": _VIDEO_CALLS,
        "session_calls": _SESSION_CALLS,
        "max_per_video": limits["max_per_video"],
        "max_per_session": limits["max_per_session"],
        "run_disabled": _RUN_DISABLED,
        "session_disabled": _SESSION_DISABLED,
    }
