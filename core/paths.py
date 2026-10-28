"""Where the app keeps its files (copied from luckytwitch_downloader.py, same names, same locations).

The data folder is shared with the tkinter app: from source it is the app folder, packaged it is the per-user
data folder. For a packaged pre-release (a build version containing a hyphen, such as ``v0.8.0-beta.1``), a separate
sibling folder ``LuckyTwitch-beta`` is used so a beta install never overwrites a stable install's settings or login.
Tests monkeypatch the attributes of THIS module (the other core modules read them at call time).
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.resources import resource_path
from luckytwitch_engine import APP_DIR, user_data_dir

PRE_RELEASE_DIR_SUFFIX = "-beta"
APP_USER_MODEL_ID = "LuckyTwitch.Downloader"
PRE_RELEASE_APP_USER_MODEL_ID = "LuckyTwitch.Downloader.Beta"


def read_bundled_version() -> str:
    """Return the version string written into ``version.txt`` by the build script when frozen, or ``""``."""
    try:
        p = resource_path("version.txt")
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def is_prerelease_version(version: str) -> bool:
    """Pre-release tags contain a hyphen (for example ``v0.8.0-beta.1``); stable tags (``v2.0.0``, ``1.0``) do not."""
    return "-" in (version or "").strip()


def resolve_data_dir(frozen: bool = False, version: str = "") -> Path:
    """Return the folder where settings, credentials, recent channels and link files live.

    - From source (``frozen=False``): ``APP_DIR`` (same as the tkinter app).
    - Frozen stable release (no ``-`` in ``version``): ``user_data_dir()`` (same as 1.x so upgrading to v2.0.0 keeps
      the user's Twitch login, saved settings, recent streamers and tools).
    - Frozen pre-release (``-`` in ``version``, e.g. ``v0.8.0-beta.1``): a sibling folder ``LuckyTwitch-beta`` next to
      ``user_data_dir()`` so a beta install never overwrites a stable install's settings or login.
    """
    if not frozen:
        return APP_DIR
    base = user_data_dir()
    if is_prerelease_version(version):
        return base.with_name(base.name + PRE_RELEASE_DIR_SUFFIX)
    return base


def resolve_app_user_model_id(version: str = "") -> str:
    """Return the Windows taskbar AppUserModelID (separate for pre-release builds)."""
    return PRE_RELEASE_APP_USER_MODEL_ID if is_prerelease_version(version) else APP_USER_MODEL_ID


FROZEN = getattr(sys, "frozen", False)
BUNDLED_VERSION = read_bundled_version() if FROZEN else ""
DATA_DIR = resolve_data_dir(FROZEN, BUNDLED_VERSION)
CONFIG_PATH = DATA_DIR / "config.json"
SETTINGS_PATH = DATA_DIR / "luckytwitch_settings.json"
RECENT_PATH = DATA_DIR / "luckytwitch_recent.json"
LINKS_DIR = DATA_DIR / "links"  # links other launches leave for the open window (see weblink.py)
BEAT_PATH = DATA_DIR / "running.beat"  # the open window touches this so a second launch knows it is there
UI_STATE_PATH = DATA_DIR / "luckytwitch_ui.json"
UPDATE_STATE_PATH = DATA_DIR / "luckytwitch_update.json"
MAX_RECENT = 12


def ensure_data_dir() -> None:
    """Create the data folder. The tkinter app does this while importing its module; here the entry point calls it."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
