"""luckytwitch:// links in the real window: they fill in the Plan tab and read the VOD, and they never queue
or start anything. Also the Options > Tools card that sets the links up.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
"""

import time

import pytest

tk = pytest.importorskip("tkinter")

import luckytwitch_downloader as dl  # noqa: E402
import luckytwitch_engine as eng  # noqa: E402
import weblink  # noqa: E402
from test_gui_plan_tab import SOURCE, gui  # noqa: E402,F401  (the fixture that opens the real window)

VOD = "https://www.twitch.tv/videos/123"


def link(cuts="", label=""):
    return weblink.build_link(VOD, cuts, label)


@pytest.fixture()
def reads(gui, monkeypatch):
    """«Get info» without the network: it returns SOURCE, and the calls are recorded."""
    calls: list[str] = []

    def fake_info(text):
        calls.append(text)
        return eng.SourceInfo(**SOURCE)

    monkeypatch.setattr(dl, "get_source_info", fake_info)
    gui.calls = calls
    return gui


def pump(gui, seconds=1.5, until=lambda: False):
    end = time.time() + seconds
    while time.time() < end and not until():
        gui.root.update()
        time.sleep(0.02)
    gui.root.update()


# --------------------------------------------------------------------------- opening a link
def test_a_link_fills_the_plan_tab_and_reads_the_vod(reads):
    app = reads.app
    app.open_link(link("0:20:00 to 3:30:00", "Big Stream"))
    pump(reads, until=lambda: app.source is not None)
    assert app.vod_var.get() == VOD
    assert reads.cuts_text() == "0:20:00 to 3:30:00"
    assert reads.calls == [VOD]
    assert app.source.title == "Big Stream"
    assert app.notebook.select() == str(app.tab_plan)
    assert "opened from a link (Big Stream)" in app.status.get()
    assert reads.boxes == []


def test_without_cut_points_the_default_is_the_whole_vod(reads):
    app = reads.app
    app.open_link(link())
    pump(reads, until=lambda: app.source is not None)
    assert reads.cuts_text() == "0:00:00 - end"


def test_a_link_replaces_the_cut_points_that_were_there(reads):
    app = reads.app
    reads.set_cuts("1:00:00 - 2:00:00")
    app.open_link(link("5:00 - 10:00"))
    pump(reads, until=lambda: app.source is not None)
    assert reads.cuts_text() == "5:00 - 10:00"


def test_a_link_never_adds_to_the_queue_or_starts_a_download(reads, monkeypatch):
    app = reads.app
    started = []
    monkeypatch.setattr(app, "start_queue", lambda *a, **k: started.append(1))
    app.open_link(link("0:00 - 30:00"))
    pump(reads, until=lambda: app.source is not None)
    assert app.items == [] and started == []
    assert app.worker is None


def test_the_previous_vod_is_forgotten_so_its_cuts_cannot_be_reused(gui, monkeypatch):
    app = gui.app
    pump(gui, 3, until=lambda: not app.tools_busy)  # the (stubbed) tool setup at start-up has to finish first
    gui.load_vod(title="Old stream")
    monkeypatch.setattr(dl, "get_source_info", lambda text: (_ for _ in ()).throw(eng.EngineError("no such VOD")))
    app.open_link(link("1:00 - 2:00"))
    assert app.source is None  # reading the new one failed or has not finished: nothing is loaded
    pump(gui, until=lambda: gui.boxes)
    assert app.source is None
    assert gui.boxes and gui.boxes[0][0] == "showerror"
    assert app._info_from_link is None  # a later manual «Get info» does not claim to come from a link


def test_a_bad_link_says_why_and_changes_nothing(reads):
    app = reads.app
    reads.set_cuts("keep me")
    app.open_link("luckytwitch://open?url=file:///etc/passwd")
    assert reads.boxes and reads.boxes[0][0] == "showwarning" and "http" in reads.boxes[0][2]
    assert reads.cuts_text() == "keep me" and reads.calls == []


def test_a_link_waits_while_the_tools_are_being_prepared(reads):
    app = reads.app
    app.tools_busy = True
    app.open_link(link("0:00 - 10:00"))
    pump(reads, 0.3)
    assert reads.calls == [] and app.vod_var.get() == ""  # nothing changed yet
    app.tools_busy = False
    pump(reads, 3, until=lambda: app.source is not None)
    assert reads.calls == [VOD] and reads.cuts_text() == "0:00 - 10:00"


# --------------------------------------------------------------------------- the file route (a second launch)
def test_a_link_left_in_the_folder_is_picked_up_by_the_window(reads):
    app = reads.app
    weblink._drop(dl.LINKS_DIR, link("0:10:00 - 0:20:00", "From a file"))
    pump(reads, 2, until=lambda: app.source is not None)
    assert reads.cuts_text() == "0:10:00 - 0:20:00"
    assert not list(dl.LINKS_DIR.glob("*.link"))


def test_the_window_says_it_is_alive_and_stops_saying_so_when_it_closes(reads):
    pump(reads, 0.3)
    assert weblink.is_running(dl.BEAT_PATH)
    reads.root.destroy = lambda: None  # closing must not really destroy the window the fixture still owns
    try:
        reads.app.on_close()
    finally:
        del reads.root.destroy
    assert not dl.BEAT_PATH.exists()


def test_a_second_launch_hands_its_link_to_the_open_window(reads, monkeypatch):
    app = reads.app
    pump(reads, 0.3)  # the first heartbeat
    monkeypatch.setattr(dl.sys, "argv", ["LuckyTwitch.exe", link("0:00 - 5:00")])
    created = []
    monkeypatch.setattr(dl.tk, "Tk", lambda *a, **k: created.append(1))  # a second window must not be built
    import threading
    done = []
    t = threading.Thread(target=lambda: done.append(dl.main()))
    t.start()  # main() waits for the open window to take the link, so let this window keep polling
    pump(reads, 3, until=lambda: not t.is_alive())
    t.join(5)
    assert done == [None] and created == []
    pump(reads, 2, until=lambda: reads.cuts_text() == "0:00 - 5:00")
    assert reads.cuts_text() == "0:00 - 5:00"


# --------------------------------------------------------------------------- Options > Tools: setting the links up
class FakeRegistry:
    def __init__(self, state, supported=True):
        self.state, self.supported, self.registered = state, supported, 0

    def registration(self, *a, **k):
        return weblink.Registration(self.supported, self.state, "")

    def register(self, *a, **k):
        self.registered += 1
        self.state = "ok"


@pytest.mark.parametrize("state, button, text", [
    ("missing", "Set up links", "Not set up"),
    ("other", "Use this copy", "another copy"),
    ("ok", "Set up again", "Set up:"),
])
def test_the_tools_card_shows_the_state_of_the_links(gui, monkeypatch, state, button, text):
    fake = FakeRegistry(state)
    monkeypatch.setattr(weblink, "registration", fake.registration)
    gui.app.refresh_link_state()
    assert gui.app.link_btn.cget("text") == button
    assert text in gui.app.link_info.get()


def test_pressing_the_button_registers_and_updates_the_card(gui, monkeypatch):
    fake = FakeRegistry("missing")
    monkeypatch.setattr(weblink, "registration", fake.registration)
    monkeypatch.setattr(weblink, "register", fake.register)
    gui.app.refresh_link_state()
    gui.app.link_btn.invoke()
    assert fake.registered == 1 and "Set up:" in gui.app.link_info.get()


def test_a_refusal_from_the_system_is_shown(gui, monkeypatch):
    def refuse(*a, **k):
        raise OSError("access denied")

    monkeypatch.setattr(weblink, "register", refuse)
    gui.app.register_links()
    assert gui.boxes and gui.boxes[0][0] == "showerror" and "access denied" in gui.boxes[0][2]


def test_where_the_app_cannot_set_itself_up_there_is_no_button(gui, monkeypatch):
    fake = FakeRegistry("unsupported", supported=False)
    monkeypatch.setattr(weblink, "registration", fake.registration)
    gui.app.refresh_link_state()
    assert not gui.app.link_btn.winfo_manager()
    assert gui.app.link_info.get()
