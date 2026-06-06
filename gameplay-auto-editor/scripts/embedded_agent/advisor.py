"""Main embedded advisor orchestrator."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from scripts.embedded_agent.connector import AgentConnector, ApprovalCallback
from scripts.embedded_agent.context_builder import build_app_context
from scripts.embedded_agent.llm_client import SYSTEM_PROMPT, chat_completion
from scripts.embedded_agent.memory import AgentMemory
from scripts.embedded_agent.settings import EmbeddedAgentSettings, load_agent_settings
from scripts.embedded_agent.tools import list_tool_schemas

logger = logging.getLogger(__name__)


class EmbeddedAgentAdvisor:
    """Read-only advisor with optional review-tier tools and human approval."""

    QUICK_PROMPTS = {
        "explain_clips": "Explain why the generated clips were selected and which ones I should review before posting.",
        "help_setup": "Help me set up this app. What do I need installed and configured?",
        "suggest_settings": "Based on my latest run, what settings should I change to get better clips?",
        "posting_strategy": "Which platforms should I post these clips to, and any caption improvements?",
    }

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        project_root: Path | None = None,
        approval_callback: ApprovalCallback | None = None,
    ):
        self.config = dict(config or {})
        self.settings = load_agent_settings(self.config)
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.memory = AgentMemory(max_messages=40)
        self.connector = AgentConnector(
            project_root=self.project_root,
            require_approval=self.settings.require_tool_approval,
            approval_callback=approval_callback,
        )
        self._report: dict[str, Any] | None = None
        self._ui_settings: dict[str, Any] | None = None
        self._refresh_system_prompt()

    def is_enabled(self) -> bool:
        rollout = dict(self.config.get("rollout") or {})
        optional = dict(rollout.get("optional_features") or {})
        return bool(self.settings.enabled) and bool(optional.get("embedded_agent", False))

    def update_context(
        self,
        *,
        report: dict[str, Any] | None = None,
        ui_settings: dict[str, Any] | None = None,
    ) -> None:
        if report is not None:
            self._report = report
        if ui_settings is not None:
            self._ui_settings = ui_settings
        self._refresh_system_prompt()

    def clear_conversation(self) -> None:
        self.memory.clear()
        self._refresh_system_prompt()

    def ask(self, user_message: str) -> dict[str, Any]:
        if not user_message.strip():
            return {"ok": False, "error": "Message cannot be empty."}
        if self.memory.turn_count >= self.settings.max_turns_per_session:
            return {
                "ok": False,
                "error": f"Session limit reached ({self.settings.max_turns_per_session} turns). Clear chat to continue.",
            }

        self.memory.add_user(user_message.strip())
        tool_results = self._run_requested_tools(user_message)
        messages = self._build_messages(tool_results)

        response = chat_completion(
            provider=self.settings.provider,
            model=self.settings.model,
            messages=messages,
            openai_api_key=self.settings.openai_api_key,
            anthropic_api_key=self.settings.anthropic_api_key,
        )

        if response.get("fallback"):
            fb = response.get("fallback") or {}
            content = str(fb.get("content") or "")
            provider = str(fb.get("provider") or "local_fallback")
            response_ok = bool(content)
        else:
            content = str(response.get("content") or "")
            provider = str(response.get("provider") or "unknown")
            response_ok = bool(response.get("ok", True) and content)

        if not content:
            content = "I couldn't generate a response. Try rephrasing or check your API key."

        if tool_results:
            tool_block = _format_tool_results(tool_results)
            content = f"{content}\n\n{tool_block}".strip()

        self.memory.add_assistant(content)
        return {
            "ok": response_ok,
            "content": content,
            "provider": provider,
            "tool_results": tool_results,
        }

    def ask_quick(self, prompt_key: str) -> dict[str, Any]:
        prompt = self.QUICK_PROMPTS.get(prompt_key)
        if not prompt:
            return {"ok": False, "error": f"Unknown quick prompt: {prompt_key}"}
        return self.ask(prompt)

    def get_pending_suggestions(self) -> list[dict[str, str]]:
        if not self.settings.allow_settings_suggestions:
            return []
        result = self.connector.execute(
            "suggest_settings",
            context={"config": self.config, "report": self._report},
        )
        return list(result.get("suggestions") or [])

    def _refresh_system_prompt(self) -> None:
        context = build_app_context(
            config=self.config,
            report=self._report,
            ui_settings=self._ui_settings,
            max_clips=self.settings.max_context_clips,
        )
        tools = ", ".join(t["name"] for t in list_tool_schemas())
        prompt = (
            f"{SYSTEM_PROMPT}\n\nAvailable tools: {tools}\n\n{context}"
        )
        self.memory.add_system(prompt)

    def _build_messages(self, tool_results: list[dict[str, Any]]) -> list[dict[str, str]]:
        messages = self.memory.history()
        if tool_results:
            messages = messages + [
                {
                    "role": "user",
                    "content": "Tool results:\n" + json.dumps(tool_results, indent=2)[:6000],
                }
            ]
        return messages

    def _run_requested_tools(self, user_message: str) -> list[dict[str, Any]]:
        text = user_message.lower()
        requested: list[str] = []
        if any(word in text for word in ("setup", "install", "configure", "tesseract", "ffmpeg")):
            requested.append("get_setup_help")
        if any(word in text for word in ("config", "setting", "profile", "preset")):
            requested.append("get_config_status")
        if any(word in text for word in ("run", "summary", "report", "batch", "result")):
            requested.append("get_run_summary")
        if "clip" in text:
            clip_index = _extract_clip_index(text)
            requested.append("explain_clip_selection")
        if any(word in text for word in ("suggest", "improve", "better", "change setting")):
            if self.settings.allow_settings_suggestions:
                requested.append("suggest_settings")

        if not requested and self._report:
            requested = ["get_run_summary"]

        context = {"config": self.config, "report": self._report}
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tool_name in requested[: self.settings.max_tool_calls_per_turn]:
            if tool_name in seen:
                continue
            seen.add(tool_name)
            args: dict[str, Any] = {}
            if tool_name in {"get_clip_details", "explain_clip_selection"}:
                args["clip_index"] = _extract_clip_index(text) or 1
            result = self.connector.execute(tool_name, arguments=args, context=context)
            results.append({"tool": tool_name, "result": result})
        return results


def _extract_clip_index(text: str) -> int | None:
    match = re.search(r"clip\s*(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def _format_tool_results(results: list[dict[str, Any]]) -> str:
    lines = ["--- Tool data ---"]
    for item in results:
        payload = item.get("result") or {}
        if payload.get("suggestions"):
            lines.append("Suggested settings (review before applying):")
            for suggestion in payload["suggestions"]:
                lines.append(
                    f"- {suggestion.get('setting')}: {suggestion.get('current')} → {suggestion.get('suggested')} "
                    f"({suggestion.get('reason')})"
                )
        elif payload.get("explanation"):
            lines.append(str(payload["explanation"]))
        elif payload.get("help"):
            lines.append(str(payload["help"])[:1200])
        elif payload.get("ok"):
            lines.append(json.dumps({k: v for k, v in payload.items() if k != "ok"}, default=str)[:800])
    return "\n".join(lines)
