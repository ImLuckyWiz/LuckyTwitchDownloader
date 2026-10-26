"""Tests for core/ui_state.py (persisting layout geometry, active tab, and drawer states)."""

from __future__ import annotations

import json
from pathlib import Path

from core import ui_state


def test_load_ui_state_defaults_when_no_file(tmp_path: Path):
    target = tmp_path / "luckytwitch_ui.json"
    state = ui_state.load_ui_state(target)
    assert state.window_w == 1020
    assert state.window_h == 910
    assert state.active_tab == "Plan"
    assert state.rail_expanded is False
    assert state.log_open is False


def test_load_ui_state_survives_invalid_json(tmp_path: Path):
    target = tmp_path / "luckytwitch_ui.json"
    target.write_text("{broken json", encoding="utf-8")
    state = ui_state.load_ui_state(target)
    assert state.window_w == 1020


def test_save_and_load_ui_state_roundtrip(tmp_path: Path):
    target = tmp_path / "luckytwitch_ui.json"
    s1 = ui_state.UIState(
        window_x=100,
        window_y=200,
        window_w=1280,
        window_h=800,
        active_tab="Queue & log",
        rail_expanded=True,
        log_open=True,
        splitter_sizes=[250, 450],
    )
    ui_state.save_ui_state(s1, target)
    assert target.is_file()

    loaded = ui_state.load_ui_state(target)
    assert loaded.window_x == 100
    assert loaded.window_y == 200
    assert loaded.window_w == 1280
    assert loaded.window_h == 800
    assert loaded.active_tab == "Queue & log"
    assert loaded.rail_expanded is True
    assert loaded.log_open is True
    assert loaded.splitter_sizes == [250, 450]


def test_save_ui_state_ignores_os_errors(tmp_path: Path):
    # Non-writable target directory should not crash
    blocked = tmp_path / "file_blocker"
    blocked.write_text("x", encoding="utf-8")
    ui_state.save_ui_state(ui_state.UIState(), blocked / "sub" / "ui.json")
