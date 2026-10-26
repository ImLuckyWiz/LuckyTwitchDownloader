"""Tests for the First-Run Welcome & Quick Setup experience (docs/FIRST_RUN_WELCOME_PLAN.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from core.settings import DEFAULTS
from core.ui_state import UIState, load_ui_state, save_ui_state
from qt_ui.main_window import MainWindow
from qt_ui.motion import Motion
from qt_ui.welcome import AnimatedCanvas, QuickSetupCard, WelcomeOverlay


def test_quick_setup_card_controls_and_toggles(qtbot, tmp_path):
    card = QuickSetupCard(
        initial_out_dir=str(tmp_path),
        initial_container="mp4",
        is_signed_in=False,
    )
    qtbot.addWidget(card)
    card.show()
    qtbot.waitExposed(card)

    assert card.selected_out_dir == str(tmp_path)
    assert card.selected_container == "mp4"
    assert "Not signed in" in card.auth_status_lbl.text()

    # Toggle to MKV
    qtbot.mouseClick(card.mkv_btn, Qt.MouseButton.LeftButton)
    assert card.selected_container == "mkv"

    # Toggle back to MP4
    qtbot.mouseClick(card.mp4_btn, Qt.MouseButton.LeftButton)
    assert card.selected_container == "mp4"

    # Set signed in
    card.set_signed_in(True)
    assert "Signed in" in card.auth_status_lbl.text()
    assert card.auth_dot.text() == "\u25cf"


def test_welcome_overlay_dismiss_via_button(qtbot, tmp_path):
    parent = QWidget()
    parent.resize(1020, 910)
    qtbot.addWidget(parent)
    parent.show()

    overlay = WelcomeOverlay(
        initial_out_dir=str(tmp_path / "downloads"),
        initial_container="mkv",
        is_signed_in=False,
        parent=parent,
    )
    overlay.setGeometry(0, 0, parent.width(), parent.height())
    overlay.show()
    qtbot.waitExposed(overlay)

    done = []
    overlay.finished.connect(lambda out_dir, fmt: done.append((out_dir, fmt)))

    qtbot.mouseClick(overlay.start_btn, Qt.MouseButton.LeftButton)
    assert len(done) == 1
    assert done[0] == (str(tmp_path / "downloads"), "mkv")


def test_welcome_overlay_dismiss_via_escape_key(qtbot, tmp_path):
    parent = QWidget()
    parent.resize(1020, 910)
    qtbot.addWidget(parent)
    parent.show()

    overlay = WelcomeOverlay(
        initial_out_dir=str(tmp_path / "downloads"),
        initial_container="mp4",
        is_signed_in=False,
        parent=parent,
    )
    overlay.setGeometry(0, 0, parent.width(), parent.height())
    overlay.show()
    qtbot.waitExposed(overlay)

    done = []
    overlay.finished.connect(lambda out_dir, fmt: done.append((out_dir, fmt)))

    qtbot.keyClick(overlay, Qt.Key.Key_Escape)
    assert len(done) == 1
    assert done[0] == (str(tmp_path / "downloads"), "mp4")


def test_animated_canvas_paint_and_motion(qtbot):
    canvas = AnimatedCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 300)
    canvas.show()
    qtbot.waitExposed(canvas)

    # When motion is disabled (default in tests)
    assert not canvas._timer.isActive()
    canvas.start_bloom(duration_ms=0)
    assert canvas._glow_alpha_mult == 1.0

    # When motion is enabled
    Motion.set_enabled(True)
    try:
        canvas.start_bloom(duration_ms=60)
        assert canvas._timer.isActive()
        qtbot.wait(80)
        assert canvas._glow_alpha_mult > 0.0
    finally:
        Motion.set_enabled(False)


def test_main_window_show_welcome_overlay_updates_settings_and_ui_state(qtbot, tmp_path, monkeypatch):
    from core import paths
    ui_path = tmp_path / "data" / "luckytwitch_ui.json"
    monkeypatch.setattr(paths, "UI_STATE_PATH", ui_path)

    settings = dict(DEFAULTS)
    win = MainWindow(settings=settings, client=None, show_welcome=True)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)

    assert win.welcome_overlay is not None
    assert win.welcome_overlay.isVisible()

    # Switch format to MKV in the overlay and click Start
    win.welcome_overlay.setup_card._set_container("mkv")
    qtbot.mouseClick(win.welcome_overlay.start_btn, Qt.MouseButton.LeftButton)

    assert win.settings["container"] == "mkv"
    assert win.welcome_overlay is None

    # Verify saved UIState has has_completed_onboarding=True
    loaded = load_ui_state(ui_path)
    assert loaded.has_completed_onboarding is True


def test_main_window_f2_shortcut_reopens_welcome_overlay(qtbot, tmp_path, monkeypatch):
    from core import paths
    ui_path = tmp_path / "data" / "luckytwitch_ui.json"
    monkeypatch.setattr(paths, "UI_STATE_PATH", ui_path)
    save_ui_state(UIState(has_completed_onboarding=True), ui_path)

    win = MainWindow(settings=dict(DEFAULTS), client=None, show_welcome=False)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)

    assert win.welcome_overlay is None

    # Activate F2 shortcut
    assert "F2" in win.shortcuts
    win.shortcuts["F2"].activated.emit()
    assert win.welcome_overlay is not None
    assert win.welcome_overlay.isVisible()
    win.welcome_overlay.dismiss()
