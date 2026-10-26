"""LuckyTwitch Downloader, PySide6 version (migration branch). The Search, Options and Queue tabs are built; Plan comes next.

    python luckytwitch_qt.py

The tkinter app (luckytwitch_downloader.py) stays the shipped one until the cutover. Both use the same data
folder; the settings are saved when the window closes. The tools (yt-dlp, ffmpeg) are prepared in the background
right after the window opens, like the tkinter app does.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core import paths
from core.config import make_client
from core.settings import load_settings
from qt_ui.main_window import MainWindow
from qt_ui.theme import apply_theme, set_app_icon


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    paths.ensure_data_dir()
    apply_theme(app)
    set_app_icon(app)
    window = MainWindow(settings=load_settings(), client=make_client())
    window.show()
    window.start_tools_setup()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
