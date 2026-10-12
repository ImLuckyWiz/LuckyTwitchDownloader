"""Colours, fonts and tiny helpers shared by the UI modules (kept here to avoid circular imports)."""

from __future__ import annotations

import sys

# --- fonts (per platform) --- #
if sys.platform == "win32":
    MONO_FONT, UI_FONT = "Consolas", "Segoe UI"
elif sys.platform == "darwin":
    MONO_FONT, UI_FONT = "Menlo", "Helvetica Neue"
else:
    MONO_FONT, UI_FONT = "DejaVu Sans Mono", "DejaVu Sans"

# --- palette --- #
BG = "#1e1f22"
BG2 = "#2b2d31"
BG3 = "#3a3c42"
FG = "#e6e6e6"
MUTED = "#9a9da4"
ERR = "#ff6b6b"
OK = "#6bd49a"
ACCENT = "#9146ff"


def bmp(text) -> str:
    """Drop characters outside the Basic Multilingual Plane (emoji): some Windows Tk builds choke on them."""
    return "".join(ch for ch in str(text) if ord(ch) <= 0xFFFF)
