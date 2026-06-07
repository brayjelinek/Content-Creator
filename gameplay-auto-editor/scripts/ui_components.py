"""Reusable modern UI components for the desktop app."""

from __future__ import annotations

import tkinter as tk
from tkinter import BOTH, END, LEFT, RIGHT, W, X, Y, ttk
from typing import Callable

from scripts.ui_design_system import DS, DesignSystem


def create_button(
    parent: tk.Misc,
    text: str,
    *,
    style: str = "Secondary.TButton",
    icon: str = "",
    command: Callable | None = None,
) -> ttk.Button:
    label = f"{icon}  {text}".strip() if icon else text
    return ttk.Button(parent, text=label, style=style, command=command)


def create_input(
    parent: tk.Misc,
    *,
    textvariable=None,
    show: str | None = None,
    width: int = 36,
    style: str = "TEntry",
) -> ttk.Entry:
    """Modern text input aligned with the design system."""
    kwargs: dict = {"style": style, "width": width}
    if textvariable is not None:
        kwargs["textvariable"] = textvariable
    if show is not None:
        kwargs["show"] = show
    return ttk.Entry(parent, **kwargs)


class ScrollablePanel(tk.Frame):
    """Vertical scroll container for workflow sections that exceed the viewport."""

    def __init__(self, master: tk.Misc):
        super().__init__(master, bg=DS.color.background)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            bg=DS.color.background,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="Surface.TFrame", padding=(0, 0, DS.space.xs, 0))
        self.body.bind("<Configure>", self._on_body_configure)
        self._body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self._wheel_bound = False
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_body_configure(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._body_window, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event | None = None) -> None:
        if self._wheel_bound:
            return
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)
        self._wheel_bound = True

    def _unbind_mousewheel(self, _event: tk.Event | None = None) -> None:
        if not self._wheel_bound:
            return
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")
        self._wheel_bound = False

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event: tk.Event) -> None:
        direction = -1 if event.num == 4 else 1
        self.canvas.yview_scroll(direction, "units")

    def refresh(self) -> None:
        self.body.update_idletasks()
        self._on_body_configure()

    def scroll_to_widget(self, widget: tk.Misc) -> None:
        self.body.update_idletasks()
        self.refresh()
        widget_y = widget.winfo_rooty() - self.body.winfo_rooty()
        total = max(self.body.winfo_height(), 1)
        fraction = max(0.0, min(1.0, widget_y / total))
        self.canvas.yview_moveto(fraction)


class SectionCard(tk.Frame):
    """Card container with optional title, padding, and border styling."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        title: str = "",
        subtitle: str = "",
        padding: int | None = None,
        radius: int | None = None,
        shadow: str = "border",
        min_height: int | None = None,
    ):
        self.tokens = DS
        self._padding = padding or self.tokens.space.lg
        self._radius = radius or self.tokens.radius.lg
        self._fill = self.tokens.color.surface_elevated
        self._border = self.tokens.color.border
        shadow_map = {
            "subtle": self.tokens.shadow.subtle,
            "medium": self.tokens.shadow.medium,
            "strong": self.tokens.shadow.strong,
        }
        self._shadow_color = shadow_map.get(shadow, self.tokens.shadow.subtle)
        self._shadow_mode = shadow
        self._min_height = min_height or 0

        super().__init__(master, bg=self.tokens.color.background)

        outer = tk.Frame(self, bg=self.tokens.color.background)
        outer.pack(fill=BOTH, expand=True, padx=0, pady=(0, self.tokens.space.sm))

        self.canvas = tk.Canvas(
            outer,
            highlightthickness=0,
            bd=0,
            bg=self.tokens.color.background,
        )
        self.canvas.pack(fill=BOTH, expand=True)

        self.content = ttk.Frame(self.canvas, style="CardSurface.TFrame", padding=self._padding)
        self._window = self.canvas.create_window(self._padding, self._padding, window=self.content, anchor="nw")

        if title:
            ttk.Label(self.content, text=title, style="H5.TLabel").pack(anchor=W)
        if subtitle:
            ttk.Label(self.content, text=subtitle, style="Caption.TLabel").pack(
                anchor=W, pady=(self.tokens.space.xs, self.tokens.space.sm)
            )

        self.content.bind("<Configure>", self._sync_content_size)
        self.bind("<Map>", self._sync_content_size)
        self.canvas.bind("<Configure>", self._redraw)

    def _sync_content_size(self, event: tk.Event | None = None) -> None:
        """Grow the canvas to fit embedded content."""
        self.content.update_idletasks()
        if self._min_height:
            target_height = self._min_height
        else:
            content_height = max(int(self.content.winfo_reqheight()), 1)
            target_height = content_height + (self._padding * 2) + 6
        self.canvas.configure(height=target_height)
        canvas_width = max(self.canvas.winfo_width(), self.content.winfo_reqwidth() + (self._padding * 2) + 4, 80)
        inner_width = max(canvas_width - (self._padding * 2) - 4, 80)
        self.canvas.itemconfigure(self._window, width=inner_width)
        self._redraw()

    def _redraw(self, event: tk.Event | None = None) -> None:
        width = max(self.canvas.winfo_width(), 10)
        height = max(self.canvas.winfo_height(), 10)
        self.canvas.delete("card")
        if self._shadow_mode == "border":
            self._round_rect(
                0,
                0,
                width - 1,
                height - 1,
                self._radius,
                fill=self._fill,
                outline=self._border,
                width=1,
                tags="card",
            )
        else:
            self._round_rect(3, 5, width - 1, height - 1, self._radius + 2, fill=self._shadow_color, tags="card")
            self._round_rect(0, 0, width - 4, height - 6, self._radius, fill=self._fill, tags="card")
        self.canvas.tag_lower("card")
        inner_width = max(width - (self._padding * 2) - 4, 80)
        self.canvas.itemconfigure(self._window, width=inner_width)
        self.canvas.tag_raise(self._window)

    def _round_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> None:
        radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        self.canvas.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class ClipsPanel(tk.Frame):
    """Fixed-height scrollable region for clip cards."""

    def __init__(self, master: tk.Misc, *, title: str, min_height: int = 220):
        super().__init__(master, bg=DS.color.background)
        self.card = SectionCard(self, title=title, min_height=min_height, padding=DS.space.md)
        self.card.pack(fill="x")

        scroll_wrap = ttk.Frame(self.card.content, style="CardSurface.TFrame")
        scroll_wrap.pack(fill="x")

        inner_height = max(min_height - 72, 120)
        self.canvas = tk.Canvas(
            scroll_wrap,
            highlightthickness=0,
            bd=0,
            bg=DS.color.surface,
            height=inner_height,
        )
        self.scrollbar = ttk.Scrollbar(scroll_wrap, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="CardSurface.TFrame")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", self._resize_body)
        self.canvas.pack(side=LEFT, fill="x", expand=True)
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self._wheel_bound = False

    def _resize_body(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._body_window, width=event.width)

    def bind_mousewheel(self, callback: Callable) -> None:
        def _bind(_event: tk.Event | None = None) -> None:
            if self._wheel_bound:
                return
            self.canvas.bind_all("<MouseWheel>", callback)
            self.canvas.bind_all("<Button-4>", lambda e: callback(e))
            self.canvas.bind_all("<Button-5>", lambda e: callback(e))
            self._wheel_bound = True

        def _unbind(_event: tk.Event | None = None) -> None:
            if not self._wheel_bound:
                return
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
            self._wheel_bound = False

        self.canvas.bind("<Enter>", _bind)
        self.canvas.bind("<Leave>", _unbind)

    def refresh(self) -> None:
        self.body.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


class ShimmerPlaceholder(tk.Canvas):
    """Animated shimmer blocks shown while clips are generating."""

    def __init__(self, master: tk.Misc, *, blocks: int = 3, height: int = 88):
        super().__init__(
            master,
            height=(height * blocks) + (DS.space.md * (blocks - 1)),
            highlightthickness=0,
            bd=0,
            bg=DS.color.surface,
        )
        self._blocks = blocks
        self._block_height = height
        self._phase = 0
        self._running = False
        self._items: list[int] = []

    def start(self) -> None:
        self._running = True
        self._animate()

    def stop(self) -> None:
        self._running = False

    def _animate(self) -> None:
        if not self._running:
            return
        self.delete("all")
        width = max(self.winfo_width(), 280)
        for index in range(self._blocks):
            y = index * (self._block_height + DS.space.md)
            base = DS.color.surface_hover
            highlight = DS.color.neutral_700
            offset = (self._phase + index * 24) % width
            self.create_rectangle(0, y, width, y + self._block_height, fill=base, outline="")
            shimmer_w = max(width // 3, 80)
            x1 = offset - shimmer_w
            x2 = offset
            self.create_rectangle(x1, y, x2, y + self._block_height, fill=highlight, outline="")
        self._phase = (self._phase + 18) % max(width, 1)
        self.after(70, self._animate)


class EmptyState(ttk.Frame):
    def __init__(self, master: tk.Misc, *, title: str, message: str, icon: str = "🎬"):
        super().__init__(master, style="CardSurface.TFrame", padding=DS.space.xl)
        ttk.Label(self, text=icon, style="H2.TLabel").pack(anchor=W)
        ttk.Label(self, text=title, style="H4.TLabel").pack(anchor=W, pady=(DS.space.sm, DS.space.xs))
        ttk.Label(self, text=message, style="Caption.TLabel", wraplength=520).pack(anchor=W)


class FormField(ttk.Frame):
    def __init__(self, master: tk.Misc, label: str):
        super().__init__(master, style="CardSurface.TFrame")
        ttk.Label(self, text=label, style="Caption.TLabel").pack(anchor=W)

    def attach(self, widget: tk.Misc) -> tk.Misc:
        widget.pack(anchor=W, pady=(DS.space.xs, 0))
        return widget


class ModernInput(FormField):
    """Labeled input field with consistent spacing and typography."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        *,
        textvariable=None,
        show: str | None = None,
        width: int = 36,
        style: str = "TEntry",
    ):
        super().__init__(master, label)
        self.entry = create_input(
            self,
            textvariable=textvariable,
            show=show,
            width=width,
            style=style,
        )
        self.entry.pack(anchor=W, pady=(DS.space.xs, 0))

    @property
    def widget(self) -> ttk.Entry:
        return self.entry


class SmoothProgressAnimator:
    """Ease progress bar updates for smoother feedback."""

    def __init__(self, root: tk.Misc, progress_var: tk.DoubleVar):
        self.root = root
        self.progress_var = progress_var
        self._target = 0.0
        self._current = 0.0
        self._job: str | None = None

    def set_target(self, value: float) -> None:
        self._target = max(0.0, min(100.0, float(value)))
        if self._job is None:
            self._tick()

    def reset(self) -> None:
        self._target = 0.0
        self._current = 0.0
        self.progress_var.set(0.0)
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None

    def _tick(self) -> None:
        delta = self._target - self._current
        if abs(delta) < 0.4:
            self._current = self._target
            self.progress_var.set(self._current)
            self._job = None
            return
        self._current += delta * 0.22
        self.progress_var.set(self._current)
        self._job = self.root.after(30, self._tick)


class StepStrip(tk.Frame):
    def __init__(self, master: tk.Misc, steps: list[str]):
        super().__init__(master, bg=DS.color.surface)
        self.labels: list[ttk.Label] = []
        self._accents: list[tk.Frame] = []
        for index, label in enumerate(steps):
            step_frame = ttk.Frame(self, style="Surface.TFrame")
            step_frame.pack(side=LEFT, expand=True, fill=X, padx=(0, DS.space.sm if index < len(steps) - 1 else 0))
            style = "StepActive.TLabel" if index == 0 else "Step.TLabel"
            item = ttk.Label(step_frame, text=label, style=style)
            item.pack(anchor=W)
            accent = tk.Frame(step_frame, bg=DS.color.primary if index == 0 else DS.color.border, height=2)
            accent.pack(fill=X, pady=(DS.space.xs, 0))
            self.labels.append(item)
            self._accents.append(accent)

    def set_active(self, step: int) -> None:
        for index, label in enumerate(self.labels):
            active = index + 1 == step
            label.configure(style="StepActive.TLabel" if active else "Step.TLabel")
            if index < len(self._accents):
                self._accents[index].configure(bg=DS.color.primary if active else DS.color.border)
