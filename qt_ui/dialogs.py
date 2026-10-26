"""Message boxes, in one place, so the tabs call ``dialogs.info(...)`` and the tests replace these functions.

Same titles and texts as the tkinter app's ``messagebox`` calls; the dialogs are modal and belong to ``parent``.
GUI thread only (a worker thread reports through a Bridge signal and the slot opens the box).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def info(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def warning(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def error(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def ask_yes_no(parent: QWidget | None, title: str, text: str) -> bool:
    """«Yes» / «No» question (tkinter ``askyesno``). Escape and closing the box answer No."""
    answer = QMessageBox.question(parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes


def ask_ok_cancel(parent: QWidget | None, title: str, text: str) -> bool:
    """«OK» / «Cancel» question (tkinter ``askokcancel``)."""
    answer = QMessageBox.question(parent, title, text,
                                  QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                  QMessageBox.StandardButton.Ok)
    return answer == QMessageBox.StandardButton.Ok


def choose_folder(parent: QWidget | None, title: str, start: str = "") -> str:
    """The system's folder picker (tkinter ``askdirectory``). ``""`` when the person cancels."""
    return QFileDialog.getExistingDirectory(parent, title, start)


def open_file(parent: QWidget | None, title: str, start: str = "", name_filter: str = "All files (*.*)") -> str:
    """The system's file picker (tkinter ``askopenfilename``). ``name_filter`` like «Chat files (*.json);;All files (*.*)».
    ``""`` when the person cancels."""
    path, _chosen = QFileDialog.getOpenFileName(parent, title, start, name_filter)
    return path


def save_file(parent: QWidget | None, title: str, start: str = "", name_filter: str = "Text files (*.txt);;All files (*.*)") -> str:
    """The system's save-file picker (Phase 9c, F3 «Save log…»). ``""`` when the person cancels."""
    path, _chosen = QFileDialog.getSaveFileName(parent, title, start, name_filter)
    return path
