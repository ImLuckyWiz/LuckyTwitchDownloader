"""Non-modal toast cards stacked at the bottom-right of the window (Phase 9b, B5).

Auto-dismisses after ``DURATION_MS`` (4 000 ms), pauses the countdown while hovered, and supports
an optional action button (e.g. «Open folder», «Go to Queue») and a «\u2715» close button.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.palette import ACCENT, ERR, OK, WARN

KIND_COLOURS = {
    "info": ACCENT,
    "success": OK,
    "ok": OK,
    "warning": WARN,
    "warn": WARN,
    "error": ERR,
}


class ToastCard(QFrame):
    """A single non-modal notification card."""

    closed = Signal(object)  # emits self when dismissed

    DURATION_MS = 4000
    WIDTH = 340

    def __init__(
        self,
        title: str,
        message: str = "",
        kind: str = "info",
        action: tuple[str, Callable[[], None]] | None = None,
        duration_ms: int = DURATION_MS,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("toastCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.title = title
        self.message = message
        self.kind = kind
        self.duration_ms = duration_ms
        self._hovered = False
        self.setFixedWidth(self.WIDTH)

        colour = KIND_COLOURS.get(kind, ACCENT)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 10, 0)
        root.setSpacing(10)

        self.stripe = QFrame(self)
        self.stripe.setFixedWidth(4)
        self.stripe.setStyleSheet(f"background-color: {colour}; border-top-left-radius: 7px; border-bottom-left-radius: 7px;")
        root.addWidget(self.stripe)

        body = QWidget(self)
        blay = QVBoxLayout(body)
        blay.setContentsMargins(0, 8, 0, 8)
        blay.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self.title_label = QLabel(title, body)
        self.title_label.setProperty("role", "rowtitle")
        top.addWidget(self.title_label, 1)

        self.close_btn = QPushButton("\u2715", body)
        self.close_btn.setProperty("variant", "ghost")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setAccessibleName("Dismiss notification")
        self.close_btn.clicked.connect(self.dismiss)
        top.addWidget(self.close_btn)
        blay.addLayout(top)

        self.message_label: QLabel | None = None
        if message:
            self.message_label = QLabel(message, body)
            self.message_label.setProperty("role", "muted")
            self.message_label.setWordWrap(True)
            blay.addWidget(self.message_label)

        self.action_btn: QPushButton | None = None
        if action is not None:
            label, callback = action
            arow = QHBoxLayout()
            arow.setContentsMargins(0, 4, 0, 0)
            self.action_btn = QPushButton(label, body)
            self.action_btn.setProperty("variant", "chip")
            self.action_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)

            def _trigger() -> None:
                try:
                    callback()
                finally:
                    self.dismiss()

            self.action_btn.clicked.connect(_trigger)
            arow.addWidget(self.action_btn)
            arow.addStretch(1)
            blay.addLayout(arow)

        root.addWidget(body, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        if duration_ms > 0:
            self._timer.start(duration_ms)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        if self.duration_ms > 0:
            self._timer.start(self.duration_ms)
        super().leaveEvent(event)

    def set_hovered(self, hovered: bool) -> None:
        """Test helper for pausing/resuming auto-dismiss without a real mouse pointer."""
        self._hovered = hovered
        if hovered:
            self._timer.stop()
        elif self.duration_ms > 0:
            self._timer.start(self.duration_ms)

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()
        self.closed.emit(self)
        self.deleteLater()


class ToastHost(QObject):
    """Manages a vertical stack of ``ToastCard`` widgets anchored to the bottom-right of ``window``."""

    MARGIN_RIGHT = 16
    MARGIN_BOTTOM = 38  # above the 28 px status bar
    GAP = 8
    MAX_VISIBLE = 3

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.window = window
        self.toasts: list[ToastCard] = []
        window.installEventFilter(self)

    def show_toast(
        self,
        title: str,
        message: str = "",
        kind: str = "info",
        action: tuple[str, Callable[[], None]] | None = None,
        duration_ms: int = ToastCard.DURATION_MS,
    ) -> ToastCard:
        while len(self.toasts) >= self.MAX_VISIBLE:
            oldest = self.toasts.pop(0)
            oldest.dismiss()
        card = ToastCard(title, message, kind=kind, action=action, duration_ms=duration_ms, parent=self.window)
        card.closed.connect(self._on_closed)
        self.toasts.append(card)
        card.adjustSize()
        card.show()
        card.raise_()
        self.reposition()
        return card

    def clear(self) -> None:
        for card in list(self.toasts):
            card.dismiss()
        self.toasts.clear()

    def _on_closed(self, card: ToastCard) -> None:
        if card in self.toasts:
            self.toasts.remove(card)
        self.reposition()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.window and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.reposition()
        return super().eventFilter(watched, event)

    def reposition(self) -> None:
        if not self.toasts:
            return
        w = self.window.width()
        y = self.window.height() - self.MARGIN_BOTTOM
        for card in reversed(self.toasts):
            card.adjustSize()
            ch = card.sizeHint().height()
            card.resize(card.WIDTH, ch)
            y -= ch
            x = max(8, w - card.WIDTH - self.MARGIN_RIGHT)
            card.move(QPoint(x, max(8, y)))
            card.raise_()
            y -= self.GAP
