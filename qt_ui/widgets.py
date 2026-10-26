"""The widget kit of the Qt app (Phase 2): ports of ``ui/widgets.py``.

  ``Toggle``       animated on/off switch (a checkable button: click, Space or Enter flips it)
  ``Tooltip``      the small dark pop-up shown after the pointer rests on a widget (own window, wraps at 380 px)
  ``InfoIcon``     a small «i» that shows a ``Tooltip``
  ``Card``         a surface with a hairline border, optional title and subtitle; rows go in with ``add_row``
  ``SettingRow``   bold name + muted hint (+ ⓘ) on the left, the control on the right, divider underneath
  ``Collapsible``  «▸ Advanced» header that shows and hides ``.body``
  ``SideNav``      vertical list of entries, one selected, Up/Down move the selection
  ``TokenChips``   buttons that insert ``{token}`` at the cursor of a line edit (replacing a selection)
  ``EmptyState``   a message laid over an empty list or table, optionally with a button
  ``ScrollFrame`` / ``ScrollPage``   a vertically scrolling page; the page has a footer bar that never scrolls
  ``ComboBox``     drop-down list (Phase 4): the stylesheet draws the field, the widget draws the little arrow
  ``SpinBox``      whole-number field with up/down arrows (Phase 5); like ``ComboBox`` it ignores the mouse wheel
                   until it has the keyboard focus, so scrolling a page never changes a value by accident

Colours come from ``core.palette``; the looks that need a stylesheet (card, divider, sidebar, chip, ...) are in
``qt_ui/theme.py`` and are chosen with object names and the dynamic properties ``variant`` / ``role`` /
``selected``. Widgets draw nothing that the stylesheet could do, except ``Toggle`` and ``InfoIcon`` (painted).

Differences from the tkinter versions are listed in docs/migration/MIGRATION_LOG.md. ``wrap_to`` is not ported:
word-wrapped labels follow their layout in Qt. All of it runs on the GUI thread only.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QObject, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)

from core.palette import ACCENT, ACCENT_HOVER, ACCENT_TEXT, BG3, BORDER, DISABLED, FG, MUTED, WHITE

_ON_TRACK_DISABLED = "#4a3a78"  # the purple track of a disabled switch (same value as the tkinter Toggle)
_OFF_TRACK_HOVER = "#4a4d55"


def _mix(a: str, b: str, t: float) -> QColor:
    """Colour between ``a`` (t = 0) and ``b`` (t = 1), both ``#rrggbb``."""
    ca, cb = QColor(a), QColor(b)
    return QColor(*(round(x + (y - x) * t) for x, y in zip(ca.getRgb()[:3], cb.getRgb()[:3])))


def _set_variant(widget: QWidget, name: str, value) -> None:
    """Change a dynamic property that the stylesheet looks at and make the widget restyle itself now."""
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


# --------------------------------------------------------------------------- #
# Toggle switch
# --------------------------------------------------------------------------- #
class Toggle(QAbstractButton):
    """An on/off switch. Click, Space or Enter flips it.

    It is a checkable button: ``isChecked()`` / ``setChecked()`` are the value, ``toggled(bool)`` fires on every
    change, ``clicked(bool)`` ONLY when the user flips it (tkinter's ``command``: code that sets the value does not
    run it). The knob slides to the new position in about 70 ms (instantly while the switch is hidden).
    """

    W, H = 42, 24
    DURATION_MS = 70

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._hover = False
        self._pos = 1.0 if checked else 0.0  # 0 = off, 1 = on (animated)
        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(self.DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._follow)

    # ---- animated position ---- #
    def _get_position(self) -> float:
        return self._pos

    def _set_position(self, value: float) -> None:
        self._pos = float(value)
        self.update()

    position = Property(float, _get_position, _set_position)

    def _follow(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        self._anim.stop()
        if not self.isVisible():
            self._set_position(target)
            return
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(target)
        self._anim.start()

    def is_animating(self) -> bool:
        return self._anim.state() == QPropertyAnimation.State.Running

    # ---- hover ---- #
    def set_hovered(self, hovered: bool) -> None:
        self._hover = hovered
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.set_hovered(False)
        super().leaveEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.EnabledChange:
            self.setCursor(Qt.CursorShape.PointingHandCursor if self.isEnabled() else Qt.CursorShape.ArrowCursor)
            self.update()
        super().changeEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.update()

    # ---- keyboard: Space is the button's own; Enter flips it too, like the tkinter switch ---- #
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.isEnabled() and not event.isAutoRepeat():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---- drawing ---- #
    def sizeHint(self) -> QSize:
        return QSize(self.W, self.H)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.W, self.H)

    def track_colour(self) -> QColor:
        """The colour of the track now (between the off and the on colour while the knob slides)."""
        if not self.isEnabled():
            off, on = BG3, _ON_TRACK_DISABLED
        else:
            off, on = (_OFF_TRACK_HOVER if self._hover else BG3), (ACCENT_HOVER if self._hover else ACCENT)
        return _mix(off, on, self._pos)

    def paintEvent(self, event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
        enabled = self.isEnabled()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.track_colour())
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        pad = h * 0.17
        r = h / 2 - pad
        cx = pad + r + self._pos * (w - 2 * (pad + r))
        p.setBrush(QColor(DISABLED if not enabled else WHITE))
        if self.is_animating() and 0.0 < self._pos < 1.0:
            stretch = 1.0 + 0.14 * math.sin(math.pi * self._pos)
            rx = r * stretch
            ry = r / math.sqrt(stretch)
            p.drawEllipse(QPointF(cx, h / 2), rx, ry)
        else:
            p.drawEllipse(QRectF(cx - r, h / 2 - r, 2 * r, 2 * r))
        if self.hasFocus() and enabled:  # keyboard focus ring
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(ACCENT_HOVER), 1))
            p.drawRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), h / 2 - 1.5, h / 2 - 1.5)  # 1 px wide, 1 px inside the track
        p.end()


# --------------------------------------------------------------------------- #
# Tooltip and the info icon
# --------------------------------------------------------------------------- #
class Tooltip(QObject):
    """A small dark pop-up with explanatory text, shown after the pointer has rested on ``widget`` for ``DELAY`` ms.

    It is a window of its own (not Qt's ``QToolTip``) so that the width is ours: lines wrap at ``wraplength``.
    It goes away when the pointer leaves, a button is pressed, or the widget is hidden or destroyed.
    ``tip`` is the pop-up label while it is on screen, else None. ``show_now()`` / ``hide_tip()`` skip the timer.
    """

    DELAY = 450
    PAD_X, PAD_Y = 10, 7

    def __init__(self, widget: QWidget, text: str, wraplength: int = 380):
        super().__init__(widget)
        self.widget, self.text, self.wraplength = widget, text, wraplength
        self.tip: QLabel | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DELAY)
        self._timer.timeout.connect(self.show_now)
        widget.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        kind = event.type()
        if obj is self.widget:
            if kind == QEvent.Type.Enter:
                self._timer.start()
            elif kind in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide, QEvent.Type.Close,
                          QEvent.Type.DeferredDelete):
                self.hide_tip()
        return False

    def show_now(self) -> None:
        self._timer.stop()
        if self.tip is not None or not self.text:
            return
        label = QLabel(self.text, None, Qt.WindowType.ToolTip)
        label.setObjectName("tooltipBubble")
        label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        label.setWordWrap(True)
        label.setContentsMargins(self.PAD_X, self.PAD_Y, self.PAD_X, self.PAD_Y)
        # as wide as the text needs, but never wider than ``wraplength`` (a wrapped QLabel would guess its width)
        inner = max(40, self.wraplength - 2 * self.PAD_X)
        text_w = label.fontMetrics().boundingRect(QRect(0, 0, inner, 10000), Qt.TextFlag.TextWordWrap, self.text).width()
        width = min(self.wraplength, text_w + 2 * self.PAD_X + 6)
        label.setFixedWidth(width)
        label.setFixedHeight(label.heightForWidth(width))
        pos = self.widget.mapToGlobal(QPoint(12, self.widget.height() + 6))
        screen = self.widget.screen()
        if screen is not None:
            area = screen.availableGeometry()
            pos.setX(min(pos.x(), area.right() - width - 8))
            pos.setX(max(area.left(), pos.x()))
        label.move(pos)
        label.show()
        self.tip = label
        try:
            from qt_ui.motion import DURATION_MICRO, Motion, animate_slide_and_fade
            if Motion.enabled():
                animate_slide_and_fade(
                    label,
                    pos + QPoint(0, 3),
                    pos,
                    start_alpha=0.0,
                    end_alpha=1.0,
                    duration_ms=DURATION_MICRO,
                )
        except Exception:
            pass

    def hide_tip(self) -> None:
        self._timer.stop()
        if self.tip is not None:
            tip, self.tip = self.tip, None
            prev = getattr(tip, "_slide_fade_group", None)
            if prev is not None:
                prev.stop()
                tip._slide_fade_group = None
            tip.hide()
            tip.deleteLater()


class InfoIcon(QWidget):
    """A small «i» in a hairline box that shows ``text`` as a tooltip. Add it to a layout yourself."""

    SIZE = 18

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.text = text
        self._hover = False
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setAccessibleName("Information")
        self.setAccessibleDescription(text)
        self.tooltip = Tooltip(self, text)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def set_hovered(self, hovered: bool) -> None:
        self._hover = hovered
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setPen(QPen(QColor(ACCENT if self._hover else BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(WHITE if self._hover else MUTED))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "i")
        p.end()


# --------------------------------------------------------------------------- #
# Card and setting row
# --------------------------------------------------------------------------- #
class WrapLabel(QLabel):
    """A word-wrapped label whose height follows ITS width, also when a layout offers more than ``maximumWidth``.

    A plain wrapped ``QLabel`` inside nested layouts is asked for its height at the width the layout has, not at the
    width it will get (it stops at its maximum), and then comes out a line too short: the last line is cut off.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return super().heightForWidth(min(width, self.maximumWidth()))


class MarqueeLabel(QWidget):
    """A single-line label that smoothly auto-scrolls horizontally if its text overflows available width.

    Auto-looping behavior:
    1. Pauses at start for ~1.5 s
    2. Scrolls smoothly across to the end
    3. Pauses at end for ~1.5 s
    4. Resets to start and repeats
    Respects Motion.enabled() (when disabled, draws cleanly elided text without running timers).
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text
        self._offset: float = 0.0
        self._state: str = "pause_start"
        self._pause_ticks: int = 0
        self._speed: float = 35.0  # px/s
        self._fps: int = 30
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._fps)
        self._timer.timeout.connect(self._on_tick)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if text:
            self.setToolTip(text)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        if self._text == text:
            return
        self._text = text
        self._offset = 0.0
        self._state = "pause_start"
        self._pause_ticks = 0
        self.setToolTip(text)
        self.update()
        self._check_timer()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(min(120, fm.horizontalAdvance(self._text)), fm.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(30, self.fontMetrics().height())

    def _overflow(self) -> float:
        total_w = self.fontMetrics().horizontalAdvance(self._text)
        return max(0.0, float(total_w - self.width()))

    def _check_timer(self) -> None:
        try:
            from qt_ui.motion import Motion
            motion_ok = Motion.enabled()
        except ImportError:
            motion_ok = True

        if motion_ok and self.isVisible() and self._overflow() > 0:
            if not self._timer.isActive():
                self._timer.start()
        else:
            if self._timer.isActive():
                self._timer.stop()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._check_timer()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._overflow() <= 0:
            self._offset = 0.0
        self._check_timer()

    def _on_tick(self) -> None:
        overflow = self._overflow()
        if overflow <= 0:
            self._offset = 0.0
            self._timer.stop()
            self.update()
            return

        pause_limit = int(1.5 * self._fps)
        if self._state == "pause_start":
            self._pause_ticks += 1
            if self._pause_ticks >= pause_limit:
                self._pause_ticks = 0
                self._state = "scrolling"
        elif self._state == "scrolling":
            step = self._speed / self._fps
            self._offset += step
            if self._offset >= overflow:
                self._offset = overflow
                self._state = "pause_end"
                self._pause_ticks = 0
            self.update()
        elif self._state == "pause_end":
            self._pause_ticks += 1
            if self._pause_ticks >= pause_limit:
                self._pause_ticks = 0
                self._offset = 0.0
                self._state = "pause_start"
                self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fm = self.fontMetrics()
        overflow = self._overflow()

        try:
            from qt_ui.motion import Motion
            motion_ok = Motion.enabled()
        except ImportError:
            motion_ok = True

        p.setPen(QColor(MUTED))
        if not motion_ok or overflow <= 0:
            elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, max(0, self.width()))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        else:
            p.setClipRect(self.rect())
            y = (self.height() + fm.ascent() - fm.descent()) // 2
            p.drawText(int(round(-self._offset)), y, self._text)
        p.end()


class SettingRow(QWidget):
    """``[ Name  ⓘ ]                          [ control ]``  /  ``[ one-line hint ]``, then a divider.

    Put the control in with ``add_control(widget)`` (it sits on the right). ``below`` is a full-width area under the
    text for wide controls (file name templates and the like); put things in with ``below_layout``. ``divider`` is
    None when the row was made without one (the last row of a card). ``hint_label`` and ``info`` are None when
    there is no hint / no ⓘ.
    """

    HINT_MAX_WIDTH = 470

    def __init__(self, title: str, hint: str = "", info: str = "", divider: bool = True,
                 parent: QWidget | None = None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 10, 0, 10)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setRowStretch(3, 1)  # spare height goes below the row, never between its parts

        text = QWidget(self)
        text_box = QVBoxLayout(text)
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.title_label = QLabel(title, text)
        self.title_label.setProperty("role", "rowtitle")
        top.addWidget(self.title_label)

        self.changed_dot = QLabel("●", text)
        self.changed_dot.setProperty("role", "accent")
        self.changed_dot.setStyleSheet(f"color: {ACCENT_TEXT}; font-size: 10px;")
        self.changed_dot.setToolTip("Modified from default")
        self.changed_dot.setVisible(False)
        top.addWidget(self.changed_dot)

        self.reset_btn = QPushButton("Reset", text)
        self.reset_btn.setProperty("variant", "ghost")
        self.reset_btn.setStyleSheet(f"font-size: 11px; padding: 1px 4px; color: {MUTED};")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setToolTip("Reset to default")
        self.reset_btn.setVisible(False)
        self._on_reset_callback = None
        self.reset_btn.clicked.connect(self._handle_reset)
        top.addWidget(self.reset_btn)

        self.info: InfoIcon | None = None
        if info:
            self.info = InfoIcon(info, text)
            top.addWidget(self.info)
        top.addStretch(1)
        text_box.addLayout(top)
        self.hint_label: QLabel | None = None
        if hint:
            self.hint_label = WrapLabel(hint, text)
            self.hint_label.setProperty("role", "muted")
            self.hint_label.setMaximumWidth(self.HINT_MAX_WIDTH)
            self.hint_label.setContentsMargins(0, 2, 0, 0)
            text_box.addWidget(self.hint_label)
        grid.addWidget(text, 0, 0, Qt.AlignmentFlag.AlignVCenter)  # fills the column: the hint wraps at its own max width

        self.control = QWidget(self)
        self.control_layout = QHBoxLayout(self.control)
        self.control_layout.setContentsMargins(0, 0, 0, 0)
        self.control_layout.setSpacing(6)
        grid.addWidget(self.control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.below = QWidget(self)
        self.below_layout = QVBoxLayout(self.below)
        self.below_layout.setContentsMargins(0, 0, 0, 0)
        self.below_layout.setSpacing(0)
        grid.addWidget(self.below, 1, 0, 1, 2)

        self.divider: QFrame | None = None
        if divider:
            gap = QWidget(self)  # 10 px of air above the hairline, like tkinter's pady=(10, 0)
            gap_box = QVBoxLayout(gap)
            gap_box.setContentsMargins(0, 10, 0, 0)
            self.divider = QFrame(gap)
            self.divider.setObjectName("divider")
            self.divider.setFixedHeight(1)
            gap_box.addWidget(self.divider)
            grid.addWidget(gap, 2, 0, 1, 2)

    def add_control(self, widget: QWidget) -> QWidget:
        self.control_layout.addWidget(widget)
        return widget

    def add_below(self, widget: QWidget) -> QWidget:
        self.below_layout.addWidget(widget)
        return widget

    def set_changed(self, changed: bool, on_reset: Callable[[], None] | None = None) -> None:
        """Show or hide the 'modified from default' accent dot and Reset button (Phase 9d, G2)."""
        self.changed_dot.setVisible(bool(changed))
        self.reset_btn.setVisible(bool(changed))
        self._on_reset_callback = on_reset

    def _handle_reset(self) -> None:
        if callable(self._on_reset_callback):
            self._on_reset_callback()


class Card(QFrame):
    """A surface (``BG2`` with a hairline border). Children go in ``.body`` (``add_row`` / ``add_widget``)."""

    def __init__(self, title: str | None = None, subtitle: str | None = None, padding: int = 16,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.title_label: QLabel | None = None
        self.subtitle_label: QLabel | None = None
        if title:
            head = QWidget(self)
            head.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)  # the body takes spare height
            head_box = QVBoxLayout(head)
            head_box.setContentsMargins(padding, padding - 2, padding, 0)
            head_box.setSpacing(2)
            self.title_label = QLabel(title, head)
            self.title_label.setProperty("role", "heading")
            head_box.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = WrapLabel(subtitle, head)
                self.subtitle_label.setProperty("role", "muted")
                head_box.addWidget(self.subtitle_label)
            outer.addWidget(head)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(padding, 8, padding, padding - 4)
        self.body_layout.setSpacing(0)
        outer.addWidget(self.body, 1)
        self.rows: list[SettingRow] = []

    def add_row(self, title: str, hint: str = "", info: str = "", divider: bool = True) -> SettingRow:
        row = SettingRow(title, hint, info, divider, self.body)
        self.body_layout.addWidget(row)
        self.rows.append(row)
        return row

    def add_widget(self, widget: QWidget) -> QWidget:
        self.body_layout.addWidget(widget)
        return widget


# --------------------------------------------------------------------------- #
# «Advanced» area
# --------------------------------------------------------------------------- #
class Collapsible(QWidget):
    """A header button («▸ Advanced») that shows and hides ``.body``. Rows go in with ``add_row`` like a Card.

    ``toggled(bool)`` fires after every open / close (the owner may want to scroll to the new content).
    """

    toggled = Signal(bool)

    def __init__(self, title: str = "Advanced", hint: str = "", opened: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.title, self.hint = title, hint
        self.opened = opened
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(0)
        self.header = QPushButton(self)
        self.header.setProperty("variant", "cardghost")
        self.header.clicked.connect(self.toggle)
        outer.addWidget(self.header, 0, Qt.AlignmentFlag.AlignLeft)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        outer.addWidget(self.body)
        self.rows: list[SettingRow] = []
        self._apply(animate=False)

    def add_row(self, title: str, hint: str = "", info: str = "", divider: bool = True) -> SettingRow:
        row = SettingRow(title, hint, info, divider, self.body)
        self.body_layout.addWidget(row)
        self.rows.append(row)
        return row

    def toggle(self) -> None:
        self.set_opened(not self.opened)

    def set_opened(self, opened: bool) -> None:
        if opened == self.opened:
            return
        self.opened = opened
        self._apply(animate=True)
        self.toggled.emit(self.opened)

    def _apply(self, animate: bool = False) -> None:
        from qt_ui.motion import QWIDGETSIZE_MAX, Motion, animate_height

        arrow = "\u25be" if self.opened else "\u25b8"
        self.header.setText(f"{arrow}  {self.title}" + (f"   \u00b7   {self.hint}" if self.hint else ""))
        if not animate or not Motion.enabled() or not self.isVisible():
            prev = getattr(self.body, "_height_anim", None)
            if prev is not None:
                prev.stop()
                self.body._height_anim = None
            self.body.setMaximumHeight(QWIDGETSIZE_MAX)
            self.body.setVisible(self.opened)
            return
        if self.opened:
            self.body.setMaximumHeight(0)
            self.body.setVisible(True)
            target = max(self.body.sizeHint().height(), 1)
            animate_height(
                self.body, 0, target, Motion.NORMAL_MS,
                on_finished=lambda: self.body.setMaximumHeight(QWIDGETSIZE_MAX),
            )
        else:
            start = max(self.body.height(), 1)

            def _after_close() -> None:
                self.body.setVisible(False)
                self.body.setMaximumHeight(QWIDGETSIZE_MAX)

            animate_height(self.body, start, 0, Motion.NORMAL_MS, on_finished=_after_close)


# --------------------------------------------------------------------------- #
# Sidebar navigation
# --------------------------------------------------------------------------- #
class _NavButton(QPushButton):
    """A sidebar entry: Up / Down hand the selection to the owner."""

    def __init__(self, text: str, nav: "SideNav", key: str):
        super().__init__(text, nav)
        self._nav, self._key = nav, key

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Down:
            self._nav.step(self._key, 1)
        elif event.key() == Qt.Key.Key_Up:
            self._nav.step(self._key, -1)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class SideNav(QFrame):
    """A vertical list of entries; the selected one is tinted purple. ``selected(key)`` fires on every ``select``.

    Entries are real buttons: Tab reaches each of them, Space picks one, Up / Down move the selection (and the
    focus) and stop at the ends. ``current`` is the selected key (None until the first ``select``).
    """

    selected = Signal(str)

    def __init__(self, items: Iterable[tuple[str, str]], width_chars: int = 17, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sideNav")
        self._raw_items = list(items)
        box = QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        box.setSpacing(2)
        self.keys: list[str] = []
        self.buttons: dict[str, QPushButton] = {}
        self.current: str | None = None
        min_w = round(self.fontMetrics().horizontalAdvance("0") * width_chars) + 28
        for key, label in items:
            b = _NavButton(label, self, key)
            b.setProperty("variant", "nav")
            b.setProperty("selected", False)
            b.setMinimumWidth(min_w)
            b.clicked.connect(lambda _checked=False, k=key: self.select(k))
            box.addWidget(b)
            self.keys.append(key)
            self.buttons[key] = b
        box.addStretch(1)

    def step(self, key: str, delta: int) -> None:
        """What the Up / Down key does on the entry ``key``: select the neighbour and focus it (nothing at the ends)."""
        i = self.keys.index(key) + delta
        if 0 <= i < len(self.keys):
            self.select(self.keys[i])
            self.buttons[self.keys[i]].setFocus(Qt.FocusReason.TabFocusReason)

    def select(self, key: str) -> None:
        if key not in self.buttons:
            return
        self.current = key
        for k, b in self.buttons.items():
            _set_variant(b, "selected", k == key)
        self.selected.emit(key)

    def set_badge(self, key: str, count: int) -> None:
        """Update the sidebar item label to show count of changed settings (e.g. 'Chat (2)') (Phase 9d, G2)."""
        btn = self.buttons.get(key)
        if btn is not None:
            base_label = next((l for k, l in self._raw_items if k == key), key)
            btn.setText(f"{base_label} ({count})" if count > 0 else base_label)


# --------------------------------------------------------------------------- #
# Clickable {token} chips
# --------------------------------------------------------------------------- #
class TokenChips(QWidget):
    """A grid of small buttons; clicking one inserts ``{token}`` at the cursor of ``entry`` (a ``QLineEdit``).

    A selection in the field is replaced, like typing over it. A read-only or disabled field is left alone. The
    chips can be reached with Tab but do not take the focus when clicked, so the field keeps its cursor and selection.
    """

    def __init__(self, entry: QLineEdit, tokens: Iterable[str], per_row: int = 6, parent: QWidget | None = None):
        super().__init__(parent)
        self.entry = entry
        self.chips: list[QPushButton] = []
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        for i, tok in enumerate(tokens):
            b = QPushButton("{" + tok + "}", self)
            b.setProperty("variant", "chip")
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.clicked.connect(lambda _checked=False, t=tok: self.insert(t))
            grid.addWidget(b, i // per_row, i % per_row, Qt.AlignmentFlag.AlignLeft)
            self.chips.append(b)
        grid.setColumnStretch(per_row, 1)  # keeps the chips to the left

    def insert(self, token: str) -> None:
        if not self.entry.isEnabled() or self.entry.isReadOnly():
            return
        self.entry.insert("{" + token + "}")  # QLineEdit.insert replaces the selected text
        self.entry.setFocus()

    def set_enabled(self, on: bool) -> None:
        for b in self.chips:
            b.setEnabled(on)


# --------------------------------------------------------------------------- #
# Empty state: a friendly message laid over an empty list
# --------------------------------------------------------------------------- #
class EmptyState(QWidget):
    """A message centred over a list or table (``target``) while it has nothing to show.

    ``show_message(title, text, button=("Sign in…", command))`` fills and shows it, ``hide_message()`` removes it.
    It covers the target below ``top`` pixels (so the column headings stay visible) and follows the target's size.
    ``compact=True`` wraps narrower, for narrow lists. ``shown`` tells whether it is on.
    """

    def __init__(self, target: QWidget, top: int = 0, compact: bool = False):
        super().__init__(target)
        self.setObjectName("emptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._target, self._top = target, top
        self._wrap = 190 if compact else 380
        self.shown = False
        self.title_label: QLabel | None = None
        self.text_label: QLabel | None = None
        self.button: QPushButton | None = None
        self._inner = QWidget(self)
        self._box = QVBoxLayout(self._inner)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(0)
        self._box.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        target.installEventFilter(self)
        super().hide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._target and event.type() == QEvent.Type.Resize and self.shown:
            self._place()
        return False

    def _label(self, text: str, role: str | None) -> QLabel:
        lbl = QLabel(text, self._inner)
        if role:
            lbl.setProperty("role", role)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        lbl.setWordWrap(True)
        font = lbl.font()
        font.setPointSize(11 if role == "emptytitle" else 10)
        font.setBold(role == "emptytitle")
        lbl.setFont(font)
        width = min(self._wrap, lbl.fontMetrics().boundingRect(
            QRect(0, 0, self._wrap, 10000), Qt.TextFlag.TextWordWrap, text).width() + 6)
        lbl.setFixedWidth(width)
        lbl.setFixedHeight(lbl.heightForWidth(width))
        return lbl

    def show_message(self, title: str = "", text: str = "", button: tuple[str, Callable[[], object]] | None = None) -> None:
        """Replace the lines (never stack them) and show the message on top of the target."""
        while self._box.count():
            item = self._box.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.title_label = self.text_label = self.button = None
        if title:
            self.title_label = self._label(title, "emptytitle")
            self._box.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignHCenter)
        if text:
            self.text_label = self._label(text, "muted")
            self._box.addSpacing(4 if title else 0)
            self._box.addWidget(self.text_label, 0, Qt.AlignmentFlag.AlignHCenter)
        if button:
            label, command = button
            self.button = QPushButton(label, self._inner)
            self.button.setProperty("variant", "accent")
            self.button.clicked.connect(lambda _checked=False: command())
            self._box.addSpacing(12)
            self._box.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.shown = True
        self._place()
        super().show()
        self.raise_()

    def hide_message(self) -> None:
        if self.shown:
            super().hide()
            self.shown = False

    def texts(self) -> list[str]:
        """The lines on show: title, text (the button's label is not a line)."""
        return [w.text() for w in (self.title_label, self.text_label) if w is not None]

    def _place(self) -> None:
        w, h = self._target.width(), max(0, self._target.height() - self._top)
        self.setGeometry(0, self._top, w, h)
        self._inner.adjustSize()
        size = self._inner.sizeHint()
        self._inner.resize(size)
        # centred horizontally, and at 42 % of the height (a little above the middle, like the tkinter version)
        self._inner.move(round((w - size.width()) / 2), max(0, round(h * 0.42 - size.height() / 2)))


# --------------------------------------------------------------------------- #
# Scrollable page
# --------------------------------------------------------------------------- #
class ScrollFrame(QScrollArea):
    """A tab page that scrolls vertically when the window is too short for its content.

    Put the widgets in ``.body`` (a widget with a vertical layout, ``body_layout``). When the window is tall
    enough ``.body`` stretches to fill it; otherwise a scroll bar appears and the mouse wheel scrolls. Qt follows
    changes inside the body by itself, so tkinter's ``refit()`` has no counterpart. There is no horizontal scroll bar.
    """

    def __init__(self, padding: int = 8, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("scrollFrame")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("scrollBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(padding, padding, padding, padding)
        self.body_layout.setSpacing(8)
        self.setWidget(self.body)

    def scroll_to_top(self) -> None:
        self.verticalScrollBar().setValue(0)

    def scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def is_scrollable(self) -> bool:
        return self.verticalScrollBar().maximum() > 0


class ScrollPage(QWidget):
    """A ``ScrollFrame`` with a fixed bar underneath that never scrolls away.

    Content goes in ``.body`` (as with ScrollFrame), the always-visible bar is ``.footer`` (``footer_layout``, a
    horizontal layout). Tab order: the bar is the LAST stop after the page. Qt orders the stops by creation, and the
    bar is created before the content, so ``fix_tab_order()`` moves the bar's stops behind the page's; it runs by
    itself the first time the page is shown, call it again after adding focusable widgets later.
    """

    def __init__(self, padding: int = 8, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = ScrollFrame(padding, self)
        outer.addWidget(self.scroll, 1)
        self.footer_line = QFrame(self)
        self.footer_line.setObjectName("divider")
        self.footer_line.setFixedHeight(1)
        outer.addWidget(self.footer_line)
        self.footer = QWidget(self)
        self.footer.setObjectName("pageFooter")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 10, 12, 10)
        outer.addWidget(self.footer)
        self.body = self.scroll.body
        self.body_layout = self.scroll.body_layout
        self._tab_order_done = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._tab_order_done:
            self._tab_order_done = True
            self.fix_tab_order()

    def fix_tab_order(self) -> None:
        """Make the footer's Tab stops come after all stops of the page's body (the order is otherwise by creation)."""
        chain: list[QWidget] = []
        w = self.scroll
        for _ in range(100000):  # bounded walk around the focus chain, starting at this page's scroll area
            if chain and w is chain[0]:
                break
            chain.append(w)
            w = w.nextInFocusChain()

        def stop(widget: QWidget) -> bool:
            return bool(widget.focusPolicy() & Qt.FocusPolicy.TabFocus)

        mine = [x for x in chain if (self.body.isAncestorOf(x) or self.footer.isAncestorOf(x)) and stop(x)]
        body_stops = [x for x in mine if self.body.isAncestorOf(x)]
        footer_stops = [x for x in mine if self.footer.isAncestorOf(x)]
        order = body_stops + footer_stops
        for a, b in zip(order, order[1:]):
            QWidget.setTabOrder(a, b)

    def tab_stops(self) -> list[QWidget]:
        """The page's Tab stops in the order Tab visits them: body first, then the footer (for tests and checks)."""
        chain: list[QWidget] = []
        start = w = self.scroll
        for _ in range(100000):
            chain.append(w)
            w = w.nextInFocusChain()
            if w is start:
                break
        return [x for x in chain if (self.body.isAncestorOf(x) or self.footer.isAncestorOf(x))
                and x.focusPolicy() & Qt.FocusPolicy.TabFocus]


# --------------------------------------------------------------------------- #
# Drop-down list
# --------------------------------------------------------------------------- #
class ComboBox(QComboBox):
    """A read-only drop-down (``activated`` is the user-only signal, like tkinter's ``<<ComboboxSelected>>``).

    The stylesheet gives the field its look and an empty drop-down area (``QComboBox::down-arrow`` has no image);
    the arrow is painted here, grey, white while the pointer is over the box or the list is open.
    """

    ARROW_AREA = 22  # width of the drop-down area (the same number as in theme.py)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # the wheel alone never gives it the focus (see wheelEvent)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt name)
        """Only a box that has the keyboard focus reacts to the wheel; otherwise the page under it scrolls."""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().paintEvent(event)
        lit = self.isEnabled() and (self.underMouse() or self.view().isVisible())
        colour = QColor(FG if lit else (MUTED if self.isEnabled() else DISABLED))
        cx, cy = self.width() - self.ARROW_AREA / 2 - 1, self.height() / 2
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour)
        p.drawPolygon(QPolygonF([QPointF(cx - 4, cy - 2), QPointF(cx + 4, cy - 2), QPointF(cx, cy + 2.5)]))
        p.end()


# --------------------------------------------------------------------------- #
# Whole-number field
# --------------------------------------------------------------------------- #
class SpinBox(QSpinBox):
    """A whole-number field with two small arrows (the tkinter ``Spinbox``). Up / Down keys and the arrows step by 1.

    The stylesheet draws the field and reserves the arrow area on the right (``QSpinBox::up-button`` and
    ``down-button`` have no image); the arrows are painted here, grey, white while the pointer is over the box.
    The wheel only works while the box has the keyboard focus (see ``ComboBox``).
    """

    ARROW_AREA = 18  # width of the arrow area (the same number as in theme.py)

    def __init__(self, low: int = 0, high: int = 100, width_chars: int = 6, parent: QWidget | None = None):
        super().__init__(parent)
        self.setRange(low, high)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setKeyboardTracking(True)  # a value typed in becomes the setting at once, like tkinter's StringVar
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumWidth(round(self.fontMetrics().horizontalAdvance("0") * width_chars) + self.ARROW_AREA + 20)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().paintEvent(event)
        lit = self.isEnabled() and self.underMouse()
        colour = QColor(FG if lit else (MUTED if self.isEnabled() else DISABLED))
        cx = self.width() - self.ARROW_AREA / 2 - 1
        mid = self.height() / 2
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour)
        p.drawPolygon(QPolygonF([QPointF(cx - 3.5, mid - 2.5), QPointF(cx + 3.5, mid - 2.5), QPointF(cx, mid - 6.5)]))
        p.drawPolygon(QPolygonF([QPointF(cx - 3.5, mid + 2.5), QPointF(cx + 3.5, mid + 2.5), QPointF(cx, mid + 6.5)]))
        p.end()
