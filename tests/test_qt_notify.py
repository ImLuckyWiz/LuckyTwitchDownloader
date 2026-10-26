"""Tests for non-modal toasts and notification service (Phase 9b, B5 & B6: qt_ui/toast.py, qt_ui/notify.py)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from qt_ui import notify, theme  # noqa: E402
from qt_ui.toast import ToastCard, ToastHost  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_notify(qtbot):
    app = QApplication.instance()
    saved = (app.palette(), app.font(), app.styleSheet())
    theme.apply_theme(app)
    notify.calls.clear()
    yield
    notify.calls.clear()
    app.setStyleSheet(saved[2])
    app.setPalette(saved[0])
    app.setFont(saved[1])


def test_notify_info_success_warning_create_toasts_and_log_calls(qtbot):
    win = QWidget()
    win.resize(800, 600)
    qtbot.addWidget(win)
    win.show()

    c1 = notify.info(win, "Info title", "Info body")
    c2 = notify.success(win, "Done", "Saved file")
    c3 = notify.warning(win, "Heads up", "Check this")

    assert isinstance(c1, ToastCard) and c1.isVisible()
    assert isinstance(c2, ToastCard) and c2.isVisible()
    assert isinstance(c3, ToastCard) and c3.isVisible()
    assert notify.calls == [
        ("info", "Info title", "Info body"),
        ("success", "Done", "Saved file"),
        ("warning", "Heads up", "Check this"),
    ]


def test_toast_action_button_runs_callback_and_dismisses(qtbot):
    win = QWidget()
    win.resize(800, 600)
    qtbot.addWidget(win)
    win.show()

    clicked = []
    card = notify.success(win, "Added to queue", "Streamer · Stream", action=("Go to Queue", lambda: clicked.append(1)))
    assert card is not None and card.action_btn is not None
    assert card.action_btn.text() == "Go to Queue"
    qtbot.mouseClick(card.action_btn, Qt.MouseButton.LeftButton)
    assert clicked == [1]
    assert not card.isVisible()


def test_toast_close_button_dismisses_and_removes_from_host(qtbot):
    win = QWidget()
    win.resize(800, 600)
    qtbot.addWidget(win)
    win.show()

    card = notify.info(win, "Hello", "World")
    host = win._toast_host
    assert isinstance(host, ToastHost) and card in host.toasts
    qtbot.mouseClick(card.close_btn, Qt.MouseButton.LeftButton)
    assert card not in host.toasts


def test_toast_auto_dismisses_and_pauses_while_hovered(qtbot):
    win = QWidget()
    win.resize(800, 600)
    qtbot.addWidget(win)
    win.show()

    card = ToastCard("Short", "Message", duration_ms=60, parent=win)
    closed = []
    card.closed.connect(closed.append)
    card.show()
    card.set_hovered(True)
    qtbot.wait(100)
    assert card.isVisible() and not closed  # paused while hovered
    card.set_hovered(False)
    qtbot.waitUntil(lambda: bool(closed), timeout=1000)


def test_toast_host_caps_visible_stack_at_max(qtbot):
    win = QWidget()
    win.resize(800, 600)
    qtbot.addWidget(win)
    win.show()

    for i in range(5):
        notify.info(win, f"Toast {i}", "Body")
    host = win._toast_host
    assert len(host.toasts) == ToastHost.MAX_VISIBLE
    assert [t.title for t in host.toasts] == ["Toast 2", "Toast 3", "Toast 4"]


def test_system_notify_is_safe_on_offscreen(qtbot):
    win = QWidget()
    win.resize(800, 600)
    qtbot.addWidget(win)
    win.show()

    card = notify.system_notify(win, "Queue finished", "All done")
    assert isinstance(card, ToastCard)
    assert notify.calls[-1] == ("success", "Queue finished", "All done")
