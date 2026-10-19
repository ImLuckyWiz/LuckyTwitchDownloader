"""Search tab after the redesign: the sign-in banner, the empty-state messages over each list, the header of the
VOD list, and the ``EmptyState`` widget itself.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
The Twitch client is a stand-in and no network is touched (the fixture lives in test_gui_plan_tab.py).
"""

import threading
import time

import pytest

tk = pytest.importorskip("tkinter")

from tkinter import ttk  # noqa: E402

import luckytwitch_downloader as dl  # noqa: E402
from test_gui_plan_tab import gui  # noqa: E402,F401  (the fixture that opens the real window)
from ui.widgets import EmptyState  # noqa: E402

RESULTS = [
    dict(id="1", login="streamer", name="Streamer", live=True),
    dict(id="2", login="other", name="Other One", live=False),
]


def vod(i, **kw):
    return dict(title=f"Stream {i}", date="2026-10-01", duration=3600.0 + i, views=10 * i, thumb=None, **kw)


def texts(empty: EmptyState) -> list[str]:
    """The lines of text an EmptyState currently shows (title first)."""
    return [w.cget("text") for w in empty._inner.winfo_children() if w.winfo_class() == "Label"]


def list_widget(gui) -> ttk.Treeview:
    """A list in a window of its own (the tab's frame is managed by grid, so it can't take a packed child)."""
    win = tk.Toplevel(gui.root)
    tree = ttk.Treeview(win)
    tree.pack(fill="both", expand=True)
    gui.root.update()
    return tree


def sign_in(gui):
    gui.app.client = object()  # anything truthy: the app only asks «is there a session?»
    gui.app.update_search_state()


# ------------------------------------------------------------------ the sign-in banner
def test_without_a_session_the_banner_shows_and_searching_is_off(gui):
    app = gui.app
    assert app.signin_bar.winfo_manager() == "grid"
    assert str(app.search_btn.cget("state")) == "disabled"
    assert texts(app.sv_empty)[0] == "Sign in to browse VODs"
    assert "Get info" in texts(app.sv_empty)[1]  # and says pasting a link still works without signing in


def test_signing_in_hides_the_banner_and_enables_searching(gui):
    sign_in(gui)
    app = gui.app
    assert app.signin_bar.winfo_manager() == ""
    assert str(app.search_btn.cget("state")) == "normal"
    assert texts(app.sv_empty)[0] == "Pick a streamer"


def test_the_banner_button_opens_the_sign_in_dialog(gui):
    buttons = [w for w in gui.app.signin_bar.winfo_children() if w.winfo_class() == "TButton"]
    assert [b.cget("text") for b in buttons] == ["Sign in…"]
    assert buttons[0].cget("command") != ""


# ------------------------------------------------------------------ the three lists
def test_the_lists_start_with_a_hint_each(gui):
    app = gui.app
    assert app.ch_empty.shown and texts(app.ch_empty) == ["Search results show up here."]
    assert app.recent_empty.shown and texts(app.recent_empty) == ["Streamers you open show up here."]
    assert app.sv_empty.shown
    assert str(app.clear_recent_btn.cget("state")) == "disabled"  # nothing to clear


def test_a_search_without_results_says_what_was_searched(gui):
    sign_in(gui)
    gui.app.on_search_ok("zzzz", [])
    assert gui.app.ch_empty.shown
    assert texts(gui.app.ch_empty) == ["No streamers found for «zzzz»", "Check the spelling."]


def test_search_results_replace_the_message_and_a_new_empty_search_brings_it_back(gui):
    sign_in(gui)
    app = gui.app
    app.on_search_ok("stre", RESULTS)
    assert not app.ch_empty.shown
    assert [app.ch_tree.item(i, "values")[0] for i in app.ch_tree.get_children()] == ["● Streamer", "Other One"]
    app.on_search_ok("nothing", [])
    assert app.ch_empty.shown and not app.ch_tree.get_children()


def test_recent_streamers_toggle_their_message_and_the_clear_button(gui):
    app = gui.app
    app.add_recent(dict(id="9", login="x", name="Ex"))
    assert not app.recent_empty.shown
    assert str(app.clear_recent_btn.cget("state")) == "normal"
    assert [app.recent_tree.item(i, "values")[0] for i in app.recent_tree.get_children()] == ["Ex"]
    app.clear_recent()
    assert app.recent_empty.shown
    assert str(app.clear_recent_btn.cget("state")) == "disabled"


# ------------------------------------------------------------------ the VOD list
def test_vods_hide_the_message_and_the_header_counts_them(gui):
    sign_in(gui)
    app = gui.app
    app.sv_channel, app.sv_gen = RESULTS[0], 1
    app.on_videos_ok(1, [vod(1), vod(2)], None)
    assert not app.sv_empty.shown
    assert app.sv_title.get() == "Streamer  ·  2 VODs"
    assert len(app.sv_tree.get_children()) == 2


def test_the_header_says_there_is_more_and_uses_the_singular(gui):
    sign_in(gui)
    app = gui.app
    app.sv_channel, app.sv_gen = RESULTS[0], 1
    app.on_videos_ok(1, [vod(1)], "next-page")
    assert app.sv_title.get() == "Streamer  ·  1 VOD  ·  more available"
    assert str(app.more_btn.cget("state")) == "normal"


def test_a_streamer_without_vods_gets_an_explanation(gui):
    sign_in(gui)
    app = gui.app
    app.sv_channel, app.sv_gen = RESULTS[0], 1
    app.on_videos_ok(1, [], None)
    assert app.sv_empty.shown
    assert texts(app.sv_empty)[0] == "No past broadcasts found"
    assert "Twitch deletes VODs" in texts(app.sv_empty)[1]
    assert app.sv_title.get() == "Streamer: no past broadcasts found"


def test_loading_is_announced_and_a_failure_ends_it(gui, monkeypatch):
    sign_in(gui)
    app = gui.app
    gate = threading.Event()

    def slow_fetch(client, channel_id, kind, after=None):
        gate.wait(5)
        raise RuntimeError("boom")

    monkeypatch.setattr(dl, "fetch_videos", slow_fetch)
    app.load_channel(RESULTS[0])
    assert app.sv_loading and texts(app.sv_empty)[0] == "Loading VODs…"
    gate.set()
    end = time.time() + 5
    while app.sv_loading and time.time() < end:
        app.poll_queue()
        gui.root.update()
        time.sleep(0.02)
    assert not app.sv_loading
    assert app.sv_title.get() == "Could not load the VODs."
    assert texts(app.sv_empty)[0] == "Pick a streamer" or texts(app.sv_empty)[0].startswith("No ")


def test_an_answer_for_an_older_streamer_changes_nothing(gui):
    sign_in(gui)
    app = gui.app
    app.sv_channel, app.sv_gen = RESULTS[0], 2
    app.sv_loading = True
    app.on_videos_ok(1, [vod(1)], None)  # generation 1 is stale
    assert app.sv_loading and not app.sv_tree.get_children()


def test_vod_headings_line_up_with_their_columns(gui):
    tree = gui.app.sv_tree
    for col in tree["columns"]:
        assert tree.heading(col, "anchor") == tree.column(col, "anchor")


def test_the_use_hint_sits_next_to_the_button_and_the_header_has_no_instruction(gui):
    app = gui.app
    sign_in(gui)
    app.sv_channel, app.sv_gen = RESULTS[0], 1
    app.on_videos_ok(1, [vod(1)], None)
    assert "double-click" not in app.sv_title.get().lower()  # it used to run into the drop-down
    labels = []

    def walk(w):
        for c in w.winfo_children():
            if c.winfo_class() == "TLabel":
                labels.append(c.cget("text"))
            walk(c)

    walk(app.tab_search)
    assert "Double-click a VOD to use it" in labels


def test_the_streamer_lists_keep_working_as_before(gui):
    app = gui.app
    assert tuple(app.ch_tree["columns"]) == ("name",) and tuple(app.recent_tree["columns"]) == ("name",)
    # no column heading: the card has the title. (Tk gives back '' for show=() on Python 3.12 but an empty tuple on 3.14,
    # which str() turned into '()': so test for "nothing shown" instead of comparing strings)
    assert not app.ch_tree.cget("show") and not app.recent_tree.cget("show")
    assert isinstance(app.sv_tree, ttk.Treeview) and tuple(app.sv_tree["columns"]) == ("title", "date", "dur", "views")


# ------------------------------------------------------------------ the widget on its own
def test_empty_state_shows_hides_and_refills(gui):
    tree = list_widget(gui)
    es = EmptyState(tree)
    assert not es.shown
    es.show("Title", "Body")
    assert es.shown and texts(es) == ["Title", "Body"]
    es.show("Other", "")  # showing again replaces the lines, never stacks them
    assert texts(es) == ["Other"]
    es.hide()
    es.hide()  # harmless twice
    assert not es.shown and es.winfo_manager() == ""


def test_empty_state_can_carry_a_button(gui):
    tree = list_widget(gui)
    es = EmptyState(tree)
    clicks = []
    es.show("Sign in", "", button=("Sign in…", lambda: clicks.append(1)))
    btn = next(w for w in es._inner.winfo_children() if w.winfo_class() == "TButton")
    assert btn.cget("text") == "Sign in…"
    btn.invoke()
    assert clicks == [1]


def test_empty_state_leaves_room_for_the_column_headings(gui):
    tree = list_widget(gui)
    es = EmptyState(tree, top=34)
    es.show("x")
    gui.root.update()
    assert int(es.place_info()["y"]) == 34
