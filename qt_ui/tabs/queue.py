"""The Queue & log tab (Phase 3): the job table, its buttons, and the coloured log.

Port of ``build_queue_tab``, ``refresh_queue_summary``, ``enqueue``, ``set_item_status``, ``start_queue``,
``cancel_current``, ``remove_selected``, ``clear_finished``, ``open_queue_folder``, ``log``, ``clear_log`` and
``copy_log``. The tab owns the queue (``model``), the worker (``runner``) and the log; the main window connects the
parts that belong to the whole window (progress bar, status line, closing).

Hooks the main window sets (the defaults make the tab work on its own, which the tests use):
  ``blocked_reason()``  a status-bar sentence while the tools setup or a saved-chat overlay is busy, else ""
  ``output_dir()``      the output folder from the settings
Signals: ``status_message(str)`` (for the status line), ``plan_requested()`` («Go to the Plan tab»),
``show_requested()`` (select this tab when the queue starts).
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QTableView,
    QVBoxLayout, QWidget,
)

from core.files import open_in_file_manager
from core.palette import ERR, FG, MUTED, OK, WARN
from core.settings import DEFAULTS
from core.status import log_kind
from luckytwitch_engine import stream_dir
from qt_ui import dialogs
from qt_ui.bridge import Bridge
from qt_ui.queue_model import COLUMNS, IID_ROLE, QueueItem, QueueModel
from qt_ui.queue_runner import QueueRunner
from qt_ui.theme import mono_font
from qt_ui.widgets import Card, EmptyState, ScrollFrame

HEADER_HEIGHT = 34  # the column headings; the empty-state message starts under them
ROW_HEIGHT = 28
LOG_COLOURS = {"stamp": MUTED, "muted": MUTED, "err": ERR, "warn": WARN, "ok": OK, "plain": FG}


class LogView(QPlainTextEdit):
    """Read-only log: «[hh:mm:ss] » in muted grey, then the message coloured by its kind; follows the newest line."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("logView")
        self.setReadOnly(True)
        self.setFont(mono_font())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.setMinimumHeight(8 * self.fontMetrics().lineSpacing() + 16)  # tkinter: height=8 lines
        self._formats: dict[str, QTextCharFormat] = {}
        for kind, colour in LOG_COLOURS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            self._formats[kind] = fmt

    def add_line(self, msg: str) -> None:
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"[{time.strftime('%H:%M:%S')}] ", self._formats["stamp"])
        cursor.insertText(f"{msg}\n", self._formats[log_kind(msg)])
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        self.clear()

    def log_text(self) -> str:
        return self.toPlainText().rstrip("\n")


class QueueTab(QWidget):
    status_message = Signal(str)
    plan_requested = Signal()
    show_requested = Signal()

    def __init__(self, bridge: Bridge | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("QueueTab")
        self.bridge = bridge if bridge is not None else Bridge(self)
        self.model = QueueModel(self)
        self.runner = QueueRunner(self.bridge, self)
        self.blocked_reason = lambda: ""
        self.output_dir = lambda: DEFAULTS["out_dir"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollFrame(8, self)  # scrolls when the window is too short, like the tkinter ScrollFrame
        self.scroll.body_layout.setSpacing(10)
        outer.addWidget(self.scroll)
        self._build_queue_card()
        self._build_log_card()

        self.bridge.log.connect(self.log)
        self.bridge.item.connect(self.set_item_status)
        self.bridge.queue_done.connect(self.on_queue_done)
        self.refresh_summary()

    # ---------------------------- building ---------------------------- #
    def _build_queue_card(self) -> None:
        self.queue_card = Card("Queue")
        self.scroll.body_layout.addWidget(self.queue_card, 1)
        self.summary_label = QLabel("")
        self.summary_label.setProperty("role", "muted")
        self.summary_label.setContentsMargins(0, 0, 0, 8)
        self.queue_card.add_widget(self.summary_label)

        self.table = QTableView()
        self.table.setObjectName("queueTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        head = self.table.horizontalHeader()
        head.setFixedHeight(HEADER_HEIGHT)
        head.setHighlightSections(False)
        head.setSectionsClickable(False)
        for col, (_key, _text, width, _anchor, stretch) in enumerate(COLUMNS):
            head.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch if stretch else QHeaderView.ResizeMode.Fixed)
            if not stretch:
                head.resizeSection(col, width)
        self.table.setMinimumHeight(HEADER_HEIGHT + 6 * ROW_HEIGHT + 2)  # tkinter: height=6 rows
        self.queue_card.add_widget(self.table)
        self.empty = EmptyState(self.table, top=HEADER_HEIGHT)  # under the column headings
        self.queue_card.body_layout.setStretchFactor(self.table, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 10, 0, 0)
        buttons.setSpacing(6)
        self.start_btn = QPushButton("Start queue")
        self.start_btn.setProperty("variant", "accent")
        self.start_btn.clicked.connect(self.start_queue)
        self.cancel_btn = QPushButton("Cancel current")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_current)
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Clear finished")
        self.clear_btn.clicked.connect(self.clear_finished)
        self.folder_btn = QPushButton("Open folder")
        self.folder_btn.clicked.connect(self.open_queue_folder)
        for b in (self.start_btn, self.cancel_btn, self.remove_btn, self.clear_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.folder_btn)
        self.queue_card.body_layout.addLayout(buttons)

    def _build_log_card(self) -> None:
        self.log_card = Card("Log")
        self.scroll.body_layout.addWidget(self.log_card, 1)
        self.log_view = LogView()
        self.log_card.add_widget(self.log_view)
        self.log_card.body_layout.setStretchFactor(self.log_view, 1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        buttons.setSpacing(6)
        buttons.addStretch(1)
        self.copy_btn = QPushButton("Copy log")
        self.copy_btn.clicked.connect(self.copy_log)
        self.clear_log_btn = QPushButton("Clear log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.clear_log_btn)
        self.log_card.body_layout.addLayout(buttons)

    # ---------------------------- the log ---------------------------- #
    def log(self, msg: str) -> None:
        self.log_view.add_line(msg)

    def clear_log(self) -> None:
        self.log_view.clear_log()

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.log_text())
        self.status_message.emit("Log copied to the clipboard.")

    # ---------------------------- the queue ---------------------------- #
    @property
    def items(self) -> list[QueueItem]:
        return self.model.items

    def refresh_summary(self) -> None:
        """The one-line count above the list, and the message over it while the queue is empty."""
        self.summary_label.setText(self.model.summary())
        if self.items:
            self.empty.hide_message()
        else:
            self.empty.show_message("Nothing in the queue yet",
                                    "Set your cut points in the Plan tab and press «Add to queue».",
                                    button=("Go to the Plan tab", self.plan_requested.emit))

    def enqueue(self, job: object, label: str, n_parts: int, strat: str) -> QueueItem:
        item = self.model.add(job, label, n_parts, strat)
        self.refresh_summary()
        self.log(f"Queued: {label} ({n_parts} parts, {strat})")
        return item

    def set_item_status(self, iid: str, status: str) -> None:
        self.model.set_status(iid, status)
        self.refresh_summary()

    def selected_iid(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        return self.model.index(rows[0].row(), 0).data(IID_ROLE) if rows else None

    def select_item(self, iid: str) -> None:
        row = self.model.row_of(iid)
        if row >= 0:
            self.table.selectionModel().select(
                self.model.index(row, 0),
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
            self.table.setCurrentIndex(self.model.index(row, 0))

    def remove_selected(self) -> None:
        iid = self.selected_iid()
        if iid is None:
            return
        it = self.model.find(iid)
        if it and it.status == "running":
            dialogs.info(self, "Running", "Cancel the running job first.")
            return
        self.model.remove(iid)
        self.refresh_summary()

    def clear_finished(self) -> None:
        self.model.clear_finished()
        self.refresh_summary()

    # ---------------------------- running ---------------------------- #
    def set_running(self, running: bool) -> None:
        """«Start queue» is off and «Cancel current» on while something runs (a job, or a saved-chat overlay)."""
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)

    def start_queue(self) -> None:
        if self.runner.is_running():
            return
        reason = self.blocked_reason()
        if reason:
            self.status_message.emit(reason)
            return
        todo = [it for it in self.items if it.status == "queued"]
        if not todo:
            self.status_message.emit("Nothing queued.")
            return
        self.show_requested.emit()
        self.set_running(True)
        self.runner.start(todo)

    def cancel_current(self) -> None:
        if self.runner.cancel():
            self.status_message.emit("Cancelling…")

    def on_queue_done(self) -> None:
        self.set_running(False)
        self.runner.finish()

    # ---------------------------- folders ---------------------------- #
    def open_output_folder(self, path: Path | None = None, select: bool = False) -> None:
        """Open the output folder (created if missing), or ``path`` when given."""
        target = Path(path) if path else Path(str(self.output_dir()).strip() or DEFAULTS["out_dir"])
        try:
            if not select:
                target.mkdir(parents=True, exist_ok=True)
            open_in_file_manager(target, select)
        except OSError as e:
            dialogs.info(self, "Open folder", f"Could not open:\n{target}\n\n{e}")

    def open_queue_folder(self) -> None:
        """Open where the selected queue item was saved (highlighting its first file); else the last finished item;
        else the output folder."""
        sel = self.selected_iid()
        item = self.model.find(sel) if sel else None
        if item is None:
            item = next((i for i in reversed(self.items) if i.files), None)
        if item:
            files = [Path(f) for f in item.files if Path(f).exists()]
            if files:
                self.open_output_folder(files[0], select=True)
                return
            try:  # not finished yet: its stream folder if it exists
                folder = stream_dir(item.job.source, item.job.opts)
                if folder.is_dir():
                    self.open_output_folder(folder)
                    return
            except Exception:  # noqa: BLE001
                pass
            self.open_output_folder(Path(item.job.opts.out_dir))
            return
        self.open_output_folder()
