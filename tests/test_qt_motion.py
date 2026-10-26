"""Tests for Phase 1: Modern Motion Core and Micro-interactions."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from core.palette import ACCENT, BG3
from qt_ui.motion import (
    DURATION_ENTER, DURATION_FAST, DURATION_INSTANT, DURATION_MICRO, DURATION_NORMAL, DURATION_PULSE,
    EASING_IN, EASING_OUT, EASING_SNAP, EASING_SMOOTH, ButtonHoverAnimator, Motion, animate_height,
    animate_opacity, animate_slide_and_fade, animate_value, animate_width,
)
from qt_ui.widgets import Toggle, Tooltip


def test_motion_modern_tokens_and_curves():
    assert Motion.DURATION_INSTANT == 0
    assert Motion.DURATION_MICRO == 80
    assert Motion.DURATION_FAST == 140
    assert Motion.DURATION_NORMAL == 200
    assert Motion.DURATION_ENTER == 240
    assert Motion.DURATION_PULSE == 1200

    Motion.set_enabled(False)
    assert Motion.duration(Motion.DURATION_NORMAL) == 0
    assert Motion.duration(Motion.DURATION_MICRO) == 0

    Motion.set_enabled(True)
    try:
        assert Motion.duration(Motion.DURATION_NORMAL) == 200
        assert Motion.duration(Motion.DURATION_MICRO) == 80
        assert Motion.duration(Motion.DURATION_FAST) == 140
    finally:
        Motion.set_enabled(False)


def test_animate_opacity_instant_when_motion_disabled(qtbot):
    lbl = QLabel("Test")
    qtbot.addWidget(lbl)
    lbl.show()
    qtbot.waitExposed(lbl)

    done = []
    Motion.set_enabled(False)
    anim = animate_opacity(lbl, 0.0, 1.0, duration_ms=200, on_finished=lambda: done.append(True))
    assert anim is None
    assert done == [True]
    effect = lbl.graphicsEffect()
    assert effect is not None
    assert effect.opacity() == 1.0


def test_animate_opacity_runs_when_motion_enabled(qtbot):
    lbl = QLabel("Test")
    qtbot.addWidget(lbl)
    lbl.show()
    qtbot.waitExposed(lbl)

    done = []
    Motion.set_enabled(True)
    try:
        anim = animate_opacity(lbl, 0.0, 1.0, duration_ms=60, on_finished=lambda: done.append(True))
        assert anim is not None
        qtbot.waitUntil(lambda: len(done) == 1, timeout=1000)
        effect = lbl.graphicsEffect()
        assert effect.opacity() == 1.0
    finally:
        Motion.set_enabled(False)


def test_animate_slide_and_fade_instant_when_disabled(qtbot):
    lbl = QLabel("Test")
    qtbot.addWidget(lbl)
    lbl.show()
    qtbot.waitExposed(lbl)

    done = []
    start = QPoint(10, 10)
    end = QPoint(10, 20)
    Motion.set_enabled(False)
    group = animate_slide_and_fade(lbl, start, end, 0.0, 1.0, duration_ms=100, on_finished=lambda: done.append(True))
    assert group is None
    assert done == [True]
    assert lbl.pos() == end
    assert lbl.graphicsEffect().opacity() == 1.0


def test_animate_slide_and_fade_runs_when_enabled(qtbot):
    lbl = QLabel("Test")
    qtbot.addWidget(lbl)
    lbl.show()
    qtbot.waitExposed(lbl)

    done = []
    start = QPoint(10, 10)
    end = QPoint(10, 20)
    Motion.set_enabled(True)
    try:
        group = animate_slide_and_fade(lbl, start, end, 0.0, 1.0, duration_ms=60, on_finished=lambda: done.append(True))
        assert group is not None
        qtbot.waitUntil(lambda: len(done) == 1, timeout=1000)
        assert lbl.pos() == end
        assert lbl.graphicsEffect().opacity() == 1.0
    finally:
        Motion.set_enabled(False)


def test_animate_value_instant_and_animated(qtbot):
    w = QWidget()
    qtbot.addWidget(w)

    vals = []
    done = []

    # Instant when disabled
    Motion.set_enabled(False)
    anim = animate_value(w, 0.0, 100.0, duration_ms=100, on_update=vals.append, on_finished=lambda: done.append(True))
    assert anim is None
    assert vals == [100.0]
    assert done == [True]

    # Animated when enabled
    vals.clear()
    done.clear()
    Motion.set_enabled(True)
    try:
        anim = animate_value(w, 0.0, 100.0, duration_ms=60, on_update=vals.append, on_finished=lambda: done.append(True))
        assert anim is not None
        qtbot.waitUntil(lambda: len(done) == 1, timeout=1000)
        assert vals[-1] == 100.0
    finally:
        Motion.set_enabled(False)


def test_toggle_easing_and_motion(qtbot):
    t = Toggle(checked=False)
    qtbot.addWidget(t)
    t.show()
    qtbot.waitExposed(t)

    assert not t.isChecked() and t.position == 0.0
    t.setChecked(True)
    qtbot.waitUntil(lambda: t.position == 1.0, timeout=1000)
    assert t.position == 1.0


def test_tooltip_slide_and_fade_integration(qtbot):
    btn = QPushButton("Target")
    qtbot.addWidget(btn)
    btn.show()
    qtbot.waitExposed(btn)

    tip = Tooltip(btn, "Help text")
    Motion.set_enabled(True)
    try:
        tip.show_now()
        assert tip.tip is not None
        qtbot.wait(100)
        assert tip.tip.isVisible()
        tip.hide_tip()
        assert tip.tip is None
    finally:
        Motion.set_enabled(False)


def test_toast_card_slide_and_fade_on_dismiss_when_motion_enabled(qtbot):
    from qt_ui.toast import ToastCard
    win = QWidget()
    win.resize(600, 400)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)

    card = ToastCard("Notice", "Body text", duration_ms=0, parent=win)
    card.show()
    qtbot.waitExposed(card)

    closed = []
    card.closed.connect(closed.append)
    Motion.set_enabled(True)
    try:
        card.dismiss()
        assert getattr(card, "_slide_fade_group", None) is not None
        qtbot.waitUntil(lambda: len(closed) == 1, timeout=1000)
        import shiboken6; assert not shiboken6.isValid(card) or not card.isVisible()
    finally:
        Motion.set_enabled(False)


def test_toast_host_slide_in_when_motion_enabled(qtbot):
    from qt_ui.toast import ToastHost
    win = QWidget()
    win.resize(600, 400)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)

    host = ToastHost(win)
    Motion.set_enabled(True)
    try:
        card = host.show_toast("Title", "Message", duration_ms=0)
        assert getattr(card, "_slide_fade_group", None) is not None
        qtbot.waitUntil(lambda: getattr(card, "_slide_fade_group", None) is None, timeout=1000)
        assert card.isVisible()
    finally:
        Motion.set_enabled(False)


def test_themed_dialog_accordion_animates_when_motion_enabled(qtbot):
    from qt_ui.dialogs import ThemedDialog
    dlg = ThemedDialog(None, "Error", "Summary line\nTraceback details here")
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)

    assert not dlg.details_edit.isVisible()
    Motion.set_enabled(True)
    try:
        dlg.toggle_details_btn.click()
        assert dlg.details_edit.isVisible()
        qtbot.waitUntil(lambda: getattr(dlg.details_edit, "_height_anim", None) is None, timeout=1000)
        assert dlg.details_edit.height() >= 100
        dlg.toggle_details_btn.click()
        qtbot.waitUntil(lambda: not dlg.details_edit.isVisible(), timeout=1000)
    finally:
        Motion.set_enabled(False)
        dlg.accept()


def test_animated_stacked_widget_crossfades_when_motion_enabled(qtbot):
    from qt_ui.shell import AnimatedStackedWidget
    stack = AnimatedStackedWidget()
    qtbot.addWidget(stack)
    w1 = QLabel("Page 1")
    w2 = QLabel("Page 2")
    stack.addWidget(w1)
    stack.addWidget(w2)
    stack.show()
    qtbot.waitExposed(stack)

    assert stack.currentIndex() == 0
    Motion.set_enabled(True)
    try:
        stack.setCurrentIndex(1)
        assert stack.currentIndex() == 1
        qtbot.waitUntil(lambda: w2.graphicsEffect() is None, timeout=1000)
    finally:
        Motion.set_enabled(False)


def test_vod_strip_slide_reveal_and_clear_when_motion_enabled(qtbot):
    from qt_ui.shell import VodStrip
    import types
    parent = QWidget()
    parent.resize(600, 400)
    qtbot.addWidget(parent)
    strip = VodStrip(parent)
    parent.show()
    qtbot.waitExposed(parent)

    assert not strip.isVisible()
    Motion.set_enabled(True)
    try:
        sample = types.SimpleNamespace(url="https://twitch.tv/videos/123", vod_id="123", title="Test VOD", uploader="Tester", upload_date="2026-01-01", duration=3600, muted=[])
        strip.set_vod(sample)
        assert strip.isVisible()
        qtbot.waitUntil(lambda: getattr(strip, "_height_anim", None) is None, timeout=1000)
        assert strip.height() == strip.HEIGHT

        strip.clear()
        qtbot.waitUntil(lambda: not strip.isVisible(), timeout=1000)
    finally:
        Motion.set_enabled(False)


def test_activity_pill_fade_when_motion_enabled(qtbot):
    from qt_ui.main_window import MainWindow
    win = MainWindow(settings={}, client=None)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)

    assert not win.activity_pill.isVisible()
    Motion.set_enabled(True)
    try:
        win._set_activity_pill_visible(True)
        assert win.activity_pill.isVisible()
        qtbot.waitUntil(lambda: getattr(win.activity_pill, "_opacity_anim", None) is None, timeout=1000)
        assert win.activity_pill.graphicsEffect().opacity() == 1.0

        win._set_activity_pill_visible(False)
        qtbot.waitUntil(lambda: not win.activity_pill.isVisible(), timeout=1000)
    finally:
        Motion.set_enabled(False)


def test_queue_delegate_indeterminate_shimmer_when_motion_enabled(qtbot):
    from qt_ui.tabs.queue import QueueRowDelegate, QueueTab
    from qt_ui.bridge import Bridge
    from PySide6.QtWidgets import QTableView

    table = QTableView()
    qtbot.addWidget(table)
    table.show()
    qtbot.waitExposed(table)

    tab = QueueTab(Bridge(table))
    delegate = QueueRowDelegate(table, tab)

    Motion.set_enabled(True)
    try:
        delegate._ensure_shimmer()
        assert delegate._shimmer_timer is not None
        assert delegate._shimmer_timer.isActive()
        prev = delegate._shimmer_phase
        qtbot.wait(60)
        assert delegate._shimmer_phase != prev
    finally:
        if delegate._shimmer_timer:
            delegate._shimmer_timer.stop()
        Motion.set_enabled(False)


def test_channel_delegate_live_marker_pulses_when_motion_enabled(qtbot):
    from qt_ui.search_models import ChannelDelegate
    from PySide6.QtWidgets import QStyleOptionViewItem
    from PySide6.QtGui import QPainter, QImage, QStandardItemModel, QStandardItem
    from qt_ui.search_models import CHANNEL_ROLE

    delegate = ChannelDelegate(live_marker=True)
    img = QImage(200, 40, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)

    model = QStandardItemModel()
    item = QStandardItem("streamer")
    item.setData({"name": "streamer", "live": True}, CHANNEL_ROLE)
    model.appendRow(item)
    idx = model.index(0, 0)

    opt = QStyleOptionViewItem()
    opt.rect = img.rect()

    Motion.set_enabled(True)
    try:
        delegate.paint(p, opt, idx)
    finally:
        p.end()
        Motion.set_enabled(False)
