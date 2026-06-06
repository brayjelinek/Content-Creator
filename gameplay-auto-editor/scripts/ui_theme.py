"""Modern dark theme for the desktop app."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk


class AppTheme:
    """Centralized palette and ttk style configuration."""

    # Neutral gray palette with a single accent
    BG = "#111214"
    SURFACE = "#181a1f"
    SURFACE_ELEVATED = "#202329"
    SURFACE_HOVER = "#2a2e36"
    BORDER = "#343944"
    TEXT = "#f5f6f8"
    TEXT_MUTED = "#a3a8b3"
    TEXT_DIM = "#727784"
    ACCENT = "#6366f1"
    ACCENT_SOFT = "#2a2d4a"
    ACCENT_GLOW = "#818cf8"
    SUCCESS = "#22c55e"
    WARNING = "#eab308"
    DANGER = "#ef4444"
    INPUT_BG = "#15171c"
    HERO_GRADIENT = "#1b1e26"
    SHADOW = "#0a0b0d"

    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 12
    SPACING_LG = 16
    SPACING_XL = 24
    RADIUS = 10

    FONT_UI = ("Segoe UI", 10) if sys.platform.startswith("win") else ("Roboto", 10)
    FONT_UI_BOLD = ("Segoe UI Semibold", 10, "bold") if sys.platform.startswith("win") else ("Roboto Medium", 10, "bold")
    FONT_TITLE = ("Segoe UI Semibold", 20, "bold") if sys.platform.startswith("win") else ("Roboto Medium", 20, "bold")
    FONT_HERO = ("Segoe UI Semibold", 15, "bold") if sys.platform.startswith("win") else ("Roboto Medium", 15, "bold")
    FONT_SUBTITLE = ("Segoe UI", 10) if sys.platform.startswith("win") else ("Roboto", 10)
    FONT_SMALL = ("Segoe UI", 9) if sys.platform.startswith("win") else ("Roboto", 9)
    FONT_MONO = ("Consolas", 9) if sys.platform.startswith("win") else ("DejaVu Sans Mono", 9)
    FONT_CHIP = ("Segoe UI", 8) if sys.platform.startswith("win") else ("Roboto", 8)
    FONT_STEP = ("Segoe UI Semibold", 9) if sys.platform.startswith("win") else ("Roboto Medium", 9)

    @classmethod
    def apply(cls, root: tk.Tk) -> ttk.Style:
        root.configure(bg=cls.BG)
        try:
            style = ttk.Style(root)
            style.theme_use("clam")
        except tk.TclError:
            style = ttk.Style(root)

        style.configure(".", background=cls.BG, foreground=cls.TEXT, font=cls.FONT_UI)
        style.configure("TFrame", background=cls.BG)
        style.configure("Surface.TFrame", background=cls.SURFACE)
        style.configure("Elevated.TFrame", background=cls.SURFACE_ELEVATED)
        style.configure("Hero.TFrame", background=cls.HERO_GRADIENT)
        style.configure("Steps.TFrame", background=cls.SURFACE)
        style.configure("Copilot.TFrame", background=cls.SURFACE_ELEVATED)

        style.configure("TLabel", background=cls.BG, foreground=cls.TEXT, font=cls.FONT_UI)
        style.configure("Muted.TLabel", background=cls.BG, foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)
        style.configure("Surface.TLabel", background=cls.SURFACE, foreground=cls.TEXT, font=cls.FONT_UI)
        style.configure("Hero.TLabel", background=cls.HERO_GRADIENT, foreground=cls.TEXT, font=cls.FONT_HERO)
        style.configure("HeroMuted.TLabel", background=cls.HERO_GRADIENT, foreground=cls.TEXT_MUTED, font=cls.FONT_SUBTITLE)
        style.configure("Step.TLabel", background=cls.SURFACE, foreground=cls.TEXT_DIM, font=cls.FONT_STEP)
        style.configure("StepActive.TLabel", background=cls.SURFACE, foreground=cls.ACCENT_GLOW, font=cls.FONT_STEP)
        style.configure("Copilot.TLabel", background=cls.SURFACE_ELEVATED, foreground=cls.TEXT, font=cls.FONT_UI)
        style.configure(
            "CopilotMuted.TLabel",
            background=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT_MUTED,
            font=cls.FONT_SMALL,
        )
        style.configure("Title.TLabel", background=cls.BG, foreground=cls.TEXT, font=cls.FONT_TITLE)
        style.configure("Subtitle.TLabel", background=cls.BG, foreground=cls.TEXT_MUTED, font=cls.FONT_SUBTITLE)
        style.configure("CardTitle.TLabel", background=cls.SURFACE_ELEVATED, foreground=cls.TEXT, font=cls.FONT_UI_BOLD)
        style.configure("CardMuted.TLabel", background=cls.SURFACE_ELEVATED, foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)
        style.configure("HeroCardMuted.TLabel", background=cls.HERO_GRADIENT, foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)

        style.configure(
            "TButton",
            background=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(cls.SPACING_MD, cls.SPACING_SM),
            font=cls.FONT_UI,
        )
        style.map(
            "TButton",
            background=[("active", cls.SURFACE_HOVER), ("pressed", cls.BORDER)],
            foreground=[("disabled", cls.TEXT_DIM)],
        )
        style.configure(
            "Accent.TButton",
            background=cls.ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            padding=(cls.SPACING_LG, cls.SPACING_MD),
            font=cls.FONT_UI_BOLD,
        )
        style.map(
            "Accent.TButton",
            background=[("active", cls.ACCENT_GLOW), ("pressed", cls.ACCENT)],
            foreground=[("disabled", cls.TEXT_DIM)],
        )
        style.configure(
            "Ghost.TButton",
            background=cls.SURFACE,
            foreground=cls.TEXT_MUTED,
            borderwidth=0,
            padding=(cls.SPACING_MD, cls.SPACING_SM),
            font=cls.FONT_SMALL,
        )
        style.map("Ghost.TButton", background=[("active", cls.SURFACE_HOVER)])
        style.configure(
            "Chip.TButton",
            background=cls.ACCENT_SOFT,
            foreground=cls.ACCENT_GLOW,
            borderwidth=0,
            padding=(cls.SPACING_MD, cls.SPACING_XS + 1),
            font=cls.FONT_CHIP,
        )
        style.map("Chip.TButton", background=[("active", cls.SURFACE_HOVER)])

        style.configure(
            "TEntry",
            fieldbackground=cls.INPUT_BG,
            foreground=cls.TEXT,
            bordercolor=cls.BORDER,
            lightcolor=cls.BORDER,
            darkcolor=cls.BORDER,
            insertcolor=cls.TEXT,
            padding=cls.SPACING_SM,
        )
        style.configure(
            "Copilot.TEntry",
            fieldbackground=cls.INPUT_BG,
            foreground=cls.TEXT,
            bordercolor=cls.BORDER,
            padding=cls.SPACING_MD,
        )
        style.configure(
            "TCombobox",
            fieldbackground=cls.SURFACE_ELEVATED,
            background=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT,
            arrowcolor=cls.TEXT_MUTED,
            bordercolor=cls.BORDER,
            padding=cls.SPACING_SM,
        )
        style.configure(
            "TSpinbox",
            fieldbackground=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT,
            arrowcolor=cls.TEXT_MUTED,
            bordercolor=cls.BORDER,
        )
        style.configure(
            "TProgressbar",
            background=cls.ACCENT,
            troughcolor=cls.SURFACE_ELEVATED,
            bordercolor=cls.BG,
            lightcolor=cls.ACCENT,
            darkcolor=cls.ACCENT,
            thickness=6,
        )
        style.configure(
            "TLabelframe",
            background=cls.SURFACE,
            foreground=cls.TEXT_MUTED,
            bordercolor=cls.BG,
            relief="flat",
            borderwidth=0,
        )
        style.configure("TLabelframe.Label", background=cls.SURFACE, foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)
        style.configure(
            "Card.TLabelframe",
            background=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT,
            bordercolor=cls.BG,
            relief="flat",
            borderwidth=0,
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT,
            font=cls.FONT_UI_BOLD,
        )
        style.configure("TNotebook", background=cls.BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background=cls.SURFACE,
            foreground=cls.TEXT_MUTED,
            padding=(cls.SPACING_LG, cls.SPACING_SM),
            font=cls.FONT_SMALL,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", cls.SURFACE_ELEVATED)],
            foreground=[("selected", cls.TEXT)],
        )
        style.configure(
            "Treeview",
            background=cls.SURFACE_ELEVATED,
            foreground=cls.TEXT,
            fieldbackground=cls.SURFACE_ELEVATED,
            bordercolor=cls.BG,
            rowheight=28,
        )
        style.configure("Treeview.Heading", background=cls.SURFACE, foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)
        style.configure("Vertical.TScrollbar", background=cls.SURFACE, troughcolor=cls.BG, bordercolor=cls.BG)
        return style

    @classmethod
    def configure_text_widget(cls, widget: tk.Text, *, mono: bool = False) -> None:
        widget.configure(
            bg=cls.INPUT_BG if mono else cls.SURFACE_ELEVATED,
            fg=cls.TEXT,
            insertbackground=cls.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=cls.BORDER,
            highlightcolor=cls.ACCENT,
            font=cls.FONT_MONO if mono else cls.FONT_UI,
            padx=cls.SPACING_MD,
            pady=cls.SPACING_SM,
            selectbackground=cls.ACCENT_SOFT,
            selectforeground=cls.TEXT,
        )

    @classmethod
    def configure_copilot_chat(cls, widget: tk.Text) -> None:
        widget.configure(
            bg=cls.SURFACE_ELEVATED,
            fg=cls.TEXT,
            insertbackground=cls.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=cls.FONT_UI,
            padx=cls.SPACING_MD,
            pady=cls.SPACING_MD,
            wrap="word",
            spacing1=cls.SPACING_XS,
            spacing3=cls.SPACING_SM,
        )
        widget.tag_configure("meta", foreground=cls.TEXT_DIM, font=cls.FONT_SMALL, spacing1=cls.SPACING_MD, spacing3=2)
        widget.tag_configure("user_label", foreground=cls.ACCENT_GLOW, font=cls.FONT_UI_BOLD, spacing1=cls.SPACING_LG)
        widget.tag_configure("user_body", foreground=cls.TEXT, lmargin1=cls.SPACING_MD, lmargin2=cls.SPACING_MD, rmargin=cls.SPACING_XL)
        widget.tag_configure("agent_label", foreground=cls.SUCCESS, font=cls.FONT_UI_BOLD, spacing1=cls.SPACING_LG)
        widget.tag_configure("agent_body", foreground=cls.TEXT, lmargin1=cls.SPACING_MD, lmargin2=cls.SPACING_MD, rmargin=cls.SPACING_MD)
        widget.tag_configure("system", foreground=cls.TEXT_DIM, font=cls.FONT_SMALL, spacing1=cls.SPACING_XL)

    @classmethod
    def configure_results_canvas(cls, widget: tk.Canvas) -> None:
        widget.configure(bg=cls.SURFACE, highlightthickness=0, bd=0)
