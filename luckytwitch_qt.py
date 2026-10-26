"""LuckyTwitch Downloader, PySide6 version (default entry point from v2.0.0; packaged by build_windows.bat and
build_mac.sh).

    python luckytwitch_qt.py

The legacy tkinter entry point (luckytwitch_downloader.py) stays in the repository for one release cycle before
removal. Both use the same data folder (except packaged pre-release builds with a hyphen in the version, which use
LuckyTwitch-beta); the settings are saved when the window closes. The tools (yt-dlp, ffmpeg) are prepared in the
background right after the window opens. A ``luckytwitch://`` link passed on the command line is handed to an
already-open window when one is running, or opened here after start-up; on macOS, ``QFileOpenEvent`` delivers links
to the running app.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtWidgets import QApplication

import weblink
from core import paths
from core.config import make_client
from core.settings import load_settings
from qt_ui.main_window import MainWindow
from qt_ui.theme import apply_theme, set_app_icon


class LuckyApplication(QApplication):
    """``QApplication`` that also turns macOS ``QFileOpenEvent`` URL events into ``link_opened(str)`` (replaces
    tkinter's ``::tk::mac::LaunchURL``)."""

    link_opened = Signal(str)

    def event(self, ev) -> bool:  # noqa: N802 (Qt name)
        if ev.type() == QEvent.Type.FileOpen:
            url = ev.url().toString() if hasattr(ev, "url") else ""
            if not url and hasattr(ev, "file"):
                url = ev.file()
            if url:
                self.link_opened.emit(url)
                return True
        return super().event(ev)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    paths.ensure_data_dir()
    link = weblink.find_link(argv[1:])  # started by a luckytwitch:// link?
    if link and weblink.hand_off(link, paths.LINKS_DIR, paths.BEAT_PATH):
        return 0  # the window that is already open took it
    app = LuckyApplication(argv)
    apply_theme(app)
    set_app_icon(app)
    window = MainWindow(settings=load_settings(), client=make_client())
    if hasattr(app, "link_opened"):
        app.link_opened.connect(window.open_link)
    window.show()
    window.start_tools_setup()
    if link:
        QTimer.singleShot(300, lambda: window.open_link(link))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
