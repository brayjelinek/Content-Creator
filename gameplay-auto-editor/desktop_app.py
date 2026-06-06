"""Native desktop app for Gameplay Auto Editor."""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import BOTH, END, LEFT, W, Canvas, filedialog, messagebox
from tkinter import DoubleVar, StringVar, Text, Tk
from tkinter import ttk

from scripts.clip_metadata import quality_tier, summarize_enhancements
from scripts.embedded_agent.advisor import EmbeddedAgentAdvisor
from scripts.pipeline import PROJECT_ROOT, load_config, run_pipeline
from scripts.social_publish.manager import SocialPublishManager
from scripts.ui_logging import attach_ui_log_handler, detach_ui_log_handler


APP_TITLE = "Gameplay Auto Editor"


class QueueWriter:
    def __init__(self, output_queue: queue.Queue[str]):
        self.output_queue = output_queue

    def write(self, text: str) -> None:
        if text.strip():
            self.output_queue.put(text)

    def flush(self) -> None:
        return


class GameplayAutoEditorApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1040x760")
        self.root.minsize(900, 650)

        self.output_queue: queue.Queue = queue.Queue()
        self.selected_video: Path | None = None
        self.report: dict | None = None
        self.progress_var = DoubleVar(value=0.0)
        self.stage_var = StringVar(value="Waiting to start...")

        self.provider_var = StringVar(value=self._initial_provider())
        self.max_clips_var = StringVar(value="5")
        self.min_score_var = StringVar(value="25")
        self.interval_var = StringVar(value="3")
        self.max_frames_var = StringVar(value="10")
        self.platform_var = StringVar(value=self._initial_platform_preset())
        self.theme_var = StringVar(value=self._initial_theme())
        self.game_profile_var = StringVar(value=self._initial_game_profile())
        self.smart_reframe_var = StringVar(value=self._initial_smart_reframe())
        self.status_var = StringVar(value="Choose a gameplay video to begin.")
        self.openai_key_var = StringVar(value="")
        self.key_status_var = StringVar(value=self._api_key_status())
        self.ocr_status_var = StringVar(value=self._ocr_status())
        self.video_queue: list[Path] = []
        self.batch_reports: list[dict] = []
        self.config = load_config()
        self.social_manager = SocialPublishManager(self.config, PROJECT_ROOT)
        self.agent_advisor = EmbeddedAgentAdvisor(
            self.config,
            PROJECT_ROOT,
            approval_callback=self._agent_tool_approval,
        )
        self.agent_input_var = StringVar(value="")
        self.agent_status_var = StringVar(value=self._agent_status_text())
        self.social_status_vars = {
            "youtube": StringVar(value="YouTube: checking..."),
            "tiktok": StringVar(value="TikTok: checking..."),
            "instagram": StringVar(value="Instagram: checking..."),
        }

        self._build_ui()
        self._poll_output_queue()
        self._refresh_social_status()
        self.agent_advisor.update_context(ui_settings=self._ui_settings_snapshot())

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=("Arial", 22, "bold")).pack(anchor=W)
        ttk.Label(
            header,
            text="Upload gameplay, generate vertical clips, review the winners, and open or export the ones you like.",
        ).pack(anchor=W, pady=(4, 14))

        controls = ttk.LabelFrame(outer, text="1. Select video and clip settings", padding=14)
        controls.pack(fill="x", pady=(0, 12))

        file_row = ttk.Frame(controls)
        file_row.pack(fill="x", pady=(0, 10))
        ttk.Button(file_row, text="Choose gameplay video", command=self.choose_video).pack(side=LEFT)
        ttk.Button(file_row, text="Add to queue", command=self.add_to_queue).pack(side=LEFT, padx=(8, 0))
        ttk.Button(file_row, text="Clear queue", command=self.clear_queue).pack(side=LEFT, padx=(8, 0))
        self.file_label = ttk.Label(file_row, text="No video selected")
        self.file_label.pack(side=LEFT, padx=12)

        queue_row = ttk.Frame(controls)
        queue_row.pack(fill="x", pady=(0, 10))
        ttk.Label(queue_row, text="Batch queue:").pack(side=LEFT)
        self.queue_listbox = ttk.Treeview(queue_row, columns=("video",), show="headings", height=3)
        self.queue_listbox.heading("video", text="Queued videos")
        self.queue_listbox.column("video", width=760, stretch=True)
        self.queue_listbox.pack(side=LEFT, fill="x", expand=True, padx=(8, 0))

        settings_row = ttk.Frame(controls)
        settings_row.pack(fill="x")
        self._add_combobox(settings_row, "Vision mode", self.provider_var, ["heuristic", "auto", "openai", "anthropic"])
        self._add_spinbox(settings_row, "Sample clips", self.max_clips_var, 1, 10)
        self._add_spinbox(settings_row, "Minimum score", self.min_score_var, 0, 100)
        self._add_spinbox(settings_row, "Analyze every N seconds", self.interval_var, 1, 10)
        self._add_spinbox(settings_row, "Max AI frames", self.max_frames_var, 1, 40)
        self._add_combobox(
            settings_row,
            "Platform preset",
            self.platform_var,
            ["generic", "tiktok", "youtube_shorts", "instagram_reels"],
        )
        self._add_combobox(settings_row, "Visual theme", self.theme_var, ["default", "hormozi", "minimal", "gen_z"])
        self._add_combobox(
            settings_row,
            "Game profile",
            self.game_profile_var,
            ["generic", "valorant", "cod", "fortnite"],
        )
        self._add_combobox(settings_row, "Smart reframe", self.smart_reframe_var, ["off", "on"])

        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=(0, 12))
        self.generate_button = ttk.Button(action_row, text="Generate clips", command=self.generate_clips)
        self.generate_button.pack(side=LEFT)
        ttk.Button(action_row, text="Open final clips folder", command=lambda: open_path(PROJECT_ROOT / "final_clips")).pack(
            side=LEFT,
            padx=8,
        )
        ttk.Button(action_row, text="Export all clips...", command=self.export_all_clips).pack(side=LEFT, padx=(0, 8))
        ttk.Button(action_row, text="Copy all captions", command=self.copy_all_captions).pack(side=LEFT)
        ttk.Label(action_row, textvariable=self.status_var).pack(side=LEFT, padx=12)

        api_frame = ttk.LabelFrame(outer, text="Optional: AI vision key", padding=10)
        api_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(api_frame, textvariable=self.key_status_var).pack(anchor=W)
        api_row = ttk.Frame(api_frame)
        api_row.pack(fill="x", pady=(6, 0))
        ttk.Label(api_row, text="OpenAI API key").pack(side=LEFT)
        ttk.Entry(api_row, textvariable=self.openai_key_var, show="*", width=58).pack(side=LEFT, padx=8)
        ttk.Button(api_row, text="Save key", command=self.save_openai_key).pack(side=LEFT)

        ocr_frame = ttk.LabelFrame(outer, text="Optional: Killfeed OCR (Tesseract)", padding=10)
        ocr_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(ocr_frame, textvariable=self.ocr_status_var, wraplength=960).pack(anchor=W)
        ttk.Label(
            ocr_frame,
            text="Install Tesseract for killfeed detection: https://github.com/UB-Mannheim/tesseract/wiki",
            wraplength=960,
        ).pack(anchor=W, pady=(4, 0))

        self.social_frame = ttk.LabelFrame(outer, text="Optional: Direct platform posting (OAuth)", padding=10)
        self.social_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            self.social_frame,
            text=(
                "Connect YouTube, TikTok, or Instagram to post clips directly. "
                "Tokens are stored in your OS keychain — never in config or logs. "
                "You must confirm each post. Enable social_publish.enabled and "
                "rollout.optional_features.direct_publish in config.json to activate."
            ),
            wraplength=960,
        ).pack(anchor=W)
        for platform, label in (
            ("youtube", "YouTube Shorts"),
            ("tiktok", "TikTok"),
            ("instagram", "Instagram Reels"),
        ):
            row = ttk.Frame(self.social_frame)
            row.pack(fill="x", pady=(6, 0))
            ttk.Label(row, text=label, width=18).pack(side=LEFT)
            ttk.Label(row, textvariable=self.social_status_vars[platform], wraplength=520).pack(
                side=LEFT,
                padx=(0, 12),
            )
            ttk.Button(row, text="Connect", command=lambda p=platform: self.connect_platform(p)).pack(side=LEFT)
            ttk.Button(row, text="Disconnect", command=lambda p=platform: self.disconnect_platform(p)).pack(
                side=LEFT,
                padx=(8, 0),
            )

        self.agent_frame = ttk.LabelFrame(outer, text="Optional: AI Assistant (advisor)", padding=10)
        self.agent_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            self.agent_frame,
            text=(
                "Ask questions about your clips, setup, settings, and posting strategy. "
                "The assistant uses local run data only — secrets are never sent. "
                "Mutating actions require your approval. Enable embedded_agent.enabled and "
                "rollout.optional_features.embedded_agent in config.json."
            ),
            wraplength=960,
        ).pack(anchor=W)
        ttk.Label(self.agent_frame, textvariable=self.agent_status_var, wraplength=960).pack(anchor=W, pady=(4, 0))

        quick_row = ttk.Frame(self.agent_frame)
        quick_row.pack(fill="x", pady=(6, 0))
        ttk.Label(quick_row, text="Quick:").pack(side=LEFT)
        for label, key in (
            ("Explain clips", "explain_clips"),
            ("Help setup", "help_setup"),
            ("Suggest settings", "suggest_settings"),
            ("Posting tips", "posting_strategy"),
        ):
            ttk.Button(quick_row, text=label, command=lambda k=key: self.agent_quick_prompt(k)).pack(
                side=LEFT,
                padx=(8, 0),
            )

        self.agent_chat = Text(self.agent_frame, height=6, wrap="word", state="disabled")
        self.agent_chat.pack(fill="x", pady=(8, 0))

        input_row = ttk.Frame(self.agent_frame)
        input_row.pack(fill="x", pady=(6, 0))
        self.agent_entry = ttk.Entry(input_row, textvariable=self.agent_input_var, width=80)
        self.agent_entry.pack(side=LEFT, fill="x", expand=True)
        self.agent_entry.bind("<Return>", lambda _event: self.agent_send_message())
        ttk.Button(input_row, text="Send", command=self.agent_send_message).pack(side=LEFT, padx=(8, 0))
        ttk.Button(input_row, text="Clear chat", command=self.agent_clear_chat).pack(side=LEFT, padx=(8, 0))

        progress = ttk.LabelFrame(outer, text="2. Progress", padding=10)
        progress.pack(fill="x", pady=(0, 12))
        self.progress_bar = ttk.Progressbar(progress, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(progress, textvariable=self.stage_var).pack(anchor=W, pady=(0, 6))
        self.progress_text = Text(progress, height=8, wrap="word")
        self.progress_text.pack(fill="x")

        results_outer = ttk.LabelFrame(outer, text="3. Review generated clips", padding=10)
        results_outer.pack(fill=BOTH, expand=True)
        self.results_canvas_widget = Canvas(results_outer, highlightthickness=0)
        self.results_scrollbar = ttk.Scrollbar(
            results_outer,
            orient="vertical",
            command=self.results_canvas_widget.yview,
        )
        self.results_canvas = ttk.Frame(self.results_canvas_widget)
        self.results_canvas.bind(
            "<Configure>",
            lambda _event: self.results_canvas_widget.configure(
                scrollregion=self.results_canvas_widget.bbox("all")
            ),
        )
        self.results_window = self.results_canvas_widget.create_window(
            (0, 0),
            window=self.results_canvas,
            anchor="nw",
        )
        self.results_canvas_widget.configure(yscrollcommand=self.results_scrollbar.set)
        self.results_canvas_widget.bind(
            "<Configure>",
            lambda event: self.results_canvas_widget.itemconfigure(self.results_window, width=event.width),
        )
        self.results_canvas_widget.pack(side=LEFT, fill=BOTH, expand=True)
        self.results_scrollbar.pack(side="right", fill="y")
        self.results_canvas_widget.bind_all("<MouseWheel>", self._on_mousewheel)

        self.results_placeholder = ttk.Label(
            self.results_canvas,
            text="Generated clips will appear here with score, caption, and open/export buttons.",
        )
        self.results_placeholder.pack(anchor=W)

    def _add_combobox(self, parent: ttk.Frame, label: str, variable: StringVar, values: list[str]) -> None:
        frame = ttk.Frame(parent)
        frame.pack(side=LEFT, padx=(0, 18))
        ttk.Label(frame, text=label).pack(anchor=W)
        ttk.Combobox(frame, textvariable=variable, values=values, width=14, state="readonly").pack(anchor=W)

    def _add_spinbox(self, parent: ttk.Frame, label: str, variable: StringVar, from_: int, to: int) -> None:
        frame = ttk.Frame(parent)
        frame.pack(side=LEFT, padx=(0, 18))
        ttk.Label(frame, text=label).pack(anchor=W)
        ttk.Spinbox(frame, from_=from_, to=to, textvariable=variable, width=8).pack(anchor=W)

    def choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose gameplay video",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.webm *.avi"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self.selected_video = Path(path)
        self.file_label.configure(text=self.selected_video.name)
        self.status_var.set("Ready to generate clips.")

    def add_to_queue(self) -> None:
        if not self.selected_video:
            messagebox.showinfo(APP_TITLE, "Choose a gameplay video first.")
            return
        if self.selected_video in self.video_queue:
            self.status_var.set("Video already in queue.")
            return
        self.video_queue.append(self.selected_video)
        self._refresh_queue_list()
        self.status_var.set(f"{len(self.video_queue)} video(s) queued.")

    def clear_queue(self) -> None:
        self.video_queue.clear()
        self._refresh_queue_list()
        self.status_var.set("Queue cleared.")

    def _refresh_queue_list(self) -> None:
        for item in self.queue_listbox.get_children():
            self.queue_listbox.delete(item)
        for index, path in enumerate(self.video_queue, start=1):
            self.queue_listbox.insert("", END, iid=str(index), values=(path.name,))

    def generate_clips(self) -> None:
        targets = list(self.video_queue) if self.video_queue else ([self.selected_video] if self.selected_video else [])
        if not targets:
            messagebox.showinfo(APP_TITLE, "Choose a gameplay video first.")
            return

        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            messagebox.showerror(
                APP_TITLE,
                "FFmpeg is required but was not found. Install FFmpeg, then reopen the app.",
            )
            return

        try:
            from scripts.ocr_utils import initialize_ocr
            from scripts.pipeline_validation import preflight_pipeline
            from scripts.pipeline import load_config

            config = load_config()
            ocr_status = initialize_ocr(config.get("ocr", {}))
            if ocr_status.get("available"):
                self.ocr_status_var.set(f"Killfeed OCR ready: {ocr_status.get('tesseract_path')}")
            else:
                self.ocr_status_var.set(
                    "Killfeed OCR not detected. Clips still generate. "
                    "Install from https://github.com/UB-Mannheim/tesseract/wiki"
                )

            preflight = preflight_pipeline(targets[0], config.get("rendering", {}))
            if not preflight["ok"]:
                messagebox.showerror(APP_TITLE, "\n".join(preflight["errors"]))
                return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Preflight check failed:\n{exc}")
            return

        settings = self._settings_override()
        self.generate_button.configure(state="disabled")
        self.batch_reports = []
        self.status_var.set(f"Generating clips for {len(targets)} video(s)...")
        self.progress_var.set(0.0)
        self.stage_var.set("Starting clip generation...")
        self.progress_text.delete("1.0", END)
        self._reset_results_panel()

        thread = threading.Thread(target=self._run_batch_worker, args=(targets, settings), daemon=True)
        thread.start()

    def _run_batch_worker(self, targets: list[Path], settings: dict) -> None:
        writer = QueueWriter(self.output_queue)
        ui_session = attach_ui_log_handler(self.output_queue)

        def progress_callback(event: dict) -> None:
            self.output_queue.put(("EVENT", event))

        combined_report: dict | None = None
        try:
            with redirect_stdout(writer):
                for index, video_path in enumerate(targets, start=1):
                    self.output_queue.put(f"\n=== Batch {index}/{len(targets)}: {video_path.name} ===\n")
                    report = run_pipeline(
                        video_path,
                        config_override=settings,
                        progress_callback=progress_callback,
                    )
                    self.batch_reports.append(report)
                    combined_report = report
            if combined_report and len(self.batch_reports) > 1:
                combined_report = self._merge_batch_reports(self.batch_reports)
            self.output_queue.put(("DONE", combined_report or {}))
            if self.video_queue:
                self.video_queue.clear()
                self.root.after(0, self._refresh_queue_list)
        except Exception as exc:  # noqa: BLE001
            self.output_queue.put(("ERROR", f"{exc}\n\n{traceback.format_exc()}"))
        finally:
            detach_ui_log_handler(ui_session)

    def _merge_batch_reports(self, reports: list[dict]) -> dict:
        last = dict(reports[-1])
        last["batch_count"] = len(reports)
        last["clips_created"] = sum(int(report.get("clips_created", 0)) for report in reports)
        last["batch_videos"] = [str(report.get("input_video", "")) for report in reports]
        return last

    def save_openai_key(self) -> None:
        key = self.openai_key_var.get().strip()
        if not key:
            messagebox.showinfo(APP_TITLE, "Paste an OpenAI API key first.")
            return

        env_path = PROJECT_ROOT / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(
            "\n".join(
                [
                    "VISION_PROVIDER=openai",
                    f"OPENAI_API_KEY={key}",
                    "OPENAI_MODEL=gpt-4o-mini",
                    "ANTHROPIC_API_KEY=",
                    "ANTHROPIC_MODEL=claude-3-5-haiku-latest",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.provider_var.set("openai")
        self.openai_key_var.set("")
        self.key_status_var.set("OpenAI key saved. Vision mode is set to openai.")
        self.status_var.set("API key saved.")

    def _poll_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "DONE":
                    self._generation_done(item[1])
                elif isinstance(item, tuple) and item[0] == "ERROR":
                    self._generation_failed(item[1])
                elif isinstance(item, tuple) and item[0] == "EVENT":
                    self._handle_ui_event(item[1])
                else:
                    self._append_progress(str(item))
        except queue.Empty:
            pass

        self.root.after(200, self._poll_output_queue)

    def _handle_ui_event(self, event: dict) -> None:
        event_type = event.get("type")
        message = event.get("message", "")
        percent = event.get("percent")

        if isinstance(percent, (int, float)):
            self.progress_var.set(float(percent))
        if message:
            self.stage_var.set(message)

        if event_type == "progress":
            stage = event.get("stage", "processing")
            if message:
                self._append_progress(f"[{stage}] {message}")
        elif event_type == "highlights_detected":
            count = int(event.get("count", 0))
            self._append_progress(f"Highlight detection complete: {count} moment(s) found.")
        elif event_type == "notice":
            self._append_progress(message)
        elif event_type in ("clips_ready", "refresh_clips_ui"):
            self._apply_clips_event(event)
        elif event_type == "run_summary":
            self._append_progress(message)
            report = event.get("report") or {}
            features = report.get("features_applied") or {}
            enabled = [name.replace("_", " ") for name, active in features.items() if active]
            if enabled:
                self._append_progress("Active features: " + ", ".join(enabled))
            tiers = report.get("quality_tier_counts") or {}
            if tiers:
                tier_text = ", ".join(f"{key}={value}" for key, value in sorted(tiers.items()))
                self._append_progress(f"Quality tiers: {tier_text}")

    def _apply_clips_event(self, event: dict) -> None:
        clip_count = int(event.get("count", 0))
        message = event.get("message") or f"{clip_count} clip(s) ready to review."
        if event.get("type") == "clips_ready":
            self.progress_var.set(100.0)
            self.stage_var.set(message)
        self._append_progress(message)
        report = {
            "clips": event.get("clips") or [],
            "clips_ready": event.get("clips_ready") or [],
            "clips_created": max(clip_count, len(event.get("clips_ready") or [])),
            "output_dir": event.get("output_dir") or str((PROJECT_ROOT / "final_clips").resolve()),
        }
        self._show_results(report)

    def _generation_done(self, report: dict) -> None:
        self.report = report
        self.agent_advisor.update_context(report=report, ui_settings=self._ui_settings_snapshot())
        self.agent_status_var.set(self._agent_status_text())
        self.generate_button.configure(state="normal")
        clips_created = int(report.get("clips_created", 0))
        batch_count = int(report.get("batch_count", 0))
        self.progress_var.set(100.0)
        if batch_count > 1:
            self.stage_var.set(f"Batch done. Processed {batch_count} video(s), created {clips_created} clip(s).")
            self.status_var.set(f"Batch done. {batch_count} video(s), {clips_created} clip(s).")
        else:
            self.stage_var.set(f"Done. Created {clips_created} clip(s).")
            self.status_var.set(f"Done. Created {clips_created} clip(s).")
        if clips_created == 0:
            reason = report.get("failure_reason")
            log_file = report.get("log_file", "")
            if reason == "render_failed":
                hint = "Highlights were found but FFmpeg rendering failed. Open the log file for [FFmpeg] errors."
            else:
                hint = "No clips were created. Open the log file for details."
            self._append_progress(f"\n{hint}\nLog file: {log_file}\n")
        self._show_results(report)

    def _generation_failed(self, error_text: str) -> None:
        self.generate_button.configure(state="normal")
        self.status_var.set("Generation failed.")
        self.stage_var.set("Generation failed.")
        self._append_progress(error_text)
        messagebox.showerror(APP_TITLE, "Clip generation failed. See the progress box for details.")

    def _resolve_clip_file(self, clip: dict, report: dict | None = None) -> Path | None:
        raw_path = clip.get("final_clip")
        if not raw_path:
            return None

        active_report = report or self.report or {}
        candidates = [
            Path(raw_path),
            PROJECT_ROOT / "final_clips" / Path(raw_path).name,
            PROJECT_ROOT / Path(raw_path).name,
        ]
        output_dir = active_report.get("output_dir")
        if output_dir:
            candidates.insert(0, Path(output_dir) / Path(raw_path).name)

        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return Path(raw_path).resolve()

    def _clips_for_display(self, report: dict) -> list[dict]:
        clips = list(report.get("clips") or [])
        if clips:
            return clips

        clips_ready = list(report.get("clips_ready") or [])
        if clips_ready:
            return [
                {
                    "final_clip": path,
                    "score": 0,
                    "hook_text": Path(path).stem.replace("_", " "),
                    "caption_text": Path(path).name,
                    "categories": [],
                    "start": 0,
                    "end": 0,
                }
                for path in clips_ready
            ]

        final_dir = Path(report.get("output_dir") or PROJECT_ROOT / "final_clips")
        if final_dir.exists():
            discovered = sorted(final_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
            if discovered:
                return [
                    {
                        "final_clip": str(path.resolve()),
                        "score": 0,
                        "hook_text": path.stem.replace("_", " "),
                        "caption_text": path.name,
                        "categories": [],
                        "start": 0,
                        "end": 0,
                    }
                    for path in discovered[:10]
                ]
        return []

    def _show_results(self, report: dict) -> None:
        self._clear_results()
        clips = self._clips_for_display(report)
        if not clips:
            reason = report.get("failure_reason")
            if reason == "render_failed":
                message = (
                    "Highlights were detected but rendering failed. "
                    "Check the log file for [FFmpeg] errors (font path, filter chain, or missing FFmpeg)."
                )
            else:
                message = (
                    "Clips are still being finalized. If nothing appears shortly, open the final clips folder "
                    "or check the progress log for details."
                )
            ttk.Label(self.results_canvas, text=message, wraplength=900).pack(anchor=W)
            log_file = report.get("log_file")
            if log_file:
                ttk.Label(self.results_canvas, text=f"Log file: {log_file}", wraplength=900).pack(anchor=W, pady=(6, 0))
            output_dir = report.get("output_dir") or str((PROJECT_ROOT / "final_clips").resolve())
            ttk.Label(self.results_canvas, text=f"Output folder: {output_dir}", wraplength=900).pack(
                anchor=W,
                pady=(6, 0),
            )
            self._refresh_results_canvas()
            return

        for index, clip in enumerate(clips, start=1):
            final_clip = self._resolve_clip_file(clip, report)
            if final_clip is None:
                continue

            clip = dict(clip)
            clip["final_clip"] = str(final_clip)

            card = ttk.LabelFrame(
                self.results_canvas,
                text=f"Clip {index} - score {clip.get('score', 0)}/100 ({clip.get('quality_tier', quality_tier(clip))})",
                padding=10,
            )
            card.pack(fill="x", pady=(0, 10))

            badges = summarize_enhancements(clip)
            if badges:
                ttk.Label(card, text=f"Applied: {', '.join(badges)}", wraplength=900).pack(anchor=W, pady=(0, 4))

            tier = clip.get("quality_tier") or quality_tier(clip)
            if tier == "review_recommended":
                ttk.Label(
                    card,
                    text="Review recommended — lower-confidence moment selected by fallback scoring.",
                    wraplength=900,
                ).pack(anchor=W, pady=(0, 4))
            elif tier == "fallback" or clip.get("selection_mode", "").startswith("fallback") or report.get("used_fallback"):
                ttk.Label(
                    card,
                    text="Fallback clip — generated automatically when no strong highlights were found.",
                    wraplength=900,
                ).pack(anchor=W, pady=(0, 4))

            ttk.Label(card, text=f"File: {final_clip.name}").pack(anchor=W)
            ttk.Label(card, text=f"Hook: {clip.get('hook_text', '')}", font=("Arial", 11, "bold")).pack(anchor=W)
            ttk.Label(card, text=f"Caption: {clip.get('caption_text', '')}", wraplength=900).pack(anchor=W, pady=(4, 0))
            ttk.Label(card, text=f"Categories: {', '.join(clip.get('categories', [])) or 'none'}").pack(anchor=W)
            if clip.get("start") or clip.get("end"):
                ttk.Label(card, text=f"Moment: {clip.get('start')}s to {clip.get('end')}s").pack(anchor=W)

            buttons = ttk.Frame(card)
            buttons.pack(fill="x", pady=(8, 0))
            ttk.Button(buttons, text="Play clip", command=lambda p=final_clip: open_path(p)).pack(side=LEFT)
            ttk.Button(buttons, text="Open folder", command=lambda p=final_clip: open_path(p.parent)).pack(
                side=LEFT,
                padx=8,
            )
            ttk.Button(buttons, text="Export copy...", command=lambda p=final_clip: export_clip(p)).pack(side=LEFT)
            ttk.Button(buttons, text="Copy caption", command=lambda c=clip: self.copy_caption(c)).pack(side=LEFT, padx=8)
            ttk.Button(
                buttons,
                text="Copy social post",
                command=lambda c=clip: self.copy_social_caption(c),
            ).pack(side=LEFT)
            if self.social_manager.is_enabled():
                post_row = ttk.Frame(card)
                post_row.pack(fill="x", pady=(6, 0))
                ttk.Label(post_row, text="Post to:").pack(side=LEFT)
                for platform, label in (
                    ("youtube", "YouTube"),
                    ("tiktok", "TikTok"),
                    ("instagram", "Reels"),
                ):
                    ttk.Button(
                        post_row,
                        text=label,
                        command=lambda p=platform, c=clip, path=final_clip: self.post_clip(p, c, path),
                    ).pack(side=LEFT, padx=(8, 0))
            if clip.get("source_frame") and Path(str(clip.get("source_frame"))).exists():
                ttk.Button(
                    buttons,
                    text="Preview frame",
                    command=lambda c=clip: self.preview_frame(c),
                ).pack(side=LEFT, padx=8)

        self._refresh_results_canvas()

    def _refresh_results_canvas(self) -> None:
        self.results_canvas.update_idletasks()
        self.results_canvas_widget.configure(scrollregion=self.results_canvas_widget.bbox("all"))

    def copy_caption(self, clip: dict) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(clip.get("caption_text", ""))
        self.status_var.set("Caption copied.")

    def copy_social_caption(self, clip: dict) -> None:
        text = clip.get("social_caption") or clip.get("caption_text") or ""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Social caption copied.")

    def _refresh_social_status(self) -> None:
        if not self.social_manager.storage_ready():
            message = "Secure storage unavailable — connect disabled"
            for platform in self.social_status_vars:
                self.social_status_vars[platform].set(message)
            return

        statuses = self.social_manager.platform_status()
        for platform, status in statuses.items():
            if not status.configured:
                text = f"Not configured — {status.message}"
            elif status.connected:
                label = status.account_label or platform.title()
                text = f"Connected ({label})"
            else:
                text = status.message or "Not connected"
            self.social_status_vars[platform].set(text)

    def connect_platform(self, platform: str) -> None:
        if not self.social_manager.storage_ready():
            messagebox.showerror(
                APP_TITLE,
                "Secure token storage is unavailable on this system. "
                "Install a supported OS keychain backend before connecting accounts.",
            )
            return

        self.status_var.set(f"Opening browser to connect {platform.title()}...")
        thread = threading.Thread(target=self._connect_platform_worker, args=(platform,), daemon=True)
        thread.start()

    def _connect_platform_worker(self, platform: str) -> None:
        try:
            status = self.social_manager.connect(platform)
            self.root.after(0, lambda: self._on_connect_finished(platform, status, None))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._on_connect_finished(platform, None, exc))

    def _on_connect_finished(self, platform: str, status, error: Exception | None) -> None:
        self._refresh_social_status()
        if error:
            messagebox.showerror(APP_TITLE, f"Could not connect {platform.title()}:\n{error}")
            self.status_var.set(f"{platform.title()} connection failed.")
            return
        messagebox.showinfo(APP_TITLE, f"{platform.title()} connected successfully.")
        self.status_var.set(f"{platform.title()} connected.")

    def disconnect_platform(self, platform: str) -> None:
        if not messagebox.askyesno(
            APP_TITLE,
            f"Disconnect {platform.title()}?\n\nStored tokens will be removed from secure storage.",
        ):
            return
        try:
            self.social_manager.disconnect(platform)
            self._refresh_social_status()
            self.status_var.set(f"{platform.title()} disconnected.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Could not disconnect {platform.title()}:\n{exc}")

    def post_clip(self, platform: str, clip: dict, video_path: Path) -> None:
        if not self.social_manager.is_enabled():
            messagebox.showinfo(
                APP_TITLE,
                "Direct publishing is disabled. Enable social_publish.enabled and "
                "rollout.optional_features.direct_publish in config.json.",
            )
            return

        status = self.social_manager.platform_status().get(platform)
        if not status or not status.connected:
            messagebox.showinfo(APP_TITLE, f"Connect {platform.title()} before posting.")
            return

        title = str(clip.get("hook_text") or clip.get("caption_text") or video_path.stem)
        description = str(clip.get("social_caption") or clip.get("caption_text") or title)
        privacy = self.social_manager.default_privacy(platform)
        platform_label = {"youtube": "YouTube Shorts", "tiktok": "TikTok", "instagram": "Instagram Reels"}.get(
            platform,
            platform.title(),
        )

        confirmed = messagebox.askyesno(
            APP_TITLE,
            (
                f"Post this clip to {platform_label}?\n\n"
                f"File: {video_path.name}\n"
                f"Title: {title[:80]}\n"
                f"Privacy: {privacy}\n\n"
                "This will upload the video using your connected account."
            ),
        )
        if not confirmed:
            return

        self.status_var.set(f"Posting to {platform_label}...")
        thread = threading.Thread(
            target=self._post_clip_worker,
            args=(platform, video_path, title, description, privacy),
            daemon=True,
        )
        thread.start()

    def _post_clip_worker(
        self,
        platform: str,
        video_path: Path,
        title: str,
        description: str,
        privacy: str,
    ) -> None:
        try:
            result = self.social_manager.publish_clip(
                platform,
                video_path,
                title=title,
                description=description,
                privacy=privacy,
                user_confirmed=True,
            )
            self.root.after(0, lambda: self._on_post_finished(platform, result, None))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._on_post_finished(platform, None, exc))

    def _on_post_finished(self, platform: str, result, error: Exception | None) -> None:
        if error:
            messagebox.showerror(APP_TITLE, f"Post to {platform.title()} failed:\n{error}")
            self.status_var.set(f"{platform.title()} post failed.")
            return
        if result.ok:
            extra = f"\n\nURL: {result.video_url}" if result.video_url else ""
            messagebox.showinfo(APP_TITLE, f"{result.message}{extra}")
            self.status_var.set(f"Posted to {platform.title()}.")
        else:
            messagebox.showwarning(APP_TITLE, result.message)
            self.status_var.set(result.message)

    def _agent_status_text(self) -> str:
        if not self.agent_advisor.is_enabled():
            return "Assistant disabled — enable embedded_agent in config.json to activate."
        provider = self.agent_advisor.settings.provider
        has_key = bool(self.agent_advisor.settings.openai_api_key or self.agent_advisor.settings.anthropic_api_key)
        mode = "AI-powered" if has_key else "local fallback (add OPENAI_API_KEY for full responses)"
        return f"Assistant ready ({mode}, provider={provider})."

    def _ui_settings_snapshot(self) -> dict[str, str]:
        return {
            "vision_provider": self.provider_var.get(),
            "max_clips": self.max_clips_var.get(),
            "min_score": self.min_score_var.get(),
            "platform_preset": self.platform_var.get(),
            "game_profile": self.game_profile_var.get(),
            "smart_reframe": self.smart_reframe_var.get(),
        }

    def _agent_tool_approval(self, tool_name: str, arguments: dict) -> bool:
        if tool_name == "suggest_settings":
            return messagebox.askyesno(
                APP_TITLE,
                "The assistant wants to analyze your settings and suggest improvements.\n\nAllow this?",
            )
        return messagebox.askyesno(
            APP_TITLE,
            f"Allow assistant tool: {tool_name}?",
        )

    def _append_agent_message(self, role: str, content: str) -> None:
        self.agent_chat.configure(state="normal")
        prefix = "You: " if role == "user" else "Assistant: "
        self.agent_chat.insert(END, f"{prefix}{content}\n\n")
        self.agent_chat.configure(state="disabled")
        self.agent_chat.see(END)

    def agent_clear_chat(self) -> None:
        self.agent_advisor.clear_conversation()
        self.agent_chat.configure(state="normal")
        self.agent_chat.delete("1.0", END)
        self.agent_chat.configure(state="disabled")
        self.status_var.set("Assistant chat cleared.")

    def agent_send_message(self) -> None:
        message = self.agent_input_var.get().strip()
        if not message:
            return
        if not self.agent_advisor.is_enabled():
            messagebox.showinfo(
                APP_TITLE,
                "Assistant is disabled. Enable embedded_agent.enabled and "
                "rollout.optional_features.embedded_agent in config.json.",
            )
            return
        self.agent_input_var.set("")
        self._append_agent_message("user", message)
        self.agent_status_var.set("Assistant thinking...")
        thread = threading.Thread(target=self._agent_worker, args=(message,), daemon=True)
        thread.start()

    def agent_quick_prompt(self, prompt_key: str) -> None:
        if not self.agent_advisor.is_enabled():
            messagebox.showinfo(APP_TITLE, "Enable embedded_agent in config.json first.")
            return
        prompt = self.agent_advisor.QUICK_PROMPTS.get(prompt_key, "")
        if not prompt:
            return
        self.agent_input_var.set(prompt)
        self.agent_send_message()

    def _agent_worker(self, message: str) -> None:
        try:
            self.agent_advisor.update_context(
                report=self.report,
                ui_settings=self._ui_settings_snapshot(),
            )
            result = self.agent_advisor.ask(message)
            self.root.after(0, lambda: self._on_agent_response(result, None))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._on_agent_response(None, exc))

    def _on_agent_response(self, result: dict | None, error: Exception | None) -> None:
        self.agent_status_var.set(self._agent_status_text())
        if error:
            self._append_agent_message("assistant", f"Error: {error}")
            return
        content = str((result or {}).get("content") or "No response.")
        self._append_agent_message("assistant", content)
        suggestions: list[dict[str, str]] = []
        for item in (result or {}).get("tool_results") or []:
            if item.get("tool") == "suggest_settings":
                suggestions.extend((item.get("result") or {}).get("suggestions") or [])
        if suggestions and messagebox.askyesno(
            APP_TITLE,
            f"The assistant found {len(suggestions)} setting suggestion(s).\n\nApply them to the UI controls?",
        ):
            self._apply_agent_suggestions(suggestions)

    def _apply_agent_suggestions(self, suggestions: list[dict[str, str]]) -> None:
        mapping = {
            "highlight_detection.min_score": ("min_score_var", str),
            "highlight_detection.max_clips": ("max_clips_var", str),
            "highlight_detection.game_profile": ("game_profile_var", str),
            "vision.provider": ("provider_var", str),
            "rendering.platform_preset": ("platform_var", str),
        }
        applied = 0
        for suggestion in suggestions:
            setting = suggestion.get("setting", "")
            suggested = str(suggestion.get("suggested", "")).split("/")[0].strip()
            attr = mapping.get(setting)
            if not attr or not suggested:
                continue
            var_name, _ = attr
            var = getattr(self, var_name, None)
            if var is not None:
                var.set(suggested.split()[0])
                applied += 1
        self.status_var.set(f"Applied {applied} assistant suggestion(s) to UI controls.")

    def copy_all_captions(self) -> None:
        report = self.report or {}
        clips = self._clips_for_display(report)
        if not clips:
            messagebox.showinfo(APP_TITLE, "Generate clips first.")
            return
        lines = []
        for index, clip in enumerate(clips, start=1):
            caption = clip.get("social_caption") or clip.get("caption_text") or ""
            if caption:
                lines.append(f"Clip {index}: {caption}")
        if not lines:
            messagebox.showinfo(APP_TITLE, "No captions available to copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n\n".join(lines))
        self.status_var.set(f"Copied {len(lines)} caption(s).")

    def export_all_clips(self) -> None:
        report = self.report or {}
        clips = self._clips_for_display(report)
        if not clips:
            messagebox.showinfo(APP_TITLE, "Generate clips first.")
            return

        destination = filedialog.askdirectory(title="Choose export folder for all clips")
        if not destination:
            return

        export_dir = Path(destination)
        export_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for clip in clips:
            source = self._resolve_clip_file(clip, report)
            if source is None or not source.exists():
                continue
            target = export_dir / source.name
            shutil.copyfile(source, target)
            copied += 1

        captions_path = export_dir / "captions.txt"
        caption_lines = []
        for index, clip in enumerate(clips, start=1):
            caption = clip.get("social_caption") or clip.get("caption_text") or ""
            if caption:
                caption_lines.append(f"Clip {index}: {caption}")
        if caption_lines:
            captions_path.write_text("\n\n".join(caption_lines), encoding="utf-8")

        messagebox.showinfo(APP_TITLE, f"Exported {copied} clip(s) to:\n{export_dir}")
        self.status_var.set(f"Exported {copied} clip(s).")

    def preview_frame(self, clip: dict) -> None:
        frame_path = clip.get("source_frame")
        if not frame_path:
            messagebox.showinfo(APP_TITLE, "No preview frame available for this clip.")
            return
        path = Path(str(frame_path))
        if not path.exists():
            messagebox.showinfo(APP_TITLE, "Preview frame file not found.")
            return
        open_path(path)

    def _reset_results_panel(self) -> None:
        self._clear_results(show_placeholder=True)

    def _clear_results(self, show_placeholder: bool = False) -> None:
        for child in self.results_canvas.winfo_children():
            child.destroy()
        if show_placeholder:
            ttk.Label(
                self.results_canvas,
                text="Generated clips will appear here with score, caption, and open/export buttons.",
                wraplength=900,
            ).pack(anchor=W)
        self._refresh_results_canvas()

    def _append_progress(self, text: str) -> None:
        self.progress_text.insert(END, text if text.endswith("\n") else text + "\n")
        self.progress_text.see(END)

    def _on_mousewheel(self, event) -> None:
        self.results_canvas_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _settings_override(self) -> dict:
        return {
            "vision": {
                "provider": self.provider_var.get(),
                "analysis_interval_seconds": int(self.interval_var.get()),
                "max_frames_to_analyze": int(self.max_frames_var.get()),
            },
            "rendering": {
                "platform_preset": self.platform_var.get(),
                "theme": self.theme_var.get(),
                "smart_reframe": {
                    "enabled": self.smart_reframe_var.get() == "on",
                },
            },
            "highlight_detection": {
                "max_clips": int(self.max_clips_var.get()),
                "min_score": int(self.min_score_var.get()),
                "game_profile": self.game_profile_var.get(),
            },
        }

    def _ocr_status(self) -> str:
        try:
            from scripts.ocr_utils import initialize_ocr

            status = initialize_ocr(load_config().get("ocr", {}))
            if status.get("available"):
                return f"Killfeed OCR ready: {status.get('tesseract_path')}"
            return (
                "Killfeed OCR not installed. Clips still generate without it. "
                "Install from https://github.com/UB-Mannheim/tesseract/wiki"
            )
        except Exception:  # noqa: BLE001
            return "Killfeed OCR status unknown. Clips still generate without it."

    def _initial_provider(self) -> str:
        try:
            return str(load_config().get("vision", {}).get("provider", "heuristic"))
        except Exception:  # noqa: BLE001
            return "heuristic"

    def _initial_platform_preset(self) -> str:
        try:
            return str(load_config().get("rendering", {}).get("platform_preset", "tiktok"))
        except Exception:  # noqa: BLE001
            return "tiktok"

    def _initial_theme(self) -> str:
        try:
            return str(load_config().get("rendering", {}).get("theme", "default"))
        except Exception:  # noqa: BLE001
            return "default"

    def _initial_game_profile(self) -> str:
        try:
            return str(load_config().get("highlight_detection", {}).get("game_profile", "generic"))
        except Exception:  # noqa: BLE001
            return "generic"

    def _initial_smart_reframe(self) -> str:
        try:
            enabled = bool(load_config().get("rendering", {}).get("smart_reframe", {}).get("enabled", False))
            return "on" if enabled else "off"
        except Exception:  # noqa: BLE001
            return "off"

    def _api_key_status(self) -> str:
        try:
            key_configured = bool(load_config().get("vision", {}).get("openai_api_key"))
        except Exception:  # noqa: BLE001
            key_configured = False

        if key_configured:
            return "OpenAI key is configured. You can paste a new key here to replace it."
        return "No OpenAI key saved yet. The app can still run in heuristic mode."


def export_clip(path: Path) -> None:
    if not path.exists():
        messagebox.showerror(APP_TITLE, f"Clip not found: {path}")
        return

    destination = filedialog.asksaveasfilename(
        title="Export clip",
        initialfile=path.name,
        defaultextension=".mp4",
        filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
    )
    if not destination:
        return

    shutil.copyfile(path, destination)
    messagebox.showinfo(APP_TITLE, f"Exported clip to:\n{destination}")


def open_path(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        messagebox.showerror(APP_TITLE, f"Path not found: {path}")
        return

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _add_packaged_bin_to_path() -> None:
    candidates = [
        Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "bin",
        Path(sys.executable).resolve().parent / "bin" if getattr(sys, "frozen", False) else PROJECT_ROOT / "bin",
    ]
    for bin_dir in candidates:
        if bin_dir.exists():
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def main() -> int:
    _add_packaged_bin_to_path()
    root = Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    GameplayAutoEditorApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
