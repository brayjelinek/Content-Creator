"""Bridge pipeline logging into the desktop UI queue."""

from __future__ import annotations

import logging
import queue
import time
from typing import Callable


class LogRateLimiter:
    """Suppress repeated log lines within a short window."""

    def __init__(self, interval_seconds: float = 1.5, max_keys: int = 256):
        self.interval_seconds = interval_seconds
        self.max_keys = max_keys
        self._last_seen: dict[str, float] = {}

    def allow(self, message: str) -> bool:
        key = " ".join(message.split())[:160]
        now = time.monotonic()
        last = self._last_seen.get(key)
        if last is not None and now - last < self.interval_seconds:
            return False
        self._last_seen[key] = now
        if len(self._last_seen) > self.max_keys:
            oldest = sorted(self._last_seen.items(), key=lambda item: item[1])[:32]
            for stale_key, _ in oldest:
                self._last_seen.pop(stale_key, None)
        return True


class UIQueueLogHandler(logging.Handler):
    """Forward log records to a thread-safe queue for the Tkinter UI."""

    def __init__(self, put_func: Callable[[str], None], rate_limiter: LogRateLimiter | None = None):
        super().__init__()
        self.put_func = put_func
        self.rate_limiter = rate_limiter or LogRateLimiter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            if not message.strip():
                return
            if not self.rate_limiter.allow(message):
                return
            self.put_func(message)
        except Exception:  # noqa: BLE001 - logging must never break pipeline
            return


class UIHandlerSession:
    """Temporary UI logging session that avoids duplicate console output."""

    def __init__(self, handler: UIQueueLogHandler, paused_handlers: list[logging.Handler]):
        self.handler = handler
        self.paused_handlers = paused_handlers


def attach_ui_log_handler(output_queue: queue.Queue) -> UIHandlerSession:
    """Attach a queue-backed log handler to the root logger."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    paused_handlers: list[logging.Handler] = []
    for existing in root.handlers[:]:
        if isinstance(existing, UIQueueLogHandler):
            root.removeHandler(existing)
            existing.close()
            continue
        if isinstance(existing, logging.StreamHandler) and not isinstance(existing, logging.FileHandler):
            root.removeHandler(existing)
            paused_handlers.append(existing)

    handler = UIQueueLogHandler(output_queue.put)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    return UIHandlerSession(handler, paused_handlers)


def detach_ui_log_handler(session: UIHandlerSession) -> None:
    """Remove the temporary UI log handler and restore console handlers."""
    root = logging.getLogger()
    root.removeHandler(session.handler)
    session.handler.close()

    for handler in session.paused_handlers:
        root.addHandler(handler)
