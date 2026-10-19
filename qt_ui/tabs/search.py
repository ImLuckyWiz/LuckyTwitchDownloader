"""The Search tab. Empty placeholder (Phase 1); built in Phase 4."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class SearchTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SearchTab")
