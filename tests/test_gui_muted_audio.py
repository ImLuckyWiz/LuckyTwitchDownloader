"""Tkinter GUI tests for muted audio: the red line on the timeline, muted time per part,
and the Get info loading indicators.

These tests need Tk and a display (on a headless Linux box: xvfb-run -a python -m pytest).
"""

from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tk = pytest.importorskip("tkinter")

import luckytwitch_downloader as dl  # noqa: E402
import luckytwitch_engine as eng  # noqa: E402
import test_gui_plan_tab as plan_tab_tests  # noqa: E402
import test_gui_timeline as tl_tests  # noqa: E402
from ui import timeline as tlm  # noqa: E402
from ui.timeline import Timeline  # noqa: E402

gui = plan_tab_tests.gui


def red_bars(tl):
    return [
        i
        for i in tl.canvas.find_all()
        if tl.canvas.type(i) == "rectangle"
        and tl.canvas.itemcget(i, "fill") == tlm.MUTED_COLOUR
    ]


def test_the_timeline_draws_a_red_line_for_each_muted_stretch_and_says_how_much(gui):
    rig = tl_tests.Rig(gui.root)
    rig.load()
    assert red_bars(rig.tl) == [] and rig.tl.muted_box.winfo_manager() == ""
    rig.tl.set_muted([(600, 900), (3000, 3300)])
    rig.tl.redraw()
    assert len(red_bars(rig.tl)) == 2
    assert rig.tl.muted_lbl.get() == "2 stretches · 0:10:00 silenced by Twitch"
    assert rig.tl.muted_box.winfo_manager() == "pack"  # shown (the test window itself is hidden)
    y0 = tlm.Y_GAMES + tlm.GAMES_H - tlm.MUTED_H  # it sits along the bottom of the games bar
    assert all(rig.tl.canvas.coords(i)[1] == y0 for i in red_bars(rig.tl))


def test_the_red_line_can_be_switched_off(gui):
    rig = tl_tests.Rig(gui.root)
    rig.load()
    rig.tl.set_muted([(600, 900)])
    rig.tl.show_muted.set(False)
    rig.tl._toggle_muted()
    rig.tl.redraw()
    assert red_bars(rig.tl) == []
    assert rig.tl._muted_at(700) is None


def test_a_new_vod_forgets_the_old_muted_stretches(gui):
    rig = tl_tests.Rig(gui.root)
    rig.load()
    rig.tl.set_muted([(600, 900)])
    rig.load()
    assert rig.tl.muted == [] and red_bars(rig.tl) == []


def test_hovering_a_muted_stretch_says_so(gui):
    rig = tl_tests.Rig(gui.root)
    rig.load()
    rig.tl.set_muted([(600, 900)])
    rig.tl._hover(tl_tests.ev(x=rig.x(700), y=rig.tl.y_of("games")))
    assert "muted by Twitch (0:10:00 → 0:15:00)" in rig.tl.hint.get()
    rig.tl._hover(tl_tests.ev(x=rig.x(1000), y=rig.tl.y_of("games")))
    assert "muted by Twitch" not in rig.tl.hint.get()


def test_cuts_snap_to_the_edges_of_muted_stretches(gui):
    rig = tl_tests.Rig(gui.root)
    rig.load(ranges=())
    rig.tl.set_muted([(601, 901)])
    assert rig.tl._snap(602) == 601 and rig.tl._snap(900) == 901
    rig.tl.show_muted.set(False)
    rig.tl._toggle_muted()
    assert rig.tl._snap(602) == 602  # hidden: not snapped to


def test_the_plan_tab_hands_the_muted_stretches_to_the_timeline(gui):
    gui.load_vod(muted=[(600.0, 900.0)])
    gui.app.sync_timeline()
    assert gui.app.timeline.muted == [(600.0, 900.0)]


def test_each_part_says_how_much_of_it_is_muted(gui):
    gui.load_vod(muted=[(600.0, 900.0), (3500.0, 3700.0)])
    gui.set_cuts("0:00:00 - 1:00:00 - end")
    gui.app.update_preview()
    text, kind = gui.preview()
    lines = text.splitlines()
    assert kind == "ok"
    assert lines[0].endswith("(1:00:00)   ·  0:06:40 muted")  # 300 s + the first 100 s of the second stretch
    assert lines[1].endswith("(1:00:00)   ·  0:01:40 muted")
    assert "0:08:20 muted" in gui.app.plan_summary.get()  # 500 s in all


def test_without_muted_stretches_the_preview_is_as_before(gui):
    gui.load_vod()
    gui.set_cuts("0:00:00 - end")
    gui.app.update_preview()
    assert "muted" not in gui.preview()[0] and "muted" not in gui.app.plan_summary.get()


# --------------------------------------------------------------------------- «Get info» shows that it is working
def pump_until(gui, cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        gui.app.poll_queue()
        gui.root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_get_info_shows_it_is_working_then_goes_back(gui, monkeypatch):
    release = threading.Event()

    def slow_info(text):
        release.wait(5)
        return eng.SourceInfo(**plan_tab_tests.SOURCE)

    monkeypatch.setattr(dl, "get_source_info", slow_info)
    app = gui.app
    app.tools_busy = False  # (the start-up tool check is stubbed; its "done" message may not have been read yet)
    app.vod_var.set("123")
    app.on_get_info()
    gui.root.update()
    try:
        assert app.info_btn.cget("text").startswith("Loading") and str(app.info_btn.cget("state")) == "disabled"
        assert app.info_var.get().startswith("Reading VOD info")
        assert str(app.progress.cget("mode")) == "indeterminate"
        assert pump_until(gui, lambda: app.info_btn.cget("text") == "Loading...")  # the dots move
    finally:
        release.set()
    assert pump_until(gui, lambda: app.source is not None)
    assert app.info_btn.cget("text") == "Get info" and str(app.info_btn.cget("state")) == "normal"
    assert str(app.progress.cget("mode")) == "determinate" and app._info_job is None
    assert "Big Stream" in app.info_var.get()


def test_get_info_that_fails_also_goes_back(gui, monkeypatch):
    def boom(text):
        raise eng.EngineError("yt-dlp could not read that URL")

    monkeypatch.setattr(dl, "get_source_info", boom)
    app = gui.app
    app.tools_busy = False
    before = app.info_var.get()
    app.vod_var.set("123")
    app.on_get_info()
    assert pump_until(gui, lambda: any(b[0] == "showerror" for b in gui.boxes))
    assert app.info_btn.cget("text") == "Get info" and str(app.info_btn.cget("state")) == "normal"
    assert app.info_var.get() == before and app._info_job is None


def test_get_info_leaves_the_bar_alone_while_a_download_runs(gui, monkeypatch):
    monkeypatch.setattr(dl, "get_source_info", lambda text: eng.SourceInfo(**plan_tab_tests.SOURCE))
    app = gui.app
    app.worker = SimpleNamespace(is_alive=lambda: True)
    app.progress.config(mode="determinate")
    app.progress["value"] = 42
    app.set_info_busy(True)
    assert str(app.progress.cget("mode")) == "determinate" and app.progress["value"] == 42
    app.set_info_busy(False)
    assert app.progress["value"] == 42
    app.worker = None
