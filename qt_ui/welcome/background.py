"""Atmospheric animated background canvas for the Welcome & Quick Setup experience."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from core.palette import BG
from qt_ui.motion import DURATION_PULSE, Motion, animate_value


class AnimatedCanvas(QWidget):
    """Draws deep charcoal canvas + dynamic ambient radial glow behind hero branding."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._glow_alpha_mult = 1.0 if not Motion.enabled() else 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._on_tick)

    def start_bloom(self, duration_ms: int = 300) -> None:
        """Bloom in the ambient radial glow."""
        if not Motion.enabled() or not self.isVisible() or duration_ms <= 0:
            self._glow_alpha_mult = 1.0
            self.update()
            return

        def _update(val: float) -> None:
            self._glow_alpha_mult = float(val)
            self.update()

        animate_value(self, 0.0, 1.0, duration_ms=duration_ms, on_update=_update)
        if not self._timer.isActive():
            self._timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if Motion.enabled() and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()

    def _on_tick(self) -> None:
        if not Motion.enabled():
            self._timer.stop()
            return
        self._phase = (self._phase + 0.04) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        # 1. Base deep background
        p.fillRect(QRectF(0, 0, w, h), QColor(BG))

        # 2. Ambient radial glow (centered slightly above middle, behind hero icon)
        cx = w / 2.0
        cy = max(140.0, h * 0.28)

        base_radius = min(w * 0.45, 360.0)
        pulse = math.sin(self._phase) if (Motion.enabled() and self._timer.isActive()) else 0.0
        radius = base_radius + 15.0 * pulse

        grad = QRadialGradient(QPointF(cx, cy), radius)

        # Twitch Purple (#9146ff) center -> Emerald (#6bd49a) ring -> transparent outer
        alpha_factor = self._glow_alpha_mult * (0.18 + 0.05 * pulse)
        purple_alpha = max(0, min(255, int(255 * alpha_factor)))
        emerald_alpha = max(0, min(255, int(180 * alpha_factor * 0.7)))

        c_purple = QColor(145, 70, 255, purple_alpha)
        c_emerald = QColor(107, 212, 154, emerald_alpha)
        c_transparent = QColor(30, 31, 34, 0)

        grad.setColorAt(0.0, c_purple)
        grad.setColorAt(0.45, c_emerald)
        grad.setColorAt(1.0, c_transparent)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.end()
