"""The Options tab. Empty placeholder (Phase 1); built in Phase 5."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class OptionsTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OptionsTab")
