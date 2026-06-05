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
from tkinter import BOTH, END, LEFT, RIGHT, VERTICAL, W, filedialog, messagebox
from tkinter import StringVar, Text, Tk
from tkinter import ttk

from scripts.pipeline import PROJECT_ROOT, load_config, run_pipeline


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

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.selected_video: Path | None = None
        self.report: dict | None = None

        self.provider_var = StringVar(value=self._initial_provider())
        self.max_clips_var = StringVar(value="5")
        self.min_score_var = StringVar(value="55")
        self.interval_var = StringVar(value="3")
        self.status_var = StringVar(value="Choose a gameplay video to begin.")
        self.openai_key_var = StringVar(value="")
        self.key_status_var = StringVar(value=self._api_key_status())

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
        self.file_label = ttk.Label(file_row, text="No video selected")
        self.file_label.pack(side=LEFT, padx=12)

        settings_row = ttk.Frame(controls)
        settings_row.pack(fill="x")
        self._add_combobox(settings_row, "Vision mode", self.provider_var, ["heuristic", "auto", "openai", "anthropic"])
        self._add_spinbox(settings_row, "Sample clips", self.max_clips_var, 1, 10)
        self._add_spinbox(settings_row, "Minimum score", self.min_score_var, 0, 100)
        self._add_spinbox(settings_row, "Analyze every N seconds", self.interval_var, 1, 10)

        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=(0, 12))
        self.generate_button = ttk.Button(action_row, text="Generate sample clips", command=self.generate_clips)
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

        progress = ttk.LabelFrame(outer, text="2. Progress", padding=10)
        progress.pack(fill="x", pady=(0, 12))
        self.progress_text = Text(progress, height=8, wrap="word")
        self.progress_text.pack(fill="x")

        results_outer = ttk.LabelFrame(outer, text="3. Review generated clips", padding=10)
        results_outer.pack(fill=BOTH, expand=True)
        self.results_canvas = ttk.Frame(results_outer)
        self.results_canvas.pack(fill=BOTH, expand=True)

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

    def generate_clips(self) -> None:
        if not self.selected_video:
            messagebox.showinfo(APP_TITLE, "Choose a gameplay video first.")
            return

        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            messagebox.showerror(
                APP_TITLE,
                "FFmpeg is required but was not found. Install FFmpeg, then reopen the app.",
            )
            return

        settings = self._settings_override()
        self.generate_button.configure(state="disabled")
        self.status_var.set("Generating clips. This can take a few minutes...")
        self.progress_text.delete("1.0", END)
        self._clear_results()

        thread = threading.Thread(target=self._run_generation_worker, args=(self.selected_video, settings), daemon=True)
        thread.start()

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

    def _run_generation_worker(self, video_path: Path, settings: dict) -> None:
        writer = QueueWriter(self.output_queue)
        try:
            with redirect_stdout(writer):
                report = run_pipeline(video_path, config_override=settings)
            self.output_queue.put(("DONE", report))
        except Exception as exc:  # noqa: BLE001 - show friendly UI errors.
            self.output_queue.put(("ERROR", f"{exc}\n\n{traceback.format_exc()}"))

    def _poll_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "DONE":
                    self._generation_done(item[1])
                elif isinstance(item, tuple) and item[0] == "ERROR":
                    self._generation_failed(item[1])
                else:
                    self._append_progress(str(item))
        except queue.Empty:
            pass

        self.root.after(200, self._poll_output_queue)

    def _generation_done(self, report: dict) -> None:
        self.report = report
        self.generate_button.configure(state="normal")
        self.status_var.set(f"Done. Created {report.get('clips_created', 0)} clip(s).")
        self._show_results(report)

    def _generation_failed(self, error_text: str) -> None:
        self.generate_button.configure(state="normal")
        self.status_var.set("Generation failed.")
        self._append_progress(error_text)
        messagebox.showerror(APP_TITLE, "Clip generation failed. See the progress box for details.")

    def _show_results(self, report: dict) -> None:
        self._clear_results()
        clips = report.get("clips", [])
        if not clips:
            ttk.Label(self.results_canvas, text="No clips were created. Try lowering the minimum score.").pack(anchor=W)
            return

        for index, clip in enumerate(clips, start=1):
            card = ttk.LabelFrame(
                self.results_canvas,
                text=f"Clip {index} - score {clip.get('score', 0)}/100",
                padding=10,
            )
            card.pack(fill="x", pady=(0, 10))

            ttk.Label(card, text=f"Hook: {clip.get('hook_text', '')}", font=("Arial", 11, "bold")).pack(anchor=W)
            ttk.Label(card, text=f"Caption: {clip.get('caption_text', '')}", wraplength=900).pack(anchor=W, pady=(4, 0))
            ttk.Label(card, text=f"Categories: {', '.join(clip.get('categories', [])) or 'none'}").pack(anchor=W)
            ttk.Label(card, text=f"Moment: {clip.get('start')}s to {clip.get('end')}s").pack(anchor=W)

            buttons = ttk.Frame(card)
            buttons.pack(fill="x", pady=(8, 0))
            final_clip = Path(clip["final_clip"])
            ttk.Button(buttons, text="Play clip", command=lambda p=final_clip: open_path(p)).pack(side=LEFT)
            ttk.Button(buttons, text="Open folder", command=lambda p=final_clip: open_path(p.parent)).pack(
                side=LEFT,
                padx=8,
            )
            ttk.Button(buttons, text="Export copy...", command=lambda p=final_clip: export_clip(p)).pack(side=LEFT)
            ttk.Button(buttons, text="Copy caption", command=lambda c=clip: self.copy_caption(c)).pack(side=LEFT, padx=8)

    def copy_caption(self, clip: dict) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(clip.get("caption_text", ""))
        self.status_var.set("Caption copied.")

    def _clear_results(self) -> None:
        for child in self.results_canvas.winfo_children():
            child.destroy()

    def _append_progress(self, text: str) -> None:
        self.progress_text.insert(END, text if text.endswith("\n") else text + "\n")
        self.progress_text.see(END)

    def _settings_override(self) -> dict:
        return {
            "vision": {
                "provider": self.provider_var.get(),
                "analysis_interval_seconds": int(self.interval_var.get()),
            },
            "highlight_detection": {
                "max_clips": int(self.max_clips_var.get()),
                "min_score": int(self.min_score_var.get()),
            },
        }

    def _initial_provider(self) -> str:
        try:
            return str(load_config().get("vision", {}).get("provider", "heuristic"))
        except Exception:  # noqa: BLE001
            return "heuristic"

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
