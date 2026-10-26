"""Pure geometry, snapping and undo-history helpers for the Timeline (Phase 7, ``core/timeline.py``).

Copied from ``ui/timeline.py`` with no UI toolkit imports so both ``qt_ui/timeline.py`` and UI-free unit tests can use
them directly while ``ui/timeline.py`` stays untouched until cutover.
"""

from __future__ import annotations

import zlib
from typing import Iterable, Sequence

from luckytwitch_engine import GameSegment, Range

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
MUTED_COLOUR = "#ff4d4d"  # Twitch-silenced stretches (the plugin shows them red in Premiere too)
MUTED_H = 4  # height of the red line along the bottom of the games bar
IDLE_HINT = ("Click the thumbnails to cut \u00b7 click a part to skip it \u00b7 drag a cut line to move it \u00b7 "
             "right-click a cut line to remove it \u00b7 wheel = zoom")

_TIME_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600]


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
        """factor > 1 zooms in, < 1 zooms out; the moment under ``anchor_x`` stays under it."""
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
    """Smallest "round" time step (seconds) whose marks are at least ``min_px`` apart."""
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


def y_of(zone: str) -> int:
    """A y coordinate that lies inside the given row (``ruler``, ``games``, ``thumbs``, ``parts``)."""
    return {"ruler": Y_RULER + RULER_H // 2, "games": Y_GAMES + GAMES_H // 2,
            "thumbs": Y_THUMBS + THUMB_H // 2, "parts": Y_PARTS + PARTS_H // 2}[zone]


def build_snap_points(duration: float, segments: Iterable[GameSegment] = (),
                      clip_marks: Iterable[float] = (), muted: Iterable[Range] = (),
                      show_muted: bool = True) -> list[float]:
    """Sorted moments (seconds) that cuts and dragged edges snap to."""
    pts: set[float] = {0.0, float(duration)}
    for g in segments:
        pts.update((float(g.start), float(g.end)))
    pts.update(float(t) for t in clip_marks)
    if show_muted:
        for s, e in muted:
            pts.update((float(s), float(e)))
    return sorted(pts)


def snap_time(t: float, snap_points: Sequence[float], px_per_sec: float, snap_px: float = SNAP_PX) -> int:
    """Snap ``t`` to the closest point in ``snap_points`` if within ``snap_px`` pixels, rounded to a whole second."""
    tol = snap_px / px_per_sec
    best = min(snap_points, key=lambda p: abs(p - t), default=None)
    if best is not None and abs(best - t) <= tol:
        return round(best)
    return round(t)


# --- Phase 9f helpers: snap feedback, clip flags, game legend, skipped sections, minimap --- #
SNAP_GAME, SNAP_CLIP, SNAP_MUTED, SNAP_EDGE = "Game change", "Clip", "Muted edge", "VOD edge"


def build_snap_kinds(duration: float, segments: Iterable[GameSegment] = (),
                     clip_marks: Iterable[float] = (), muted: Iterable[Range] = (),
                     show_muted: bool = True) -> dict[float, str]:
    """What each snap point is (same points as ``build_snap_points``). Where two kinds meet the stronger one wins:
    VOD edge > game change > clip > muted edge."""
    kinds: dict[float, str] = {}
    if show_muted:
        for s, e in muted:
            kinds[float(s)] = kinds[float(e)] = SNAP_MUTED
    for t in clip_marks:
        kinds[float(t)] = SNAP_CLIP
    for g in segments:
        kinds[float(g.start)] = kinds[float(g.end)] = SNAP_GAME
    kinds[0.0] = kinds[float(duration)] = SNAP_EDGE
    return kinds


def snap_target(t: float, snap_points: Sequence[float], px_per_sec: float, snap_px: float = SNAP_PX) -> float | None:
    """The snap point ``snap_time`` would use for ``t`` (None when nothing is within ``snap_px`` pixels)."""
    tol = snap_px / px_per_sec
    best = min(snap_points, key=lambda p: abs(p - t), default=None)
    return best if best is not None and abs(best - t) <= tol else None


def cluster_marks(times: Sequence[float], px_per_sec: float, min_px: float = 9.0) -> list[tuple[float, int, float, float]]:
    """Group sorted moments that would sit closer than ``min_px`` pixels to the first of their group.
    Returns ``(centre_time, count, first_time, last_time)`` per group (count 1 = a lone flag)."""
    out: list[tuple[float, int, float, float]] = []
    group: list[float] = []
    for t in sorted(times):
        if group and (t - group[0]) * px_per_sec >= min_px:
            out.append((sum(group) / len(group), len(group), group[0], group[-1]))
            group = []
        group.append(t)
    if group:
        out.append((sum(group) / len(group), len(group), group[0], group[-1]))
    return out


def game_key(title: str) -> str:
    return title.strip().lower()


def game_totals(segments: Iterable[GameSegment]) -> list[tuple[str, float]]:
    """``(title, seconds)`` per game (a game seen twice is summed), longest first; segments without a title are left out."""
    names: dict[str, str] = {}
    totals: dict[str, float] = {}
    for g in segments:
        key = game_key(g.title or "")
        if not key:
            continue
        names.setdefault(key, g.title.strip())
        totals[key] = totals.get(key, 0.0) + max(0.0, float(g.end) - float(g.start))
    return sorted(((names[k], v) for k, v in totals.items()), key=lambda kv: -kv[1])


def gaps_of(ranges: Sequence[Range], duration: float) -> list[Range]:
    """The skipped sections: what lies between the parts (and before the first / after the last)."""
    out: list[Range] = []
    cursor = 0.0
    for s, e in sorted(ranges):
        if s > cursor + 1e-6:
            out.append((cursor, float(s)))
        cursor = max(cursor, float(e))
    if duration > cursor + 1e-6:
        out.append((cursor, float(duration)))
    return out


def minimap_lens(start: float, span: float, duration: float, width: float, pad: float = PADX,
                 min_w: float = 8.0) -> tuple[float, float]:
    """Left and right x of the lens that shows the visible window on a minimap ``width`` px wide."""
    inner = max(width - 2 * pad, 1.0)
    dur = max(duration, 1.0)
    x0 = pad + inner * (start / dur)
    x1 = pad + inner * ((start + span) / dur)
    if x1 - x0 < min_w:
        x1 = x0 + min_w
    return x0, min(x1, pad + inner)
