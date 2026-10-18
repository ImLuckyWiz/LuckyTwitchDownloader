"""
Plan tab tests that drive the real Tk window.

They need Tk and a display. On a desktop they just open a (hidden) window; on a headless Linux box run
    xvfb-run -a python -m pytest
When Tk or a display is missing the whole module is skipped, it never fails.

Nothing here touches the network or your real settings: the tool download, the Twitch client, the
settings files and the message boxes are all replaced.
"""

import pytest

tk = pytest.importorskip("tkinter")

import luckytwitch_downloader as dl  # noqa: E402
import luckytwitch_engine as eng  # noqa: E402
from ui.plan_tab import PlanTabMixin  # noqa: E402

SOURCE = dict(url="https://www.twitch.tv/videos/123", id="v123", title="Big Stream", uploader="Streamer",
              duration=7200.0, date="2026-10-01", twitch_vod_id="123")


def make_clips():
    return [
        {"id": "a", "vod_offset": 630.4, "view_count": 500, "duration": 30, "title": "Epic fail \U0001F602",
         "creator_name": "viewer1", "url": "https://clips.twitch.tv/a"},
        {"id": "b", "vod_offset": 3612, "view_count": 10, "duration": 12, "title": "Small one",
         "creator_name": "viewer2", "url": "https://clips.twitch.tv/b"},
        {"id": "c", "vod_offset": None, "view_count": 99, "duration": 20, "title": "No offset",
         "creator_name": "viewer3", "url": "https://clips.twitch.tv/c"},
    ]


class Harness:
    """The running App plus helpers and the things we intercepted (message boxes, opened URLs)."""

    def __init__(self, app, root):
        self.app, self.root = app, root
        self.boxes: list[tuple[str, str, str]] = []
        self.opened: list[str] = []

    def set_cuts(self, text):
        self.app.cuts.delete("1.0", "end")
        self.app.cuts.insert("1.0", text)

    def cuts_text(self):
        return self.app.cuts.get("1.0", "end").strip()

    def preview(self):
        return self.app.preview.get("1.0", "end").rstrip("\n"), self.app.preview_kind

    def rows(self):
        return [list(self.app.tree.item(i, "values")) for i in self.app.tree.get_children()]

    def load_vod(self, **overrides):
        self.app.source = eng.SourceInfo(**{**SOURCE, **overrides})

    def load_clips(self):
        self.app.clips, self.app.clips_loaded = make_clips(), True
        self.app.refresh_clips()


@pytest.fixture()
def gui(tmp_path, monkeypatch):
    # isolate from the real machine
    monkeypatch.setattr(dl, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(dl, "RECENT_PATH", tmp_path / "recent.json")
    monkeypatch.setattr(dl, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(dl, "LINKS_DIR", tmp_path / "links")
    monkeypatch.setattr(dl, "BEAT_PATH", tmp_path / "running.beat")
    monkeypatch.setattr(dl, "ensure_tools", lambda *a, **k: None)
    monkeypatch.setattr(dl, "describe_tools", lambda: "stubbed tools")
    monkeypatch.setattr(dl, "make_client", lambda: None)
    try:
        root = tk.Tk()
    except tk.TclError as e:  # no display
        pytest.skip(f"no usable display for Tk: {e}")
    root.withdraw()
    dl.apply_dark_theme(root)
    app = dl.App(root)
    root.update()
    h = Harness(app, root)
    monkeypatch.setattr(dl.webbrowser, "open", lambda url, *a, **k: h.opened.append(url))
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(dl.messagebox, name, lambda title, msg, _n=name, **k: h.boxes.append((_n, title, msg)))
    yield h
    for after_id in root.tk.call("after", "info"):  # the app polls every 100 ms: stop that before closing
        root.after_cancel(after_id)
    root.destroy()


# --------------------------------------------------------------------------- structure
def test_app_uses_the_plan_tab_mixin(gui):
    assert isinstance(gui.app, PlanTabMixin)
    for name in ("build_plan_tab", "set_preview", "update_preview", "refresh_clips", "open_clip", "split_at_clip"):
        # the App must not shadow them: they live only in ui/plan_tab.py
        assert getattr(dl.App, name) is getattr(PlanTabMixin, name)


def test_tabs_are_in_the_expected_order(gui):
    titles = [gui.app.notebook.tab(t, "text").strip() for t in gui.app.notebook.tabs()]
    assert titles == ["Search", "Plan", "Options", "Queue & log"]


def test_plan_tab_has_its_widgets(gui):
    app = gui.app
    assert app.cuts.winfo_class() == "Text"
    assert app.preview.winfo_class() == "Text"
    assert tuple(app.tree["columns"]) == ("at", "views", "dur", "title", "creator", "chap")
    button_texts = set()

    def walk(w):
        for c in w.winfo_children():
            if c.winfo_class() == "TButton":
                button_texts.add(c.cget("text"))
            walk(c)

    walk(app.tab_plan.body)
    walk(app.tab_plan.footer)  # «Add to queue» / «Add & start» sit in the bar that stays visible
    assert {"Split at selected clip", "Download only selected clip", "Add to queue", "Add & start"} <= button_texts


# --------------------------------------------------------------------------- preview
def test_preview_empty_hint(gui):
    gui.app.update_preview()
    assert gui.preview() == ("Write the cut points above (press «Get info» first so «end» works).", "muted")


def test_preview_end_needs_get_info(gui):
    gui.set_cuts("0:00 - end")
    gui.app.update_preview()
    assert gui.preview() == ("⚠ «end» needs the VOD length: press «Get info» first.", "err")


def test_preview_lists_the_parts(gui):
    gui.load_vod()
    gui.set_cuts("0:00 - 30:00 - 1:30:00 - end")
    gui.app.update_preview()
    text, kind = gui.preview()
    assert kind == "ok"
    assert text == (
        "Part 1:  0:00:00 → 0:30:00   (0:30:00)\n"
        "Part 2:  0:30:00 → 1:30:00   (1:00:00)\n"
        "Part 3:  1:30:00 → 2:00:00   (0:30:00)\n"
        "→ download the full VOD once, then split it   (parts cover 100% of the VOD)"
    )


def test_preview_picks_sections_for_small_coverage(gui):
    gui.load_vod()
    gui.set_cuts("0:00 - 5:00")
    gui.app.update_preview()
    text, kind = gui.preview()
    assert kind == "ok"
    assert text.endswith("→ download only these parts   (parts cover 4% of the VOD)")


def test_preview_follows_the_strategy_option(gui):
    gui.load_vod()
    gui.set_cuts("0:00 - 30:00 - end")
    gui.app.vars["strategy"].set("Download only the parts")
    gui.app.update_preview()
    assert "download only these parts" in gui.preview()[0]
    gui.app.vars["strategy"].set("Download full VOD, then split")
    gui.app.update_preview()
    assert "download the full VOD once" in gui.preview()[0]


@pytest.mark.parametrize(
    "text, message",
    [
        ("30:00 - 10:00", "⚠ Cut points must increase: 0:30:00 → 0:10:00."),
        ("0:00 - 30:00 ; 20:00 - 40:00", "⚠ Parts overlap: 0:00:00–0:30:00 and 0:20:00–0:40:00."),
        ("0:00 - 3:00:00", "⚠ 3:00:00 is beyond the end of the VOD (2:00:00)."),
        ("30:00", "⚠ «30:00»: a group needs at least two points (use 0 and end)."),
        ("banana - 10:00", "⚠ Invalid time: «banana». Use H:MM:SS, MM:SS, seconds or 1h30m."),
    ],
)
def test_preview_shows_errors(gui, text, message):
    gui.load_vod()
    gui.set_cuts(text)
    gui.app.update_preview()
    assert gui.preview() == (message, "err")


def test_typing_in_the_box_updates_the_preview(gui):
    gui.load_vod()
    gui.set_cuts("0:00 - 10:00")
    # key events only reach a window that has focus, so this one test shows the window
    gui.root.deiconify()
    gui.root.update()
    gui.app.cuts.focus_force()
    gui.root.update()
    if gui.root.focus_get() is not gui.app.cuts:
        pytest.skip("this environment does not give the window keyboard focus")
    gui.app.cuts.event_generate("<KeyRelease>")  # what typing does
    gui.root.update()
    assert gui.preview()[0].startswith("Part 1:  0:00:00 → 0:10:00")


def test_build_options_reads_the_cut_text_from_the_tab(gui):
    gui.set_cuts("  0:00 - 10:00 - end  \n")
    assert gui.app.build_options().cut_text == "0:00 - 10:00 - end"


# --------------------------------------------------------------------------- clips table
def test_clips_table_rows_and_label(gui):
    gui.load_clips()
    assert gui.rows() == [
        ["0:10:00", "500", "30s", "Epic fail ", "viewer1", "✓"],  # emoji stripped from the title
        ["1:00:00", "10", "12s", "Small one", "viewer2", "✓"],
        ["-", "99", "20s", "No offset", "viewer3", "?"],
    ]
    assert gui.app.clips_lbl.get() == (
        "2 of 3 clips pass the filter → 2 chapters  (1 can't be placed: no offset)  [chapters are OFF]"
    )


def test_clips_table_follows_the_filter_and_chapters_switch(gui):
    gui.load_clips()
    gui.app.vars["chapters"].set(True)
    gui.app.vars["min_views"].set("100")
    gui.app.refresh_clips()
    assert [r[5] for r in gui.rows()] == ["✓", "—", "?"]
    assert gui.app.clips_lbl.get() == "1 of 3 clips pass the filter → 1 chapters  (1 can't be placed: no offset)"


def test_clips_table_empty_messages(gui):
    gui.app.clips, gui.app.clips_loaded = [], False
    gui.app.refresh_clips()
    assert gui.rows() == []
    assert gui.app.clips_lbl.get() == "No clips loaded (sign in with the Twitch API… button, optional)."
    gui.app.clips_loaded = True
    gui.app.refresh_clips()
    assert gui.app.clips_lbl.get() == "This VOD has no clips."


def test_double_click_target_opens_the_clip_url(gui):
    gui.load_clips()
    gui.app.tree.selection_set("1")
    gui.app.open_clip(None)
    assert gui.opened == ["https://clips.twitch.tv/b"]


# --------------------------------------------------------------------------- split at clip
def test_split_needs_a_selection(gui):
    gui.load_clips()
    gui.app.split_at_clip()
    assert gui.boxes == [("showinfo", "Select a clip", "Select a clip in the table first.")]


def test_split_needs_exactly_one_clip(gui):
    gui.load_clips()
    gui.app.tree.selection_set("0", "1")
    gui.app.split_at_clip()
    assert gui.boxes == [("showinfo", "Select one clip", "Splitting works with a single clip: select just one.")]


def test_split_needs_a_loaded_vod(gui):
    gui.load_clips()
    gui.app.source = None
    gui.app.tree.selection_set("0")
    gui.app.split_at_clip()
    assert gui.boxes == [("showinfo", "No VOD", "Press «Get info» first.")]


def test_split_needs_a_clip_with_a_position(gui):
    gui.load_vod()
    gui.load_clips()
    gui.app.tree.selection_set("2")
    gui.app.split_at_clip()
    assert gui.boxes == [("showinfo", "No offset", "That clip has no position in the VOD.")]


def test_split_inserts_a_cut_point_before_the_clip_and_refreshes_the_preview(gui):
    gui.load_vod()
    gui.load_clips()
    gui.set_cuts("0:00:00 - end")
    gui.app.tree.selection_set("1")  # clip at 1:00:00, default lead-in 3 s
    gui.app.split_at_clip()
    assert gui.boxes == []
    assert gui.cuts_text() == "0:00:00 - 0:59:57 - end"
    assert gui.preview()[0].startswith("Part 1:  0:00:00 → 0:59:57   (0:59:57)\nPart 2:  0:59:57 → 2:00:00")


def test_split_with_empty_text_starts_from_the_whole_vod(gui):
    gui.load_vod()
    gui.load_clips()
    gui.set_cuts("")
    gui.app.tree.selection_set("1")
    gui.app.split_at_clip()
    assert gui.cuts_text() == "0:00:00 - 0:59:57 - end"


def test_split_outside_every_part_explains_why(gui):
    gui.load_vod()
    gui.load_clips()
    gui.set_cuts("0:00:00 - 0:10:00")
    gui.app.tree.selection_set("1")
    gui.app.split_at_clip()
    assert gui.boxes == [("showinfo", "Can't split here", "That moment is not inside any of your parts.")]
    assert gui.cuts_text() == "0:00:00 - 0:10:00"  # untouched


def test_split_respects_the_lead_in_setting(gui):
    gui.load_vod()
    gui.load_clips()
    gui.set_cuts("0:00:00 - end")
    gui.app.vars["pad_before"].set("10")
    gui.app.tree.selection_set("1")
    gui.app.split_at_clip()
    assert gui.cuts_text() == "0:00:00 - 0:59:50 - end"


def test_splitting_twice_at_the_same_clip_keeps_a_valid_plan(gui):
    gui.load_vod()
    gui.load_clips()
    gui.set_cuts("0:00:00 - end")
    gui.app.tree.selection_set("1")
    gui.app.split_at_clip()
    once = gui.cuts_text()
    gui.app.split_at_clip()
    assert gui.cuts_text() == once  # the second split did not write a duplicate boundary
    assert gui.preview()[1] == "ok"


# --------------------------------------------------------------------------- wiring with the rest of the app
def test_get_info_result_fills_the_plan_tab(gui):
    info = eng.SourceInfo(url="https://www.twitch.tv/videos/9", id="v9", title="Other", uploader="Someone",
                          duration=3600.0, date="2026-09-09", twitch_vod_id="9")
    gui.app.on_info_ok(info, make_clips()[:2], True, "")
    assert gui.app.info_var.get() == "Someone · Other · 1:00:00 · 2026-09-09 · 2 clips"
    assert gui.cuts_text() == "0:00:00 - end"
    assert gui.preview()[0].startswith("Part 1:  0:00:00 → 1:00:00   (1:00:00)")
    assert len(gui.rows()) == 2


def test_get_info_keeps_cut_points_the_user_already_typed(gui):
    gui.set_cuts("0:00 - 10:00")
    info = eng.SourceInfo(**{**SOURCE, "duration": 3600.0})
    gui.app.on_info_ok(info, [], True, "")
    assert gui.cuts_text() == "0:00 - 10:00"


def test_download_selected_clips_queues_one_job_per_clip(gui):
    gui.load_vod(duration=3600.0)
    gui.load_clips()
    gui.set_cuts("0:00 - end")
    gui.app.items.clear()
    gui.app.tree.selection_set("0", "1")
    gui.app.download_clips()
    jobs = [(it["job"].opts.cut_text, it["job"].opts.strategy) for it in gui.app.items]
    assert jobs == [("0:09:57 - 0:10:34", "sections"), ("0:59:57 - 1:00:00", "sections")]
