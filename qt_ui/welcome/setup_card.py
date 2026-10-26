"""Essential Quick Setup Card for first-run configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core.palette import ACCENT, ACCENT_DIM, ACCENT_HOVER, BG, BG2, BG3, BORDER, BORDER_STRONG, FG, MUTED, OK, WHITE
from qt_ui.icons import icon


class QuickSetupCard(QFrame):
    """Semi-transparent container exposing the essential 3 first-run settings."""

    signin_requested = Signal()

    def __init__(
        self,
        initial_out_dir: str,
        initial_container: str = "mp4",
        is_signed_in: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("quickSetupCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(540)
        self.setStyleSheet(
            f"QFrame#quickSetupCard {{ "
            f"background-color: {BG2}; "
            f"border: 1px solid {BORDER_STRONG}; "
            f"border-radius: 12px; "
            f"}}"
        )

        self._out_dir = str(initial_out_dir)
        self._container = str(initial_container).lower()
        self._is_signed_in = bool(is_signed_in)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        # Card Heading
        head_row = QHBoxLayout()
        head_lbl = QLabel("QUICK SETUP (ESSENTIALS)", self)
        head_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 9pt; font-weight: bold; letter-spacing: 0.5px;")
        head_row.addWidget(head_lbl)
        head_row.addStretch(1)
        lay.addLayout(head_row)

        # 1. Download Folder
        dir_box = QVBoxLayout()
        dir_box.setSpacing(4)
        dir_title = QLabel("Download Folder:", self)
        dir_title.setStyleSheet("font-weight: bold;")
        dir_box.addWidget(dir_title)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_entry = QLineEdit(self)
        self.dir_entry.setText(self._out_dir)
        self.dir_entry.setReadOnly(True)
        self.dir_entry.setToolTip("Path where downloaded videos and clips are saved")
        dir_row.addWidget(self.dir_entry, 1)

        self.browse_btn = QPushButton("Browse\u2026", self)
        self.browse_btn.setProperty("variant", "ghost")
        self.browse_btn.setIcon(icon("folder", 14))
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_row.addWidget(self.browse_btn)
        dir_box.addLayout(dir_row)
        lay.addLayout(dir_box)

        # 2. Preferred Video Container Format (MP4 vs MKV)
        fmt_box = QVBoxLayout()
        fmt_box.setSpacing(4)
        fmt_title = QLabel("Preferred Format:", self)
        fmt_title.setStyleSheet("font-weight: bold;")
        fmt_box.addWidget(fmt_title)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)

        self.mp4_btn = QPushButton("MP4 (Universal && Premiere)", self)
        self.mp4_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mp4_btn.setToolTip("Best compatibility with video editors, media players, and mobile devices")
        self.mp4_btn.clicked.connect(lambda: self._set_container("mp4"))

        self.mkv_btn = QPushButton("MKV (Crash-Resistant)", self)
        self.mkv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mkv_btn.setToolTip("Stream-safe format: survives unexpected system crashes or power interruptions")
        self.mkv_btn.clicked.connect(lambda: self._set_container("mkv"))

        fmt_row.addWidget(self.mp4_btn, 1)
        fmt_row.addWidget(self.mkv_btn, 1)
        fmt_box.addLayout(fmt_row)
        lay.addLayout(fmt_box)

        # 3. Twitch Authentication (Optional)
        auth_box = QVBoxLayout()
        auth_box.setSpacing(4)
        auth_title = QLabel("Twitch Account (Optional):", self)
        auth_title.setStyleSheet("font-weight: bold;")
        auth_box.addWidget(auth_title)

        auth_row = QHBoxLayout()
        auth_row.setSpacing(8)

        self.auth_dot = QLabel("\u25cf" if self._is_signed_in else "\u25cb", self)
        self.auth_dot.setStyleSheet(f"color: {OK if self._is_signed_in else MUTED}; font-size: 11pt;")
        auth_row.addWidget(self.auth_dot)

        self.auth_status_lbl = QLabel("Signed in to Twitch" if self._is_signed_in else "Not signed in (Guest)", self)
        self.auth_status_lbl.setProperty("role", "muted")
        auth_row.addWidget(self.auth_status_lbl, 1)

        self.auth_btn = QPushButton("Manage Account\u2026" if self._is_signed_in else "Sign in with Twitch\u2026", self)
        self.auth_btn.setProperty("variant", "ghost")
        self.auth_btn.setIcon(icon("user", 14))
        self.auth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auth_btn.clicked.connect(self.signin_requested.emit)
        auth_row.addWidget(self.auth_btn)
        auth_box.addLayout(auth_row)
        lay.addLayout(auth_box)

        self._refresh_container_buttons()

    def _browse_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Download Folder", self._out_dir)
        if chosen:
            self._out_dir = chosen
            self.dir_entry.setText(chosen)

    def _set_container(self, fmt: str) -> None:
        self._container = fmt.lower()
        self._refresh_container_buttons()

    def _refresh_container_buttons(self) -> None:
        is_mp4 = self._container == "mp4"
        self.mp4_btn.setStyleSheet(
            f"background-color: {ACCENT_DIM if is_mp4 else BG3}; "
            f"color: {WHITE if is_mp4 else FG}; "
            f"border: 1px solid {ACCENT if is_mp4 else BORDER}; "
            f"font-weight: {'bold' if is_mp4 else 'normal'}; "
            f"padding: 7px 12px; border-radius: 6px;"
        )
        self.mkv_btn.setStyleSheet(
            f"background-color: {ACCENT_DIM if not is_mp4 else BG3}; "
            f"color: {WHITE if not is_mp4 else FG}; "
            f"border: 1px solid {ACCENT if not is_mp4 else BORDER}; "
            f"font-weight: {'bold' if not is_mp4 else 'normal'}; "
            f"padding: 7px 12px; border-radius: 6px;"
        )

    def set_signed_in(self, signed_in: bool) -> None:
        self._is_signed_in = bool(signed_in)
        self.auth_dot.setText("\u25cf" if self._is_signed_in else "\u25cb")
        self.auth_dot.setStyleSheet(f"color: {OK if self._is_signed_in else MUTED}; font-size: 11pt;")
        self.auth_status_lbl.setText("Signed in to Twitch" if self._is_signed_in else "Not signed in (Guest)")
        self.auth_btn.setText("Manage Account\u2026" if self._is_signed_in else "Sign in with Twitch\u2026")

    @property
    def selected_out_dir(self) -> str:
        return self._out_dir

    @property
    def selected_container(self) -> str:
        return self._container
