"""
LuckyTwitch Downloader - download a Twitch VOD (via yt-dlp) and cut it into
several parts in one go, optionally adding the VOD's clips as chapters.

Requirements:
    pip install requests pillow

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
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

try:  # thumbnails in the Search tab; without Pillow everything else still works
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = ImageTk = None

from luckytwitch_engine import (
    APP_DIR,
    TOOLS_DIR,
    TWITCH_CLIENT_ID,
    Cancelled,
    ClipFilter,
    Ctx,
    EngineError,
    Job,
    JobOptions,
    TwitchClient,
    describe_tools,
    device_login_poll,
    device_login_start,
    clip_cut_text,
    ensure_tools,
    fetch_clips_for_vod,
    fetch_thumbnail,
    fetch_videos,
    fmt_hms,
    get_source_info,
    insert_cut_point,
    make_chapters,
    make_plan,
    run_job,
    search_channels,
    stream_dir,
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
RECENT_PATH = DATA_DIR / "luckytwitch_recent.json"
MAX_RECENT = 12

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

VIDEO_KINDS = {
    "Past broadcasts": "archive",
    "Highlights": "highlight",
    "Uploads": "upload",
}
THUMB_SIZE = (128, 72)

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
    "premiere_xml": False,
    "subfolders": True,
    "folder_template": "{date} - {title} - {id}",
    "clip_name_template": "{clip_title}",
    "clip_pad_before": "3",
    "clip_pad_after": "3",
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


def open_in_file_manager(path: Path, select: bool = False) -> None:
    """Open a folder in Explorer / Finder / the file manager. With select=True and a file, highlight that file."""
    path = Path(path)
    if sys.platform == "win32":
        if select and path.is_file():
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            os.startfile(str(path if path.is_dir() else path.parent))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if select and path.is_file() else ["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])


# --------------------------------------------------------------------------- #
# Config / settings
# --------------------------------------------------------------------------- #
def _read_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_credentials():
    """Own-app credentials (client id + secret), or None."""
    data = _read_config()
    if data.get("client_id") and data.get("client_secret"):
        return data
    return None


def save_credentials(client_id, client_secret):
    data = _read_config()
    data.update({"client_id": client_id, "client_secret": client_secret})
    _write_config(data)


def clear_credentials():
    data = _read_config()
    data.pop("client_id", None)
    data.pop("client_secret", None)
    _write_config(data)


def save_login_tokens(access, refresh):
    """Store (or, with None, remove) the tokens of 'Sign in with Twitch'."""
    data = _read_config()
    if refresh:
        data.update({"access_token": access, "refresh_token": refresh})
    else:
        data.pop("access_token", None)
        data.pop("refresh_token", None)
    _write_config(data)


def make_client() -> "TwitchClient | None":
    """Build the Twitch client from what is saved: own app first, otherwise the signed-in user."""
    creds = load_credentials()
    if creds:
        return TwitchClient(creds["client_id"], creds["client_secret"])
    data = _read_config()
    if data.get("refresh_token"):
        return TwitchClient(
            TWITCH_CLIENT_ID,
            access_token=data.get("access_token"),
            refresh_token=data["refresh_token"],
            on_tokens=save_login_tokens,
        )
    return None


def load_settings():
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def load_recent() -> list[dict]:
    """Streamers picked in the Search tab, most recent first: [{id, login, name}]."""
    try:
        data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        if isinstance(c, dict) and c.get("id"):
            login = str(c.get("login") or "")
            out.append({"id": str(c["id"]), "login": login, "name": str(c.get("name") or login)})
    return out[:MAX_RECENT]


def save_recent(items: list[dict]) -> None:
    try:
        RECENT_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


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
    style.configure("Vods.Treeview", rowheight=THUMB_SIZE[1] + 8)  # tall rows: room for the thumbnails
    style.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG2, arrowcolor=FG, bordercolor=BG2)
    style.map("Vertical.TScrollbar", background=[("active", "#4a4d55")])
    style.configure("Horizontal.TProgressbar", troughcolor=BG2, background=ACCENT, bordercolor=BG2,
                    lightcolor=ACCENT, darkcolor=ACCENT)
    dark_titlebar(root)


# --------------------------------------------------------------------------- #
# Scrollable tab page
# --------------------------------------------------------------------------- #
class ScrollFrame(ttk.Frame):
    """
    A tab page that scrolls vertically when the window is too short for its content.
    Put the widgets in `.body`. When the window is tall enough `.body` stretches to fill it (so rows
    with a grid weight still grow); otherwise a scrollbar appears and the mouse wheel scrolls.
    """

    def __init__(self, parent, padding: int = 8):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, borderwidth=0, yscrollincrement=20)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=padding)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._fit)
        self.canvas.bind("<Configure>", self._fit)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):  # Windows/macOS, Linux up/down
            self.canvas.bind_all(seq, self._on_wheel, add="+")

    def _fit(self, _event=None):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1:
            return  # not laid out yet
        height = max(ch, self.body.winfo_reqheight())
        self.canvas.itemconfigure(self._win, width=cw, height=height)
        self.canvas.configure(scrollregion=(0, 0, cw, height))

    def _on_wheel(self, event):
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):  # Tk quirk with combobox pop-downs
            return
        p = w
        while p is not None and p is not self:
            p = p.master
        if p is None:
            return  # the pointer is not over this page
        if isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox, ttk.Combobox, ttk.Spinbox)):
            return  # these handle the wheel themselves
        if self.body.winfo_reqheight() <= self.canvas.winfo_height():
            return  # everything fits: nothing to scroll
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = int(event.delta)
            if sys.platform == "darwin":
                units = -delta
            else:
                units = -3 * (delta // 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(units, "units")


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
        # Search tab state
        self.recent = load_recent()
        self.sv_gen = 0  # bumped on every new channel / type: results of older requests are ignored
        self.sv_channel: dict | None = None
        self.sv_results: list[dict] = []
        self.sv_videos: list[dict] = []
        self.sv_cursor: str | None = None
        self.sv_images: dict[str, object] = {}  # keeps the thumbnails alive (Tk drops unreferenced images)
        self.thumb_q: queue.Queue = queue.Queue()

        root.title("LuckyTwitch Downloader")
        root.geometry("1020x910")
        root.minsize(900, 560)
        self.build_ui()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll_queue)

        if Image is not None:
            for _ in range(4):
                threading.Thread(target=self._thumb_worker, daemon=True).start()
        else:
            self.log("Pillow is not installed: thumbnails are disabled in the Search tab (pip install pillow).")

        self.client = make_client()
        self.update_search_state()
        if not self.client:  # nothing to search with yet: start on the Plan tab
            self.notebook.select(self.tab_plan)
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
            premiere_xml=bool(v["premiere_xml"].get()),
            subfolders=bool(v["subfolders"].get()),
            folder_template=v["folder_template"].get().strip() or DEFAULTS["folder_template"],
            clip_name_template=v["clip_name_template"].get().strip() or DEFAULTS["clip_name_template"],
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
        # every tab is a ScrollFrame: its content goes in `.body` and scrolls if the window is short
        self.tab_search = ScrollFrame(nb)
        self.tab_plan = ScrollFrame(nb)
        self.tab_options = ScrollFrame(nb)
        self.tab_queue = ScrollFrame(nb)
        nb.add(self.tab_search, text="  Search  ")
        nb.add(self.tab_plan, text="  Plan  ")
        nb.add(self.tab_options, text="  Options  ")
        nb.add(self.tab_queue, text="  Queue & log  ")
        self.notebook = nb
        self.build_search_tab()
        self.build_plan_tab()
        self.build_options_tab()
        self.build_queue_tab()

    def build_search_tab(self):
        t = self.tab_search.body
        t.columnconfigure(1, weight=1)
        t.rowconfigure(2, weight=1)

        # --- search box --- #
        top = ttk.Frame(t)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="Streamer:").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        entry.bind("<Return>", lambda e: self.on_search())
        self.search_btn = ttk.Button(top, text="Search", command=self.on_search)
        self.search_btn.pack(side="left")

        # --- shown while not signed in --- #
        self.signin_bar = ttk.Frame(t)
        self.signin_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(self.signin_bar, text="⚠ Sign in with Twitch to search streamers and list their VODs.",
                  foreground=ERR).pack(side="left")
        ttk.Button(self.signin_bar, text="Sign in…", command=self.ask_credentials).pack(side="left", padx=8)

        # --- left: found channels + recent streamers --- #
        left = ttk.Frame(t)
        left.grid(row=2, column=0, sticky="ns", padx=(0, 10), pady=(8, 0))

        def mini_tree(title: str, height: int) -> ttk.Treeview:
            tr = ttk.Treeview(left, columns=("name",), show="headings", selectmode="browse", height=height)
            tr.heading("name", text=title)
            tr.column("name", width=220, anchor="w")
            tr.bind("<<TreeviewSelect>>", self.on_pick_channel)
            return tr

        self.ch_tree = mini_tree("Results  (● = live now)", 6)
        self.ch_tree.pack(fill="x")
        ttk.Label(left, text="").pack()
        self.recent_tree = mini_tree("Recent streamers", 8)
        self.recent_tree.pack(fill="both", expand=True)
        ttk.Button(left, text="Clear recent", command=self.clear_recent).pack(anchor="e", pady=(4, 0))
        self.refresh_recent()

        # --- right: the VODs --- #
        right = ttk.Frame(t)
        right.grid(row=2, column=1, sticky="nsew", pady=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        hdr = ttk.Frame(right)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.sv_title = tk.StringVar(value="Search for a streamer, or pick one from your recent list.")
        ttk.Label(hdr, textvariable=self.sv_title, style="Muted.TLabel").pack(side="left")
        self.sv_type = tk.StringVar(value="Past broadcasts")
        kind = ttk.Combobox(hdr, textvariable=self.sv_type, values=list(VIDEO_KINDS), state="readonly", width=16)
        kind.pack(side="right")
        kind.bind("<<ComboboxSelected>>",
                  lambda e: self.sv_channel and self.load_channel(self.sv_channel, remember=False))

        self.sv_tree = ttk.Treeview(right, columns=("title", "date", "dur", "views"), show="tree headings",
                                    style="Vods.Treeview", selectmode="browse", height=5)
        self.sv_tree.heading("#0", text="")
        self.sv_tree.column("#0", width=THUMB_SIZE[0] + 12, stretch=False, anchor="center")
        for col, text, width, anchor in [
            ("title", "Title", 360, "w"), ("date", "Date", 90, "center"),
            ("dur", "Length", 80, "center"), ("views", "Views", 70, "center"),
        ]:
            self.sv_tree.heading(col, text=text)
            self.sv_tree.column(col, width=width, anchor=anchor, stretch=(col == "title"))
        sb = ttk.Scrollbar(right, orient="vertical", command=self.sv_tree.yview)
        self.sv_tree.configure(yscrollcommand=sb.set)
        self.sv_tree.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        self.sv_tree.bind("<Double-1>", lambda e: self.sv_tree.identify_row(e.y) and self.use_selected_vod())
        self.sv_tree.bind("<Return>", lambda e: self.use_selected_vod())
        brow = ttk.Frame(right)
        brow.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.more_btn = ttk.Button(brow, text="Load more", command=self.load_more, state="disabled")
        self.more_btn.pack(side="left")
        ttk.Button(brow, text="Use this VOD", command=self.use_selected_vod).pack(side="right")

    def build_plan_tab(self):
        t = self.tab_plan.body
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
        self.tree = ttk.Treeview(chf, columns=cols, show="headings", selectmode="extended", height=6)
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
        ttk.Button(brow, text="Download only selected clip", command=self.download_clips).pack(side="left", padx=(6, 0))
        ttk.Label(brow, textvariable=self.clips_lbl, style="Muted.TLabel").pack(side="left", padx=10)

        # --- add buttons --- #
        act = ttk.Frame(t)
        act.grid(row=2, column=0, sticky="e", pady=(8, 0))
        ttk.Button(act, text="Add to queue", command=lambda: self.add_to_queue(False)).pack(side="left")
        ttk.Button(act, text="Add & start", command=lambda: self.add_to_queue(True)).pack(side="left", padx=(6, 0))

    def build_options_tab(self):
        t = self.tab_options.body
        t.columnconfigure(0, weight=1)

        out = ttk.LabelFrame(t, text="Output", padding=10)
        out.grid(row=0, column=0, sticky="ew")
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Folder:").grid(row=0, column=0, sticky="e", pady=3)
        ttk.Entry(out, textvariable=self.var("out_dir")).grid(row=0, column=1, sticky="ew", padx=6)
        fbtns = ttk.Frame(out)
        fbtns.grid(row=0, column=2)
        ttk.Button(fbtns, text="Browse…", command=self.pick_folder).pack(side="left")
        ttk.Button(fbtns, text="Open folder", command=lambda: self.open_output_folder()).pack(side="left", padx=(6, 0))

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
        ttk.Checkbutton(chf, text="Also export the clips as markers for Premiere Pro (.markers.xml next to each part, "
                                  "works even if chapters are off)",
                        variable=self.var("premiere_xml"), command=self.refresh_clips).grid(
            row=5, column=0, columnspan=2, sticky="w")

        clf = ttk.LabelFrame(t, text="Single clip downloads (button «Download only selected clip»)", padding=10)
        clf.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        clf.columnconfigure(1, weight=1)
        ttk.Label(clf, text="File name:").grid(row=0, column=0, sticky="e", pady=3)
        ttk.Entry(clf, textvariable=self.var("clip_name_template")).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(clf, text="Tokens: {clip_title} {creator} {views} {clip_id} {clip_duration}   and also   "
                            "{streamer} {date} {id} {title} {start} {end}   ({id} and {title} are the VOD's)",
                  style="Muted.TLabel", wraplength=900, justify="left").grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(clf, text="Extra time:").grid(row=2, column=0, sticky="e", pady=3)
        row = ttk.Frame(clf)
        row.grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(row, text="before").pack(side="left")
        ttk.Spinbox(row, textvariable=self.var("clip_pad_before"), from_=0, to=600, width=5).pack(side="left", padx=4)
        ttk.Label(row, text="s      after").pack(side="left")
        ttk.Spinbox(row, textvariable=self.var("clip_pad_after"), from_=0, to=600, width=5).pack(side="left", padx=4)
        ttk.Label(row, text="s      seconds added around the clip", style="Muted.TLabel").pack(side="left")

        tools = ttk.LabelFrame(t, text="Tools (yt-dlp and ffmpeg)", padding=10)
        tools.grid(row=3, column=0, sticky="ew", pady=(10, 0))
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
        t = self.tab_queue.body
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
        ttk.Button(btns, text="Open folder", command=self.open_queue_folder).pack(side="right")
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
        body = ttk.Frame(dlg, padding=15)
        body.pack()

        ttk.Label(
            body,
            text="Optional: only needed to fetch clips (clips → chapters).\n"
                 "Sign in with your Twitch account: no developer app needed.",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        status_var = tk.StringVar()
        code_var = tk.StringVar()
        ttk.Label(body, textvariable=status_var, justify="left", wraplength=470).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 2))
        code_lbl = ttk.Label(body, textvariable=code_var, font=(MONO_FONT, 18, "bold"), foreground=ACCENT)
        code_lbl.grid(row=2, column=0, columnspan=2, pady=(2, 2))

        login_q: queue.Queue = queue.Queue()
        cancel_ev = threading.Event()
        state = {"busy": False, "url": ""}

        def signed_in() -> bool:
            return bool(_read_config().get("refresh_token")) and not load_credentials()

        def refresh_status():
            if load_credentials():
                status_var.set("Using your own Twitch app (Client ID / Secret below).")
            elif signed_in():
                status_var.set("✔ Signed in with Twitch. Clips are available.")
            else:
                status_var.set("Not signed in.")
            login_btn.config(text="Sign in again" if signed_in() else "Sign in with Twitch")
            logout_btn.config(state="normal" if (signed_in() or load_credentials()) else "disabled")
            self.update_search_state()  # show / hide the "sign in" warning of the Search tab

        def finish_login(access, refresh):
            clear_credentials()  # the signed-in account replaces a previous own-app setup
            save_login_tokens(access, refresh)
            self.client = make_client()
            code_var.set("")
            state["busy"] = False
            login_btn.config(state="normal")
            self.set_status("Signed in with Twitch.")
            refresh_status()

        def fail_login(msg):
            code_var.set("")
            state["busy"] = False
            login_btn.config(state="normal")
            refresh_status()
            messagebox.showerror("Twitch sign-in", msg, parent=dlg)

        def pump():
            try:
                while True:
                    kind, *args = login_q.get_nowait()
                    if kind == "code":
                        user_code, url = args
                        state["url"] = url
                        code_var.set(user_code)
                        status_var.set("A browser tab opened. Enter this code on twitch.tv/activate\n"
                                       "and press Authorize. Waiting for you…")
                    elif kind == "ok":
                        finish_login(*args)
                    elif kind == "error":
                        fail_login(args[0])
                    elif kind == "cancelled":
                        code_var.set("")
                        state["busy"] = False
                        login_btn.config(state="normal")
                        refresh_status()
            except queue.Empty:
                pass
            if dlg.winfo_exists():
                dlg.after(250, pump)

        def start_login():
            if state["busy"]:
                return
            state["busy"] = True
            cancel_ev.clear()
            login_btn.config(state="disabled")
            status_var.set("Contacting Twitch…")

            def work():
                try:
                    start = device_login_start()
                    url = start.get("verification_uri") or "https://www.twitch.tv/activate"
                    login_q.put(("code", start.get("user_code", ""), url))
                    try:
                        webbrowser.open(url)
                    except Exception:  # noqa: BLE001
                        pass
                    access, refresh = device_login_poll(start, cancel=cancel_ev)
                    login_q.put(("ok", access, refresh))
                except Cancelled:
                    login_q.put(("cancelled",))
                except Exception as e:  # noqa: BLE001
                    login_q.put(("error", str(e)))

            threading.Thread(target=work, daemon=True).start()

        def do_logout():
            save_login_tokens(None, None)
            clear_credentials()
            self.client = None
            id_var.set("")
            sec_var.set("")
            self.set_status("Twitch account removed.")
            refresh_status()

        def close():
            cancel_ev.set()
            dlg.destroy()

        login_row = ttk.Frame(body)
        login_row.grid(row=3, column=0, columnspan=2, pady=(6, 0), sticky="w")
        login_btn = ttk.Button(login_row, text="Sign in with Twitch", command=start_login)
        login_btn.pack(side="left")
        ttk.Button(login_row, text="Open page again",
                   command=lambda: state["url"] and webbrowser.open(state["url"])).pack(side="left", padx=(6, 0))
        logout_btn = ttk.Button(login_row, text="Sign out", command=do_logout)
        logout_btn.pack(side="left", padx=(6, 0))

        # --- advanced: own Twitch app --------------------------------------------------------
        adv = ttk.LabelFrame(body, text="Advanced: use your own Twitch app instead", padding=10)
        adv.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        cfg = load_credentials() or {}
        id_var = tk.StringVar(value=cfg.get("client_id", ""))
        sec_var = tk.StringVar(value=cfg.get("client_secret", ""))
        ttk.Label(adv, text="Client ID:").grid(row=0, column=0, sticky="e", pady=(0, 4))
        ttk.Entry(adv, textvariable=id_var, width=44).grid(row=0, column=1, pady=(0, 4))
        ttk.Label(adv, text="Client Secret:").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(adv, textvariable=sec_var, width=44, show="*").grid(row=1, column=1, pady=4)

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
            save_login_tokens(None, None)  # own app replaces a signed-in account
            save_credentials(cid, sec)
            self.client = test
            self.set_status("Twitch API credentials saved.")
            refresh_status()

        ttk.Button(adv, text="Save own app", command=save).grid(row=2, column=0, columnspan=2, sticky="e", pady=(6, 0))
        ttk.Label(body, text=f"Saved in: {CONFIG_PATH}", foreground=MUTED).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(body, text="Close", command=close).grid(row=6, column=0, columnspan=2, sticky="e", pady=(10, 0))
        dlg.protocol("WM_DELETE_WINDOW", close)
        refresh_status()
        pump()

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
                    warn = "Not signed in to Twitch: clips are not available (optional, see the Twitch API… button)."
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
            msg = "No clips loaded (sign in with the Twitch API… button, optional)." if not self.clips_loaded else "This VOD has no clips."
        else:
            placed = sum(1 for c in self.clips if c.get("vod_offset") is not None)
            msg = f"{len(included)} of {len(self.clips)} clips pass the filter → {len(chapters)} chapters"
            if placed < len(self.clips):
                msg += f"  ({len(self.clips) - placed} can't be placed: no offset)"
            if not (self.vars["chapters"].get() or self.vars["premiere_xml"].get()):
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
        if len(sel) > 1:
            messagebox.showinfo("Select one clip", "Splitting works with a single clip: select just one.")
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

    # ---------------------------- search tab logic ---------------------------- #
    def update_search_state(self):
        """Show the «sign in» warning (and disable searching) while there is no Twitch session."""
        if self.client:
            self.signin_bar.grid_remove()
        else:
            self.signin_bar.grid()
        self.search_btn.config(state="normal" if self.client else "disabled")

    def refresh_recent(self):
        self.recent_tree.delete(*self.recent_tree.get_children())
        for i, c in enumerate(self.recent):
            self.recent_tree.insert("", "end", iid=str(i), values=(bmp(c["name"]),))

    def add_recent(self, ch: dict):
        entry = {"id": ch["id"], "login": ch.get("login", ""), "name": ch.get("name") or ch.get("login", "")}
        self.recent = ([entry] + [c for c in self.recent if c["id"] != entry["id"]])[:MAX_RECENT]
        save_recent(self.recent)
        self.refresh_recent()

    def clear_recent(self):
        self.recent = []
        save_recent(self.recent)
        self.refresh_recent()

    def on_search(self):
        query = self.search_var.get().strip()
        if not query:
            return
        if not self.client:
            self.update_search_state()
            self.set_status("Sign in with Twitch to search (use the «Sign in…» button).")
            return
        self.search_btn.config(state="disabled")
        self.set_status(bmp(f"Searching for «{query}»…"))
        client = self.client

        def work():
            try:
                results = search_channels(client, query)
            except Exception as e:  # noqa: BLE001
                self.q.put(("search_err", str(e)))
                return
            self.q.put(("search_ok", query, results))

        threading.Thread(target=work, daemon=True).start()

    def on_search_ok(self, query: str, results: list[dict]):
        self.search_btn.config(state="normal" if self.client else "disabled")
        self.sv_results = results
        self.ch_tree.delete(*self.ch_tree.get_children())
        for i, c in enumerate(results):
            self.ch_tree.insert("", "end", iid=str(i), values=(bmp(("● " if c["live"] else "") + c["name"]),))
        if not results:
            self.set_status(bmp(f"No streamers found for «{query}»."))
            return
        self.set_status(f"{len(results)} streamer(s) found. Pick one to see their VODs.")
        if results[0]["login"].lower() == query.lstrip("@").lower():
            self.ch_tree.selection_set("0")  # exact match: open it straight away

    def on_search_err(self, msg: str):
        self.search_btn.config(state="normal" if self.client else "disabled")
        self.set_status("Search failed.")
        if "sign in" in msg.lower():  # the saved session expired: refresh what the tab shows
            self.client = make_client()
            self.update_search_state()
        messagebox.showerror("Search", msg)

    def on_pick_channel(self, event):
        tree = event.widget
        sel = tree.selection()
        if not sel:
            return
        from_results = tree is self.ch_tree
        ch = (self.sv_results if from_results else self.recent)[int(sel[0])]
        other = self.recent_tree if from_results else self.ch_tree
        if other.selection():
            other.selection_remove(other.selection())
        self.load_channel(ch)

    def load_channel(self, ch: dict, remember: bool = True, more: bool = False):
        """Load the first page of a streamer's VODs (or the next page when more=True)."""
        if not self.client:
            self.update_search_state()
            self.set_status("Sign in with Twitch to list VODs (use the «Sign in…» button).")
            return
        if more:
            gen = self.sv_gen
        else:
            self.sv_gen += 1
            gen = self.sv_gen
            self.sv_channel = ch
            self.sv_videos, self.sv_cursor = [], None
            self.sv_images.clear()
            self.sv_tree.delete(*self.sv_tree.get_children())
            if remember:
                self.add_recent(ch)
        kind = VIDEO_KINDS.get(self.sv_type.get(), "archive")
        after = self.sv_cursor if more else None
        self.more_btn.config(state="disabled")
        self.sv_title.set(bmp(f"{ch['name']}: loading…"))
        client = self.client

        def work():
            try:
                videos, cursor = fetch_videos(client, ch["id"], kind, after=after)
            except Exception as e:  # noqa: BLE001
                self.q.put(("videos_err", gen, str(e)))
                return
            self.q.put(("videos_ok", gen, videos, cursor))

        threading.Thread(target=work, daemon=True).start()

    def load_more(self):
        if self.sv_channel and self.sv_cursor:
            self.load_channel(self.sv_channel, more=True)

    def on_videos_ok(self, gen: int, videos: list[dict], cursor: str | None):
        if gen != self.sv_gen or not self.sv_channel:
            return  # the user already picked something else
        start = len(self.sv_videos)
        for i, v in enumerate(videos):
            iid = str(start + i)
            self.sv_tree.insert("", "end", iid=iid, values=(
                bmp(v["title"]), v["date"], fmt_hms(v["duration"]), v["views"]))
            if Image is not None and v["thumb"]:
                self.thumb_q.put((gen, iid, v["thumb"]))
        self.sv_videos.extend(videos)
        self.sv_cursor = cursor
        self.more_btn.config(state="normal" if cursor else "disabled")
        name = bmp(self.sv_channel["name"])
        if not self.sv_videos:
            self.sv_title.set(bmp(f"{name}: no {self.sv_type.get().lower()} found. Twitch deletes VODs after a "
                                  "while, and some streamers don't save them."))
        else:
            self.sv_title.set(f"{name}: {len(self.sv_videos)} VOD(s)" + ("  ·  more available" if cursor else "")
                              + "  ·  double-click one to use it")

    def on_videos_err(self, gen: int, msg: str):
        if gen != self.sv_gen:
            return
        self.sv_title.set("Could not load the VODs.")
        self.set_status("Could not load the VODs.")
        if "sign in" in msg.lower():
            self.client = make_client()
            self.update_search_state()
        messagebox.showerror("Search", msg)

    def _thumb_worker(self):
        """Background thread: download thumbnails (cached on disk) for the rows of the Search tab."""
        while True:
            gen, iid, url = self.thumb_q.get()
            if gen != self.sv_gen:
                continue  # stale: the list was replaced meanwhile
            try:
                path = fetch_thumbnail(url)
                if path:
                    self.q.put(("thumb", gen, iid, str(path)))
            except Exception:  # noqa: BLE001
                continue

    def on_thumb(self, gen: int, iid: str, path: str):
        if gen != self.sv_gen or not self.sv_tree.exists(iid):
            return
        try:
            with Image.open(path) as im:
                photo = ImageTk.PhotoImage(im.convert("RGB").resize(THUMB_SIZE))
        except Exception:  # noqa: BLE001  (unreadable image: just leave the row without one)
            return
        self.sv_images[iid] = photo
        self.sv_tree.item(iid, image=photo)

    def use_selected_vod(self):
        sel = self.sv_tree.selection()
        if not sel:
            messagebox.showinfo("Select a VOD", "Select a VOD in the list first.")
            return
        video = self.sv_videos[int(sel[0])]
        self.vod_var.set(video["url"])
        self.notebook.select(self.tab_plan)
        self.on_get_info()

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
        self.enqueue(job, label, len(plan.parts), strat)
        self.save_settings()
        if start:
            self.start_queue()
        else:
            self.set_status(f"Added to queue ({len(self.items)} item(s)).")

    def enqueue(self, job: Job, label: str, n_parts: int, strat: str):
        iid = self.qtree.insert("", "end", values=(len(self.items) + 1, label, n_parts, strat, "queued"))
        self.items.append({"job": job, "iid": iid, "status": "queued"})
        self.log(f"Queued: {label} ({n_parts} parts, {strat})")

    def download_clips(self):
        """Queue each selected clip as its own download (just that clip, named after the clip)."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a clip", "Select a clip in the table first.")
            return
        if not self.source:
            messagebox.showinfo("No VOD", "Press «Get info» first.")
            return
        base = self.build_options()
        before, after = self.num("clip_pad_before", float, 3), self.num("clip_pad_after", float, 3)
        added = 0
        for iid in sel:
            clip = self.clips[int(iid)]
            title = clip.get("title") or "Clip"
            try:
                cut = clip_cut_text(clip, self.source.duration, before, after)
                # a clip is always downloaded on its own: no full VOD, no chapters, no extra files
                opts = replace(base, cut_text=cut, strategy="sections", chapters=False,
                               keep_full=False, sidecar=False, premiere_xml=False)
                make_plan(opts.cut_text, self.source.duration, opts.strategy, opts.full_threshold)
            except EngineError as e:
                messagebox.showwarning("Clip", f"«{bmp(title)}»: {e}")
                continue
            job = Job(self.source, opts, single_clip=clip)
            label = bmp(f"{self.source.uploader} · Clip: {title}")[:70]
            self.enqueue(job, label, 1, "only the clip")
            added += 1
        if added:
            self.save_settings()
            self.set_status(f"Added {added} clip(s) to the queue ({len(self.items)} item(s)). "
                            "Open «Queue & log» and press «Start queue».")

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
                    it["files"] = list(results)
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

    def open_output_folder(self, path: Path | None = None, select: bool = False):
        """Open the output folder (created if missing), or `path` when given."""
        target = Path(path) if path else Path(self.vars["out_dir"].get().strip() or DEFAULTS["out_dir"])
        try:
            if not select:
                target.mkdir(parents=True, exist_ok=True)
            open_in_file_manager(target, select)
        except OSError as e:
            messagebox.showinfo("Open folder", f"Could not open:\n{target}\n\n{e}")

    def open_queue_folder(self):
        """Open where the selected queue item was saved (highlighting its first file); else the last
        finished item; else the output folder."""
        sel = self.qtree.selection()
        item = next((i for i in self.items if sel and i["iid"] == sel[0]), None)
        if item is None:
            item = next((i for i in reversed(self.items) if i.get("files")), None)
        if item:
            files = [Path(f) for f in item.get("files", []) if Path(f).exists()]
            if files:
                self.open_output_folder(files[0], select=True)
                return
            try:  # not finished yet: its stream folder if it exists
                folder = stream_dir(item["job"].source, item["job"].opts)
                if folder.is_dir():
                    self.open_output_folder(folder)
                    return
            except Exception:  # noqa: BLE001
                pass
            self.open_output_folder(Path(item["job"].opts.out_dir))
            return
        self.open_output_folder()

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
                elif kind == "search_ok":
                    self.on_search_ok(msg[1], msg[2])
                elif kind == "search_err":
                    self.on_search_err(msg[1])
                elif kind == "videos_ok":
                    self.on_videos_ok(msg[1], msg[2], msg[3])
                elif kind == "videos_err":
                    self.on_videos_err(msg[1], msg[2])
                elif kind == "thumb":
                    self.on_thumb(msg[1], msg[2], msg[3])
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
