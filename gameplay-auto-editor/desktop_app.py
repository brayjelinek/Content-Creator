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
from scripts.pipeline import PROJECT_ROOT, load_config, run_pipeline
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

        self._build_ui()
        self._poll_output_queue()

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
