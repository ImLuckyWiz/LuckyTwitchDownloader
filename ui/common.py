"""Colours, fonts and tiny helpers shared by the UI modules (kept here to avoid circular imports)."""

from __future__ import annotations

import sys
from pathlib import Path

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
WARN = "#e5b567"   # cancelled jobs, warnings in the log
ACCENT = "#9146ff"
# extra tokens used by the refined theme (same family as the colours above)
BORDER = "#35373c"        # hairlines around cards and fields
HOVER = "#44474f"         # hovered neutral button / row
PRESSED = "#50535c"
ACCENT_HOVER = "#a46bff"
ACCENT_PRESS = "#7b35e6"
ACCENT_DIM = "#3a2a66"    # accent tint: selected sidebar entry, soft highlights
DISABLED = "#6d7078"
WHITE = "#ffffff"


def bmp(text) -> str:
    """Drop characters outside the Basic Multilingual Plane (emoji): some Windows Tk builds choke on them."""
    return "".join(ch for ch in str(text) if ord(ch) <= 0xFFFF)


def resource_path(*parts: str) -> Path:
    """A bundled data file: next to the sources, or inside the frozen bundle."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
    elif getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent

    candidate = base.joinpath(*parts)
    if not candidate.exists() and getattr(sys, "frozen", False):
        # On macOS .app bundles, data files might be placed in Contents/Resources
        res_candidate = base.parent.joinpath("Resources", *parts)
        if res_candidate.exists():
            return res_candidate
    return candidate


APP_ID = "LuckyTwitch.Downloader"


def set_app_icon(root) -> None:
    """Window / taskbar icon (the default feather of Tk otherwise). Silent if the files are missing."""
    if sys.platform == "win32":
        try:  # own taskbar identity, so Windows shows our icon instead of python.exe's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass
        try:
            root.iconbitmap(default=str(resource_path("assets", "icon.ico")))
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        import tkinter as tk

        img = tk.PhotoImage(file=str(resource_path("assets", "icon.png")))
        root.iconphoto(True, img)
        root._lt_icon = img  # keep a reference, Tk drops unreferenced images
    except Exception:  # noqa: BLE001
        pass
