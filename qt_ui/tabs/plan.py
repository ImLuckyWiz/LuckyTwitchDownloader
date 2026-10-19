"""The Plan tab. Empty placeholder (Phase 1); built in Phase 6."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class PlanTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PlanTab")
