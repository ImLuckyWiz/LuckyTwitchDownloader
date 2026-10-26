"""The main window: top bar, info line, four tabs, progress bar and status line.

Mirrors ``App.build_ui`` of the tkinter app (window 1020x910, minimum 900x560, same texts, same order). The
handler of «Get info» is a stub (Phase 6). Phase 3 filled the Queue & log tab and added what belongs to the whole
window: the progress bar and status line (``set_progress``), the «Job n/m» prefix, and closing (cancel a running
job, save the settings, remove the heartbeat file). Phase 4 filled the Search tab and the Twitch API dialog; the
window owns the Twitch ``client`` (setting it refreshes the Search tab). Phase 5 filled the Options tab: the window
owns the two background jobs it starts (the tools setup and the overlay of a saved chat), builds the engine's
``JobOptions`` from the settings (``build_options``) and passes the settings dictionary to the tab, which edits it.
"""

from __future__ import annotations

import weakref
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from core import paths
from core.config import make_client
from core.options import build_filter, build_options, flag
from core.settings import save_settings
from luckytwitch_engine import EngineError, describe_chat_overlay
from qt_ui import dialogs
from qt_ui.background_jobs import SavedChatRunner, ToolsRunner
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
        # the two background jobs of the Options tab: the tools setup and the overlay of a saved chat
        self.tools_busy = False
        self.tools_ctx = None
        self.saved_chat_busy = False
        self.saved_chat_ctx = None
        self.tools_runner = ToolsRunner(self.bridge)
        self.saved_chat_runner = SavedChatRunner(self.bridge)
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
            SearchTab(self.bridge), PlanTab(), OptionsTab(self.settings), QueueTab(self.bridge))
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
        queue.cancel_other = _weak(self.cancel_saved_chat)  # «Cancel current» also stops a chat overlay
        options = self.tab_options
        options.status_message.connect(self.set_status)
        options.refresh_clips_requested.connect(self.refresh_clips)
        options.preview_requested.connect(self.update_preview)
        options.output_folder_requested.connect(queue.open_output_folder)
        options.update_tools_requested.connect(self.update_tools_now)
        options.saved_chat_requested.connect(self.render_saved_chat)
        self.bridge.tools_info.connect(options.set_tools_info)
        self.bridge.tools_done.connect(self.on_tools_done)
        self.bridge.saved_chat_done.connect(self.on_saved_chat_done)
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

    # ---------------------------- options ---------------------------- #
    def cut_text(self) -> str:
        """The text of the Plan tab's cut points box. Empty until the Plan tab exists (Phase 6 fills this in)."""
        return ""

    def build_options(self):
        """The engine's ``JobOptions`` from the settings and the cut points (``App.build_options``)."""
        return build_options(self.settings, self.cut_text())

    def build_filter(self):
        return build_filter(self.settings)

    def refresh_clips(self) -> None:
        """A setting the clip list depends on changed. Stub: the Plan tab's clips come in Phase 6."""

    def update_preview(self) -> None:
        """The strategy or threshold changed. Stub: the Plan tab's preview comes in Phase 6."""

    # ---------------------------- tools (yt-dlp / ffmpeg) ---------------------------- #
    def start_tools_setup(self, force: bool = False) -> None:
        """Download missing tools / update yt-dlp in the background (``luckytwitch_qt.main`` calls this at start)."""
        if self.tools_busy:
            return
        self.tools_busy = True
        self.info_btn.setEnabled(False)
        self.tab_options.set_tools_running(True)
        self.set_status("Preparing tools (yt-dlp, ffmpeg)…")
        update = force or flag(self.settings, "auto_update")
        self.tools_ctx = self.tools_runner.start(update, force)

    def update_tools_now(self) -> None:
        if self.tab_queue.runner.is_running():
            dialogs.info(self, "Running", "Wait for the running job to finish (or cancel it) first.")
            return
        self.start_tools_setup(force=True)

    def on_tools_done(self, error: str) -> None:
        self.tools_busy = False
        self.tools_ctx = None
        self.info_btn.setEnabled(True)
        self.tab_options.set_tools_running(False)
        self.set_progress(0, "")
        if error:
            self.log(f"Tools: {error}")
            self.set_status("Some tools are missing. See the log.")
            dialogs.warning(self, "Tools", error)
        else:
            self.set_status(READY_TEXT)

    # ---------------------------- the overlay of a saved chat ---------------------------- #
    def render_saved_chat(self) -> None:
        """Options → Chat → «Draw the overlay from a saved chat»: pick a «.chat.json», confirm, draw it (no download)."""
        if self.tab_queue.runner.is_running() or self.tools_busy or self.saved_chat_busy:
            dialogs.info(self, "Busy", "Wait for the running job (or the tools setup) to finish first.")
            return
        opts = self.build_options()
        folder = Path(opts.out_dir)
        path = dialogs.open_file(self, "Choose a saved chat (.chat.json)", str(folder) if folder.is_dir() else "",
                                 "Chat files (*.json);;All files (*.*)")
        if not path:
            return
        chat = Path(path)
        try:
            summary = describe_chat_overlay(chat, opts)
        except EngineError as e:
            dialogs.error(self, "Chat overlay", str(e))
            return
        if not dialogs.ask_ok_cancel(self, "Draw the chat overlay?", summary + "\n\nIt can take a while for a long chat."):
            return
        self.start_saved_chat_render(chat, opts)

    def start_saved_chat_render(self, chat: Path, opts) -> None:
        self.saved_chat_busy = True
        self.tab_queue.set_running(True)  # «Start queue» off, «Cancel current» on (the log and the button live there)
        self.tab_options.set_saved_chat_running(True)
        self.show_queue_tab()
        self.set_status("Chat overlay…")
        self.saved_chat_ctx = self.saved_chat_runner.start(chat, opts)

    def cancel_saved_chat(self) -> bool:
        """«Cancel current» while an overlay is being drawn. False when there is none."""
        if self.saved_chat_ctx is None:
            return False
        self.saved_chat_ctx.cancel()
        return True

    def on_saved_chat_done(self, out: str, error: str) -> None:
        self.saved_chat_busy = False
        self.saved_chat_ctx = None
        self.tab_queue.set_running(False)
        self.tab_options.set_saved_chat_running(False)
        self.set_progress(0, "")
        if error:
            cancelled = error == "Cancelled."
            self.log("Cancelled." if cancelled else f"Chat overlay: {error}")
            self.set_status("Chat overlay cancelled." if cancelled else "Chat overlay failed. See the log.")
            if not cancelled:
                dialogs.error(self, "Chat overlay", error)
        else:
            self.set_status(f"Chat overlay ready: {Path(out).name}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt name)
        if self.tools_ctx:
            self.tools_ctx.cancel()
        if self.saved_chat_ctx:
            self.saved_chat_ctx.cancel()  # no orphan ffmpeg / TwitchDownloaderCLI after the window is gone
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
