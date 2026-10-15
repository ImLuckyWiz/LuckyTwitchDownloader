"""Options tab (sidebar + sections): the layout, that every setting is still wired to the same variable,
the Advanced areas, the {token} chips and the live file-name examples.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
"""

import time

import pytest

tk = pytest.importorskip("tkinter")

import luckytwitch_downloader as dl  # noqa: E402
import luckytwitch_engine as eng  # noqa: E402
from test_gui_plan_tab import SOURCE, gui  # noqa: E402,F401  (the fixture that opens the real window)
from ui.options_tab import SECTIONS, OptionsTabMixin  # noqa: E402
from ui.widgets import Collapsible, SideNav, Toggle  # noqa: E402

# every setting the old Options tab had, and the Plan-tab ones the sections must not touch
OPTIONS_VARS = {
    "out_dir", "container", "threads", "strategy", "threshold", "name_template", "subfolders", "folder_template",
    "exact", "keep_full", "title_tpl", "pad_after", "gap_title", "sidecar", "premiere_xml", "premiere_plugin",
    "game_markers", "clip_name_template", "clip_pad_before", "clip_pad_after", "chat", "chat_format",
    "chat_embed", "auto_update",
}


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def visible_sections(app):
    return [k for k, f in app._opt_sections.items() if f.winfo_manager()]


def settle(gui, seconds=0.15):
    """Let the switch animation finish (the fixture cancels pending timers when it closes the window)."""
    end = time.time() + seconds
    while time.time() < end:
        gui.root.update()
        time.sleep(0.01)


def entry_for(app, name):
    """The text field bound to the setting `name`."""
    for w in walk(app.tab_options):
        if w.winfo_class() == "TEntry" and str(w.cget("textvariable")) == str(app.vars[name]):
            return w
    raise AssertionError(f"no text field for {name}")


def chip(entry, token):
    return next(b for b in entry._lt_chips.chips if b.cget("text") == "{" + token + "}")


def section_widgets(app, key, cls):
    return [w for w in walk(app._opt_sections[key]) if isinstance(w, cls)]


def advanced(app, key):
    return section_widgets(app, key, Collapsible)[0]


# --------------------------------------------------------------------------- structure
def test_app_uses_the_options_tab_mixin_and_the_sidebar(gui):
    app = gui.app
    assert isinstance(app, OptionsTabMixin)
    assert isinstance(app.options_nav, SideNav)
    assert [k for k, _ in SECTIONS] == ["output", "cuts", "chapters", "premiere", "chat", "clips", "tools"]
    assert set(app.options_nav.buttons) == set(app._opt_sections)


def test_only_one_section_is_visible_at_a_time(gui):
    app = gui.app
    assert visible_sections(app) == ["output"]  # starts on Output
    for key, _ in SECTIONS:
        app.options_nav.select(key)
        gui.root.update()
        assert visible_sections(app) == [key]
        assert app.options_nav.current == key
        assert str(app.options_nav.buttons[key].cget("style")) == "NavSel.TButton"
        others = [b for k, b in app.options_nav.buttons.items() if k != key]
        assert all(str(b.cget("style")) == "Nav.TButton" for b in others)


def test_switching_sections_scrolls_back_to_the_top(gui):
    app = gui.app
    app.options_scroll.canvas.yview_moveto(0.5)
    app.options_nav.select("cuts")
    gui.root.update()
    assert app.options_scroll.canvas.yview()[0] == 0


def test_arrow_keys_move_through_the_sidebar(gui):
    nav = gui.app.options_nav
    for b in nav.buttons.values():
        assert b.bind("<Down>") and b.bind("<Up>")
    nav._step("output", 1)  # what the Down key does on the first entry
    assert nav.current == "cuts"
    nav._step("cuts", -1)
    assert nav.current == "output"
    nav._step("output", -1)  # nothing above the first entry
    assert nav.current == "output"
    nav._step("tools", 1)  # nothing below the last one
    assert nav.current == "output"


def test_every_old_setting_still_has_its_variable_and_a_control(gui):
    app = gui.app
    assert OPTIONS_VARS <= set(app.vars)
    bound = set()
    for w in walk(app.tab_options):
        if isinstance(w, Toggle):
            bound.add(str(w.variable))
        else:
            try:
                bound.add(str(w.cget("textvariable")))
            except (tk.TclError, AttributeError):
                pass
    for name in OPTIONS_VARS:
        assert str(app.vars[name]) in bound, f"no control is bound to {name}"
    assert app.tools_info is not None and app.update_btn is not None


def test_booleans_are_switches_not_checkboxes(gui):
    app = gui.app
    assert not [w for w in walk(app.tab_options) if isinstance(w, tk.Widget) and w.winfo_class() == "TCheckbutton"]
    switches = {str(w.variable) for w in walk(app.tab_options) if isinstance(w, Toggle)}
    for name in ("exact", "keep_full", "subfolders", "premiere_plugin", "game_markers", "premiere_xml", "sidecar",
                 "chat", "chat_embed", "auto_update"):
        assert str(app.vars[name]) in switches, name


def test_the_chapters_switch_stays_in_the_plan_tab(gui):
    app = gui.app
    plan_vars = {str(w.variable) for w in walk(app.tab_plan) if isinstance(w, Toggle)}
    assert str(app.vars["chapters"]) in plan_vars
    assert not [w for w in walk(app.tab_plan) if w.winfo_class() == "TCheckbutton"]  # no checkbox left in Plan


# --------------------------------------------------------------------------- the approved split
UP_FRONT = {
    "output": {"out_dir", "container"},
    "cuts": {"strategy", "exact", "keep_full"},
    "premiere": {"premiere_plugin", "game_markers"},
    "chat": {"chat"},
}
IN_ADVANCED = {
    "output": {"threads", "name_template", "subfolders", "folder_template"},
    "cuts": {"threshold"},
    "premiere": {"premiere_xml", "sidecar"},
    "chat": {"chat_format", "chat_embed"},
}


def names_under(app, widget):
    inside = {id(w) for w in walk(widget)}
    out = set()
    for name, var in app.vars.items():
        for w in walk(app.tab_options):
            if id(w) not in inside:
                continue
            tv = getattr(w, "variable", None)
            try:
                tv = tv or w.cget("textvariable")
            except (tk.TclError, AttributeError):
                pass
            if tv is not None and str(tv) == str(var):
                out.add(name)
    return out


@pytest.mark.parametrize("key", list(UP_FRONT))
def test_up_front_and_advanced_settings_are_split_as_agreed(gui, key):
    app = gui.app
    adv = advanced(app, key)
    in_adv = names_under(app, adv)
    section = names_under(app, app._opt_sections[key])
    assert IN_ADVANCED[key] <= in_adv
    assert UP_FRONT[key] <= section - in_adv  # visible without opening Advanced


def test_chapters_clips_and_tools_have_no_advanced_area(gui):
    app = gui.app
    for key in ("chapters", "clips", "tools"):
        assert not section_widgets(app, key, Collapsible)


def test_advanced_starts_collapsed_and_opens_on_click(gui):
    app = gui.app
    app.options_nav.select("output")
    gui.root.update()
    adv = advanced(app, "output")
    assert not adv.opened and not adv.body.winfo_ismapped()
    assert "\u25b8" in adv.header.cget("text")
    adv.header.invoke()
    gui.root.update()
    assert adv.opened and adv.body.winfo_ismapped()
    assert "\u25be" in adv.header.cget("text")
    adv.header.invoke()
    gui.root.update()
    assert not adv.body.winfo_ismapped()


def test_a_value_inside_a_collapsed_advanced_area_is_still_used(gui):
    app = gui.app
    app.vars["threads"].set("12")
    app.vars["threshold"].set("75")
    app.vars["chat_format"].set("txt")
    app.cuts.insert("1.0", "0:00 - 0:10")
    opts = app.build_options()
    assert (opts.threads, opts.full_threshold, opts.chat_format) == (12, 0.75, "txt")


# --------------------------------------------------------------------------- switches
def test_a_switch_changes_the_setting_and_saves(gui, tmp_path):
    app = gui.app
    app.options_nav.select("cuts")
    gui.root.update()
    sw = next(w for w in section_widgets(app, "cuts", Toggle) if w.variable is app.vars["exact"])
    assert app.build_options().exact is False
    sw._click()
    settle(gui)
    assert app.vars["exact"].get() is True
    app.cuts.insert("1.0", "0:00 - 0:10")
    assert app.build_options().exact is True
    app.save_settings()
    assert '"exact": true' in (tmp_path / "settings.json").read_text()


def test_the_markers_switches_refresh_the_clips_like_the_checkboxes_did(gui):
    app = gui.app
    for name in ("premiere_plugin", "premiere_xml"):
        sw = next(w for w in section_widgets(app, "premiere", Toggle) if w.variable is app.vars[name])
        assert sw.command == app.refresh_clips, name
        sw._click()  # must run without raising
    settle(gui)
    assert app.vars["premiere_plugin"].get() is True and app.vars["premiere_xml"].get() is True


# --------------------------------------------------------------------------- chips and live examples
def test_clicking_a_chip_inserts_the_token_at_the_cursor(gui):
    app = gui.app
    entry = entry_for(app, "name_template")
    app.vars["name_template"].set("A - B")
    entry.icursor(4)  # between «A - » and «B»
    chip(entry, "title").invoke()
    assert app.vars["name_template"].get() == "A - {title}B"
    assert entry.index("insert") == len("A - {title}") or entry.index("insert") == 4  # cursor stays usable


def test_a_chip_replaces_the_selected_text(gui):
    app = gui.app
    entry = entry_for(app, "folder_template")
    app.vars["folder_template"].set("xxx - {id}")
    entry.selection_range(0, 3)
    chip(entry, "date").invoke()
    assert app.vars["folder_template"].get() == "{date} - {id}"


def test_every_template_field_has_chips_for_its_tokens(gui):
    app = gui.app
    expected = {
        "name_template": {"streamer", "date", "id", "title", "n", "total", "start", "end"},
        "folder_template": {"streamer", "date", "id", "title"},
        "title_tpl": {"title", "creator", "views", "duration"},
        "clip_name_template": {"clip_title", "creator", "views", "clip_id", "clip_duration",
                               "streamer", "date", "id", "title", "start", "end"},
    }
    for name, tokens in expected.items():
        got = {b.cget("text").strip("{}") for b in entry_for(app, name)._lt_chips.chips}
        assert got == tokens, name


def test_examples_use_a_sample_vod_until_one_is_loaded_then_the_real_one(gui):
    app = gui.app
    assert app._example_file_name() == "Streamer - 2026-10-01 - 123 - part1.mp4"
    assert app._example_folder_name() == "Streamer/2026-10-01 - Big Stream - 123"
    gui.load_vod(uploader="Zed", title="Late night", date="2026-12-24", twitch_vod_id="999")
    app.refresh_name_examples()
    assert app._example_file_name() == "Zed - 2026-12-24 - 999 - part1.mp4"
    assert app._example_folder_name() == "Zed/2026-12-24 - Late night - 999"


def example_text(app, key, startswith=""):
    labels = [w for w in walk(app._opt_sections[key]) if w.winfo_class() == "TLabel"
              and str(w.cget("text")).startswith("Example:")]
    return [str(w.cget("text")) for w in labels]


def test_the_example_line_follows_the_template_as_you_type(gui):
    app = gui.app
    app.options_nav.select("output")
    app.vars["name_template"].set("{n} of {total} - {title}")
    gui.root.update()
    assert "Example:  1 of 3 - Big Stream.mp4" in example_text(app, "output")
    app.vars["container"].set("mkv")
    gui.root.update()
    assert "Example:  1 of 3 - Big Stream.mkv" in example_text(app, "output")


def test_a_half_typed_template_never_breaks_the_example(gui):
    app = gui.app
    for bad in ("{", "{title", "{0}", "}{", ""):
        app.vars["name_template"].set(bad)
        app.vars["clip_name_template"].set(bad)
        app.vars["title_tpl"].set(bad)
        gui.root.update()
    assert example_text(app, "output") and example_text(app, "clips") and example_text(app, "chapters")


def test_the_example_matches_what_the_engine_really_names_the_file(gui):
    app = gui.app
    app.vars["name_template"].set("{streamer}_{start}-{end}")
    src = eng.SourceInfo(**SOURCE)
    opts = eng.JobOptions(cut_text="", out_dir="OUT", name_template="{streamer}_{start}-{end}")
    expect = eng.part_stem(src, opts, eng.Part(1, 0, 3600), 3) + ".mp4"
    assert app._example_file_name() == expect


def test_clip_and_chapter_examples(gui):
    app = gui.app
    app.vars["clip_name_template"].set("{clip_title} by {creator} ({views})")
    assert app._example_clip_name() == "Epic fail by viewer1 (500).mp4"
    assert app._example_chapter() == "Epic fail (viewer1, 500 views)"
    app.vars["title_tpl"].set("{title} - {nope}")
    assert app._example_chapter() == "Epic fail - {nope}"


def test_turning_subfolders_off_greys_out_the_stream_folder_field(gui):
    app = gui.app
    assert "disabled" not in app.folder_entry.state()
    app.vars["subfolders"].set(False)
    gui.root.update()
    assert "disabled" in app.folder_entry.state()
    assert all("disabled" in b.state() for b in app.folder_entry._lt_chips.chips)
    before = app.vars["folder_template"].get()
    app.folder_entry._lt_chips.insert("id")  # a disabled field ignores chip clicks
    assert app.vars["folder_template"].get() == before
    app.vars["subfolders"].set(True)
    gui.root.update()
    assert "disabled" not in app.folder_entry.state()
    assert all("disabled" not in b.state() for b in app.folder_entry._lt_chips.chips)
    settle(gui)


# --------------------------------------------------------------------------- tools section keeps working
def test_tools_status_is_still_driven_by_the_apps_message_loop(gui):
    app = gui.app
    app.q.put(("tools_info", "yt-dlp 2026.01.01 and ffmpeg OK"))
    app.poll_queue()
    assert app.tools_info.get() == "yt-dlp 2026.01.01 and ffmpeg OK"
    app.update_btn.config(state="disabled")
    assert str(app.update_btn.cget("state")) == "disabled"


def test_the_scroll_frame_is_still_importable_from_the_main_module():
    assert dl.ScrollFrame.__module__ == "ui.widgets"


def test_opening_advanced_makes_the_page_scroll_to_the_new_content(gui):
    app = gui.app
    gui.root.geometry("1020x400")
    gui.root.deiconify()  # the fixture's window is withdrawn: nothing is laid out (no scroll area) until it is shown
    app.notebook.select(app.tab_options)
    app.options_nav.select("output")
    gui.root.update()
    scroll, adv = app.options_scroll, advanced(app, "output")
    region_before = int(float(scroll.canvas.cget("scrollregion").split()[3]))
    adv.header.invoke()
    gui.root.update()
    region_after = int(float(scroll.canvas.cget("scrollregion").split()[3]))
    assert region_after > region_before  # a taller page than the window: it can now be scrolled
    assert region_after >= scroll.body.winfo_reqheight()
