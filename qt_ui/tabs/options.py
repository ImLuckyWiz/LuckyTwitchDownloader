"""The Options tab (Phase 5): a sidebar with one section visible at a time (Output, Cuts, Chapters, Premiere Pro,
Chat, Clips, Tools). Port of ``ui/options_tab.py`` (same texts, same order, same split between up-front and Advanced).

Each setting is a row (bold name, one-line hint, the control on the right); on/off settings are switches, long
explanations live in the little «i» tooltips, and settings that are set once and rarely touched sit in a collapsed
«Advanced» area inside their section. Template fields (file name, stream folder, clip name, chapter title) get
clickable ``{token}`` chips and a live example computed by the engine's own naming functions (``core.examples``).

Every control is bound to a key of the settings dictionary by a ``SettingsBinder`` (the key names are the ones the
tkinter app saved). The tab edits the dictionary and tells the window what it needs through signals:

  ``refresh_clips_requested``   a setting the Plan tab's clip list depends on changed (tkinter ``refresh_clips``)
  ``preview_requested``         the strategy or threshold changed (tkinter ``update_preview``)
  ``output_folder_requested``   «Open folder» next to the output folder
  ``update_tools_requested``    «Update yt-dlp now»
  ``saved_chat_requested``      «Choose chat file…»
  ``status_message(str)``       a sentence for the status line

and the window tells the tab, through methods: ``set_tools_info(text)``, ``set_tools_running(bool)``,
``set_saved_chat_running(bool)``, ``refresh_name_examples()`` (also when a VOD is loaded, to use its real name) and
the hook ``source_provider`` (returns the loaded ``SourceInfo`` or None; Phase 6 sets it).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

import weblink
from core import examples
from core.files import open_in_file_manager
from core.options import (
    AUDIO_FORMAT_NAMES, CHAT_RENDER_FPS_NAMES, CHAT_RENDER_LOOK_NAMES, CHAT_RENDER_TYPE_NAMES, QUALITY_NAMES,
    STRATEGY_NAMES, flag,
)
from core.settings import DEFAULTS
from luckytwitch_engine import APP_DIR, CHAT_FORMATS, TOOLS_DIR
from qt_ui import dialogs
from qt_ui.binder import SettingsBinder
from qt_ui.icons import icon
from qt_ui.widgets import Card, Collapsible, ComboBox, ScrollFrame, SettingRow, SideNav, SpinBox, Toggle, TokenChips, WrapLabel

SECTIONS = [
    ("output", "Output"),
    ("cuts", "Cuts"),
    ("chapters", "Chapters"),
    ("premiere", "Premiere Pro"),
    ("chat", "Chat"),
    ("clips", "Clips"),
    ("tools", "Tools"),
]

# changing one of these redraws every «Example:» line
EXAMPLE_KEYS = {"name_template", "folder_template", "clip_name_template", "title_tpl", "container"}


def _no_source():
    return None


class OptionsTab(QWidget):
    refresh_clips_requested = Signal()
    preview_requested = Signal()
    output_folder_requested = Signal()
    update_tools_requested = Signal()
    saved_chat_requested = Signal()
    status_message = Signal(str)

    def __init__(self, settings: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OptionsTab")
        self.settings = settings if settings is not None else {}
        self.binder = SettingsBinder(self.settings, self)
        self.source_provider = _no_source
        self.sections: dict[str, QWidget] = {}
        self.advanced: dict[str, Collapsible] = {}
        self.toggles: dict[str, Toggle] = {}
        self.template_entries: dict[str, QLineEdit] = {}
        self.chip_rows: dict[str, TokenChips] = {}
        self.example_labels: dict[str, QLabel] = {}  # setting name -> its «Example:» line
        self.rows_by_key: dict[str, tuple[SettingRow, str]] = {}
        self.searchable_rows: list[dict] = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        left = QVBoxLayout()
        left.setContentsMargins(0, 8, 0, 0)
        self.nav = SideNav(SECTIONS)
        left.addWidget(self.nav)
        left.addStretch(1)
        outer.addLayout(left)
        self.scroll = ScrollFrame(4, self)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # nothing decorative in the Tab order
        outer.addWidget(self.scroll, 1)
        body = self.scroll.body_layout
        body.setSpacing(0)

        # G1: Settings search bar at the top of the options view
        search_row = QHBoxLayout()
        search_row.setContentsMargins(4, 4, 4, 12)
        search_row.setSpacing(8)
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search settings\u2026")
        self.search_entry.setClearButtonEnabled(True)
        self.search_entry.textChanged.connect(self._on_search_query_changed)
        search_row.addWidget(self.search_entry, 1)

        self.match_counter = QLabel("")
        self.match_counter.setProperty("role", "muted")
        self.match_counter.setVisible(False)
        search_row.addWidget(self.match_counter)
        body.addLayout(search_row)

        for key, _label in SECTIONS:
            section = QWidget()
            lay = QVBoxLayout(section)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            self.sections[key] = section
            body.addWidget(section)
        body.addStretch(1)  # spare height goes below the section, never into its cards

        self._section_output(self.sections["output"])
        self._section_cuts(self.sections["cuts"])
        self._section_chapters(self.sections["chapters"])
        self._section_premiere(self.sections["premiere"])
        self._section_chat(self.sections["chat"])
        self._section_clips(self.sections["clips"])
        self._section_tools(self.sections["tools"])

        self.nav.selected.connect(self.show_section)
        self.nav.select("output")
        self.binder.changed.connect(self._on_setting_changed)
        self._sync_folder_template()
        self.refresh_name_examples()
        self.refresh_changed_markers()

    # ------------------------------------------------------------------ sections
    def show_section(self, key: str) -> None:
        for k, section in self.sections.items():
            section.setVisible(k == key)
        self.scroll.scroll_to_top()

    def visible_sections(self) -> list[str]:
        return [k for k, w in self.sections.items() if not w.isHidden()]

    # ------------------------------------------------------------------ small builders
    def _heading(self, section: QWidget, title: str, subtitle: str) -> None:
        lay = section.layout()
        head = QLabel(title)
        head.setProperty("role", "title")
        head.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(head)
        sub = WrapLabel(subtitle)
        sub.setProperty("role", "muted")
        sub.setMaximumWidth(640)
        sub.setContentsMargins(4, 2, 0, 10)
        lay.addWidget(sub)

    def _card(self, section: QWidget, title: str | None = None, subtitle: str | None = None) -> Card:
        card = Card(title, subtitle)
        lay = section.layout()
        lay.addWidget(card)
        lay.addSpacing(12)
        return card

    def _advanced(self, key: str, card: Card, hint: str) -> Collapsible:
        """The collapsed «Advanced» area at the bottom of a card."""
        adv = Collapsible("Advanced", hint)
        card.add_widget(adv)
        self.advanced[key] = adv
        return adv

    def _switch(self, row, key: str, refresh_clips: bool = False) -> Toggle:
        toggle = Toggle()
        self.binder.bind(key, toggle)
        if refresh_clips:
            toggle.clicked.connect(self.refresh_clips_requested)  # only a click by the person, like the old command
        row.add_control(toggle)
        self.toggles[key] = toggle
        return toggle

    def _entry(self, key: str, chars: int = 0) -> QLineEdit:
        entry = QLineEdit()
        if chars:
            entry.setFixedWidth(round(entry.fontMetrics().horizontalAdvance("0") * chars) + 20)
        self.binder.bind(key, entry)
        return entry

    def _spin(self, key: str, low: int, high: int, chars: int = 6) -> SpinBox:
        spin = SpinBox(low, high, chars)
        self.binder.bind(key, spin)
        return spin

    def _combo(self, key: str, values: list[str], chars: int) -> ComboBox:
        combo = ComboBox()
        combo.addItems(values)
        combo.setMinimumWidth(round(combo.fontMetrics().horizontalAdvance("0") * chars) + 40)
        self.binder.bind(key, combo)
        return combo

    def _unit(self, row, text: str) -> None:
        row.add_control(QLabel(text))

    def _template_row(self, holder, title: str, hint: str, key: str, tokens: list[str], info: str = "",
                      divider: bool = True, per_row: int = 6, section_key: str = "",
                      card: Card | None = None, adv: Collapsible | None = None) -> QLineEdit:
        """A name template: entry + clickable token chips + a live example. Returns the entry."""
        row = holder.add_row(title, hint, info, divider=divider)
        entry = self._entry(key)
        chips = TokenChips(entry, tokens, per_row=per_row)
        example = WrapLabel()
        example.setProperty("role", "muted")
        example.setMaximumWidth(640)
        example.setContentsMargins(0, 2, 0, 0)
        lay = row.below_layout
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(entry)
        lay.addSpacing(8)
        lay.addWidget(chips, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(example)
        self.template_entries[key] = entry
        self.chip_rows[key] = chips
        self.example_labels[key] = example
        if section_key and card:
            self._register_setting(row, key, section_key, card, adv)
        return entry

    def _register_setting(self, row: SettingRow, key: str, section_key: str, card: Card,
                          adv: Collapsible | None = None) -> None:
        self.rows_by_key[key] = (row, section_key)
        info_text = row.info.text if getattr(row, "info", None) is not None else ""
        hint_text = row.hint_label.text() if getattr(row, "hint_label", None) is not None else ""
        search_text = f"{row.title_label.text()} {hint_text} {info_text}".lower()
        self.searchable_rows.append({
            "row": row,
            "key": key,
            "section_key": section_key,
            "card": card,
            "adv": adv,
            "text": search_text,
        })

    # ------------------------------------------------------------------ live examples & preview (G3)
    def example_for(self, key: str) -> str:
        """The text of the example under the template ``key`` (without «Example:»). A half-typed template never
        raises: the answer is then «(can't be shown: ...)»."""
        source = self.source_provider()
        try:
            if key == "name_template":
                return examples.example_file_name(self.settings, source)
            if key == "folder_template":
                return examples.example_folder_name(self.settings, source)
            if key == "clip_name_template":
                return examples.example_clip_name(self.settings, source)
            return examples.example_chapter(self.settings)
        except Exception as e:  # noqa: BLE001  (a half-typed template must never break the tab)
            return f"(can't be shown: {e})"

    def refresh_name_examples(self) -> None:
        """Redraw every «Example:» line (also called when a VOD is loaded, to use its real name)."""
        for key, label in self.example_labels.items():
            label.setText("Example:  " + self.example_for(key))
        self._refresh_save_preview()

    def _refresh_save_preview(self) -> None:
        """Update the 'Files will be saved as' card (G3) with the fully resolved sample path and disk space."""
        if not hasattr(self, "save_preview_path"):
            return
        out_dir = str(self.settings.get("out_dir") or DEFAULTS["out_dir"])
        container = str(self.settings.get("container") or "mp4")
        folder_tpl = self.example_for("folder_template")
        name_tpl = self.example_for("name_template")
        subfolders = flag(self.settings, "subfolders")
        file_name = name_tpl if name_tpl.endswith(f".{container}") else f"{name_tpl}.{container}"
        if subfolders and folder_tpl and not folder_tpl.startswith("("):
            full_path = Path(out_dir) / folder_tpl / file_name
        else:
            full_path = Path(out_dir) / file_name
        self.save_preview_path.setText(str(full_path))

        try:
            target_dir = Path(out_dir)
            while not target_dir.exists() and target_dir.parent != target_dir:
                target_dir = target_dir.parent
            if target_dir.exists():
                free_bytes = shutil.disk_usage(target_dir).free
                free_gb = free_bytes / (1024 ** 3)
                self.disk_space_label.setText(f"Drive free space: {free_gb:.1f} GB")
            else:
                self.disk_space_label.setText("Destination folder will be created on first download")
        except Exception:
            self.disk_space_label.setText("")

    def _on_setting_changed(self, key: str) -> None:
        if key in EXAMPLE_KEYS:
            self.refresh_name_examples()
        if key == "subfolders":
            self._sync_folder_template()
        if key == "out_dir":
            self._refresh_save_preview()
        self.refresh_changed_markers()

    def refresh_changed_markers(self) -> None:
        """G2: update 'Changed from default' accent dots and SideNav count badges."""
        counts: dict[str, int] = {k: 0 for k, _ in SECTIONS}
        for key, (row, section_key) in self.rows_by_key.items():
            curr = self.settings.get(key)
            default = DEFAULTS.get(key)
            is_changed = curr is not None and default is not None and str(curr) != str(default)
            if is_changed:
                counts[section_key] = counts.get(section_key, 0) + 1

            def _make_reset(k=key, def_val=default):
                return lambda: self.binder.set(k, def_val)

            row.set_changed(is_changed, on_reset=_make_reset())

        for section_key, count in counts.items():
            self.nav.set_badge(section_key, count)

    def _on_search_query_changed(self, text: str) -> None:
        """G1: Search settings across all sections, expanding matches and updating match counter."""
        query = text.strip().lower()
        if not query:
            self.match_counter.setVisible(False)
            for item in self.searchable_rows:
                item["row"].setVisible(True)
                item["card"].setVisible(True)
            self.show_section(self.nav.current or "output")
            return

        matched = 0
        sections_with_matches: set[str] = set()
        cards_with_matches: set[Card] = set()

        for item in self.searchable_rows:
            matches = query in item["text"]
            item["row"].setVisible(matches)
            if matches:
                matched += 1
                sections_with_matches.add(item["section_key"])
                cards_with_matches.add(item["card"])
                if item["adv"] is not None:
                    item["adv"].set_opened(True)

        for s_key, section_widget in self.sections.items():
            section_widget.setVisible(s_key in sections_with_matches)

        for item in self.searchable_rows:
            item["card"].setVisible(item["card"] in cards_with_matches)

        self.match_counter.setText(f"{matched} match" if matched == 1 else f"{matched} matches")
        self.match_counter.setVisible(True)

    def _sync_folder_template(self) -> None:
        """«Stream folder name» is greyed out while «Organize in subfolders» is off."""
        on = flag(self.settings, "subfolders")
        entry = self.template_entries.get("folder_template")
        if entry is not None:
            entry.setEnabled(on)
            self.chip_rows["folder_template"].set_enabled(on)

    # ------------------------------------------------------------------ Output
    def _section_output(self, f: QWidget) -> None:
        self._heading(f, "Output", "Where the finished files go and how they are named.")

        # G3: Files will be saved as preview card
        self.save_preview_card = self._card(f, "Files will be saved as", "Full destination path of your next download.")
        preview_row = self.save_preview_card.add_row("Destination preview", "")
        self.save_preview_path = WrapLabel("")
        self.save_preview_path.setProperty("role", "accent")
        self.save_preview_path.setMaximumWidth(640)
        self.disk_space_label = QLabel("")
        self.disk_space_label.setProperty("role", "muted")
        preview_row.below_layout.setContentsMargins(0, 4, 0, 0)
        preview_row.below_layout.addWidget(self.save_preview_path)
        preview_row.below_layout.addWidget(self.disk_space_label)

        card = self._card(f)

        row = card.add_row("Output folder", "Where the finished files are saved.")
        self._register_setting(row, "out_dir", "output", card)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self.pick_folder)
        row.add_control(self.browse_btn)
        self.open_folder_btn = QPushButton("Open folder")
        self.open_folder_btn.clicked.connect(self.output_folder_requested)
        row.add_control(self.open_folder_btn)
        row.below_layout.setContentsMargins(0, 8, 0, 0)
        row.below_layout.addWidget(self._entry("out_dir"))

        row = card.add_row("Format", "Container of the finished files.", divider=False)
        self._register_setting(row, "container", "output", card)
        row.add_control(self._combo("container", ["mp4", "mkv"], 5))

        adv = self._advanced("output", card, "download threads, file and folder names")
        row = adv.add_row("Download threads", "Parallel connections per download. 8 is a good default.")
        self._register_setting(row, "threads", "output", card, adv)
        row.add_control(self._spin("threads", 1, 32, 5))

        self._template_row(
            adv, "File name", "How each part is called. Click a token to add it.", "name_template",
            [
                "streamer", "stream_date", "download_date", "date", "year", "month", "day", "game",
                "quality", "id", "title", "duration", "n", "total", "start", "end",
            ],
            per_row=8,
            info="{stream_date} is when the stream aired, {download_date} today's date, {date} alias for stream date. "
                 "{year}, {month}, {day} are broadcast dates. {game} is the dominant game played. {duration} is the part length. "
                 "{quality} is the video quality. {n} is part number, {total} total parts, {start} and {end} part timestamps.",
            section_key="output", card=card, adv=adv)

        row = adv.add_row("Auto-clean titles", "Strip bot commands (!links, !gsupps) and promo tags from stream titles.")
        self._register_setting(row, "clean_title", "output", card, adv)
        self._switch(row, "clean_title")

        row = adv.add_row("Organize in subfolders", "Folder / Streamer / Stream / parts.")
        self._register_setting(row, "subfolders", "output", card, adv)
        self._switch(row, "subfolders")

        self.folder_entry = self._template_row(
            adv, "Stream folder name", "Name of the folder that holds one stream's files.", "folder_template",
            [
                "streamer", "stream_date", "download_date", "date", "year", "month",
                "day", "game", "quality", "id", "title", "duration",
            ],
            divider=False, per_row=6,
            info="{stream_date} is when the stream aired, {download_date} today's date, {date} alias for stream date. "
                 "{year}, {month}, {day} are broadcast dates. {game} is the dominant stream game. "
                 "{duration} is the total stream length. {quality} is the video quality.",
            section_key="output", card=card, adv=adv)

        qcard = self._card(f, "Quality", "What to download when a VOD offers several qualities (Twitch VODs).")
        row = qcard.add_row(
            "Default quality", "Used when you load a VOD. You can change it for each VOD on the Plan tab.",
            info="Best available is the highest quality Twitch offers. If a VOD does not have the chosen quality, the "
                 "closest lower one is used. Audio only downloads just the sound.")
        self._register_setting(row, "default_quality", "output", qcard)
        row.add_control(self._combo("default_quality", QUALITY_NAMES, 16))
        row = qcard.add_row(
            "Audio-only file", "How the sound is saved when the quality is Audio only.", divider=False,
            info="m4a keeps Twitch's own audio exactly as it is (no re-encoding). mp3 converts it with ffmpeg "
                 "(192 kbit/s) and plays everywhere.")
        self._register_setting(row, "audio_format", "output", qcard)
        row.add_control(self._combo("audio_format", AUDIO_FORMAT_NAMES, 26))

    # ------------------------------------------------------------------ Cuts
    def _section_cuts(self, f: QWidget) -> None:
        self._heading(f, "Cuts", "How the VOD is downloaded and cut into parts.")
        card = self._card(f)

        row = card.add_row(
            "Strategy", "How the VOD is downloaded.",
            info="Auto: downloads the full VOD once and splits it when the parts cover at least the "
                 "threshold (see Advanced), otherwise downloads only the parts.\nOr force one of the two.")
        self._register_setting(row, "strategy", "cuts", card)
        combo = self._combo("strategy", STRATEGY_NAMES, 30)
        combo.activated.connect(self.preview_requested)  # only a choice by the person, like <<ComboboxSelected>>
        row.add_control(combo)

        row = card.add_row(
            "Frame-exact cuts", "Slow and CPU heavy. Off = lossless, ~2 s precision.",
            info="Off (default): the cuts are lossless and land on keyframes, about 2 seconds "
                 "of precision.\nOn: the video is re-encoded so every cut is frame-exact. "
                 "That is slow and uses a lot of CPU.")
        self._register_setting(row, "exact", "cuts", card)
        self._switch(row, "exact")

        row = card.add_row("Keep the full VOD", "Also keep the full file when the full-VOD strategy is used.",
                           divider=False)
        self._register_setting(row, "keep_full", "cuts", card)
        self._switch(row, "keep_full")

        adv = self._advanced("cuts", card, "auto threshold")
        row = adv.add_row(
            "Auto threshold", "Auto uses the full VOD above this share.", divider=False,
            info="Auto downloads the full VOD (and splits it) when the parts cover at least this "
                 "percentage of it; below that it downloads only the parts.")
        self._register_setting(row, "threshold", "cuts", card, adv)
        spin = self._spin("threshold", 1, 100, 5)
        spin.valueChanged.connect(self.preview_requested)
        row.add_control(spin)
        self._unit(row, "%")

    # ------------------------------------------------------------------ Chapters
    def _section_chapters(self, f: QWidget) -> None:
        self._heading(f, "Chapters",
                      "How the chapters look. Switch them on with «Add clips as chapters» in the Plan tab.")
        card = self._card(f)

        entry = self._template_row(
            card, "Chapter title", "Name of each clip's chapter.", "title_tpl",
            ["title", "creator", "views", "duration"], per_row=4,
            section_key="chapters", card=card)
        entry.textEdited.connect(self.refresh_clips_requested)

        row = card.add_row("Tail", "Seconds the chapter lasts after the clip ends.")
        self._register_setting(row, "pad_after", "chapters", card)
        spin = self._spin("pad_after", 0, 600, 6)
        spin.valueChanged.connect(self.refresh_clips_requested)
        row.add_control(spin)
        self._unit(row, "s")

        row = card.add_row(
            "Gap chapter name", "Name for the stretches between clips.", divider=False,
            info="MP4 needs every stretch to have a name, so don't leave this empty for MP4. "
                 "Empty is fine only for MKV.")
        self._register_setting(row, "gap_title", "chapters", card)
        row.add_control(self._entry("gap_title", 18))

    # ------------------------------------------------------------------ Premiere Pro
    def _section_premiere(self, f: QWidget) -> None:
        self._heading(f, "Premiere Pro", "Markers you can bring into Adobe Premiere Pro next to each part.")
        card = self._card(f)

        row = card.add_row(
            "LuckyTwitch Premiere plugin", "Saves a .markers.json with colors and clip details.",
            info="One .markers.json next to each part, for the LuckyTwitch Premiere plugin. "
                 "It works even if chapters are off.")
        self._register_setting(row, "premiere_plugin", "premiere", card)
        self._switch(row, "premiere_plugin", refresh_clips=True)

        row = card.add_row(
            "Game / category changes", "Also marks every time the game changes.",
            info="Adds markers named «GAME: ...» to the .markers.xml and as game markers in the "
                 ".markers.json. Works for full VODs and for parts, even if chapters are off.")
        self._register_setting(row, "game_markers", "premiere", card)
        self._switch(row, "game_markers")

        row = card.add_row(
            "Muted audio", "Also marks the stretches Twitch silenced.", divider=False,
            info="Twitch mutes copyrighted audio in a VOD. Those stretches are added to the "
                 ".markers.json as «muted» markers (the plugin decides the color), so you can see "
                 "them in Premiere. It needs the plugin file above to be on. The same stretches "
                 "show in red on the Plan tab's timeline.")
        self._register_setting(row, "muted_markers", "premiere", card)
        self._switch(row, "muted_markers")

        adv = self._advanced("premiere", card, "plain markers and clip list")
        row = adv.add_row("Plain Premiere markers", "Saves a .markers.xml you can import without the plugin.",
                          info="Plain import, without colors. Works even if chapters are off.")
        self._register_setting(row, "premiere_xml", "premiere", card, adv)
        self._switch(row, "premiere_xml", refresh_clips=True)
        row = adv.add_row("Clip list", "Saves a .clips.json (clip titles, creators, links) next to each part.",
                          divider=False)
        self._register_setting(row, "sidecar", "premiere", card, adv)
        self._switch(row, "sidecar")

    # ------------------------------------------------------------------ Chat
    def _section_chat(self, f: QWidget) -> None:
        self._heading(f, "Chat", "Download the chat that went with the stream, or turn it into a video you can put "
                                 "over the footage in your editor (Twitch VODs only).")
        card = self._card(f)

        row = card.add_row(
            "Download the chat", "Saves the chat of each part next to it.",
            info="Uses TwitchDownloaderCLI, downloaded the first time. Saved next to each part "
                 "as «name.chat.json». Inside the .json the message times count from the start of "
                 "the VOD, not from the start of the part; the file's start/end say which stretch "
                 "it covers.\nTwitchDownloader is MIT licensed (github.com/lay295/TwitchDownloader).")
        self._register_setting(row, "chat", "chat", card)
        self._switch(row, "chat")

        row = card.add_row(
            "Chat as a video (overlay)", "Draws the chat of each part as a video for your editor.",
            info="Saved next to each part as «name.chat-overlay.mov» (or .mp4). It works even if the "
                 "stream had no chat on screen: put it on the track above the video, at the start of "
                 "the part, and place it where you want it. It begins together with the part and can "
                 "run up to a second longer at the end.\nIt takes a while: a long part can take "
                 "from minutes to hours to draw, depending on the type. Emotes and badges are "
                 "fetched from Twitch, BTTV, FFZ and 7TV when it is drawn, so it needs internet.\n"
                 "Size on disk for a very busy chat (3 messages a second, 400 x 1080): about 3.4 GB "
                 "per hour with Animation, 28 GB with ProRes 4444, 0.4 GB with H.264.")
        self._register_setting(row, "chat_render", "chat", card)
        self._switch(row, "chat_render")

        row = card.add_row(
            "Draw the overlay from a saved chat", "Pick a «.chat.json» you already have. Nothing is downloaded.",
            divider=False,
            info="Uses the overlay settings below (type, look, size, text size, frame rate). The video is "
                 "not touched. If «name.mp4» (or .mkv…) is next to the chat, the overlay takes its size "
                 "and frame rate; if «name.markers.json» is there too, it is lined up to the fraction of "
                 "a second. The result is saved next to the chat as «name.chat-overlay.mov» (or .mp4).")
        self.saved_chat_btn = QPushButton("Choose chat file…")
        self.saved_chat_btn.clicked.connect(self.saved_chat_requested)
        row.add_control(self.saved_chat_btn)

        adv = self._advanced("chat", card, "file format, embedded emotes and how the overlay looks")
        row = adv.add_row("Format", "File type of the saved chat.")
        self._register_setting(row, "chat_format", "chat", card, adv)
        row.add_control(self._combo("chat_format", list(CHAT_FORMATS), 6))
        row = adv.add_row("Embed emotes and badges", "Bigger file, but it works offline.")
        self._register_setting(row, "chat_embed", "chat", card, adv)
        self._switch(row, "chat_embed")

        row = adv.add_row(
            "Overlay type", "How the chat video is saved.",
            info="Transparent · Animation: QuickTime Animation with an alpha channel. Lossless, "
                 "much smaller and faster to draw than ProRes, and read by Premiere Pro and After "
                 "Effects.\nTransparent · ProRes 4444: the same idea with the codec almost every "
                 "editor knows, but very big files. Use it if your editor does not read "
                 "Animation.\nBlack background · H.264: small and quick, but not see-through. In the "
                 "editor, set the clip's blend mode to Screen and the black disappears.")
        self._register_setting(row, "chat_render_mode", "chat", card, adv)
        row.add_control(self._combo("chat_render_mode", CHAT_RENDER_TYPE_NAMES, 36))
        row = adv.add_row("Look", "What is behind the text (not used by the black background type).")
        self._register_setting(row, "chat_render_look", "chat", card, adv)
        row.add_control(self._combo("chat_render_look", CHAT_RENDER_LOOK_NAMES, 28))
        row = adv.add_row("Size", "Width × height in pixels. Height 0 = the same as the video.")
        self._register_setting(row, "chat_render_width", "chat", card, adv)
        row.add_control(self._spin("chat_render_width", 100, 3840, 6))
        times = QLabel("×")
        times.setProperty("role", "muted")
        row.add_control(times)
        self._register_setting(row, "chat_render_height", "chat", card, adv)
        row.add_control(self._spin("chat_render_height", 0, 4320, 6))
        row = adv.add_row("Text size", "Size of the letters, in points.")
        self._register_setting(row, "chat_render_font_size", "chat", card, adv)
        row.add_control(self._spin("chat_render_font_size", 6, 96, 5))
        row = adv.add_row("Frame rate", "Frames per second of the chat video.")
        self._register_setting(row, "chat_render_fps", "chat", card, adv)
        row.add_control(self._combo("chat_render_fps", CHAT_RENDER_FPS_NAMES, 14))
        row = adv.add_row("Smooth scrolling", "Redraws on every frame instead of 5 times a second. Slower.",
                          divider=False)
        self._register_setting(row, "chat_render_smooth", "chat", card, adv)
        self._switch(row, "chat_render_smooth")

    # ------------------------------------------------------------------ Clips
    def _section_clips(self, f: QWidget) -> None:
        self._heading(f, "Clips", "Used by the «Download only selected clip» button in the Plan tab.")
        card = self._card(f)

        self._template_row(
            card, "File name", "How a single downloaded clip is called.", "clip_name_template",
            ["clip_title", "creator", "views", "clip_id", "clip_duration",
             "streamer", "date", "id", "title", "start", "end"],
            info="Clip tokens: {clip_title} {creator} {views} {clip_id} {clip_duration}.\nYou can also use the "
                 "VOD's: {streamer} {date} {id} {title} {start} {end}. ({id} and {title} are the VOD's, not the clip's.)",
            section_key="clips", card=card)

        row = card.add_row("Extra time before", "Seconds added before the clip starts.")
        self._register_setting(row, "clip_pad_before", "clips", card)
        row.add_control(self._spin("clip_pad_before", 0, 600, 6))
        self._unit(row, "s")
        row = card.add_row("Extra time after", "Seconds added after the clip ends.", divider=False)
        self._register_setting(row, "clip_pad_after", "clips", card)
        row.add_control(self._spin("clip_pad_after", 0, 600, 6))
        self._unit(row, "s")

    # ------------------------------------------------------------------ Tools
    def _section_tools(self, f: QWidget) -> None:
        self._heading(f, "Tools", "yt-dlp and ffmpeg do the downloading and cutting.")

        # G5 Dedicated tools status card
        tools_status_card = self._card(f, "Download & processing tools")
        self.ytdlp_row = tools_status_card.add_row("yt-dlp", "Twitch stream downloader engine")
        self.ytdlp_status_label = QLabel("Checking…")
        self.ytdlp_status_label.setProperty("role", "muted")
        self.ytdlp_row.add_control(self.ytdlp_status_label)

        self.ffmpeg_row = tools_status_card.add_row("ffmpeg", "Audio/video muxing, cutting, and stitching", divider=False)
        self.ffmpeg_status_label = QLabel("Checking…")
        self.ffmpeg_status_label.setProperty("role", "muted")
        self.ffmpeg_row.add_control(self.ffmpeg_status_label)

        card = self._card(f)

        row = card.add_row("Installed tools", "")
        self.tools_info_label = WrapLabel("Checking…")
        self.tools_info_label.setProperty("role", "muted")
        self.tools_info_label.setMaximumWidth(640)
        row.below_layout.setContentsMargins(0, 4, 0, 0)
        row.below_layout.addWidget(self.tools_info_label)

        row = card.add_row("Check for yt-dlp updates on startup", "Recommended: Twitch changes often.")
        self._register_setting(row, "auto_update", "tools", card)
        self._switch(row, "auto_update")

        row = card.add_row("Update yt-dlp", "Download the latest version now.")
        self.update_btn = QPushButton("Update yt-dlp now")
        self.update_btn.clicked.connect(self.update_tools_requested)
        row.add_control(self.update_btn)
        row = card.add_row("Tools folder", "Where yt-dlp, ffmpeg and TwitchDownloaderCLI are kept.", divider=False)
        self.tools_folder_btn = QPushButton("Open tools folder")
        self.tools_folder_btn.clicked.connect(self.open_tools_folder)
        row.add_control(self.tools_folder_btn)

        card = self._card(
            f, "Links from web pages",
            "A page can offer a luckytwitch:// link that opens a VOD here with the cut points already "
            "filled in. A link only fills in the Plan tab: it never starts a download.")
        row = card.add_row("Open luckytwitch:// links", "", divider=False)
        self.link_info_label = WrapLabel("")
        self.link_info_label.setProperty("role", "muted")
        self.link_info_label.setMaximumWidth(640)
        row.below_layout.setContentsMargins(0, 4, 0, 0)
        row.below_layout.addWidget(self.link_info_label)
        self.link_btn = QPushButton("Set up links")
        self.link_btn.clicked.connect(self.register_links)
        row.add_control(self.link_btn)
        self.refresh_link_state()

    # ------------------------------------------------------------------ actions of the tab
    def pick_folder(self) -> None:
        start = str(self.binder.get("out_dir") or "") or str(APP_DIR)
        folder = dialogs.choose_folder(self, "Output folder", start)
        if folder:
            self.binder.set("out_dir", folder)

    def open_tools_folder(self) -> None:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            open_in_file_manager(TOOLS_DIR)
        except OSError as e:
            dialogs.info(self, "Tools folder", f"{TOOLS_DIR}\n\n{e}")

    def refresh_link_state(self) -> None:
        """Say whether this computer sends luckytwitch:// links to this app (Windows can be set up from here)."""
        st = weblink.registration()
        if not st.supported:
            self.link_btn.setVisible(False)
            if sys.platform == "darwin":
                self.link_info_label.setText(
                    "macOS sends these links to the app by itself once it is in Applications. If a link "
                    "does nothing, open LuckyTwitch from Applications once and try again.")
            else:
                self.link_info_label.setText("Links are not supported on this system.")
        elif st.state == "ok":
            self.link_btn.setVisible(True)
            self.link_info_label.setText("Set up: these links open this app.")
            self.link_btn.setText("Set up again")
        elif st.state == "other":
            self.link_btn.setVisible(True)
            self.link_info_label.setText(
                "These links currently open another copy of LuckyTwitch. Press the button to use this one.")
            self.link_btn.setText("Use this copy")
        else:
            self.link_btn.setVisible(True)
            self.link_info_label.setText("Not set up: these links do nothing on this computer yet.")
            self.link_btn.setText("Set up links")

    def register_links(self) -> None:
        try:
            weblink.register()
        except OSError as e:
            dialogs.error(self, "Links", f"Windows did not accept the setting:\n{e}")
            return
        self.refresh_link_state()
        self.status_message.emit("Links are set up: luckytwitch:// links now open this app.")

    # ------------------------------------------------------------------ what the window tells the tab
    def set_tools_info(self, text: str) -> None:
        self.tools_info_label.setText(text)
        for part in text.replace("\n", " · ").split(" · "):
            p = part.strip()
            if "yt-dlp" in p.lower() and hasattr(self, "ytdlp_status_label"):
                self.ytdlp_status_label.setText(p)
            elif "ffmpeg" in p.lower() and hasattr(self, "ffmpeg_status_label"):
                self.ffmpeg_status_label.setText(p)

    def set_tools_running(self, running: bool) -> None:
        self.update_btn.setEnabled(not running)

    def set_saved_chat_running(self, running: bool) -> None:
        self.saved_chat_btn.setEnabled(not running)
