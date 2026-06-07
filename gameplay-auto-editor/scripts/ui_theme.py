"""Modern theme wiring for the desktop app."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from scripts.ui_design_system import DS, DesignSystem


class AppTheme:
    """Centralized palette and ttk style configuration."""

    DS = DS

    @classmethod
    def _c(cls, name: str) -> str:
        return getattr(cls.DS.color, name)

    @classmethod
    def apply(cls, root: tk.Tk) -> ttk.Style:
        fonts = DesignSystem.build_fonts(root)
        cls.fonts = fonts

        BG = cls._c("background")
        SURFACE = cls._c("surface")
        SURFACE_ELEVATED = cls._c("surface_elevated")
        SURFACE_HOVER = cls._c("surface_hover")
        BORDER = cls._c("border")
        TEXT = cls._c("text")
        TEXT_MUTED = cls._c("text_muted")
        TEXT_DIM = cls._c("text_dim")
        ACCENT = cls._c("primary")
        ACCENT_SOFT = cls._c("primary_soft")
        ACCENT_GLOW = cls._c("primary_hover")
        SUCCESS = cls._c("success")
        INPUT_BG = cls._c("input")

        cls.BG = BG
        cls.SURFACE = SURFACE
        cls.SURFACE_ELEVATED = SURFACE_ELEVATED
        cls.SURFACE_HOVER = SURFACE_HOVER
        cls.BORDER = BORDER
        cls.TEXT = TEXT
        cls.TEXT_MUTED = TEXT_MUTED
        cls.TEXT_DIM = TEXT_DIM
        cls.ACCENT = ACCENT
        cls.ACCENT_SOFT = ACCENT_SOFT
        cls.ACCENT_GLOW = ACCENT_GLOW
        cls.SUCCESS = SUCCESS
        cls.INPUT_BG = INPUT_BG
        cls.FONT_UI = fonts.body
        cls.FONT_UI_BOLD = fonts.body_bold
        cls.FONT_TITLE = fonts.h2
        cls.FONT_HERO = fonts.h3
        cls.FONT_SUBTITLE = fonts.body
        cls.FONT_SMALL = fonts.caption
        cls.FONT_MONO = (fonts.mono, 10)
        cls.FONT_CHIP = fonts.caption
        cls.FONT_STEP = fonts.h6
        cls.SPACING_XS = DS.space.xs
        cls.SPACING_SM = DS.space.sm
        cls.SPACING_MD = DS.space.md
        cls.SPACING_LG = DS.space.lg
        cls.SPACING_XL = DS.space.xl
        cls.SPACING_XXL = DS.space.xxl

        root.configure(bg=BG)
        try:
            style = ttk.Style(root)
            style.theme_use("clam")
        except tk.TclError:
            style = ttk.Style(root)

        style.configure(".", background=BG, foreground=TEXT, font=fonts.body)
        style.configure("TFrame", background=BG)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("Elevated.TFrame", background=SURFACE_ELEVATED)
        style.configure("CardSurface.TFrame", background=SURFACE_ELEVATED)
        style.configure("Hero.TFrame", background=SURFACE_ELEVATED)
        style.configure("Steps.TFrame", background=BG)
        style.configure("Copilot.TFrame", background=SURFACE_ELEVATED)

        for name, font in (
            ("H1.TLabel", fonts.h1),
            ("H2.TLabel", fonts.h2),
            ("H3.TLabel", fonts.h3),
            ("H4.TLabel", fonts.h4),
            ("H5.TLabel", fonts.h5),
            ("H6.TLabel", fonts.h6),
            ("Body.TLabel", fonts.body),
            ("Caption.TLabel", fonts.caption),
        ):
            style.configure(name, background=SURFACE_ELEVATED, foreground=TEXT, font=font)

        for name, font in (
            ("H1OnBg.TLabel", fonts.h1),
            ("H2OnBg.TLabel", fonts.h2),
            ("H3OnBg.TLabel", fonts.h3),
            ("H4OnBg.TLabel", fonts.h4),
            ("H5OnBg.TLabel", fonts.h5),
            ("H6OnBg.TLabel", fonts.h6),
            ("BodyOnBg.TLabel", fonts.body),
            ("CaptionOnBg.TLabel", fonts.caption),
        ):
            style.configure(name, background=BG, foreground=TEXT, font=font)
        style.configure("CaptionOnBg.TLabel", foreground=TEXT_MUTED)

        style.configure("TLabel", background=BG, foreground=TEXT, font=fonts.body)
        style.configure("Muted.TLabel", background=BG, foreground=TEXT_MUTED, font=fonts.caption)
        style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT, font=fonts.body)
        style.configure("Hero.TLabel", background=SURFACE_ELEVATED, foreground=TEXT, font=fonts.h3)
        style.configure("HeroMuted.TLabel", background=SURFACE_ELEVATED, foreground=TEXT_MUTED, font=fonts.body)
        style.configure("Step.TLabel", background=SURFACE, foreground=TEXT_DIM, font=fonts.caption)
        style.configure("StepActive.TLabel", background=SURFACE, foreground=TEXT, font=fonts.body_bold)
        style.configure("Copilot.TLabel", background=SURFACE_ELEVATED, foreground=TEXT, font=fonts.body_bold)
        style.configure("CopilotMuted.TLabel", background=SURFACE_ELEVATED, foreground=TEXT_MUTED, font=fonts.caption)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=fonts.h2)
        style.configure("Subtitle.TLabel", background=BG, foreground=TEXT_MUTED, font=fonts.body)
        style.configure("CardTitle.TLabel", background=SURFACE_ELEVATED, foreground=TEXT, font=fonts.body_bold)
        style.configure("CardMuted.TLabel", background=SURFACE_ELEVATED, foreground=TEXT_MUTED, font=fonts.caption)
        style.configure("HeroCardMuted.TLabel", background=SURFACE_ELEVATED, foreground=TEXT_MUTED, font=fonts.caption)

        style.configure(
            "TButton",
            background=SURFACE_ELEVATED,
            foreground=TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(DS.space.md, DS.space.sm),
            font=fonts.body,
        )
        style.map(
            "TButton",
            background=[("active", SURFACE_HOVER), ("pressed", BORDER), ("disabled", SURFACE)],
            foreground=[("disabled", TEXT_DIM)],
        )
        style.configure(
            "Danger.TButton",
            background=cls._c("danger"),
            foreground="#ffffff",
            borderwidth=0,
            padding=(DS.space.md, DS.space.sm),
            font=fonts.button,
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#dc2626"), ("pressed", cls._c("danger")), ("disabled", SURFACE_HOVER)],
            foreground=[("disabled", TEXT_DIM)],
        )
        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            padding=(DS.space.lg, DS.space.md),
            font=fonts.button,
        )
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_GLOW), ("pressed", ACCENT), ("disabled", SURFACE_HOVER)],
            foreground=[("disabled", TEXT_DIM)],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            padding=(DS.space.lg, DS.space.md),
            font=fonts.button,
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_GLOW), ("pressed", ACCENT), ("disabled", SURFACE_HOVER)],
            foreground=[("disabled", TEXT_DIM)],
        )
        style.configure(
            "Secondary.TButton",
            background=SURFACE,
            foreground=TEXT,
            borderwidth=0,
            padding=(DS.space.md, DS.space.sm),
            font=fonts.body,
        )
        style.map("Secondary.TButton", background=[("active", SURFACE_HOVER), ("pressed", BORDER)])
        style.configure(
            "Ghost.TButton",
            background=SURFACE,
            foreground=TEXT_MUTED,
            borderwidth=0,
            padding=(DS.space.md, DS.space.sm),
            font=fonts.caption,
        )
        style.map("Ghost.TButton", background=[("active", SURFACE_HOVER)])
        style.configure(
            "Chip.TButton",
            background=ACCENT_SOFT,
            foreground=ACCENT_GLOW,
            borderwidth=0,
            padding=(DS.space.md, DS.space.xs + 1),
            font=fonts.caption,
        )
        style.map("Chip.TButton", background=[("active", SURFACE_HOVER)])

        style.configure(
            "TEntry",
            fieldbackground=INPUT_BG,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            insertcolor=TEXT,
            padding=DS.space.sm,
        )
        style.map("TEntry", fieldbackground=[("focus", SURFACE_HOVER)], bordercolor=[("focus", ACCENT)])
        style.configure(
            "Copilot.TEntry",
            fieldbackground=INPUT_BG,
            foreground=TEXT,
            bordercolor=BORDER,
            padding=DS.space.md,
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_ELEVATED,
            background=SURFACE_ELEVATED,
            foreground=TEXT,
            arrowcolor=TEXT_MUTED,
            bordercolor=BORDER,
            padding=DS.space.sm,
        )
        style.map("TCombobox", fieldbackground=[("readonly", SURFACE_ELEVATED)])
        style.configure(
            "TSpinbox",
            fieldbackground=SURFACE_ELEVATED,
            foreground=TEXT,
            arrowcolor=TEXT_MUTED,
            bordercolor=BORDER,
        )
        style.configure(
            "TProgressbar",
            background=ACCENT,
            troughcolor=SURFACE,
            bordercolor=BG,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=8,
        )
        style.configure("TLabelframe", background=SURFACE, foreground=TEXT_MUTED, bordercolor=BG, relief="flat")
        style.configure("TLabelframe.Label", background=SURFACE, foreground=TEXT_MUTED, font=fonts.caption)
        style.configure("Card.TLabelframe", background=SURFACE_ELEVATED, foreground=TEXT, bordercolor=BG, relief="flat")
        style.configure("Card.TLabelframe.Label", background=SURFACE_ELEVATED, foreground=TEXT, font=fonts.body_bold)
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background=BG,
            foreground=TEXT_DIM,
            padding=(DS.space.lg, DS.space.sm),
            font=fonts.caption,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", SURFACE_ELEVATED)],
            foreground=[("selected", TEXT)],
        )
        style.configure(
            "Treeview",
            background=SURFACE,
            foreground=TEXT,
            fieldbackground=SURFACE,
            bordercolor=BG,
            rowheight=30,
        )
        style.configure("Treeview.Heading", background=SURFACE_ELEVATED, foreground=TEXT_MUTED, font=fonts.caption)
        style.configure("Vertical.TScrollbar", background=SURFACE, troughcolor=BG, bordercolor=BG)
        return style

    @classmethod
    def configure_text_widget(cls, widget: tk.Text, *, mono: bool = False) -> None:
        widget.configure(
            bg=cls.INPUT_BG if mono else cls.SURFACE,
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
            bg=cls.SURFACE,
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
