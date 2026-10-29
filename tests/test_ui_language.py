"""Tests for UI language configuration (Phase F4 temporary disablement for v2.9.1)."""

from __future__ import annotations

import pytest

from core import paths
from core.i18n import get_language
from core.ui_state import UIState, load_ui_state, save_ui_state
from qt_ui.main_window import MainWindow


def test_ui_language_temporarily_disabled_in_v2_9_1(qtbot, tmp_path, monkeypatch):
    test_ui_path = tmp_path / "luckytwitch_ui.json"
    monkeypatch.setattr(paths, "UI_STATE_PATH", test_ui_path)

    # 1. Even if previously saved state had 'es', app forces English in v2.9.1
    st = UIState(language="es")
    save_ui_state(st, test_ui_path)

    win = MainWindow()
    qtbot.addWidget(win)

    assert get_language() == "en"
    assert win.command_bar.prompt_label.text() == "VOD URL or ID:"
    assert win.command_bar.info_btn.text() == "Get info"
    assert win.tab_queue.start_btn.text() == "Start queue"
    assert win.tabs.tabText(0) == "Search"
    assert win.tabs.tabText(3) == "Queue && log"

    # 2. Options language combo is disabled to prevent partial / half-Spanish UI
    combo = win.tab_options.lang_combo
    assert combo.isEnabled() is False
    assert combo.currentIndex() == 0
    assert "English" in combo.currentText()
    assert "temporarily disabled" in combo.toolTip().lower()

    win.close()
