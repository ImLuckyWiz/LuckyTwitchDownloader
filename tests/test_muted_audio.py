"""The stretches Twitch silenced: reading them from the HLS playlist, the muted markers in the .markers.json
for the Premiere plugin, and how the Plan tab shows them (red line on the timeline, muted time per part).

The GUI tests need Tk and a display (on a headless box: xvfb-run -a python -m pytest); the rest does not.
Regenerate the muted sample with:  python tests/test_muted_audio.py
"""

import json
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import luckytwitch_engine as eng  # noqa: E402
from luckytwitch_engine import Chapter, premiere_markers_json  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PLAYLIST_EXCERPT = FIXTURES / "playlist_muted_excerpt.m3u8"  # the start of a real Twitch playlist (segments 0-24)
SAMPLE = FIXTURES / "markers_sample_muted.json"


def playlist(names, length=10.0, extra=()):
    lines = ["#EXTM3U", "#EXT-X-VERSION:6", "#EXT-X-TARGETDURATION:10", "#EXT-X-PLAYLIST-TYPE:EVENT",
             '#EXT-X-MAP:URI="init-0.mp4"', *extra]
    for n in names:
        lines += [f"#EXTINF:{length:.3f},", n]
    return "\n".join(lines + ["#EXT-X-ENDLIST"]) + "\n"


# --------------------------------------------------------------------------- reading the playlist
def test_a_real_playlist_excerpt_gives_the_first_three_minutes():
    # segments 0-17 are "N-muted.mp4", 18-24 are plain: the same start as the VOD this was checked with
    assert eng.parse_muted_ranges(PLAYLIST_EXCERPT.read_text(encoding="utf-8")) == [(0.0, 180.0)]


def test_touching_muted_segments_are_merged_and_gaps_split_them():
    text = playlist(["0.mp4", "1-muted.mp4", "2-muted.mp4", "3.mp4", "4-muted.mp4"])
    assert eng.parse_muted_ranges(text) == [(10.0, 30.0), (40.0, 50.0)]


def test_nothing_muted_gives_an_empty_list():
    assert eng.parse_muted_ranges(playlist(["0.mp4", "1.mp4"])) == []


@pytest.mark.parametrize("name", ["5-muted.ts", "5-MUTED.mp4", "5-muted", "sub/dir/5-muted.mp4",
                                  "https://x.example/v/5-muted.mp4?token=abc"])
def test_name_variants_that_mean_muted(name):
    assert eng.parse_muted_ranges(playlist(["0.mp4", name])) == [(10.0, 20.0)]


@pytest.mark.parametrize("name", ["5.mp4", "muted.mp4", "5-muted-extra.mp4", "unmuted.mp4", "5_muted.mp4"])
def test_names_that_do_not_mean_muted(name):
    assert eng.parse_muted_ranges(playlist(["0.mp4", name])) == []


def test_unknown_tags_and_blank_lines_are_ignored_and_times_still_add_up():
    text = playlist(["0.mp4", "1-muted.mp4"], extra=["#EXT-X-TWITCH-TOTAL-SECS:20", "#EXT-X-DISCONTINUITY", ""])
    assert eng.parse_muted_ranges(text) == [(10.0, 20.0)]  # parse_hls_playlist would refuse the discontinuity


def test_ranges_are_cut_off_at_the_vod_length():
    text = playlist(["0.mp4", "1-muted.mp4", "2-muted.mp4"])
    assert eng.parse_muted_ranges(text, duration=25.0) == [(10.0, 25.0)]
    assert eng.parse_muted_ranges(text, duration=10.0) == []


def test_garbage_does_not_raise():
    assert eng.parse_muted_ranges("") == []
    assert eng.parse_muted_ranges("<html>nope</html>") == []
    assert eng.parse_muted_ranges("#EXTINF:abc,\n1-muted.mp4\n") == []


# --------------------------------------------------------------------------- finding and fetching the playlist
FORMATS = [
    {"format_id": "sb0", "format_note": "storyboard", "url": "https://x/sb.jpg"},
    {"format_id": "Audio_Only", "vcodec": "none", "url": "https://x/audio_only/index-muted-A.m3u8"},
    {"format_id": "360p", "vcodec": "avc1", "height": 360, "fps": 30.0, "tbr": 700, "url": "https://x/360p30/index-muted-A.m3u8"},
    {"format_id": "1080p60", "vcodec": "avc1", "height": 1080, "fps": 60.0, "tbr": 6000,
     "url": "https://x/chunked/index-muted-A.m3u8?sig=1"},
    {"format_id": "720p60", "vcodec": "avc1", "height": 720, "fps": 60.0, "tbr": 3500, "url": "https://x/720p60/index-muted-A.m3u8"},
]


def test_the_best_video_playlist_is_chosen_like_the_download_does():
    assert eng.pick_playlist_url(FORMATS) == "https://x/chunked/index-muted-A.m3u8?sig=1"


@pytest.mark.parametrize("formats", [None, [], "x", [None, 3], [{"url": "https://x/a.mp4"}],
                                     [{"vcodec": "none", "url": "https://x/a.m3u8"}]])
def test_no_usable_playlist_gives_none(formats):
    assert eng.pick_playlist_url(formats) is None


def fake_get(monkeypatch, text=None, error=None, seen=None):
    def get(url, **kw):
        if seen is not None:
            seen.append((url, kw))
        if error:
            raise error
        return SimpleNamespace(text=text, raise_for_status=lambda: None)

    monkeypatch.setattr(eng.requests, "get", get)


def test_fetching_reads_the_chosen_playlist(monkeypatch):
    seen = []
    fake_get(monkeypatch, playlist(["0.mp4", "1-muted.mp4"]), seen=seen)
    assert eng.fetch_muted_ranges(FORMATS, 100.0) == [(10.0, 20.0)]
    assert seen[0][0] == "https://x/chunked/index-muted-A.m3u8?sig=1" and seen[0][1]["timeout"] <= 20


def test_a_failed_request_means_unknown_not_an_error(monkeypatch):
    fake_get(monkeypatch, error=requests.ConnectionError("offline"))
    assert eng.fetch_muted_ranges(FORMATS, 100.0) is None


def test_no_playlist_means_unknown_and_no_request(monkeypatch):
    seen = []
    fake_get(monkeypatch, "", seen=seen)
    assert eng.fetch_muted_ranges([{"url": "https://x/a.mp4"}], 100.0) is None and not seen


def test_a_playlist_with_nothing_muted_is_known_to_be_empty(monkeypatch):
    fake_get(monkeypatch, playlist(["0.mp4", "1.mp4"]))
    assert eng.fetch_muted_ranges(FORMATS, 100.0) == []


def test_get_source_info_only_asks_for_twitch_vods(monkeypatch):
    import subprocess

    def run_with(info_url):
        raw = json.dumps({"id": "1", "title": "t", "duration": 60, "formats": FORMATS})
        monkeypatch.setattr(eng, "find_tool", lambda name: "yt-dlp")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=raw, stderr=""))
        return eng.get_source_info(info_url)

    seen = []
    fake_get(monkeypatch, playlist(["0.mp4", "1-muted.mp4"]), seen=seen)
    assert run_with("https://www.twitch.tv/videos/1").muted == [(10.0, 20.0)]
    seen.clear()
    assert run_with("https://example.com/watch/1").muted is None and not seen


def test_overlap_counts_only_the_seconds_inside():
    muted = [(10.0, 20.0), (50.0, 80.0)]
    assert eng.muted_overlap(muted, 0, 100) == 40
    assert eng.muted_overlap(muted, 15, 55) == 10
    assert eng.muted_overlap(muted, 20, 50) == 0
    assert eng.muted_overlap(None, 0, 100) == 0 and eng.muted_overlap([], 0, 100) == 0


# --------------------------------------------------------------------------- the .markers.json
def _sample_text() -> str:
    chapters = [
        Chapter(0, 50, "Just Chatting", kind="game"),
        Chapter(12, 30, eng.MUTED_TITLE, kind="muted"),
        Chapter(50, 70, "Resident Evil 2", kind="game"),
    ]
    src = eng.SourceInfo(url="https://www.twitch.tv/videos/1", id="1", title="Big stream", uploader="Streamer",
                         duration=26264.851, date="2026-01-01", twitch_vod_id="1")
    return premiere_markers_json("Streamer - 2026-01-01 - 1 - part1", chapters, 70.0, 29.97, src, 1200.0, 1270.0)


def test_a_muted_marker_has_its_kind_times_and_a_comment():
    muted = [m for m in json.loads(_sample_text())["markers"] if m["kind"] == "muted"]
    assert muted == [{"kind": "muted", "name": "Muted audio", "start": 12, "end": 30, "comment": eng.MUTED_COMMENT}]


def test_the_file_version_is_not_bumped_so_the_current_plugin_still_opens_it():
    assert json.loads(_sample_text())["version"] == 1 == eng.MARKERS_JSON_VERSION


def test_the_muted_sample_matches_what_the_app_writes():
    assert SAMPLE.read_text(encoding="utf-8") == _sample_text(), (
        "tests/fixtures/markers_sample_muted.json is out of date: run  python tests/test_muted_audio.py")


def test_the_shared_sample_the_plugin_tests_read_has_no_muted_marker():
    # the plugin team's tests read markers_sample.json and expect every marker to be understood: leave it alone
    assert '"muted"' not in (FIXTURES / "markers_sample.json").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- how run_job uses it
import test_premiere_plugin_json as pj  # noqa: E402  (its job harness: one part, 1200 s -> 1270 s of the VOD)


def run(monkeypatch, tmp_path, muted, **flags):
    """pj._run, but with the VOD's muted stretches set and the options given."""
    real_src = pj._src
    monkeypatch.setattr(pj, "_src", lambda segments=(): replace(real_src(segments), muted=muted))
    return pj._run(monkeypatch, tmp_path, **flags)


def muted_markers(dest):
    return [m for m in json.loads(pj._files(dest)[1].read_text(encoding="utf-8"))["markers"] if m["kind"] == "muted"]


MUTED_IN_VOD = [(1100.0, 1210.0), (1250.0, 1300.0), (2000.0, 2100.0)]  # two touch the part, one is far away


def test_muted_markers_are_relative_to_the_part_and_cut_at_its_edges(monkeypatch, tmp_path):
    dest, logs = run(monkeypatch, tmp_path, MUTED_IN_VOD, premiere_plugin=True, muted_markers=True)
    assert [(m["start"], m["end"]) for m in muted_markers(dest)] == [(0.0, 10.0), (50.0, 70.0)]
    assert any("2 muted markers" in m for m in logs) and any("Muted audio: 3 stretch" in m for m in logs)


def test_muted_markers_sit_in_time_order_with_the_others(monkeypatch, tmp_path):
    dest, _ = run(monkeypatch, tmp_path, MUTED_IN_VOD, premiere_plugin=True, muted_markers=True, game_markers=True)
    markers = json.loads(pj._files(dest)[1].read_text(encoding="utf-8"))["markers"]
    assert [m["start"] for m in markers] == sorted(m["start"] for m in markers)
    assert {m["kind"] for m in markers} == {"clip", "game", "muted"}


def test_muted_alone_is_enough_to_write_the_json(monkeypatch, tmp_path):
    # no clips and no games: only the muted stretch is there to mark (the same harness as pj.test_nothing_to_mark...)
    monkeypatch.setattr(eng, "find_tool", lambda n: "/bin/true")
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"x" * 5000)
    monkeypatch.setattr(eng, "download_section_aligned", lambda ctx, url, p, wd: (raw, 1200.0, 1270.0))
    monkeypatch.setattr(eng, "probe_video", lambda path: (29.97, 1920, 1080))
    monkeypatch.setattr(eng, "finalize_part", lambda ctx, f, stem, *a, **k: (stem.parent.mkdir(parents=True, exist_ok=True), stem.with_suffix(".mp4"))[1])
    opts = eng.JobOptions(cut_text="0:20:03 - 0:21:03", out_dir=str(tmp_path / "out"), strategy="sections",
                          premiere_plugin=True, muted_markers=True)
    src = replace(pj._src(), muted=[(1210.0, 1220.0)])
    (dest,) = eng.run_job(eng.Job(source=src, opts=opts, clips=[]), eng.Ctx(log=lambda m: None))
    assert [(m["start"], m["end"]) for m in muted_markers(dest)] == [(10.0, 20.0)]


def test_the_switch_off_means_no_muted_markers(monkeypatch, tmp_path):
    dest, logs = run(monkeypatch, tmp_path, MUTED_IN_VOD, premiere_plugin=True, muted_markers=False)
    assert muted_markers(dest) == [] and not any("Muted audio" in m for m in logs)


def test_muted_markers_need_the_plugin_file(monkeypatch, tmp_path):
    dest, _ = run(monkeypatch, tmp_path, MUTED_IN_VOD, premiere_xml=True, muted_markers=True)
    xml, js = pj._files(dest)
    assert not js.exists() and "Muted audio" not in xml.read_text(encoding="utf-8")  # the plain XML has no colors: left out


def test_no_muted_stretch_in_the_part_adds_nothing(monkeypatch, tmp_path):
    dest, _ = run(monkeypatch, tmp_path, [(5000.0, 5100.0)], premiere_plugin=True, muted_markers=True)
    assert muted_markers(dest) == []


def test_when_get_info_could_not_tell_the_job_tries_once_more(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "get_playlist_url", lambda ctx, url: "https://x/p.m3u8")
    monkeypatch.setattr(eng, "muted_from_playlist_url", lambda url, duration=None: [(1210.0, 1230.0)])
    dest, _ = run(monkeypatch, tmp_path, None, premiere_plugin=True, muted_markers=True)
    assert [(m["start"], m["end"]) for m in muted_markers(dest)] == [(10.0, 30.0)]


def test_when_it_still_cannot_tell_the_download_goes_on_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "get_playlist_url", lambda ctx, url: (_ for _ in ()).throw(eng.EngineError("no playlist")))
    dest, logs = run(monkeypatch, tmp_path, None, premiere_plugin=True, muted_markers=True)
    assert not pj._files(dest)[1].exists() or muted_markers(dest) == []
    assert any("could not read which parts Twitch silenced" in m for m in logs)


def test_the_option_is_off_by_default():
    assert eng.JobOptions(cut_text="", out_dir="x").muted_markers is False


# --------------------------------------------------------------------------- the Plan tab
tk = pytest.importorskip("tkinter")

import test_gui_plan_tab as plan_tab_tests  # noqa: E402
import test_gui_timeline as tl_tests  # noqa: E402
from ui import timeline as tlm  # noqa: E402
from ui.timeline import Timeline  # noqa: E402

gui = plan_tab_tests.gui


def red_bars(tl):
    return [i for i in tl.canvas.find_all() if tl.canvas.type(i) == "rectangle"
            and tl.canvas.itemcget(i, "fill") == tlm.MUTED_COLOUR]


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
    import luckytwitch_downloader as dl

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
    import luckytwitch_downloader as dl

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
    import luckytwitch_downloader as dl

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


if __name__ == "__main__":  # regenerate the muted sample
    SAMPLE.write_text(_sample_text(), encoding="utf-8")
    print("wrote", SAMPLE)
