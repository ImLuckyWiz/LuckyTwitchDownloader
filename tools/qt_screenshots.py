"""Takes baseline or redesign screenshots of the PySide6 app (Phase 9).

Usage:
    python tools/qt_screenshots.py                         # saves to docs/migration/phase9/baseline/
    python tools/qt_screenshots.py docs/migration/phase9/v1  # or to a custom output folder

Works on both real displays and headless CI via QT_QPA_PLATFORM=offscreen.
Saves PNGs for every tab, Options section, and dialog at both 1020x910 and 900x560.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication

from core import paths
from core.settings import load_settings
from luckytwitch_engine import SourceInfo
from luckytwitch_qt import LuckyApplication
from qt_ui.main_window import MainWindow
from qt_ui.theme import apply_theme, set_app_icon

SIZES = [("1020x910", 1020, 910), ("900x560", 900, 560)]
SAMPLE_SOURCE = SourceInfo(
    url="https://www.twitch.tv/videos/123",
    id="v123",
    title="Big Stream [Redesign Test]",
    uploader="Streamer",
    duration=7200.0,
    date="2026-10-01",
    twitch_vod_id="123",
)


def capture(window: MainWindow, out_path: Path) -> None:
    QApplication.processEvents()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = window.grab()
    pix.save(str(out_path), "PNG")
    print(f"Saved: {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")


def main(out_dir: Path | None = None) -> int:
    target_dir = out_dir or (ROOT / "build" / "screenshots")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Isolate from user machine settings
    tmp = Path(tempfile.mkdtemp(prefix="lt_qt_screens_"))
    paths.DATA_DIR = tmp
    paths.SETTINGS_PATH = tmp / "settings.json"
    paths.CONFIG_PATH = tmp / "config.json"
    paths.RECENT_PATH = tmp / "recent.json"
    paths.LINKS_DIR = tmp / "links"
    paths.BEAT_PATH = tmp / "running.beat"
    paths.UI_STATE_PATH = tmp / "luckytwitch_ui.json"

    app = QApplication.instance()
    if app is None:
        app = LuckyApplication(["--no-weblink"])
    apply_theme(app)
    set_app_icon(app)

    for size_name, w, h in SIZES:
        win = MainWindow(settings=load_settings(), client=None)
        win.resize(w, h)
        win.show()
        QApplication.processEvents()

        # 1. Plan Tab (empty)
        win.tabs.setCurrentIndex(1)
        capture(win, target_dir / f"{size_name}_plan_empty.png")

        # 2. Plan Tab (loaded sample VOD)
        win.on_info_ok(SAMPLE_SOURCE, [], True, "")
        capture(win, target_dir / f"{size_name}_plan_loaded.png")

        # 3. Search Tab
        win.tabs.setCurrentIndex(0)
        capture(win, target_dir / f"{size_name}_search.png")

        # 4. Queue & Log Tab
        win.tabs.setCurrentIndex(3)
        capture(win, target_dir / f"{size_name}_queue.png")

        # 5. Options Sections
        win.tabs.setCurrentIndex(2)
        if hasattr(win, "tab_options") and hasattr(win.tab_options, "side_nav"):
            for sec_key in ("output", "cuts", "chat", "tools"):
                win.tab_options.side_nav.select(sec_key)
                capture(win, target_dir / f"{size_name}_options_{sec_key}.png")

        win.close()
        QApplication.processEvents()

    print(f"\nAll baseline screenshots generated in {target_dir}")
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(main(out))
