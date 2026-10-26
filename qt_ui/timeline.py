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
from typing import Callable, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut,
)
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollBar, QSizePolicy, QVBoxLayout, QWidget,
)

try:
    from shiboken6 import isValid
except ImportError:
    def isValid(obj: object) -> bool:  # noqa: N802
        return True

from core.palette import ACCENT, BG, BG2, BG3, ERR, FG, MUTED, OK, UI_FONT, WHITE
from core.timeline import (
    CUT_COLOUR, EDGE_COLOUR, EDGE_TOL_PX, GAME_COLOURS, GAMES_H, GAP, HEIGHT, IDLE_HINT, MUTED_COLOUR, MUTED_H,
    PADX, PARTS_H, PREVIEW_MAX_W, RULER_H, SNAP_PX, THUMB_H, THUMB_W, Viewport, Y_GAMES, Y_PARTS, Y_RULER,
    Y_THUMBS, build_snap_points, game_colour, nice_step, snap_time, y_of, zone_at,
)
from luckytwitch_engine import (
    Edge, GameSegment, Range, Storyboard, add_cut, edges_of, fmt_hms, isolate_span, move_edge, nearest_edge,
    part_index_at, remove_cut, toggle_part,
)
from qt_ui.widgets import Toggle, WrapLabel

try:  # thumbnails are PIL images returned by the engine; everything else works without Pillow
    from PIL import Image, ImageEnhance
except ImportError:  # pragma: no cover - exercised by patching Image = None
    Image = ImageEnhance = None

__all__ = [
    "CUT_COLOUR", "EDGE_COLOUR", "EDGE_TOL_PX", "GAME_COLOURS", "GAMES_H", "GAP", "HEIGHT", "IDLE_HINT",
    "MUTED_COLOUR", "MUTED_H", "PADX", "PARTS_H", "PREVIEW_MAX_W", "RULER_H", "SNAP_PX", "THUMB_H", "THUMB_W",
    "Timeline", "TimelineCanvas", "Viewport", "Y_GAMES", "Y_PARTS", "Y_RULER", "Y_THUMBS", "game_colour",
    "nice_step", "y_of", "zone_at",
]

SCROLL_SCALE = 10_000


def _pil_to_qpixmap(im) -> QPixmap | None:
    """Convert a PIL ``Image`` to a ``QPixmap`` on the GUI thread."""
    if im is None:
        return None
    rgba = im.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


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
            self.tl._on_right(pos.x(), pos.y())
            event.accept()
            return
        if btn == Qt.MouseButton.LeftButton:
            self.tl._on_press(pos.x(), pos.y(), shift=shift)
            event.accept()
            return
        super().mousePressEvent(event)

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
        self.muted: list[Range] = []  # stretches Twitch silenced (VOD seconds)
        self.vp = Viewport()
        self._history: list[list[Range]] = []
        self._drag: Edge | None = None
        self._pan: tuple[float, float] | None = None
        self._pixmaps: dict[tuple[int, bool], QPixmap] = {}
        self._preview_pixmaps: dict[int, QPixmap] = {}
        self._snap_points: list[float] = []
        self._hover_pos: tuple[float, float, bool] | None = None  # (x, y, dragging)
        self._updating_bar = False
        self._redraw_pending = False
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.timeout.connect(self._flush_redraw)

        # scene records from the last paint pass (so tests and inspectors can query drawn texts and rectangles)
        self.drawn_texts: list[str] = []
        self.drawn_muted_rects: list[tuple[float, float, float, float]] = []
        self.drawn_thumb_count: int = 0
        self.drawn_hover_preview: bool = False

        # layout & child widgets
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)
        self.btn_out = QPushButton("\u2212")
        self.btn_out.clicked.connect(self.zoom_out)
        self.btn_in = QPushButton("+")
        self.btn_in.clicked.connect(self.zoom_in)
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.clicked.connect(self.zoom_fit)
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo)
        for b in (self.btn_out, self.btn_in, self.btn_fit):
            bar.addWidget(b)
        bar.addSpacing(4)
        bar.addWidget(self.btn_undo)

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

        self.hbar = QScrollBar(Qt.Orientation.Horizontal, self)
        self.hbar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hbar.setRange(0, 0)
        self.hbar.valueChanged.connect(self._on_hbar_value)
        outer.addWidget(self.hbar)

        self.hint_label = WrapLabel(IDLE_HINT, self)
        self.hint_label.setProperty("role", "muted")
        self.hint_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        outer.addWidget(self.hint_label)

        for seq in ("Ctrl+Z", "Meta+Z"):
            sc = QShortcut(QKeySequence(seq), self.canvas)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self.undo)

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
        self.set_muted(None, redraw=False)
        self._history.clear()
        self._pixmaps.clear()
        self._preview_pixmaps.clear()
        self._drag = self._pan = None
        self._hover_pos = None
        self.vp = Viewport(self.duration or 1.0, self._draw_width())
        self._rebuild_snap_points()
        self._sync_buttons()
        self.hint_label.setText(IDLE_HINT)
        self.invalidate()

    def set_frames(self, frames: list | None) -> None:
        self.frames = frames
        self.frames_state = "ready" if frames and any(f is not None for f in frames) else "failed"
        self._pixmaps.clear()
        self._preview_pixmaps.clear()
        self.invalidate()

    def set_ranges(self, ranges: list[Range] | None) -> None:
        """The parts as the cut text describes them now (None = the text is invalid)."""
        new = None if ranges is None else [(s, e) for s, e in ranges]
        if new == self.ranges:
            return
        self.ranges = new
        self.invalidate()

    def set_clip_marks(self, times: Sequence[float]) -> None:
        self.clip_marks = sorted(float(t) for t in times)
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
        self.ranges = self._history.pop()
        self._sync_buttons()
        self.invalidate()
        self.on_edit(list(self.ranges))

    def _push_history(self) -> None:
        if self.ranges is not None:
            self._history.append(list(self.ranges))
            del self._history[:-100]
            self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.btn_undo.setEnabled(bool(self._history))

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
            return
        t = self.t_at(x)
        if zone == "thumbs":
            self._cut_at(t)
        elif zone == "parts":
            new = toggle_part(self.ranges, t, self.duration)
            if new is None:
                self._say("At least one part has to stay.")
                return
            self._push_history()
            self._apply(new)

    def _cut_at(self, t: float) -> None:
        assert self.ranges is not None
        t = self._snap(t)
        new = add_cut(self.ranges, t)
        if new is None:
            if part_index_at(self.ranges, t) is None:
                self._say("That section is skipped: click it in the parts row to keep it again.")
            else:
                self._say("There is already a cut line there.")
            return
        self._push_history()
        self._apply(new)
        # the new line follows the mouse while the button is down
        self._drag = next((e for e in edges_of(new) if e.kind == "cut" and e.t == t), None)

    def _on_double(self, x: float, y: float, shift: bool = False) -> None:
        if not self._ready() or zone_at(y) != "games":
            self._on_press(x, y, shift=shift)
            return
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        seg = self._segment_at(self.t_at(x))
        if seg is None:
            return
        new = isolate_span(self.ranges, seg.start, seg.end, self.duration, only=shift)
        if new != self.ranges:
            self._push_history()
            self._apply(new)

    def _on_motion(self, x: float, y: float) -> None:
        if self._pan is not None:
            x0, start0 = self._pan
            self.vp.pan_to(start0 - (x - x0) / self.vp.px_per_sec)
            self.invalidate()
        elif self._drag is not None and self.ranges is not None:
            t = self._snap(self.t_at(x))
            new = move_edge(self.ranges, self._drag, t, self.duration)
            if new != self.ranges:
                moved = next((e for e in edges_of(new) if e.kind == self._drag.kind and e.index == self._drag.index), None)
                self._apply(new)
                if moved is not None:
                    self._drag = moved
            self._hover_pos = (x, y, True)
            self.invalidate()

    def _on_release(self) -> None:
        self._drag = None
        self._pan = None
        self._hover_pos = None
        self.invalidate()

    def _on_right(self, x: float, y: float) -> None:
        if not self._ready() or self.ranges is None or zone_at(y) == "ruler":
            return
        edge = self._edge_at(x)
        if edge is None:
            return
        if edge.kind != "cut":
            self._say("Only a cut line between two parts can be removed (click the part to skip it instead).")
            return
        self._push_history()
        self._apply(remove_cut(self.ranges, edge.index))

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

    # ------------------------------------------------------------------ hover
    def _on_hover(self, x: float, y: float) -> None:
        if not self._ready() or self._drag is not None or self._pan is not None:
            return
        zone = zone_at(y)
        t = self.t_at(x)
        edge = self._edge_at(x) if zone != "ruler" else None
        seg = self._segment_at(t)
        where = f"{fmt_hms(max(0, min(t, self.duration)))}" + (f"  \u00b7  {seg.title}" if seg and seg.title else "")
        mu = self._muted_at(t)
        if mu is not None:
            where += f"  \u00b7  muted by Twitch ({fmt_hms(mu[0])} \u2192 {fmt_hms(mu[1])})"
        if edge is not None:
            what = "drag to move" + (", right-click to remove" if edge.kind == "cut" else "")
            cursor = Qt.CursorShape.SizeHorCursor
        elif zone == "ruler":
            what, cursor = "drag to move along the VOD", Qt.CursorShape.SizeAllCursor
        elif zone == "games":
            what, cursor = "double-click: make this game its own part (Shift: only this game)", Qt.CursorShape.ArrowCursor
        elif zone == "thumbs":
            what, cursor = "click to cut here", Qt.CursorShape.CrossCursor
        else:
            kept = self.ranges is not None and part_index_at(self.ranges, t) is not None
            what, cursor = ("click to skip this part" if kept else "click to keep this section"), Qt.CursorShape.PointingHandCursor
        self.canvas.setCursor(cursor)
        self._say(f"{where}  \u00b7  {what}")
        self._hover_pos = (x, y, False)
        self.invalidate()

    def _on_leave(self) -> None:
        self._hover_pos = None
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
        if hasattr(self, "_redraw_timer"):
            self._redraw_timer.stop()
        super().closeEvent(event)

    def redraw(self) -> None:
        """Force an immediate synchronous paint/state update (useful in tests)."""
        self._redraw_pending = False
        self.vp.width = self._draw_width()
        if self.duration:
            self.vp.clamp()
        self._update_scrollbar()
        self.canvas.repaint()

    def _x_range(self, start: float, end: float) -> tuple[float, float] | None:
        """Pixel span of ``[start, end]``, clipped to the drawing area; None if it is not visible."""
        x0 = max(self.x_of(start), PADX)
        x1 = min(self.x_of(end), PADX + self.vp.width)
        return (x0, x1) if x1 > x0 else None

    def _paint_canvas(self, widget: QWidget) -> None:
        self.drawn_texts.clear()
        self.drawn_muted_rects.clear()
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
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(OK))
        for ct in self.clip_marks:
            x = self.x_of(ct)
            if PADX <= x <= PADX + vp.width:
                p.drawPolygon(QPolygonF([QPointF(x - 4, Y_RULER), QPointF(x + 4, Y_RULER), QPointF(x, Y_RULER + 6)]))

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
        for g in self.segments:
            span = self._x_range(g.start, g.end)
            if span is None:
                continue
            x0, x1 = span
            rect = QRectF(x0, Y_GAMES, x1 - x0, GAMES_H)
            p.fillRect(rect, QColor(game_colour(g.title)))
            p.setPen(bg_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)
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
        p.fillRect(QRectF(PADX, Y_THUMBS, vp.width, THUMB_H), QColor(BG2))
        sb = self.storyboard
        if self.frames_state != "ready" or sb is None or Image is None:
            msg = {"loading": "Loading thumbnails\u2026", "failed": "Thumbnails are not available",
                   "none": "This VOD has no preview thumbnails"}.get(self.frames_state, "")
            if sb is not None and Image is None:
                msg = "Thumbnails need Pillow (pip install pillow)"
            self._draw_text(
                p, QRectF(PADX, Y_THUMBS, vp.width, THUMB_H),
                msg, MUTED, 9, Qt.AlignmentFlag.AlignCenter,
            )
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

    def _draw_parts(self, p: QPainter) -> None:
        vp = self.vp
        p.fillRect(QRectF(PADX, Y_PARTS, vp.width, PARTS_H), QColor(BG2))
        if self.ranges is None:
            self._draw_text(
                p, QRectF(PADX, Y_PARTS, vp.width, PARTS_H),
                "The cut points text has an error: fix it to edit here.", ERR, 9, Qt.AlignmentFlag.AlignCenter,
            )
            return
        if not self.ranges:
            self._draw_text(
                p, QRectF(PADX, Y_PARTS, vp.width, PARTS_H),
                "No parts yet: click here to start with the whole VOD.", MUTED, 9, Qt.AlignmentFlag.AlignCenter,
            )
        bg_pen = QPen(QColor(BG), 1)
        accent_col = QColor(ACCENT)
        for n, (s, e) in enumerate(self.ranges, 1):
            span = self._x_range(s, e)
            if span is None:
                continue
            x0, x1 = span
            rect = QRectF(x0, Y_PARTS, x1 - x0, PARTS_H)
            p.fillRect(rect, accent_col)
            p.setPen(bg_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)
            label = f"Part {n} \u00b7 {fmt_hms(e - s)}"
            if x1 - x0 >= len(label) * 6.5 + 10:
                self._draw_text(p, rect, label, WHITE, 9, Qt.AlignmentFlag.AlignCenter)
            elif x1 - x0 >= 30:
                self._draw_text(p, rect, str(n), WHITE, 9, Qt.AlignmentFlag.AlignCenter)
        for edge in edges_of(self.ranges):
            x = self.x_of(edge.t)
            if not (PADX - 1 <= x <= PADX + vp.width + 1):
                continue
            grabbed = self._drag is not None and (edge.kind, edge.index) == (self._drag.kind, self._drag.index)
            colour = QColor(OK if grabbed else (CUT_COLOUR if edge.kind == "cut" else EDGE_COLOUR))
            p.setPen(QPen(colour, 2))
            p.drawLine(QPointF(x, Y_GAMES), QPointF(x, Y_PARTS + PARTS_H))
            handle = QRectF(x - 3, Y_PARTS + 5, 6, PARTS_H - 10)
            p.fillRect(handle, colour)
            p.setPen(bg_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(handle)

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
