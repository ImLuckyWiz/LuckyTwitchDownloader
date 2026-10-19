"""Where the app keeps its files (copied from luckytwitch_downloader.py, same names, same locations).

The data folder is shared with the tkinter app: from source it is the app folder, packaged it is the per-user
data folder. Tests monkeypatch the attributes of THIS module (the other core modules read them at call time).
"""

from __future__ import annotations

import sys
from pathlib import Path

from luckytwitch_engine import APP_DIR, user_data_dir

FROZEN = getattr(sys, "frozen", False)
DATA_DIR = user_data_dir() if FROZEN else APP_DIR
CONFIG_PATH = DATA_DIR / "config.json"
SETTINGS_PATH = DATA_DIR / "luckytwitch_settings.json"
RECENT_PATH = DATA_DIR / "luckytwitch_recent.json"
LINKS_DIR = DATA_DIR / "links"  # links other launches leave for the open window (see weblink.py)
BEAT_PATH = DATA_DIR / "running.beat"  # the open window touches this so a second launch knows it is there
MAX_RECENT = 12


def ensure_data_dir() -> None:
    """Create the data folder. The tkinter app does this while importing its module; here the entry point calls it."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
