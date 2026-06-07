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
from tkinter import BOTH, END, LEFT, RIGHT, W, X, Y, BOTTOM, TOP, Canvas, filedialog, messagebox
from tkinter import DoubleVar, StringVar, Text, Tk
from tkinter import ttk
import tkinter as tk

from scripts.clip_metadata import format_virality_subscores, quality_tier, summarize_enhancements
from scripts.embedded_agent.advisor import EmbeddedAgentAdvisor
from scripts.pipeline import PROJECT_ROOT, load_config, run_pipeline
from scripts.pipeline_control import PipelineCancelled, get_pipeline_control, reset_pipeline_control
from scripts.user_config import patch_user_config
from scripts.social_publish.manager import SocialPublishManager
from scripts.ui_logging import LogRateLimiter, attach_ui_log_handler, detach_ui_log_handler
from scripts.ui_theme import AppTheme
from scripts import ui_copy as copy
from scripts.subprocess_utils import popen_quiet
from scripts.ui_components import (
    ClipsPanel,
    EmptyState,
    FormField,
    ModernInput,
    ScrollablePanel,
    SectionCard,
    ShimmerPlaceholder,
    SmoothProgressAnimator,
    StepStrip,
    create_button,
    create_input,
)


APP_TITLE = copy.APP_DISPLAY_NAME


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
        self.root.geometry("1280x820")
        self.root.minsize(1024, 700)
        self.theme = AppTheme.apply(self.root)
        self.copilot_visible = True
        self.advanced_visible = True
        self.integrations_visible = True
        self.workflow_step = 1
        self._log_rate_limiter = LogRateLimiter(interval_seconds=1.5)
        self._shimmer: ShimmerPlaceholder | None = None
        self._progress_animator: SmoothProgressAnimator | None = None

        self.output_queue: queue.Queue = queue.Queue()
        self.selected_video: Path | None = None
        self.report: dict | None = None
        self.progress_var = DoubleVar(value=0.0)
        self.stage_var = StringVar(value=copy.STATUS_IDLE)

        self.provider_var = StringVar(value=self._initial_provider())
        self.max_clips_var = StringVar(value=self._initial_max_clips())
        self.min_score_var = StringVar(value=self._initial_min_score())
        self.interval_var = StringVar(value=self._initial_scan_interval())
        self.max_frames_var = StringVar(value=self._initial_max_frames())
        self.platform_var = StringVar(value=self._initial_platform_preset())
        self.theme_var = StringVar(value=self._initial_theme())
        self.game_profile_var = StringVar(value=self._initial_game_profile())
        self.smart_reframe_var = StringVar(value=self._initial_smart_reframe())
        self.rollout_phase_var = StringVar(value=self._initial_rollout_phase())
        self.rollout_phase_hint_var = StringVar(value=self._rollout_phase_summary())
        self.clip_prompt_var = StringVar(value=self._initial_clip_prompt())
        self.chat_log_path_var = StringVar(value=self._initial_chat_log_path())
        self.chat_log_status_var = StringVar(value=self._chat_log_status_text())
        self.status_var = StringVar(value=copy.STATUS_IDLE)
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
        self.root.after_idle(self._finalize_card_layout)
        self.root.after(150, self._finalize_card_layout)

    def _finalize_card_layout(self) -> None:
        """Re-measure cards after all child widgets are attached."""
        from scripts.ui_components import SectionCard

        def walk(widget: tk.Misc) -> None:
            if isinstance(widget, SectionCard):
                widget._sync_content_size()
            for child in widget.winfo_children():
                walk(child)

        walk(self.root)
        self.root.update_idletasks()
        if hasattr(self, "workflow_scroll"):
            self.workflow_scroll.refresh()

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=(AppTheme.SPACING_LG, AppTheme.SPACING_MD))
        shell.pack(fill=BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        top = ttk.Frame(shell)
        top.grid(row=0, column=0, sticky="ew", pady=(0, AppTheme.SPACING_MD))
        title_block = ttk.Frame(top)
        title_block.pack(side=LEFT, fill="x", expand=True)
        ttk.Label(title_block, text=APP_TITLE, style="Title.TLabel").pack(anchor=W)
        ttk.Label(title_block, text=copy.HERO_SUBLINE, style="Subtitle.TLabel").pack(
            anchor=W, pady=(AppTheme.SPACING_XS, 0)
        )

        top_actions = ttk.Frame(top)
        top_actions.pack(side=RIGHT)
        self.copilot_toggle_btn = create_button(
            top_actions,
            copy.BTN_HIDE_ASSISTANT,
            style="Ghost.TButton",
            command=self.toggle_copilot_panel,
        )
        self.copilot_toggle_btn.pack(side=RIGHT, padx=(AppTheme.SPACING_SM, 0))
        ttk.Label(top_actions, textvariable=self.status_var, style="Muted.TLabel").pack(side=RIGHT)

        self.main_pane = tk.PanedWindow(
            shell,
            orient=tk.HORIZONTAL,
            sashwidth=4,
            sashrelief=tk.FLAT,
            bg=AppTheme.BORDER,
            bd=0,
        )
        self.main_pane.grid(row=1, column=0, sticky="nsew")

        self.left_panel = ttk.Frame(self.main_pane, style="Surface.TFrame", padding=AppTheme.SPACING_MD)
        self.main_pane.add(self.left_panel, minsize=640)

        self._build_workflow_panel(self.left_panel)

        self.copilot_panel = ttk.Frame(self.main_pane, style="Copilot.TFrame", width=360)
        self.main_pane.add(self.copilot_panel, minsize=320)
        self._build_copilot_panel(self.copilot_panel)

        self._progress_animator = SmoothProgressAnimator(self.root, self.progress_var)

    def _build_workflow_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=0)

        self.workflow_scroll = ScrollablePanel(parent)
        self.workflow_scroll.grid(row=0, column=0, sticky="nsew")
        workflow = self.workflow_scroll.body
        workflow.columnconfigure(0, weight=1)
        workflow.columnconfigure(1, weight=1)

        steps_card = SectionCard(workflow, padding=AppTheme.SPACING_MD, shadow="subtle")
        steps_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_MD))
        self.step_strip = StepStrip(steps_card.content, [copy.STEP_PICK, copy.STEP_CREATE, copy.STEP_REVIEW])
        self.step_strip.pack(fill="x")
        self.step_labels = self.step_strip.labels

        hero_card = SectionCard(
            workflow,
            title=copy.HERO_HEADLINE,
            padding=AppTheme.SPACING_LG,
        )
        hero_card.grid(row=1, column=0, sticky="nsew", padx=(0, AppTheme.SPACING_SM), pady=(0, AppTheme.SPACING_MD))

        file_row = ttk.Frame(hero_card.content, style="CardSurface.TFrame")
        file_row.pack(fill="x")
        create_button(file_row, copy.BTN_SELECT_VIDEO, style="Secondary.TButton", icon="▶", command=self.choose_video).pack(
            side=LEFT
        )
        create_button(
            file_row,
            copy.BTN_ADD_QUEUE,
            style="Ghost.TButton",
            icon="+",
            command=self.add_to_queue,
        ).pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))
        create_button(
            file_row,
            copy.BTN_CLEAR_QUEUE,
            style="Ghost.TButton",
            command=self.clear_queue,
        ).pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))
        self.file_label = ttk.Label(file_row, text=copy.MSG_CLIP_READY, style="Caption.TLabel")
        self.file_label.pack(side=LEFT, padx=(AppTheme.SPACING_MD, 0))

        queue_row = ttk.Frame(hero_card.content, style="CardSurface.TFrame")
        queue_row.pack(fill="x", pady=(AppTheme.SPACING_MD, 0))
        ttk.Label(queue_row, text="Batch queue", style="Caption.TLabel").pack(anchor=W)
        self.queue_listbox = ttk.Treeview(queue_row, columns=("video",), show="headings", height=2)
        self.queue_listbox.heading("video", text="Videos waiting to process")
        self.queue_listbox.column("video", width=420, stretch=True)
        self.queue_listbox.pack(fill="x", pady=(AppTheme.SPACING_XS, 0))

        settings_card = SectionCard(workflow, title=copy.SECTION_CLIP_SETTINGS, padding=AppTheme.SPACING_LG)
        settings_card.grid(row=1, column=1, sticky="nsew", padx=(AppTheme.SPACING_SM, 0), pady=(0, AppTheme.SPACING_MD))

        settings_header = ttk.Frame(settings_card.content, style="CardSurface.TFrame")
        settings_header.pack(fill="x", pady=(0, AppTheme.SPACING_SM))
        self.advanced_toggle_btn = create_button(
            settings_header,
            copy.BTN_HIDE_ADVANCED,
            style="Ghost.TButton",
            command=self.toggle_advanced_settings,
        )
        self.advanced_toggle_btn.pack(side=RIGHT)

        settings_grid = ttk.Frame(settings_card.content, style="CardSurface.TFrame")
        settings_grid.pack(fill="x")
        settings_grid.columnconfigure(0, weight=1)
        settings_grid.columnconfigure(1, weight=1)
        self._add_combobox_grid(settings_grid, 0, 0, copy.LBL_DETECTION, self.provider_var, list(copy.DETECTION_LABEL_TO_VALUE))
        self._add_spinbox_grid(settings_grid, 0, 1, copy.LBL_CLIP_COUNT, self.max_clips_var, 1, 10)
        self._add_spinbox_grid(settings_grid, 1, 0, copy.LBL_SENSITIVITY, self.min_score_var, 0, 100)
        self._add_combobox_grid(settings_grid, 1, 1, copy.LBL_EXPORT_FOR, self.platform_var, list(copy.PLATFORM_LABEL_TO_VALUE))
        self._add_combobox_grid(
            settings_grid,
            2,
            0,
            copy.LBL_ROLLOUT_PHASE,
            self.rollout_phase_var,
            list(copy.ROLLOUT_PHASE_LABEL_TO_VALUE),
            command=self._on_rollout_phase_changed,
        )
        ttk.Label(
            settings_grid,
            textvariable=self.rollout_phase_hint_var,
            style="Caption.TLabel",
            wraplength=420,
        ).grid(row=2, column=1, sticky="w", padx=(AppTheme.SPACING_SM, 0), pady=(AppTheme.SPACING_XS, 0))
        self._add_combobox_grid(settings_grid, 3, 0, copy.LBL_GAME, self.game_profile_var, list(copy.GAME_LABEL_TO_VALUE))
        prompt_field = FormField(settings_grid, copy.LBL_CLIP_PROMPT)
        prompt_field.attach(create_input(prompt_field, textvariable=self.clip_prompt_var, width=28))
        prompt_field.grid(row=3, column=1, sticky="ew", padx=(AppTheme.SPACING_SM, 0), pady=(0, AppTheme.SPACING_SM))

        self.advanced_settings = ttk.Frame(settings_card.content, style="CardSurface.TFrame")
        self._add_combobox_grid(self.advanced_settings, 0, 0, copy.LBL_LOOK, self.theme_var, list(copy.THEME_LABEL_TO_VALUE))
        self._add_combobox_grid(self.advanced_settings, 0, 1, copy.LBL_FACECAM, self.smart_reframe_var, list(copy.REFRAME_LABEL_TO_VALUE))
        self._add_spinbox_grid(self.advanced_settings, 1, 0, copy.LBL_SCAN_EVERY, self.interval_var, 1, 10)
        self._add_spinbox_grid(self.advanced_settings, 1, 1, copy.LBL_AI_FRAMES, self.max_frames_var, 1, 40)
        self.advanced_settings.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(AppTheme.SPACING_SM, 0))
        self.advanced_settings.columnconfigure(0, weight=1)
        self.advanced_settings.columnconfigure(1, weight=1)

        create_card = SectionCard(workflow, title=copy.SECTION_CREATE, padding=AppTheme.SPACING_MD, shadow="subtle")
        create_card.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_SM))
        create_row = ttk.Frame(create_card.content, style="CardSurface.TFrame")
        create_row.pack(fill="x")
        self.generate_button = create_button(
            create_row,
            copy.BTN_CREATE_CLIPS,
            style="Primary.TButton",
            icon="✨",
            command=self.generate_clips,
        )
        self.generate_button.pack(side=LEFT)
        self.cancel_button = create_button(
            create_row,
            copy.BTN_CANCEL,
            style="Ghost.TButton",
            command=self.cancel_generation,
        )
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))
        ttk.Label(
            create_row,
            text="Cancel stops after the current pipeline step.",
            style="Caption.TLabel",
        ).pack(side=LEFT, padx=(AppTheme.SPACING_MD, 0))

        export_card = SectionCard(workflow, title=copy.SECTION_EXPORT, padding=AppTheme.SPACING_MD, shadow="subtle")
        export_card.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_SM))
        export_row = ttk.Frame(export_card.content, style="CardSurface.TFrame")
        export_row.pack(fill="x")
        self.export_folder_btn = create_button(
            export_row,
            copy.BTN_OPEN_FOLDER,
            style="Secondary.TButton",
            icon="📁",
            command=lambda: open_path(PROJECT_ROOT / "final_clips"),
        )
        self.export_folder_btn.pack(side=LEFT)
        self.export_all_btn = create_button(
            export_row,
            copy.BTN_SAVE_ALL,
            style="Ghost.TButton",
            command=self.export_all_clips,
        )
        self.export_all_btn.pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))
        self.export_captions_btn = create_button(
            export_row,
            copy.BTN_COPY_CAPTIONS,
            style="Ghost.TButton",
            command=self.copy_all_captions,
        )
        self.export_captions_btn.pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))
        ttk.Label(
            export_row,
            text="Use per-clip Play / Save / Copy buttons in the list below.",
            style="Caption.TLabel",
        ).pack(side=LEFT, padx=(AppTheme.SPACING_MD, 0))
        self._set_export_actions_enabled(False)

        tools_header = ttk.Frame(workflow, style="Surface.TFrame")
        tools_header.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_XS))
        ttk.Label(tools_header, text=copy.SECTION_TOOLS, style="H6.TLabel").pack(side=LEFT)
        self.integrations_toggle_btn = create_button(
            tools_header,
            copy.BTN_HIDE_INTEGRATIONS,
            style="Ghost.TButton",
            command=self.toggle_integrations,
        )
        self.integrations_toggle_btn.pack(side=RIGHT)

        self.clips_panel = ClipsPanel(workflow, title=copy.SECTION_YOUR_CLIPS, min_height=220)
        self.clips_panel.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_MD))
        ttk.Label(
            workflow,
            text=copy.EMPTY_STATE_HINT,
            style="Caption.TLabel",
            wraplength=760,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, AppTheme.SPACING_XS))
        self.clips_panel.bind_mousewheel(self._on_clips_mousewheel)
        self.results_canvas = self.clips_panel.body
        self.results_canvas_widget = self.clips_panel.canvas
        self.results_scrollbar = self.clips_panel.scrollbar
        self._show_empty_clips_state()

        self.integrations_card = SectionCard(workflow, title=copy.SECTION_TOOLS, padding=AppTheme.SPACING_MD, shadow="subtle")
        self.integrations_card.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_MD))
        integrations = ttk.Notebook(self.integrations_card.content)
        integrations.pack(fill="x")
        self._build_integrations_tabs(integrations)

        progress_shell = ttk.Frame(parent, style="Surface.TFrame")
        progress_shell.grid(row=1, column=0, sticky="ew", pady=(AppTheme.SPACING_SM, 0))
        progress_card = SectionCard(progress_shell, title=copy.SECTION_CREATING, padding=AppTheme.SPACING_MD, shadow="medium")
        progress_card.pack(fill="x")
        self.progress_bar = ttk.Progressbar(progress_card.content, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, AppTheme.SPACING_SM))
        ttk.Label(progress_card.content, textvariable=self.stage_var, style="Caption.TLabel").pack(anchor=W, pady=(0, AppTheme.SPACING_XS))
        self.progress_text = Text(progress_card.content, height=3, wrap="word")
        AppTheme.configure_text_widget(self.progress_text, mono=True)
        self.progress_text.pack(fill="x")
        self.progress_card = progress_card

    def _build_integrations_tabs(self, notebook: ttk.Notebook) -> None:
        social_tab = ttk.Frame(notebook, style="CardSurface.TFrame", padding=AppTheme.SPACING_MD)
        notebook.add(social_tab, text=copy.TAB_SHARE)
        self.social_frame = social_tab
        ttk.Label(
            social_tab,
            text=copy.TAB_SHARE_HELP,
            style="Caption.TLabel",
            wraplength=560,
        ).pack(anchor=W, pady=(0, AppTheme.SPACING_MD))

        for platform, label in (
            ("youtube", "YouTube Shorts"),
            ("tiktok", "TikTok"),
            ("instagram", "Instagram Reels"),
        ):
            row = SectionCard(social_tab, padding=AppTheme.SPACING_MD, shadow="subtle")
            row.pack(fill="x", pady=(0, AppTheme.SPACING_SM))
            header = ttk.Frame(row.content, style="CardSurface.TFrame")
            header.pack(fill="x")
            ttk.Label(header, text=label, style="H6.TLabel").pack(side=LEFT)
            ttk.Label(
                header,
                textvariable=self.social_status_vars[platform],
                style="CardMuted.TLabel",
                wraplength=280,
            ).pack(side=LEFT, padx=(AppTheme.SPACING_MD, 0), fill="x", expand=True)
            actions = ttk.Frame(row.content, style="CardSurface.TFrame")
            actions.pack(fill="x", pady=(AppTheme.SPACING_SM, 0))
            create_button(
                actions,
                "Connect",
                style="Primary.TButton",
                icon="🔗",
                command=lambda p=platform: self.connect_platform(p),
            ).pack(side=LEFT)
            create_button(
                actions,
                "Disconnect",
                style="Ghost.TButton",
                command=lambda p=platform: self.disconnect_platform(p),
            ).pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))

        api_tab = ttk.Frame(notebook, style="CardSurface.TFrame", padding=AppTheme.SPACING_MD)
        notebook.add(api_tab, text=copy.TAB_SMARTER)
        ttk.Label(api_tab, textvariable=self.key_status_var, style="Caption.TLabel", wraplength=560).pack(
            anchor=W, pady=(0, AppTheme.SPACING_MD)
        )
        api_field = ModernInput(
            api_tab,
            "OpenAI API key",
            textvariable=self.openai_key_var,
            show="*",
            width=42,
        )
        api_field.pack(fill="x", pady=(0, AppTheme.SPACING_SM))
        create_button(api_tab, "Save key", style="Primary.TButton", icon="💾", command=self.save_openai_key).pack(
            anchor=W, pady=(0, AppTheme.SPACING_MD)
        )

        ttk.Label(api_tab, text=copy.LBL_CHAT_LOG, style="H6.TLabel").pack(anchor=W)
        ttk.Label(api_tab, textvariable=self.chat_log_status_var, style="Caption.TLabel", wraplength=560).pack(
            anchor=W, pady=(AppTheme.SPACING_XS, AppTheme.SPACING_SM)
        )
        chat_field = ModernInput(
            api_tab,
            "Chat log file",
            textvariable=self.chat_log_path_var,
            width=42,
        )
        chat_field.pack(fill="x", pady=(0, AppTheme.SPACING_SM))
        chat_actions = ttk.Frame(api_tab, style="CardSurface.TFrame")
        chat_actions.pack(fill="x")
        create_button(
            chat_actions,
            copy.BTN_BROWSE_CHAT_LOG,
            style="Secondary.TButton",
            command=self.choose_chat_log,
        ).pack(side=LEFT)
        create_button(
            chat_actions,
            copy.BTN_SAVE_CHAT_LOG,
            style="Primary.TButton",
            command=self.save_chat_log_path,
        ).pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))
        create_button(
            chat_actions,
            copy.BTN_CLEAR_CHAT_LOG,
            style="Ghost.TButton",
            command=self.clear_chat_log_path,
        ).pack(side=LEFT, padx=(AppTheme.SPACING_SM, 0))

        ocr_tab = ttk.Frame(notebook, style="CardSurface.TFrame", padding=AppTheme.SPACING_MD)
        notebook.add(ocr_tab, text=copy.TAB_KILLFEED)
        ttk.Label(ocr_tab, textvariable=self.ocr_status_var, style="Caption.TLabel", wraplength=560).pack(anchor=W)
        ttk.Label(
            ocr_tab,
            text="Install Tesseract for killfeed OCR: https://github.com/UB-Mannheim/tesseract/wiki",
            style="CardMuted.TLabel",
            wraplength=560,
        ).pack(anchor=W, pady=(AppTheme.SPACING_SM, 0))

    def _build_copilot_panel(self, parent: ttk.Frame) -> None:
        parent.pack_propagate(False)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        card = SectionCard(parent, title=copy.ASSISTANT_TITLE, subtitle=copy.ASSISTANT_TAGLINE, padding=AppTheme.SPACING_LG)
        card.pack(fill=BOTH, expand=True, padx=AppTheme.SPACING_SM, pady=AppTheme.SPACING_SM)
        ttk.Label(card.content, textvariable=self.agent_status_var, style="Caption.TLabel", wraplength=300).pack(
            anchor=W, pady=(0, AppTheme.SPACING_SM)
        )

        chips = ttk.Frame(card.content, style="CardSurface.TFrame")
        chips.pack(fill="x", pady=(0, AppTheme.SPACING_SM))
        for label, key in (
            (copy.CHIP_EXPLAIN, "explain_clips"),
            (copy.CHIP_SETUP, "help_setup"),
            (copy.CHIP_SETTINGS, "suggest_settings"),
            (copy.CHIP_POST, "posting_strategy"),
        ):
            create_button(chips, label, style="Chip.TButton", command=lambda k=key: self.agent_quick_prompt(k)).pack(
                side=LEFT, padx=(0, AppTheme.SPACING_XS), pady=(0, AppTheme.SPACING_XS)
            )

        chat_wrap = ttk.Frame(card.content, style="CardSurface.TFrame")
        chat_wrap.pack(fill=BOTH, expand=True)
        self.agent_chat = Text(chat_wrap, wrap="word", state="disabled")
        AppTheme.configure_copilot_chat(self.agent_chat)
        self.agent_chat.pack(fill=BOTH, expand=True)
        self._append_agent_system_welcome()

        composer = ttk.Frame(card.content, style="CardSurface.TFrame")
        composer.pack(fill="x", pady=(AppTheme.SPACING_SM, 0))
        self.agent_entry = create_input(composer, textvariable=self.agent_input_var, style="Copilot.TEntry", width=40)
        self.agent_entry.pack(fill="x")
        self.agent_entry.bind("<Return>", lambda _event: self.agent_send_message())
        create_button(composer, copy.BTN_ASK, style="Primary.TButton", command=self.agent_send_message).pack(
            fill="x", pady=(AppTheme.SPACING_SM, 0)
        )
        create_button(composer, copy.BTN_CLEAR_CHAT, style="Ghost.TButton", command=self.agent_clear_chat).pack(
            fill="x", pady=(AppTheme.SPACING_XS, 0)
        )

    def toggle_copilot_panel(self) -> None:
        if self.copilot_visible:
            self.main_pane.forget(self.copilot_panel)
            self.copilot_visible = False
            self.copilot_toggle_btn.configure(text=copy.BTN_SHOW_ASSISTANT)
        else:
            self.main_pane.add(self.copilot_panel, minsize=320)
            self.copilot_visible = True
            self.copilot_toggle_btn.configure(text=copy.BTN_HIDE_ASSISTANT)

    def toggle_advanced_settings(self) -> None:
        if self.advanced_visible:
            self.advanced_settings.grid_remove()
            self.advanced_visible = False
            self.advanced_toggle_btn.configure(text=copy.BTN_SHOW_ADVANCED)
        else:
            self.advanced_settings.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(AppTheme.SPACING_SM, 0))
            self.advanced_settings.columnconfigure(0, weight=1)
            self.advanced_settings.columnconfigure(1, weight=1)
            self.advanced_visible = True
            self.advanced_toggle_btn.configure(text=copy.BTN_HIDE_ADVANCED)
        self._finalize_card_layout()

    def toggle_integrations(self) -> None:
        if self.integrations_visible:
            self.integrations_card.grid_remove()
            self.integrations_visible = False
            self.integrations_toggle_btn.configure(text=copy.BTN_SHOW_INTEGRATIONS)
        else:
            self.integrations_card.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, AppTheme.SPACING_MD))
            self.integrations_visible = True
            self.integrations_toggle_btn.configure(text=copy.BTN_HIDE_INTEGRATIONS)
        self._finalize_card_layout()

    def _set_export_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (self.export_all_btn, self.export_captions_btn):
            button.configure(state=state)

    def _set_workflow_step(self, step: int) -> None:
        self.workflow_step = max(1, min(step, 3))
        self.step_strip.set_active(self.workflow_step)

    def _append_agent_system_welcome(self) -> None:
        self.agent_chat.configure(state="normal")
        self.agent_chat.insert(
            END,
            f"{copy.ASSISTANT_WELCOME}\n",
            "system",
        )
        self.agent_chat.configure(state="disabled")

    def _add_combobox_grid(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: StringVar,
        values: list[str] | dict[str, str],
        command=None,
    ) -> None:
        options = list(values.keys()) if isinstance(values, dict) else values
        field = FormField(parent, label)
        combo = ttk.Combobox(field, textvariable=variable, values=options, width=16, state="readonly")
        if command is not None:
            combo.bind("<<ComboboxSelected>>", lambda _event: command())
        field.attach(combo)
        field.grid(row=row, column=column, sticky="ew", padx=(0, AppTheme.SPACING_SM), pady=(0, AppTheme.SPACING_SM))

    def _add_spinbox_grid(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: StringVar,
        from_: int,
        to: int,
    ) -> None:
        field = FormField(parent, label)
        field.attach(ttk.Spinbox(field, from_=from_, to=to, textvariable=variable, width=8))
        field.grid(row=row, column=column, sticky="ew", padx=(0, AppTheme.SPACING_SM), pady=(0, AppTheme.SPACING_SM))

    def _add_combobox(self, parent: ttk.Frame, label: str, variable: StringVar, values: list[str] | dict[str, str]) -> None:
        options = list(values.keys()) if isinstance(values, dict) else values
        field = FormField(parent, label)
        field.attach(ttk.Combobox(field, textvariable=variable, values=options, width=14, state="readonly"))
        field.pack(side=LEFT, padx=(0, AppTheme.SPACING_MD))

    def _add_spinbox(self, parent: ttk.Frame, label: str, variable: StringVar, from_: int, to: int) -> None:
        field = FormField(parent, label)
        field.attach(ttk.Spinbox(field, from_=from_, to=to, textvariable=variable, width=7))
        field.pack(side=LEFT, padx=(0, AppTheme.SPACING_MD))

    def choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title=copy.BTN_SELECT_VIDEO,
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.webm *.avi"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self.selected_video = Path(path)
        self.file_label.configure(text=self.selected_video.name)
        self.status_var.set(copy.STATUS_VIDEO_SELECTED)
        self._set_workflow_step(2)

    def add_to_queue(self) -> None:
        if not self.selected_video:
            messagebox.showinfo(APP_TITLE, copy.MSG_PICK_VIDEO_FIRST)
            return
        if self.selected_video in self.video_queue:
            self.status_var.set("That video is already in your batch.")
            return
        self.video_queue.append(self.selected_video)
        self._refresh_queue_list()
        self.status_var.set(f"{len(self.video_queue)} video(s) ready in batch.")
        self._set_workflow_step(2)

    def clear_queue(self) -> None:
        self.video_queue.clear()
        self._refresh_queue_list()
        self.status_var.set("Batch cleared.")

    def _refresh_queue_list(self) -> None:
        for item in self.queue_listbox.get_children():
            self.queue_listbox.delete(item)
        for index, path in enumerate(self.video_queue, start=1):
            self.queue_listbox.insert("", END, iid=str(index), values=(path.name,))

    def generate_clips(self) -> None:
        targets = list(self.video_queue) if self.video_queue else ([self.selected_video] if self.selected_video else [])
        if not targets:
            messagebox.showinfo(APP_TITLE, copy.MSG_PICK_VIDEO_FIRST)
            return

        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            messagebox.showerror(APP_TITLE, copy.MSG_FFMPEG_MISSING)
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
        self._reload_runtime_services()
        reset_pipeline_control()
        self.generate_button.configure(state="disabled", text=copy.BTN_CREATING_CLIPS)
        self.cancel_button.configure(state="normal", text=copy.BTN_CANCEL)
        self.batch_reports = []
        self.status_var.set(copy.STATUS_CREATING)
        self._set_workflow_step(2)
        if self._progress_animator:
            self._progress_animator.reset()
        self.stage_var.set(copy.STATUS_CREATING)
        self.progress_text.delete("1.0", END)
        self._show_shimmer()

        thread = threading.Thread(target=self._run_batch_worker, args=(targets, settings), daemon=True)
        thread.start()

    def cancel_generation(self) -> None:
        get_pipeline_control().cancel()
        self.cancel_button.configure(state="disabled", text=copy.BTN_CANCELLING)
        self.status_var.set("Stopping after the current step…")
        self.stage_var.set("Cancellation requested")

    def _run_batch_worker(self, targets: list[Path], settings: dict) -> None:
        writer = QueueWriter(self.output_queue)
        ui_session = attach_ui_log_handler(self.output_queue)
        control = get_pipeline_control()

        def progress_callback(event: dict) -> None:
            self.output_queue.put(("EVENT", event))

        combined_report: dict | None = None
        accumulated_clips: list[dict] = []
        accumulated_ready: list[str] = []
        batch_errors: list[dict] = []
        cancelled = False
        try:
            with redirect_stdout(writer):
                for index, video_path in enumerate(targets, start=1):
                    if control.is_cancelled:
                        cancelled = True
                        break
                    self.output_queue.put(f"\n=== Batch {index}/{len(targets)}: {video_path.name} ===\n")
                    self.output_queue.put(
                        ("EVENT", {"type": "progress", "stage": "batch", "percent": 0, "message": f"Batch video {index}/{len(targets)}..."})
                    )
                    try:
                        report = run_pipeline(
                            video_path,
                            config_override=settings,
                            progress_callback=progress_callback,
                            pipeline_control=control,
                        )
                    except PipelineCancelled:
                        cancelled = True
                        self.output_queue.put(f"[Batch] Cancelled during {video_path.name}\n")
                        break
                    except Exception as exc:  # noqa: BLE001
                        batch_errors.append({"video": str(video_path), "error": str(exc)})
                        self.output_queue.put(f"[Batch] Failed on {video_path.name}: {exc}\n")
                        continue
                    self.batch_reports.append(report)
                    accumulated_clips.extend(report.get("clips") or [])
                    accumulated_ready.extend(report.get("clips_ready") or [])
                    combined_report = report
            if combined_report and len(self.batch_reports) > 1:
                combined_report = self._merge_batch_reports(self.batch_reports)
            elif combined_report:
                combined_report = dict(combined_report)
                combined_report["clips"] = accumulated_clips
                combined_report["clips_ready"] = accumulated_ready
                combined_report["clips_created"] = len(accumulated_clips)
            elif batch_errors and not accumulated_clips:
                combined_report = {
                    "clips": [],
                    "clips_ready": [],
                    "clips_created": 0,
                    "failure_reason": "batch_failed",
                    "batch_errors": batch_errors,
                }
            if combined_report is not None and batch_errors:
                combined_report["batch_errors"] = batch_errors
                combined_report["batch_failed_count"] = len(batch_errors)
            if cancelled:
                if combined_report is None and accumulated_clips:
                    combined_report = {
                        "clips": accumulated_clips,
                        "clips_ready": accumulated_ready,
                        "clips_created": len(accumulated_clips),
                    }
                if combined_report is not None:
                    combined_report["failure_reason"] = "cancelled"
            self.output_queue.put(("DONE", combined_report or {}))
            if self.video_queue:
                self.video_queue.clear()
                self.root.after(0, self._refresh_queue_list)
        except Exception as exc:  # noqa: BLE001
            self.output_queue.put(("ERROR", f"{exc}\n\n{traceback.format_exc()}"))
        finally:
            detach_ui_log_handler(ui_session)

    def _merge_batch_reports(self, reports: list[dict]) -> dict:
        merged = dict(reports[-1])
        merged["batch_count"] = len(reports)
        merged["clips_created"] = sum(int(report.get("clips_created", 0)) for report in reports)
        merged["batch_videos"] = [str(report.get("input_video", "")) for report in reports]
        merged["clips"] = []
        merged["clips_ready"] = []
        for report in reports:
            merged["clips"].extend(report.get("clips") or [])
            merged["clips_ready"].extend(report.get("clips_ready") or [])
        if not merged.get("failure_reason") and merged["clips_created"] == 0:
            merged["failure_reason"] = "render_failed"
        return merged

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
        self.provider_var.set(copy.DETECTION_VALUE_TO_LABEL.get("openai", "OpenAI vision"))
        self.openai_key_var.set("")
        self.key_status_var.set("OpenAI key saved. Smart detection is ready.")
        self.status_var.set("API key saved.")
        self._reload_runtime_services()

    def _config_path(self) -> Path:
        return PROJECT_ROOT / "config.json"

    def _reload_runtime_services(self) -> None:
        """Refresh config-backed services after UI or file changes."""
        override = self._settings_override()
        patch_user_config(
            self._config_path(),
            {
                "rollout": override.get("rollout") or {},
                "chat_signals": override.get("chat_signals") or {},
            },
        )
        self.config = load_config()
        self.social_manager = SocialPublishManager(self.config, PROJECT_ROOT)
        self.agent_advisor = EmbeddedAgentAdvisor(
            self.config,
            PROJECT_ROOT,
            approval_callback=self._agent_tool_approval,
        )
        self.agent_status_var.set(self._agent_status_text())
        self.chat_log_status_var.set(self._chat_log_status_text())

    def choose_chat_log(self) -> None:
        path = filedialog.askopenfilename(
            title="Select chat log",
            filetypes=[
                ("Chat logs", "*.json *.csv *.txt *.log"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.chat_log_path_var.set(path)

    def save_chat_log_path(self) -> None:
        path = self.chat_log_path_var.get().strip()
        if not path:
            messagebox.showinfo(APP_TITLE, "Choose a chat log file first.")
            return
        if not Path(path).exists():
            messagebox.showerror(APP_TITLE, f"File not found:\n{path}")
            return
        patch_user_config(
            self._config_path(),
            {"chat_signals": {"chat_log_path": path}},
        )
        self._reload_runtime_services()
        self.status_var.set(copy.MSG_CHAT_LOG_SAVED)

    def clear_chat_log_path(self) -> None:
        self.chat_log_path_var.set("")
        patch_user_config(
            self._config_path(),
            {"chat_signals": {"chat_log_path": ""}},
        )
        self._reload_runtime_services()
        self.status_var.set(copy.MSG_CHAT_LOG_CLEARED)

    def _chat_log_status_text(self) -> str:
        path = self.chat_log_path_var.get().strip()
        phase = self._rollout_phase_value()
        if path and Path(path).exists():
            return f"Chat spike scoring active — using {Path(path).name}"
        if phase == "phase_3":
            return "Phase 3 active. Optional: add a Twitch/chat export here for reaction spike scoring."
        return "No chat log configured."

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
            if self._progress_animator:
                self._progress_animator.set_target(float(percent))
            else:
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
        message = event.get("message") or (copy.STATUS_DONE if clip_count else copy.SECTION_EMPTY_CLIPS)
        if event.get("type") == "clips_ready":
            if self._progress_animator:
                self._progress_animator.set_target(100.0)
            else:
                self.progress_var.set(100.0)
            self.stage_var.set(message)
            self._hide_shimmer()
        self._append_progress(message)
        report = dict(self.report or {})
        report.update(
            {
                "clips": event.get("clips") or [],
                "clips_ready": event.get("clips_ready") or [],
                "clips_created": max(clip_count, len(event.get("clips") or []), len(event.get("clips_ready") or [])),
                "output_dir": event.get("output_dir") or str((PROJECT_ROOT / "final_clips").resolve()),
                "failure_reason": event.get("failure_reason") or report.get("failure_reason"),
            }
        )
        self.report = report
        self._show_results(report)
        clip_total = int(report.get("clips_created", 0))
        self._set_export_actions_enabled(clip_total > 0)
        if clip_count:
            self._set_workflow_step(3)

    def _generation_done(self, report: dict) -> None:
        self.report = report
        self.agent_advisor.update_context(report=report, ui_settings=self._ui_settings_snapshot())
        self.agent_status_var.set(self._agent_status_text())
        self.generate_button.configure(state="normal", text=copy.BTN_CREATE_CLIPS)
        self.cancel_button.configure(state="disabled", text=copy.BTN_CANCEL)
        clips_created = int(report.get("clips_created", 0))
        batch_count = int(report.get("batch_count", 0))
        if self._progress_animator:
            self._progress_animator.set_target(100.0)
        else:
            self.progress_var.set(100.0)
        self._hide_shimmer()
        if report.get("failure_reason") == "cancelled":
            self.stage_var.set("Cancelled")
            self.status_var.set("Clip creation cancelled.")
        elif batch_count > 1:
            self.stage_var.set(f"All done — {clips_created} clip(s) from {batch_count} video(s).")
            self.status_var.set(copy.STATUS_DONE)
        else:
            self.stage_var.set(f"All done — {clips_created} clip(s) ready.")
            self.status_var.set(copy.STATUS_DONE)
        self._set_workflow_step(3)
        if clips_created == 0:
            reason = report.get("failure_reason")
            log_file = report.get("log_file", "")
            if reason == "render_failed":
                hint = "Highlights were found but FFmpeg rendering failed. Open the log file for [FFmpeg] errors."
            else:
                hint = "No clips were created. Open the log file for details."
            self._append_progress(f"\n{hint}\nLog file: {log_file}\n")
        self._show_results(report)
        self._set_export_actions_enabled(clips_created > 0)

    def _generation_failed(self, error_text: str) -> None:
        self.generate_button.configure(state="normal", text=copy.BTN_CREATE_CLIPS)
        self.cancel_button.configure(state="disabled", text=copy.BTN_CANCEL)
        self.status_var.set(copy.STATUS_FAILED)
        self.stage_var.set(copy.STATUS_FAILED)
        self._hide_shimmer()
        self._append_progress(error_text)
        failure_report = {
            "clips": [],
            "clips_ready": [],
            "clips_created": 0,
            "failure_reason": "pipeline_error",
            "output_dir": str((PROJECT_ROOT / "final_clips").resolve()),
        }
        self.report = failure_report
        self._show_results(failure_report)
        self._set_export_actions_enabled(False)
        messagebox.showerror(APP_TITLE, "Clip creation failed. See the activity log below for details.")

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
            discovered = sorted(final_dir.glob("*_vertical.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
            if not discovered:
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
        rendered_cards = 0
        if not clips:
            reason = report.get("failure_reason")
            if reason == "render_failed":
                message = copy.MSG_RENDER_FAILED
                title = "Rendering needs attention"
            else:
                message = copy.SECTION_EMPTY_CLIPS
                title = copy.EMPTY_STATE_TITLE
            EmptyState(self.results_canvas, title=title, message=message, icon="🎬").pack(
                anchor=W, fill="x", padx=AppTheme.SPACING_SM, pady=AppTheme.SPACING_SM
            )
            log_file = report.get("log_file")
            if log_file:
                ttk.Label(self.results_canvas, text=f"Log file: {log_file}", style="Caption.TLabel").pack(
                    anchor=W, padx=AppTheme.SPACING_MD
                )
            self._refresh_results_canvas()
            return

        for index, clip in enumerate(clips, start=1):
            final_clip = self._resolve_clip_file(clip, report)
            if final_clip is None:
                continue
            if not final_clip.exists():
                continue

            rendered_cards += 1
            clip = dict(clip)
            clip["final_clip"] = str(final_clip)

            card = SectionCard(
                self.results_canvas,
                title=f"Clip {index} · {clip.get('score', 0)}/100 · {clip.get('quality_tier', quality_tier(clip))}",
                padding=AppTheme.SPACING_MD,
                shadow="subtle",
            )
            card.pack(fill="x", pady=(0, AppTheme.SPACING_MD), padx=AppTheme.SPACING_XS)
            card_content = card.content

            badges = summarize_enhancements(clip)
            if badges:
                ttk.Label(
                    card_content,
                    text=" · ".join(badges),
                    style="CardMuted.TLabel",
                    wraplength=520,
                ).pack(anchor=W, pady=(0, AppTheme.SPACING_XS))

            subscores = format_virality_subscores(clip)
            if subscores:
                ttk.Label(
                    card_content,
                    text=f"Virality: {subscores}",
                    style="CardMuted.TLabel",
                    wraplength=520,
                ).pack(anchor=W, pady=(0, AppTheme.SPACING_XS))

            tier = clip.get("quality_tier") or quality_tier(clip)
            if tier == "review_recommended":
                ttk.Label(
                    card_content,
                    text="Review recommended before posting.",
                    style="CardMuted.TLabel",
                    wraplength=520,
                ).pack(anchor=W, pady=(0, AppTheme.SPACING_XS))
            elif tier == "fallback" or clip.get("selection_mode", "").startswith("fallback") or report.get("used_fallback"):
                ttk.Label(
                    card_content,
                    text="Fallback clip — auto-generated when no strong highlights were found.",
                    style="CardMuted.TLabel",
                    wraplength=520,
                ).pack(anchor=W, pady=(0, AppTheme.SPACING_XS))

            ttk.Label(card_content, text=final_clip.name, style="CardMuted.TLabel").pack(anchor=W)
            ttk.Label(card_content, text=clip.get("hook_text", ""), style="CardTitle.TLabel").pack(
                anchor=W, pady=(AppTheme.SPACING_XS, 0)
            )
            ttk.Label(card_content, text=clip.get("caption_text", ""), style="CardMuted.TLabel", wraplength=520).pack(
                anchor=W, pady=(AppTheme.SPACING_XS, 0)
            )
            ttk.Label(
                card_content,
                text=f"Categories: {', '.join(clip.get('categories', [])) or 'none'}",
                style="CardMuted.TLabel",
            ).pack(anchor=W)
            if clip.get("start") or clip.get("end"):
                ttk.Label(
                    card_content,
                    text=f"{clip.get('start')}s → {clip.get('end')}s",
                    style="CardMuted.TLabel",
                ).pack(anchor=W)

            buttons = ttk.Frame(card_content, style="CardSurface.TFrame")
            buttons.pack(fill="x", pady=(AppTheme.SPACING_MD, 0))
            ttk.Label(buttons, text="Clip actions:", style="CardMuted.TLabel").pack(side=LEFT, padx=(0, AppTheme.SPACING_SM))
            create_button(buttons, copy.BTN_PLAY, style="Secondary.TButton", command=lambda p=final_clip: open_path(p)).pack(
                side=LEFT
            )
            create_button(
                buttons, copy.BTN_FOLDER, style="Ghost.TButton", command=lambda p=final_clip: open_path(p.parent)
            ).pack(side=LEFT, padx=(AppTheme.SPACING_XS, 0))
            create_button(buttons, copy.BTN_SAVE_ONE, style="Ghost.TButton", command=lambda p=final_clip: export_clip(p)).pack(
                side=LEFT, padx=(AppTheme.SPACING_XS, 0)
            )
            create_button(
                buttons, copy.BTN_COPY_ONE, style="Ghost.TButton", command=lambda c=clip: self.copy_caption(c)
            ).pack(side=LEFT, padx=(AppTheme.SPACING_XS, 0))
            create_button(
                buttons,
                copy.BTN_COPY_SOCIAL,
                style="Ghost.TButton",
                command=lambda c=clip: self.copy_social_caption(c),
            ).pack(side=LEFT, padx=(AppTheme.SPACING_XS, 0))
            if self.social_manager.is_enabled():
                post_row = ttk.Frame(card_content, style="CardSurface.TFrame")
                post_row.pack(fill="x", pady=(AppTheme.SPACING_SM, 0))
                ttk.Label(post_row, text=copy.BTN_POST, style="CardMuted.TLabel").pack(side=LEFT)
                for platform, label in (
                    ("youtube", "YouTube"),
                    ("tiktok", "TikTok"),
                    ("instagram", "Reels"),
                ):
                    create_button(
                        post_row,
                        label,
                        style="Chip.TButton",
                        command=lambda p=platform, c=clip, path=final_clip: self.post_clip(p, c, path),
                    ).pack(side=LEFT, padx=(AppTheme.SPACING_XS, 0))
            if clip.get("source_frame") and Path(str(clip.get("source_frame"))).exists():
                create_button(
                    buttons,
                    copy.BTN_FRAME,
                    style="Ghost.TButton",
                    command=lambda c=clip: self.preview_frame(c),
                ).pack(side=LEFT, padx=(AppTheme.SPACING_XS, 0))

        if rendered_cards == 0 and clips:
            EmptyState(
                self.results_canvas,
                title=copy.EMPTY_STATE_TITLE,
                message=copy.SECTION_EMPTY_CLIPS,
                icon="🎬",
            ).pack(anchor=W, fill="x", padx=AppTheme.SPACING_SM, pady=AppTheme.SPACING_SM)

        self._refresh_results_canvas()

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
            phase = self._rollout_phase_value()
            if phase == "phase_3":
                return "Phase 3 assistant loading — restart the app if this persists."
            return "Assistant disabled — set Quality rollout to Phase 3 or enable in config.json."
        provider = self.agent_advisor.settings.provider
        has_key = bool(self.agent_advisor.settings.openai_api_key or self.agent_advisor.settings.anthropic_api_key)
        mode = "AI-powered" if has_key else "local tips (add OpenAI key in Integrations for full AI)"
        return f"Phase 3 assistant ready ({mode}, provider={provider})."

    def _ui_settings_snapshot(self) -> dict[str, str]:
        return {
            "vision_provider": self._provider_value(),
            "max_clips": self.max_clips_var.get(),
            "min_score": self.min_score_var.get(),
            "platform_preset": self._platform_value(),
            "game_profile": self._game_profile_value(),
            "smart_reframe": self._smart_reframe_value(),
            "rollout_phase": self._rollout_phase_value(),
        }

    def _provider_value(self) -> str:
        return copy.DETECTION_LABEL_TO_VALUE.get(self.provider_var.get(), self.provider_var.get())

    def _platform_value(self) -> str:
        return copy.PLATFORM_LABEL_TO_VALUE.get(self.platform_var.get(), self.platform_var.get())

    def _theme_value(self) -> str:
        return copy.THEME_LABEL_TO_VALUE.get(self.theme_var.get(), self.theme_var.get())

    def _game_profile_value(self) -> str:
        return copy.GAME_LABEL_TO_VALUE.get(self.game_profile_var.get(), self.game_profile_var.get())

    def _smart_reframe_value(self) -> str:
        return copy.REFRAME_LABEL_TO_VALUE.get(self.smart_reframe_var.get(), self.smart_reframe_var.get())

    def _rollout_phase_value(self) -> str:
        return copy.ROLLOUT_PHASE_LABEL_TO_VALUE.get(
            self.rollout_phase_var.get(),
            self.rollout_phase_var.get(),
        )

    def _on_rollout_phase_changed(self) -> None:
        from scripts.config_rollout import describe_rollout_phase

        phase = self._rollout_phase_value()
        self.rollout_phase_hint_var.set(describe_rollout_phase(phase)["summary"])
        if phase in {"phase_1", "phase_2", "phase_3"}:
            self.smart_reframe_var.set(copy.REFRAME_VALUE_TO_LABEL.get("on", "On"))
        if phase in {"phase_2", "phase_3"}:
            self.provider_var.set(copy.DETECTION_VALUE_TO_LABEL.get("auto", "Smart auto"))
        if phase == "stable":
            self.smart_reframe_var.set(copy.REFRAME_VALUE_TO_LABEL.get("off", "Off"))
            self.provider_var.set(copy.DETECTION_VALUE_TO_LABEL.get("heuristic", "Fast (no API key)"))
        patch_user_config(self._config_path(), {"rollout": {"phase": phase}})
        self._reload_runtime_services()
        self.agent_advisor.update_context(ui_settings=self._ui_settings_snapshot())

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
        if role == "user":
            self.agent_chat.insert(END, "You\n", "user_label")
            self.agent_chat.insert(END, f"{content}\n", "user_body")
        else:
            self.agent_chat.insert(END, f"{copy.ASSISTANT_TITLE}\n", "agent_label")
            self.agent_chat.insert(END, f"{content}\n", "agent_body")
        self.agent_chat.configure(state="disabled")
        self.agent_chat.see(END)

    def agent_clear_chat(self) -> None:
        self.agent_advisor.clear_conversation()
        self.agent_chat.configure(state="normal")
        self.agent_chat.delete("1.0", END)
        self._append_agent_system_welcome()
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
            "highlight_detection.min_score": "min_score_var",
            "highlight_detection.max_clips": "max_clips_var",
            "highlight_detection.game_profile": "game_profile_var",
            "vision.provider": "provider_var",
            "rendering.platform_preset": "platform_var",
        }
        label_maps = {
            "game_profile_var": copy.GAME_VALUE_TO_LABEL,
            "provider_var": copy.DETECTION_VALUE_TO_LABEL,
            "platform_var": copy.PLATFORM_VALUE_TO_LABEL,
        }
        applied = 0
        for suggestion in suggestions:
            setting = suggestion.get("setting", "")
            suggested = str(suggestion.get("suggested", "")).split("/")[0].strip()
            var_name = mapping.get(setting)
            if not var_name or not suggested:
                continue
            var = getattr(self, var_name, None)
            if var is None:
                continue
            value = suggested.split()[0]
            label_map = label_maps.get(var_name)
            var.set(label_map.get(value, value) if label_map else value)
            applied += 1
        self.status_var.set(f"Applied {applied} suggestion(s) from your assistant.")

    def copy_all_captions(self) -> None:
        report = self.report or {}
        clips = self._clips_for_display(report)
        if not clips:
            messagebox.showinfo(APP_TITLE, copy.MSG_NO_CLIPS_YET)
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
        self.status_var.set(copy.MSG_CAPTIONS_COPIED)

    def export_all_clips(self) -> None:
        report = self.report or {}
        clips = self._clips_for_display(report)
        if not clips:
            messagebox.showinfo(APP_TITLE, copy.MSG_NO_CLIPS_YET)
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

    def _show_empty_clips_state(self) -> None:
        self._clear_results()
        EmptyState(
            self.results_canvas,
            title=copy.EMPTY_STATE_TITLE,
            message=f"{copy.SECTION_EMPTY_CLIPS}\n\n{copy.EMPTY_STATE_HINT}",
            icon="🎬",
        ).pack(anchor=W, fill="x", padx=AppTheme.SPACING_SM, pady=AppTheme.SPACING_SM)
        self._refresh_results_canvas()
        self._set_export_actions_enabled(False)

    def _show_shimmer(self) -> None:
        self._clear_results()
        self._shimmer = ShimmerPlaceholder(self.results_canvas, blocks=3)
        self._shimmer.pack(fill="x", padx=AppTheme.SPACING_SM, pady=AppTheme.SPACING_SM)
        self._shimmer.start()
        ttk.Label(
            self.results_canvas,
            text=copy.LOADING_CLIPS,
            style="Caption.TLabel",
        ).pack(anchor=W, padx=AppTheme.SPACING_MD, pady=(0, AppTheme.SPACING_SM))
        self._refresh_results_canvas()

    def _hide_shimmer(self) -> None:
        if self._shimmer is not None:
            self._shimmer.stop()
            self._shimmer = None

    def _reset_results_panel(self) -> None:
        self._show_shimmer()

    def _clear_results(self, show_placeholder: bool = False) -> None:
        self._hide_shimmer()
        for child in self.results_canvas.winfo_children():
            child.destroy()
        if show_placeholder:
            EmptyState(
                self.results_canvas,
                title=copy.EMPTY_STATE_TITLE,
                message=copy.SECTION_EMPTY_CLIPS,
                icon="🎬",
            ).pack(anchor=W, fill="x", padx=AppTheme.SPACING_SM, pady=AppTheme.SPACING_SM)
        self._refresh_results_canvas()

    def _refresh_results_canvas(self) -> None:
        self.clips_panel.refresh()

    def _append_progress(self, text: str) -> None:
        line = text if text.endswith("\n") else text + "\n"
        if not self._log_rate_limiter.allow(line):
            return
        self.progress_text.insert(END, line)
        self.progress_text.see(END)

    def _on_clips_mousewheel(self, event) -> None:
        if hasattr(event, "delta") and event.delta:
            self.results_canvas_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif getattr(event, "num", None) == 4:
            self.results_canvas_widget.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.results_canvas_widget.yview_scroll(1, "units")

    def _settings_override(self) -> dict:
        chat_path = self.chat_log_path_var.get().strip()
        override = {
            "rollout": {
                "phase": self._rollout_phase_value(),
            },
            "vision": {
                "provider": self._provider_value(),
                "analysis_interval_seconds": int(self.interval_var.get()),
                "max_frames_to_analyze": int(self.max_frames_var.get()),
            },
            "rendering": {
                "platform_preset": self._platform_value(),
                "theme": self._theme_value(),
                "smart_reframe": {
                    "enabled": self._smart_reframe_value() == "on",
                },
            },
            "highlight_detection": {
                "max_clips": int(self.max_clips_var.get()),
                "min_score": int(self.min_score_var.get()),
                "game_profile": self._game_profile_value(),
                "clip_prompt": self.clip_prompt_var.get().strip(),
                "weighted_scoring": {
                    "min_final_score": int(self.min_score_var.get()),
                },
            },
        }
        if chat_path:
            override["chat_signals"] = {"chat_log_path": chat_path}
        return override

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
            value = str(load_config().get("vision", {}).get("provider", "heuristic"))
        except Exception:  # noqa: BLE001
            value = "heuristic"
        return copy.DETECTION_VALUE_TO_LABEL.get(value, value)

    def _initial_platform_preset(self) -> str:
        try:
            value = str(load_config().get("rendering", {}).get("platform_preset", "tiktok"))
        except Exception:  # noqa: BLE001
            value = "tiktok"
        return copy.PLATFORM_VALUE_TO_LABEL.get(value, value)

    def _initial_theme(self) -> str:
        try:
            value = str(load_config().get("rendering", {}).get("theme", "default"))
        except Exception:  # noqa: BLE001
            value = "default"
        return copy.THEME_VALUE_TO_LABEL.get(value, value)

    def _initial_game_profile(self) -> str:
        try:
            value = str(load_config().get("highlight_detection", {}).get("game_profile", "generic"))
        except Exception:  # noqa: BLE001
            value = "generic"
        return copy.GAME_VALUE_TO_LABEL.get(value, value)

    def _initial_smart_reframe(self) -> str:
        try:
            enabled = bool(load_config().get("rendering", {}).get("smart_reframe", {}).get("enabled", False))
            value = "on" if enabled else "off"
        except Exception:  # noqa: BLE001
            value = "off"
        return copy.REFRAME_VALUE_TO_LABEL.get(value, value)

    def _initial_min_score(self) -> str:
        try:
            highlight = load_config().get("highlight_detection", {})
            value = highlight.get("min_score", highlight.get("weighted_scoring", {}).get("min_final_score", 60))
            return str(int(value))
        except Exception:  # noqa: BLE001
            return "60"

    def _initial_max_clips(self) -> str:
        try:
            return str(int(load_config().get("highlight_detection", {}).get("max_clips", 5)))
        except Exception:  # noqa: BLE001
            return "5"

    def _initial_scan_interval(self) -> str:
        try:
            return str(int(load_config().get("vision", {}).get("analysis_interval_seconds", 3)))
        except Exception:  # noqa: BLE001
            return "3"

    def _initial_max_frames(self) -> str:
        try:
            vision = load_config().get("vision", {})
            micro = vision.get("microclip_sampling", {})
            value = micro.get("max_samples", vision.get("max_frames_to_analyze", 60))
            return str(int(value))
        except Exception:  # noqa: BLE001
            return "60"

    def _initial_rollout_phase(self) -> str:
        try:
            phase = str(load_config().get("rollout", {}).get("phase", "phase_4"))
        except Exception:  # noqa: BLE001
            phase = "phase_4"
        return copy.ROLLOUT_PHASE_VALUE_TO_LABEL.get(phase, phase)

    def _initial_clip_prompt(self) -> str:
        try:
            return str(load_config().get("highlight_detection", {}).get("clip_prompt", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    def _rollout_phase_summary(self) -> str:
        from scripts.config_rollout import describe_rollout_phase

        return describe_rollout_phase(self._rollout_phase_value())["summary"]

    def _initial_chat_log_path(self) -> str:
        try:
            return str(load_config().get("chat_signals", {}).get("chat_log_path", "") or "")
        except Exception:  # noqa: BLE001
            return ""

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
        popen_quiet(["open", str(path)])
    else:
        popen_quiet(["xdg-open", str(path)])


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
    GameplayAutoEditorApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
