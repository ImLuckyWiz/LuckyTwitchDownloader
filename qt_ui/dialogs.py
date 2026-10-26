"""Message boxes and system pickers, in one place, so the tabs call ``dialogs.info(...)`` and the tests replace
these functions.

Phase 9h (H1, H2): Themed custom dialogs with dark surfaces, vector icons, expandable error details fold,
and one-click 'Copy details' button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from core.palette import ACCENT, ERR, MUTED
from qt_ui.icons import icon, pixmap
from qt_ui.theme import mono_font


class ThemedDialog(QDialog):
    """Modern themed modal dialog with vector icon, summary, optional collapsible technical details,
    and styled action buttons (Phase 9h, H1, H2)."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        text: str,
        icon_name: str = "info",
        icon_colour: str = ACCENT,
        details: str | None = None,
        buttons: tuple[tuple[str, str, bool], ...] = (("OK", "accent", True),),
    ):
        super().__init__(parent)
        self.setObjectName("themedDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setMaximumWidth(540)

        # Parse text into summary and details if details not explicitly given
        summary = text
        auto_details = details
        if auto_details is None and "\n" in text:
            parts = text.split("\n", 1)
            summary = parts[0].strip()
            auto_details = parts[1].strip()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 16)
        outer.setSpacing(14)

        # Header: Icon + Title & Summary
        head = QHBoxLayout()
        head.setSpacing(14)
        head.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setPixmap(pixmap(icon_name, 28, icon_colour, dpr=1.0))
        self.icon_lbl.setFixedSize(32, 32)
        head.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(6)
        self.title_lbl = QLabel(title, self)
        font = self.title_lbl.font()
        font.setPointSize(11)
        font.setBold(True)
        self.title_lbl.setFont(font)
        text_box.addWidget(self.title_lbl)

        self.summary_lbl = QLabel(summary, self)
        self.summary_lbl.setWordWrap(True)
        text_box.addWidget(self.summary_lbl)
        head.addLayout(text_box, 1)
        outer.addLayout(head)

        # Optional Collapsible Details (H2)
        self._details_text = auto_details
        self.toggle_details_btn: QPushButton | None = None
        self.copy_details_btn: QPushButton | None = None
        self.details_edit: QPlainTextEdit | None = None

        if auto_details:
            details_bar = QHBoxLayout()
            details_bar.setSpacing(8)
            self.toggle_details_btn = QPushButton("Show details", self)
            self.toggle_details_btn.setProperty("variant", "ghost")
            self.toggle_details_btn.setIcon(icon("chevron-down", 14))
            self.toggle_details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.toggle_details_btn.clicked.connect(self._toggle_details)
            details_bar.addWidget(self.toggle_details_btn)

            details_bar.addStretch(1)

            self.copy_details_btn = QPushButton("Copy details", self)
            self.copy_details_btn.setProperty("variant", "ghost")
            self.copy_details_btn.setIcon(icon("copy", 14))
            self.copy_details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.copy_details_btn.clicked.connect(self._copy_details)
            details_bar.addWidget(self.copy_details_btn)
            outer.addLayout(details_bar)

            self.details_edit = QPlainTextEdit(self)
            self.details_edit.setObjectName("dialogDetails")
            self.details_edit.setPlainText(auto_details)
            self.details_edit.setReadOnly(True)
            self.details_edit.setFont(mono_font())
            self.details_edit.setFixedHeight(120)
            self.details_edit.setVisible(False)
            outer.addWidget(self.details_edit)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)
        self.action_buttons: list[QPushButton] = []
        for btn_label, variant, is_accept in buttons:
            btn = QPushButton(btn_label, self)
            if variant:
                btn.setProperty("variant", variant)
            if is_accept:
                btn.setDefault(True)
                btn.clicked.connect(self.accept)
            else:
                btn.clicked.connect(self.reject)
            btn_row.addWidget(btn)
            self.action_buttons.append(btn)
        outer.addLayout(btn_row)

    def _toggle_details(self) -> None:
        if self.details_edit is None or self.toggle_details_btn is None:
            return
        visible = not self.details_edit.isVisible()
        self.details_edit.setVisible(visible)
        self.toggle_details_btn.setText("Hide details" if visible else "Show details")
        self.toggle_details_btn.setIcon(icon("chevron-down" if not visible else "x", 14))
        self.adjustSize()

    def _copy_details(self) -> None:
        if self.copy_details_btn is None:
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(self._details_text or "")
            self.copy_details_btn.setText("Copied!")
            btn = self.copy_details_btn
            def _reset() -> None:
                try:
                    btn.setText("Copy details")
                except (RuntimeError, ReferenceError):
                    pass
            QTimer.singleShot(1500, _reset)


def info(parent: QWidget | None, title: str, text: str) -> None:
    ThemedDialog(parent, title, text, icon_name="info", icon_colour=ACCENT, buttons=(("OK", "accent", True),)).exec()


def warning(parent: QWidget | None, title: str, text: str) -> None:
    ThemedDialog(parent, title, text, icon_name="alert", icon_colour="#f59e0b", buttons=(("OK", "accent", True),)).exec()


def error(parent: QWidget | None, title: str, text: str, details: str | None = None) -> None:
    ThemedDialog(parent, title, text, icon_name="alert", icon_colour=ERR, details=details, buttons=(("OK", "destructive", True),)).exec()


def ask_yes_no(parent: QWidget | None, title: str, text: str, destructive: bool = False) -> bool:
    """«Yes» / «No» question (tkinter ``askyesno``). Escape and closing the box answer No."""
    dlg = ThemedDialog(
        parent, title, text,
        icon_name="alert" if destructive else "info",
        icon_colour=ERR if destructive else ACCENT,
        buttons=(("No", "ghost", False), ("Yes", "destructive" if destructive else "accent", True)),
    )
    return dlg.exec() == QDialog.DialogCode.Accepted


def ask_ok_cancel(parent: QWidget | None, title: str, text: str, destructive: bool = False) -> bool:
    """«OK» / «Cancel» question (tkinter ``askokcancel``)."""
    dlg = ThemedDialog(
        parent, title, text,
        icon_name="alert" if destructive else "info",
        icon_colour=ERR if destructive else ACCENT,
        buttons=(("Cancel", "ghost", False), ("OK", "destructive" if destructive else "accent", True)),
    )
    return dlg.exec() == QDialog.DialogCode.Accepted


def choose_folder(parent: QWidget | None, title: str, start: str = "") -> str:
    """The system's folder picker (tkinter ``askdirectory``). ``""`` when the person cancels."""
    return QFileDialog.getExistingDirectory(parent, title, start)


def open_file(parent: QWidget | None, title: str, start: str = "", name_filter: str = "All files (*.*)") -> str:
    """The system's file picker (tkinter ``askopenfilename``). ``""`` when the person cancels."""
    path, _chosen = QFileDialog.getOpenFileName(parent, title, start, name_filter)
    return path


def save_file(parent: QWidget | None, title: str, start: str = "", name_filter: str = "Text files (*.txt);;All files (*.*)") -> str:
    """The system's save-file picker (Phase 9c, F3 «Save log…»). ``""`` when the person cancels."""
    path, _chosen = QFileDialog.getSaveFileName(parent, title, start, name_filter)
    return path
