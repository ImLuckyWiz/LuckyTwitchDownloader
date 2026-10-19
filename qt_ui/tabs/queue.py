"""The Queue & log tab. Empty placeholder (Phase 1); built in Phase 3."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class QueueTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("QueueTab")
