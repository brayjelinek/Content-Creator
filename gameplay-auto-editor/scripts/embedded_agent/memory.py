"""In-memory session conversation history (never persisted to disk)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentMemory:
    """Bounded conversation memory for one app session."""

    max_messages: int = 40
    messages: list[dict[str, str]] = field(default_factory=list)
    turn_count: int = 0

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self.turn_count += 1
        self._trim()

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_system(self, content: str) -> None:
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0] = {"role": "system", "content": content}
        else:
            self.messages.insert(0, {"role": "system", "content": content})

    def history(self) -> list[dict[str, str]]:
        return list(self.messages)

    def clear(self) -> None:
        system = [m for m in self.messages if m.get("role") == "system"]
        self.messages = system
        self.turn_count = 0

    def _trim(self) -> None:
        system = [m for m in self.messages if m.get("role") == "system"]
        rest = [m for m in self.messages if m.get("role") != "system"]
        if len(rest) > self.max_messages:
            rest = rest[-self.max_messages :]
        self.messages = system + rest
