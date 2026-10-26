"""The Qt widget kit (Phase 2, qt_ui/widgets.py). pytest-qt on the offscreen platform; no display needed.

Ported from the behaviours of ``ui/widgets.py`` that the tkinter tests cover (``test_gui_theme_and_icon.py``,
``test_gui_options_tab.py``, ``test_gui_search_tab.py``, ``test_gui_plan_redesign.py``, ``test_gui_final_pass.py``).
Where the stylesheet matters the tests look at real pixels (``widget.grab()``), so a missing rule fails them.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QStandardItemModel, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QLabel, QLineEdit, QListView, QPushButton, QTableView, QVBoxLayout, QWidget,
)

import core.palette as pal  # noqa: E402
from qt_ui import theme  # noqa: E402
from qt_ui import widgets as w  # noqa: E402
from qt_ui.widgets import (  # noqa: E402
    Card, Collapsible, EmptyState, InfoIcon, ScrollFrame, ScrollPage, SettingRow, SideNav, Toggle, TokenChips,
    Tooltip,
)


# --------------------------------------------------------------------------- helpers
@pytest.fixture(autouse=True)
def themed(qtbot):
    app = QApplication.instance()
    saved = (app.palette(), app.font(), app.styleSheet())
    theme.apply_theme(app)
    yield app
    app.setStyleSheet(saved[2])
    app.setPalette(saved[0])
    app.setFont(saved[1])


def shown(qtbot, widget, size=None, active=False):
    qtbot.addWidget(widget)
    if size:
        widget.resize(*size)
    widget.show()
    qtbot.waitExposed(widget)
    if active:
        widget.activateWindow()
        qtbot.waitUntil(widget.isActiveWindow, timeout=2000)
    return widget


def pixel(widget, x, y) -> str:
    """The colour of one pixel of the widget as it is drawn (``#rrggbb``)."""
    return widget.grab().toImage().pixelColor(x, y).name()


def near(colour: str, expected: str, tol: int = 6) -> bool:
    a, b = QColor(colour), QColor(expected)
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) <= tol


def settle(qtbot, ms=30):
    qtbot.wait(ms)


# =========================================================================== Toggle
def test_a_toggle_starts_in_the_state_it_was_given(qtbot):
    off, on = Toggle(), Toggle(True)
    qtbot.addWidget(off)
    qtbot.addWidget(on)
    assert not off.isChecked() and off.position == 0.0
    assert on.isChecked() and on.position == 1.0


def test_a_click_flips_the_toggle_and_runs_the_command_once(qtbot):
    t = shown(qtbot, Toggle())
    clicked, toggled = [], []
    t.clicked.connect(lambda checked, log=clicked: log.append(checked))
    t.toggled.connect(toggled.append)
    qtbot.mouseClick(t, Qt.MouseButton.LeftButton)
    assert t.isChecked() and clicked == [True] and toggled == [True]
    qtbot.mouseClick(t, Qt.MouseButton.LeftButton)
    assert not t.isChecked() and clicked == [True, False] and toggled == [True, False]


@pytest.mark.parametrize("key", [Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_space_and_enter_flip_the_toggle(qtbot, key):
    t = shown(qtbot, Toggle())
    clicked = []
    t.clicked.connect(lambda checked, log=clicked: log.append(checked))
    qtbot.keyClick(t, key)
    assert t.isChecked() and clicked == [True]
    qtbot.keyClick(t, key)
    assert not t.isChecked() and clicked == [True, False]


def test_other_keys_do_nothing(qtbot):
    t = shown(qtbot, Toggle())
    qtbot.keyClick(t, Qt.Key.Key_A)
    qtbot.keyClick(t, Qt.Key.Key_Escape)
    assert not t.isChecked()


def test_setting_the_value_from_code_follows_without_running_the_command(qtbot):
    t = shown(qtbot, Toggle())
    clicked, toggled = [], []
    t.clicked.connect(lambda checked, log=clicked: log.append(checked))
    t.toggled.connect(toggled.append)
    t.setChecked(True)  # changed from code: the switch follows (animated), the command is not called
    assert toggled == [True] and clicked == []
    qtbot.waitUntil(lambda: t.position == 1.0, timeout=2000)
    t.setChecked(False)
    qtbot.waitUntil(lambda: t.position == 0.0, timeout=2000)
    assert clicked == []


def test_the_knob_slides_instead_of_jumping(qtbot):
    t = shown(qtbot, Toggle())
    seen = []
    t.setChecked(True)
    assert t.is_animating()
    qtbot.waitUntil(lambda: (seen.append(t.position), t.position == 1.0)[1], timeout=2000)
    assert 0.0 <= min(seen) and max(seen) == 1.0
    assert not t.is_animating()


def test_a_hidden_toggle_jumps_straight_to_the_new_position(qtbot):
    t = Toggle()
    qtbot.addWidget(t)
    t.setChecked(True)
    assert t.position == 1.0 and not t.is_animating()


def test_a_disabled_toggle_ignores_clicks_and_keys(qtbot):
    t = shown(qtbot, Toggle())
    clicked = []
    t.clicked.connect(lambda checked, log=clicked: log.append(checked))
    t.setEnabled(False)
    qtbot.mouseClick(t, Qt.MouseButton.LeftButton)
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Return):
        qtbot.keyClick(t, key)
    assert not t.isChecked() and clicked == []
    t.setEnabled(True)
    qtbot.mouseClick(t, Qt.MouseButton.LeftButton)
    assert t.isChecked() and clicked == [True]


def test_the_cursor_is_a_hand_only_while_it_can_be_clicked(qtbot):
    t = shown(qtbot, Toggle())
    assert t.cursor().shape() == Qt.CursorShape.PointingHandCursor
    t.setEnabled(False)
    assert t.cursor().shape() == Qt.CursorShape.ArrowCursor
    t.setEnabled(True)
    assert t.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_a_toggle_can_take_the_focus_by_tab_and_by_click(qtbot):
    t = Toggle()
    qtbot.addWidget(t)
    assert t.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_the_switch_is_42_by_24(qtbot):
    t = shown(qtbot, Toggle())
    assert (t.width(), t.height()) == (42, 24) and (Toggle.W, Toggle.H) == (42, 24)


def test_the_track_colours_are_the_palette_ones(qtbot):
    off, on = shown(qtbot, Toggle()), shown(qtbot, Toggle(True))
    assert off.track_colour().name() == pal.BG3 and on.track_colour().name() == pal.ACCENT
    off.set_hovered(True)
    on.set_hovered(True)
    assert off.track_colour().name() == "#4a4d55" and on.track_colour().name() == pal.ACCENT_HOVER
    off.set_hovered(False)
    on.setEnabled(False)
    assert on.track_colour().name() == "#4a3a78"
    off.setEnabled(False)
    assert off.track_colour().name() == pal.BG3


def test_the_switch_is_drawn_in_those_colours(qtbot):
    off, on = shown(qtbot, Toggle()), shown(qtbot, Toggle(True))
    # right end of the track, away from the knob when off; left end when on
    assert near(pixel(off, 36, 12), pal.BG3) and near(pixel(on, 5, 12), pal.ACCENT)
    # the knob: at the left when off, at the right when on (white)
    assert near(pixel(off, 12, 12), pal.WHITE) and near(pixel(on, 30, 12), pal.WHITE)
    on.setEnabled(False)
    assert near(pixel(on, 30, 12), pal.DISABLED) and near(pixel(on, 5, 12), "#4a3a78")


def test_the_toggle_draws_a_focus_ring_only_while_focused(qtbot):
    t = shown(qtbot, Toggle(), active=True)
    t.clearFocus()  # (a lone widget gets the focus when its window is activated)
    # the ring is a 1 px line in ACCENT_HOVER, one pixel inside the track (offscreen the pointer may rest on the
    # switch, so compare with whatever colour the track has right now)
    assert near(pixel(t, 21, 1), t.track_colour().name())
    t.setFocus(Qt.FocusReason.TabFocusReason)
    qtbot.waitUntil(t.hasFocus, timeout=2000)
    assert near(pixel(t, 21, 1), pal.ACCENT_HOVER)
    t.clearFocus()
    assert near(pixel(t, 21, 1), t.track_colour().name())
    t.setFocus(Qt.FocusReason.TabFocusReason)
    t.setEnabled(False)  # a disabled switch shows no ring
    assert not near(pixel(t, 21, 1), pal.ACCENT_HOVER)


def test_destroying_a_toggle_in_the_middle_of_its_animation_is_harmless(qtbot):
    t = shown(qtbot, Toggle())
    t.setChecked(True)
    assert t.is_animating()
    t.deleteLater()
    qtbot.wait(150)  # a timer or animation that outlived the widget would raise here (pytest-qt reports it)


def test_mix_blends_two_colours():
    assert w._mix("#000000", "#ffffff", 0.0).name() == "#000000"
    assert w._mix("#000000", "#ffffff", 1.0).name() == "#ffffff"
    assert w._mix("#000000", "#ffffff", 0.5).name() in ("#808080", "#7f7f7f")


# =========================================================================== Tooltip and info icon
def _enter(widget):
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Enter))


def _leave(widget):
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))


def test_a_tooltip_shows_and_hides(qtbot):
    lbl = shown(qtbot, QLabel("hover me"))
    tip = Tooltip(lbl, "explanation")
    assert tip.tip is None
    tip.show_now()
    assert tip.tip is not None and tip.tip.text() == "explanation" and tip.tip.isVisible()
    tip.hide_tip()
    assert tip.tip is None
    tip.hide_tip()  # harmless twice


def test_a_tooltip_appears_after_the_pointer_rests_and_not_before(qtbot):
    lbl = shown(qtbot, QLabel("hover me"))
    tip = Tooltip(lbl, "explanation")
    _enter(lbl)
    assert tip.tip is None  # the delay (450 ms) has not passed
    qtbot.waitUntil(lambda: tip.tip is not None, timeout=3000)
    assert Tooltip.DELAY == 450


@pytest.mark.parametrize("how", ["leave", "press", "hide"])
def test_a_tooltip_goes_away_when_the_pointer_leaves_a_button_is_pressed_or_the_widget_hides(qtbot, how):
    lbl = shown(qtbot, QLabel("hover me"))
    tip = Tooltip(lbl, "explanation")
    tip.show_now()
    assert tip.tip is not None
    if how == "leave":
        _leave(lbl)
    elif how == "press":
        qtbot.mouseClick(lbl, Qt.MouseButton.LeftButton)
    else:
        lbl.hide()
    assert tip.tip is None


def test_leaving_before_the_delay_cancels_the_tooltip(qtbot):
    lbl = QLabel("hover me")
    lbl.move(300, 200)  # away from the (offscreen) mouse pointer, which would send a real Enter of its own
    shown(qtbot, lbl)
    tip = Tooltip(lbl, "explanation")
    _enter(lbl)
    _leave(lbl)
    qtbot.wait(Tooltip.DELAY + 150)
    assert tip.tip is None


def test_a_tooltip_without_text_never_shows(qtbot):
    lbl = shown(qtbot, QLabel("x"))
    tip = Tooltip(lbl, "")
    tip.show_now()
    assert tip.tip is None


def test_a_long_tooltip_wraps_at_380_and_a_short_one_stays_narrow(qtbot):
    lbl = shown(qtbot, QLabel("x"))
    short = Tooltip(lbl, "Short.")
    short.show_now()
    assert short.tip.width() < 150
    short.hide_tip()
    long = Tooltip(lbl, "A long explanation that goes on and on. " * 12)
    long.show_now()
    assert long.tip.width() <= 380 and long.tip.height() > 3 * short_height(qtbot)
    wide = Tooltip(lbl, "word " * 100, wraplength=200)
    wide.show_now()
    assert wide.tip.width() <= 200
    for t in (long, wide):
        t.hide_tip()


def short_height(qtbot) -> int:
    lbl = QLabel("x")
    qtbot.addWidget(lbl)
    return lbl.fontMetrics().height()


def test_the_tooltip_sits_under_the_widget_and_inside_the_screen(qtbot):
    lbl = QLabel("edge")
    qtbot.addWidget(lbl)
    area = lbl.screen().availableGeometry()
    lbl.move(area.right() - 30, area.top() + 40)  # at the right edge: the tip must be pulled back in
    lbl.show()
    qtbot.waitExposed(lbl)
    tip = Tooltip(lbl, "A long explanation that goes on and on. " * 4)
    tip.show_now()
    top_left = lbl.mapToGlobal(QPoint(0, lbl.height()))
    assert tip.tip.y() == top_left.y() + 6
    assert tip.tip.x() + tip.tip.width() <= area.right() - 8 + 1
    tip.hide_tip()


def test_the_tooltip_is_a_dark_bubble(qtbot):
    lbl = shown(qtbot, QLabel("x"))
    tip = Tooltip(lbl, "text")
    tip.show_now()
    assert tip.tip.objectName() == "tooltipBubble"
    assert near(pixel(tip.tip, 3, 3), pal.BG3) or near(pixel(tip.tip, 3, 3), pal.BORDER)
    assert near(pixel(tip.tip, tip.tip.width() // 2, 4), pal.BG3)
    tip.hide_tip()


def test_the_info_icon_shows_its_text_as_a_tooltip(qtbot):
    icon = shown(qtbot, InfoIcon("What this does."))
    assert icon.tooltip.text == "What this does." and icon.text == "What this does."
    assert icon.accessibleDescription() == "What this does."
    icon.tooltip.show_now()
    assert icon.tooltip.tip.text() == "What this does."
    icon.tooltip.hide_tip()


def test_the_info_icon_lights_up_while_hovered(qtbot):
    icon = shown(qtbot, InfoIcon("x"))
    assert near(pixel(icon, 0, 5), pal.BORDER)
    _enter(icon)
    assert near(pixel(icon, 0, 5), pal.ACCENT)
    _leave(icon)
    assert near(pixel(icon, 0, 5), pal.BORDER)
    assert icon.cursor().shape() == Qt.CursorShape.WhatsThisCursor
    assert icon.focusPolicy() == Qt.FocusPolicy.NoFocus  # nothing decorative in the Tab order


# =========================================================================== Card and SettingRow
def test_a_card_collects_setting_rows(qtbot):
    card = shown(qtbot, Card("Output", "where files go"))
    r1 = card.add_row("Name", "hint", info="long text")
    r2 = card.add_row("Other", divider=False)
    assert isinstance(r1, SettingRow) and r2.divider is None and r1.divider is not None
    r1.add_control(Toggle())
    assert card.rows == [r1, r2] and r1.parent() is card.body and card.body_layout.count() == 2
    assert card.title_label.text() == "Output" and card.subtitle_label.text() == "where files go"


def test_a_card_without_a_title_or_subtitle_has_no_such_labels(qtbot):
    plain = Card()
    titled = Card("Only a title")
    qtbot.addWidget(plain)
    qtbot.addWidget(titled)
    assert plain.title_label is None and plain.subtitle_label is None
    assert titled.title_label is not None and titled.subtitle_label is None


def test_a_card_can_hold_any_widget(qtbot):
    card = shown(qtbot, Card("T"))
    edit = card.add_widget(QLineEdit("free"))
    assert edit.parent() is card.body


def test_a_card_is_a_bordered_surface(qtbot):
    card = shown(qtbot, Card("T"), size=(300, 120))
    assert card.objectName() == "card"
    assert near(pixel(card, 150, 0), pal.BORDER) and near(pixel(card, 150, 100), pal.BG2)


def test_a_card_pads_its_content(qtbot):
    card = Card("T", padding=20)
    qtbot.addWidget(card)
    m = card.body_layout.contentsMargins()
    assert (m.left(), m.right()) == (20, 20)


def test_a_setting_row_has_name_hint_and_info(qtbot):
    row = shown(qtbot, SettingRow("Threads", "How many at once.", info="Long text."))
    assert row.title_label.text() == "Threads" and row.hint_label.text() == "How many at once."
    assert isinstance(row.info, InfoIcon) and row.info.text == "Long text."
    bare = SettingRow("Just a name")
    qtbot.addWidget(bare)
    assert bare.hint_label is None and bare.info is None


def test_the_name_is_bold_and_the_hint_muted(qtbot):
    row = shown(qtbot, SettingRow("Threads", "How many at once."))
    assert row.title_label.font().bold() or "bold" in row.title_label.styleSheet() or \
        row.title_label.property("role") == "rowtitle"
    assert row.hint_label.property("role") == "muted"


def _brightest(widget, child) -> QColor:
    """The brightest pixel of ``child`` as drawn inside ``widget`` (the colour of its text, antialiased)."""
    img = widget.grab().toImage()
    box = child.geometry().translated(child.parentWidget().mapTo(widget, QPoint(0, 0)))
    best, best_sum = QColor("#000000"), -1
    for x in range(box.left(), box.right() + 1):
        for y in range(box.top(), box.bottom() + 1):
            c = img.pixelColor(x, y)
            if c.red() + c.green() + c.blue() > best_sum:
                best, best_sum = c, c.red() + c.green() + c.blue()
    return best


def test_the_hint_is_drawn_in_the_muted_colour_and_the_name_in_the_bright_one(qtbot):
    card = Card()
    row = card.add_row("Threads", "How many at once.")
    shown(qtbot, card, size=(400, 100))
    hint, name = _brightest(card, row.hint_label), _brightest(card, row.title_label)
    assert near(hint.name(), pal.MUTED, tol=24) and near(name.name(), pal.FG, tol=24)


def test_the_control_sits_on_the_right_and_the_text_on_the_left(qtbot):
    row = SettingRow("Name", "hint")
    toggle = row.add_control(Toggle())
    shown(qtbot, row, size=(700, 80))
    text_left = row.title_label.mapTo(row, QPoint(0, 0)).x()
    assert text_left == 0
    assert toggle.mapTo(row, QPoint(0, 0)).x() + toggle.width() == row.width()
    text_mid = row.title_label.parentWidget().geometry().center().y()
    assert abs(toggle.mapTo(row, QPoint(0, 0)).y() + toggle.height() / 2 - text_mid) <= 2  # centred on the text


def test_the_divider_is_a_one_pixel_hairline_under_the_row(qtbot):
    row = shown(qtbot, SettingRow("Name", "hint"), size=(500, 90))
    assert row.divider.height() == 1 and row.divider.width() == row.width()
    y = row.divider.mapTo(row, QPoint(0, 0)).y()
    assert y > row.title_label.geometry().bottom() and near(pixel(row, 100, y), pal.BORDER)
    assert y == row.divider.parent().y() + 10  # 10 px of air above it, like tkinter's pady=(10, 0)


def test_a_row_without_a_divider_draws_none(qtbot):
    row = shown(qtbot, SettingRow("Name", "hint", divider=False), size=(500, 90))
    assert row.divider is None
    assert all(not near(pixel(row, 100, y), pal.BORDER) for y in range(row.height()))


def test_the_below_area_is_full_width_under_the_text(qtbot):
    row = SettingRow("Template", "File name")
    field = row.add_below(QLineEdit("{streamer}"))
    row.add_control(Toggle())
    shown(qtbot, row, size=(600, 140))
    assert row.below.width() == row.width() and field.width() == row.width()
    assert row.below.geometry().top() >= row.title_label.geometry().bottom()


def test_a_long_hint_wraps_and_the_row_grows_to_show_all_of_it(qtbot):
    long_hint = "This hint is long enough that it has to wrap onto several lines. " * 4
    row = SettingRow("Name", long_hint)
    one = SettingRow("Name", "Short.")
    row.add_control(Toggle())
    shown(qtbot, row, size=(700, 300))
    shown(qtbot, one, size=(700, 300))
    assert row.hint_label.wordWrap() and row.hint_label.width() <= SettingRow.HINT_MAX_WIDTH
    line = one.hint_label.height()
    assert row.hint_label.height() >= 3 * (line - 2)
    assert row.hint_label.height() >= row.hint_label.heightForWidth(row.hint_label.width())  # nothing cut off
    assert row.sizeHint().height() > one.sizeHint().height()


# =========================================================================== Collapsible
def test_advanced_starts_collapsed_and_opens_on_click(qtbot):
    adv = Collapsible("Advanced")
    adv.add_row("Hidden", "only when opened")
    shown(qtbot, adv)
    toggles = []
    adv.toggled.connect(toggles.append)
    assert not adv.opened and not adv.body.isVisible()
    assert adv.header.text().startswith("\u25b8")
    qtbot.mouseClick(adv.header, Qt.MouseButton.LeftButton)
    assert adv.opened and adv.body.isVisible()
    assert adv.header.text().startswith("\u25be")
    qtbot.mouseClick(adv.header, Qt.MouseButton.LeftButton)
    assert not adv.opened and not adv.body.isVisible()
    assert toggles == [True, False]


def test_the_header_shows_the_title_and_the_hint(qtbot):
    plain = Collapsible("Advanced")
    hinted = Collapsible("Advanced", hint="rarely needed", opened=True)
    qtbot.addWidget(plain)
    qtbot.addWidget(hinted)
    assert plain.header.text() == "\u25b8  Advanced"
    assert hinted.header.text() == "\u25be  Advanced   \u00b7   rarely needed"


def test_the_header_is_a_real_button_that_space_opens(qtbot):
    adv = shown(qtbot, Collapsible("Advanced"), active=True)
    assert adv.header.focusPolicy() & Qt.FocusPolicy.TabFocus
    adv.header.setFocus()
    qtbot.keyClick(adv.header, Qt.Key.Key_Space)
    assert adv.opened


def test_a_collapsible_can_start_opened_and_be_set_from_code(qtbot):
    adv = shown(qtbot, Collapsible("Advanced", opened=True))
    assert adv.opened and adv.body.isVisible()
    signals = []
    adv.toggled.connect(signals.append)
    adv.set_opened(True)  # no change: no signal
    adv.set_opened(False)
    assert signals == [False] and not adv.body.isVisible()


def test_rows_go_into_the_body_like_in_a_card(qtbot):
    adv = Collapsible("Advanced")
    r = adv.add_row("Name", "hint", info="long", divider=False)
    qtbot.addWidget(adv)
    assert isinstance(r, SettingRow) and r.parent() is adv.body and adv.rows == [r] and r.divider is None


def test_opening_advanced_makes_the_page_scroll_to_the_new_content(qtbot):
    frame = ScrollFrame()
    adv = Collapsible("Advanced")
    for i in range(8):
        adv.add_row(f"Row {i}", "A hint line.").add_control(Toggle())
    frame.body_layout.addWidget(adv)
    frame.body_layout.addStretch(1)
    shown(qtbot, frame, size=(500, 220))
    before = frame.verticalScrollBar().maximum()
    adv.header.click()
    qtbot.waitUntil(lambda: frame.verticalScrollBar().maximum() > before, timeout=2000)
    assert frame.is_scrollable()
    adv.header.click()
    qtbot.waitUntil(lambda: frame.verticalScrollBar().maximum() == before, timeout=2000)


# =========================================================================== SideNav
ITEMS = [("output", "Output"), ("cuts", "Cuts"), ("chat", "Chat"), ("tools", "Tools")]


def test_the_sidebar_has_one_button_per_entry_in_order(qtbot):
    nav = shown(qtbot, SideNav(ITEMS))
    assert nav.keys == ["output", "cuts", "chat", "tools"] and list(nav.buttons) == nav.keys
    assert [b.text() for b in nav.buttons.values()] == ["Output", "Cuts", "Chat", "Tools"]
    assert nav.current is None and all(b.property("selected") is False for b in nav.buttons.values())


def test_selecting_an_entry_tints_it_and_tells_the_owner(qtbot):
    nav = shown(qtbot, SideNav(ITEMS))
    got = []
    nav.selected.connect(got.append)
    for key in nav.keys:
        nav.select(key)
        assert nav.current == key and got[-1] == key
        assert nav.buttons[key].property("selected") is True
        assert all(b.property("selected") is False for k, b in nav.buttons.items() if k != key)
    assert got == nav.keys


def test_clicking_a_button_selects_it(qtbot):
    nav = shown(qtbot, SideNav(ITEMS))
    got = []
    nav.selected.connect(got.append)
    qtbot.mouseClick(nav.buttons["chat"], Qt.MouseButton.LeftButton)
    assert nav.current == "chat" and got == ["chat"]


def test_selecting_the_same_entry_again_tells_the_owner_again(qtbot):
    nav = shown(qtbot, SideNav(ITEMS))
    got = []
    nav.selected.connect(got.append)
    nav.select("cuts")
    nav.select("cuts")
    assert got == ["cuts", "cuts"]  # like the tkinter SideNav: the command runs on every select


def test_an_unknown_key_is_ignored(qtbot):
    nav = shown(qtbot, SideNav(ITEMS))
    got = []
    nav.selected.connect(got.append)
    nav.select("nope")
    assert nav.current is None and got == []


def test_the_selected_entry_is_purple_tinted_and_the_others_flat(qtbot):
    nav = shown(qtbot, SideNav(ITEMS))
    nav.select("cuts")
    b_sel, b_other = nav.buttons["cuts"], nav.buttons["output"]
    assert near(pixel(b_sel, 3, 3), pal.ACCENT_DIM) and near(pixel(b_other, 3, 3), pal.BG2)
    nav.select("output")
    assert near(pixel(nav.buttons["output"], 3, 3), pal.ACCENT_DIM) and near(pixel(nav.buttons["cuts"], 3, 3), pal.BG2)


def test_arrow_keys_move_through_the_sidebar(qtbot):
    nav = shown(qtbot, SideNav(ITEMS), active=True)
    nav.select("output")
    nav.buttons["output"].setFocus()
    qtbot.keyClick(nav.buttons["output"], Qt.Key.Key_Down)  # what the Down key does on the first entry
    assert nav.current == "cuts"
    qtbot.keyClick(nav.buttons["cuts"], Qt.Key.Key_Up)
    assert nav.current == "output"
    qtbot.keyClick(nav.buttons["output"], Qt.Key.Key_Up)  # nothing above the first entry
    assert nav.current == "output"
    nav.select("tools")
    qtbot.keyClick(nav.buttons["tools"], Qt.Key.Key_Down)  # nothing below the last one
    assert nav.current == "tools"


def test_the_arrow_keys_move_the_focus_with_the_selection(qtbot):
    nav = shown(qtbot, SideNav(ITEMS), active=True)
    nav.select("output")
    nav.buttons["output"].setFocus()
    qtbot.keyClick(nav.buttons["output"], Qt.Key.Key_Down)
    qtbot.waitUntil(nav.buttons["cuts"].hasFocus, timeout=2000)


def test_every_entry_is_a_tab_stop_and_space_picks_it(qtbot):
    nav = shown(qtbot, SideNav(ITEMS), active=True)
    assert all(b.focusPolicy() & Qt.FocusPolicy.TabFocus for b in nav.buttons.values())
    nav.buttons["chat"].setFocus()
    qtbot.keyClick(nav.buttons["chat"], Qt.Key.Key_Space)
    assert nav.current == "chat"


def test_the_sidebar_is_a_surface_with_the_entries_at_the_top(qtbot):
    nav = shown(qtbot, SideNav(ITEMS), size=(200, 500))
    assert nav.objectName() == "sideNav" and near(pixel(nav, 2, 2), pal.BG2)
    first, last = nav.buttons["output"], nav.buttons["tools"]
    assert first.y() < 20 and last.y() + last.height() < 250  # packed at the top, not spread over the height


# =========================================================================== TokenChips
TOKENS = ["streamer", "date", "id", "title", "n", "total", "start", "end"]


def chips_for(qtbot, text="", tokens=TOKENS, **kw):
    entry = QLineEdit(text)
    chips = TokenChips(entry, tokens, **kw)
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.addWidget(entry)
    lay.addWidget(chips)
    shown(qtbot, host, active=True)
    chips.host = host  # keep the Python wrapper of the parent alive
    return entry, chips


def chip(chips, token):
    return next(b for b in chips.chips if b.text() == "{" + token + "}")


def test_there_is_a_chip_per_token_laid_out_in_rows_of_six(qtbot):
    entry, chips = chips_for(qtbot)
    assert [b.text() for b in chips.chips] == ["{" + t + "}" for t in TOKENS]
    pos = [chips.layout().getItemPosition(i)[:2] for i in range(len(TOKENS))]
    assert pos == [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 0), (1, 1)]
    _e2, narrow = chips_for(qtbot, tokens=TOKENS, per_row=3)
    assert narrow.layout().getItemPosition(3)[:2] == (1, 0)


def test_clicking_a_chip_inserts_the_token_at_the_cursor(qtbot):
    entry, chips = chips_for(qtbot, "A - B")
    entry.setCursorPosition(4)  # between «A - » and «B»
    chip(chips, "title").click()
    assert entry.text() == "A - {title}B" and entry.cursorPosition() == len("A - {title}")


def test_a_chip_replaces_the_selected_text(qtbot):
    entry, chips = chips_for(qtbot, "xxx - {id}")
    entry.setSelection(0, 3)
    chip(chips, "date").click()
    assert entry.text() == "{date} - {id}"


def test_a_real_mouse_click_keeps_the_selection_to_replace(qtbot):
    entry, chips = chips_for(qtbot, "xxx - {id}")
    entry.setFocus()
    entry.setSelection(0, 3)
    qtbot.mouseClick(chip(chips, "date"), Qt.MouseButton.LeftButton)  # the chip does not steal the focus
    assert entry.text() == "{date} - {id}"


def test_chips_insert_into_an_empty_field_and_at_the_end_and_twice(qtbot):
    entry, chips = chips_for(qtbot, "")
    chip(chips, "id").click()
    assert entry.text() == "{id}"
    entry.setCursorPosition(len(entry.text()))
    chip(chips, "n").click()
    chip(chips, "total").click()
    assert entry.text() == "{id}{n}{total}"


def test_the_field_gets_the_focus_after_an_insert(qtbot):
    entry, chips = chips_for(qtbot, "x")
    chip(chips, "id").click()
    qtbot.waitUntil(entry.hasFocus, timeout=2000)


def test_a_disabled_or_read_only_field_is_left_alone(qtbot):
    entry, chips = chips_for(qtbot, "keep")
    entry.setEnabled(False)
    chips.insert("id")
    assert entry.text() == "keep"
    entry.setEnabled(True)
    entry.setReadOnly(True)
    chips.insert("id")
    assert entry.text() == "keep"
    entry.setReadOnly(False)
    chips.insert("id")
    assert entry.text() == "{id}keep" or entry.text() == "keep{id}"


def test_the_chips_can_be_switched_off_and_on(qtbot):
    entry, chips = chips_for(qtbot, "keep")
    chips.set_enabled(False)
    assert all(not b.isEnabled() for b in chips.chips)
    chip(chips, "id").click()  # a disabled button does not click
    assert entry.text() == "keep"
    chips.set_enabled(True)
    assert all(b.isEnabled() for b in chips.chips)


def test_chips_are_tab_stops_that_do_not_take_the_focus_on_click(qtbot):
    _entry, chips = chips_for(qtbot, "x")
    assert all(b.focusPolicy() == Qt.FocusPolicy.TabFocus for b in chips.chips)


def test_chips_are_small_flat_buttons(qtbot):
    _entry, chips = chips_for(qtbot, "x")
    b = chips.chips[0]
    assert b.property("variant") == "chip" and near(pixel(b, 1, 1), pal.BG3)
    chips.set_enabled(False)
    assert near(pixel(b, 1, 1), pal.BG2)


# =========================================================================== EmptyState
def a_list(qtbot, size=(500, 300)):
    view = QListView()
    view.setModel(QStandardItemModel(0, 1))
    return shown(qtbot, view, size=size)


def test_empty_state_shows_hides_and_refills(qtbot):
    es = EmptyState(a_list(qtbot))
    assert not es.shown and not es.isVisible()
    es.show_message("Title", "Body")
    assert es.shown and es.isVisible() and es.texts() == ["Title", "Body"]
    es.show_message("Other", "")  # showing again replaces the lines, never stacks them
    assert es.texts() == ["Other"]
    es.hide_message()
    es.hide_message()  # harmless twice
    assert not es.shown and not es.isVisible()


def test_empty_state_can_carry_a_button(qtbot):
    es = EmptyState(a_list(qtbot))
    clicks = []
    es.show_message("Sign in", "", button=("Sign in…", lambda: clicks.append(1)))
    assert es.button.text() == "Sign in…" and es.button.property("variant") == "accent"
    qtbot.mouseClick(es.button, Qt.MouseButton.LeftButton)
    assert clicks == [1]
    es.show_message("Again")  # a new message without a button drops the old button
    assert es.button is None


def test_empty_state_leaves_room_for_the_column_headings(qtbot):
    table = QTableView()
    table.setModel(QStandardItemModel(0, 3))
    shown(qtbot, table, size=(500, 300))
    es = EmptyState(table, top=34)
    es.show_message("x")
    assert es.geometry().y() == 34 and es.geometry().height() == table.height() - 34
    assert es.geometry().width() == table.width()


def test_empty_state_covers_the_list_and_follows_its_size(qtbot):
    view = a_list(qtbot)
    es = EmptyState(view)
    es.show_message("Title", "Body")
    assert es.parent() is view and es.geometry().size() == view.size()
    view.resize(640, 380)
    qtbot.waitUntil(lambda: es.geometry().size() == view.size(), timeout=2000)


def test_empty_state_is_centred_a_little_above_the_middle(qtbot):
    view = a_list(qtbot, size=(600, 400))
    es = EmptyState(view)
    es.show_message("Title", "Body text")
    inner = es._inner.geometry()
    assert abs(inner.center().x() - es.width() / 2) <= 2
    assert abs(inner.center().y() - es.height() * 0.42) <= 3


def test_empty_state_hides_what_is_under_it(qtbot):
    view = a_list(qtbot)
    es = EmptyState(view)
    es.show_message("Title")
    assert near(pixel(view, 4, 4), pal.BG2) and near(pixel(view, view.width() - 4, view.height() - 4), pal.BG2)
    es.hide_message()
    assert not es.isVisible()


def test_a_message_is_title_in_bold_and_muted_text(qtbot):
    es = EmptyState(a_list(qtbot))
    es.show_message("Title", "Body")
    assert es.title_label.font().bold() and not es.text_label.font().bold()
    assert es.title_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert es.text_label.property("role") == "muted"


def test_a_compact_state_wraps_narrower(qtbot):
    long_text = "A fairly long sentence that needs several lines when the space is narrow. " * 3
    wide = EmptyState(a_list(qtbot))
    narrow = EmptyState(a_list(qtbot), compact=True)
    wide.show_message("T", long_text)
    narrow.show_message("T", long_text)
    assert 190 < wide.text_label.width() <= 380
    assert narrow.text_label.width() <= 190
    assert narrow.text_label.height() > wide.text_label.height()
    assert narrow.text_label.height() >= narrow.text_label.heightForWidth(narrow.text_label.width())


def test_a_message_with_only_a_title_or_only_text_works(qtbot):
    es = EmptyState(a_list(qtbot))
    es.show_message("Only title")
    assert es.texts() == ["Only title"] and es.text_label is None
    es.show_message("", "Only text")
    assert es.texts() == ["Only text"] and es.title_label is None
    es.show_message()
    assert es.texts() == [] and es.shown


def test_the_overlay_stays_on_top_of_a_view_with_a_table(qtbot):
    table = QTableView()
    table.setModel(QStandardItemModel(0, 2))
    shown(qtbot, table, size=(500, 300))
    es = EmptyState(table, top=table.horizontalHeader().height())
    es.show_message("No VODs")
    assert es.geometry().y() == table.horizontalHeader().height()
    assert near(pixel(table, 50, 5), pal.BG3)  # the headings are not covered
    assert near(pixel(table, 250, 200), pal.BG2)


# =========================================================================== ScrollFrame and ScrollPage
def tall_page(qtbot, height, lines=40):
    page = ScrollPage()
    for i in range(lines):
        page.body_layout.addWidget(QLabel(f"line {i}"))
    page.footer_layout.addStretch(1)
    page.footer_btn = QPushButton("Add to queue")
    page.footer_layout.addWidget(page.footer_btn)
    shown(qtbot, page, size=(500, height))
    return page


def test_a_scroll_page_has_a_body_and_a_footer(qtbot):
    page = ScrollPage()
    qtbot.addWidget(page)
    assert page.body is page.scroll.body and page.body_layout is page.scroll.body_layout
    assert page.footer is not None and page.footer_line.height() == 1


def test_the_footer_stays_visible_when_the_page_scrolls(qtbot):
    page = tall_page(qtbot, 300)
    bar = page.scroll.verticalScrollBar()
    assert bar.maximum() > 0  # the content does not fit: it really scrolls
    before = page.footer_btn.mapTo(page, QPoint(0, 0))
    page.scroll.scroll_to_bottom()
    assert bar.value() == bar.maximum()
    after = page.footer_btn.mapTo(page, QPoint(0, 0))
    assert before == after  # the bar did not move
    assert page.footer.y() >= page.scroll.y() + page.scroll.height()  # under the scrolling part
    assert page.footer.y() + page.footer_btn.y() + page.footer_btn.height() <= page.height()  # inside the page


def test_the_footer_is_a_hairline_and_a_bar_at_the_bottom(qtbot):
    page = tall_page(qtbot, 300)
    assert page.footer.geometry().bottom() == page.height() - 1
    assert near(pixel(page, 250, page.footer_line.y()), pal.BORDER)
    assert page.footer_line.y() == page.footer.y() - 1


def test_the_body_fills_a_tall_window_and_scrolls_in_a_short_one(qtbot):
    short = ScrollPage()
    short.body_layout.addWidget(QLabel("only line"))
    shown(qtbot, short, size=(500, 400))
    assert not short.scroll.is_scrollable()
    assert short.body.height() == short.scroll.viewport().height()  # stretches to fill, so grid weights still grow
    tall = tall_page(qtbot, 200)
    assert tall.scroll.is_scrollable() and tall.body.height() > tall.scroll.viewport().height()


def test_there_is_no_horizontal_scroll_bar(qtbot):
    page = tall_page(qtbot, 300)
    assert page.scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_the_mouse_wheel_scrolls_the_page(qtbot):
    page = tall_page(qtbot, 300)
    view = page.scroll.viewport()
    bar = page.scroll.verticalScrollBar()
    assert bar.value() == 0
    event = QWheelEvent(QPointF(50, 50), QPointF(view.mapToGlobal(QPoint(50, 50))), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view, event)
    assert bar.value() > 0
    page.scroll.scroll_to_top()
    assert bar.value() == 0


def test_the_page_is_laid_out_on_the_background_colour(qtbot):
    page = tall_page(qtbot, 300)
    assert near(pixel(page, 490, 5), pal.BG) or near(pixel(page, 480, 150), pal.BG)


def test_the_footer_is_the_last_tab_stop_even_though_it_was_built_first(qtbot):
    page = ScrollPage()
    footer_btn = QPushButton("Add to queue")
    page.footer_layout.addWidget(footer_btn)  # the bar is built first, like in the tkinter plan tab
    edit1, edit2 = QLineEdit(), QLineEdit()
    page.body_layout.addWidget(edit1)
    page.body_layout.addWidget(edit2)
    assert page.tab_stops()[0] is footer_btn  # Qt's own order is by creation: the control case
    shown(qtbot, page)  # showing the page puts the bar behind the body
    assert page.tab_stops() == [edit1, edit2, footer_btn]


def test_tab_and_shift_tab_walk_the_page_in_that_order(qtbot):
    page = ScrollPage()
    footer_btn = QPushButton("Add to queue")
    page.footer_layout.addWidget(footer_btn)
    edit1, edit2 = QLineEdit(), QLineEdit()
    page.body_layout.addWidget(edit1)
    page.body_layout.addWidget(edit2)
    shown(qtbot, page, active=True)
    edit2.setFocus()
    qtbot.waitUntil(edit2.hasFocus, timeout=2000)
    qtbot.keyClick(edit2, Qt.Key.Key_Tab)
    qtbot.waitUntil(footer_btn.hasFocus, timeout=2000)
    qtbot.keyClick(footer_btn, Qt.Key.Key_Backtab)
    qtbot.waitUntil(edit2.hasFocus, timeout=2000)


def test_fix_tab_order_can_run_again_after_more_widgets_were_added(qtbot):
    page = ScrollPage()
    footer_btn = QPushButton("Add & start")
    page.footer_layout.addWidget(footer_btn)
    shown(qtbot, page)
    late = QLineEdit()
    page.body_layout.addWidget(late)
    page.fix_tab_order()
    assert page.tab_stops() == [late, footer_btn]


def test_the_sidebar_and_a_scroll_frame_work_together_like_the_options_tab(qtbot):
    """Switching a section scrolls the page back to the top (``test_switching_sections_scrolls_back_to_the_top``)."""
    host = QWidget()
    lay = QVBoxLayout(host)
    frame = ScrollFrame()
    nav = SideNav(ITEMS)
    lay.addWidget(nav)
    lay.addWidget(frame)
    for i in range(40):
        frame.body_layout.addWidget(QLabel(f"line {i}"))
    nav.selected.connect(lambda _key: frame.scroll_to_top())
    shown(qtbot, host, size=(400, 400))
    frame.verticalScrollBar().setValue(frame.verticalScrollBar().maximum() // 2)
    assert frame.verticalScrollBar().value() > 0
    nav.select("cuts")
    assert frame.verticalScrollBar().value() == 0


# =========================================================================== the stylesheet of the kit
def test_the_stylesheet_has_the_rules_of_the_widget_kit():
    qss = theme.build_qss()
    for selector in ('QFrame#card', 'QFrame#divider', 'QFrame#sideNav', 'QWidget#emptyState', 'QLabel#tooltipBubble',
                     'QPushButton[variant="nav"]', 'QPushButton[variant="nav"][selected="true"]',
                     'QPushButton[variant="cardghost"]', 'QPushButton[variant="chip"]', 'QLabel[role="rowtitle"]'):
        assert selector in qss, selector
    assert "$" not in qss


def test_the_advanced_header_is_a_flat_muted_button_that_lights_up(qtbot):
    adv = shown(qtbot, Collapsible("Advanced"))
    assert near(pixel(adv.header, 2, 2), pal.BG2)
    adv.header.setDown(True)
    assert near(pixel(adv.header, 2, 2), pal.PRESSED)
    adv.header.setDown(False)
