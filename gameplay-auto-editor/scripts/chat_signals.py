"""Optional chat-log spike detection for highlight scoring."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def load_chat_spike_times(chat_log_path: str | Path | None, config: dict | None = None) -> list[float]:
    """Parse a chat log and return timestamps where activity spikes."""
    cfg = dict(config or {})
    if not cfg.get("enabled", False):
        return []

    path = Path(chat_log_path) if chat_log_path else None
    if not path or not path.exists():
        return []

    try:
        messages = _parse_chat_log(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ChatSignals] Could not parse chat log — skipping: %s", exc)
        return []

    if not messages:
        return []

    window_seconds = float(cfg.get("window_seconds", 2.0))
    min_messages = max(2, int(cfg.get("min_messages_per_window", 5)))
    spikes = _find_spike_times(messages, window_seconds, min_messages)
    if spikes:
        logger.info("[ChatSignals] Detected %s chat spike window(s)", len(spikes))
    return spikes


def apply_chat_spikes_to_analyses(analyses: list[dict], spike_times: list[float], config: dict | None = None) -> None:
    """Tag analyses near chat spikes with a gameplay signal (non-blocking)."""
    if not spike_times:
        return

    cfg = dict(config or {})
    match_window = float(cfg.get("match_window_seconds", 2.5))
    bonus = float(cfg.get("score_bonus", 15))

    for item in analyses:
        timestamp = float(item.get("timestamp", 0))
        if not any(abs(timestamp - spike) <= match_window for spike in spike_times):
            continue
        signals = dict(item.get("gameplay_signals") or {})
        signals["chat_spike_detected"] = True
        item["gameplay_signals"] = signals
        item["chat_spike_bonus"] = bonus


def _parse_chat_log(path: Path) -> list[tuple[float, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []

    if path.suffix.lower() == ".json" or text.startswith("{"):
        return _parse_chat_json(text)
    if path.suffix.lower() == ".csv":
        return _parse_chat_csv(path)
    return _parse_chat_lines(text)


def _parse_chat_json(text: str) -> list[tuple[float, str]]:
    payload = json.loads(text)
    rows: list[tuple[float, str]] = []

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get("comments") or payload.get("messages") or payload.get("chat") or []
    else:
        return rows

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        timestamp = _coerce_timestamp(
            entry.get("timestamp")
            or entry.get("time")
            or entry.get("offset")
            or entry.get("content_offset_seconds")
        )
        message = str(entry.get("message") or entry.get("text") or entry.get("body") or "").strip()
        if timestamp is not None:
            rows.append((timestamp, message))
    return rows


def _parse_chat_csv(path: Path) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    with path.open(encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        for line in reader:
            if len(line) < 2:
                continue
            timestamp = _coerce_timestamp(line[0])
            if timestamp is None:
                continue
            rows.append((timestamp, line[1].strip()))
    return rows


def _parse_chat_lines(text: str) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    pattern = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[|,:\-]\s*(.+)$")
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        rows.append((float(match.group(1)), match.group(2).strip()))
    return rows


def _coerce_timestamp(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _find_spike_times(messages: list[tuple[float, str]], window_seconds: float, min_messages: int) -> list[float]:
    if not messages:
        return []

    messages = sorted(messages, key=lambda item: item[0])
    spikes: list[float] = []
    start = 0
    for end in range(len(messages)):
        while messages[end][0] - messages[start][0] > window_seconds:
            start += 1
        if end - start + 1 >= min_messages:
            center = (messages[start][0] + messages[end][0]) / 2.0
            if not spikes or abs(center - spikes[-1]) > window_seconds:
                spikes.append(round(center, 2))
    return spikes
