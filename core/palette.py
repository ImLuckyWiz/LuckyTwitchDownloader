"""Colour tokens and font names (copied from ui/common.py). Plain data: no Qt, no tkinter."""

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
MUTED = "#a3a6ad"  # Phase 9: raised from #9a9da4 to pass WCAG AA (4.5:1 on BG3)
ERR = "#ff6b6b"
OK = "#6bd49a"
WARN = "#e5b567"   # cancelled jobs, warnings in the log
ACCENT = "#9146ff"
ACCENT_TEXT = "#b380ff"  # Phase 9: lighter accent tint passing WCAG AA (4.89:1 on BG2) for text
# extra tokens used by the refined theme (same family as the colours above)
BORDER = "#35373c"        # hairlines around cards and fields
BORDER_STRONG = "#484b52" # Phase 9: visible card & separator border (1.58:1 on BG2)
FIELD_BORDER = "#5a5e67"  # Phase 9: distinct input border
HOVER = "#44474f"         # hovered neutral button / row
PRESSED = "#50535c"
ACCENT_HOVER = "#a46bff"
ACCENT_PRESS = "#7b35e6"
ACCENT_DIM = "#3a2a66"    # accent tint: selected sidebar entry, soft highlights
DISABLED = "#6d7078"
WHITE = "#ffffff"

# every colour token by name (the theme generates its stylesheet from this)
TOKENS = {
    "BG": BG, "BG2": BG2, "BG3": BG3, "FG": FG, "MUTED": MUTED, "ERR": ERR, "OK": OK, "WARN": WARN,
    "ACCENT": ACCENT, "ACCENT_TEXT": ACCENT_TEXT, "BORDER": BORDER, "BORDER_STRONG": BORDER_STRONG,
    "FIELD_BORDER": FIELD_BORDER, "HOVER": HOVER, "PRESSED": PRESSED, "ACCENT_HOVER": ACCENT_HOVER,
    "ACCENT_PRESS": ACCENT_PRESS, "ACCENT_DIM": ACCENT_DIM, "DISABLED": DISABLED, "WHITE": WHITE,
}
