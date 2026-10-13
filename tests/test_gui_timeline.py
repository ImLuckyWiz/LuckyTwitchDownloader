"""The Timeline widget (ui/timeline.py) on its own, and wired into the Plan tab.

Like test_gui_plan_tab.py these need Tk and a display (on a headless box: xvfb-run -a python -m pytest) and are
skipped when there is none. The mouse is simulated by calling the widget's handlers with fake events, so no real
window or pointer is needed.
"""

import time
import zlib
from types import SimpleNamespace

import pytest

tk = pytest.importorskip("tkinter")

import luckytwitch_engine as eng  # noqa: E402
from luckytwitch_engine import GameSegment, Storyboard  # noqa: E402
import test_gui_plan_tab as plan_tab_tests  # noqa: E402
from ui import plan_tab as plan_tab_module  # noqa: E402
from ui import timeline as tlm  # noqa: E402
from ui.timeline import Timeline, Viewport, game_colour, nice_step, zone_at  # noqa: E402

SOURCE = plan_tab_tests.SOURCE
gui = plan_tab_tests.gui  # the fixture that runs the whole App lives in test_gui_plan_tab.py

DUR = 7200.0
SEGMENTS = [GameSegment(0, 3000, "Just Chatting"), GameSegment(3000, 5400, "Elden Ring"), GameSegment(5400, 7200, "Just Chatting")]
SB = Storyboard(urls=["a"], tile_w=160, tile_h=90, columns=5, rows=40, interval=DUR / 200, count=200)


def ev(x=0, y=0, state=0, delta=0, num=None):
    return SimpleNamespace(x=x, y=y, state=state, delta=delta, num=num)


def fake_frames(n=200):
    from PIL import Image

    return [Image.new("RGB", (160, 90), ((i * 37) % 256, (i * 91) % 256, (i * 13) % 256)) for i in range(n)]


class Rig:
    """A Timeline in its own window that records every edit it reports."""

    def __init__(self, root):
        self.root = root
        self.edits: list[list] = []
        self.tl = Timeline(root, on_edit=lambda r: self.edits.append(list(r)))
        self.tl.pack(fill="x")
        root.update_idletasks()

    def load(self, ranges=((0, 7200),), segments=SEGMENTS, storyboard=None):
        self.tl.set_source(DUR, segments, storyboard)
        self.tl.set_ranges(list(ranges) if ranges is not None else None)
        self.tl.redraw()

    # simulated mouse, by moment in the VOD
    def x(self, t):
        return self.tl.x_of(t)

    def click(self, t, zone="thumbs", state=0):
        self.tl._press(ev(self.x(t), Timeline.y_of(zone), state))
        self.tl._release(ev())

    def drag(self, t0, t1, zone="parts"):
        y = Timeline.y_of(zone)
        self.tl._press(ev(self.x(t0), y))
        self.tl._motion(ev(self.x(t1), y))
        self.tl._release(ev())

    def right_click(self, t, zone="parts"):
        self.tl._right(ev(self.x(t), Timeline.y_of(zone)))

    def double_click(self, t, zone="games", state=0):
        self.tl._double(ev(self.x(t), Timeline.y_of(zone), state))
        self.tl._release(ev())

    def last(self):
        return self.edits[-1] if self.edits else None


@pytest.fixture()
def rig():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no usable display for Tk: {e}")
    root.withdraw()
    import luckytwitch_downloader as dl

    dl.apply_dark_theme(root)  # defines the Muted.TLabel style the toolbar uses
    r = Rig(root)
    yield r
    for after_id in root.tk.call("after", "info"):
        root.after_cancel(after_id)
    root.destroy()


# --------------------------------------------------------------------------- pure helpers
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
    assert game_colour("Elden Ring") in tlm.GAME_COLOURS
    # crc32, not Python's per-run randomised hash(): the value is the same in every run
    assert game_colour("Just Chatting") == tlm.GAME_COLOURS[zlib.crc32(b"just chatting") % len(tlm.GAME_COLOURS)]


def test_rows_of_the_widget_are_found_by_height():
    assert [zone_at(Timeline.y_of(z)) for z in ("ruler", "games", "thumbs", "parts")] == ["ruler", "games", "thumbs", "parts"]
    assert zone_at(0) == "ruler" and zone_at(tlm.Y_PARTS) == "parts"


# --------------------------------------------------------------------------- the widget alone
def test_without_a_vod_it_says_so_and_ignores_the_mouse(rig):
    rig.tl.redraw()
    texts = [rig.tl.canvas.itemcget(i, "text") for i in rig.tl.canvas.find_all() if rig.tl.canvas.type(i) == "text"]
    assert any("Get info" in t for t in texts)
    rig.tl._press(ev(50, Timeline.y_of("thumbs")))
    rig.tl._wheel(ev(50, 10, delta=120))
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
    assert rig.edits == [] and "skip" in rig.tl.hint.get()


def test_clicking_a_part_skips_it_and_clicking_the_gap_brings_it_back(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)])
    rig.click(1000, zone="parts")
    assert rig.last() == [(1800, 7200)]
    rig.click(1000, zone="parts")
    assert rig.last() == [(0, 1800), (1800, 7200)]


def test_the_last_remaining_part_cannot_be_skipped(rig):
    rig.load(ranges=[(0, 7200)])
    rig.click(3000, zone="parts")  # (not near an edge: a click within a few pixels of one grabs it instead)
    assert rig.edits == [] and "one part" in rig.tl.hint.get()


def test_clicking_a_skipped_section_in_the_thumbnails_explains_instead_of_cutting(rig):
    rig.load(ranges=[(0, 1000), (3000, 7200)], segments=[])
    rig.click(2000)
    assert rig.edits == [] and "skipped" in rig.tl.hint.get()


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
    rig.double_click(4000, state=0x1)
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
    assert rig.edits == [] and "error" in rig.tl.hint.get()


def test_mouse_wheel_zooms_around_the_mouse_and_shift_wheel_moves(rig):
    rig.load()
    x = rig.x(1800)  # a pixel off the middle of the VOD (the pixel is read BEFORE zooming)
    rig.tl._wheel(ev(x, 10, delta=120))
    assert rig.tl.vp.span < DUR
    assert rig.tl.t_at(x) == pytest.approx(1800, abs=1)  # the moment under the mouse did not move
    start = rig.tl.vp.start
    rig.tl._wheel(ev(100, 10, state=0x1, delta=-120))
    assert rig.tl.vp.start > start
    rig.tl._wheel(ev(100, 10, num=5))
    rig.tl.zoom_fit()
    assert rig.tl.vp.span == DUR


def test_dragging_the_ruler_pans_a_zoomed_timeline(rig):
    rig.load()
    rig.tl.zoom_in()
    rig.tl.zoom_in()
    start = rig.tl.vp.start
    y = Timeline.y_of("ruler")
    rig.tl._press(ev(300, y))
    rig.tl._motion(ev(200, y))
    rig.tl._release(ev())
    assert rig.tl.vp.start > start and rig.edits == []


def test_a_new_vod_forgets_the_old_one(rig):
    rig.load(ranges=[(0, 1800), (1800, 7200)], storyboard=SB)
    rig.click(900, zone="parts")
    assert rig.tl.btn_undo.instate(["!disabled"])
    rig.tl.set_source(600, [], None)
    assert (rig.tl.ranges, rig.tl.segments, rig.tl.frames_state) == (None, [], "none")
    assert rig.tl.btn_undo.instate(["disabled"])
    rig.tl.undo()  # nothing to undo
    assert rig.edits[-1] == [(1800, 7200)]


def test_hovering_names_the_time_and_the_game(rig):
    rig.load()
    rig.tl._hover(ev(rig.x(4000), Timeline.y_of("thumbs")))
    assert "1:06:40" in rig.tl.hint.get() and "Elden Ring" in rig.tl.hint.get()
    rig.tl._leave(ev())
    assert rig.tl.hint.get() == tlm.IDLE_HINT


def test_without_game_information_the_games_row_says_so(rig):
    rig.load(segments=[])
    texts = [rig.tl.canvas.itemcget(i, "text") for i in rig.tl.canvas.find_all() if rig.tl.canvas.type(i) == "text"]
    assert any("No game information" in t for t in texts)


# --------------------------------------------------------------------------- thumbnails
pytest.importorskip("PIL.Image", reason="Pillow is optional")


def image_items(tl):
    return [i for i in tl.canvas.find_all() if tl.canvas.type(i) == "image"]


def texts_of(tl):
    return [tl.canvas.itemcget(i, "text") for i in tl.canvas.find_all() if tl.canvas.type(i) == "text"]


def test_thumbnails_show_loading_then_pictures(rig):
    rig.load(storyboard=SB)
    assert rig.tl.frames_state == "loading" and any("Loading" in t for t in texts_of(rig.tl))
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    n = len(image_items(rig.tl))
    assert rig.tl.frames_state == "ready" and 1 <= n <= rig.tl.vp.width / tlm.THUMB_W + 3  # never a pile of overlaps


def test_zooming_in_shows_more_of_the_frames(rig):
    rig.load(storyboard=SB)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    before = rig.tl.vp.span
    for _ in range(4):
        rig.tl.zoom_in()
    rig.tl.redraw()
    assert rig.tl.vp.span < before and len(image_items(rig.tl)) >= 1


def test_frames_that_all_failed_say_unavailable(rig):
    rig.load(storyboard=SB)
    rig.tl.set_frames([None] * 200)
    rig.tl.redraw()
    assert rig.tl.frames_state == "failed" and image_items(rig.tl) == []
    assert any("not available" in t for t in texts_of(rig.tl))


def test_a_vod_without_a_storyboard_says_so(rig):
    rig.load(storyboard=None)
    assert rig.tl.frames_state == "none" and any("no preview" in t for t in texts_of(rig.tl))


def test_without_pillow_the_timeline_still_works_and_says_why(rig, monkeypatch):
    monkeypatch.setattr(tlm, "ImageTk", None)
    rig.load(storyboard=SB)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    assert image_items(rig.tl) == [] and any("Pillow" in t for t in texts_of(rig.tl))
    rig.click(1800)
    assert rig.last() == [(0, 1800), (1800, 7200)]


def test_the_hover_preview_appears_only_when_the_pictures_are_ready(rig):
    rig.load(storyboard=SB)
    rig.tl._hover(ev(rig.x(3000), Timeline.y_of("thumbs")))
    assert not image_items(rig.tl)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    before = len(image_items(rig.tl))
    rig.tl._hover(ev(rig.x(3000), Timeline.y_of("thumbs")))
    assert len(image_items(rig.tl)) == before + 1


def test_skipped_parts_are_dimmed_in_the_thumbnails(rig):
    rig.load(ranges=[(0, 3600)], storyboard=SB)
    rig.tl.set_frames(fake_frames())
    rig.tl.redraw()
    assert any(dim for (_, dim) in rig.tl._photos) and any(not dim for (_, dim) in rig.tl._photos)


# --------------------------------------------------------------------------- inside the Plan tab
def load_vod_with_timeline(gui, **extra):
    gui.app.source = eng.SourceInfo(**{**SOURCE, "segments": SEGMENTS, "storyboard": SB, **extra})
    gui.set_cuts("0:00:00 - end")
    gui.app.update_preview()
    return gui.app.timeline


def pump(gui, until, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        gui.app.poll_queue()
        gui.root.update()
        if until():
            return True
        time.sleep(0.02)
    return until()


def test_the_timeline_sits_above_the_cut_points(gui):
    rows = {w: w.grid_info()["row"] for w in gui.app.tab_plan.body.winfo_children() if w.grid_info()}
    labels = {w.cget("text"): r for w, r in rows.items() if w.winfo_class() == "TLabelframe"}
    assert labels["Timeline"] < labels["Cut points"] < labels["Clips → chapters (optional)"]


def test_loading_a_vod_feeds_the_timeline(gui):
    tl = load_vod_with_timeline(gui)
    assert tl.duration == DUR and tl.segments == SEGMENTS and tl.storyboard is SB
    assert tl.ranges == [(0, 7200)]


def test_the_timeline_follows_the_cut_text(gui):
    tl = load_vod_with_timeline(gui)
    gui.set_cuts("0:00:00 - 30:00 - 1:30:00 ; 1:45:00 - end")
    gui.app.update_preview()
    assert tl.ranges == [(0, 1800), (1800, 5400), (6300, 7200)]
    gui.set_cuts("")
    gui.app.update_preview()
    assert tl.ranges == []


def test_a_broken_cut_text_switches_the_timeline_to_its_error_state(gui):
    tl = load_vod_with_timeline(gui)
    gui.set_cuts("0:00:00 - 50:00 - 40:00 - end")
    gui.app.update_preview()
    assert tl.ranges is None
    assert gui.preview()[1] == "err"


def test_an_edit_on_the_timeline_rewrites_the_cut_text_and_the_preview(gui):
    tl = load_vod_with_timeline(gui)
    tl.redraw()
    tl._press(ev(tl.x_of(600), Timeline.y_of("thumbs")))
    tl._release(ev())
    assert gui.cuts_text() == "0:00:00 - 0:10:00 - end"
    assert "Part 2:  0:10:00 → 2:00:00" in gui.preview()[0]


def test_skipping_the_first_part_moves_the_start(gui):
    tl = load_vod_with_timeline(gui)
    gui.set_cuts("0:00:00 - 0:10:00 - end")
    gui.app.update_preview()
    tl.redraw()
    tl._press(ev(tl.x_of(300), Timeline.y_of("parts")))
    tl._release(ev())
    assert gui.cuts_text() == "0:10:00 - end"
    assert gui.preview()[1] == "ok"


def test_skipping_a_middle_part_writes_a_second_line(gui):
    tl = load_vod_with_timeline(gui)
    gui.set_cuts("0:00:00 - 0:10:00 - 1:00:00 - end")
    gui.app.update_preview()
    tl.redraw()
    tl._press(ev(tl.x_of(2000), Timeline.y_of("parts")))
    tl._release(ev())
    assert gui.cuts_text() == "0:00:00 - 0:10:00\n1:00:00 - end"
    assert gui.preview()[1] == "ok" and "Part 2:  1:00:00" in gui.preview()[0]


def test_the_timeline_and_the_text_agree_after_a_long_series_of_edits(gui):
    import random

    rng = random.Random(7)
    tl = load_vod_with_timeline(gui)
    tl.redraw()
    for _ in range(60):
        t = rng.uniform(0, DUR)
        zone = rng.choice(["thumbs", "parts", "thumbs"])
        tl._press(ev(tl.x_of(t), Timeline.y_of(zone)))
        tl._release(ev())
        if rng.random() < 0.2:
            tl.undo()
        assert tl.ranges == eng.ranges_of(gui.cuts_text(), DUR)  # the text always says what the timeline shows
        assert gui.preview()[1] == "ok"


def test_split_at_a_clip_updates_the_timeline_and_a_second_split_changes_nothing(gui):
    tl = load_vod_with_timeline(gui)
    gui.load_clips()
    assert tl.clip_marks == [600, 3600]
    gui.app.tree.selection_set("0")
    gui.app.split_at_clip()
    first = gui.cuts_text()
    assert len(tl.ranges) == 2
    gui.app.split_at_clip()
    assert gui.cuts_text() == first and gui.boxes == [] and gui.preview()[1] == "ok"


def test_frames_arrive_in_the_background_and_reach_the_timeline(gui, monkeypatch):
    calls = []
    monkeypatch.setattr(plan_tab_module, "load_storyboard_frames", lambda sb: calls.append(sb) or fake_frames())
    tl = load_vod_with_timeline(gui)
    assert tl.frames_state == "loading"
    assert pump(gui, lambda: tl.frames_state == "ready")
    assert calls == [SB]


def test_frames_of_a_vod_that_was_replaced_are_ignored(gui, monkeypatch):
    monkeypatch.setattr(plan_tab_module, "load_storyboard_frames", lambda sb: [None] * sb.count)
    load_vod_with_timeline(gui)
    old = gui.app.source
    gui.app.source = eng.SourceInfo(**{**SOURCE, "id": "v2", "storyboard": None})
    gui.app.update_preview()
    gui.app.on_frames(old, fake_frames())
    assert gui.app.timeline.frames_state == "none"


def test_a_crash_while_loading_frames_only_costs_the_thumbnails(gui, monkeypatch):
    def boom(sb):
        raise RuntimeError("disk full")

    monkeypatch.setattr(plan_tab_module, "load_storyboard_frames", boom)
    tl = load_vod_with_timeline(gui)
    assert pump(gui, lambda: tl.frames_state == "failed")
    assert tl.ranges == [(0, 7200)]


def test_without_pillow_no_frames_are_requested(gui, monkeypatch):
    monkeypatch.setattr(plan_tab_module.timeline_module, "Image", None)
    monkeypatch.setattr(plan_tab_module, "load_storyboard_frames", lambda sb: pytest.fail("must not load"))
    tl = load_vod_with_timeline(gui)
    assert tl.frames_state == "failed"


def test_a_vod_without_game_info_or_thumbnails_still_gets_a_working_timeline(gui):
    gui.app.source = eng.SourceInfo(**SOURCE)  # the defaults: no segments, no storyboard
    gui.set_cuts("0:00:00 - end")
    gui.app.update_preview()
    tl = gui.app.timeline
    assert tl.segments == [] and tl.frames_state == "none" and tl.ranges == [(0, 7200)]


def test_with_no_vod_the_timeline_waits(gui):
    assert gui.app.timeline.duration == 0 and gui.app.timeline.ranges is None
    gui.set_cuts("0:00:00 - 10:00")
    gui.app.update_preview()
    assert gui.app.timeline.ranges is None


def test_refreshing_the_clips_updates_the_marks_without_a_vod_change(gui):
    tl = load_vod_with_timeline(gui)
    gui.load_clips()
    assert tl.clip_marks == [600, 3600]
    gui.app.clips = []
    gui.app.refresh_clips()
    assert tl.clip_marks == []
