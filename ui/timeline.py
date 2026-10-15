"""
Timeline: the whole VOD on one strip, to see where the games change and to place the cuts with the mouse.

Rows, top to bottom:
    ruler    time marks (green triangles = clips). Drag to move along the VOD.
    games    one bar per game / category the streamer was in. Double-click one to make it its own part
             (Shift + double-click: keep only that game).
    thumbs   preview frames of the VOD. Click to cut there, drag a cut line to move it.
    parts    the parts that will be downloaded (purple); skipped sections are dark. Click a part to skip
             it, click a skipped section to bring it back.
Right-click a cut line (between two touching parts) to remove it. Mouse wheel = zoom, Shift + wheel or the
scroll bar = move. "Undo" (or Ctrl+Z) takes back the last timeline edit.

The widget knows nothing about the rest of the app. The owner feeds it with set_source() / set_frames() /
set_ranges() / set_clip_marks() and gets every edit back through `on_edit(ranges)`; the cut text is
rebuilt from those ranges by the engine (see "Editing the parts" in luckytwitch_engine.py).
"""

from __future__ import annotations

import math
import sys
import tkinter as tk
import zlib
from tkinter import ttk
from typing import Callable, Sequence

from luckytwitch_engine import (
    Edge,
    GameSegment,
    Range,
    Storyboard,
    add_cut,
    edges_of,
    fmt_hms,
    isolate_span,
    move_edge,
    nearest_edge,
    part_index_at,
    remove_cut,
    toggle_part,
)
from ui.common import ACCENT, BG, BG2, BG3, ERR, FG, MUTED, OK, UI_FONT

try:  # thumbnails need Pillow; everything else works without it
    from PIL import Image, ImageEnhance, ImageTk
except ImportError:  # pragma: no cover - exercised through the "no Pillow" test by patching these names
    Image = ImageEnhance = ImageTk = None

# --- geometry (pixels) --- #
THUMB_W, THUMB_H = 100, 56
PADX = 8  # room left and right so the first / last cut line is not clipped
RULER_H, GAMES_H, PARTS_H, GAP = 20, 22, 26, 3
Y_RULER = 0
Y_GAMES = Y_RULER + RULER_H + GAP
Y_THUMBS = Y_GAMES + GAMES_H + GAP
Y_PARTS = Y_THUMBS + THUMB_H + GAP
HEIGHT = Y_PARTS + PARTS_H + 4
EDGE_TOL_PX = 6  # how close to a cut line the mouse has to be to grab it
SNAP_PX = 6  # cuts snap to game changes and clips this close
PREVIEW_MAX_W = 160

GAME_COLOURS = ["#3b5b8c", "#8c3b6e", "#3b8c6a", "#8c6a3b", "#6a3b8c", "#3b7f8c", "#8c4a3b", "#5d8c3b"]
CUT_COLOUR = "#ffffff"
EDGE_COLOUR = "#d2b8ff"
IDLE_HINT = ("Click the thumbnails to cut · click a part to skip it · drag a cut line to move it · "
             "right-click a cut line to remove it · wheel = zoom")

_TIME_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600]


# --------------------------------------------------------------------------- pure helpers (no Tk)
class Viewport:
    """Which stretch of the VOD is visible and how it maps to pixels (x = 0 is the left end of the drawing area)."""

    def __init__(self, duration: float = 1.0, width: int = 1):
        self.duration = max(float(duration), 1.0)
        self.width = max(int(width), 1)
        self.start = 0.0
        self.span = self.duration

    @property
    def min_span(self) -> float:
        return min(30.0, self.duration)

    @property
    def px_per_sec(self) -> float:
        return self.width / self.span

    @property
    def zoomed(self) -> bool:
        return self.span < self.duration - 1e-6

    def t2x(self, t: float) -> float:
        return (t - self.start) * self.px_per_sec

    def x2t(self, x: float) -> float:
        return self.start + x / self.px_per_sec

    def clamp(self) -> None:
        self.span = min(max(self.span, self.min_span), self.duration)
        self.start = min(max(self.start, 0.0), self.duration - self.span)

    def zoom(self, factor: float, anchor_x: float) -> None:
        """factor > 1 zooms in, < 1 zooms out; the moment under `anchor_x` stays under it."""
        anchor_t = self.x2t(anchor_x)
        frac = min(max(anchor_x / self.width, 0.0), 1.0)
        self.span = min(max(self.span / factor, self.min_span), self.duration)
        self.start = anchor_t - frac * self.span
        self.clamp()

    def pan_to(self, start: float) -> None:
        self.start = start
        self.clamp()

    def fit(self) -> None:
        self.start, self.span = 0.0, self.duration


def nice_step(px_per_sec: float, min_px: float = 80.0) -> int:
    """Smallest "round" time step (seconds) whose marks are at least `min_px` apart."""
    return next((s for s in _TIME_STEPS if s * px_per_sec >= min_px), _TIME_STEPS[-1])


def game_colour(title: str) -> str:
    """Same game, same colour, in every VOD and every run (crc32, not Python's randomised hash)."""
    return GAME_COLOURS[zlib.crc32(title.strip().lower().encode("utf-8")) % len(GAME_COLOURS)]


def zone_at(y: float) -> str:
    if y < Y_GAMES:
        return "ruler"
    if y < Y_THUMBS:
        return "games"
    if y < Y_PARTS:
        return "thumbs"
    return "parts"


# --------------------------------------------------------------------------- the widget
class Timeline(ttk.Frame):
    def __init__(self, master, on_edit: Callable[[list[Range]], None] | None = None):
        super().__init__(master)
        self.on_edit = on_edit or (lambda ranges: None)

        # model
        self.duration: float = 0.0
        self.segments: list[GameSegment] = []
        self.storyboard: Storyboard | None = None
        self.frames: list | None = None  # PIL images (None entries = unavailable); None = not loaded yet
        self.frames_state = "none"  # none | loading | ready | failed
        self.ranges: list[Range] | None = None  # None = the cut text is invalid
        self.clip_marks: list[float] = []
        self.vp = Viewport()
        self._history: list[list[Range]] = []
        self._drag: Edge | None = None
        self._pan: tuple[int, float] | None = None
        self._photos: dict[tuple[int, bool], object] = {}
        self._preview_photos: dict[int, object] = {}
        self._redraw_job: str | None = None
        self._snap_points: list[float] = []

        # widgets
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 4))
        self.btn_out = ttk.Button(bar, text="−", width=3, command=self.zoom_out)
        self.btn_in = ttk.Button(bar, text="+", width=3, command=self.zoom_in)
        self.btn_fit = ttk.Button(bar, text="Fit", width=4, command=self.zoom_fit)
        self.btn_undo = ttk.Button(bar, text="Undo", width=6, command=self.undo, state="disabled")
        for b in (self.btn_out, self.btn_in, self.btn_fit):
            b.pack(side="left", padx=(0, 4))
        self.btn_undo.pack(side="left", padx=(8, 0))
        self.hint = tk.StringVar(value=IDLE_HINT)

        self.canvas = tk.Canvas(self, height=HEIGHT, bg=BG, highlightthickness=0, borderwidth=0, takefocus=1)
        self.canvas.pack(fill="x")
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self._hscroll)
        self.hbar.pack(fill="x", pady=(2, 0))
        # the hint gets a line of its own under the strip: next to the buttons it would be cut off
        hint_lbl = ttk.Label(self, textvariable=self.hint, style="Muted.TLabel", justify="left")
        hint_lbl.pack(fill="x", pady=(4, 0))
        # the hint wraps to the width of the strip (at the minimum window width it is longer than one line)
        self.bind("<Configure>", lambda e: hint_lbl.configure(wraplength=max(200, e.width - 4)) if e.widget is self else None,
                  add="+")

        c = self.canvas
        c.bind("<Configure>", lambda e: self.invalidate())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<Triple-Button-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Motion>", self._hover)
        c.bind("<Leave>", self._leave)
        c.bind("<ButtonPress-3>", self._right)
        if sys.platform == "darwin":  # the secondary button is 2 there, and Ctrl+click is the usual alternative
            c.bind("<ButtonPress-2>", self._right)
            c.bind("<Control-ButtonPress-1>", self._right)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            c.bind(seq, self._wheel)
        for seq in ("<Control-z>", "<Command-z>"):
            c.bind(seq, lambda e: self.undo())

    # ------------------------------------------------------------------ feeding the widget
    def set_source(self, duration: float, segments: Sequence[GameSegment] = (), storyboard: Storyboard | None = None):
        """A new VOD: forget everything about the previous one."""
        self.duration = float(duration or 0)
        self.segments = list(segments)
        self.storyboard = storyboard
        self.frames = None
        self.frames_state = "loading" if storyboard else "none"
        self.ranges = None
        self.clip_marks = []
        self._history.clear()
        self._photos.clear()
        self._preview_photos.clear()
        self._drag = self._pan = None
        self.vp = Viewport(self.duration or 1.0, self._draw_width())
        self._rebuild_snap_points()
        self._sync_buttons()
        self.hint.set(IDLE_HINT)
        self.invalidate()

    def set_frames(self, frames: list | None) -> None:
        self.frames = frames
        self.frames_state = "ready" if frames and any(f is not None for f in frames) else "failed"
        self._photos.clear()
        self._preview_photos.clear()
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

    def _rebuild_snap_points(self) -> None:
        pts = {0.0, self.duration}
        for g in self.segments:
            pts.update((g.start, g.end))
        pts.update(self.clip_marks)
        self._snap_points = sorted(pts)

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

    def _hscroll(self, *args) -> None:
        if not self.duration:
            return
        if args[0] == "moveto":
            self.vp.pan_to(float(args[1]) * self.vp.duration)
        elif args[0] == "scroll":
            n, what = int(args[1]), args[2]
            self.vp.pan_to(self.vp.start + n * self.vp.span * (0.9 if what == "pages" else 0.1))
        self.invalidate()

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
        self.btn_undo.config(state="normal" if self._history else "disabled")

    # ------------------------------------------------------------------ coordinates
    def _draw_width(self) -> int:
        w = self.canvas.winfo_width()
        if w <= 50:  # not laid out yet (or a test): fall back to the requested width
            w = self.canvas.winfo_reqwidth()  # (cget("width") may be "10c", a Tk distance, not a number)
        return max(w - 2 * PADX, 1)

    def x_of(self, t: float) -> float:
        """Canvas x of the moment `t`."""
        return PADX + self.vp.t2x(t)

    def t_at(self, x: float) -> float:
        return self.vp.x2t(x - PADX)

    @staticmethod
    def y_of(zone: str) -> int:
        """A y that lies inside the given row (useful for tests)."""
        return {"ruler": Y_RULER + RULER_H // 2, "games": Y_GAMES + GAMES_H // 2,
                "thumbs": Y_THUMBS + THUMB_H // 2, "parts": Y_PARTS + PARTS_H // 2}[zone]

    def _snap(self, t: float) -> int:
        tol = SNAP_PX / self.vp.px_per_sec
        best = min(self._snap_points, key=lambda p: abs(p - t), default=None)
        if best is not None and abs(best - t) <= tol:
            return round(best)
        return round(t)

    def _segment_at(self, t: float) -> GameSegment | None:
        return next((g for g in self.segments if g.start <= t < g.end), None)

    def _edge_at(self, x: float) -> Edge | None:
        if not self.ranges:
            return None
        return nearest_edge(self.ranges, self.t_at(x), EDGE_TOL_PX / self.vp.px_per_sec)

    # ------------------------------------------------------------------ mouse
    def _ready(self) -> bool:
        return bool(self.duration)

    def _say(self, text: str) -> None:
        self.hint.set(text)

    def _press(self, event) -> None:
        self.canvas.focus_set()
        if not self._ready():
            return
        zone = zone_at(event.y)
        if zone == "ruler":
            self._pan = (event.x, self.vp.start)
            return
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        edge = self._edge_at(event.x)
        if edge is not None:
            self._push_history()
            self._drag = edge
            return
        t = self.t_at(event.x)
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

    def _double(self, event) -> None:
        if not self._ready() or zone_at(event.y) != "games":
            self._press(event)
            return
        if self.ranges is None:
            self._say("The cut points text has an error: fix it to edit here.")
            return
        seg = self._segment_at(self.t_at(event.x))
        if seg is None:
            return
        new = isolate_span(self.ranges, seg.start, seg.end, self.duration, only=bool(event.state & 0x1))
        if new != self.ranges:
            self._push_history()
            self._apply(new)

    def _motion(self, event) -> None:
        if self._pan is not None:
            x0, start0 = self._pan
            self.vp.pan_to(start0 - (event.x - x0) / self.vp.px_per_sec)
            self.invalidate()
        elif self._drag is not None and self.ranges is not None:
            t = self._snap(self.t_at(event.x))
            new = move_edge(self.ranges, self._drag, t, self.duration)
            if new != self.ranges:
                moved = next((e for e in edges_of(new) if e.kind == self._drag.kind and e.index == self._drag.index), None)
                self._apply(new)
                if moved is not None:
                    self._drag = moved
            self._hover_overlay(event.x, event.y, dragging=True)

    def _release(self, _event) -> None:
        self._drag = None
        self._pan = None
        self.invalidate()

    def _right(self, event) -> None:
        if not self._ready() or self.ranges is None or zone_at(event.y) == "ruler":
            return
        edge = self._edge_at(event.x)
        if edge is None:
            return
        if edge.kind != "cut":
            self._say("Only a cut line between two parts can be removed (click the part to skip it instead).")
            return
        self._push_history()
        self._apply(remove_cut(self.ranges, edge.index))

    def _wheel(self, event):
        if not self._ready():
            return "break"
        if getattr(event, "num", None) == 4:
            direction = 1
        elif getattr(event, "num", None) == 5:
            direction = -1
        else:
            direction = 1 if event.delta > 0 else -1
        if event.state & 0x1:  # Shift: move along the VOD
            self.vp.pan_to(self.vp.start - direction * self.vp.span * 0.15)
            self.invalidate()
        else:
            self._zoom(1.25 if direction > 0 else 1 / 1.25, event.x - PADX)
        return "break"  # keep the page behind from scrolling

    def _apply(self, ranges: list[Range]) -> None:
        self.ranges = ranges
        self.invalidate()
        self.on_edit(list(ranges))

    # ------------------------------------------------------------------ hover
    def _hover(self, event) -> None:
        if not self._ready() or self._drag is not None or self._pan is not None:
            return
        zone = zone_at(event.y)
        t = self.t_at(event.x)
        edge = self._edge_at(event.x) if zone != "ruler" else None
        seg = self._segment_at(t)
        where = f"{fmt_hms(max(0, min(t, self.duration)))}" + (f"  ·  {seg.title}" if seg and seg.title else "")
        if edge is not None:
            what = "drag to move" + (", right-click to remove" if edge.kind == "cut" else "")
            cursor = "sb_h_double_arrow"
        elif zone == "ruler":
            what, cursor = "drag to move along the VOD", "fleur"
        elif zone == "games":
            what, cursor = "double-click: make this game its own part (Shift: only this game)", "arrow"
        elif zone == "thumbs":
            what, cursor = "click to cut here", "crosshair"
        else:
            kept = self.ranges is not None and part_index_at(self.ranges, t) is not None
            what, cursor = ("click to skip this part" if kept else "click to keep this section"), "hand2"
        self.canvas.config(cursor=cursor)
        self._say(f"{where}  ·  {what}")
        self._hover_overlay(event.x, event.y)

    def _leave(self, _event) -> None:
        self.canvas.delete("hover")
        self.canvas.config(cursor="")
        if self._drag is None:
            self.hint.set(IDLE_HINT)

    def _hover_overlay(self, x: int, y: int, dragging: bool = False) -> None:
        c = self.canvas
        c.delete("hover")
        if not self.duration or not (PADX <= x <= PADX + self.vp.width):
            return
        t = max(0.0, min(self.t_at(x), self.duration))
        c.create_line(x, 0, x, HEIGHT, fill=MUTED, dash=(2, 3), tags="hover")
        label = fmt_hms(t)
        tx = min(max(x, PADX + 26), PADX + self.vp.width - 26)
        c.create_rectangle(tx - 26, 2, tx + 26, RULER_H - 3, fill=BG3, outline="", tags="hover")
        c.create_text(tx, RULER_H // 2, text=label, fill=FG, font=(UI_FONT, 9), tags="hover")
        if dragging or self.frames_state != "ready" or ImageTk is None or self.storyboard is None:
            return
        idx = self.storyboard.frame_index_at(t)
        photo = self._preview_photo(idx)
        if photo is None:
            return
        w, h = photo.width(), photo.height()
        left = x + 14 if x + 14 + w < PADX + self.vp.width else x - 14 - w
        top = Y_GAMES
        c.create_rectangle(left - 2, top - 2, left + w + 2, top + h + 2, fill=BG, outline=FG, tags="hover")
        c.create_image(left, top, image=photo, anchor="nw", tags="hover")

    # ------------------------------------------------------------------ images
    def _frame_image(self, idx: int):
        if not self.frames or not (0 <= idx < len(self.frames)):
            return None
        return self.frames[idx]

    def _photo(self, idx: int, dim: bool):
        key = (idx, dim)
        if key not in self._photos:
            im = self._frame_image(idx)
            if im is None or ImageTk is None:
                return None
            im = im.resize((THUMB_W, THUMB_H))
            if dim:
                im = ImageEnhance.Brightness(im).enhance(0.35)
            self._photos[key] = ImageTk.PhotoImage(im, master=self.canvas)
        return self._photos[key]

    def _preview_photo(self, idx: int):
        if idx not in self._preview_photos:
            im = self._frame_image(idx)
            if im is None or ImageTk is None:
                return None
            if im.width > PREVIEW_MAX_W:
                im = im.resize((PREVIEW_MAX_W, round(im.height * PREVIEW_MAX_W / im.width)))
            self._preview_photos[idx] = ImageTk.PhotoImage(im, master=self.canvas)
        return self._preview_photos[idx]

    # ------------------------------------------------------------------ drawing
    def invalidate(self) -> None:
        """Redraw soon (several requests in a row cost one redraw).

        The job is scheduled on the top-level window, not on this widget: a window that cancels all its pending
        jobs (as the tests and the app's shutdown do) then cannot trip over a job it does not own."""
        if self._redraw_job is None:
            self._redraw_job = self.winfo_toplevel().after_idle(self._redraw_job_fired)

    def _redraw_job_fired(self) -> None:
        self._redraw_job = None
        if self.winfo_exists():
            self.redraw()

    def redraw(self) -> None:
        if self._redraw_job is not None:
            try:
                self.winfo_toplevel().after_cancel(self._redraw_job)
            except tk.TclError:
                pass
            self._redraw_job = None
        c = self.canvas
        c.delete("all")
        if not self.duration:
            c.create_text(c.winfo_width() // 2 or 200, HEIGHT // 2, fill=MUTED, font=(UI_FONT, 10),
                          text="Press «Get info» to see the VOD here.")
            self._update_scrollbar()
            return
        self.vp.width = self._draw_width()
        self.vp.clamp()
        self._draw_ruler()
        self._draw_games()
        self._draw_thumbs()
        self._draw_parts()
        self._update_scrollbar()

    def _update_scrollbar(self) -> None:
        if self.duration:
            self.hbar.set(self.vp.start / self.vp.duration, (self.vp.start + self.vp.span) / self.vp.duration)
        else:
            self.hbar.set(0, 1)

    def _x_range(self, start: float, end: float) -> tuple[float, float] | None:
        """Pixel span of [start, end], clipped to the drawing area; None if it is not visible."""
        x0 = max(self.x_of(start), PADX)
        x1 = min(self.x_of(end), PADX + self.vp.width)
        return (x0, x1) if x1 > x0 else None

    def _draw_ruler(self) -> None:
        c, vp = self.canvas, self.vp
        step = nice_step(vp.px_per_sec)
        t = math.floor(vp.start / step) * step
        base = Y_RULER + RULER_H
        while t <= vp.start + vp.span + step:
            x = self.x_of(t)
            if PADX - 1 <= x <= PADX + vp.width + 1:
                c.create_line(x, base - 5, x, base, fill=MUTED)
                c.create_text(x + 3, base - 10, text=fmt_hms(t), fill=MUTED, anchor="w", font=(UI_FONT, 8))
            t += step
        for ct in self.clip_marks:
            x = self.x_of(ct)
            if PADX <= x <= PADX + vp.width:
                c.create_polygon(x - 4, Y_RULER, x + 4, Y_RULER, x, Y_RULER + 6, fill=OK, outline="")

    def _draw_games(self) -> None:
        c = self.canvas
        if not self.segments:
            c.create_rectangle(PADX, Y_GAMES, PADX + self.vp.width, Y_GAMES + GAMES_H, fill=BG2, outline="")
            c.create_text(PADX + 6, Y_GAMES + GAMES_H // 2, anchor="w", fill=MUTED, font=(UI_FONT, 9),
                          text="No game information for this VOD")
            return
        for g in self.segments:
            span = self._x_range(g.start, g.end)
            if span is None:
                continue
            x0, x1 = span
            c.create_rectangle(x0, Y_GAMES, x1, Y_GAMES + GAMES_H, fill=game_colour(g.title), outline=BG)
            room = int((x1 - x0 - 8) / 6.3)
            if room >= 3 and g.title:
                text = g.title if len(g.title) <= room else g.title[: room - 1] + "…"
                c.create_text(x0 + 4, Y_GAMES + GAMES_H // 2, text=text, anchor="w", fill="#ffffff", font=(UI_FONT, 9))

    def _draw_thumbs(self) -> None:
        c, vp = self.canvas, self.vp
        c.create_rectangle(PADX, Y_THUMBS, PADX + vp.width, Y_THUMBS + THUMB_H, fill=BG2, outline="")
        sb = self.storyboard
        if self.frames_state != "ready" or sb is None or ImageTk is None:
            msg = {"loading": "Loading thumbnails…", "failed": "Thumbnails are not available",
                   "none": "This VOD has no preview thumbnails"}.get(self.frames_state, "")
            if sb is not None and ImageTk is None:
                msg = "Thumbnails need Pillow (pip install pillow)"
            c.create_text(PADX + vp.width // 2, Y_THUMBS + THUMB_H // 2, text=msg, fill=MUTED, font=(UI_FONT, 9))
            return
        per_frame = vp.px_per_sec * sb.interval  # pixels one frame covers
        step = max(1, math.ceil(THUMB_W / per_frame))  # show every `step`-th frame so they do not overlap
        first = max(0, int(vp.start / sb.interval) // step * step - step)
        for i in range(first, sb.count, step):
            x = self.x_of(sb.frame_time(i))
            if x > PADX + vp.width:
                break
            if x + THUMB_W < PADX:
                continue
            kept = self.ranges is None or part_index_at(self.ranges, sb.frame_time(i)) is not None
            photo = self._photo(i, dim=not kept)
            if photo is None:
                continue
            # clip the picture to the drawing area by drawing the margins over it afterwards
            c.create_image(x, Y_THUMBS, image=photo, anchor="nw")
        c.create_rectangle(0, Y_THUMBS, PADX, Y_THUMBS + THUMB_H, fill=BG, outline="")
        c.create_rectangle(PADX + vp.width, Y_THUMBS, PADX + vp.width + PADX + THUMB_W, Y_THUMBS + THUMB_H, fill=BG, outline="")

    def _draw_parts(self) -> None:
        c, vp = self.canvas, self.vp
        c.create_rectangle(PADX, Y_PARTS, PADX + vp.width, Y_PARTS + PARTS_H, fill=BG2, outline="")
        if self.ranges is None:
            c.create_text(PADX + vp.width // 2, Y_PARTS + PARTS_H // 2, fill=ERR, font=(UI_FONT, 9),
                          text="The cut points text has an error: fix it to edit here.")
            return
        if not self.ranges:
            c.create_text(PADX + vp.width // 2, Y_PARTS + PARTS_H // 2, fill=MUTED, font=(UI_FONT, 9),
                          text="No parts yet: click here to start with the whole VOD.")
        for n, (s, e) in enumerate(self.ranges, 1):
            span = self._x_range(s, e)
            if span is None:
                continue
            x0, x1 = span
            c.create_rectangle(x0, Y_PARTS, x1, Y_PARTS + PARTS_H, fill=ACCENT, outline=BG)
            label = f"Part {n} · {fmt_hms(e - s)}"
            if x1 - x0 >= len(label) * 6.5 + 10:
                c.create_text((x0 + x1) / 2, Y_PARTS + PARTS_H // 2, text=label, fill="#ffffff", font=(UI_FONT, 9))
            elif x1 - x0 >= 30:
                c.create_text((x0 + x1) / 2, Y_PARTS + PARTS_H // 2, text=str(n), fill="#ffffff", font=(UI_FONT, 9))
        for edge in edges_of(self.ranges):
            x = self.x_of(edge.t)
            if not (PADX - 1 <= x <= PADX + vp.width + 1):
                continue
            grabbed = self._drag is not None and (edge.kind, edge.index) == (self._drag.kind, self._drag.index)
            colour = OK if grabbed else (CUT_COLOUR if edge.kind == "cut" else EDGE_COLOUR)
            c.create_line(x, Y_GAMES, x, Y_PARTS + PARTS_H, fill=colour, width=2)
            c.create_rectangle(x - 3, Y_PARTS + 5, x + 3, Y_PARTS + PARTS_H - 5, fill=colour, outline=BG)
