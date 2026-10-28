"""
Tests for Phase W (Custom Window Bar): CustomTitleBar, CaptionButton, and window integration.
"""

from __future__ import annotations

import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from core.settings import DEFAULTS
from qt_ui.main_window import MainWindow
from qt_ui.titlebar import CustomTitleBar, TITLEBAR_HEIGHT


@pytest.fixture(scope="module", autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_custom_titlebar_creation(qtbot):
    win = MainWindow(settings=dict(DEFAULTS), client=object())
    qtbot.addWidget(win)
    win.show()

    assert win.title_bar is not None
    assert isinstance(win.title_bar, CustomTitleBar)
    assert win.title_bar.height() == TITLEBAR_HEIGHT
    assert win.title_bar.min_btn is not None
    assert win.title_bar.max_btn is not None
    assert win.title_bar.close_btn is not None


def test_custom_titlebar_maximize_toggle(qtbot):
    win = MainWindow(settings=dict(DEFAULTS), client=object())
    qtbot.addWidget(win)
    win.show()

    tb = win.title_bar
    assert tb.max_btn.toolTip() == "Maximize"

    # Click maximize
    tb.max_btn.click()
    assert win.isMaximized()
    assert tb.max_btn.toolTip() == "Restore"

    # Click restore
    tb.max_btn.click()
    assert not win.isMaximized()
    assert tb.max_btn.toolTip() == "Maximize"


def test_custom_titlebar_double_click_maximize(qtbot):
    win = MainWindow(settings=dict(DEFAULTS), client=object())
    qtbot.addWidget(win)
    win.show()

    tb = win.title_bar
    assert not win.isMaximized()

    # Simulate double click in empty space of title bar
    center = QPointF(tb.width() / 2, tb.height() / 2)
    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        center,
        center,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    tb.mouseDoubleClickEvent(ev)
    assert win.isMaximized()


def test_custom_titlebar_native_frame_flag(qtbot, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app", "--native-frame"])
    win = MainWindow(settings=dict(DEFAULTS), client=object())
    qtbot.addWidget(win)

    assert win.title_bar is None
    assert not win.use_custom_titlebar


def test_custom_titlebar_disabled_by_settings(qtbot):
    s = dict(DEFAULTS)
    s["custom_titlebar"] = False
    win = MainWindow(settings=s, client=object())
    qtbot.addWidget(win)

    assert win.title_bar is None
    assert not win.use_custom_titlebar


def test_custom_titlebar_title_sync(qtbot):
    win = MainWindow(settings=dict(DEFAULTS), client=object())
    qtbot.addWidget(win)

    win.setWindowTitle("Custom Title Test")
    assert win.title_bar.title_label.text() == "Custom Title Test"
