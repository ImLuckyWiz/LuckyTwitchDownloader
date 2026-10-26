"""Timeline (Phase 7, ``qt_ui/timeline.py``): the whole VOD on one strip, to see where the games change and to place
the cuts with the mouse.

Port of ``ui/timeline.py`` (decision D2: custom ``QWidget`` painted with ``QPainter``, reusing ``Viewport``,
``nice_step``, ``game_colour`` and ``zone_at`` from ``core/timeline.py``).

Rows, top to bottom:
    ruler    time marks (green triangles = clips). Drag to move along the VOD.
    games    one bar per game / category the streamer was in. Double-click one to make it its own part
             (Shift + double-click: keep only that game). A thin red line along its bottom edge marks the
             stretches Twitch silenced (muted audio); it can be switched off with the «Show muted» switch.
    thumbs   preview frames of the VOD. Click to cut there, drag a cut line to move it.
    parts    the parts that will be downloaded (purple); skipped sections are dark. Click a part to skip
             it, click a skipped section to bring it back.
Right-click a cut line (between two touching parts) to remove it (on macOS, Ctrl+click also removes a cut line).
Mouse wheel = zoom, Shift + wheel or the scroll bar = move. "Undo" (or Ctrl+Z / Cmd+Z) takes back the last timeline
edit.

The widget knows nothing about the rest of the app. The owner feeds it with ``set_source()`` / ``set_frames()`` /
``set_ranges()`` / ``set_clip_marks()`` / ``set_muted()`` and gets every edit back through ``on_edit(ranges)``; the cut
text is rebuilt from those ranges by the engine.
"""

from __future__ import annotations

import math
import sys
import time
from typing import Callable, Sequence

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QImage, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QPolygonF, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLayout, QMenu, QPushButton, QScrollBar, QSizePolicy, QVBoxLayout, QWidget,
)

try:
    from shiboken6 import isValid
except ImportError:
    def isValid(obj: object) -> bool:  # noqa: N802
        return True

from core.palette import ACCENT, ACCENT_HOVER, BG, BG2, BG3, ERR, FG, MUTED, OK, UI_FONT, WHITE
from core.timeline import (
    CUT_COLOUR, EDGE_COLOUR, EDGE_TOL_PX, GAME_COLOURS, GAMES_H, GAP, HEIGHT, IDLE_HINT, MUTED_COLOUR, MUTED_H,
    PADX, PARTS_H, PREVIEW_MAX_W, RULER_H, SNAP_PX, THUMB_H, THUMB_W, Viewport, Y_GAMES, Y_PARTS, Y_RULER,
    Y_THUMBS, build_snap_kinds, build_snap_points, cluster_marks, game_colour, game_key, game_totals, gaps_of,
    minimap_lens, nice_step, snap_target, snap_time, y_of, zone_at,
)
from luckytwitch_engine import (
    Edge, GameSegment, Range, Storyboard, add_cut, edges_of, fmt_hms, isolate_span, move_edge, nearest_edge,
    part_index_at, remove_cut, toggle_part,
)
from qt_ui.icons import icon
from qt_ui.widgets import Toggle, WrapLabel

try:  # thumbnails are PIL images returned by the engine; everything else works without Pillow
    from PIL import Image, ImageEnhance
except ImportError:  # pragma: no cover - exercised by patching Image = None
    Image = ImageEnhance = None

__all__ = [
    "CUT_COLOUR", "EDGE_COLOUR", "EDGE_TOL_PX", "GAME_COLOURS", "GAMES_H", "GAP", "HEIGHT", "IDLE_HINT",
    "MUTED_COLOUR", "MUTED_H", "PADX", "PARTS_H", "PREVIEW_MAX_W", "RULER_H", "SNAP_PX", "THUMB_H", "THUMB_W",
    "Timeline", "TimelineCanvas", "TimelineMinimap", "Viewport", "Y_GAMES", "Y_PARTS", "Y_RULER", "Y_THUMBS",
    "game_colour", "nice_step", "y_of", "zone_at",
]

SCROLL_SCALE = 10_000
NUDGE_STEP, NUDGE_SHIFT_STEP = 1, 10  # seconds per arrow key press (Shift = 10 s)
# Alt asks for 0.1 s, but cut points are whole seconds in the engine (``move_edge`` rounds), so Alt nudges by the
# smallest step there is: 1 s (MIGRATION_LOG no. 26).
NUDGE_ALT_STEP = 1
PART_RADIUS = 6.0
FLAG_MIN_PX = 9.0  # clip flags closer than this merge into one counter badge
MINIMAP_H = 12
LEGEND_MAX_CHIPS = 12
SHIMMER_MS = 40
SHIMMER_STEP = 0.03


def _motion_enabled() -> bool:
    try:
        from qt_ui.motion import Motion
        return Motion.enabled()
    except ImportError:  # pragma: no cover
        return True


def _short_dur(seconds: float) -> str:
    """``3h 10m`` / ``12m 05s`` / ``45s`` (the legend chips)."""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


def _pil_to_qpixmap(im) -> QPixmap | None:
    """Convert a PIL ``Image`` to a ``QPixmap`` on the GUI thread."""
    if im is None:
        return None
    rgba = im.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def _dot_icon(colour: str, size: int = 10):
    """A small round colour swatch for a legend chip."""
    from PySide6.QtGui import QIcon

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(colour))
    p.drawEllipse(0, 0, size, size)
    p.end()
    return QIcon(pm)


class _FlowLayout(QLayout):
    """Left-to-right layout that wraps onto new lines (the game legend), with a proper ``heightForWidth``."""

    def __init__(self, parent: QWidget | None = None, hspacing: int = 6, vspacing: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._h, self._v = hspacing, vspacing

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            nxt = x + hint.width()
            if nxt > area.right() + 1 and line_h > 0:
                x, y, line_h = area.x(), y + line_h + self._v, 0
                nxt = x + hint.width()
            if not test:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = nxt + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


class _LegendChip(QPushButton):
    """One game of the legend: click = make it its own part, hover = light it up on the strip."""

    hovered = Signal(str)
    unhovered = Signal()

    def __init__(self, title: str, seconds: float, parent: QWidget | None = None):
        super().__init__(f"{title}  {_short_dur(seconds)}", parent)
        self.title = title
        self.seconds = seconds
        self.setProperty("variant", "chip")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(_dot_icon(game_colour(title)))
        self.setToolTip(f"{title}: {fmt_hms(seconds)} in total\nClick: make it its own part · Shift+click: keep only this game")

    def enterEvent(self, event) -> None:  # noqa: N802
        self.hovered.emit(self.title)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.unhovered.emit()
        super().leaveEvent(event)


class TimelineMinimap(QWidget):
    """A thin overview of the whole VOD shown while the strip is zoomed in: game colours, the parts, and a lens for
    the visible window. Click to centre the lens there, drag the lens to move along the VOD (E3)."""

    def __init__(self, timeline: Timeline):
        super().__init__(timeline)
        self.tl = timeline
        self.setFixedHeight(MINIMAP_H)
        self._grab: float | None = None  # seconds between the lens start and the mouse while dragging
        self.drawn_lens: tuple[float, float] | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Overview of the whole VOD: drag the highlighted window to move along it")

    def _inner(self) -> float:
        return max(self.width() - 2 * PADX, 1.0)

    def t_at(self, x: float) -> float:
        return (x - PADX) / self._inner() * max(self.tl.duration, 1.0)

    def x_of(self, t: float) -> float:
        return PADX + self._inner() * (t / max(self.tl.duration, 1.0))

    def lens(self) -> tuple[float, float]:
        vp = self.tl.vp
        return minimap_lens(vp.start, vp.span, self.tl.duration, self.width())

    def paintEvent(self, _event) -> None:  # noqa: N802
        tl = self.tl
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG))
        if not tl.duration:
            p.end()
            return
        track = QRectF(PADX, 2, self._inner(), self.height() - 4)
        p.fillRect(track, QColor(BG2))
        for g in tl.segments:
            x0, x1 = self.x_of(g.start), self.x_of(g.end)
            col = QColor(game_colour(g.title))
            col.setAlpha(170)
            p.fillRect(QRectF(x0, track.top(), max(x1 - x0, 1.0), track.height()), col)
        if tl.ranges:
            keep = QColor(ACCENT)
            for s, e in tl.ranges:
                p.fillRect(QRectF(self.x_of(s), track.bottom() - 2, max(self.x_of(e) - self.x_of(s), 1.0), 2), keep)
            p.setPen(QPen(QColor(CUT_COLOUR), 1))
            for edge in edges_of(tl.ranges):
                if edge.kind == "cut":
                    x = self.x_of(edge.t)
                    p.drawLine(QPointF(x, track.top()), QPointF(x, track.bottom()))
        x0, x1 = self.lens()
        self.drawn_lens = (x0, x1)
        fill = QColor(ACCENT_HOVER)
        fill.setAlpha(70)
        lens = QRectF(x0, 0.5, x1 - x0, self.height() - 1)
        p.fillRect(lens, fill)
        p.setPen(QPen(QColor(ACCENT_HOVER), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(lens, 3, 3)
        p.end()

    def _pan_to_pointer(self, x: float) -> None:
        if self._grab is None or not self.tl.duration:
            return
        self.tl.vp.pan_to(self.t_at(x) - self._grab)
        self.tl.invalidate()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self.tl.duration:
            super().mousePressEvent(event)
            return
        x = event.position().x()
        x0, x1 = self.lens()
        if x0 <= x <= x1:
            self._grab = self.t_at(x) - self.tl.vp.start
        else:
            self._grab = self.tl.vp.span / 2  # centre the lens on the click
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._pan_to_pointer(x)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._grab is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._pan_to_pointer(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._grab is not None:
            self._grab = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TimelineCanvas(QWidget):
    """The custom-painted strip inside ``Timeline``."""

    def __init__(self, timeline: Timeline):
        super().__init__(timeline)
        self.tl = timeline
        self.setFixedHeight(HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def paintEvent(self, _event) -> None:  # noqa: N802
        self.tl._paint_canvas(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.tl.invalidate()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        btn = event.button()
        mods = event.modifiers()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if btn == Qt.MouseButton.RightButton or (
            sys.platform == "darwin" and (
                btn == Qt.MouseButton.MiddleButton
                or (btn == Qt.MouseButton.LeftButton and bool(mods & Qt.KeyboardModifier.ControlModifier))
            )
        ):
            self.tl._on_right(pos.x(), pos.y(), event.globalPosition().toPoint())
            event.accept()
            return
        if btn == Qt.MouseButton.LeftButton:
            self.tl._on_press(pos.x(), pos.y(), shift=shift)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.tl._on_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.tl._on_double(pos.x(), pos.y(), shift=shift)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if event.buttons() & Qt.MouseButton.LeftButton and (self.tl._drag is not None or self.tl._pan is not None):
            self.tl._on_motion(pos.x(), pos.y())
        else:
            self.tl._on_hover(pos.x(), pos.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.tl._on_release()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.tl._on_leave()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y() or event.angleDelta().x()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.tl._on_wheel(event.position().x(), delta, shift=shift)
        event.accept()  # keep the ScrollPage behind from scrolling


class Timeline(QWidget):
    """The full Timeline widget: toolbar, custom-painted strip, horizontal scrollbar, and wrapping hint line."""

    y_of = staticmethod(y_of)

    def __init__(self, on_edit: Callable[[list[Range]], None] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.on_edit = on_edit or (lambda ranges: None)

        # model
        self.duration: float = 0.0
        self.segments: list[GameSegment] = []
        self.storyboard: Storyboard | None = None
        self.frames: list | None = None  # PIL images (None entries = unavailable); None = not loaded yet
        self.frames_state = "none"  # none | loading | ready | failed
        self.ranges: list[Range] | None = None  # None = the cut text is invalid
        self.clip_marks: list[float] = []
        self.clip_details: dict[float, str] = {}  # moment -> "title · creator · N views" (flag tooltips)
        self.muted: list[Range] = []  # stretches Twitch silenced (VOD seconds)
        self.vp = Viewport()
        self._history: list[list[Range]] = []
        self._future: list[list[Range]] = []  # what Redo brings back
        self._drag: Edge | None = None
        self._pan: tuple[float, float] | None = None
        self._selected: tuple[str, int] | None = None  # (kind, index) of the cut line the keyboard acts on
        self._hover_t: float | None = None  # the moment under the mouse (S cuts there)
        self._last_nudge: tuple[tuple[str, int], float] | None = None
        self._highlight_title: str | None = None  # a legend chip is hovered: light that game up
        self._snap_feedback: tuple[float, str] | None = None  # (moment, what it snapped to)
        self._context_menu: QMenu | None = None
        self._pixmaps: dict[tuple[int, bool], QPixmap] = {}
        self._preview_pixmaps: dict[int, QPixmap] = {}
        self._snap_points: list[float] = []
        self._snap_kinds: dict[float, str] = {}
        self._hover_pos: tuple[float, float, bool] | None = None  # (x, y, dragging)
        self._updating_bar = False
        self._redraw_pending = False
        self._shimmer_phase = 0.0
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.timeout.connect(self._flush_redraw)
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(SHIMMER_MS)
        self._shimmer_timer.timeout.connect(self._on_shimmer)
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.timeout.connect(self._clear_snap_feedback)

        # scene records from the last paint pass (so tests and inspectors can query drawn texts and rectangles)
        self.drawn_texts: list[str] = []
        self.drawn_muted_rects: list[tuple[float, float, float, float]] = []
        self.drawn_skipped_rects: list[tuple[float, float, float, float]] = []
        self.drawn_flags: list[tuple[float, int]] = []  # (x, how many clips) of each flag / badge in the ruler
        self.drawn_thumb_count: int = 0
        self.drawn_hover_preview: bool = False

        # layout & child widgets
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)
        self.btn_out = QPushButton()
        self.btn_out.setIcon(icon("minus", 16))
        self.btn_out.setToolTip("Zoom out  (−)")
        self.btn_out.setAccessibleName("Zoom out")
        self.btn_out.clicked.connect(self.zoom_out)
        self.btn_in = QPushButton()
        self.btn_in.setIcon(icon("plus", 16))
        self.btn_in.setToolTip("Zoom in  (+)")
        self.btn_in.setAccessibleName("Zoom in")
        self.btn_in.clicked.connect(self.zoom_in)
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setIcon(icon("fit", 16))
        self.btn_fit.setToolTip("Show the whole VOD  (0)")
        self.btn_fit.clicked.connect(self.zoom_fit)
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setIcon(icon("undo", 16))
        self.btn_undo.setToolTip("Undo the last edit  (Ctrl+Z)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setIcon(icon("redo", 16))
        self.btn_redo.setToolTip("Redo the edit you took back  (Ctrl+Y)")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self.redo)
        for b in (self.btn_out, self.btn_in, self.btn_fit):
            bar.addWidget(b)
        bar.addSpacing(4)
        bar.addWidget(self.btn_undo)
        bar.addWidget(self.btn_redo)
        bar.addSpacing(6)
        self.zoom_label = QLabel("")
        self.zoom_label.setProperty("role", "muted")
        bar.addWidget(self.zoom_label)

        self.muted_box = QWidget(self)
        mbox = QHBoxLayout(self.muted_box)
        mbox.setContentsMargins(12, 0, 0, 0)
        mbox.setSpacing(6)
        muted_title = QLabel("Show muted")
        muted_title.setProperty("role", "muted")
        mbox.addWidget(muted_title)
        self.muted_switch = Toggle(checked=True)
        self.muted_switch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.muted_switch.clicked.connect(self._toggle_muted)
        mbox.addWidget(self.muted_switch)
        self.muted_info = QLabel("")
        self.muted_info.setProperty("role", "muted")
        mbox.addWidget(self.muted_info)
        self.muted_box.hide()
        bar.addWidget(self.muted_box)
        bar.addStretch(1)
        outer.addLayout(bar)

        self.canvas = TimelineCanvas(self)
        outer.addWidget(self.canvas)

        self.minimap = TimelineMinimap(self)
        self.minimap.hide()  # only while zoomed in; it replaces the scroll bar then
        outer.addWidget(self.minimap)

        self.hbar = QScrollBar(Qt.Orientation.Horizontal, self)
        self.hbar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hbar.setRange(0, 0)
        self.hbar.valueChanged.connect(self._on_hbar_value)
        outer.addWidget(self.hbar)

        self.legend_box = QWidget(self)
        self.legend_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.legend_layout = _FlowLayout(self.legend_box, hspacing=6, vspacing=4)
        self.legend_layout.setContentsMargins(0, 2, 0, 2)
        self.legend_chips: list[_LegendChip] = []
        self.legend_box.hide()
        outer.addWidget(self.legend_box)

        self.hint_label = WrapLabel(IDLE_HINT, self)
        self.hint_label.setProperty("role", "muted")
        self.hint_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        outer.addWidget(self.hint_label)

        for seq in ("Ctrl+Z", "Meta+Z"):
            sc = QShortcut(QKeySequence(seq), self.canvas)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self.undo)
        for seq in ("Ctrl+Y", "Ctrl+Shift+Z", "Meta+Shift+Z"):
            sc = QShortcut(QKeySequence(seq), self.canvas)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self.redo)

    # ------------------------------------------------------------------ feeding the widget
    @property
    def show_muted_enabled(self) -> bool:
        return self.muted_switch.isChecked()

    def set_show_muted(self, on: bool) -> None:
        self.muted_switch.setChecked(bool(on))
        self._toggle_muted()

    def hint_text(self) -> str:
        return self.hint_label.text()

    def set_source(self, duration: float, segments: Sequence[GameSegment] = (),
                   storyboard: Storyboard | None = None) -> None:
        """A new VOD: forget everything about the previous one."""
        self.duration = float(duration or 0)
        self.segments = list(segments)
        self.storyboard = storyboard
        self.frames = None
        if storyboard is not None and Image is None:
            self.frames_state = "failed"
        else:
            self.frames_state = "loading" if storyboard else "none"
        self.ranges = None
        self.clip_marks = []
        self.clip_details = {}
        self.set_muted(None, redraw=False)
        self._history.clear()
        self._future.clear()
        self._pixmaps.clear()
        self._preview_pixmaps.clear()
        self._drag = self._pan = None
        self._selected = self._hover_t = self._last_nudge = None
        self._highlight_title = None
        self._clear_snap_feedback(redraw=False)
        self._hover_pos = None
        self.vp = Viewport(self.duration or 1.0, self._draw_width())
        self._rebuild_snap_points()
        self._rebuild_legend()
        self._sync_buttons()
        self._sync_shimmer()
        self.hint_label.setText(IDLE_HINT)
        self.invalidate()

    def set_frames(self, frames: list | None) -> None:
        self.frames = frames
        self.frames_state = "ready" if frames and any(f is not None for f in frames) else "failed"
        self._pixmaps.clear()
        self._preview_pixmaps.clear()
        self._sync_shimmer()
        self.invalidate()

    def set_ranges(self, ranges: list[Range] | None) -> None:
        """The parts as the cut text describes them now (None = the text is invalid)."""
        new = None if ranges is None else [(s, e) for s, e in ranges]
        if new == self.ranges:
            return
        self.ranges = new
        self._selected = None
        self.invalidate()

    def set_clip_marks(self, times: Sequence[float], details: dict[float, str] | None = None) -> None:
        """The moments of the VOD's clips (flags in the ruler, snap points). ``details`` maps a moment to the text of
        its tooltip (title, creator, views)."""
        self.clip_marks = sorted(float(t) for t in times)
        self.clip_details = dict(details or {})
        self._rebuild_snap_points()
        self.invalidate()

    def set_muted(self, ranges: Sequence[Range] | None, redraw: bool = True) -> None:
        """The stretches Twitch silenced (None / empty = none, or not known). Drawn as a red line; cuts snap to them."""
        self.muted = sorted((float(s), float(e)) for s, e in (ranges or []) if e > s)
        if self.muted:
            total = sum(e - s for s, e in self.muted)
            n = len(self.muted)
            self.muted_info.setText(f"{n} stretch{'es' if n != 1 else ''} \u00b7 {fmt_hms(total)} silenced by Twitch")
            self.muted_switch.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.muted_box.show()
        else:
            self.muted_info.setText("")
            self.muted_switch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.muted_box.hide()
        self._rebuild_snap_points()
        if redraw:
            self.invalidate()

    def _toggle_muted(self, _checked: bool = False) -> None:
        self._rebuild_snap_points()  # hidden stretches are not snapped to either
        self.invalidate()

    def _muted_at(self, t: float) -> Range | None:
        return next(((s, e) for s, e in self.muted if s <= t < e), None) if self.show_muted_enabled else None

    def _rebuild_snap_points(self) -> None:
        self._snap_points = build_snap_points(
            self.duration, self.segments, self.clip_marks, self.muted, show_muted=self.show_muted_enabled
        )
        self._snap_kinds = build_snap_kinds(
            self.duration, self.segments, self.clip_marks, self.muted, show_muted=self.show_muted_enabled
        )

    # ------------------------------------------------------------------ game legend (E4)
    def _rebuild_legend(self) -> None:
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.legend_chips = []
        totals = game_totals(self.segments)
        for title, seconds in totals[:LEGEND_MAX_CHIPS]:
            chip = _LegendChip(title, seconds, self.legend_box)
            chip.clicked.connect(lambda _=False, t=title: self._on_chip_clicked(t))
            chip.hovered.connect(self._highlight_game)
            chip.unhovered.connect(lambda: self._highlight_game(None))
            self.legend_layout.addWidget(chip)
            self.legend_chips.append(chip)
        if len(totals) > LEGEND_MAX_CHIPS:
            more = QLabel(f"+{len(totals) - LEGEND_MAX_CHIPS} more")
            more.setProperty("role", "muted")
            self.legend_layout.addWidget(more)
        self.legend_box.setVisible(bool(self.legend_chips))
        self.legend_box.updateGeometry()

    def _on_chip_clicked(self, title: str) -> None:
        shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.isolate_game(title, only=shift)

    def _highlight_game(self, title: str | None) -> None:
        key = game_key(title) if title else None
        if key != self._highlight_title:
            self._highlight_title = key
            self.invalidate()

    def isolate_game(self, title: str, only: bool = False) -> None:
        """Every stretch of the game ``title`` becomes its own part (``only``: keep just those stretches)."""
        if not self._ready():
            return
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        key = game_key(title)
        spans = [(g.start, g.end) for g in self.segments if game_key(g.title or "") == key]
        if not spans:
            return
        if only:
            new: list[Range] = []
            for a, b in sorted(spans):
                a, b = max(0, round(a)), min(self.duration, round(b))
                if b - a < 1:
                    continue
                if new and abs(new[-1][1] - a) < 1e-6:
                    new[-1] = (new[-1][0], b)
                else:
                    new.append((a, b))
            if not new:
                return
        else:
            new = list(self.ranges)
            for a, b in spans:
                new = isolate_span(new, a, b, self.duration)
        if new != self.ranges:
            self._push_history()
            self._apply(new)
            self._say(f"{title}: " + ("kept alone" if only else "is its own part now"))

    # ------------------------------------------------------------------ zoom / scroll / undo
    def zoom_in(self) -> None:
        self._zoom(1.6, self.vp.width / 2)

    def zoom_out(self) -> None:
        self._zoom(1 / 1.6, self.vp.width / 2)

    def zoom_fit(self) -> None:
        self.vp.fit()
        self.invalidate()

    def _zoom(self, factor: float, anchor_x: float) -> None:
        if self.duration:
            self.vp.zoom(factor, anchor_x)
            self.invalidate()

    def _on_hbar_value(self, value: int) -> None:
        if self._updating_bar or not self.duration:
            return
        self.vp.pan_to((value / SCROLL_SCALE) * self.vp.duration)
        self.invalidate()

    def _update_scrollbar(self) -> None:
        self._updating_bar = True
        try:
            if self.duration and self.vp.zoomed:
                page = max(1, round((self.vp.span / self.vp.duration) * SCROLL_SCALE))
                maximum = max(0, SCROLL_SCALE - page)
                val = round((self.vp.start / self.vp.duration) * SCROLL_SCALE)
                self.hbar.setPageStep(page)
                self.hbar.setSingleStep(max(1, page // 10))
                self.hbar.setRange(0, maximum)
                self.hbar.setValue(min(max(val, 0), maximum))
            else:
                self.hbar.setPageStep(SCROLL_SCALE)
                self.hbar.setRange(0, 0)
                self.hbar.setValue(0)
        finally:
            self._updating_bar = False

    def undo(self) -> None:
        if not self._history or self.ranges is None:
            return
        self._future.append(list(self.ranges))
        del self._future[:-100]
        self.ranges = self._history.pop()
        self._selected = self._last_nudge = None
        self._sync_buttons()
        self.invalidate()
        self.on_edit(list(self.ranges))

    def redo(self) -> None:
        """Bring back the edit that ``undo`` took away (any new edit forgets what could be redone)."""
        if not self._future or self.ranges is None:
            return
        self._history.append(list(self.ranges))
        del self._history[:-100]
        self.ranges = self._future.pop()
        self._selected = self._last_nudge = None
        self._sync_buttons()
        self.invalidate()
        self.on_edit(list(self.ranges))

    def _push_history(self) -> None:
        if self.ranges is not None:
            self._history.append(list(self.ranges))
            del self._history[:-100]
            self._future.clear()
            self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.btn_undo.setEnabled(bool(self._history))
        self.btn_redo.setEnabled(bool(self._future))

    def _sync_chrome(self) -> None:
        """The pieces around the strip that follow the zoom: the minimap (instead of the scroll bar) and the readout."""
        if not hasattr(self, "legend_box"):  # still being built
            return
        zoomed = bool(self.duration and self.vp.zoomed)
        self.minimap.setVisible(zoomed)
        self.hbar.setVisible(not zoomed)
        if not self.duration:
            text = ""
        elif zoomed:
            text = f"Showing {fmt_hms(self.vp.span)} of {fmt_hms(self.duration)}"
        else:
            text = f"Showing the whole VOD \u00b7 {fmt_hms(self.duration)}"
        if self.zoom_label.text() != text:
            self.zoom_label.setText(text)
        self.minimap.update()

    # ------------------------------------------------------------------ coordinates
    def _draw_width(self) -> int:
        w = self.canvas.width()
        if w <= 50:
            w = max(self.width(), 400)
        return max(w - 2 * PADX, 1)

    def x_of(self, t: float) -> float:
        """Canvas x of the moment ``t``."""
        return PADX + self.vp.t2x(t)

    def t_at(self, x: float) -> float:
        return self.vp.x2t(x - PADX)

    def _snap(self, t: float) -> int:
        return snap_time(t, self._snap_points, self.vp.px_per_sec, SNAP_PX)

    def _snap_with_kind(self, t: float) -> tuple[int, str | None]:
        """Like ``_snap`` and also says what the moment snapped to (None: it did not snap)."""
        target = snap_target(t, self._snap_points, self.vp.px_per_sec, SNAP_PX)
        if target is None:
            return round(t), None
        return round(target), self._snap_kinds.get(target)

    def _set_snap_feedback(self, t: float, kind: str | None, ttl_ms: int = 0) -> None:
        """Show the guide line and «snaps to: …» label (E8). ``ttl_ms`` > 0: remove it by itself after that long."""
        self._snap_timer.stop()
        self._snap_feedback = (float(t), kind) if kind else None
        if self._snap_feedback is not None and ttl_ms > 0:
            self._snap_timer.start(ttl_ms)
        self.invalidate()

    def _clear_snap_feedback(self, redraw: bool = True) -> None:
        self._snap_timer.stop()
        if self._snap_feedback is not None:
            self._snap_feedback = None
            if redraw:
                self.invalidate()

    def _segment_at(self, t: float) -> GameSegment | None:
        return next((g for g in self.segments if g.start <= t < g.end), None)

    def _edge_at(self, x: float) -> Edge | None:
        if not self.ranges:
            return None
        return nearest_edge(self.ranges, self.t_at(x), EDGE_TOL_PX / self.vp.px_per_sec)

    # ------------------------------------------------------------------ mouse & interaction
    def _ready(self) -> bool:
        return bool(self.duration)

    def _say(self, text: str) -> None:
        self.hint_label.setText(text)

    def _on_press(self, x: float, y: float, shift: bool = False) -> None:
        self.canvas.setFocus()
        if not self._ready():
            return
        zone = zone_at(y)
        if zone == "ruler":
            self._pan = (x, self.vp.start)
            return
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        edge = self._edge_at(x)
        if edge is not None:
            self._push_history()
            self._drag = edge
            self._selected = (edge.kind, edge.index)
            self.invalidate()
            return
        self._selected = None
        t = self.t_at(x)
        if zone == "thumbs":
            self._cut_at(t)
        elif zone == "parts":
            self._toggle_part_at(t)

    def _toggle_part_at(self, t: float) -> None:
        if self.ranges is None:
            return
        new = toggle_part(self.ranges, t, self.duration)
        if new is None:
            self._say("At least one part has to stay.")
            return
        self._push_history()
        self._apply(new)

    def _cut_at(self, t: float, follow: bool = True) -> None:
        """Cut at ``t`` (snapped). ``follow``: the new line sticks to the mouse while the button is down."""
        assert self.ranges is not None
        t, kind = self._snap_with_kind(t)
        new = add_cut(self.ranges, t)
        if new is None:
            if part_index_at(self.ranges, t) is None:
                self._say("That section is skipped: click it in the parts row to keep it again.")
            else:
                self._say("There is already a cut line there.")
            return
        self._push_history()
        self._apply(new)
        added = next((e for e in edges_of(new) if e.kind == "cut" and e.t == t), None)
        self._selected = (added.kind, added.index) if added is not None else None
        if follow:
            self._drag = added  # the new line follows the mouse while the button is down
        self._set_snap_feedback(t, kind, ttl_ms=0 if follow else 1500)

    def _on_double(self, x: float, y: float, shift: bool = False) -> None:
        if not self._ready() or zone_at(y) != "games":
            self._on_press(x, y, shift=shift)
            return
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        self.isolate_game_at(self.t_at(x), only=shift)

    def isolate_game_at(self, t: float, only: bool = False) -> None:
        """The game stretch at ``t`` becomes its own part (``only``: keep just that stretch)."""
        if self.ranges is None:
            return
        seg = self._segment_at(t)
        if seg is None:
            return
        new = isolate_span(self.ranges, seg.start, seg.end, self.duration, only=only)
        if new != self.ranges:
            self._push_history()
            self._apply(new)

    def _on_motion(self, x: float, y: float) -> None:
        if self._pan is not None:
            x0, start0 = self._pan
            self.vp.pan_to(start0 - (x - x0) / self.vp.px_per_sec)
            self.invalidate()
        elif self._drag is not None and self.ranges is not None:
            t, kind = self._snap_with_kind(self.t_at(x))
            new = move_edge(self.ranges, self._drag, t, self.duration)
            if new != self.ranges:
                moved = next((e for e in edges_of(new) if e.kind == self._drag.kind and e.index == self._drag.index), None)
                self._apply(new)
                if moved is not None:
                    self._drag = moved
                    self._selected = (moved.kind, moved.index)
            self._snap_feedback = (float(t), kind) if kind else None
            self._hover_pos = (x, y, True)
            self.invalidate()

    def _on_release(self) -> None:
        self._drag = None
        self._pan = None
        self._hover_pos = None
        self._clear_snap_feedback(redraw=False)
        self.invalidate()

    def _on_right(self, x: float, y: float, global_pos: QPoint | None = None) -> None:
        if not self._ready() or self.ranges is None or zone_at(y) == "ruler":
            return
        edge = self._edge_at(x)
        if edge is None:
            self._show_context_menu(self.t_at(x), global_pos)
            return
        if edge.kind != "cut":
            self._say("Only a cut line between two parts can be removed (click the part to skip it instead).")
            return
        self._push_history()
        self._selected = None
        self._apply(remove_cut(self.ranges, edge.index))

    # ------------------------------------------------------------------ right-click menu (E7)
    def _build_context_menu(self, t: float) -> QMenu:
        """The menu for a right-click on empty timeline at moment ``t`` (a cut line keeps removing itself instead)."""
        t = max(0.0, min(t, float(self.duration)))
        menu = QMenu(self.canvas)
        menu.setObjectName("timelineMenu")
        ranges = self.ranges
        editable = ranges is not None
        snapped = self._snap(t)
        can_cut = editable and add_cut(ranges, snapped) is not None
        act = menu.addAction(icon("scissors", 16), f"Cut here  ({fmt_hms(snapped)})")
        act.setEnabled(can_cut)
        act.triggered.connect(lambda _=False, at=t: self._cut_at(at, follow=False))
        kept = editable and part_index_at(ranges, t) is not None
        act = menu.addAction(icon("x" if kept else "plus", 16), "Skip this part" if kept else "Keep this section")
        act.setEnabled(editable and (not kept or len(ranges) > 1))
        act.triggered.connect(lambda _=False, at=t: self._toggle_part_at(at))
        seg = self._segment_at(t)
        name = f" ({seg.title})" if seg and seg.title else ""
        act = menu.addAction(icon("flag", 16), f"Isolate this game{name}")
        act.setEnabled(editable and seg is not None)
        act.triggered.connect(lambda _=False, at=t: self.isolate_game_at(at))
        menu.addSeparator()
        act = menu.addAction(icon("undo", 16), "Undo")
        act.setEnabled(bool(self._history))
        act.triggered.connect(self.undo)
        act = menu.addAction(icon("redo", 16), "Redo")
        act.setEnabled(bool(self._future))
        act.triggered.connect(self.redo)
        return menu

    def _show_context_menu(self, t: float, global_pos: QPoint | None) -> None:
        if self._context_menu is not None:
            self._context_menu.close()
            self._context_menu.deleteLater()
        self._context_menu = self._build_context_menu(t)
        if global_pos is not None:
            self._context_menu.popup(global_pos)  # popup, not exec: it must never block

    # ------------------------------------------------------------------ keyboard (E2)
    def _edge_target(self) -> Edge | None:
        """The cut line the keyboard acts on: the selected one, else the one nearest the mouse."""
        if not self.ranges:
            return None
        if self._selected is not None:
            found = next((e for e in edges_of(self.ranges) if (e.kind, e.index) == self._selected), None)
            if found is not None:
                return found
            self._selected = None
        if self._hover_t is None:
            return None
        return nearest_edge(self.ranges, self._hover_t, 40 / self.vp.px_per_sec)

    def _on_key(self, event) -> bool:
        """S cut at the mouse · Delete remove the cut · arrows nudge it · Home/End · +/-/0 zoom. Ctrl combos are
        shortcuts (undo / redo), not handled here. True = the key was used."""
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            return False
        if not self._ready():
            return False
        key = event.key()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        K = Qt.Key
        if key == K.Key_S:
            self.cut_at_hover()
        elif key in (K.Key_Delete, K.Key_Backspace):
            self.remove_selected_cut()
        elif key in (K.Key_Left, K.Key_Right):
            step = NUDGE_ALT_STEP if alt else (NUDGE_SHIFT_STEP if shift else NUDGE_STEP)
            self.nudge_edge(-1 if key == K.Key_Left else 1, step)
        elif key == K.Key_Home:
            self.vp.pan_to(0)
            self.invalidate()
        elif key == K.Key_End:
            self.vp.pan_to(self.duration - self.vp.span)
            self.invalidate()
        elif key in (K.Key_Plus, K.Key_Equal):
            self.zoom_in()
        elif key in (K.Key_Minus, K.Key_Underscore):
            self.zoom_out()
        elif key == K.Key_0:
            self.zoom_fit()
        else:
            return False
        return True

    def cut_at_hover(self) -> None:
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
        elif self._hover_t is None:
            self._say("Move the mouse over the timeline first, then press S to cut there.")
        else:
            self._cut_at(self._hover_t, follow=False)

    def remove_selected_cut(self) -> None:
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        edge = self._edge_target()
        if edge is None:
            self._say("Click a cut line (or hold the mouse next to it), then press Delete to remove it.")
        elif edge.kind != "cut":
            self._say("Only a cut line between two parts can be removed (click the part to skip it instead).")
        else:
            self._push_history()
            self._selected = None
            self._apply(remove_cut(self.ranges, edge.index))

    def nudge_edge(self, direction: int, step: float) -> None:
        """Move the selected / nearest cut line ``step`` seconds (Left = -1, Right = +1). With none, pan instead."""
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        edge = self._edge_target()
        if edge is None:
            self.vp.pan_to(self.vp.start + direction * self.vp.span * 0.1)
            self.invalidate()
            return
        new = move_edge(self.ranges, edge, edge.t + direction * step, self.duration)
        if new == self.ranges:
            return
        key = (edge.kind, edge.index)
        now = time.monotonic()
        if not (self._last_nudge and self._last_nudge[0] == key and now - self._last_nudge[1] < 0.8):
            self._push_history()  # one undo takes back a whole run of nudges
        self._last_nudge = (key, now)
        moved = next((e for e in edges_of(new) if e.kind == edge.kind and e.index == edge.index), None)
        self._apply(new)
        if moved is not None:
            self._selected = (moved.kind, moved.index)
            if not (self.vp.start <= moved.t <= self.vp.start + self.vp.span):
                self.vp.pan_to(moved.t - self.vp.span / 2)
            self._say(f"Cut line at {fmt_hms(moved.t)}")
            _, kind = self._snap_with_kind(moved.t)
            self._set_snap_feedback(moved.t, kind, ttl_ms=1500)
        self.invalidate()

    def _on_wheel(self, x: float, delta: float, shift: bool = False) -> None:
        if not self._ready() or delta == 0:
            return
        direction = 1 if delta > 0 else -1
        if shift:  # Shift: move along the VOD
            self.vp.pan_to(self.vp.start - direction * self.vp.span * 0.15)
            self.invalidate()
        else:
            self._zoom(1.25 if direction > 0 else 1 / 1.25, x - PADX)

    def _apply(self, ranges: list[Range]) -> None:
        self.ranges = ranges
        self.invalidate()
        self.on_edit(list(ranges))

    # ------------------------------------------------------------------ clip flags (E5)
    def _flags(self) -> list[tuple[float, float, int, float, float]]:
        """The flags / counter badges the ruler shows now: ``(x, centre_time, count, first_time, last_time)``."""
        vp = self.vp
        lo, hi = vp.start - 12 / vp.px_per_sec, vp.start + vp.span + 12 / vp.px_per_sec
        visible = [t for t in self.clip_marks if lo <= t <= hi]
        out = []
        for centre, count, first, last in cluster_marks(visible, vp.px_per_sec, FLAG_MIN_PX):
            x = self.x_of(centre)
            if PADX - 6 <= x <= PADX + vp.width + 6:
                out.append((x, centre, count, first, last))
        return out

    def _flag_text(self, count: int, first: float, last: float) -> str:
        if count == 1:
            detail = self.clip_details.get(first, "")
            return f"{detail}\nat {fmt_hms(first)}" if detail else f"Clip at {fmt_hms(first)}"
        times = [t for t in self.clip_marks if first <= t <= last]
        lines = [f"{count} clips between {fmt_hms(first)} and {fmt_hms(last)}"]
        lines += [f"\u2022 {self.clip_details.get(t, fmt_hms(t))}" for t in times[:4]]
        if len(times) > 4:
            lines.append(f"\u2026 and {len(times) - 4} more (zoom in to see them)")
        return "\n".join(lines)

    def _flag_at(self, x: float, y: float) -> str:
        """The tooltip of the flag / badge under the mouse, or "" when there is none."""
        if y > Y_RULER + 14:
            return ""
        for fx, _centre, count, first, last in self._flags():
            reach = 6 if count == 1 else 9
            if abs(x - fx) <= reach:
                return self._flag_text(count, first, last)
        return ""

    # ------------------------------------------------------------------ hover
    def _on_hover(self, x: float, y: float) -> None:
        if not self._ready() or self._drag is not None or self._pan is not None:
            return
        zone = zone_at(y)
        t = self.t_at(x)
        self._hover_t = max(0.0, min(t, float(self.duration)))
        edge = self._edge_at(x) if zone != "ruler" else None
        seg = self._segment_at(t)
        where = f"{fmt_hms(max(0, min(t, self.duration)))}" + (f"  \u00b7  {seg.title}" if seg and seg.title else "")
        mu = self._muted_at(t)
        if mu is not None:
            where += f"  \u00b7  muted by Twitch ({fmt_hms(mu[0])} \u2192 {fmt_hms(mu[1])})"
        tip = self._flag_at(x, y) if zone == "ruler" else ""
        if edge is not None:
            what = "drag to move" + (", right-click to remove" if edge.kind == "cut" else "")
            cursor = Qt.CursorShape.SizeHorCursor
        elif tip:
            what, cursor = "clip flag", Qt.CursorShape.PointingHandCursor
        elif zone == "ruler":
            what, cursor = "drag to move along the VOD", Qt.CursorShape.SizeAllCursor
        elif zone == "games":
            what, cursor = "double-click: make this game its own part (Shift: only this game)", Qt.CursorShape.ArrowCursor
        elif zone == "thumbs":
            what, cursor = "click to cut here (or press S)", Qt.CursorShape.CrossCursor
        else:
            kept = self.ranges is not None and part_index_at(self.ranges, t) is not None
            what, cursor = ("click to skip this part" if kept else "click to keep this section"), Qt.CursorShape.PointingHandCursor
        if self.canvas.toolTip() != tip:
            self.canvas.setToolTip(tip)
        self.canvas.setCursor(cursor)
        self._say(f"{where}  \u00b7  {what}")
        self._hover_pos = (x, y, False)
        self.invalidate()

    def _on_leave(self) -> None:
        self._hover_pos = None
        self._hover_t = None
        self.canvas.setToolTip("")
        self.canvas.unsetCursor()
        if self._drag is None:
            self.hint_label.setText(IDLE_HINT)
        self.invalidate()

    # ------------------------------------------------------------------ images
    def _frame_image(self, idx: int):
        if not self.frames or not (0 <= idx < len(self.frames)):
            return None
        return self.frames[idx]

    def _pixmap(self, idx: int, dim: bool) -> QPixmap | None:
        key = (idx, dim)
        if key not in self._pixmaps:
            im = self._frame_image(idx)
            if im is None or Image is None:
                return None
            im = im.resize((THUMB_W, THUMB_H))
            if dim and ImageEnhance is not None:
                im = ImageEnhance.Brightness(im).enhance(0.35)
            pm = _pil_to_qpixmap(im)
            if pm is None:
                return None
            self._pixmaps[key] = pm
        return self._pixmaps[key]

    def _preview_pixmap(self, idx: int) -> QPixmap | None:
        if idx not in self._preview_pixmaps:
            im = self._frame_image(idx)
            if im is None or Image is None:
                return None
            if im.width > PREVIEW_MAX_W:
                im = im.resize((PREVIEW_MAX_W, round(im.height * PREVIEW_MAX_W / im.width)))
            pm = _pil_to_qpixmap(im)
            if pm is None:
                return None
            self._preview_pixmaps[idx] = pm
        return self._preview_pixmaps[idx]

    # ------------------------------------------------------------------ drawing
    def invalidate(self) -> None:
        """Schedule a repaint (coalesced through Qt's update mechanism and ``_redraw_pending``)."""
        self.vp.width = self._draw_width()
        if self.duration:
            self.vp.clamp()
        self._update_scrollbar()
        self._sync_chrome()
        if not self._redraw_pending:
            self._redraw_pending = True
            if hasattr(self, "_redraw_timer"):
                self._redraw_timer.start(0)
            else:
                QTimer.singleShot(0, self._flush_redraw)
        try:
            if hasattr(self, "canvas") and isValid(self.canvas):
                self.canvas.update()
        except RuntimeError:
            pass

    def _flush_redraw(self) -> None:
        self._redraw_pending = False
        try:
            if hasattr(self, "canvas") and isValid(self.canvas):
                self.canvas.update()
        except RuntimeError:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802
        for name in ("_redraw_timer", "_shimmer_timer", "_snap_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                timer.stop()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_shimmer()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._shimmer_timer.stop()

    # ------------------------------------------------------------------ loading shimmer (E9)
    def _sync_shimmer(self) -> None:
        """The thumbnail placeholders shimmer only while frames load, the widget is on screen and motion is allowed."""
        want = (self.frames_state == "loading" and bool(self.duration) and self.isVisible() and _motion_enabled())
        if want and not self._shimmer_timer.isActive():
            self._shimmer_timer.start()
        elif not want and self._shimmer_timer.isActive():
            self._shimmer_timer.stop()

    def _on_shimmer(self) -> None:
        if self.frames_state != "loading":
            self._shimmer_timer.stop()
            return
        self._shimmer_phase = (self._shimmer_phase + SHIMMER_STEP) % 1.0
        self.canvas.update()

    def redraw(self) -> None:
        """Force an immediate synchronous paint/state update (useful in tests)."""
        self._redraw_pending = False
        self.vp.width = self._draw_width()
        if self.duration:
            self.vp.clamp()
        self._update_scrollbar()
        self._sync_chrome()
        pm = QPixmap(max(self.canvas.width(), 400), HEIGHT)
        self._paint_canvas(pm)
        self.canvas.update()
        if self.minimap.isVisible():
            mpm = QPixmap(max(self.minimap.width(), 400), MINIMAP_H)
            self._paint_minimap(mpm)
            self.minimap.update()

    def _paint_minimap(self, target) -> None:
        p = QPainter(target)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = target.width() if hasattr(target, "width") else self.minimap.width()
        h = target.height() if hasattr(target, "height") else self.minimap.height()
        track = QRectF(PADX, 1, max(w - 2 * PADX, 1), h - 2)
        p.fillRect(QRectF(0, 0, w, h), QColor(BG))
        p.fillRect(track, QColor(BG2))
        for g in self.segments:
            x0, x1 = self.minimap.x_of(g.start), self.minimap.x_of(g.end)
            col = QColor(game_colour(g.title))
            col.setAlpha(170)
            p.fillRect(QRectF(x0, track.top(), max(x1 - x0, 1.0), track.height()), col)
        if self.ranges:
            keep = QColor(ACCENT)
            for s, e in self.ranges:
                p.fillRect(
                    QRectF(self.minimap.x_of(s), track.bottom() - 2, max(self.minimap.x_of(e) - self.minimap.x_of(s), 1.0), 2),
                    keep,
                )
            p.setPen(QPen(QColor(CUT_COLOUR), 1))
            for edge in edges_of(self.ranges):
                if edge.kind == "cut":
                    x = self.minimap.x_of(edge.t)
                    p.drawLine(QPointF(x, track.top()), QPointF(x, track.bottom()))
        x0, x1 = self.minimap.lens()
        self.minimap.drawn_lens = (x0, x1)
        fill = QColor(ACCENT_HOVER)
        fill.setAlpha(70)
        lens = QRectF(x0, 0.5, x1 - x0, h - 1)
        p.fillRect(lens, fill)
        p.setPen(QPen(QColor(ACCENT_HOVER), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(lens, 3, 3)
        p.end()

    def _x_range(self, start: float, end: float) -> tuple[float, float] | None:
        """Pixel span of ``[start, end]``, clipped to the drawing area; None if it is not visible."""
        x0 = max(self.x_of(start), PADX)
        x1 = min(self.x_of(end), PADX + self.vp.width)
        return (x0, x1) if x1 > x0 else None

    def _paint_canvas(self, widget: QWidget) -> None:
        self.drawn_texts.clear()
        self.drawn_muted_rects.clear()
        self.drawn_skipped_rects.clear()
        self.drawn_flags.clear()
        self.drawn_thumb_count = 0
        self.drawn_hover_preview = False

        p = QPainter(widget)
        p.fillRect(widget.rect(), QColor(BG))

        if not self.duration:
            self._draw_text(
                p, QRectF(0, 0, widget.width() or 400, HEIGHT),
                "Press «Get info» to see the VOD here.", MUTED, 10, Qt.AlignmentFlag.AlignCenter,
            )
            self._update_scrollbar()
            p.end()
            return

        self.vp.width = self._draw_width()
        self.vp.clamp()
        self._draw_ruler(p)
        self._draw_games(p)
        self._draw_muted(p)
        self._draw_thumbs(p)
        self._draw_parts(p)
        self._draw_snap_feedback(p)
        if self._hover_pos is not None:
            hx, hy, dragging = self._hover_pos
            self._draw_hover_overlay(p, hx, hy, dragging=dragging)
        self._update_scrollbar()
        p.end()

    def _draw_text(self, p: QPainter, rect: QRectF, text: str, colour: str, size_pt: int,
                   align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> None:
        self.drawn_texts.append(text)
        font = QFont(UI_FONT, size_pt)
        p.setFont(font)
        p.setPen(QColor(colour))
        p.drawText(rect, int(align), text)

    def _draw_ruler(self, p: QPainter) -> None:
        vp = self.vp
        step = nice_step(vp.px_per_sec)
        t = math.floor(vp.start / step) * step
        base = Y_RULER + RULER_H
        font = QFont(UI_FONT, 8)
        p.setFont(font)
        muted_col = QColor(MUTED)
        while t <= vp.start + vp.span + step:
            x = self.x_of(t)
            if PADX - 1 <= x <= PADX + vp.width + 1:
                p.setPen(muted_col)
                p.drawLine(QPointF(x, base - 5), QPointF(x, base))
                txt = fmt_hms(t)
                self.drawn_texts.append(txt)
                p.drawText(QRectF(x + 3, Y_RULER, 72, RULER_H - 2),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), txt)
            t += step
        # clip flags; flags that would sit on top of each other merge into one counter badge (E5)
        ok_col = QColor(OK)
        for fx, _centre, count, _first, _last in self._flags():
            if not (PADX - 1 <= fx <= PADX + vp.width + 1):
                continue
            self.drawn_flags.append((fx, count))
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if count == 1:
                p.setPen(QPen(ok_col, 1.4))
                p.drawLine(QPointF(fx, Y_RULER + 1), QPointF(fx, Y_RULER + 11))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ok_col)
                p.drawPolygon(QPolygonF([QPointF(fx, Y_RULER + 1), QPointF(fx + 8, Y_RULER + 4.5), QPointF(fx, Y_RULER + 8)]))
                p.restore()
            else:
                label = str(count) if count < 100 else "99+"
                w = max(16.0, 7.5 * len(label) + 8)
                badge = QRectF(fx - w / 2, Y_RULER + 1, w, 13)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ok_col)
                p.drawRoundedRect(badge, 6.5, 6.5)
                p.restore()
                self._draw_text(p, badge, label, BG, 8, Qt.AlignmentFlag.AlignCenter)

    def _draw_games(self, p: QPainter) -> None:
        if not self.segments:
            p.fillRect(QRectF(PADX, Y_GAMES, self.vp.width, GAMES_H), QColor(BG2))
            self._draw_text(
                p, QRectF(PADX + 6, Y_GAMES, self.vp.width - 12, GAMES_H),
                "No game information for this VOD", MUTED, 9,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            return
        bg_pen = QPen(QColor(BG), 1)
        hl = self._highlight_title
        for g in self.segments:
            span = self._x_range(g.start, g.end)
            if span is None:
                continue
            x0, x1 = span
            rect = QRectF(x0, Y_GAMES, x1 - x0, GAMES_H)
            mine = hl is not None and game_key(g.title or "") == hl
            col = QColor(game_colour(g.title))
            if hl is not None and not mine:
                col.setAlpha(70)  # another game is lit up (legend hover): fade this one
            p.fillRect(rect, col)
            p.setPen(bg_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)
            if mine:
                p.setPen(QPen(QColor(WHITE), 2))
                p.drawRect(rect.adjusted(1, 1, -1, -1))
            room = int((x1 - x0 - 8) / 6.3)
            if room >= 3 and g.title:
                text = g.title if len(g.title) <= room else g.title[: room - 1] + "\u2026"
                self._draw_text(
                    p, QRectF(x0 + 4, Y_GAMES, max(0.0, x1 - x0 - 8), GAMES_H),
                    text, WHITE, 9, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                )

    def _draw_muted(self, p: QPainter) -> None:
        """A thin red line along the bottom of the games bar wherever Twitch silenced the audio."""
        if not self.muted or not self.show_muted_enabled:
            return
        y0 = Y_GAMES + GAMES_H - MUTED_H
        col = QColor(MUTED_COLOUR)
        for s, e in self.muted:
            span = self._x_range(s, e)
            if span is None:
                continue
            x0, x1 = span
            w = max(x1 - x0, 2.0)  # keep each stretch at least 2 px wide so it is visible at Fit on long VODs
            p.fillRect(QRectF(x0, y0, w, MUTED_H), col)
            self.drawn_muted_rects.append((x0, float(y0), x0 + w, float(Y_GAMES + GAMES_H)))

    def _draw_thumbs(self, p: QPainter) -> None:
        vp = self.vp
        track = QRectF(PADX, Y_THUMBS, vp.width, THUMB_H)
        p.fillRect(track, QColor(BG2))
        sb = self.storyboard
        if self.frames_state != "ready" or sb is None or Image is None:
            msg = {"loading": "Loading thumbnails\u2026", "failed": "Thumbnails are not available",
                   "none": "This VOD has no preview thumbnails"}.get(self.frames_state, "")
            if sb is not None and Image is None:
                msg = "Thumbnails need Pillow (pip install pillow)"
            if self.frames_state == "loading" and Image is not None:
                self._draw_shimmer(p, track)
            else:
                # no pictures will come: a neutral striped placeholder (the game colours above still tell the story)
                p.fillRect(track, QBrush(QColor(BG3), Qt.BrushStyle.BDiagPattern))
            self._draw_placeholder_label(p, track, msg)
            return
        per_frame = vp.px_per_sec * sb.interval  # pixels one frame covers
        step = max(1, math.ceil(THUMB_W / per_frame))  # show every `step`-th frame so they do not overlap
        first = max(0, int(vp.start / sb.interval) // step * step - step)
        p.save()
        p.setClipRect(QRectF(PADX, Y_THUMBS, vp.width, THUMB_H))
        for i in range(first, sb.count, step):
            x = self.x_of(sb.frame_time(i))
            if x > PADX + vp.width:
                break
            if x + THUMB_W < PADX:
                continue
            kept = self.ranges is None or part_index_at(self.ranges, sb.frame_time(i)) is not None
            pm = self._pixmap(i, dim=not kept)
            if pm is None:
                continue
            p.drawPixmap(round(x), Y_THUMBS, pm)
            self.drawn_thumb_count += 1
        p.restore()

    def _draw_shimmer(self, p: QPainter, track: QRectF) -> None:
        """Grey picture-shaped tiles with a soft light sweeping over them while the thumbnails download."""
        p.save()
        p.setClipRect(track)
        tile = QColor(BG3)
        tile.setAlpha(150)
        x = track.left() + 2
        while x < track.right():
            p.fillRect(QRectF(x, track.top() + 4, THUMB_W - 6, THUMB_H - 8), tile)
            x += THUMB_W
        band = max(120.0, track.width() * 0.25)
        cx = track.left() - band + self._shimmer_phase * (track.width() + 2 * band)
        grad = QLinearGradient(cx - band / 2, 0, cx + band / 2, 0)
        light = QColor(FG)
        clear = QColor(FG)
        clear.setAlpha(0)
        light.setAlpha(38)
        grad.setColorAt(0.0, clear)
        grad.setColorAt(0.5, light)
        grad.setColorAt(1.0, clear)
        p.fillRect(track, QBrush(grad))
        p.restore()

    def _draw_placeholder_label(self, p: QPainter, track: QRectF, msg: str) -> None:
        if not msg:
            return
        fm = QFontMetricsF(QFont(UI_FONT, 9))
        w = min(track.width() - 8, fm.horizontalAdvance(msg) + 32)
        pill = QRectF(track.center().x() - w / 2, track.center().y() - 11, w, 22)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fill = QColor(BG2)
        fill.setAlpha(235)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(pill, 11, 11)
        p.restore()
        self._draw_text(p, track, msg, MUTED, 9, Qt.AlignmentFlag.AlignCenter)

    def _draw_parts(self, p: QPainter) -> None:
        vp = self.vp
        track = QRectF(PADX, Y_PARTS, vp.width, PARTS_H)
        p.fillRect(track, QColor(BG2))
        if self.ranges is None:
            self._draw_text(
                p, track,
                "The cut points text has an error: fix it to edit here.", ERR, 9, Qt.AlignmentFlag.AlignCenter,
            )
            return
        # skipped sections are hatched, so "left out" reads even without colour (E1)
        hatch = QColor(MUTED)
        hatch.setAlpha(120)
        for s, e in gaps_of(self.ranges, self.duration):
            span = self._x_range(s, e)
            if span is None:
                continue
            x0, x1 = span
            area = QRectF(x0, Y_PARTS, x1 - x0, PARTS_H)
            p.fillRect(area, QBrush(hatch, Qt.BrushStyle.BDiagPattern))
            self.drawn_skipped_rects.append((x0, float(Y_PARTS), x1, float(Y_PARTS + PARTS_H)))
        if not self.ranges:
            self._draw_text(
                p, track,
                "No parts yet: click here to start with the whole VOD.", MUTED, 9, Qt.AlignmentFlag.AlignCenter,
            )
        bg_pen = QPen(QColor(BG), 1)
        hover_part = None
        if self._hover_pos is not None and self._drag is None:
            hx, hy, _dragging = self._hover_pos
            if zone_at(hy) == "parts":
                hover_part = part_index_at(self.ranges, self.t_at(hx))
        view_end = vp.start + vp.span
        for n, (s, e) in enumerate(self.ranges, 1):
            span = self._x_range(s, e)
            if span is None:
                continue
            x0, x1 = span
            hovered = hover_part == n - 1
            rect = QRectF(x0, Y_PARTS - (1 if hovered else 0), x1 - x0, PARTS_H)  # a hovered part lifts 1 px
            radius = min(PART_RADIUS, rect.width() / 2, rect.height() / 2)
            fill = QColor(ACCENT_HOVER if hovered else ACCENT)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            p.fillPath(path, fill)
            # an end that runs off the visible window is not an end: keep it square
            if s < vp.start - 1e-6:
                p.fillRect(QRectF(rect.left(), rect.top(), radius, rect.height()), fill)
            if e > view_end + 1e-6:
                p.fillRect(QRectF(rect.right() - radius, rect.top(), radius, rect.height()), fill)
            p.setPen(bg_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.restore()
            dur = fmt_hms(e - s)
            width = x1 - x0
            for label in (f"Part {n} \u00b7 {dur}", f"P{n} \u00b7 {dur}"):
                if width >= len(label) * 6.5 + 10:
                    self._draw_text(p, rect, label, WHITE, 9, Qt.AlignmentFlag.AlignCenter)
                    break
            else:
                if width >= 30:
                    self._draw_text(p, rect, str(n), WHITE, 9, Qt.AlignmentFlag.AlignCenter)
        for edge in edges_of(self.ranges):
            x = self.x_of(edge.t)
            if not (PADX - 1 <= x <= PADX + vp.width + 1):
                continue
            grabbed = self._drag is not None and (edge.kind, edge.index) == (self._drag.kind, self._drag.index)
            selected = self._selected == (edge.kind, edge.index)
            colour = QColor(OK if (grabbed or selected) else (CUT_COLOUR if edge.kind == "cut" else EDGE_COLOUR))
            p.setPen(QPen(colour, 3 if selected else 2))
            p.drawLine(QPointF(x, Y_GAMES), QPointF(x, Y_PARTS + PARTS_H))
            handle = QRectF(x - 3, Y_PARTS + 5, 6, PARTS_H - 10)
            p.fillRect(handle, colour)
            p.setPen(bg_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(handle)

    def _draw_snap_feedback(self, p: QPainter) -> None:
        """While a cut sticks to something: a thin guide line and «snaps to: …» (E8)."""
        if self._snap_feedback is None:
            return
        t, kind = self._snap_feedback
        x = self.x_of(t)
        if not (PADX - 1 <= x <= PADX + self.vp.width + 1):
            return
        p.setPen(QPen(QColor(OK), 1))
        p.drawLine(QPointF(x, Y_GAMES), QPointF(x, Y_PARTS + PARTS_H))
        text = f"snaps to: {kind}"
        w = QFontMetricsF(QFont(UI_FONT, 8)).horizontalAdvance(text) + 14
        left = x + 6 if x + 6 + w < PADX + self.vp.width else x - 6 - w
        pill = QRectF(left, Y_THUMBS + 3, w, 17)
        p.fillRect(pill, QColor(BG3))
        p.setPen(QPen(QColor(OK), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(pill)
        self._draw_text(p, pill, text, OK, 8, Qt.AlignmentFlag.AlignCenter)

    def _draw_hover_overlay(self, p: QPainter, x: float, _y: float, dragging: bool = False) -> None:
        if not self.duration or not (PADX <= x <= PADX + self.vp.width):
            return
        t = max(0.0, min(self.t_at(x), self.duration))
        dash_pen = QPen(QColor(MUTED), 1, Qt.PenStyle.DashLine)
        p.setPen(dash_pen)
        p.drawLine(QPointF(x, 0), QPointF(x, HEIGHT))
        label = fmt_hms(t)
        tx = min(max(x, PADX + 26), PADX + self.vp.width - 26)
        badge = QRectF(tx - 26, 2, 52, RULER_H - 5)
        p.fillRect(badge, QColor(BG3))
        self._draw_text(p, badge, label, FG, 9, Qt.AlignmentFlag.AlignCenter)
        if dragging or self.frames_state != "ready" or Image is None or self.storyboard is None:
            return
        idx = self.storyboard.frame_index_at(t)
        pm = self._preview_pixmap(idx)
        if pm is None:
            return
        w, h = pm.width(), pm.height()
        left = x + 14 if x + 14 + w < PADX + self.vp.width else x - 14 - w
        top = Y_GAMES
        box = QRectF(left - 2, top - 2, w + 4, h + 4)
        p.fillRect(box, QColor(BG))
        p.setPen(QPen(QColor(FG), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(box)
        p.drawPixmap(round(left), round(top), pm)
        self.drawn_hover_preview = True
