"""The main window: top bar, info line, four tabs, progress bar and status line (Phase 1: the frame only).

Mirrors ``App.build_ui`` of the tkinter app (window 1020x910, minimum 900x560, same texts, same order). The
handlers of «Get info» and «Twitch API…» are stubs: they come in Phase 6 and Phase 4. The tabs are empty.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from qt_ui.bridge import Bridge
from qt_ui.tabs import OptionsTab, PlanTab, QueueTab, SearchTab
from qt_ui.theme import dark_titlebar

WINDOW_TITLE = "LuckyTwitch Downloader"
START_SIZE = (1020, 910)
MIN_SIZE = (900, 560)
TAB_NAMES = ("Search", "Plan", "Options", "Queue & log")
READY_TEXT = "Ready. Paste a VOD URL or ID and press «Get info»."
NO_VOD_TEXT = "No VOD loaded."


def _tab_text(name: str) -> str:
    """Qt reads '&' in a tab title as a keyboard-shortcut mark; '&&' shows a real ampersand."""
    return name.replace("&", "&&")


class MainWindow(QMainWindow):
    """``client`` is the Twitch client (or None when nobody is signed in): without one the app starts on the Plan
    tab, as the tkinter app does. ``settings`` is the dict from ``core.settings.load_settings()``."""

    def __init__(self, bridge: Bridge | None = None, settings: dict | None = None, client=None):
        super().__init__()
        self.bridge = bridge if bridge is not None else Bridge(self)
        self.settings = settings if settings is not None else {}
        self.client = client

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*START_SIZE)
        self.setMinimumSize(*MIN_SIZE)

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(central)

        # top bar: the VOD entry, «Get info», «Twitch API…»
        top = QWidget()
        row = QHBoxLayout(top)
        row.setContentsMargins(10, 10, 10, 2)
        row.setSpacing(8)
        row.addWidget(QLabel("VOD URL or ID:"))
        self.vod_entry = QLineEdit()
        self.vod_entry.returnPressed.connect(self.on_get_info)
        row.addWidget(self.vod_entry, 1)
        self.info_btn = QPushButton("Get info")
        self.info_btn.setProperty("variant", "accent")
        self.info_btn.setMinimumWidth(96)
        self.info_btn.clicked.connect(self.on_get_info)
        row.addWidget(self.info_btn)
        self.api_btn = QPushButton("Twitch API…")
        self.api_btn.clicked.connect(self.ask_credentials)
        row.addWidget(self.api_btn)
        outer.addWidget(top)

        # info line under it
        self.info_label = QLabel(NO_VOD_TEXT)
        self.info_label.setProperty("role", "muted")
        self.info_label.setContentsMargins(12, 0, 10, 4)
        outer.addWidget(self.info_label)

        # the four tabs
        tabs_box = QWidget()
        tabs_lay = QHBoxLayout(tabs_box)
        tabs_lay.setContentsMargins(10, 0, 10, 4)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tab_search, self.tab_plan, self.tab_options, self.tab_queue = (
            SearchTab(), PlanTab(), OptionsTab(), QueueTab())
        for widget, name in zip((self.tab_search, self.tab_plan, self.tab_options, self.tab_queue), TAB_NAMES):
            self.tabs.addTab(widget, _tab_text(name))
        tabs_lay.addWidget(self.tabs)
        outer.addWidget(tabs_box, 1)

        # bottom, always visible: progress bar and status line
        bottom = QWidget()
        bot = QVBoxLayout(bottom)
        bot.setContentsMargins(10, 4, 10, 8)
        bot.setSpacing(4)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        bot.addWidget(self.progress)
        self.status_label = QLabel()
        bot.addWidget(self.status_label)
        outer.addWidget(bottom)

        # keyboard order of the top bar, then the tabs
        self.setTabOrder(self.vod_entry, self.info_btn)
        self.setTabOrder(self.info_btn, self.api_btn)
        self.setTabOrder(self.api_btn, self.tabs.tabBar())

        if self.client is None:  # nothing to search with yet: start on the Plan tab
            self.tabs.setCurrentWidget(self.tab_plan)
        self.set_status(READY_TEXT)
        dark_titlebar(self)

    # ---------------------------- helpers ---------------------------- #
    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def tab_names(self) -> list[str]:
        """The titles as the person reads them (with the '&' of «Queue & log» unescaped)."""
        return [self.tabs.tabText(i).replace("&&", "&") for i in range(self.tabs.count())]

    # ---------------------------- stubs ---------------------------- #
    def on_get_info(self) -> None:
        """Stub. The Get info flow comes in Phase 6."""

    def ask_credentials(self) -> None:
        """Stub. The Twitch API / sign-in dialog comes in Phase 4."""
