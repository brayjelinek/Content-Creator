"""Cooperative cancellation token for long-running pipeline stages."""

from __future__ import annotations

from threading import Lock


class PipelineCancelled(Exception):
    """Raised when the user cancels an in-flight pipeline run."""

    def __init__(self, stage: str = "") -> None:
        self.stage = stage
        message = f"Pipeline cancelled{f' during {stage}' if stage else ''}."
        super().__init__(message)


class PipelineControl:
    """Thread-safe cancel flag checked between pipeline stages."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._cancelled = False

    def reset(self) -> None:
        with self._lock:
            self._cancelled = False

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def check(self, stage: str = "") -> None:
        if self.is_cancelled:
            raise PipelineCancelled(stage)


_active_control: PipelineControl | None = None


def get_pipeline_control() -> PipelineControl:
    """Return the active pipeline control token (lazy singleton)."""
    global _active_control
    if _active_control is None:
        _active_control = PipelineControl()
    return _active_control


def reset_pipeline_control() -> PipelineControl:
    """Reset and return the active pipeline control token."""
    control = get_pipeline_control()
    control.reset()
    return control
