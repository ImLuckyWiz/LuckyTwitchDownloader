"""The Search tab (Phase 4): find a streamer, pick one of their VODs.

Port of ``build_search_tab``, ``update_search_state``, ``refresh_search_empty_states``, ``refresh_recent``,
``add_recent``, ``clear_recent``, ``on_search``, ``on_search_ok``, ``on_search_err``, ``on_pick_channel``,
``load_channel``, ``load_more``, ``on_videos_ok``, ``on_videos_err``, ``on_thumb`` and ``use_selected_vod``.

The tab owns the lists (models), the state of the search (``sv_*``, the generation counter ``sv_gen`` that makes
answers of an older request harmless) and the thumbnail workers. What belongs to the whole window it asks for:
  ``get_client()``     the Twitch client (or None: nobody is signed in)
  ``reload_client()``  make the client again from what is saved (a saved session that expired)
Signals: ``status_message(str)`` (status line), ``signin_requested()`` («Sign in…»), ``vod_chosen(url)`` («Use this
VOD»: the window fills the VOD entry, selects the Plan tab and presses «Get info»).

Workers (a search, a page of VODs) are plain daemon threads that report through the Bridge
(``search_ok``, ``search_err``, ``videos_ok``, ``videos_err``, ``thumb``); the slots below run on the GUI thread.
``search_channels`` and ``fetch_videos`` are looked up in this module when a worker runs, so tests replace them.
"""

from __future__ import annotations

import threading
import types

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QPushButton,
    QSizePolicy, QTableView, QVBoxLayout, QWidget,
)

from core.recent import load_recent, save_recent
from core.paths import MAX_RECENT
from core.search import VIDEO_KINDS
from luckytwitch_engine import fetch_videos, search_channels
from qt_ui import dialogs
from qt_ui.bridge import Bridge
from qt_ui.search_models import (
    CHANNEL_ROW_HEIGHT, ROW_HEIGHT, THUMB_COLUMN_WIDTH, VOD_COLUMNS, ChannelModel, ThumbDelegate, VodModel,
)
from qt_ui.thumbs import ThumbFetcher
from qt_ui.widgets import Card, ComboBox, EmptyState, ScrollFrame, WrapLabel

HEADER_HEIGHT = 34  # the column headings of the VOD table; its empty-state message starts under them
LEFT_WIDTH = 242  # the two streamer cards (tkinter: lists 216 px wide inside a 12 px padding)
START_TITLE = "Search for a streamer, or pick one from your recent list."
SIGNIN_TEXT = "Sign in with Twitch to search streamers and list their VODs."


class VodTable(QTableView):
    """The VOD table. Double-click on a row or Enter/Return uses the VOD (``use_requested``)."""

    use_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.doubleClicked.connect(self._on_double_clicked)

    def _on_double_clicked(self, index) -> None:
        if index.isValid():
            self.use_requested.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.use_requested.emit()
            return
        super().keyPressEvent(event)


def _channel_list(model: ChannelModel, rows: int) -> QListView:
    view = QListView()
    view.setModel(model)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setUniformItemSizes(True)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    view.setMinimumHeight(rows * CHANNEL_ROW_HEIGHT + 2)  # tkinter: height=6 and 8 rows
    return view


class SearchTab(QWidget):
    status_message = Signal(str)
    signin_requested = Signal()
    vod_chosen = Signal(str)

    def __init__(self, bridge: Bridge | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SearchTab")
        self.bridge = bridge if bridge is not None else Bridge(self)
        self.get_client = lambda: None
        self.reload_client = lambda: None
        # state of the search (names as in the tkinter app)
        self.recent = load_recent()
        self.sv_channel: dict | None = None
        self.sv_results: list[dict] = []
        self.sv_query = ""  # what the last search looked for (to say «no streamers found for …»)
        self.sv_loading = False  # a page of VODs is being fetched
        self.sv_cursor: str | None = None
        self.results_model = ChannelModel(live_marker=True, parent=self)
        self.recent_model = ChannelModel(parent=self)
        self.vod_model = VodModel(parent=self)
        self._gen = types.SimpleNamespace(value=0)  # the generation lives in a small object of its own, so the
        self.thumbs = ThumbFetcher(self.bridge, lambda gen=self._gen: gen.value)  # workers hold no reference to the tab

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollFrame(8, self)  # scrolls when the window is too short, like the tkinter ScrollFrame
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # nothing decorative in the Tab order
        self.scroll.body_layout.setSpacing(0)
        outer.addWidget(self.scroll)
        self._build_search_row()
        self._build_signin_bar()
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 10, 0, 0)
        columns.setSpacing(12)
        columns.addWidget(self._build_left())
        columns.addWidget(self._build_right(), 1)
        self.scroll.body_layout.addLayout(columns, 1)
        self._tab_order()

        self.bridge.search_ok.connect(self.on_search_ok)
        self.bridge.search_err.connect(self.on_search_err)
        self.bridge.videos_ok.connect(self.on_videos_ok)
        self.bridge.videos_err.connect(self.on_videos_err)
        self.bridge.thumb.connect(self.on_thumb)
        self.results_view.selectionModel().selectionChanged.connect(self._results_selected)
        self.recent_view.selectionModel().selectionChanged.connect(self._recent_selected)
        self.refresh_recent()  # fills the recent list and shows the empty-state messages
        self.update_search_state()

    # ---------------------------- building ---------------------------- #
    def _build_search_row(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Streamer:"))
        self.search_edit = QLineEdit()
        self.search_edit.returnPressed.connect(self.on_search)
        row.addWidget(self.search_edit, 1)
        self.search_btn = QPushButton("Search")
        self.search_btn.setProperty("variant", "accent")
        self.search_btn.clicked.connect(self.on_search)
        row.addWidget(self.search_btn)
        self.scroll.body_layout.addLayout(row)

    def _build_signin_bar(self) -> None:
        """Shown while not signed in: a tinted banner with the way out."""
        self.signin_bar = QFrame()
        self.signin_bar.setObjectName("signinBar")
        self.signin_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self.signin_bar)
        row.setContentsMargins(14, 8, 14, 8)
        self.signin_label = QLabel(SIGNIN_TEXT)
        row.addWidget(self.signin_label, 1)
        self.signin_btn = QPushButton("Sign in…")
        self.signin_btn.setProperty("variant", "accent")
        self.signin_btn.clicked.connect(self.signin_requested.emit)
        row.addWidget(self.signin_btn)
        holder = QVBoxLayout()
        holder.setContentsMargins(0, 8, 0, 0)
        holder.addWidget(self.signin_bar)
        self.scroll.body_layout.addLayout(holder)

    def _build_left(self) -> QWidget:
        """Found channels and recent streamers."""
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        box = QVBoxLayout(left)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        res_card = Card("Results", "● = live now", padding=12)
        self.results_view = _channel_list(self.results_model, 6)
        res_card.add_widget(self.results_view)
        box.addWidget(res_card)
        rec_card = Card("Recent streamers", "The ones you opened lately", padding=12)
        self.recent_view = _channel_list(self.recent_model, 8)
        rec_card.add_widget(self.recent_view)
        rec_card.body_layout.setStretchFactor(self.recent_view, 1)
        self.clear_recent_btn = QPushButton("Clear recent")
        self.clear_recent_btn.setProperty("variant", "ghost")
        self.clear_recent_btn.clicked.connect(self.clear_recent)
        clear_row = QHBoxLayout()
        clear_row.setContentsMargins(0, 6, 0, 0)
        clear_row.addStretch(1)
        clear_row.addWidget(self.clear_recent_btn)
        rec_card.body_layout.addLayout(clear_row)
        box.addWidget(rec_card, 1)
        self.ch_empty = EmptyState(self.results_view, compact=True)
        self.recent_empty = EmptyState(self.recent_view, compact=True)
        return left

    def _build_right(self) -> QWidget:
        """The VODs of the picked streamer."""
        right = QWidget()
        box = QVBoxLayout(right)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 6)
        self.title_label = WrapLabel(START_TITLE)
        self.title_label.setProperty("role", "heading")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title_label.setMinimumWidth(0)
        head.addWidget(self.title_label, 1)  # at the minimum window width the title wraps, the list never gets cut
        self.type_combo = ComboBox()
        self.type_combo.addItems(list(VIDEO_KINDS))
        self.type_combo.setMinimumContentsLength(16)
        self.type_combo.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.type_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.type_combo.activated.connect(self._on_kind_chosen)
        head.addWidget(self.type_combo, 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(head)

        self.vod_table = VodTable()
        self.vod_table.setObjectName("vodTable")
        self.vod_table.setModel(self.vod_model)
        self.vod_table.setItemDelegateForColumn(0, ThumbDelegate(self.vod_table))
        self.vod_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.vod_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.vod_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.vod_table.setShowGrid(False)
        self.vod_table.setWordWrap(False)
        self.vod_table.verticalHeader().hide()
        self.vod_table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        head_view = self.vod_table.horizontalHeader()
        head_view.setFixedHeight(HEADER_HEIGHT)
        head_view.setHighlightSections(False)
        head_view.setSectionsClickable(False)
        for col, (_key, _text, width, _anchor, stretch) in enumerate(VOD_COLUMNS):
            head_view.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch if stretch else QHeaderView.ResizeMode.Fixed)
            if not stretch:
                head_view.resizeSection(col, width)
        self.vod_table.setMinimumHeight(HEADER_HEIGHT + 5 * ROW_HEIGHT // 2)  # tkinter: height=5 rows, then it grows
        self.vod_table.use_requested.connect(self.use_selected_vod)
        box.addWidget(self.vod_table, 1)
        self.sv_empty = EmptyState(self.vod_table, top=HEADER_HEIGHT)  # under the column headings

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        buttons.setSpacing(12)
        self.more_btn = QPushButton("Load more")
        self.more_btn.setEnabled(False)
        self.more_btn.clicked.connect(self.load_more)
        buttons.addWidget(self.more_btn)
        buttons.addStretch(1)
        self.use_hint = QLabel("Double-click a VOD to use it")
        self.use_hint.setProperty("role", "muted")
        buttons.addWidget(self.use_hint)
        self.use_btn = QPushButton("Use this VOD")
        self.use_btn.setProperty("variant", "accent")
        self.use_btn.clicked.connect(self.use_selected_vod)
        buttons.addWidget(self.use_btn)
        box.addLayout(buttons)
        return right

    def _tab_order(self) -> None:
        """The order the widgets were made in is the order of the keyboard: nothing decorative takes focus."""
        chain = (self.search_edit, self.search_btn, self.signin_btn, self.results_view, self.recent_view,
                 self.clear_recent_btn, self.type_combo, self.vod_table, self.more_btn, self.use_btn)
        for a, b in zip(chain, chain[1:]):
            QWidget.setTabOrder(a, b)

    # ---------------------------- state ---------------------------- #
    @property
    def client(self):
        return self.get_client()

    @property
    def sv_gen(self) -> int:
        """Bumped on every new channel / kind: answers of older requests are ignored."""
        return self._gen.value

    @sv_gen.setter
    def sv_gen(self, value: int) -> None:
        self._gen.value = value

    @property
    def sv_videos(self) -> list[dict]:
        return self.vod_model.videos

    @property
    def sv_type(self) -> str:
        return self.type_combo.currentText()

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def update_search_state(self) -> None:
        """Show the «sign in» warning (and disable searching) while there is no Twitch session."""
        signed_in = bool(self.client)
        self.signin_bar.setVisible(not signed_in)
        self.search_btn.setEnabled(signed_in)
        self.refresh_search_empty_states()

    def refresh_search_empty_states(self) -> None:
        """Show a friendly message over each list of the tab that has nothing in it (and only then)."""
        # the VODs of the picked streamer
        if self.sv_videos:
            self.sv_empty.hide_message()
        elif self.sv_loading:
            self.sv_empty.show_message("Loading VODs…", "One moment.")
        elif not self.client and self.sv_channel is None:
            self.sv_empty.show_message(
                "Sign in to browse VODs",
                "Use the «Sign in…» button above. Or paste a VOD link at the top and press «Get info»: "
                "that works without signing in.")
        elif self.sv_channel is None:
            self.sv_empty.show_message(
                "Pick a streamer",
                "Search for a name above, or choose one from your recent streamers. "
                "You can also paste a VOD link at the top and press «Get info».")
        else:
            self.sv_empty.show_message(
                f"No {self.sv_type.lower()} found",
                "Twitch deletes VODs after a while, and some streamers don't save them. "
                "Try another kind of video in the list above.")
        # the search results
        if self.sv_results:
            self.ch_empty.hide_message()
        elif self.sv_query:
            self.ch_empty.show_message(f"No streamers found for «{self.sv_query}»", "Check the spelling.")
        else:
            self.ch_empty.show_message("", "Search results show up here.")
        # the recent streamers
        if self.recent:
            self.recent_empty.hide_message()
        else:
            self.recent_empty.show_message("", "Streamers you open show up here.")
        self.clear_recent_btn.setEnabled(bool(self.recent))

    # ---------------------------- recent streamers ---------------------------- #
    def refresh_recent(self) -> None:
        self.recent_model.set_channels(self.recent)
        self.refresh_search_empty_states()

    def add_recent(self, ch: dict) -> None:
        entry = {"id": ch["id"], "login": ch.get("login", ""), "name": ch.get("name") or ch.get("login", "")}
        self.recent = ([entry] + [c for c in self.recent if c["id"] != entry["id"]])[:MAX_RECENT]
        save_recent(self.recent)
        self.refresh_recent()

    def clear_recent(self) -> None:
        self.recent = []
        save_recent(self.recent)
        self.refresh_recent()

    # ---------------------------- searching ---------------------------- #
    def on_search(self) -> None:
        query = self.search_edit.text().strip()
        if not query:
            return
        if not self.client:
            self.update_search_state()
            self.status_message.emit("Sign in with Twitch to search (use the «Sign in…» button).")
            return
        self.search_btn.setEnabled(False)
        self.status_message.emit(f"Searching for «{query}»…")
        client, bridge = self.client, self.bridge

        def work():
            try:
                results = search_channels(client, query)
            except Exception as e:  # noqa: BLE001
                bridge.search_err.emit(str(e))
                return
            bridge.search_ok.emit(query, results)

        threading.Thread(target=work, daemon=True).start()

    def on_search_ok(self, query: str, results: list[dict]) -> None:
        self.search_btn.setEnabled(bool(self.client))
        self.sv_results = results
        self.sv_query = query
        self.results_model.set_channels(results)
        self.refresh_search_empty_states()
        if not results:
            self.status_message.emit(f"No streamers found for «{query}».")
            return
        self.status_message.emit(f"{len(results)} streamer(s) found. Pick one to see their VODs.")
        if results[0]["login"].lower() == query.lstrip("@").lower():
            self.select_channel(self.results_view, 0)  # exact match: open it straight away

    def on_search_err(self, msg: str) -> None:
        self.search_btn.setEnabled(bool(self.client))
        self.status_message.emit("Search failed.")
        if "sign in" in msg.lower():  # the saved session expired: refresh what the tab shows
            self.reload_client()
            self.update_search_state()
        dialogs.error(self, "Search", msg)

    # ---------------------------- picking a streamer ---------------------------- #
    @staticmethod
    def select_channel(view: QListView, row: int) -> None:
        """Select a row like a click does (this loads that streamer's VODs through ``_on_pick``)."""
        index = view.model().index(row, 0)
        view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        view.setCurrentIndex(index)

    def _results_selected(self, *_args) -> None:
        self._on_pick(True)

    def _recent_selected(self, *_args) -> None:
        self._on_pick(False)

    def _on_pick(self, from_results: bool) -> None:
        view, other = (self.results_view, self.recent_view) if from_results else (self.recent_view, self.results_view)
        rows = view.selectionModel().selectedRows()
        if not rows:
            return
        ch = (self.sv_results if from_results else self.recent)[rows[0].row()]
        other.selectionModel().clearSelection()
        self.load_channel(ch)

    def _on_kind_chosen(self, _index: int) -> None:
        if self.sv_channel:
            self.load_channel(self.sv_channel, remember=False)

    def load_channel(self, ch: dict, remember: bool = True, more: bool = False) -> None:
        """Load the first page of a streamer's VODs (or the next page when ``more``)."""
        if not self.client:
            self.update_search_state()
            self.status_message.emit("Sign in with Twitch to list VODs (use the «Sign in…» button).")
            return
        if more:
            gen = self.sv_gen
        else:
            self.sv_gen += 1
            gen = self.sv_gen
            self.sv_channel = ch
            self.sv_cursor = None
            self.vod_model.clear()
            if remember:
                self.add_recent(ch)
        kind = VIDEO_KINDS.get(self.sv_type, "archive")
        after = self.sv_cursor if more else None
        self.more_btn.setEnabled(False)
        self.sv_loading = True
        self.refresh_search_empty_states()
        self.set_title(f"{ch['name']}: loading…")
        client, bridge = self.client, self.bridge

        def work():
            try:
                videos, cursor = fetch_videos(client, ch["id"], kind, after=after)
            except Exception as e:  # noqa: BLE001
                bridge.videos_err.emit(gen, str(e))
                return
            bridge.videos_ok.emit(gen, videos, cursor)

        threading.Thread(target=work, daemon=True).start()

    def load_more(self) -> None:
        if self.sv_channel and self.sv_cursor:
            self.load_channel(self.sv_channel, more=True)

    def on_videos_ok(self, gen: int, videos: list[dict], cursor: str | None) -> None:
        if gen != self.sv_gen or not self.sv_channel:
            return  # the user already picked something else
        self.sv_loading = False
        start = self.vod_model.append(videos)
        for i, v in enumerate(videos):
            if v["thumb"]:
                self.thumbs.submit(gen, str(start + i), v["thumb"])
        self.sv_cursor = cursor
        self.more_btn.setEnabled(bool(cursor))
        name = self.sv_channel["name"]
        self.refresh_search_empty_states()
        if not self.sv_videos:
            self.set_title(f"{name}: no {self.sv_type.lower()} found")
        else:
            n = len(self.sv_videos)
            self.set_title(f"{name}  ·  {n} VOD{'s' if n != 1 else ''}" + ("  ·  more available" if cursor else ""))

    def on_videos_err(self, gen: int, msg: str) -> None:
        if gen != self.sv_gen:
            return
        self.sv_loading = False
        self.refresh_search_empty_states()
        self.set_title("Could not load the VODs.")
        self.status_message.emit("Could not load the VODs.")
        if "sign in" in msg.lower():
            self.reload_client()
            self.update_search_state()
        dialogs.error(self, "Search", msg)

    def on_thumb(self, gen: int, iid: str, path: str) -> None:
        """A thumbnail was fetched to disk: build its pixmap here, on the GUI thread."""
        if gen != self.sv_gen:
            return
        self.vod_model.set_thumb(iid, path)

    # ---------------------------- using a VOD ---------------------------- #
    def selected_video(self) -> dict | None:
        rows = self.vod_table.selectionModel().selectedRows()
        return self.sv_videos[rows[0].row()] if rows else None

    def select_vod(self, row: int) -> None:
        index = self.vod_model.index(row, 0)
        self.vod_table.selectionModel().select(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
        self.vod_table.setCurrentIndex(index)

    def use_selected_vod(self) -> None:
        video = self.selected_video()
        if video is None:
            dialogs.info(self, "Select a VOD", "Select a VOD in the list first.")
            return
        self.vod_chosen.emit(video["url"])

    def shutdown(self) -> None:
        """The window is closing: the thumbnail threads end."""
        self.thumbs.stop()
