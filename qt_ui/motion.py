"""Central motion and micro-interaction helper (Phase 9a, A6).

Provides consistent duration tokens, easing curves, an accessibility / test switch
(``Motion.set_enabled(False)`` in ``tests/conftest.py`` and Windows ``SPI_GETCLIENTAREAANIMATION``
detection), and reusable height/width/color animators.
"""

from __future__ import annotations

import sys
from typing import Callable

import shiboken6
from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QWidget

FAST_MS = 120
NORMAL_MS = 180
SLIDE_MS = 150
EASING = QEasingCurve.Type.OutCubic
QWIDGETSIZE_MAX = 16777215


def system_animations_enabled() -> bool:
    """Return False if the OS explicitly disables client-area animations (Windows SPI_GETCLIENTAREAANIMATION)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        enabled = ctypes.c_int(1)
        # SPI_GETCLIENTAREAANIMATION = 0x1042
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value) if ok else True
    except Exception:  # noqa: BLE001
        return True


class Motion:
    """Global switch and helpers for UI animations."""

    FAST_MS = FAST_MS
    NORMAL_MS = NORMAL_MS
    SLIDE_MS = SLIDE_MS
    EASING = EASING

    _override: bool | None = None

    @classmethod
    def set_enabled(cls, enabled: bool | None) -> None:
        """Force animations on (True), off (False), or follow the OS setting (None)."""
        cls._override = enabled

    @classmethod
    def enabled(cls) -> bool:
        """Whether UI animations should run."""
        if cls._override is not None:
            return cls._override
        return system_animations_enabled()

    @classmethod
    def duration(cls, ms: int = NORMAL_MS) -> int:
        """Effective animation duration in milliseconds (0 when motion is disabled)."""
        return int(ms) if cls.enabled() else 0


def animate_height(
    widget: QWidget,
    start_h: int,
    end_h: int,
    duration_ms: int = NORMAL_MS,
    on_finished: Callable[[], None] | None = None,
) -> QVariantAnimation | None:
    """Animate ``widget.maximumHeight`` from ``start_h`` to ``end_h`` with ``OutCubic`` easing."""
    prev = getattr(widget, "_height_anim", None)
    if isinstance(prev, QVariantAnimation):
        prev.stop()
        widget._height_anim = None

    if not Motion.enabled() or not widget.isVisible() or duration_ms <= 0 or start_h == end_h:
        widget.setMaximumHeight(QWIDGETSIZE_MAX if end_h > 0 else 0)
        if on_finished is not None:
            on_finished()
        return None

    anim = QVariantAnimation(widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(max(0, int(start_h)))
    anim.setEndValue(max(0, int(end_h)))
    anim.setEasingCurve(EASING)

    def _step(val) -> None:
        if shiboken6.isValid(widget):
            widget.setMaximumHeight(int(val))

    def _done() -> None:
        if shiboken6.isValid(widget):
            widget._height_anim = None
            if on_finished is not None:
                on_finished()

    anim.valueChanged.connect(_step)
    anim.finished.connect(_done)
    widget._height_anim = anim
    widget.setMaximumHeight(max(0, int(start_h)))
    anim.start()
    return anim


def animate_width(
    widget: QWidget,
    start_w: int,
    end_w: int,
    duration_ms: int = NORMAL_MS,
    on_finished: Callable[[], None] | None = None,
) -> QVariantAnimation | None:
    """Animate ``widget.setFixedWidth`` from ``start_w`` to ``end_w`` with ``OutCubic`` easing."""
    prev = getattr(widget, "_width_anim", None)
    if isinstance(prev, QVariantAnimation):
        prev.stop()
        widget._width_anim = None

    if not Motion.enabled() or not widget.isVisible() or duration_ms <= 0 or start_w == end_w:
        widget.setFixedWidth(int(end_w))
        if on_finished is not None:
            on_finished()
        return None

    anim = QVariantAnimation(widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(int(start_w))
    anim.setEndValue(int(end_w))
    anim.setEasingCurve(EASING)

    def _step(val) -> None:
        if shiboken6.isValid(widget):
            widget.setFixedWidth(int(val))

    def _done() -> None:
        if shiboken6.isValid(widget):
            widget.setFixedWidth(int(end_w))
            widget._width_anim = None
            if on_finished is not None:
                on_finished()

    anim.valueChanged.connect(_step)
    anim.finished.connect(_done)
    widget._width_anim = anim
    anim.start()
    return anim


class ButtonHoverAnimator(QObject):
    """Opt-in 120 ms colour interpolator for custom-painted or standalone buttons (Phase 9a spike).

    Note: Standard QSS-styled ``QPushButton`` widgets use QSS ``:hover`` / ``:focus`` rules directly
    because setting per-frame inline ``setStyleSheet`` on a ``QPushButton`` overrides application-level
    dynamic property selectors (``[variant="..."]``, ``[selected="true"]``). Use this helper on custom
    surfaces that read ``animator.current_color`` in their ``paintEvent``.
    """

    def __init__(
        self,
        parent: QPushButton | QWidget,
        normal_color: str,
        hover_color: str,
        duration_ms: int = FAST_MS,
    ):
        super().__init__(parent)
        self._widget = parent
        self._normal = QColor(normal_color)
        self._hover = QColor(hover_color)
        self._progress = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(duration_ms)
        self._anim.setEasingCurve(EASING)
        self._anim.valueChanged.connect(self._on_step)

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def current_color(self) -> QColor:
        t = self._progress
        return QColor(
            round(self._normal.red() + (self._hover.red() - self._normal.red()) * t),
            round(self._normal.green() + (self._hover.green() - self._normal.green()) * t),
            round(self._normal.blue() + (self._hover.blue() - self._normal.blue()) * t),
        )

    def set_hovered(self, hovered: bool) -> None:
        target = 1.0 if hovered else 0.0
        self._anim.stop()
        if not Motion.enabled() or not self._widget.isVisible():
            self._progress = target
            if shiboken6.isValid(self._widget):
                self._widget.update()
            return
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_step(self, value: float) -> None:
        self._progress = float(value)
        if shiboken6.isValid(self._widget):
            self._widget.update()
