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
