"""Every widget of the Qt widget kit (qt_ui/widgets.py) in every state, on one page. Not part of the app.

    python tools/widget_gallery.py                       # opens the gallery (needs a display)
    python tools/widget_gallery.py --screenshot out.png  # renders it offscreen to a PNG (and out_tooltip.png), exits
    python tools/widget_gallery.py --check               # builds it, pokes every widget, prints a line, exits 0 or 1

Hover and focus cannot be forced on a screenshot by a mouse, so the gallery sets them through the widgets' own
``set_hovered`` and ``setFocus``. The SideNav on the left scrolls the page to its card.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QStringListModel  # noqa: E402
from PySide6.QtGui import QStandardItemModel  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from qt_ui.theme import apply_theme  # noqa: E402
from qt_ui.widgets import (  # noqa: E402
    Card, Collapsible, EmptyState, InfoIcon, ScrollPage, SideNav, Toggle, TokenChips,
)

SECTIONS = (("toggle", "Toggle"), ("rows", "Setting rows"), ("collapsible", "Collapsible"), ("chips", "Token chips"),
            ("empty", "Empty states"), ("info", "Info icon"), ("footer", "Footer"))


def _caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "muted")
    lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    return lbl


def _with_caption(widget: QWidget, text: str, fill: bool = False) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    if fill:
        lay.addWidget(widget)
    else:
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
    lay.addWidget(_caption(text))
    return box


class Gallery(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LuckyTwitch Qt: widget gallery")
        self.resize(1020, 910)
        self.cards: dict[str, QWidget] = {}
        self.log: list[str] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        self.nav = SideNav(SECTIONS)
        root.addWidget(self.nav, 0)
        self.page = ScrollPage()
        root.addWidget(self.page, 1)
        self._build_toggles()
        self._build_rows()
        self._build_collapsible()
        self._build_chips()
        self._build_empty_states()
        self._build_info()
        self._build_footer()
        self.page.body_layout.addStretch(1)
        self.nav.selected.connect(self._go)
        self.nav.select("toggle")

    def _card(self, key: str, title: str, subtitle: str | None = None) -> Card:
        card = Card(title, subtitle)
        self.cards[key] = card
        self.page.body_layout.addWidget(card)
        return card

    def _go(self, key: str) -> None:
        self.log.append(f"nav:{key}")
        card = self.cards.get(key)
        if card is not None:
            self.page.scroll.ensureWidgetVisible(card, 0, 0)

    # ---- toggles ---- #
    def _build_toggles(self) -> None:
        card = self._card("toggle", "Toggle", "Click, Space or Enter flips it. The knob slides.")
        row = QHBoxLayout()
        row.setSpacing(24)
        self.toggles: dict[str, Toggle] = {}
        for name, caption, checked, enabled, hover in (
            ("off", "off", False, True, False), ("on", "on", True, True, False),
            ("hover_off", "hover, off", False, True, True), ("hover_on", "hover, on", True, True, True),
            ("focus", "keyboard focus", True, True, False),
            ("dis_off", "disabled, off", False, False, False), ("dis_on", "disabled, on", True, False, False),
        ):
            t = Toggle(checked)
            t.setEnabled(enabled)
            if hover:
                t.set_hovered(True)
            self.toggles[name] = t
            row.addWidget(_with_caption(t, caption))
        row.addStretch(1)
        card.body_layout.addLayout(row)
        self.toggles["off"].clicked.connect(lambda c: self.log.append(f"toggle:{c}"))

    # ---- setting rows ---- #
    def _build_rows(self) -> None:
        card = self._card("rows", "Setting rows", "Name and hint on the left, the control on the right, a divider under it.")
        r1 = card.add_row("Switch with a hint", "One short line that says what the switch does.")
        r1.add_control(Toggle(True))
        r2 = card.add_row("With the ⓘ tooltip", "Hover the i to read the long explanation.",
                          info="The long explanation lives in the tooltip. It wraps at 380 px, so even a long "
                               "sentence stays readable and never runs off the edge of the screen.")
        r2.add_control(Toggle(False))
        r3 = card.add_row("A text control", "Any widget can sit on the right.")
        field = QLineEdit("12")
        field.setFixedWidth(80)
        r3.add_control(field)
        r4 = card.add_row("A wide control below", "File name template", divider=False)
        wide = QLineEdit("{streamer} - {date} - {title}")
        r4.add_below(wide)
        self.row_without_divider = r4

    # ---- collapsible ---- #
    def _build_collapsible(self) -> None:
        card = self._card("collapsible", "Collapsible", "Closed by default; the header is a button (Tab, Space).")
        self.collapsed = Collapsible("Advanced", "rarely needed")
        self.collapsed.add_row("Hidden row", "Only shown when opened.").add_control(Toggle(False))
        card.add_widget(self.collapsed)
        self.opened = Collapsible("Advanced (opened)", opened=True)
        self.opened.add_row("Visible row", "This one starts open.").add_control(Toggle(True))
        self.opened.add_row("Last row", divider=False).add_control(Toggle(False))
        card.add_widget(self.opened)

    # ---- chips ---- #
    def _build_chips(self) -> None:
        card = self._card("chips", "Token chips", "Click inserts {token} at the cursor; a selection is replaced.")
        self.chip_entry = QLineEdit("xxx - {id}")
        self.chip_entry.setSelection(0, 3)
        card.add_widget(self.chip_entry)
        self.chips = TokenChips(self.chip_entry, ["streamer", "date", "id", "title", "n", "total", "start", "end"], per_row=6)
        card.add_widget(self.chips)
        self.off_entry = QLineEdit("disabled field")
        self.off_entry.setEnabled(False)
        card.add_widget(self.off_entry)
        self.off_chips = TokenChips(self.off_entry, ["streamer", "date", "id"])
        self.off_chips.set_enabled(False)
        card.add_widget(self.off_chips)

    # ---- empty states ---- #
    def _build_empty_states(self) -> None:
        card = self._card("empty", "Empty states", "A message over an empty list or table; the headings stay visible.")
        grid = QHBoxLayout()
        grid.setSpacing(12)
        table = QTableView()
        table.setModel(_headers_model(["Title", "Date", "Duration", "Views"]))
        table.setFixedHeight(170)
        table.setMinimumWidth(420)
        self.es_table = EmptyState(table, top=table.horizontalHeader().height() or 30)
        self.es_table.show_message("No VODs yet", "Search for a streamer and pick one to see its VODs here.")
        grid.addWidget(_with_caption(table, "title and text, headings visible", fill=True), 3)
        listing = QListView()
        listing.setModel(QStringListModel([]))
        listing.setFixedHeight(170)
        self.es_button = EmptyState(listing)
        self.es_button.show_message("Not signed in", "Sign in with Twitch to search.", button=("Sign in…", lambda: self.log.append("signin")))
        grid.addWidget(_with_caption(listing, "with a button", fill=True), 2)
        narrow = QListView()
        narrow.setModel(QStringListModel([]))
        narrow.setFixedSize(210, 170)
        self.es_compact = EmptyState(narrow, compact=True)
        self.es_compact.show_message("Nothing here", "Narrow lists wrap the text earlier.")
        grid.addWidget(_with_caption(narrow, "compact"), 0)
        card.body_layout.addLayout(grid)

    # ---- info icon ---- #
    def _build_info(self) -> None:
        card = self._card("info", "Info icon", "Rest the pointer on the i: the tooltip follows after about half a second.")
        row = QHBoxLayout()
        row.setSpacing(24)
        self.info_plain = InfoIcon("A short tooltip.")
        self.info_hover = InfoIcon("The icon turns purple while the pointer is on it.")
        self.info_hover.set_hovered(True)
        self.info_long = InfoIcon("A longer tooltip wraps at 380 px: it is a window of its own, so the width is ours "
                                  "and not the platform's. Move the pointer away and it disappears again.")
        for icon, caption in ((self.info_plain, "normal"), (self.info_hover, "hover"), (self.info_long, "long text (shown)")):
            row.addWidget(_with_caption(icon, caption))
        row.addStretch(1)
        card.body_layout.addLayout(row)

    # ---- footer ---- #
    def _build_footer(self) -> None:
        self.cards["footer"] = self.page.footer
        self.page.footer_layout.addStretch(1)
        self.page.footer_layout.addWidget(QLabel("The footer bar never scrolls away."))
        b1, b2 = QPushButton("Add to queue"), QPushButton("Add && start")  # '&' marks a shortcut in Qt: type it twice
        b2.setProperty("variant", "accent")
        self.page.footer_layout.addWidget(b1)
        self.page.footer_layout.addWidget(b2)

    def put_states_on_screen(self) -> None:
        """What a screenshot needs: focus on one switch, the long tooltip open."""
        self.activateWindow()
        self.toggles["focus"].setFocus(Qt.FocusReason.TabFocusReason)
        QApplication.processEvents()
        self.info_long.tooltip.show_now()  # last: window events would hide it again


def _headers_model(headers: list[str]) -> QStandardItemModel:
    model = QStandardItemModel(0, len(headers))
    model.setHorizontalHeaderLabels(headers)
    return model


def main(argv: list[str]) -> int:
    if "--screenshot" in argv or "--check" in argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(argv)
    apply_theme(app)
    win = Gallery()
    if "--screenshot" in argv:
        out = Path(argv[argv.index("--screenshot") + 1])
        win.resize(1180, 1700)
        win.show()
        if "--open-advanced" in argv:
            win.collapsed.set_opened(True)
        app.processEvents()
        win.put_states_on_screen()
        win.grab().save(str(out))
        tip = win.info_long.tooltip.tip
        if tip is not None:
            tip.grab().save(str(out.with_name(out.stem + "_tooltip.png")))
        print(f"saved {out}")
        return 0
    if "--check" in argv:
        win.show()
        app.processEvents()
        win.toggles["off"].click()
        win.collapsed.toggle()
        win.nav.select("empty")
        ok = (win.toggles["off"].isChecked() and win.collapsed.opened and win.log[-2:] == ["toggle:True", "nav:empty"]
              and win.es_table.shown and win.es_button.shown)
        print(f"platform={app.platformName()} widgets={'ok' if ok else 'BROKEN'}")
        return 0 if ok else 1
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
