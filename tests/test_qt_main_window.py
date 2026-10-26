"""The Qt main window (Phase 1: the frame only). Smoke tests with pytest-qt; no display needed (offscreen)."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QProgressBar, QPushButton, QTabBar  # noqa: E402

import luckytwitch_qt  # noqa: E402
from core import paths  # noqa: E402
from core.settings import DEFAULTS  # noqa: E402
from qt_ui import main_window as mw  # noqa: E402
from qt_ui import theme  # noqa: E402
from qt_ui.bridge import Bridge  # noqa: E402
from qt_ui.tabs import OptionsTab, PlanTab, QueueTab, SearchTab  # noqa: E402


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
def win(qtbot, themed):
    w = mw.MainWindow(settings=dict(DEFAULTS), client=object())  # signed in: starts on the first tab
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_window_title_size_and_minimum(win):
    assert win.windowTitle() == "LuckyTwitch Downloader"
    assert mw.START_SIZE == (1020, 910)
    assert win.width() >= 900 and win.height() >= 560  # offscreen it is exactly 1020x910; a real screen may clamp it
    assert (win.minimumSize().width(), win.minimumSize().height()) == (900, 560)
    assert mw.START_SIZE == (1020, 910) and mw.MIN_SIZE == (900, 560)


def test_the_four_tabs_have_the_same_names_in_the_same_order(win):
    assert win.tab_names() == ["Search", "Plan", "Options", "Queue & log"]
    assert [type(win.tabs.widget(i)) for i in range(4)] == [SearchTab, PlanTab, OptionsTab, QueueTab]
    # the ampersand shows as a real '&' (a single '&' would turn the next letter into a shortcut)
    assert win.tabs.tabText(3) == "Queue && log"


def test_the_tabs_that_are_not_built_yet_are_empty(win):
    for i in (1, 2):  # Plan, Options (Queue & log was built in Phase 3, Search in Phase 4)
        assert win.tabs.widget(i).findChildren(QLabel) == []
        assert win.tabs.widget(i).children() == []


def test_top_bar_texts_and_widgets(win):
    labels = [l.text() for l in win.findChildren(QLabel)]
    assert "VOD URL or ID:" in labels
    assert win.info_btn.text() == "Get info" and win.info_btn.property("variant") == "accent"
    assert win.api_btn.text() == "Twitch API…" and win.api_btn.property("variant") is None
    assert isinstance(win.vod_entry, QLineEdit) and win.vod_entry.text() == ""
    assert win.info_label.text() == "No VOD loaded." and win.info_label.property("role") == "muted"


def test_bottom_bar_has_a_progress_bar_and_the_ready_status(win):
    assert isinstance(win.progress, QProgressBar)
    assert (win.progress.minimum(), win.progress.maximum(), win.progress.value()) == (0, 100, 0)
    assert win.status_label.text() == "Ready. Paste a VOD URL or ID and press «Get info»."
    win.set_status("something else")
    assert win.status_label.text() == "something else"
    # always visible: below the tabs, whatever tab is open
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        assert win.progress.isVisible() and win.status_label.isVisible()
        assert win.status_label.y() > win.tabs.y()


def test_starts_on_the_plan_tab_without_a_twitch_client_and_on_search_with_one(qtbot, themed):
    no_client = mw.MainWindow(client=None)
    qtbot.addWidget(no_client)
    assert no_client.tabs.currentWidget() is no_client.tab_plan
    signed_in = mw.MainWindow(client=object())
    qtbot.addWidget(signed_in)
    assert signed_in.tabs.currentWidget() is signed_in.tab_search


def test_the_buttons_and_enter_call_the_stub_handlers(qtbot, themed, monkeypatch):
    calls = []
    monkeypatch.setattr(mw.MainWindow, "on_get_info", lambda self: calls.append("get_info"))
    monkeypatch.setattr(mw.MainWindow, "ask_credentials", lambda self: calls.append("credentials"))
    w = mw.MainWindow(client=object())
    qtbot.addWidget(w)
    w.show()
    w.info_btn.click()
    w.api_btn.click()
    qtbot.keyClick(w.vod_entry, qtbot_key("Return"))
    assert calls == ["get_info", "credentials", "get_info"]


def qtbot_key(name):
    from PySide6.QtCore import Qt

    return getattr(Qt.Key, f"Key_{name}")


def test_the_stub_handlers_do_nothing_and_do_not_raise(win):
    before = (win.status_label.text(), win.info_label.text(), win.tabs.currentIndex())
    win.on_get_info()  # the Twitch API dialog (the other stub of Phase 1) was built in Phase 4
    assert (win.status_label.text(), win.info_label.text(), win.tabs.currentIndex()) == before


def test_keyboard_order_is_entry_then_get_info_then_twitch_api_then_the_tabs(win):
    chain, w = [], win.vod_entry
    for _ in range(12):  # follow the focus chain a few steps, keeping only the stops we care about
        if w in (win.vod_entry, win.info_btn, win.api_btn) or isinstance(w, QTabBar):
            chain.append(w)
        w = w.nextInFocusChain()
    assert chain[:4] == [win.vod_entry, win.info_btn, win.api_btn, win.tabs.tabBar()]


def test_the_window_can_be_shrunk_to_the_minimum_without_hiding_the_bottom_bar(win):
    win.resize(900, 560)
    QApplication.processEvents()
    assert win.size().width() >= 900 and win.size().height() >= 560
    assert win.status_label.geometry().bottom() <= win.centralWidget().height()
    assert win.progress.isVisible()


def test_the_window_makes_its_own_bridge_or_uses_the_one_it_is_given(qtbot, themed):
    own = mw.MainWindow()
    qtbot.addWidget(own)
    assert isinstance(own.bridge, Bridge)
    bridge = Bridge()
    given = mw.MainWindow(bridge=bridge)
    qtbot.addWidget(given)
    assert given.bridge is bridge


# ------------------------------------------------------------------ the entry point
def test_main_builds_the_window_from_the_saved_settings_and_saves_them_on_close(qtbot, themed, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(paths, "SETTINGS_PATH", tmp_path / "data" / "luckytwitch_settings.json")
    monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "data" / "config.json")
    app = QApplication.instance()
    made = []
    real_init = mw.MainWindow.__init__

    def spy(self, *a, **k):
        real_init(self, *a, **k)
        made.append((self, k))

    class FakeApp:  # main() builds its own QApplication and runs its loop: hand it the test one, with no loop
        def __new__(cls, argv):
            return app

    monkeypatch.setattr(luckytwitch_qt, "QApplication", FakeApp)
    monkeypatch.setattr(type(app), "exec", lambda self: 0)
    monkeypatch.setattr(mw.MainWindow, "__init__", spy)
    assert luckytwitch_qt.main(["luckytwitch_qt.py"]) == 0
    window, kwargs = made[0]
    qtbot.addWidget(window)
    assert kwargs["settings"] == DEFAULTS and kwargs["client"] is None
    assert (tmp_path / "data").is_dir()  # the data folder is created
    assert not paths.SETTINGS_PATH.exists()  # nothing is written until the window closes
    window.close()
    assert paths.SETTINGS_PATH.exists()  # Phase 3: saved on close, same file and keys as the tkinter app
