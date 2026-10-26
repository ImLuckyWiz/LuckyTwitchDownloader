"""core/ is a COPY of helpers that live in luckytwitch_downloader.py. These tests check the copy still behaves
exactly like the original, and that a settings file written by the real tkinter App loads in core/.

Needs tkinter (the main module imports it) and, for the last test, a display (xvfb-run -a). Skipped otherwise.
Remove this file at cutover, together with the tkinter app.
"""

import json

import pytest

tk = pytest.importorskip("tkinter")

import luckytwitch_downloader as dl  # noqa: E402
from core import config, palette, paths, recent, settings, status  # noqa: E402
from test_gui_plan_tab import gui  # noqa: E402,F401  (the fixture that opens the real tkinter window)
from ui import common  # noqa: E402

STATUSES = ["", "queued", "running…", "running", "done (3 files)", "failed", "cancelled", "weird words", "  done", "x:"]
MESSAGES = [
    "", "ERROR: x", "Warning: y", "Could not z", "Cancelled.", "Server busy", "it failed", "skipped part", "ffmpeg not found",
    "✔ ok", "all is up to date.", "tool installed.", "Queued: a", "plain text", "  ERROR indented",
]


def test_defaults_are_identical():
    assert settings.DEFAULTS == dl.DEFAULTS
    assert list(settings.DEFAULTS) == list(dl.DEFAULTS)  # same order too


def test_paths_are_identical():
    assert paths.FROZEN == dl.FROZEN and paths.DATA_DIR == dl.DATA_DIR
    for name in ("CONFIG_PATH", "SETTINGS_PATH", "RECENT_PATH", "LINKS_DIR", "BEAT_PATH", "MAX_RECENT"):
        assert getattr(paths, name) == getattr(dl, name), name


def test_palette_and_fonts_are_identical():
    for name, value in palette.TOKENS.items():
        assert getattr(common, name) == value, name
    assert (palette.UI_FONT, palette.MONO_FONT) == (common.UI_FONT, common.MONO_FONT)
    assert palette.WHITE == common.WHITE


def test_status_and_log_helpers_give_the_same_answers():
    for s in STATUSES:
        assert status.status_word(s) == dl.status_word(s), s
        assert status.status_label(s) == dl.status_label(s), s
    for m in MESSAGES:
        assert status.log_kind(m) == dl.log_kind(m), m
    for group in ([], STATUSES, ["done", "done", "failed"], ["running…", "queued"]):
        assert status.queue_summary(group) == dl.queue_summary(group)
    assert status.STATUS_ICONS == dl.STATUS_ICONS and status.STATUS_COLOURS == dl.STATUS_COLOURS
    assert status.FINISHED == dl.FINISHED


def test_resource_path_is_identical():
    from core.resources import resource_path

    assert resource_path("assets", "icon.png") == common.resource_path("assets", "icon.png")


def test_config_recent_and_settings_behave_like_the_original(tmp_path, monkeypatch):
    """The same files in, the same answers out, for the same temp folder seen by both implementations."""
    for mod in (paths, dl):
        monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "config.json")
        monkeypatch.setattr(mod, "SETTINGS_PATH", tmp_path / "settings.json")
        monkeypatch.setattr(mod, "RECENT_PATH", tmp_path / "recent.json")
    # nothing on disk yet
    assert settings.load_settings() == dl.load_settings()
    assert recent.load_recent() == dl.load_recent() == []
    assert config.read_config() == dl._read_config() == {}
    assert config.make_client() is None and dl.make_client() is None
    # files with odd content
    (tmp_path / "settings.json").write_text(json.dumps({"threads": "3", "bogus": 1, "exact": True}), encoding="utf-8")
    assert settings.load_settings() == dl.load_settings()
    (tmp_path / "recent.json").write_text(json.dumps(
        [{"id": 1, "login": "a"}, {"id": "2"}, {"nope": 1}, "x"] + [{"id": str(i)} for i in range(20)]), encoding="utf-8")
    assert recent.load_recent() == dl.load_recent()
    # credentials written by one are read by the other
    config.save_credentials("cid", "sec")
    assert dl.load_credentials() == config.load_credentials()
    dl.save_login_tokens("a1", "r1")
    assert config.read_config() == dl._read_config()
    config.clear_credentials()
    assert dl.load_credentials() is None
    client_new, client_old = config.make_client(), dl.make_client()
    assert (client_new.client_id, client_new.token, client_new.user_refresh) == \
        (client_old.client_id, client_old.token, client_old.user_refresh)


def test_the_real_tkinter_app_writes_a_settings_file_that_core_reads(gui, monkeypatch):  # noqa: F811
    """Live check: the running App saves its variables, core/ loads that very file (the gui fixture points both
    modules at the same temp settings file)."""
    app = gui.app
    changed = {"threads": "3", "exact": True, "name_template": "{streamer} x {n}", "auto_update": False,
               "chat_render_mode": "Black background · H.264 (.mp4, smallest)", "gap_title": "Charla ñandú"}
    for k, v in changed.items():
        app.vars[k].set(v)
    app.save_settings()
    assert dl.SETTINGS_PATH.is_file()
    monkeypatch.setattr(paths, "SETTINGS_PATH", dl.SETTINGS_PATH)  # the fixture only redirected the main module
    loaded = settings.load_settings()
    assert loaded == dl.load_settings()
    assert all(loaded[k] == v for k, v in changed.items())
    assert set(loaded) == set(settings.DEFAULTS)


# --------------------------------------------------------------------------- Phase 5: the golden test
# The strongest parity check of the project: for each settings fixture the real tkinter App builds its JobOptions
# from its variables, core.options builds them from the same values in a plain dict, and the two must be EQUAL.
# (Not covered, on purpose: text like "1e999". tkinter's App.num lets the OverflowError of int(inf) escape, core.options
# gives the fallback instead; see MIGRATION_LOG no. 13.)
ALL_ON = {k: True for k, v in settings.DEFAULTS.items() if isinstance(v, bool)}
GOLDEN = {
    "defaults": {},
    "everything_on": {**ALL_ON, "subfolders": True},
    "everything_off": {k: False for k in ALL_ON},
    "changed_values": {
        "out_dir": "D:/Videos/Out", "container": "mkv", "strategy": "Download full VOD, then split",
        "threshold": "75", "threads": "12", "name_template": "{streamer}_{n}of{total}", "exact": True,
        "chapters": True, "min_views": "10", "min_duration": "5.5", "top_n": "3", "pad_before": "4", "pad_after": "2",
        "title_tpl": "{title} by {creator}", "gap_title": "Charla ñandú", "chat": True, "chat_format": "html",
        "chat_embed": True, "chat_render": True, "chat_render_mode": "Transparent · ProRes 4444 (.mov, very big)",
        "chat_render_look": "Dark see-through panel", "chat_render_width": "500", "chat_render_height": "1080",
        "chat_render_font_size": "24", "chat_render_fps": "60", "chat_render_smooth": True,
        "folder_template": "{streamer}-{id}", "clip_name_template": "{clip_title}-{creator}"},
    "only_parts": {"strategy": "Download only the parts", "chat_render_mode": "Black background · H.264 (.mp4, smallest)",
                   "chat_render_fps": "30"},
    "numbers_that_are_not_numbers": {k: "abc" for k in (
        "threshold", "threads", "min_views", "min_duration", "top_n", "pad_before", "pad_after", "chat_render_width",
        "chat_render_height", "chat_render_font_size")},
    "empty_numbers": {k: "" for k in (
        "threshold", "threads", "min_views", "min_duration", "top_n", "pad_before", "pad_after", "chat_render_width",
        "chat_render_height", "chat_render_font_size")},
    "odd_numbers": {"threshold": "0", "threads": "0", "min_views": "-3", "pad_before": "-1", "top_n": "2.9",
                    "chat_render_width": "7.5", "chat_render_font_size": " 20 ", "chat_render_height": "nan"},
    "huge_and_tiny": {"threshold": "500", "threads": "-4", "pad_after": "99999", "chat_render_width": "100000"},
    "empty_texts": {"out_dir": "   ", "name_template": "  ", "folder_template": "", "clip_name_template": " ",
                    "title_tpl": "", "gap_title": "   "},
    "words_the_lists_do_not_have": {"strategy": "???", "chat_format": "docx", "chat_render_mode": "???",
                                    "chat_render_look": "???", "chat_render_fps": "45", "container": "avi"},
    "padded_texts": {"out_dir": "  C:/x  ", "name_template": "  {n}  ", "gap_title": "  Gap  ", "title_tpl": "  {title}  "},
}


@pytest.mark.parametrize("name", list(GOLDEN))
@pytest.mark.parametrize("cut_text", ["", "  0:00 - 0:10\n1:00:00 - 1:10:00  \n"])
def test_the_qt_build_options_equal_the_tkinter_ones(gui, name, cut_text):  # noqa: F811
    from core import options

    app = gui.app
    values = {**settings.DEFAULTS, **GOLDEN[name]}
    for key, value in values.items():
        app.vars[key].set(value)
    app.cuts.delete("1.0", "end")
    app.cuts.insert("1.0", cut_text)
    old = app.build_options()
    new = options.build_options(dict(values), cut_text)
    assert new == old, name
    assert options.build_filter(dict(values)) == app.build_filter(), name


def test_every_golden_fixture_names_only_real_settings():
    for name, changes in GOLDEN.items():
        assert set(changes) <= set(settings.DEFAULTS), name

