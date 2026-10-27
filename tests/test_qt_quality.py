"""Tests for Phase 6: Plan tab quality picker, preview estimation, and MainWindow wiring."""

import json
from pathlib import Path
import types
import webbrowser

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication

import luckytwitch_engine as eng
from core.settings import DEFAULTS
from qt_ui import dialogs, theme
from qt_ui import main_window as mw
from qt_ui.tabs.plan import human_size

FIXTURE_SHORT = Path("tests/fixtures/vod_single_game_short.json")
SOURCE = dict(
    url="https://www.twitch.tv/videos/123", id="v123", title="Big Stream", uploader="Streamer",
    duration=7200.0, date="2026-10-01", twitch_vod_id="123"
)


def load_fixture(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


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
def boxes(monkeypatch):
    calls = types.SimpleNamespace(log=[], opened=[])
    for name in ("info", "warning", "error"):
        monkeypatch.setattr(dialogs, name, lambda parent, title, text, _n=name: calls.log.append((_n, title, text)))
    monkeypatch.setattr(dialogs, "ask_yes_no", lambda parent, title, text: True)
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: calls.opened.append(url))
    return calls


@pytest.fixture()
def win(qtbot, themed, boxes):
    w = mw.MainWindow(settings=dict(DEFAULTS), client=None)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_human_size():
    assert human_size(1_400_000_000) == "1.4 GB"
    assert human_size(820_000_000) == "820 MB"
    assert human_size(0) == "0 B"
    assert human_size(-5) == "0 B"
    assert human_size(500) == "500 B"


def test_quality_row_hidden_without_formats_and_after_clear(win):
    plan = win.tab_plan
    assert not plan.quality_row.isVisible()

    # Empty formats keep it hidden
    plan.set_formats([], "Best available")
    assert not plan.quality_row.isVisible()
    assert plan.current_quality() == eng.QUALITY_BEST

    # Loading with formats makes it visible
    fmts = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    plan.set_formats(fmts, "Best available")
    assert plan.quality_row.isVisible()

    # clear_vod hides it again
    win.clear_vod()
    assert not plan.quality_row.isVisible()
    assert plan.current_quality() == eng.QUALITY_BEST


def test_quality_combo_items_and_default_selection(win):
    plan = win.tab_plan
    fmts = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))

    # Best available default
    plan.set_formats(fmts, "Best available")
    assert plan.quality_row.isVisible()
    assert plan.quality_combo.count() == 7  # Best + 6 formats
    assert plan.quality_combo.itemText(0) == "Best available (1080p60 (Source))"
    assert plan.quality_combo.itemData(0) == eng.QUALITY_BEST
    assert plan.quality_combo.currentIndex() == 0
    assert plan.current_quality() == eng.QUALITY_BEST

    # 720p default selects 720p60
    plan.set_formats(fmts, "720p")
    assert plan.current_quality() == "720p60"
    assert plan.quality_combo.currentText() == "720p60"

    # Audio only default selects Audio_Only
    plan.set_formats(fmts, "Audio only")
    assert plan.current_quality() == "Audio_Only"
    assert plan.quality_combo.currentText() == "Audio only"


def test_quality_pick_emits_signal_updates_options_and_does_not_mutate_settings(win, qtbot):
    plan = win.tab_plan
    fmts = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    plan.set_formats(fmts, "Best available")

    # Find 480p index
    idx_480 = -1
    for i in range(plan.quality_combo.count()):
        if plan.quality_combo.itemData(i) == "480p":
            idx_480 = i
            break
    assert idx_480 > 0

    fired = []
    plan.quality_changed.connect(fired.append)

    plan.quality_combo.setCurrentIndex(idx_480)
    plan.quality_combo.activated.emit(idx_480)

    assert fired == ["480p"]
    assert plan.current_quality() == "480p"
    assert win.build_options().quality == "480p"
    # Settings default_quality remains untouched
    assert win.settings["default_quality"] == DEFAULTS["default_quality"]


def test_add_to_queue_uses_plan_quality(win):
    fmts = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    src = eng.SourceInfo(**{**SOURCE, "formats": fmts})
    win.source = src
    win.tab_plan.source = src
    win.tab_plan.set_formats(fmts, "Best available")

    # Pick 480p
    idx_480 = [i for i in range(win.tab_plan.quality_combo.count()) if win.tab_plan.quality_combo.itemData(i) == "480p"][0]
    win.tab_plan.quality_combo.setCurrentIndex(idx_480)
    win.tab_plan.quality_combo.activated.emit(idx_480)

    win.tab_plan.set_cut_text("0:00:00 - 0:10:00")
    win.tab_plan.queue_btn.click()

    assert len(win.tab_queue.items) == 1
    assert win.tab_queue.items[0].job.opts.quality == "480p"


def test_loading_another_vod_resets_pick_to_default(win):
    fmts = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    src = eng.SourceInfo(**{**SOURCE, "formats": fmts})

    win.settings["default_quality"] = "720p"
    win.on_info_ok(src, [], True, "")
    assert win.tab_plan.current_quality() == "720p60"

    # Pick 480p manually
    idx_480 = [i for i in range(win.tab_plan.quality_combo.count()) if win.tab_plan.quality_combo.itemData(i) == "480p"][0]
    win.tab_plan.quality_combo.setCurrentIndex(idx_480)
    win.tab_plan.quality_combo.activated.emit(idx_480)
    assert win.tab_plan.current_quality() == "480p"

    # Reload another VOD -> resets to default 720p60
    src2 = eng.SourceInfo(**{**SOURCE, "id": "v456", "twitch_vod_id": "456", "formats": fmts})
    win.on_info_ok(src2, [], True, "")
    assert win.tab_plan.current_quality() == "720p60"


def test_preview_text_mentions_quality_and_audio_only(win):
    fmts = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    src = eng.SourceInfo(**{**SOURCE, "formats": fmts})
    win.source = src
    win.tab_plan.source = src
    win.tab_plan.set_formats(fmts, "Best available")
    win.tab_plan.set_cut_text("0:00:00 - 0:10:00")

    # Pick 480p
    idx_480 = [i for i in range(win.tab_plan.quality_combo.count()) if win.tab_plan.quality_combo.itemData(i) == "480p"][0]
    win.tab_plan.quality_combo.setCurrentIndex(idx_480)
    win.tab_plan.quality_combo.activated.emit(idx_480)

    preview = win.tab_plan.preview_text()
    assert "Quality: 480p" in preview
    assert "about" in preview

    # Pick Audio_Only
    idx_audio = [i for i in range(win.tab_plan.quality_combo.count()) if win.tab_plan.quality_combo.itemData(i) == "Audio_Only"][0]
    win.tab_plan.quality_combo.setCurrentIndex(idx_audio)
    win.tab_plan.quality_combo.activated.emit(idx_audio)

    preview_audio = win.tab_plan.preview_text()
    assert "Audio only" in preview_audio
