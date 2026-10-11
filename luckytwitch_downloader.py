"""
LuckyTwitch Downloader - download a Twitch VOD (via yt-dlp) and cut it into
several parts in one go, optionally adding the VOD's clips as chapters.

Requirements:
    pip install requests

yt-dlp and ffmpeg are downloaded automatically on first run (into a per-user
"tools" folder) and yt-dlp is kept up to date. Copies already on PATH, next to
this script or in a "bin" folder are used instead of downloading.

Run:
    python luckytwitch_downloader.py

Twitch API keys (Client ID / Secret) are OPTIONAL: only needed for clips -> chapters.
They are stored in config.json next to this script (same file as clips_downloader.py).
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

from luckytwitch_engine import (
    APP_DIR,
    TOOLS_DIR,
    Cancelled,
    ClipFilter,
    Ctx,
    EngineError,
    Job,
    JobOptions,
    TwitchClient,
    describe_tools,
    ensure_tools,
    fetch_clips_for_vod,
    fmt_hms,
    get_source_info,
    insert_cut_point,
    make_chapters,
    make_plan,
    run_job,
    user_data_dir,
)

# From source: keep config next to the script (as before). Packaged app: the app
# folder may be read-only (inside a macOS .app, Program Files...), so use the
# per-user data folder instead.
FROZEN = getattr(sys, "frozen", False)
DATA_DIR = user_data_dir() if FROZEN else APP_DIR
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
CONFIG_PATH = DATA_DIR / "config.json"
SETTINGS_PATH = DATA_DIR / "luckytwitch_settings.json"

if sys.platform == "win32":
    MONO_FONT, UI_FONT = "Consolas", "Segoe UI"
elif sys.platform == "darwin":
    MONO_FONT, UI_FONT = "Menlo", "Helvetica Neue"
else:
    MONO_FONT, UI_FONT = "DejaVu Sans Mono", "DejaVu Sans"

STRATEGIES = {
    "Auto": "auto",
    "Download full VOD, then split": "full",
    "Download only the parts": "sections",
}

DEFAULTS = {
    "out_dir": str((Path.home() / "Downloads" / "LuckyTwitch") if FROZEN else (APP_DIR / "downloads")),
    "container": "mp4",
    "strategy": "Auto",
    "threshold": "60",
    "exact": False,
    "keep_full": False,
    "threads": "8",
    "name_template": "{streamer} - {date} - {id} - part{n}",
    "chapters": False,
    "min_views": "0",
    "min_duration": "0",
    "top_n": "0",
    "pad_before": "3",
    "pad_after": "0",
    "title_tpl": "{title} ({creator}, {views} views)",
    "gap_title": "Stream",
    "sidecar": False,
    "subfolders": True,
    "folder_template": "{date} - {title} - {id}",
    "auto_update": True,
}

BG = "#1e1f22"
BG2 = "#2b2d31"
BG3 = "#3a3c42"
FG = "#e6e6e6"
MUTED = "#9a9da4"
ERR = "#ff6b6b"
OK = "#6bd49a"
ACCENT = "#9146ff"


def bmp(text) -> str:
    """Drop characters outside the Basic Multilingual Plane (emoji): some Windows Tk builds choke on them."""
    return "".join(ch for ch in str(text) if ord(ch) <= 0xFFFF)


# --------------------------------------------------------------------------- #
# Config / settings
# --------------------------------------------------------------------------- #
def load_credentials():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if data.get("client_id") and data.get("client_secret"):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def save_credentials(client_id, client_secret):
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.update({"client_id": client_id, "client_secret": client_secret})
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_settings():
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


# --------------------------------------------------------------------------- #
# Theme (same look as clips_downloader.py)
# --------------------------------------------------------------------------- #
def dark_titlebar(window):
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:  # noqa: BLE001
        pass


def apply_dark_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG2, bordercolor=BG3,
                    lightcolor=BG, darkcolor=BG, troughcolor=BG2, focuscolor=BG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("TLabelframe", background=BG, bordercolor=BG3)
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT)
    style.configure("TButton", background=BG3, foreground=FG, padding=6, borderwidth=0)
    style.map("TButton", background=[("disabled", BG2), ("active", ACCENT)], foreground=[("disabled", "#777777")])
    style.configure("TEntry", fieldbackground=BG2, foreground=FG, insertcolor=FG, bordercolor=BG3)
    style.configure("TSpinbox", fieldbackground=BG2, foreground=FG, insertcolor=FG, arrowcolor=FG,
                    background=BG3, bordercolor=BG3)
    style.configure("TCombobox", fieldbackground=BG2, foreground=FG, arrowcolor=FG, background=BG3,
                    selectbackground=BG2, selectforeground=FG, bordercolor=BG3)
    style.map("TCombobox", fieldbackground=[("readonly", BG2)], foreground=[("readonly", FG)])
    root.option_add("*TCombobox*Listbox.background", BG2)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT), ("!selected", BG2)])
    style.configure("TNotebook", background=BG, bordercolor=BG3, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", background=BG2, foreground=FG, padding=(14, 6), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", ACCENT), ("active", BG3)],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview", background=BG2, fieldbackground=BG2, foreground=FG, rowheight=24, borderwidth=0)
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=BG3, foreground=FG, relief="flat")
    style.map("Treeview.Heading", background=[("active", "#4a4d55")])
    style.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG2, arrowcolor=FG, bordercolor=BG2)
    style.map("Vertical.TScrollbar", background=[("active", "#4a4d55")])
    style.configure("Horizontal.TProgressbar", troughcolor=BG2, background=ACCENT, bordercolor=BG2,
                    lightcolor=ACCENT, darkcolor=ACCENT)
    dark_titlebar(root)


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: queue.Queue = queue.Queue()
        self.client: TwitchClient | None = None
        self.source = None
        self.clips: list[dict] = []
        self.clips_loaded = False
        self.items: list[dict] = []  # queue items: {job, iid, status}
        self.ctx: Ctx | None = None
        self.worker: threading.Thread | None = None
        self.vars: dict[str, tk.Variable] = {}
        self.settings = load_settings()
        self._progress_mode = "determinate"
        self._job_prefix = ""
        self.tools_busy = False
        self.tools_ctx: Ctx | None = None

        root.title("LuckyTwitch Downloader")
        root.geometry("1020x780")
        root.minsize(900, 700)
        self.build_ui()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll_queue)

        cfg = load_credentials()
        if cfg:
            self.client = TwitchClient(cfg["client_id"], cfg["client_secret"])
        self.set_status("Ready. Paste a VOD URL or ID and press «Get info».")
        self.update_preview()
        self.refresh_clips()
        self.start_tools_setup()

    # ---------------------------- helpers ---------------------------- #
    def var(self, name: str) -> tk.Variable:
        default = self.settings[name]
        v: tk.Variable = tk.BooleanVar(value=default) if isinstance(default, bool) else tk.StringVar(value=default)
        self.vars[name] = v
        return v

    def num(self, name: str, cast=float, default=0):
        try:
            return cast(float(self.vars[name].get()))
        except (ValueError, tk.TclError):
            return default

    def build_filter(self) -> ClipFilter:
        v = self.vars
        return ClipFilter(
            min_views=self.num("min_views", int),
            min_duration=self.num("min_duration", float),
            top_n=self.num("top_n", int),
            pad_before=self.num("pad_before", float, 3),
            pad_after=self.num("pad_after", float),
            title_template=v["title_tpl"].get() or DEFAULTS["title_tpl"],
            gap_title=v["gap_title"].get().strip(),
        )

    def build_options(self) -> JobOptions:
        v = self.vars
        return JobOptions(
            cut_text=self.cuts.get("1.0", "end").strip(),
            out_dir=v["out_dir"].get().strip() or DEFAULTS["out_dir"],
            container=v["container"].get(),
            strategy=STRATEGIES.get(v["strategy"].get(), "auto"),
            full_threshold=min(max(self.num("threshold", float, 60), 1), 100) / 100,
            exact=bool(v["exact"].get()),
            keep_full=bool(v["keep_full"].get()),
            threads=max(1, self.num("threads", int, 8)),
            name_template=v["name_template"].get().strip() or DEFAULTS["name_template"],
            chapters=bool(v["chapters"].get()),
            clip_filter=self.build_filter(),
            sidecar=bool(v["sidecar"].get()),
            subfolders=bool(v["subfolders"].get()),
            folder_template=v["folder_template"].get().strip() or DEFAULTS["folder_template"],
        )

    def save_settings(self):
        data = {k: v.get() for k, v in self.vars.items()}
        try:
            SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def set_status(self, text: str):
        self.status.set(text)

    def log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ---------------------------- UI ---------------------------- #
    def build_ui(self):
        # progress + status at the bottom (always visible)
        bottom = ttk.Frame(self.root, padding=(10, 4, 10, 8))
        bottom.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.status = tk.StringVar()
        ttk.Label(bottom, textvariable=self.status, anchor="w").pack(fill="x", pady=(4, 0))

        # top bar
        top = ttk.Frame(self.root, padding=(10, 10, 10, 2))
        top.pack(fill="x")
        ttk.Label(top, text="VOD URL or ID:").pack(side="left")
        self.vod_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.vod_var)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        entry.bind("<Return>", lambda e: self.on_get_info())
        self.info_btn = ttk.Button(top, text="Get info", command=self.on_get_info)
        self.info_btn.pack(side="left")
        ttk.Button(top, text="Twitch API…", command=self.ask_credentials).pack(side="left", padx=(8, 0))
        self.info_var = tk.StringVar(value="No VOD loaded.")
        ttk.Label(self.root, textvariable=self.info_var, style="Muted.TLabel", padding=(12, 0, 10, 4)).pack(fill="x")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        self.tab_plan = ttk.Frame(nb, padding=8)
        self.tab_options = ttk.Frame(nb, padding=8)
        self.tab_queue = ttk.Frame(nb, padding=8)
        nb.add(self.tab_plan, text="  Plan  ")
        nb.add(self.tab_options, text="  Options  ")
        nb.add(self.tab_queue, text="  Queue & log  ")
        self.notebook = nb
        self.build_plan_tab()
        self.build_options_tab()
        self.build_queue_tab()

    def build_plan_tab(self):
        t = self.tab_plan
        t.columnconfigure(0, weight=1)
        t.rowconfigure(1, weight=1)

        # --- cut points --- #
        cutf = ttk.LabelFrame(t, text="Cut points", padding=8)
        cutf.grid(row=0, column=0, sticky="ew")
        cutf.columnconfigure(0, weight=1)
        self.cuts = tk.Text(cutf, height=3, bg=BG2, fg=FG, insertbackground=FG, relief="flat",
                            font=(MONO_FONT, 11), padx=6, pady=4, wrap="word")
        self.cuts.grid(row=0, column=0, sticky="ew")
        self.cuts.bind("<KeyRelease>", self.update_preview)
        ttk.Label(
            cutf,
            text="Boundaries in order, e.g.  0:00:00 - 0:30:00 - 1:30:00 - end   (end = end of the VOD).   "
                 "To skip a section use «;» or a new line:  0:00:00 - 0:30:00 ; 2:00:00 - end",
            style="Muted.TLabel", wraplength=940, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 4))
        pf = ttk.Frame(cutf)
        pf.grid(row=2, column=0, sticky="ew")
        pf.columnconfigure(0, weight=1)
        self.preview = tk.Text(pf, height=5, bg=BG, fg=MUTED, relief="flat", state="disabled",
                               font=(UI_FONT, 10), wrap="word", cursor="arrow")
        self.preview.grid(row=0, column=0, sticky="ew")
        psb = ttk.Scrollbar(pf, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=psb.set)
        psb.grid(row=0, column=1, sticky="ns")
        self.preview.tag_configure("ok", foreground=OK)
        self.preview.tag_configure("err", foreground=ERR)
        self.preview.tag_configure("muted", foreground=MUTED)

        # --- clips -> chapters --- #
        chf = ttk.LabelFrame(t, text="Clips → chapters (optional)", padding=8)
        chf.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        chf.columnconfigure(0, weight=1)
        chf.rowconfigure(1, weight=1)

        frow = ttk.Frame(chf)
        frow.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(frow, text="Add clips as chapters", variable=self.var("chapters"),
                        command=self.refresh_clips).pack(side="left")

        def num_field(label, name, width=6):
            ttk.Label(frow, text=label).pack(side="left", padx=(14, 4))
            sp = ttk.Spinbox(frow, textvariable=self.var(name), from_=0, to=1_000_000, width=width,
                             command=self.refresh_clips)
            sp.pack(side="left")
            sp.bind("<KeyRelease>", lambda e: self.refresh_clips())

        num_field("Min views", "min_views")
        num_field("Min duration (s)", "min_duration", 5)
        num_field("Top N by views (0 = all)", "top_n", 5)
        num_field("Lead-in (s)", "pad_before", 4)

        cols = ("at", "views", "dur", "title", "creator", "chap")
        self.tree = ttk.Treeview(chf, columns=cols, show="headings", selectmode="browse", height=6)
        for col, text, width, anchor in [
            ("at", "At", 80, "center"), ("views", "Views", 70, "center"), ("dur", "Dur", 60, "center"),
            ("title", "Title", 380, "w"), ("creator", "Creator", 140, "w"), ("chap", "Chapter", 70, "center"),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "title"))
        sb = ttk.Scrollbar(chf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self.open_clip)
        self.clips_lbl = tk.StringVar()
        brow = ttk.Frame(chf)
        brow.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(brow, text="Split at selected clip", command=self.split_at_clip).pack(side="left")
        ttk.Label(brow, textvariable=self.clips_lbl, style="Muted.TLabel").pack(side="left", padx=10)

        # --- add buttons --- #
        act = ttk.Frame(t)
        act.grid(row=2, column=0, sticky="e", pady=(8, 0))
        ttk.Button(act, text="Add to queue", command=lambda: self.add_to_queue(False)).pack(side="left")
        ttk.Button(act, text="Add & start", command=lambda: self.add_to_queue(True)).pack(side="left", padx=(6, 0))

    def build_options_tab(self):
        t = self.tab_options
        t.columnconfigure(0, weight=1)

        out = ttk.LabelFrame(t, text="Output", padding=10)
        out.grid(row=0, column=0, sticky="ew")
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Folder:").grid(row=0, column=0, sticky="e", pady=3)
        ttk.Entry(out, textvariable=self.var("out_dir")).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(out, text="Browse…", command=self.pick_folder).grid(row=0, column=2)

        ttk.Label(out, text="Format:").grid(row=1, column=0, sticky="e", pady=3)
        row = ttk.Frame(out)
        row.grid(row=1, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Combobox(row, textvariable=self.var("container"), values=["mp4", "mkv"], width=6,
                     state="readonly").pack(side="left")
        ttk.Label(row, text="    Download threads:").pack(side="left")
        ttk.Spinbox(row, textvariable=self.var("threads"), from_=1, to=32, width=4).pack(side="left", padx=4)

        ttk.Label(out, text="Strategy:").grid(row=2, column=0, sticky="e", pady=3)
        row = ttk.Frame(out)
        row.grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        cb = ttk.Combobox(row, textvariable=self.var("strategy"), values=list(STRATEGIES),
                          state="readonly", width=30)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self.update_preview)
        ttk.Label(row, text="    Auto uses the full VOD if the parts cover at least").pack(side="left")
        sp = ttk.Spinbox(row, textvariable=self.var("threshold"), from_=1, to=100, width=4,
                         command=self.update_preview)
        sp.pack(side="left", padx=4)
        sp.bind("<KeyRelease>", self.update_preview)
        ttk.Label(row, text="%").pack(side="left")

        ttk.Label(out, text="File name:").grid(row=3, column=0, sticky="e", pady=3)
        ttk.Entry(out, textvariable=self.var("name_template")).grid(row=3, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(out, text="Tokens: {streamer} {date} {id} {title} {n} {total} {start} {end}",
                  style="Muted.TLabel").grid(row=4, column=1, columnspan=2, sticky="w", padx=6)

        ttk.Checkbutton(out, text="Organize in subfolders:  Folder / Streamer / Stream / parts",
                        variable=self.var("subfolders")).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(out, text="Stream folder:").grid(row=6, column=0, sticky="e", pady=3)
        ttk.Entry(out, textvariable=self.var("folder_template")).grid(row=6, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(out, text="Tokens: {streamer} {date} {id} {title}",
                  style="Muted.TLabel").grid(row=7, column=1, columnspan=2, sticky="w", padx=6)

        ttk.Checkbutton(out, text="Frame-exact cuts (re-encodes: slow, CPU heavy. Default = lossless, "
                                  "cuts land on keyframes, ~2 s precision)",
                        variable=self.var("exact")).grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(out, text="Keep the full VOD file as well (when the full-VOD strategy is used)",
                        variable=self.var("keep_full")).grid(row=9, column=0, columnspan=3, sticky="w")

        chf = ttk.LabelFrame(t, text="Chapter details", padding=10)
        chf.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        chf.columnconfigure(1, weight=1)
        ttk.Label(chf, text="Chapter title:").grid(row=0, column=0, sticky="e", pady=3)
        e = ttk.Entry(chf, textvariable=self.var("title_tpl"))
        e.grid(row=0, column=1, sticky="ew", padx=6)
        e.bind("<KeyRelease>", lambda ev: self.refresh_clips())
        ttk.Label(chf, text="Tokens: {title} {creator} {views} {duration}", style="Muted.TLabel").grid(
            row=1, column=1, sticky="w", padx=6)
        ttk.Label(chf, text="Tail (s):").grid(row=2, column=0, sticky="e", pady=3)
        row = ttk.Frame(chf)
        row.grid(row=2, column=1, sticky="w", padx=6)
        sp = ttk.Spinbox(row, textvariable=self.var("pad_after"), from_=0, to=600, width=5, command=self.refresh_clips)
        sp.pack(side="left")
        sp.bind("<KeyRelease>", lambda ev: self.refresh_clips())
        ttk.Label(row, text="   seconds the chapter lasts after the clip ends", style="Muted.TLabel").pack(side="left")
        ttk.Label(chf, text="Gap chapter:").grid(row=3, column=0, sticky="e", pady=3)
        row = ttk.Frame(chf)
        row.grid(row=3, column=1, sticky="w", padx=6)
        ttk.Entry(row, textvariable=self.var("gap_title"), width=16).pack(side="left")
        ttk.Label(row, text="   name for the stretches between clips (MP4 needs one; leave empty only for MKV)",
                  style="Muted.TLabel").pack(side="left")
        ttk.Checkbutton(chf, text="Also save a .clips.json next to each part (clip titles, creators, links)",
                        variable=self.var("sidecar")).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        tools = ttk.LabelFrame(t, text="Tools (yt-dlp and ffmpeg)", padding=10)
        tools.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        tools.columnconfigure(0, weight=1)
        self.tools_info = tk.StringVar(value="Checking…")
        ttk.Label(tools, textvariable=self.tools_info, style="Muted.TLabel", justify="left").grid(
            row=0, column=0, sticky="w")
        ttk.Checkbutton(tools, text="Check for yt-dlp updates on startup (recommended: Twitch changes often)",
                        variable=self.var("auto_update")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        btns = ttk.Frame(tools)
        btns.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.update_btn = ttk.Button(btns, text="Update yt-dlp now", command=self.update_tools_now)
        self.update_btn.pack(side="left")
        ttk.Button(btns, text="Open tools folder", command=self.open_tools_folder).pack(side="left", padx=6)

    def build_queue_tab(self):
        t = self.tab_queue
        t.columnconfigure(0, weight=1)
        t.rowconfigure(0, weight=1)
        t.rowconfigure(2, weight=1)
        cols = ("n", "video", "parts", "mode", "status")
        self.qtree = ttk.Treeview(t, columns=cols, show="headings", selectmode="browse", height=6)
        for col, text, width, anchor in [
            ("n", "#", 40, "center"), ("video", "Video", 420, "w"), ("parts", "Parts", 70, "center"),
            ("mode", "Strategy", 140, "center"), ("status", "Status", 200, "w"),
        ]:
            self.qtree.heading(col, text=text)
            self.qtree.column(col, width=width, anchor=anchor, stretch=(col == "video"))
        self.qtree.grid(row=0, column=0, sticky="nsew")
        btns = ttk.Frame(t)
        btns.grid(row=1, column=0, sticky="ew", pady=6)
        self.start_btn = ttk.Button(btns, text="Start queue", command=self.start_queue)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Cancel current", command=self.cancel_current, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="Clear finished", command=self.clear_finished).pack(side="left", padx=6)
        lf = ttk.LabelFrame(t, text="Log", padding=4)
        lf.grid(row=2, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.log_text = tk.Text(lf, height=8, bg=BG2, fg=FG, relief="flat", state="disabled",
                                font=(MONO_FONT, 10), wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")

    # ---------------------------- tools (yt-dlp / ffmpeg) ---------------------------- #
    def start_tools_setup(self, force: bool = False):
        """Download missing tools / update yt-dlp in the background."""
        if self.tools_busy:
            return
        self.tools_busy = True
        self.info_btn.config(state="disabled")
        self.update_btn.config(state="disabled")
        self.set_status("Preparing tools (yt-dlp, ffmpeg)…")
        update = force or bool(self.vars["auto_update"].get())

        def work():
            ctx = Ctx(log=lambda m: self.q.put(("log", m)), progress=lambda f, t: self.q.put(("progress", f, t)))
            self.tools_ctx = ctx
            error = None
            try:
                ensure_tools(ctx, update_ytdlp=update, force=force)
            except Cancelled:
                error = "Cancelled."
            except Exception as e:  # noqa: BLE001
                error = str(e)
            self.q.put(("tools_info", describe_tools()))
            self.q.put(("tools_done", error))

        threading.Thread(target=work, daemon=True).start()

    def update_tools_now(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Running", "Wait for the running job to finish (or cancel it) first.")
            return
        self.start_tools_setup(force=True)

    def open_tools_folder(self):
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(TOOLS_DIR))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(TOOLS_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(TOOLS_DIR)])
        except OSError as e:
            messagebox.showinfo("Tools folder", f"{TOOLS_DIR}\n\n{e}")

    # ---------------------------- credentials ---------------------------- #
    def ask_credentials(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Twitch API")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dark_titlebar(dlg)
        dlg.grab_set()
        cfg = load_credentials() or {}
        id_var = tk.StringVar(value=cfg.get("client_id", ""))
        sec_var = tk.StringVar(value=cfg.get("client_secret", ""))
        body = ttk.Frame(dlg, padding=15)
        body.pack()
        ttk.Label(
            body,
            text="Optional: only needed to fetch clips (clips → chapters).\n"
                 "Client ID / Secret of your app at dev.twitch.tv.\n"
                 f"Saved in: {CONFIG_PATH}",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Client ID:").grid(row=1, column=0, sticky="e", pady=(12, 4))
        ttk.Entry(body, textvariable=id_var, width=48).grid(row=1, column=1, pady=(12, 4))
        ttk.Label(body, text="Client Secret:").grid(row=2, column=0, sticky="e", pady=4)
        ttk.Entry(body, textvariable=sec_var, width=48, show="*").grid(row=2, column=1, pady=4)

        def save():
            cid, sec = id_var.get().strip(), sec_var.get().strip()
            if not cid or not sec:
                messagebox.showwarning("Missing data", "Fill in both fields.", parent=dlg)
                return
            test = TwitchClient(cid, sec)
            try:
                test.refresh_token()
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dlg)
                return
            except requests.RequestException as e:
                messagebox.showerror("Network error", str(e), parent=dlg)
                return
            save_credentials(cid, sec)
            self.client = test
            self.set_status("Twitch API credentials saved.")
            dlg.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=3, column=0, columnspan=2, pady=(14, 0), sticky="e")
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Save", command=save).pack(side="right")

    # ---------------------------- plan tab logic ---------------------------- #
    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.vars["out_dir"].get() or str(APP_DIR))
        if d:
            self.vars["out_dir"].set(d)

    def set_preview(self, text: str, kind: str):
        """kind: ok | err | muted"""
        self.preview_kind = kind
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text, kind)
        self.preview.config(state="disabled")

    def update_preview(self, *_):
        text = self.cuts.get("1.0", "end").strip()
        if not text:
            self.set_preview("Write the cut points above (press «Get info» first so «end» works).", "muted")
            return
        dur = self.source.duration if self.source else None
        opts = self.build_options()
        try:
            plan = make_plan(text, dur, opts.strategy, opts.full_threshold)
        except EngineError as e:
            self.set_preview(f"⚠ {e}", "err")
            return
        lines = [f"Part {p.index}:  {fmt_hms(p.start)} → {fmt_hms(p.end)}   ({fmt_hms(p.duration)})" for p in plan.parts]
        if plan.duration:
            how = ("download the full VOD once, then split it" if plan.strategy == "full"
                   else "download only these parts")
            lines.append(f"→ {how}   (parts cover {plan.coverage * 100:.0f}% of the VOD)")
        self.set_preview("\n".join(lines), "ok")

    def on_get_info(self):
        text = self.vod_var.get().strip()
        if not text:
            return
        if self.tools_busy:
            self.set_status("Still preparing yt-dlp / ffmpeg, one moment…")
            return
        self.info_btn.config(state="disabled")
        self.set_status("Reading VOD info…")
        client = self.client

        def work():
            try:
                info = get_source_info(text)
                clips, warn, loaded = [], "", False
                if info.twitch_vod_id and client:
                    try:
                        clips = fetch_clips_for_vod(client, info.twitch_vod_id)
                        loaded = True
                    except Exception as e:  # noqa: BLE001
                        warn = f"Could not fetch clips: {e}"
                elif info.twitch_vod_id:
                    warn = "No Twitch API credentials set: clips are not available (optional)."
                self.q.put(("info_ok", info, clips, loaded, warn))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def on_info_ok(self, info, clips, loaded, warn):
        self.info_btn.config(state="normal")
        self.source, self.clips, self.clips_loaded = info, clips, loaded
        extra = f" · {len(clips)} clips" if loaded else ""
        self.info_var.set(bmp(f"{info.uploader} · {info.title} · {fmt_hms(info.duration)} · {info.date}{extra}"))
        if not self.cuts.get("1.0", "end").strip():
            self.cuts.insert("1.0", "0:00:00 - end")
        self.update_preview()
        self.refresh_clips()
        self.set_status("VOD loaded. Set your cut points and add it to the queue.")
        if warn:
            self.log(warn)

    def refresh_clips(self, *_):
        self.tree.delete(*self.tree.get_children())
        flt = self.build_filter()
        chapters = make_chapters(self.clips, flt)
        included = {c.get("id") for ch in chapters for c in ch.clips}
        for i, c in enumerate(self.clips):
            off = c.get("vod_offset")
            mark = "?" if off is None else ("✓" if c.get("id") in included else "—")
            self.tree.insert("", "end", iid=str(i), values=(
                fmt_hms(off), c.get("view_count", 0), f"{round(c.get('duration', 0))}s",
                bmp(c.get("title", "")), bmp(c.get("creator_name", "")), mark))
        if not self.clips:
            msg = "No clips loaded (needs Twitch API credentials, optional)." if not self.clips_loaded else "This VOD has no clips."
        else:
            placed = sum(1 for c in self.clips if c.get("vod_offset") is not None)
            msg = f"{len(included)} of {len(self.clips)} clips pass the filter → {len(chapters)} chapters"
            if placed < len(self.clips):
                msg += f"  ({len(self.clips) - placed} can't be placed: no offset)"
            if not self.vars["chapters"].get():
                msg += "  [chapters are OFF]"
        self.clips_lbl.set(msg)

    def open_clip(self, _event):
        sel = self.tree.selection()
        if sel:
            webbrowser.open(self.clips[int(sel[0])].get("url", ""))

    def split_at_clip(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a clip", "Select a clip in the table first.")
            return
        if not self.source:
            messagebox.showinfo("No VOD", "Press «Get info» first.")
            return
        off = self.clips[int(sel[0])].get("vod_offset")
        if off is None:
            messagebox.showinfo("No offset", "That clip has no position in the VOD.")
            return
        t = max(0, off - self.build_filter().pad_before)
        text = self.cuts.get("1.0", "end").strip() or "0:00:00 - end"
        try:
            new = insert_cut_point(text, t, self.source.duration)
        except EngineError as e:
            messagebox.showinfo("Can't split here", str(e))
            return
        self.cuts.delete("1.0", "end")
        self.cuts.insert("1.0", new)
        self.update_preview()

    # ---------------------------- queue ---------------------------- #
    def add_to_queue(self, start: bool):
        if not self.source:
            messagebox.showinfo("No VOD", "Paste a VOD and press «Get info» first.")
            return
        opts = self.build_options()
        try:
            plan = make_plan(opts.cut_text, self.source.duration, opts.strategy, opts.full_threshold)
        except EngineError as e:
            messagebox.showwarning("Cut points", str(e))
            return
        job = Job(self.source, opts, clips=self.clips if self.clips_loaded else None, client=self.client)
        label = bmp(f"{self.source.uploader} · {self.source.title}")[:70]
        strat = {"full": "full VOD + split", "sections": "only the parts"}[plan.strategy]
        iid = self.qtree.insert("", "end", values=(len(self.items) + 1, label, len(plan.parts), strat, "queued"))
        self.items.append({"job": job, "iid": iid, "status": "queued"})
        self.save_settings()
        self.log(f"Queued: {label} ({len(plan.parts)} parts, {strat})")
        if start:
            self.start_queue()
        else:
            self.set_status(f"Added to queue ({len(self.items)} item(s)).")

    def set_item_status(self, iid: str, status: str):
        for it in self.items:
            if it["iid"] == iid:
                it["status"] = status.split()[0].rstrip("…:")  # "done (3 files)" -> "done"
        if self.qtree.exists(iid):
            self.qtree.set(iid, "status", status)

    def start_queue(self):
        if self.worker and self.worker.is_alive():
            return
        if self.tools_busy:
            self.set_status("Still preparing yt-dlp / ffmpeg, start the queue again in a moment.")
            return
        todo = [it for it in self.items if it["status"] == "queued"]
        if not todo:
            self.set_status("Nothing queued.")
            return
        self.notebook.select(self.tab_queue)
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        def work():
            for n, it in enumerate(todo, 1):
                ctx = Ctx(log=lambda m: self.q.put(("log", m)), progress=lambda f, t: self.q.put(("progress", f, t)))
                self.ctx = ctx
                self.q.put(("job", n, len(todo)))
                self.q.put(("item", it["iid"], "running…"))
                try:
                    results = run_job(it["job"], ctx)
                    self.q.put(("item", it["iid"], f"done ({len(results)} files)"))
                except Cancelled:
                    self.q.put(("item", it["iid"], "cancelled"))
                    self.q.put(("log", "Cancelled."))
                    break
                except Exception as e:  # noqa: BLE001
                    self.q.put(("item", it["iid"], "failed"))
                    self.q.put(("log", f"ERROR: {e}"))
            self.q.put(("queue_done",))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def cancel_current(self):
        if self.ctx:
            self.ctx.cancel()
            self.set_status("Cancelling…")

    def remove_selected(self):
        sel = self.qtree.selection()
        if not sel:
            return
        it = next((i for i in self.items if i["iid"] == sel[0]), None)
        if it and it["status"] == "running":
            messagebox.showinfo("Running", "Cancel the running job first.")
            return
        self.items = [i for i in self.items if i["iid"] != sel[0]]
        self.qtree.delete(sel[0])

    def clear_finished(self):
        for it in list(self.items):
            if it["status"] in ("done", "failed", "cancelled"):
                self.items.remove(it)
                self.qtree.delete(it["iid"])

    # ---------------------------- events from threads ---------------------------- #
    def set_progress(self, frac: float, text: str):
        if frac < 0:
            if self._progress_mode != "indeterminate":
                self.progress.config(mode="indeterminate")
                self.progress.start(12)
                self._progress_mode = "indeterminate"
            self.set_status(f"{self._job_prefix}{text}")
        else:
            if self._progress_mode != "determinate":
                self.progress.stop()
                self.progress.config(mode="determinate")
                self._progress_mode = "determinate"
            self.progress["value"] = frac * 100
            self.set_status(f"{self._job_prefix}{text}  —  {frac * 100:.0f}%")

    def poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "info_ok":
                    self.on_info_ok(*msg[1:])
                elif kind == "error":
                    self.info_btn.config(state="normal")
                    self.set_status("Error.")
                    messagebox.showerror("Error", msg[1])
                elif kind == "log":
                    self.log(msg[1])
                elif kind == "progress":
                    self.set_progress(msg[1], msg[2])
                elif kind == "job":
                    self._job_prefix = f"Job {msg[1]}/{msg[2]}: " if msg[2] > 1 else ""
                elif kind == "item":
                    self.set_item_status(msg[1], msg[2])
                elif kind == "tools_info":
                    self.tools_info.set(msg[1])
                elif kind == "tools_done":
                    self.tools_busy = False
                    self.tools_ctx = None
                    self.info_btn.config(state="normal")
                    self.update_btn.config(state="normal")
                    self.set_progress(0, "")
                    if msg[1]:
                        self.log(f"Tools: {msg[1]}")
                        self.set_status("Some tools are missing. See the log.")
                        messagebox.showwarning("Tools", msg[1])
                    else:
                        self.set_status("Ready. Paste a VOD URL or ID and press «Get info».")
                elif kind == "queue_done":
                    self.start_btn.config(state="normal")
                    self.cancel_btn.config(state="disabled")
                    self.set_progress(0, "")
                    self.ctx = None
                    self._job_prefix = ""
                    self.set_status("Queue finished.")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def on_close(self):
        if self.tools_ctx:
            self.tools_ctx.cancel()
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Quit", "A job is running. Cancel it and quit?"):
                return
            if self.ctx:
                self.ctx.cancel()
        self.save_settings()
        self.root.destroy()


def main():
    try:  # sharp text on high-DPI Windows screens
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    apply_dark_theme(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
