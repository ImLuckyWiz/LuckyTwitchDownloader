"""The main window: top bar, info line, four tabs, progress bar and status line.

Mirrors ``App.build_ui`` of the tkinter app (window 1020x910, minimum 900x560, same texts, same order). The
handler of «Get info» is a stub (Phase 6). Phase 3 filled the Queue & log tab and added what belongs to the whole
window: the progress bar and status line (``set_progress``), the «Job n/m» prefix, and closing (cancel a running
job, save the settings, remove the heartbeat file). Phase 4 filled the Search tab and the Twitch API dialog; the
window owns the Twitch ``client`` (setting it refreshes the Search tab).
"""

from __future__ import annotations

import weakref

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from core import paths
from core.config import make_client
from core.settings import save_settings
from qt_ui import dialogs
from qt_ui.bridge import Bridge
from qt_ui.tabs import OptionsTab, PlanTab, QueueTab, SearchTab
from qt_ui.theme import dark_titlebar
from qt_ui.twitch_dialog import TwitchDialog

WINDOW_TITLE = "LuckyTwitch Downloader"
START_SIZE = (1020, 910)
MIN_SIZE = (900, 560)
TAB_NAMES = ("Search", "Plan", "Options", "Queue & log")
READY_TEXT = "Ready. Paste a VOD URL or ID and press «Get info»."
NO_VOD_TEXT = "No VOD loaded."


def _weak(method):
    """A function that calls ``method`` while its object lives, and does nothing (returns None) afterwards."""
    ref = weakref.WeakMethod(method)

    def call(*args):
        fn = ref()
        return fn(*args) if fn is not None else None

    return call


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
        self._client = client
        self._login_dialog: TwitchDialog | None = None
        # state the later phases fill in: the tools setup (Phase 5) and the saved-chat overlay (Phase 5)
        self.tools_busy = False
        self.tools_ctx = None
        self.saved_chat_busy = False
        self._progress_mode = "determinate"
        self._job_prefix = ""

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
            SearchTab(self.bridge), PlanTab(), OptionsTab(), QueueTab(self.bridge))
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

        # the queue tab and the window talk through signals and two hooks
        queue = self.tab_queue
        queue.status_message.connect(self.set_status)
        queue.plan_requested.connect(self.show_plan_tab)
        queue.show_requested.connect(self.show_queue_tab)
        # hooks hold the window WEAKLY: a hook that kept the window alive would make a reference cycle, and when the
        # garbage collector breaks such a cycle it empties the child widgets' Python objects before Qt has finished
        # deleting them (Qt then calls into half-dead objects: errors at random moments, mostly in tests)
        queue.blocked_reason = _weak(self.queue_blocked_reason)
        queue.output_dir = _weak(self.output_dir)
        search = self.tab_search
        search.get_client = _weak(self.get_client)
        search.reload_client = _weak(self.reload_client)
        search.status_message.connect(self.set_status)
        search.signin_requested.connect(self.ask_credentials)
        search.vod_chosen.connect(self.use_vod)
        search.update_search_state()  # the client is known only now
        self.bridge.progress.connect(self.set_progress)
        self.bridge.job.connect(self.on_job)
        self.bridge.queue_done.connect(self.on_queue_done)

        if self.client is None:  # nothing to search with yet: start on the Plan tab
            self.tabs.setCurrentWidget(self.tab_plan)
        self.set_status(READY_TEXT)
        dark_titlebar(self)

    # ---------------------------- helpers ---------------------------- #
    @property
    def client(self):
        """The Twitch client, or None when nobody is signed in. Setting it refreshes the Search tab."""
        return self._client

    @client.setter
    def client(self, value) -> None:
        self._client = value
        self.update_search_state()

    def get_client(self):
        return self.client

    def reload_client(self) -> None:
        """A saved session expired: make the client again from what is saved (the Search tab asks for this)."""
        self.client = make_client()

    def output_dir(self) -> str:
        return self.settings.get("out_dir", "")

    def show_plan_tab(self) -> None:
        self.tabs.setCurrentWidget(self.tab_plan)

    def show_queue_tab(self) -> None:
        self.tabs.setCurrentWidget(self.tab_queue)

    def update_search_state(self) -> None:
        tab = getattr(self, "tab_search", None)
        if tab is not None:
            tab.update_search_state()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def log(self, msg: str) -> None:
        self.tab_queue.log(msg)

    def set_progress(self, frac: float, text: str) -> None:
        """A negative ``frac`` means «unknown»: the bar moves back and forth instead of filling."""
        if frac < 0:
            if self._progress_mode != "indeterminate":
                self.progress.setRange(0, 0)
                self._progress_mode = "indeterminate"
            self.set_status(f"{self._job_prefix}{text}")
        else:
            if self._progress_mode != "determinate":
                self.progress.setRange(0, 100)
                self._progress_mode = "determinate"
            self.progress.setValue(round(frac * 100))
            self.set_status(f"{self._job_prefix}{text}  \u2014  {frac * 100:.0f}%")

    def on_job(self, n: int, total: int) -> None:
        self._job_prefix = f"Job {n}/{total}: " if total > 1 else ""

    def on_queue_done(self) -> None:
        self.set_progress(0, "")
        self._job_prefix = ""
        self.set_status("Queue finished.")

    def queue_blocked_reason(self) -> str:
        """Why «Start queue» must wait (a status-line sentence), or ''."""
        if self.tools_busy:
            return "Still preparing yt-dlp / ffmpeg, start the queue again in a moment."
        if self.saved_chat_busy:
            return "A chat overlay is being drawn, start the queue when it finishes."
        return ""

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt name)
        if self.tools_ctx:
            self.tools_ctx.cancel()
        runner = self.tab_queue.runner
        if runner.is_running():
            if not dialogs.ask_yes_no(self, "Quit", "A job is running. Cancel it and quit?"):
                event.ignore()
                return
            if runner.ctx:
                runner.ctx.cancel()
        if self._login_dialog is not None:
            self._login_dialog.close()  # cancels a sign-in that is waiting for the person
        self.tab_search.shutdown()
        if self.settings:  # a window made without settings must not overwrite the saved file with nothing
            save_settings(self.settings)
        try:
            paths.BEAT_PATH.unlink()  # a launch right after this one must not hand its link to a window that is gone
        except OSError:
            pass
        event.accept()

    def tab_names(self) -> list[str]:
        """The titles as the person reads them (with the '&' of «Queue & log» unescaped)."""
        return [self.tabs.tabText(i).replace("&&", "&") for i in range(self.tabs.count())]

    # ---------------------------- stubs ---------------------------- #
    def on_get_info(self) -> None:
        """Stub. The Get info flow comes in Phase 6."""

    def use_vod(self, url: str) -> None:
        """«Use this VOD» in the Search tab: the link goes into the entry, the Plan tab opens, «Get info» runs."""
        self.vod_entry.setText(url)
        self.tabs.setCurrentWidget(self.tab_plan)
        self.on_get_info()

    def ask_credentials(self) -> None:
        """The Twitch API dialog (modal; this returns at once, like the tkinter one)."""
        if self._login_dialog is not None:
            self._login_dialog.close()
            self._login_dialog.deleteLater()
        self._login_dialog = TwitchDialog(self, self)
        self._login_dialog.open()
