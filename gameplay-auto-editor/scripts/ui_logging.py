"""Bridge pipeline logging into the desktop UI queue."""

from __future__ import annotations

import logging
import queue
from typing import Callable


class UIQueueLogHandler(logging.Handler):
    """Forward log records to a thread-safe queue for the Tkinter UI."""

    def __init__(self, put_func: Callable[[str], None]):
        super().__init__()
        self.put_func = put_func

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            if message.strip():
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
