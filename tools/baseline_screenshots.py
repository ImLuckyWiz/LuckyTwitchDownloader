"""Takes the baseline screenshots of the tkinter app (Phase 0 of the PySide6 migration). Not part of the app.

Usage (from the repository root, needs Pillow and a display):
    python tools/baseline_screenshots.py                 # writes into docs/migration/baseline/
    python tools/baseline_screenshots.py some\\folder     # or into another folder
    xvfb-run -a python tools/baseline_screenshots.py     # Linux without a display

It opens the real window at 1020x910 and at the minimum size 900x560 and saves one PNG per screen:
every tab, every Options section and the Twitch sign-in dialog. Your own settings, Twitch login and
tools folder are NOT touched (everything goes to a temporary folder, the network is not used).
The window must stay visible and on top while it runs: do not move or cover it.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

import luckytwitch_downloader as dl  # noqa: E402
import luckytwitch_engine as eng  # noqa: E402
from ui.options_tab import SECTIONS  # noqa: E402

SIZES = {"1020x910": "1020x910", "900x560": "900x560"}  # window size name -> geometry
SOURCE = dict(url="https://www.twitch.tv/videos/123", id="v123", title="Big Stream", uploader="Streamer",
              duration=7200.0, date="2026-10-01", twitch_vod_id="123")
CLIPS = [
    {"id": "a", "vod_offset": 630.4, "view_count": 500, "duration": 30, "title": "Epic fail", "creator_name": "viewer1",
     "url": "https://clips.twitch.tv/a"},
    {"id": "b", "vod_offset": 3612, "view_count": 10, "duration": 12, "title": "Small one", "creator_name": "viewer2",
     "url": "https://clips.twitch.tv/b"},
]


def settle(root, n=6):
    for _ in range(n):
        root.update_idletasks()
        root.update()


def grab(root, path: Path):
    settle(root)
    x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
    print("saved", path)


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="lt_baseline_"))
    # isolate from the real machine (same seams the GUI tests use)
    dl.SETTINGS_PATH, dl.RECENT_PATH, dl.CONFIG_PATH = tmp / "settings.json", tmp / "recent.json", tmp / "config.json"
    dl.LINKS_DIR, dl.BEAT_PATH = tmp / "links", tmp / "running.beat"
    dl.ensure_tools = lambda *a, **k: None
    dl.describe_tools = lambda: "tools: (not checked in the baseline run)"
    dl.make_client = lambda: None

    root = tk.Tk()
    dl.apply_dark_theme(root)
    app = dl.App(root)
    root.attributes("-topmost", True)
    root.deiconify()
    root.lift()
    root.update()

    for size_name, geo in SIZES.items():
        root.geometry(geo)
        settle(root, 10)
        tabs = {"search": app.tab_search, "plan": app.tab_plan, "options": app.tab_options, "queue": app.tab_queue}

        # tabs in their start state (no VOD, empty lists)
        for name, tab in tabs.items():
            app.notebook.select(tab)
            if name == "options":
                app.options_nav.select("output")
            grab(root, out / f"{size_name}_{name}_empty.png")

        # every Options section
        app.notebook.select(app.tab_options)
        for key, _label in SECTIONS:
            app.options_nav.select(key)
            grab(root, out / f"{size_name}_options_{key}.png")

        # Plan tab with a VOD, cut points and clips loaded
        app.source = eng.SourceInfo(**SOURCE)
        app.clips, app.clips_loaded = list(CLIPS), True
        app.refresh_clips()
        app.cuts.delete("1.0", "end")
        app.cuts.insert("1.0", "0:00:00 - 0:30:00 - 1:30:00 - end")
        app.update_preview()
        app.info_var.set("Big Stream by Streamer · 2:00:00 (sample data)")
        app.notebook.select(app.tab_plan)
        grab(root, out / f"{size_name}_plan_with_vod.png")

        # Queue & log with one line in the log
        app.log("Sample log line (baseline screenshot).")
        app.notebook.select(app.tab_queue)
        grab(root, out / f"{size_name}_queue_with_log.png")

        # Twitch sign-in dialog
        before = set(root.winfo_children())
        app.ask_credentials()
        settle(root, 10)
        dialogs = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w not in before]
        if dialogs:
            dlg = dialogs[0]
            dlg.attributes("-topmost", True)
            dlg.lift()
            grab(dlg, out / f"{size_name}_dialog_twitch_signin.png")
            dlg.destroy()
        else:
            print("could not find the sign-in dialog")
        settle(root)

        # reset for the next size
        app.source, app.clips, app.clips_loaded = None, [], False
        app.refresh_clips()
        app.cuts.delete("1.0", "end")
        app.update_preview()
        app.info_var.set("No VOD loaded.")

    for after_id in root.tk.call("after", "info"):
        root.after_cancel(after_id)
    root.destroy()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "migration" / "baseline")
