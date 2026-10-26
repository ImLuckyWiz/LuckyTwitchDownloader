"""The «Twitch API» dialog: sign in with a Twitch account (device code) or save an own Twitch app.

Port of ``App.ask_credentials``. The sign-in waits for the person to approve a code on twitch.tv/activate, so it
runs on a daemon thread; the thread reports through ``LoginSignals`` (code, ok, error, cancelled: the messages of
the tkinter dialog's own queue) and the slots run on the GUI thread. Closing the dialog (button, window X, Escape)
sets the cancel event, so the thread stops within a quarter of a second, and an answer that arrives later is
dropped.

The dialog talks to the main window through a ``host`` with ``client`` (read and write), ``set_status(text)`` and
``update_search_state()``. The names ``device_login_start``, ``device_login_poll``, ``webbrowser`` and the config
functions are looked up in this module, so tests replace them (no network, no browser).
"""

from __future__ import annotations

import threading
import webbrowser

import requests
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core import paths
from core.config import (
    clear_credentials, load_credentials, make_client, read_config, save_credentials, save_login_tokens,
)
from luckytwitch_engine import Cancelled, TwitchClient, device_login_poll, device_login_start
from qt_ui import dialogs
from qt_ui.theme import dark_titlebar, mono_font
from qt_ui.widgets import WrapLabel

TITLE = "Twitch API"
INTRO = ("Optional: only needed to fetch clips (clips → chapters).\n"
         "Sign in with your Twitch account: no developer app needed.")
WAITING_TEXT = ("A browser tab opened. Enter this code on twitch.tv/activate\n"
                "and press Authorize. Waiting for you…")
STATUS_WIDTH = 470  # tkinter: wraplength=470
ACTIVATE_URL = "https://www.twitch.tv/activate"


class LoginSignals(QObject):
    """What the sign-in thread tells the dialog. Not parented to the dialog: the thread may outlive it by a moment,
    and an object that was deleted under it would make ``emit`` raise."""

    code = Signal(str, str)  # (user code, page to enter it on)
    ok = Signal(str, str)  # (access token, refresh token)
    error = Signal(str)
    cancelled = Signal()


class TwitchDialog(QDialog):
    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self.setWindowTitle(TITLE)
        self.setModal(True)
        self.state = {"busy": False, "url": ""}
        self.cancel_ev = threading.Event()
        self.closed = False
        self.signals = LoginSignals()
        self.signals.code.connect(self.on_code)
        self.signals.ok.connect(self.finish_login)
        self.signals.error.connect(self.fail_login)
        self.signals.cancelled.connect(self.on_cancelled)

        box = QVBoxLayout(self)
        box.setContentsMargins(15, 15, 15, 15)
        box.setSpacing(0)
        box.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)  # tkinter: not resizable

        box.addWidget(QLabel(INTRO))
        self.status_label = WrapLabel("")
        self.status_label.setFixedWidth(STATUS_WIDTH)
        self.status_label.setContentsMargins(0, 10, 0, 2)
        box.addWidget(self.status_label)
        self.code_card = QWidget()
        code_box = QHBoxLayout(self.code_card)
        code_box.setContentsMargins(0, 4, 0, 4)
        code_box.setSpacing(8)
        self.code_label = QLabel("")
        self.code_label.setObjectName("loginCode")
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        font = mono_font()
        font.setPointSize(18)
        font.setBold(True)
        self.code_label.setFont(font)
        self.code_label.setContentsMargins(0, 2, 0, 2)
        self.code_label.setMinimumHeight(self.code_label.fontMetrics().lineSpacing() + 4)
        code_box.addStretch(1)
        code_box.addWidget(self.code_label)
        from qt_ui.icons import icon
        from PySide6.QtWidgets import QToolButton
        self.copy_code_btn = QToolButton()
        self.copy_code_btn.setText("Copy code")
        self.copy_code_btn.setIcon(icon("copy", 14))
        self.copy_code_btn.setProperty("variant", "ghost")
        self.copy_code_btn.setVisible(False)
        self.copy_code_btn.clicked.connect(self.copy_code)
        code_box.addWidget(self.copy_code_btn)
        code_box.addStretch(1)
        box.addWidget(self.code_card)

        login_row = QHBoxLayout()
        login_row.setContentsMargins(0, 6, 0, 0)
        login_row.setSpacing(6)
        self.login_btn = QPushButton("Sign in with Twitch")
        self.login_btn.clicked.connect(self.start_login)
        self.page_btn = QPushButton("Open page again")
        self.page_btn.clicked.connect(self.open_page)
        self.logout_btn = QPushButton("Sign out")
        self.logout_btn.clicked.connect(self.do_logout)
        for b in (self.login_btn, self.page_btn, self.logout_btn):
            login_row.addWidget(b)
        login_row.addStretch(1)
        box.addLayout(login_row)

        # --- advanced: own Twitch app --- #
        adv = QGroupBox("Advanced: use your own Twitch app instead")
        grid = QGridLayout(adv)
        grid.setContentsMargins(10, 10, 10, 10)
        cfg = load_credentials() or {}
        self.id_edit = QLineEdit(cfg.get("client_id", ""))
        self.sec_edit = QLineEdit(cfg.get("client_secret", ""))
        self.sec_edit.setEchoMode(QLineEdit.EchoMode.Password)
        entry_width = self.fontMetrics().averageCharWidth() * 44 + 16  # tkinter: width=44 characters
        for edit in (self.id_edit, self.sec_edit):
            edit.setMinimumWidth(entry_width)
        grid.addWidget(QLabel("Client ID:"), 0, 0, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.id_edit, 0, 1)
        grid.addWidget(QLabel("Client Secret:"), 1, 0, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.sec_edit, 1, 1)
        self.save_btn = QPushButton("Save own app")
        self.save_btn.clicked.connect(self.save)
        grid.addWidget(self.save_btn, 2, 0, 1, 2, Qt.AlignmentFlag.AlignRight)
        grid.setVerticalSpacing(6)
        holder = QVBoxLayout()
        holder.setContentsMargins(0, 16, 0, 0)
        holder.addWidget(adv)
        box.addLayout(holder)

        self.path_label = QLabel(f"Saved in: {paths.CONFIG_PATH}")
        self.path_label.setProperty("role", "muted")
        self.path_label.setContentsMargins(0, 10, 0, 0)
        box.addWidget(self.path_label)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        close_row = QHBoxLayout()
        close_row.setContentsMargins(0, 10, 0, 0)
        close_row.addStretch(1)
        close_row.addWidget(self.close_btn)
        box.addLayout(close_row)

        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)  # Enter in a field must not press a button (tkinter: nothing happens)
        self.refresh_status()
        dark_titlebar(self)

    # ---------------------------- what is saved ---------------------------- #
    @staticmethod
    def signed_in() -> bool:
        return bool(read_config().get("refresh_token")) and not load_credentials()

    def refresh_status(self) -> None:
        if load_credentials():
            self.status_label.setText("Using your own Twitch app (Client ID / Secret below).")
        elif self.signed_in():
            self.status_label.setText("✔ Signed in with Twitch. Clips are available.")
        else:
            self.status_label.setText("Not signed in.")
        self.login_btn.setText("Sign in again" if self.signed_in() else "Sign in with Twitch")
        self.logout_btn.setEnabled(bool(self.signed_in() or load_credentials()))
        self.host.update_search_state()  # show / hide the «sign in» warning of the Search tab

    # ---------------------------- signing in ---------------------------- #
    def start_login(self) -> None:
        if self.state["busy"]:
            return
        self.state["busy"] = True
        self.cancel_ev.clear()
        self.login_btn.setEnabled(False)
        self.status_label.setText("Contacting Twitch…")
        signals, cancel_ev = self.signals, self.cancel_ev

        def work():
            try:
                start = device_login_start()
                url = start.get("verification_uri") or ACTIVATE_URL
                signals.code.emit(start.get("user_code", ""), url)
                try:
                    webbrowser.open(url)
                except Exception:  # noqa: BLE001
                    pass
                access, refresh = device_login_poll(start, cancel=cancel_ev)
                signals.ok.emit(access, refresh)
            except Cancelled:
                signals.cancelled.emit()
            except Exception as e:  # noqa: BLE001
                signals.error.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_code(self, user_code: str, url: str) -> None:
        if self.closed:
            return
        self.state["url"] = url
        self.code_label.setText(user_code)
        if hasattr(self, "copy_code_btn"):
            self.copy_code_btn.setVisible(bool(user_code))
        self.status_label.setText(WAITING_TEXT)
    def copy_code(self) -> None:
        code = self.code_label.text().strip()
        if code:
            from PySide6.QtWidgets import QApplication
            from qt_ui.icons import icon
            QApplication.clipboard().setText(code)
            self.copy_code_btn.setText("Copied!")
            self.copy_code_btn.setIcon(icon("check", 14))
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: (self.copy_code_btn.setText("Copy code"), self.copy_code_btn.setIcon(icon("copy", 14))) if not self.closed else None)


    def finish_login(self, access: str, refresh: str) -> None:
        if self.closed:
            return  # the dialog was closed meanwhile: nothing is saved
        clear_credentials()  # the signed-in account replaces a previous own-app setup
        save_login_tokens(access, refresh)
        self.host.client = make_client()
        self.code_label.setText("")
        if hasattr(self, "copy_code_btn"):
            self.copy_code_btn.setVisible(False)
        self.state["busy"] = False
        self.login_btn.setEnabled(True)
        self.host.set_status("Signed in with Twitch.")
        self.refresh_status()

    def fail_login(self, msg: str) -> None:
        if self.closed:
            return
        self.code_label.setText("")
        if hasattr(self, "copy_code_btn"):
            self.copy_code_btn.setVisible(False)
        self.state["busy"] = False
        self.login_btn.setEnabled(True)
        self.refresh_status()
        dialogs.error(self, "Twitch sign-in", msg)

    def on_cancelled(self) -> None:
        if self.closed:
            return
        self.code_label.setText("")
        if hasattr(self, "copy_code_btn"):
            self.copy_code_btn.setVisible(False)
        self.state["busy"] = False
        self.login_btn.setEnabled(True)
        self.refresh_status()

    def open_page(self) -> None:
        if self.state["url"]:
            webbrowser.open(self.state["url"])

    def do_logout(self) -> None:
        save_login_tokens(None, None)
        clear_credentials()
        self.host.client = None
        self.id_edit.setText("")
        self.sec_edit.setText("")
        self.host.set_status("Twitch account removed.")
        self.refresh_status()

    # ---------------------------- an own Twitch app ---------------------------- #
    def save(self) -> None:
        cid, sec = self.id_edit.text().strip(), self.sec_edit.text().strip()
        if not cid or not sec:
            dialogs.warning(self, "Missing data", "Fill in both fields.")
            return
        test = TwitchClient(cid, sec)
        try:
            test.refresh_token()
        except ValueError as e:
            dialogs.error(self, "Error", str(e))
            return
        except requests.RequestException as e:
            dialogs.error(self, "Network error", str(e))
            return
        save_login_tokens(None, None)  # own app replaces a signed-in account
        save_credentials(cid, sec)
        self.host.client = test
        self.host.set_status("Twitch API credentials saved.")
        self.refresh_status()

    # ---------------------------- closing ---------------------------- #
    def done(self, result: int) -> None:  # noqa: D401 (Qt name) every way of closing ends up here
        self.cancel_ev.set()
        self.closed = True
        super().done(result)
