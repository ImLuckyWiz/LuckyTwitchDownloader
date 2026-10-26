"""The Plan tab (Phases 6 and 7): the interactive timeline strip (``qt_ui/timeline.py``), the cut points editor
with its live preview of the parts, the Clips -> chapters card, and the always-visible footer with «Add to queue» and
«Add & start».

Port of ``ui/plan_tab.py`` (``PlanTabMixin``) and the plan-tab parts of ``luckytwitch_downloader.py``. The cut text box
is the source of truth: the timeline is redrawn from it (``sync_timeline``) and every edit made on the timeline is
written back into it (``on_timeline_edit``). The five settings on this tab (``chapters``, ``min_views``,
``min_duration``, ``top_n``, ``pad_before``) are bound to the window's settings dictionary with a ``SettingsBinder``
(decision D3).
"""

from __future__ import annotations

import webbrowser
from typing import Callable, Sequence

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QScrollBar, QSizePolicy,
    QTableView, QVBoxLayout, QWidget,
)

from core.options import build_filter, build_options, flag
from core.palette import ERR, MUTED, OK
from core.settings import DEFAULTS
from luckytwitch_engine import (
    EngineError, GameSegment, Range, Storyboard, clip_start, fmt_hms, insert_cut_point, make_chapters, make_plan,
    muted_overlap, ranges_of, ranges_to_text,
)
from qt_ui import dialogs
from qt_ui import timeline as timeline_module
from qt_ui.background_jobs import FramesRunner
from qt_ui.binder import SettingsBinder
from qt_ui.bridge import Bridge
from qt_ui.theme import mono_font
from qt_ui.timeline import IDLE_HINT, Timeline
from qt_ui.widgets import Card, ScrollPage, SpinBox, Toggle, WrapLabel

HEADER_HEIGHT = 34
ROW_HEIGHT = 28
PREVIEW_COLOURS = {"ok": OK, "err": ERR, "muted": MUTED}
CUT_HINT = ("Boundaries in order, e.g.  0:00:00 - 0:30:00 - 1:30:00 - end   (end = end of the VOD).   "
            "To skip a section use «;» or a new line:  0:00:00 - 0:30:00 ; 2:00:00 - end")

CLIP_COLUMNS = (  # key, heading, width, alignment, stretches
    ("at", "At", 80, "center", False),
    ("views", "Views", 70, "center", False),
    ("dur", "Dur", 60, "center", False),
    ("title", "Title", 380, "w", True),
    ("creator", "Creator", 140, "w", False),
    ("chap", "Chapter", 108, "center", False),
)


def _alignment(kind: str) -> Qt.AlignmentFlag:
    return (Qt.AlignmentFlag.AlignHCenter if kind == "center" else Qt.AlignmentFlag.AlignLeft) | \
        Qt.AlignmentFlag.AlignVCenter


def _polish(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


class ClipModel(QAbstractTableModel):
    """The clips table of the Plan tab (decision D5): At, Views, Dur, Title, Creator, Chapter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[tuple[str, str, str, str, str, str]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(CLIP_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal or not 0 <= section < len(CLIP_COLUMNS):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return CLIP_COLUMNS[section][1]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(CLIP_COLUMNS[section][3]))
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(CLIP_COLUMNS[index.column()][3]))
        return None

    def set_rows(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()


TimelinePlaceholder = Timeline  # backward-compatible alias


class PlanTab(ScrollPage):
    add_requested = Signal(bool)  # False = «Add to queue», True = «Add & start»

    def __init__(self, settings: dict | None = None, bridge: Bridge | None = None, parent: QWidget | None = None):
        super().__init__(8, parent)
        self.setObjectName("PlanTab")
        self.settings = settings if settings is not None else {}
        self.bridge = bridge if bridge is not None else Bridge(self)
        self.binder = SettingsBinder(self.settings, self)
        self.frames_runner = FramesRunner(self.bridge)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.body_layout.setSpacing(10)

        self.source = None
        self.clips: list[dict] = []
        self.clips_loaded = False
        self._timeline_src = None
        self.preview_kind = "muted"

        self._build_timeline_card()
        self._build_cuts_card()
        self._build_clips_card()
        self._build_footer()

        self.bridge.frames.connect(self.on_frames)
        self.update_preview()
        self.refresh_clips()

    # ---------------------------- building ---------------------------- #
    def _build_timeline_card(self) -> None:
        self.timeline_card = Card("Timeline")
        self.body_layout.addWidget(self.timeline_card)
        well = QWidget()
        well.setObjectName("timelineWell")
        well.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wlay = QVBoxLayout(well)
        wlay.setContentsMargins(8, 8, 8, 8)
        self.timeline = Timeline(on_edit=self.on_timeline_edit, parent=well)
        wlay.addWidget(self.timeline)
        self.timeline_card.add_widget(well)

    def _build_cuts_card(self) -> None:
        self.cuts_card = Card("Cut points")
        self.body_layout.addWidget(self.cuts_card)
        self.cuts = QPlainTextEdit()
        self.cuts.setObjectName("cutPoints")
        font = mono_font()
        font.setPointSize(11)
        self.cuts.setFont(font)
        self.cuts.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.cuts.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.cuts.setTabChangesFocus(True)  # Tab moves to the next control instead of typing a tab character
        line_h = self.cuts.fontMetrics().lineSpacing()
        self.cuts.setFixedHeight(3 * line_h + 18)  # tkinter: height=3 lines
        self.cuts.textChanged.connect(self.update_preview)
        self.cuts_card.add_widget(self.cuts)

        self.cuts_hint = WrapLabel(CUT_HINT)
        self.cuts_hint.setProperty("role", "muted")
        self.cuts_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.cuts_hint.setContentsMargins(0, 6, 0, 8)
        self.cuts_card.add_widget(self.cuts_hint)

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("planPreview")
        self.preview.setReadOnly(True)
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.preview.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.preview.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.preview.setFixedHeight(4 * self.preview.fontMetrics().lineSpacing() + 12)  # tkinter: height=4 lines
        self._preview_formats: dict[str, QTextCharFormat] = {}
        for kind, colour in PREVIEW_COLOURS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            self._preview_formats[kind] = fmt
        self.cuts_card.add_widget(self.preview)

    def _build_clips_card(self) -> None:
        self.clips_card = Card("Clips \u2192 chapters", "Optional: put the VOD's clips in the files as chapters.")
        self.body_layout.addWidget(self.clips_card, 1)

        row = self.clips_card.add_row(
            "Add clips as chapters", "Each clip that passes the filter becomes a chapter.",
            info="Needs the Twitch API sign-in (the «Twitch API…» button). Chapters are written into the video "
                 "files; the Premiere Pro outputs (Options \u2192 Premiere Pro) have their own switches.")
        self.chapters_toggle = Toggle()
        self.binder.bind("chapters", self.chapters_toggle)
        self.chapters_toggle.clicked.connect(self.refresh_clips)
        row.add_control(self.chapters_toggle)

        frow = QWidget()
        frow.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        flay = QHBoxLayout(frow)
        flay.setContentsMargins(0, 0, 0, 8)
        flay.setSpacing(6)
        self.filter_spins: dict[str, SpinBox] = {}

        def num_field(label: str, name: str, width: int = 6, first: bool = False) -> None:
            if not first:
                flay.addSpacing(8)
            lbl = QLabel(label)
            lbl.setProperty("role", "muted")
            flay.addWidget(lbl)
            sp = SpinBox(0, 1_000_000, width)
            self.binder.bind(name, sp)
            sp.valueChanged.connect(self._on_filter_spin)
            flay.addWidget(sp)
            self.filter_spins[name] = sp

        num_field("Min views", "min_views", 6, first=True)
        num_field("Min duration (s)", "min_duration", 5)
        num_field("Top N by views (0 = all)", "top_n", 5)
        num_field("Lead-in (s)", "pad_before", 4)
        flay.addStretch(1)
        self.clips_card.add_widget(frow)

        self.clip_model = ClipModel(self)
        self.tree = QTableView()
        self.tree.setObjectName("clipsTable")
        self.tree.setModel(self.clip_model)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setShowGrid(False)
        self.tree.setWordWrap(False)
        self.tree.verticalHeader().hide()
        self.tree.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        head = self.tree.horizontalHeader()
        head.setFixedHeight(HEADER_HEIGHT)
        head.setHighlightSections(False)
        head.setSectionsClickable(False)
        for col, (_key, _text, width, _anchor, stretch) in enumerate(CLIP_COLUMNS):
            head.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch if stretch else QHeaderView.ResizeMode.Fixed)
            if not stretch:
                head.resizeSection(col, width)
        self.tree.setMinimumHeight(HEADER_HEIGHT + 6 * ROW_HEIGHT + 2)  # tkinter: height=6 rows
        self.tree.doubleClicked.connect(self.open_clip)
        self.clips_card.add_widget(self.tree)
        self.clips_card.body_layout.setStretchFactor(self.tree, 1)

        self.clips_label = WrapLabel("")
        self.clips_label.setProperty("role", "muted")
        self.clips_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.clips_label.setContentsMargins(0, 8, 0, 0)
        self.clips_card.add_widget(self.clips_label)

        brow = QWidget()
        blay = QHBoxLayout(brow)
        blay.setContentsMargins(0, 8, 0, 0)
        blay.setSpacing(6)
        self.split_btn = QPushButton("Split at selected clip")
        self.split_btn.clicked.connect(self.split_at_clip)
        self.download_clips_btn = QPushButton("Download only selected clip")
        self.download_clips_btn.clicked.connect(self.download_clips)
        blay.addWidget(self.split_btn)
        blay.addWidget(self.download_clips_btn)
        blay.addStretch(1)
        self.clips_card.add_widget(brow)

    def _build_footer(self) -> None:
        self.plan_summary_lbl = QLabel("")
        self.plan_summary_lbl.setProperty("role", "muted")
        self.footer_layout.addWidget(self.plan_summary_lbl, 1)
        self.queue_btn = QPushButton("Add to queue")
        self.queue_btn.clicked.connect(self._on_add_to_queue)
        self.start_btn = QPushButton("Add && start")
        self.start_btn.setProperty("variant", "accent")
        self.start_btn.clicked.connect(self._on_add_and_start)
        self.footer_layout.addWidget(self.queue_btn)
        self.footer_layout.addSpacing(8)
        self.footer_layout.addWidget(self.start_btn)

    def _on_add_to_queue(self) -> None:
        self.add_requested.emit(False)

    def _on_add_and_start(self) -> None:
        self.add_requested.emit(True)

    def _on_filter_spin(self, _value: int) -> None:
        if not self.binder._loading:
            self.refresh_clips()

    # ---------------------------- cut points & preview ---------------------------- #
    def cut_text(self) -> str:
        return self.cuts.toPlainText().strip()

    def set_cut_text(self, text: str) -> None:
        """Replace the cut points box without firing ``update_preview`` twice when callers follow with their own call."""
        self.cuts.blockSignals(True)
        try:
            self.cuts.setPlainText(text)
        finally:
            self.cuts.blockSignals(False)

    def build_options(self):
        return build_options(self.settings, self.cut_text())

    def build_filter(self):
        return build_filter(self.settings)

    def set_preview(self, text: str, kind: str, summary: str = "") -> None:
        """``kind``: ok | err | muted. ``summary`` is the short line in the bar at the bottom of the tab."""
        self.preview_kind = kind
        self.plan_summary_lbl.setText(summary)
        role = "err" if kind == "err" else "muted"
        if self.plan_summary_lbl.property("role") != role:
            self.plan_summary_lbl.setProperty("role", role)
            _polish(self.plan_summary_lbl)
        self.preview.clear()
        cursor = QTextCursor(self.preview.document())
        cursor.insertText(text, self._preview_formats[kind])

    def preview_text(self) -> str:
        return self.preview.toPlainText().rstrip("\n")

    def update_preview(self) -> None:
        self._render_preview()
        self.sync_timeline()

    def _render_preview(self) -> None:
        text = self.cut_text()
        if not text:
            self.set_preview("Write the cut points above (press «Get info» first so «end» works).", "muted")
            return
        dur = self.source.duration if self.source else None
        opts = self.build_options()
        try:
            plan = make_plan(text, dur, opts.strategy, opts.full_threshold)
        except EngineError as e:
            self.set_preview(f"\u26a0 {e}", "err", "Fix the cut points to add this VOD")
            return
        muted = self.source.muted if self.source else None

        def muted_note(a: float, b: float) -> str:
            m = muted_overlap(muted, a, b)
            return f"   \u00b7  {fmt_hms(m)} muted" if m >= 1 else ""

        lines = [
            f"Part {p.index}:  {fmt_hms(p.start)} \u2192 {fmt_hms(p.end)}   ({fmt_hms(p.duration)}){muted_note(p.start, p.end)}"
            for p in plan.parts
        ]
        if plan.duration:
            how = ("download the full VOD once, then split it" if plan.strategy == "full"
                   else "download only these parts")
            lines.append(f"\u2192 {how}   (parts cover {plan.coverage * 100:.0f}% of the VOD)")
        n = len(plan.parts)
        total_muted = sum(muted_overlap(muted, p.start, p.end) for p in plan.parts)
        self.set_preview(
            "\n".join(lines), "ok",
            f"{n} part{'s' if n != 1 else ''} \u00b7 {fmt_hms(sum(p.duration for p in plan.parts))} in total"
            + (f" \u00b7 {fmt_hms(total_muted)} muted" if total_muted >= 1 else ""),
        )

    # ---------------------------- clips table ---------------------------- #
    def refresh_clips(self) -> None:
        flt = self.build_filter()
        chapters = make_chapters(self.clips, flt)
        included = {c.get("id") for ch in chapters for c in ch.clips}
        rows: list[tuple[str, str, str, str, str, str]] = []
        for c in self.clips:
            off = clip_start(c)
            mark = "?" if off is None else ("\u2713" if c.get("id") in included else "\u2014")
            rows.append((
                fmt_hms(off), str(c.get("view_count", 0)), f"{round(c.get('duration', 0))}s",
                str(c.get("title", "")), str(c.get("creator_name", "")), mark,
            ))
        self.clip_model.set_rows(rows)
        if not self.clips:
            msg = ("No clips loaded (sign in with the Twitch API… button, optional)."
                   if not self.clips_loaded else "This VOD has no clips.")
        else:
            placed = sum(1 for c in self.clips if clip_start(c) is not None)
            msg = f"{len(included)} of {len(self.clips)} clips pass the filter \u2192 {len(chapters)} chapters"
            if placed < len(self.clips):
                msg += f"  ({len(self.clips) - placed} can't be placed: no offset)"
            if not (flag(self.settings, "chapters") or flag(self.settings, "premiere_xml")
                    or flag(self.settings, "premiere_plugin")):
                msg += "  [chapters are OFF]"
        self.clips_label.setText(msg)
        self.timeline.set_clip_marks(self._clip_times())

    def selected_clip_rows(self) -> list[int]:
        return sorted(idx.row() for idx in self.tree.selectionModel().selectedRows())

    def select_clips(self, *rows: int) -> None:
        sel = self.tree.selectionModel()
        sel.clearSelection()
        for r in rows:
            if 0 <= r < self.clip_model.rowCount():
                sel.select(self.clip_model.index(r, 0),
                           QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    def open_clip(self, _index=None) -> None:
        sel = self.selected_clip_rows()
        if sel:
            webbrowser.open(self.clips[sel[0]].get("url", ""))

    def split_at_clip(self) -> None:
        sel = self.selected_clip_rows()
        if not sel:
            dialogs.info(self, "Select a clip", "Select a clip in the table first.")
            return
        if len(sel) > 1:
            dialogs.info(self, "Select one clip", "Splitting works with a single clip: select just one.")
            return
        if not self.source:
            dialogs.info(self, "No VOD", "Press «Get info» first.")
            return
        off = clip_start(self.clips[sel[0]])
        if off is None:
            dialogs.info(self, "No offset", "That clip has no position in the VOD.")
            return
        t = max(0, off - self.build_filter().pad_before)
        text = self.cut_text() or "0:00:00 - end"
        try:
            new = insert_cut_point(text, t, self.source.duration)
        except EngineError as e:
            dialogs.info(self, "Can't split here", str(e))
            return
        self.set_cut_text(new)
        self.update_preview()

    # ---------------------------- downloading selected clips ---------------------------- #
    clip_download_requested = Signal()

    def download_clips(self) -> None:
        self.clip_download_requested.emit()

    # ---------------------------- timeline ---------------------------- #
    def _clip_times(self) -> list[float]:
        return [t for t in (clip_start(c) for c in self.clips) if t is not None]

    def sync_timeline(self) -> None:
        """Show the current VOD and the parts the cut text describes (called after every change of either)."""
        src = self.source
        if src is not self._timeline_src:
            self._timeline_src = src
            if src is None:
                self.timeline.set_source(0)
            else:
                self.timeline.set_source(src.duration, src.segments, src.storyboard)
                self.timeline.set_muted(src.muted)
                self._load_frames(src)
            self.timeline.set_clip_marks(self._clip_times())
        text = self.cut_text()
        if not text or src is None:
            self.timeline.set_ranges([] if src is not None else None)
            return
        try:
            self.timeline.set_ranges(ranges_of(text, src.duration))
        except EngineError:
            self.timeline.set_ranges(None)

    def on_timeline_edit(self, ranges: list[Range]) -> None:
        """The user changed the parts on the timeline: write them into the cut text."""
        dur = self.source.duration if self.source else None
        self.set_cut_text(ranges_to_text(ranges, dur))
        self.update_preview()

    def _load_frames(self, src) -> None:
        """Download the preview frames of ``src`` in the background; they arrive on ``Bridge.frames``."""
        if getattr(src, "storyboard", None) is None:
            return
        if timeline_module.Image is None:
            self.timeline.set_frames(None)
            return
        self.frames_runner.start(src)

    def on_frames(self, src, frames) -> None:
        if src is self.source:
            self.timeline.set_frames(frames)
