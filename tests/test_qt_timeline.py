"""The Qt Timeline widget (Phase 7, ``core/timeline.py`` and ``qt_ui/timeline.py``) on its own, and wired into the
Plan tab.

Ports of ``tests/test_gui_timeline.py`` (57 cases) and the 3 timeline GUI tests of ``tests/test_muted_audio.py``
(plus muted-stretch hover and snapping). Runs on Qt's offscreen platform without touching the network.
"""

from __future__ import annotations

import random
import zlib

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import luckytwitch_engine as eng  # noqa: E402
from core import timeline as core_tl  # noqa: E402
from core.settings import DEFAULTS  # noqa: E402
from luckytwitch_engine import GameSegment, Storyboard  # noqa: E402
from qt_ui import background_jobs, dialogs, theme  # noqa: E402
from qt_ui import main_window as mw  # noqa: E402
from qt_ui import timeline as tlm  # noqa: E402
from qt_ui.tabs import plan as plan_tab_module  # noqa: E402
from qt_ui.timeline import Timeline, Viewport, game_colour, nice_step, zone_at  # noqa: E402
from qt_ui.widgets import Card  # noqa: E402

SOURCE = dict(url="https://www.twitch.tv/videos/123", id="v123", title="Big Stream", uploader="Streamer",
              duration=7200.0, date="2026-10-01", twitch_vod_id="123")
DUR = 7200.0
SEGMENTS = [
    GameSegment(0, 3000, "Just Chatting"),
    GameSegment(3000, 5400, "Elden Ring"),
    GameSegment(5400, 7200, "Just Chatting"),
]
SB = Storyboard(urls=["a"], tile_w=160, tile_h=90, columns=5, rows=40, interval=DUR / 200, count=200)


def make_clips():
    return [
        {"id": "a", "vod_offset": 630.4, "view_count": 500, "duration": 30, "title": "Epic fail",
         "creator_name": "viewer1", "url": "https://clips.twitch.tv/a"},
        {"id": "b", "vod_offset": 3612, "view_count": 10, "duration": 12, "title": "Small one",
         "creator_name": "viewer2", "url": "https://clips.twitch.tv/b"},
        {"id": "c", "vod_offset": None, "view_count": 99, "duration": 20, "title": "No offset",
         "creator_name": "viewer3", "url": "https://clips.twitch.tv/c"},
    ]


def fake_frames(n: int = 200):
    from PIL import Image

    return [Image.new("RGB", (160, 90), ((i * 37) % 256, (i * 91) % 256, (i * 13) % 256)) for i in range(n)]


def send_mouse(canvas, event_type: QEvent.Type, x: float, y: float,
               button: Qt.MouseButton = Qt.MouseButton.LeftButton,
               buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
               modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    pt = QPointF(float(x), float(y))
    gpt = QPointF(canvas.mapToGlobal(QPoint(round(x), round(y))))
    ev = QMouseEvent(event_type, pt, gpt, button, buttons, modifiers)
    QApplication.sendEvent(canvas, ev)


def send_wheel(canvas, x: float, y: float, delta: int = 120,
               modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    pt = QPointF(float(x), float(y))
    gpt = QPointF(canvas.mapToGlobal(QPoint(round(x), round(y))))
    ev = QWheelEvent(pt, gpt, QPoint(0, 0), QPoint(0, delta), Qt.MouseButton.NoButton,
                     modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(canvas, ev)


class Rig:
    """A ``Timeline`` in its own window that records every edit it reports."""

    def __init__(self, qtbot):
        self.qtbot = qtbot
        self.edits: list[list] = []
        self.tl = Timeline(on_edit=lambda r: self.edits.append(list(r)))
        qtbot.addWidget(self.tl)
        self.tl.resize(900, 180)
        self.tl.show()
        qtbot.waitExposed(self.tl)

    def load(self, ranges=((0, 7200),), segments=SEGMENTS, storyboard=None):
        self.tl.set_source(DUR, segments, storyboard)
        self.tl.set_ranges(list(ranges) if ranges is not None else None)
        self.tl.redraw()

    def x(self, t: float) -> float:
        return self.tl.x_of(t)

    def click(self, t: float, zone: str = "thumbs", shift: bool = False) -> None:
        mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        x, y = self.x(t), Timeline.y_of(zone)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonPress, x, y,
                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonRelease, x, y,
                   Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, mods)

    def drag(self, t0: float, t1: float, zone: str = "parts") -> None:
        y = Timeline.y_of(zone)
        x0, x1 = self.x(t0), self.x(t1)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonPress, x0, y,
                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        send_mouse(self.tl.canvas, QEvent.Type.MouseMove, x1, y,
                   Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonRelease, x1, y,
                   Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)

    def right_click(self, t: float, zone: str = "parts") -> None:
        x, y = self.x(t), Timeline.y_of(zone)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonPress, x, y,
                   Qt.MouseButton.RightButton, Qt.MouseButton.RightButton)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonRelease, x, y,
                   Qt.MouseButton.RightButton, Qt.MouseButton.NoButton)

    def double_click(self, t: float, zone: str = "games", shift: bool = False) -> None:
        mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        x, y = self.x(t), Timeline.y_of(zone)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonDblClick, x, y,
                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)
        send_mouse(self.tl.canvas, QEvent.Type.MouseButtonRelease, x, y,
                   Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, mods)

    def hover(self, t: float, zone: str = "thumbs") -> None:
        x, y = self.x(t), Timeline.y_of(zone)
        send_mouse(self.tl.canvas, QEvent.Type.MouseMove, x, y,
                   Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)

    def leave(self) -> None:
        QApplication.sendEvent(self.tl.canvas, QEvent(QEvent.Type.Leave))

    def last(self):
        return self.edits[-1] if self.edits else None


@pytest.fixture()
def themed(qtbot):
    app = QApplication.instance()
    saved = (app.palette(), app.font(), app.styleSheet())
    theme.apply_theme(app)
    yield app
    app.setStyleSheet(saved[2])
    app.setPalette(saved[0])
    app.setFont(saved[1])


@pytest.fixture()
def rig(qtbot, themed):
    return Rig(qtbot)


@pytest.fixture()
def win(qtbot, themed, monkeypatch):
    calls: list = []
    for name in ("info", "warning", "error"):
        monkeypatch.setattr(dialogs, name, lambda parent, title, text, _n=name: calls.append((_n, title, text)))
    w = mw.MainWindow(settings=dict(DEFAULTS), client=None)
    w._boxes = calls
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


# --------------------------------------------------------------------------- 7a: pure helpers
def test_viewport_maps_time_to_pixels_and_back():
    vp = Viewport(1000, 500)
    assert vp.px_per_sec == 0.5 and vp.t2x(100) == 50 and vp.x2t(50) == 100
    vp.start, vp.span = 200, 100
    assert vp.t2x(200) == 0 and vp.t2x(300) == 500 and vp.x2t(250) == 250


def test_zoom_keeps_the_moment_under_the_mouse_in_place():
    vp = Viewport(10_000, 1000)
    t = vp.x2t(300)
    vp.zoom(4, 300)
    assert vp.span == 2500 and vp.x2t(300) == pytest.approx(t)
    vp.zoom(2, 900)
    assert vp.x2t(900) == pytest.approx(vp.start + 0.9 * vp.span)


def test_zoom_is_limited_to_the_whole_vod_and_to_30_seconds():
    vp = Viewport(10_000, 1000)
    vp.zoom(0.1, 500)
    assert (vp.start, vp.span) == (0, 10_000)
    vp.zoom(10_000, 500)
    assert vp.span == 30 and vp.zoomed
    assert Viewport(12, 500).min_span == 12  # a very short VOD cannot be zoomed at all


def test_panning_stays_inside_the_vod_and_fit_resets():
    vp = Viewport(10_000, 1000)
    vp.zoom(10, 0)
    vp.pan_to(-50)
    assert vp.start == 0
    vp.pan_to(10 ** 9)
    assert vp.start == 10_000 - vp.span
    vp.fit()
    assert (vp.start, vp.span, vp.zoomed) == (0, 10_000, False)


@pytest.mark.parametrize("pps, step", [(10, 10), (1, 120), (0.1, 900), (0.0305, 3600), (0.0001, 21600)])
def test_ruler_step_is_the_smallest_round_one_that_leaves_room(pps, step):
    assert nice_step(pps) == step
    assert nice_step(pps) * pps >= 80 or step == 21600


def test_a_game_always_gets_the_same_colour():
    assert game_colour("Just Chatting") == game_colour("  just chatting ")
    assert game_colour("Elden Ring") in core_tl.GAME_COLOURS
    assert game_colour("Just Chatting") == core_tl.GAME_COLOURS[zlib.crc32(b"just chatting") % len(core_tl.GAME_COLOURS)]


def test_rows_of_the_widget_are_found_by_height():
    assert [zone_at(Timeline.y_of(z)) for z in ("ruler", "games", "thumbs", "parts")] == [
        "ruler", "games", "thumbs", "parts"
    ]
    assert zone_at(0) == "ruler" and zone_at(core_tl.Y_PARTS) == "parts"


# --------------------------------------------------------------------------- 7b / 7d / 7e: the widget alone
def test_without_a_vod_it_says_so_and_ignores_the_mouse(rig):
    rig.tl.redraw()
    assert any("Get info" in t for t in rig.tl.drawn_texts)
    send_mouse(rig.tl.canvas, QEvent.Type.MouseButtonPress, 50, Timeline.y_of("thumbs"))
    send_wheel(rig.tl.canvas, 50, 10, delta=120)
    assert rig.edits == []


def test_clicking_the_thumbnails_cuts_there(rig):
    rig.load()
    rig.click(1800)
    assert rig.last() == [(0, 1800), (1800, 7200)]


def test_cuts_snap_to_game_changes_but_only_when_close(rig):
    rig.load()
    rig.click(3000 + 2)  # a couple of pixels away from the game change
    assert rig.last() == [(0, 3000), (3000, 7200)]
    rig.load()
    rig.click(4000)  # nowhere near anything
    assert rig.last() == [(0, 4000), (4000, 7200)]


def test_cuts_snap_to_clips_too(rig):
    rig.load(segments=[])
    rig.tl.set_clip_marks([1234])
    rig.click(1236)
    assert rig.last() == [(0, 1234), (1234, 7200)]


def test_clicking_on_a_cut_line_grabs_it_instead_of_adding_another(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)])
    rig.click(1800)
    assert rig.edits == []


def test_dragging_a_cut_line_moves_it_and_one_undo_takes_the_whole_drag_back(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)], segments=[])
    rig.drag(1800, 2400)
    assert rig.last() == [(0, 2400), (2400, 7200)]
    rig.tl.undo()
    assert rig.last() == [(0, 1800), (1800, 7200)]
    assert rig.tl.ranges == [(0, 1800), (1800, 7200)]


def test_a_cut_line_cannot_be_dragged_past_its_neighbour(rig):
    rig.load(ranges=[(0, 1800), (1800, 3600), (3600, 7200)], segments=[])
    rig.drag(1800, 5000)
    assert rig.last() == [(0, 3599), (3599, 3600), (3600, 7200)]


def test_dragging_the_start_of_a_part_next_to_a_skipped_section(rig):
    rig.load(ranges=[(0, 1000), (3000, 7200)], segments=[])
    rig.drag(3000, 2000)
    assert rig.last() == [(0, 1000), (2000, 7200)]


def test_right_click_removes_a_cut_line_between_two_parts(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)])
    rig.right_click(1800)
    assert rig.last() == [(0, 7200)]


def test_right_click_on_the_border_of_a_skipped_section_explains_instead(rig):
    rig.load(ranges=[(0, 1000), (3000, 7200)])
    rig.right_click(1000)
    assert rig.edits == [] and "skip" in rig.tl.hint_text()


def test_clicking_a_part_skips_it_and_clicking_the_gap_brings_it_back(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)])
    rig.click(1000, zone="parts")
    assert rig.last() == [(1800, 7200)]
    rig.click(1000, zone="parts")
    assert rig.last() == [(0, 1800), (1800, 7200)]


def test_the_last_remaining_part_cannot_be_skipped(rig):
    rig.load(ranges=[(0, 7200)])
    rig.click(3000, zone="parts")  # not near an edge
    assert rig.edits == [] and "one part" in rig.tl.hint_text()


def test_clicking_a_skipped_section_in_the_thumbnails_explains_instead_of_cutting(rig):
    rig.load(ranges=[(0, 1000), (3000, 7200)], segments=[])
    rig.click(2000)
    assert rig.edits == [] and "skipped" in rig.tl.hint_text()


def test_an_empty_plan_starts_with_the_whole_vod_on_a_click(rig):
    rig.load(ranges=[])
    rig.click(100, zone="parts")
    assert rig.last() == [(0, 7200)]


def test_double_clicking_a_game_makes_it_its_own_part(rig):
    rig.load()
    rig.double_click(4000)
    assert rig.last() == [(0, 3000), (3000, 5400), (5400, 7200)]


def test_shift_double_click_keeps_only_that_game(rig):
    rig.load()
    rig.double_click(4000, shift=True)
    assert rig.last() == [(3000, 5400)]


def test_double_click_outside_the_game_row_acts_like_a_click(rig):
    rig.load()
    rig.double_click(1800, zone="thumbs")
    assert rig.last() == [(0, 1800), (1800, 7200)]


def test_with_an_invalid_cut_text_the_timeline_does_not_edit(rig):
    rig.load(ranges=None)
    for zone in ("thumbs", "parts"):
        rig.click(1800, zone=zone)
    rig.double_click(4000)
    rig.right_click(1800)
    assert rig.edits == [] and "error" in rig.tl.hint_text()


def test_mouse_wheel_zooms_around_the_mouse_and_shift_wheel_moves(rig):
    rig.load()
    x = rig.x(1800)
    send_wheel(rig.tl.canvas, x, 10, delta=120)
    assert rig.tl.vp.span < DUR
    assert rig.tl.t_at(x) == pytest.approx(1800, abs=1)  # moment under the mouse stayed in place
    start = rig.tl.vp.start
    send_wheel(rig.tl.canvas, 100, 10, delta=-120, modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert rig.tl.vp.start > start
    send_wheel(rig.tl.canvas, 100, 10, delta=-120)
    rig.tl.zoom_fit()
    assert rig.tl.vp.span == DUR


def test_dragging_the_ruler_pans_a_zoomed_timeline(rig):
    rig.load()
    rig.tl.zoom_in()
    rig.tl.zoom_in()
    start = rig.tl.vp.start
    y = Timeline.y_of("ruler")
    send_mouse(rig.tl.canvas, QEvent.Type.MouseButtonPress, 300, y, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    send_mouse(rig.tl.canvas, QEvent.Type.MouseMove, 200, y, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    send_mouse(rig.tl.canvas, QEvent.Type.MouseButtonRelease, 200, y, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    assert rig.tl.vp.start > start and rig.edits == []


def test_a_new_vod_forgets_the_old_one(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)], storyboard=SB)
    rig.click(900, zone="parts")
    assert rig.tl.btn_undo.isEnabled()
    rig.tl.set_source(600, [], None)
    assert (rig.tl.ranges, rig.tl.segments, rig.tl.frames_state) == (None, [], "none")
    assert not rig.tl.btn_undo.isEnabled()
    rig.tl.undo()  # nothing to undo
    assert rig.edits[-1] == [(1800, 7200)]


def test_hovering_names_the_time_and_the_game(rig):
    rig.load()
    rig.hover(4000, zone="thumbs")
    assert "1:06:40" in rig.tl.hint_text() and "Elden Ring" in rig.tl.hint_text()
    rig.leave()
    assert rig.tl.hint_text() == tlm.IDLE_HINT


def test_without_game_information_the_games_row_says_so(rig):
    rig.load(segments=[])
    assert any("No game information" in t for t in rig.tl.drawn_texts)


# --------------------------------------------------------------------------- 7c: thumbnails
pytest.importorskip("PIL.Image", reason="Pillow is optional")


def test_thumbnails_show_loading_then_pictures(rig):
    rig.load(storyboard=SB)
    assert rig.tl.frames_state == "loading" and any("Loading" in t for t in rig.tl.drawn_texts)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    n = rig.tl.drawn_thumb_count
    assert rig.tl.frames_state == "ready" and 1 <= n <= rig.tl.vp.width / tlm.THUMB_W + 3


def test_zooming_in_shows_more_of_the_frames(rig):
    rig.load(storyboard=SB)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    before = rig.tl.vp.span
    for _ in range(4):
        rig.tl.zoom_in()
    rig.tl.redraw()
    assert rig.tl.vp.span < before and rig.tl.drawn_thumb_count >= 1


def test_frames_that_all_failed_say_unavailable(rig):
    rig.load(storyboard=SB)
    rig.tl.set_frames([None] * 200)
    rig.tl.redraw()
    assert rig.tl.frames_state == "failed" and rig.tl.drawn_thumb_count == 0
    assert any("not available" in t for t in rig.tl.drawn_texts)


def test_a_vod_without_a_storyboard_says_so(rig):
    rig.load(storyboard=None)
    assert rig.tl.frames_state == "none" and any("no preview" in t for t in rig.tl.drawn_texts)


def test_without_pillow_the_timeline_still_works_and_says_why(rig, monkeypatch):
    monkeypatch.setattr(tlm, "Image", None)
    rig.load(storyboard=SB)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    assert rig.tl.drawn_thumb_count == 0 and any("Pillow" in t for t in rig.tl.drawn_texts)
    rig.click(1800)
    assert rig.last() == [(0, 1800), (1800, 7200)]


def test_the_hover_preview_appears_only_when_the_pictures_are_ready(rig):
    rig.load(storyboard=SB)
    rig.hover(3000, zone="thumbs")
    rig.tl.redraw()
    assert not rig.tl.drawn_hover_preview
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    rig.hover(3000, zone="thumbs")
    rig.tl.redraw()
    assert rig.tl.drawn_hover_preview


def test_skipped_parts_are_dimmed_in_the_thumbnails(rig):
    rig.load(ranges=[(0, 3600)], storyboard=SB)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    assert any(dim for (_, dim) in rig.tl._pixmaps) and any(not dim for (_, dim) in rig.tl._pixmaps)


# --------------------------------------------------------------------------- 7e: muted audio stretches
def test_the_timeline_draws_a_red_line_for_each_muted_stretch_and_says_how_much(rig):
    rig.load()
    assert rig.tl.drawn_muted_rects == [] and rig.tl.muted_box.isHidden()
    rig.tl.set_muted([(600, 900), (3000, 3300)])
    rig.tl.redraw()
    assert len(rig.tl.drawn_muted_rects) == 2
    assert rig.tl.muted_info.text() == "2 stretches \u00b7 0:10:00 silenced by Twitch"
    assert not rig.tl.muted_box.isHidden()
    y0 = tlm.Y_GAMES + tlm.GAMES_H - tlm.MUTED_H
    assert all(r[1] == y0 for r in rig.tl.drawn_muted_rects)


def test_the_red_line_can_be_switched_off(rig):
    rig.load()
    rig.tl.set_muted([(600, 900)])
    rig.tl.muted_switch.click()
    rig.tl.redraw()
    assert rig.tl.drawn_muted_rects == []
    assert rig.tl._muted_at(700) is None


def test_a_new_vod_forgets_the_old_muted_stretches(rig):
    rig.load()
    rig.tl.set_muted([(600, 900)])
    rig.load()
    assert rig.tl.muted == [] and rig.tl.drawn_muted_rects == [] and rig.tl.muted_box.isHidden()


def test_hovering_a_muted_stretch_says_so(rig):
    rig.load()
    rig.tl.set_muted([(600, 900)])
    rig.hover(700, zone="games")
    assert "muted by Twitch (0:10:00 \u2192 0:15:00)" in rig.tl.hint_text()
    rig.hover(1000, zone="games")
    assert "muted by Twitch" not in rig.tl.hint_text()


def test_cuts_snap_to_the_edges_of_muted_stretches(rig):
    rig.load(ranges=())
    rig.tl.set_muted([(601, 901)])
    assert rig.tl._snap(602) == 601 and rig.tl._snap(900) == 901
    rig.tl.set_show_muted(False)
    assert rig.tl._snap(602) == 602  # hidden: not snapped to


# --------------------------------------------------------------------------- inside the Plan tab
def load_vod_with_timeline(win, **extra) -> Timeline:
    win.source = eng.SourceInfo(**{**SOURCE, "segments": SEGMENTS, "storyboard": SB, **extra})
    win.tab_plan.set_cut_text("0:00:00 - end")
    win.update_preview()
    win.tab_plan.timeline.redraw()
    return win.tab_plan.timeline


def preview_of(win) -> tuple[str, str]:
    return win.tab_plan.preview_text(), win.tab_plan.preview_kind


def _cards_in_order(layout) -> list:
    """The cards of a layout in reading order, looking inside nested layouts (the lower workspace of the Plan page
    holds Cut points and Clips side by side since Phase 9e)."""
    out = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            out.append(item.widget())
        elif item.layout() is not None:
            out.extend(_cards_in_order(item.layout()))
    return out


def test_the_timeline_sits_above_the_cut_points(win):
    page = win.tab_plan
    cards = [c for c in _cards_in_order(page.body_layout) if isinstance(c, Card)]
    titles = [c.title_label.text() for c in cards]
    assert titles.index("Timeline") < titles.index("Cut points") < titles.index("Clips \u2192 chapters")


def test_loading_a_vod_feeds_the_timeline(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    assert tl.duration == DUR and tl.segments == SEGMENTS and tl.storyboard is SB
    assert tl.ranges == [(0, 7200)]


def test_the_timeline_follows_the_cut_text(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    win.tab_plan.set_cut_text("0:00:00 - 30:00 - 1:30:00 ; 1:45:00 - end")
    win.update_preview()
    assert tl.ranges == [(0, 1800), (1800, 5400), (6300, 7200)]
    win.tab_plan.set_cut_text("")
    win.update_preview()
    assert tl.ranges == []


def test_a_broken_cut_text_switches_the_timeline_to_its_error_state(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    win.tab_plan.set_cut_text("0:00:00 - 50:00 - 40:00 - end")
    win.update_preview()
    assert tl.ranges is None
    assert preview_of(win)[1] == "err"


def test_an_edit_on_the_timeline_rewrites_the_cut_text_and_the_preview(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    tl._on_press(tl.x_of(600), Timeline.y_of("thumbs"))
    tl._on_release()
    assert win.cut_text() == "0:00:00 - 0:10:00 - end"
    assert "Part 2:  0:10:00 \u2192 2:00:00" in preview_of(win)[0]


def test_skipping_the_first_part_moves_the_start(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    win.tab_plan.set_cut_text("0:00:00 - 0:10:00 - end")
    win.update_preview()
    tl.redraw()
    tl._on_press(tl.x_of(300), Timeline.y_of("parts"))
    tl._on_release()
    assert win.cut_text() == "0:10:00 - end"
    assert preview_of(win)[1] == "ok"


def test_skipping_a_middle_part_writes_a_second_line(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    win.tab_plan.set_cut_text("0:00:00 - 0:10:00 - 1:00:00 - end")
    win.update_preview()
    tl.redraw()
    tl._on_press(tl.x_of(2000), Timeline.y_of("parts"))
    tl._on_release()
    assert win.cut_text() == "0:00:00 - 0:10:00\n1:00:00 - end"
    assert preview_of(win)[1] == "ok" and "Part 2:  1:00:00" in preview_of(win)[0]


def test_the_timeline_and_the_text_agree_after_a_long_series_of_edits(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    rng = random.Random(7)
    tl = load_vod_with_timeline(win)
    for _ in range(60):
        t = rng.uniform(0, DUR)
        zone = rng.choice(["thumbs", "parts", "thumbs"])
        tl._on_press(tl.x_of(t), Timeline.y_of(zone))
        tl._on_release()
        if rng.random() < 0.2:
            tl.undo()
        assert tl.ranges == eng.ranges_of(win.cut_text(), DUR)
        assert preview_of(win)[1] == "ok"


def test_split_at_a_clip_updates_the_timeline_and_a_second_split_changes_nothing(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    win.clips = make_clips()
    win.clips_loaded = True
    win.refresh_clips()
    assert tl.clip_marks == [pytest.approx(600.4), 3600]
    win.tab_plan.select_clips(0)
    win.tab_plan.split_at_clip()
    first = win.cut_text()
    assert len(tl.ranges) == 2
    win.tab_plan.split_at_clip()
    assert win.cut_text() == first and win._boxes == [] and preview_of(win)[1] == "ok"


def test_frames_arrive_in_the_background_and_reach_the_timeline(qtbot, win, monkeypatch):
    calls = []
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: calls.append(sb) or fake_frames())
    tl = load_vod_with_timeline(win)
    qtbot.waitUntil(lambda: tl.frames_state == "ready", timeout=3000)
    assert calls == [SB]


def test_frames_of_a_vod_that_was_replaced_are_ignored(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [None] * sb.count)
    load_vod_with_timeline(win)
    old = win.source
    win.source = eng.SourceInfo(**{**SOURCE, "id": "v2", "storyboard": None})
    win.update_preview()
    win.tab_plan.on_frames(old, fake_frames())
    assert win.tab_plan.timeline.frames_state == "none"


def test_a_crash_while_loading_frames_only_costs_the_thumbnails(qtbot, win, monkeypatch):
    def boom(sb):
        raise RuntimeError("disk full")

    monkeypatch.setattr(background_jobs, "load_storyboard_frames", boom)
    tl = load_vod_with_timeline(win)
    qtbot.waitUntil(lambda: tl.frames_state == "failed", timeout=3000)
    assert tl.ranges == [(0, 7200)]


def test_without_pillow_no_frames_are_requested(win, monkeypatch):
    monkeypatch.setattr(plan_tab_module.timeline_module, "Image", None)
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: pytest.fail("must not load"))
    tl = load_vod_with_timeline(win)
    assert tl.frames_state == "failed"


def test_a_vod_without_game_info_or_thumbnails_still_gets_a_working_timeline(win):
    win.source = eng.SourceInfo(**SOURCE)
    win.tab_plan.set_cut_text("0:00:00 - end")
    win.update_preview()
    tl = win.tab_plan.timeline
    assert tl.segments == [] and tl.frames_state == "none" and tl.ranges == [(0, 7200)]


def test_with_no_vod_the_timeline_waits(win):
    assert win.tab_plan.timeline.duration == 0 and win.tab_plan.timeline.ranges is None
    win.tab_plan.set_cut_text("0:00:00 - 10:00")
    win.update_preview()
    assert win.tab_plan.timeline.ranges is None


def test_refreshing_the_clips_updates_the_marks_without_a_vod_change(win, monkeypatch):
    monkeypatch.setattr(background_jobs, "load_storyboard_frames", lambda sb: [])
    tl = load_vod_with_timeline(win)
    win.clips = make_clips()
    win.clips_loaded = True
    win.refresh_clips()
    assert tl.clip_marks == [pytest.approx(600.4), 3600]
    assert len(tl.clip_details) == 2
    assert any("Epic fail" in d for d in tl.clip_details.values())
    win.clips = []
    win.refresh_clips()
    assert tl.clip_marks == []
    assert tl.clip_details == {}


# ---------------------------------------------------------------------------
# Phase 9f: Visual polish, keyboard editing, redo, minimap, legend, flags,
# zoom readout, context menu, and snap feedback (E1-E9)
# ---------------------------------------------------------------------------


def test_core_timeline_helpers_for_gaps_clustering_totals_snap_and_minimap():
    # gaps_of
    assert core_tl.gaps_of([(0, 1800), (3600, 7200)], 7200) == [(1800.0, 3600.0)]
    assert core_tl.gaps_of([(600, 3000)], 3600) == [(0.0, 600.0), (3000.0, 3600.0)]
    # game_totals sorted descending
    totals = core_tl.game_totals(SEGMENTS)
    assert [title for title, _ in totals] == ["Just Chatting", "Elden Ring"]
    assert totals[0][1] == pytest.approx(4800.0)
    assert totals[1][1] == pytest.approx(2400.0)
    # cluster_marks merges marks within min_px
    groups = core_tl.cluster_marks([100.0, 104.0, 250.0], px_per_sec=1.0, min_px=9.0)
    assert len(groups) == 2
    assert groups[0][1] == 2
    assert groups[1][1] == 1
    # snap_target and build_snap_kinds
    pts = core_tl.build_snap_points(7200, SEGMENTS, [1200.0], [(2000.0, 2100.0)])
    kinds = core_tl.build_snap_kinds(7200, SEGMENTS, [1200.0], [(2000.0, 2100.0)])
    t_game = core_tl.snap_target(3005.0, pts, px_per_sec=0.1)
    assert t_game == 3000.0 and kinds[t_game] == core_tl.SNAP_GAME
    t_clip = core_tl.snap_target(1203.0, pts, px_per_sec=0.1)
    assert t_clip == 1200.0 and kinds[t_clip] == core_tl.SNAP_CLIP
    assert core_tl.snap_target(4000.0, pts, px_per_sec=0.1) is None
    # minimap_lens
    lx0, lx1 = core_tl.minimap_lens(1800.0, 3600.0, 7200.0, 720.0)
    assert 0 <= lx0 < lx1 <= 720


def test_skipped_sections_draw_hatched_rects_and_parts_use_rounded_pills(qtbot):
    r = Rig(qtbot)
    r.load([(0, 1800), (3600, 7200)])
    assert len(r.tl.drawn_skipped_rects) == 1
    x0, _y0, x1, _y1 = r.tl.drawn_skipped_rects[0]
    assert x0 == pytest.approx(r.x(1800), abs=1.5)
    assert x1 == pytest.approx(r.x(3600), abs=1.5)
    assert any("Part 1" in t or "P1" in t for t in r.tl.drawn_texts)


def test_keyboard_editing_cut_delete_nudge_home_end_zoom_and_redo(qtbot):
    from PySide6.QtGui import QKeyEvent

    def press_key(tl, key, mods=Qt.KeyboardModifier.NoModifier, text=""):
        ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, text)
        QApplication.sendEvent(tl.canvas, ev)

    r = Rig(qtbot)
    r.load([(0, 7200)])
    # Hover at 1800s and press S to split
    r.hover(1800, "thumbs")
    press_key(r.tl, Qt.Key.Key_S, text="s")
    assert len(r.tl.ranges) == 2
    cut_t = r.tl.ranges[0][1]
    assert abs(cut_t - 1800) <= 20

    # Nudge cut right by 1s (Right arrow), then +10s (Shift+Right)
    press_key(r.tl, Qt.Key.Key_Right)
    assert r.tl.ranges[0][1] == cut_t + 1
    press_key(r.tl, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert r.tl.ranges[0][1] == cut_t + 11

    # Undo reverses the coalesced nudge burst and then the cut; Redo restores them
    assert r.tl.btn_undo.isEnabled()
    r.tl.undo()
    assert r.tl.ranges[0][1] == cut_t
    assert r.tl.btn_redo.isEnabled()
    r.tl.redo()
    assert r.tl.ranges[0][1] == cut_t + 11

    # Delete removes the selected cut
    press_key(r.tl, Qt.Key.Key_Delete)
    assert r.tl.ranges == [(0, 7200)]

    # Zoom keys (+, -, Home, End, 0)
    press_key(r.tl, Qt.Key.Key_Plus, text="+")
    assert r.tl.vp.zoomed
    press_key(r.tl, Qt.Key.Key_End)
    assert r.tl.vp.start + r.tl.vp.span == pytest.approx(7200)
    press_key(r.tl, Qt.Key.Key_Home)
    assert r.tl.vp.start == pytest.approx(0)
    press_key(r.tl, Qt.Key.Key_0, text="0")
    assert not r.tl.vp.zoomed


def test_minimap_appears_when_zoomed_and_pans_viewport_on_drag(qtbot):
    r = Rig(qtbot)
    r.load([(0, 3600), (3600, 7200)])
    assert not r.tl.minimap.isVisible()
    r.tl.zoom_in()
    r.tl.zoom_in()
    r.tl.redraw()
    assert r.tl.minimap.isVisible()
    assert r.tl.minimap.drawn_lens is not None
    # Click near the right side of the minimap to pan toward the end of the VOD
    w = max(r.tl.minimap.width(), 400)
    send_mouse(r.tl.minimap, QEvent.Type.MouseButtonPress, w - 30, 6,
               Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    send_mouse(r.tl.minimap, QEvent.Type.MouseButtonRelease, w - 30, 6,
               Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    assert r.tl.vp.start > 3600
    r.tl.zoom_fit()
    assert not r.tl.minimap.isVisible()


def test_game_legend_chips_isolate_and_highlight_games_and_zoom_label_updates(qtbot):
    r = Rig(qtbot)
    r.load([(0, 7200)], segments=SEGMENTS)
    assert not r.tl.legend_box.isHidden()
    assert len(r.tl.legend_chips) == 2
    assert r.tl.legend_chips[0].title == "Just Chatting"
    assert r.tl.legend_chips[1].title == "Elden Ring"
    assert "Showing the whole VOD" in r.tl.zoom_label.text()
    r.tl.zoom_in()
    assert "Showing " in r.tl.zoom_label.text() and " of 2:00:00" in r.tl.zoom_label.text()

    # Clicking the Elden Ring chip isolates Elden Ring into its own part
    r.tl.isolate_game("Elden Ring", only=True)
    assert r.tl.ranges == [(3000, 5400)]


def test_clip_flags_cluster_when_close_and_show_hover_details(qtbot):
    r = Rig(qtbot)
    r.load([(0, 7200)])
    details = {
        600.0: "First clip \u00b7 by alice \u00b7 500 views",
        610.0: "Second clip \u00b7 by bob \u00b7 120 views",
        5000.0: "Far clip \u00b7 by carol \u00b7 40 views",
    }
    r.tl.set_clip_marks([600.0, 610.0, 5000.0], details)
    r.tl.redraw()
    # 600s and 610s are within 9 px on a 2-hour VOD so they cluster into count=2
    counts = [cnt for _fx, cnt in r.tl.drawn_flags]
    assert counts == [2, 1]
    # Hover over the far clip flag on the ruler
    r.hover(5000.0, "ruler")
    assert "Far clip" in r.tl.canvas.toolTip()
    assert "carol" in r.tl.canvas.toolTip()


def test_right_click_on_empty_space_populates_context_menu_and_drag_shows_snap_feedback(qtbot):
    r = Rig(qtbot)
    r.load([(0, 7200)], segments=SEGMENTS)
    # Right-click in the middle of thumbnails (not on a cut line) opens context menu
    x = r.x(1500)
    y = core_tl.y_of("thumbs")
    send_mouse(r.tl.canvas, QEvent.Type.MouseButtonPress, x, y,
               Qt.MouseButton.RightButton, Qt.MouseButton.RightButton)
    actions = [a.text() for a in r.tl._context_menu.actions() if not a.isSeparator()]
    assert any("Cut here" in a for a in actions)
    assert any("Isolate" in a for a in actions)
    r.tl._context_menu.hide()

    # Dragging a cut near a game boundary at 3000s records snap feedback ("Game change")
    r.click(1800, "thumbs")
    assert len(r.tl.ranges) == 2
    x_cut = r.x(r.tl.ranges[0][1])
    send_mouse(r.tl.canvas, QEvent.Type.MouseButtonPress, x_cut, y,
               Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    send_mouse(r.tl.canvas, QEvent.Type.MouseMove, r.x(3005), y,
               Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    r.tl.redraw()
    assert r.tl._snap_feedback is not None
    assert r.tl._snap_feedback[1] == core_tl.SNAP_GAME
    assert any("snaps to: Game change" in t for t in r.tl.drawn_texts)
    send_mouse(r.tl.canvas, QEvent.Type.MouseButtonRelease, r.x(3005), y,
               Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)

