"""Message boxes and system pickers, in one place, so the tabs call ``dialogs.info(...)`` and the tests replace
these functions.

Phase 9h (H1, H2): Themed custom dialogs with dark surfaces, vector icons, expandable error details fold,
and one-click 'Copy details' button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
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
        from qt_ui.icons import icon
        from qt_ui.motion import DURATION_NORMAL, Motion, animate_height

        visible = not self.details_edit.isVisible()
        if not Motion.enabled():
            self.details_edit.setMaximumHeight(120 if visible else 0)
            self.details_edit.setVisible(visible)
            self.toggle_details_btn.setText("Hide details" if visible else "Show details")
            self.toggle_details_btn.setIcon(icon("chevron-down" if not visible else "x", 14))
            self.adjustSize()
            return

        if visible:
            self.details_edit.setMaximumHeight(0)
            self.details_edit.setVisible(True)
            self.toggle_details_btn.setText("Hide details")
            self.toggle_details_btn.setIcon(icon("x", 14))
            animate_height(
                self.details_edit,
                start_h=0,
                end_h=120,
                duration_ms=DURATION_NORMAL,
                on_finished=self.adjustSize,
            )
        else:
            self.toggle_details_btn.setText("Show details")
            self.toggle_details_btn.setIcon(icon("chevron-down", 14))

            def _after_collapse() -> None:
                self.details_edit.setVisible(False)
                self.adjustSize()

            animate_height(
                self.details_edit,
                start_h=self.details_edit.height(),
                end_h=0,
                duration_ms=DURATION_NORMAL,
                on_finished=_after_collapse,
            )

    def _copy_details(self) -> None:
        if self.copy_details_btn is None:
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(self._details_text or "")
            self.copy_details_btn.setText("Copied!")
            self.copy_details_btn.setIcon(icon("check", 14))
            btn = self.copy_details_btn
            def _reset() -> None:
                try:
                    btn.setText("Copy details")
                    btn.setIcon(icon("copy", 14))
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


class HistoryDialog(QDialog):
    """Download history dialog showing recorded downloads with options to open folder or load VOD."""

    vod_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("historyDialog")
        self.setWindowTitle("Download History")
        self.setModal(True)
        self.resize(760, 480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # Header row
        header = QHBoxLayout()
        title_lbl = QLabel("Download History", self)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title_lbl)

        header.addStretch(1)

        self.clear_btn = QPushButton("Clear history", self)
        self.clear_btn.setProperty("variant", "ghost")
        self.clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self.clear_btn)

        outer.addLayout(header)

        # Table
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Downloaded", "Streamer", "Title", "Parts", "Quality", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        outer.addWidget(self.table, 1)

        # Footer
        footer = QHBoxLayout()
        self.count_label = QLabel("", self)
        self.count_label.setProperty("role", "muted")
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        close_btn = QPushButton("Close", self)
        close_btn.setProperty("variant", "accent")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

        self.refresh()

    def refresh(self) -> None:
        from core import history
        from PySide6.QtWidgets import QTableWidgetItem, QWidget, QHBoxLayout, QPushButton
        from core.files import open_in_file_manager

        entries = history.load_history()
        self.table.setRowCount(len(entries))
        self.count_label.setText(f"{len(entries)} completed download(s)")

        for row, e in enumerate(entries):
            self.table.setItem(row, 0, QTableWidgetItem(e.downloaded_at))
            self.table.setItem(row, 1, QTableWidgetItem(e.streamer))
            self.table.setItem(row, 2, QTableWidgetItem(e.title))
            self.table.setItem(row, 3, QTableWidgetItem(str(e.parts)))
            self.table.setItem(row, 4, QTableWidgetItem(e.quality))

            actions_widget = QWidget(self.table)
            act_lay = QHBoxLayout(actions_widget)
            act_lay.setContentsMargins(4, 2, 4, 2)
            act_lay.setSpacing(6)

            if e.folder:
                f_btn = QPushButton("Folder", actions_widget)
                f_btn.setProperty("variant", "ghost")
                f_btn.clicked.connect(lambda _, p=e.folder: open_in_file_manager(p))
                act_lay.addWidget(f_btn)

            if e.vod_id:
                load_btn = QPushButton("Load", actions_widget)
                load_btn.setProperty("variant", "ghost")
                load_btn.clicked.connect(lambda _, vid=e.vod_id: self._load_vod(vid))
                act_lay.addWidget(load_btn)

            self.table.setCellWidget(row, 5, actions_widget)

    def _load_vod(self, vod_id: str) -> None:
        url = f"https://www.twitch.tv/videos/{vod_id}"
        self.vod_requested.emit(url)
        self.accept()

    def _on_clear(self) -> None:
        from core import history
        history.clear_history()
        self.refresh()
