"""Design tokens for the desktop app UI."""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass


@dataclass(frozen=True)
class SpaceScale:
    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 20
    xl: int = 28
    xxl: int = 36


@dataclass(frozen=True)
class RadiusScale:
    sm: int = 8
    md: int = 12
    lg: int = 16


@dataclass(frozen=True)
class ShadowScale:
    subtle: str = "#0d0e12"
    medium: str = "#08090c"
    strong: str = "#030305"


@dataclass(frozen=True)
class ColorTokens:
    background: str = "#09090b"
    surface: str = "#111114"
    surface_elevated: str = "#18181b"
    surface_hover: str = "#232329"
    primary: str = "#7c83ff"
    primary_hover: str = "#9aa0ff"
    primary_soft: str = "#2a2d4a"
    secondary: str = "#334155"
    secondary_hover: str = "#475569"
    accent: str = "#22d3ee"
    accent_soft: str = "#164e63"
    text: str = "#f8fafc"
    text_secondary: str = "#cbd5e1"
    text_muted: str = "#94a3b8"
    text_dim: str = "#64748b"
    border: str = "#27272a"
    input: str = "#0f1014"
    success: str = "#22c55e"
    warning: str = "#eab308"
    danger: str = "#ef4444"
    neutral_100: str = "#f1f5f9"
    neutral_200: str = "#e2e8f0"
    neutral_300: str = "#cbd5e1"
    neutral_400: str = "#94a3b8"
    neutral_500: str = "#64748b"
    neutral_600: str = "#475569"
    neutral_700: str = "#334155"
    neutral_800: str = "#1e293b"
    neutral_900: str = "#0f172a"


@dataclass
class FontTokens:
    family: str
    mono: str
    h1: tuple
    h2: tuple
    h3: tuple
    h4: tuple
    h5: tuple
    h6: tuple
    body: tuple
    body_bold: tuple
    caption: tuple
    button: tuple


class DesignSystem:
    space = SpaceScale()
    radius = RadiusScale()
    shadow = ShadowScale()
    color = ColorTokens()

    @classmethod
    def build_fonts(cls, root: tk.Misc) -> FontTokens:
        families = {name.lower(): name for name in tkfont.families(root)}
        if sys.platform == "darwin":
            family = families.get("sf pro display") or families.get(".applesystemuifont") or "Helvetica Neue"
        elif "inter" in families:
            family = families["inter"]
        elif sys.platform.startswith("win"):
            family = "Segoe UI"
        else:
            family = families.get("roboto") or "Helvetica Neue"

        mono = "Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono"
        return FontTokens(
            family=family,
            mono=mono,
            h1=(family, 28, "bold"),
            h2=(family, 24, "bold"),
            h3=(family, 16, "bold"),
            h4=(family, 14, "bold"),
            h5=(family, 12, "bold"),
            h6=(family, 11, "bold"),
            body=(family, 11),
            body_bold=(family, 11, "bold"),
            caption=(family, 10),
            button=(family, 11, "bold"),
        )


DS = DesignSystem()
