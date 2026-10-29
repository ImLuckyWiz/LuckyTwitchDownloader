"""Tests for UI language selection, live retranslation, and persistence."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from core import paths
from core.i18n import get_language, set_language
from core.ui_state import UIState, load_ui_state, save_ui_state
from qt_ui.main_window import MainWindow


def test_ui_language_persistence_and_live_switch(qtbot, tmp_path, monkeypatch):
    test_ui_path = tmp_path / "luckytwitch_ui.json"
    monkeypatch.setattr(paths, "UI_STATE_PATH", test_ui_path)

    # 1. Start with saved language = 'es'
    st = UIState(language="es")
    save_ui_state(st, test_ui_path)

    win = MainWindow()
    qtbot.addWidget(win)

    assert get_language() == "es"
    assert win.tab_options.lang_combo.currentText() == "Español"
    assert win.command_bar.prompt_label.text() == "URL o ID del VOD:"
    assert win.command_bar.info_btn.text() == "Obtener información"
    assert win.tab_queue.start_btn.text() == "Iniciar cola"
    assert win.tabs.tabText(0) == "Buscar"
    assert win.tabs.tabText(3) == "Cola y registros"

    # 2. Live switch to English
    win.tab_options.lang_combo.setCurrentIndex(0)
    assert get_language() == "en"

    saved_st = load_ui_state(test_ui_path)
    assert saved_st.language == "en"
    assert win.command_bar.prompt_label.text() == "VOD URL or ID:"
    assert win.command_bar.info_btn.text() == "Get info"
    assert win.tab_queue.start_btn.text() == "Start queue"
    assert win.tabs.tabText(0) == "Search"
    assert win.tabs.tabText(3) == "Queue && log"

    # 3. Live switch back to Spanish
    win.tab_options.lang_combo.setCurrentIndex(1)
    assert get_language() == "es"
    saved_st2 = load_ui_state(test_ui_path)
    assert saved_st2.language == "es"
    assert win.command_bar.prompt_label.text() == "URL o ID del VOD:"
    assert win.tab_queue.start_btn.text() == "Iniciar cola"
    assert win.tabs.tabText(0) == "Buscar"

    win.close()
