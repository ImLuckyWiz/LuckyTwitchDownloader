"""
Options tab: a sidebar with one section visible at a time (Output, Cuts, Chapters, Premiere Pro, Chat, Clips,
Tools). Each setting is a row (bold name, one-line hint, the control on the right); on/off settings are
switches, long explanations live in the little «i» tooltips, and settings that are set once and rarely
touched sit in a collapsed «Advanced» area inside their section.

Template fields (file name, stream folder, clip name, chapter title) get clickable ``{token}`` chips and a
live example. The example uses the VOD you loaded, or a sample VOD until then.

This is a mixin for ``App`` (luckytwitch_downloader.py). It expects the host to provide ``tab_options``
(a plain ttk.Frame), ``STRATEGY_NAMES``, ``CHAT_RENDER_TYPE_NAMES``, ``CHAT_RENDER_LOOK_NAMES``, ``CHAT_RENDER_FPS_NAMES``, ``var()``, ``vars``, ``source``, ``pick_folder``, ``open_output_folder``,
``update_preview``, ``refresh_clips``, ``update_tools_now``, ``open_tools_folder`` and ``render_saved_chat``. It creates
``tools_info`` and ``update_btn`` (the host's message loop updates them) and ``options_nav``.

Every setting keeps the variable name it always had, so saved settings and ``build_options()`` are unchanged.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk

import weblink
from luckytwitch_engine import CHAT_FORMATS, JobOptions, Part, SourceInfo, _SafeDict, part_stem, stream_dir
from ui.common import BG2
from ui.widgets import Card, Collapsible, ScrollFrame, SideNav, Toggle, TokenChips

SECTIONS = [
    ("output", "Output"),
    ("cuts", "Cuts"),
    ("chapters", "Chapters"),
    ("premiere", "Premiere Pro"),
    ("chat", "Chat"),
    ("clips", "Clips"),
    ("tools", "Tools"),
]

SAMPLE_SOURCE = dict(url="https://www.twitch.tv/videos/123", id="v123", title="Big Stream", uploader="Streamer",
                     duration=7200.0, date="2026-10-01", twitch_vod_id="123")
SAMPLE_CLIP = {"id": "ClipId", "title": "Epic fail", "creator_name": "viewer1", "view_count": 500, "duration": 30}

_DEFAULTS = JobOptions(cut_text="", out_dir="")  # the engine's own default templates


class OptionsTabMixin:
    # ------------------------------------------------------------------ layout
    def build_options_tab(self):
        page = self.tab_options
        page.columnconfigure(1, weight=1)
        page.rowconfigure(0, weight=1)
        self._example_refreshers: list = []
        self._opt_sections: dict[str, ttk.Frame] = {}

        self.options_nav = SideNav(page, SECTIONS, self.show_options_section)
        self.options_nav.grid(row=0, column=0, sticky="n", padx=(0, 10), pady=(8, 0))
        self.options_scroll = ScrollFrame(page, padding=4)
        self.options_scroll.grid(row=0, column=1, sticky="nsew")
        body = self.options_scroll.body
        body.columnconfigure(0, weight=1)

        for key, _label in SECTIONS:
            frame = ttk.Frame(body)
            frame.columnconfigure(0, weight=1)
            frame.grid(row=0, column=0, sticky="nsew")
            self._opt_sections[key] = frame
        self._section_output(self._opt_sections["output"])
        self._section_cuts(self._opt_sections["cuts"])
        self._section_chapters(self._opt_sections["chapters"])
        self._section_premiere(self._opt_sections["premiere"])
        self._section_chat(self._opt_sections["chat"])
        self._section_clips(self._opt_sections["clips"])
        self._section_tools(self._opt_sections["tools"])

        self.options_nav.select("output")
        self.refresh_name_examples()

    def show_options_section(self, key: str) -> None:
        for k, frame in self._opt_sections.items():
            if k == key:
                frame.grid()
            else:
                frame.grid_remove()
        self.options_scroll.canvas.yview_moveto(0)
        self.options_scroll.refit()

    def _advanced(self, card: Card, hint: str) -> Collapsible:
        """The collapsed «Advanced» area at the bottom of a card."""
        adv = Collapsible(card.body, "Advanced", hint, on_change=self.options_scroll.refit)
        adv.grid(row=card._rows, column=0, sticky="ew")
        return adv

    def _heading(self, parent, title: str, subtitle: str) -> None:
        ttk.Label(parent, text=title, style="Title.TLabel").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(parent, text=subtitle, style="Muted.TLabel", wraplength=640, justify="left").grid(
            row=1, column=0, sticky="w", padx=4, pady=(2, 10))

    def _card(self, parent, row: int, title: str | None = None, subtitle: str | None = None) -> Card:
        card = Card(parent, title, subtitle)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        return card

    # ------------------------------------------------------------------ small builders
    def _switch(self, row, name: str, command=None) -> Toggle:
        t = Toggle(row.control, self.var(name), command=command, bg=BG2)
        t.pack()
        return t

    def _entry(self, parent, name: str, width: int = 0, **kw) -> ttk.Entry:
        return ttk.Entry(parent, textvariable=self.var(name), style="Card.TEntry", **({"width": width} if width else {}), **kw)

    def _spin(self, parent, name: str, lo: int, hi: int, width: int = 6, **kw) -> ttk.Spinbox:
        return ttk.Spinbox(parent, textvariable=self.var(name), from_=lo, to=hi, width=width, style="Card.TSpinbox", **kw)

    def _template_row(self, holder, title: str, hint: str, name: str, tokens: list[str], example, info: str = "",
                      divider: bool = True, per_row: int = 6) -> ttk.Entry:
        """A name template: entry + clickable token chips + a live example. Returns the entry."""
        row = holder.add_row(title, hint, info, divider=divider)
        entry = self._entry(row.below, name)
        entry.grid(row=0, column=0, sticky="ew", pady=(8, 0))
        chip_row = TokenChips(row.below, entry, tokens, per_row=per_row)
        chip_row.grid(row=1, column=0, sticky="w", pady=(8, 0))
        label = ttk.Label(row.below, style="CardMuted.TLabel", wraplength=640, justify="left")
        label.grid(row=2, column=0, sticky="w", pady=(2, 0))

        def refresh(*_):
            try:
                label.config(text="Example:  " + example())
            except Exception as e:  # noqa: BLE001  (a half-typed template must never break the tab)
                label.config(text=f"Example:  (can't be shown: {e})")

        self.vars[name].trace_add("write", refresh)
        self._example_refreshers.append(refresh)
        entry._lt_chips = chip_row  # so callers can disable both together
        return entry

    # ------------------------------------------------------------------ live examples
    def _example_source(self) -> SourceInfo:
        return self.source if getattr(self, "source", None) else SourceInfo(**SAMPLE_SOURCE)

    def _template(self, name: str, fallback: str) -> str:
        v = self.vars.get(name)
        return (v.get().strip() if v is not None else "") or fallback

    def _example_opts(self) -> JobOptions:
        container = self.vars["container"].get() if "container" in self.vars else "mp4"
        return JobOptions(
            cut_text="", out_dir="", container=container,
            name_template=self._template("name_template", _DEFAULTS.name_template),
            folder_template=self._template("folder_template", _DEFAULTS.folder_template),
            clip_name_template=self._template("clip_name_template", _DEFAULTS.clip_name_template),
            subfolders=True)

    def _example_file_name(self) -> str:
        opts = self._example_opts()
        return f"{part_stem(self._example_source(), opts, Part(1, 0, 3600), 3)}.{opts.container}"

    def _example_folder_name(self) -> str:
        opts = self._example_opts()
        return stream_dir(self._example_source(), opts).as_posix().replace("./", "").replace("\\", "/")

    def _example_clip_name(self) -> str:
        opts = self._example_opts()
        return f"{part_stem(self._example_source(), opts, Part(1, 0, 30), 1, SAMPLE_CLIP)}.{opts.container}"

    def _example_chapter(self) -> str:
        tpl = self._template("title_tpl", "{title} ({creator}, {views} views)")
        data = _SafeDict(title=SAMPLE_CLIP["title"], creator=SAMPLE_CLIP["creator_name"],
                         views=SAMPLE_CLIP["view_count"], duration=SAMPLE_CLIP["duration"])
        try:
            return tpl.format_map(data)
        except (ValueError, IndexError):
            return "(the template has an unfinished {…})"

    def refresh_name_examples(self) -> None:
        """Redraw every «Example:» line (also called when a VOD is loaded, to use its real name)."""
        for fn in getattr(self, "_example_refreshers", []):
            fn()

    # ------------------------------------------------------------------ sections
    def _section_output(self, f):
        self._heading(f, "Output", "Where the finished files go and how they are named.")
        card = self._card(f, 2)

        row = card.add_row("Output folder", "Where the finished files are saved.")
        ttk.Button(row.control, text="Browse…", style="Card.TButton", command=self.pick_folder).pack(side="left")
        ttk.Button(row.control, text="Open folder", style="Card.TButton",
                   command=lambda: self.open_output_folder()).pack(side="left", padx=(6, 0))
        self._entry(row.below, "out_dir").grid(row=0, column=0, sticky="ew", pady=(8, 0))

        row = card.add_row("Format", "Container of the finished files.", divider=False)
        ttk.Combobox(row.control, textvariable=self.var("container"), values=["mp4", "mkv"], width=7,
                     state="readonly", style="Card.TCombobox").pack()
        self.vars["container"].trace_add("write", lambda *_: self.refresh_name_examples())

        adv = self._advanced(card, "download threads, file and folder names")
        row = adv.add_row("Download threads", "Parallel connections per download. 8 is a good default.")
        self._spin(row.control, "threads", 1, 32, 5).pack()

        self._template_row(
            adv, "File name", "How each part is called. Click a token to add it.", "name_template",
            ["streamer", "date", "id", "title", "n", "total", "start", "end"], self._example_file_name,
            info="{n} is the part number, {total} how many parts there are, {start} and {end} the part's "
                 "time range in the VOD (like 01h02m03s). {id} is the VOD's Twitch id.")

        row = adv.add_row("Organize in subfolders", "Folder / Streamer / Stream / parts.")
        self._switch(row, "subfolders", command=self._sync_folder_template)

        self.folder_entry = self._template_row(
            adv, "Stream folder name", "Name of the folder that holds one stream's files.", "folder_template",
            ["streamer", "date", "id", "title"], self._example_folder_name, divider=False, per_row=4)
        self.vars["subfolders"].trace_add("write", lambda *_: self._sync_folder_template())
        self._sync_folder_template()

    def _sync_folder_template(self) -> None:
        on = bool(self.vars["subfolders"].get())
        self.folder_entry.state(["!disabled"] if on else ["disabled"])
        self.folder_entry._lt_chips.set_enabled(on)

    def _section_cuts(self, f):
        self._heading(f, "Cuts", "How the VOD is downloaded and cut into parts.")
        card = self._card(f, 2)

        row = card.add_row("Strategy", "How the VOD is downloaded.",
                           info="Auto: downloads the full VOD once and splits it when the parts cover at least the "
                                "threshold (see Advanced), otherwise downloads only the parts.\nOr force one of the two.")
        cb = ttk.Combobox(row.control, textvariable=self.var("strategy"), values=self.STRATEGY_NAMES, state="readonly",
                          width=30, style="Card.TCombobox")
        cb.pack()
        cb.bind("<<ComboboxSelected>>", self.update_preview)

        row = card.add_row("Frame-exact cuts", "Slow and CPU heavy. Off = lossless, ~2 s precision.",
                           info="Off (default): the cuts are lossless and land on keyframes, about 2 seconds "
                                "of precision.\nOn: the video is re-encoded so every cut is frame-exact. "
                                "That is slow and uses a lot of CPU.")
        self._switch(row, "exact")

        row = card.add_row("Keep the full VOD", "Also keep the full file when the full-VOD strategy is used.",
                           divider=False)
        self._switch(row, "keep_full")

        adv = self._advanced(card, "auto threshold")
        row = adv.add_row("Auto threshold", "Auto uses the full VOD above this share.",
                          divider=False,
                          info="Auto downloads the full VOD (and splits it) when the parts cover at least this "
                               "percentage of it; below that it downloads only the parts.")
        sp = self._spin(row.control, "threshold", 1, 100, 5, command=self.update_preview)
        sp.bind("<KeyRelease>", self.update_preview)
        sp.pack(side="left")
        ttk.Label(row.control, text="%", style="Card.TLabel").pack(side="left", padx=(4, 0))

    def _section_chapters(self, f):
        self._heading(f, "Chapters", "How the chapters look. Switch them on with «Add clips as chapters» in the Plan tab.")
        card = self._card(f, 2)

        e = self._template_row(
            card, "Chapter title", "Name of each clip's chapter.", "title_tpl",
            ["title", "creator", "views", "duration"], self._example_chapter, per_row=4)
        e.bind("<KeyRelease>", lambda ev: self.refresh_clips(), add="+")

        row = card.add_row("Tail", "Seconds the chapter lasts after the clip ends.")
        sp = self._spin(row.control, "pad_after", 0, 600, 6, command=self.refresh_clips)
        sp.bind("<KeyRelease>", lambda ev: self.refresh_clips())
        sp.pack(side="left")
        ttk.Label(row.control, text="s", style="Card.TLabel").pack(side="left", padx=(4, 0))

        row = card.add_row("Gap chapter name", "Name for the stretches between clips.",
                           info="MP4 needs every stretch to have a name, so don't leave this empty for MP4. "
                                "Empty is fine only for MKV.", divider=False)
        self._entry(row.control, "gap_title", 18).pack()

    def _section_premiere(self, f):
        self._heading(f, "Premiere Pro", "Markers you can bring into Adobe Premiere Pro next to each part.")
        card = self._card(f, 2)

        row = card.add_row("LuckyTwitch Premiere plugin", "Saves a .markers.json with colors and clip details.",
                           info="One .markers.json next to each part, for the LuckyTwitch Premiere plugin. "
                                "It works even if chapters are off.")
        self._switch(row, "premiere_plugin", command=self.refresh_clips)

        row = card.add_row("Game / category changes", "Also marks every time the game changes.",
                           info="Adds markers named «GAME: ...» to the .markers.xml and as game markers in the "
                                ".markers.json. Works for full VODs and for parts, even if chapters are off.")
        self._switch(row, "game_markers")

        row = card.add_row("Muted audio", "Also marks the stretches Twitch silenced.", divider=False,
                           info="Twitch mutes copyrighted audio in a VOD. Those stretches are added to the "
                                ".markers.json as «muted» markers (the plugin decides the color), so you can see "
                                "them in Premiere. It needs the plugin file above to be on. The same stretches "
                                "show in red on the Plan tab's timeline.")
        self._switch(row, "muted_markers")

        adv = self._advanced(card, "plain markers and clip list")
        row = adv.add_row("Plain Premiere markers", "Saves a .markers.xml you can import without the plugin.",
                          info="Plain import, without colors. Works even if chapters are off.")
        self._switch(row, "premiere_xml", command=self.refresh_clips)
        row = adv.add_row("Clip list", "Saves a .clips.json (clip titles, creators, links) next to each part.",
                          divider=False)
        self._switch(row, "sidecar")

    def _section_chat(self, f):
        self._heading(f, "Chat", "Download the chat that went with the stream, or turn it into a video you can put "
                                 "over the footage in your editor (Twitch VODs only).")
        card = self._card(f, 2)

        row = card.add_row("Download the chat", "Saves the chat of each part next to it.",
                           info="Uses TwitchDownloaderCLI, downloaded the first time. Saved next to each part "
                                "as «name.chat.json». Inside the .json the message times count from the start of "
                                "the VOD, not from the start of the part; the file's start/end say which stretch "
                                "it covers.\nTwitchDownloader is MIT licensed (github.com/lay295/TwitchDownloader).")
        self._switch(row, "chat")

        row = card.add_row("Chat as a video (overlay)", "Draws the chat of each part as a video for your editor.",
                           info="Saved next to each part as «name.chat-overlay.mov» (or .mp4). It works even if the "
                                "stream had no chat on screen: put it on the track above the video, at the start of "
                                "the part, and place it where you want it. It begins together with the part and can "
                                "run up to a second longer at the end.\nIt takes a while: a long part can take "
                                "from minutes to hours to draw, depending on the type. Emotes and badges are "
                                "fetched from Twitch, BTTV, FFZ and 7TV when it is drawn, so it needs internet.\n"
                                "Size on disk for a very busy chat (3 messages a second, 400 x 1080): about 3.4 GB "
                                "per hour with Animation, 28 GB with ProRes 4444, 0.4 GB with H.264.")
        self._switch(row, "chat_render")

        row = card.add_row("Draw the overlay from a saved chat", "Pick a «.chat.json» you already have. Nothing is downloaded.",
                           divider=False,
                           info="Uses the overlay settings below (type, look, size, text size, frame rate). The video is "
                                "not touched. If «name.mp4» (or .mkv…) is next to the chat, the overlay takes its size "
                                "and frame rate; if «name.markers.json» is there too, it is lined up to the fraction of "
                                "a second. The result is saved next to the chat as «name.chat-overlay.mov» (or .mp4).")
        self.saved_chat_btn = ttk.Button(row.control, text="Choose chat file…", style="Card.TButton",
                                         command=self.render_saved_chat)
        self.saved_chat_btn.pack()

        adv = self._advanced(card, "file format, embedded emotes and how the overlay looks")
        row = adv.add_row("Format", "File type of the saved chat.")
        ttk.Combobox(row.control, textvariable=self.var("chat_format"), values=list(CHAT_FORMATS), width=8,
                     state="readonly", style="Card.TCombobox").pack()
        row = adv.add_row("Embed emotes and badges", "Bigger file, but it works offline.")
        self._switch(row, "chat_embed")

        row = adv.add_row("Overlay type", "How the chat video is saved.",
                          info="Transparent · Animation: QuickTime Animation with an alpha channel. Lossless, "
                               "much smaller and faster to draw than ProRes, and read by Premiere Pro and After "
                               "Effects.\nTransparent · ProRes 4444: the same idea with the codec almost every "
                               "editor knows, but very big files. Use it if your editor does not read "
                               "Animation.\nBlack background · H.264: small and quick, but not see-through. In the "
                               "editor, set the clip's blend mode to Screen and the black disappears.")
        ttk.Combobox(row.control, textvariable=self.var("chat_render_mode"), values=self.CHAT_RENDER_TYPE_NAMES,
                     width=36, state="readonly", style="Card.TCombobox").pack()
        row = adv.add_row("Look", "What is behind the text (not used by the black background type).")
        ttk.Combobox(row.control, textvariable=self.var("chat_render_look"), values=self.CHAT_RENDER_LOOK_NAMES,
                     width=28, state="readonly", style="Card.TCombobox").pack()
        row = adv.add_row("Size", "Width × height in pixels. Height 0 = the same as the video.")
        self._spin(row.control, "chat_render_height", 0, 4320, 6).pack(side="right")
        ttk.Label(row.control, text="×", style="CardMuted.TLabel").pack(side="right", padx=4)
        self._spin(row.control, "chat_render_width", 100, 3840, 6).pack(side="right")
        row = adv.add_row("Text size", "Size of the letters, in points.")
        self._spin(row.control, "chat_render_font_size", 6, 96, 5).pack()
        row = adv.add_row("Frame rate", "Frames per second of the chat video.")
        ttk.Combobox(row.control, textvariable=self.var("chat_render_fps"), values=self.CHAT_RENDER_FPS_NAMES,
                     width=14, state="readonly", style="Card.TCombobox").pack()
        row = adv.add_row("Smooth scrolling", "Redraws on every frame instead of 5 times a second. Slower.",
                          divider=False)
        self._switch(row, "chat_render_smooth")

    def _section_clips(self, f):
        self._heading(f, "Clips", "Used by the «Download only selected clip» button in the Plan tab.")
        card = self._card(f, 2)

        self._template_row(
            card, "File name", "How a single downloaded clip is called.", "clip_name_template",
            ["clip_title", "creator", "views", "clip_id", "clip_duration",
             "streamer", "date", "id", "title", "start", "end"], self._example_clip_name,
            info="Clip tokens: {clip_title} {creator} {views} {clip_id} {clip_duration}.\nYou can also use the "
                 "VOD's: {streamer} {date} {id} {title} {start} {end}. ({id} and {title} are the VOD's, not the clip's.)")

        row = card.add_row("Extra time before", "Seconds added before the clip starts.")
        self._spin(row.control, "clip_pad_before", 0, 600, 6).pack(side="left")
        ttk.Label(row.control, text="s", style="Card.TLabel").pack(side="left", padx=(4, 0))
        row = card.add_row("Extra time after", "Seconds added after the clip ends.", divider=False)
        self._spin(row.control, "clip_pad_after", 0, 600, 6).pack(side="left")
        ttk.Label(row.control, text="s", style="Card.TLabel").pack(side="left", padx=(4, 0))

    def _section_tools(self, f):
        self._heading(f, "Tools", "yt-dlp and ffmpeg do the downloading and cutting.")
        card = self._card(f, 2)

        row = card.add_row("Installed tools", "")
        self.tools_info = tk.StringVar(value="Checking…")
        ttk.Label(row.below, textvariable=self.tools_info, style="CardMuted.TLabel", justify="left",
                  wraplength=640).grid(row=0, column=0, sticky="w", pady=(4, 0))

        row = card.add_row("Check for yt-dlp updates on startup", "Recommended: Twitch changes often.")
        self._switch(row, "auto_update")

        row = card.add_row("Update yt-dlp", "Download the latest version now.")
        self.update_btn = ttk.Button(row.control, text="Update yt-dlp now", style="Card.TButton",
                                     command=self.update_tools_now)
        self.update_btn.pack()
        row = card.add_row("Tools folder", "Where yt-dlp, ffmpeg and TwitchDownloaderCLI are kept.", divider=False)
        ttk.Button(row.control, text="Open tools folder", style="Card.TButton", command=self.open_tools_folder).pack()

        card = self._card(f, 3, "Links from web pages",
                          "A page can offer a luckytwitch:// link that opens a VOD here with the cut points already "
                          "filled in. A link only fills in the Plan tab: it never starts a download.")
        row = card.add_row("Open luckytwitch:// links", "", divider=False)
        self.link_info = tk.StringVar(value="")
        ttk.Label(row.below, textvariable=self.link_info, style="CardMuted.TLabel", justify="left",
                  wraplength=640).grid(row=0, column=0, sticky="w", pady=(4, 0))
        self.link_btn = ttk.Button(row.control, text="Set up links", style="Card.TButton", command=self.register_links)
        self.link_btn.pack()
        self.refresh_link_state()

    def refresh_link_state(self) -> None:
        """Say whether this computer sends luckytwitch:// links to this app (Windows can be set up from here)."""
        st = weblink.registration()
        if not st.supported:
            self.link_btn.pack_forget()
            if sys.platform == "darwin":
                self.link_info.set("macOS sends these links to the app by itself once it is in Applications. If a link "
                                   "does nothing, open LuckyTwitch from Applications once and try again.")
            else:
                self.link_info.set("Links are not supported on this system.")
        elif st.state == "ok":
            self.link_info.set("Set up: these links open this app.")
            self.link_btn.config(text="Set up again")
        elif st.state == "other":
            self.link_info.set("These links currently open another copy of LuckyTwitch. Press the button to use this one.")
            self.link_btn.config(text="Use this copy")
        else:
            self.link_info.set("Not set up: these links do nothing on this computer yet.")
            self.link_btn.config(text="Set up links")

    def register_links(self) -> None:
        try:
            weblink.register()
        except OSError as e:
            messagebox.showerror("Links", f"Windows did not accept the setting:\n{e}")
            return
        self.refresh_link_state()
        self.set_status("Links are set up: luckytwitch:// links now open this app.")
