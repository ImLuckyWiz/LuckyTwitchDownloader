"""Generates high-resolution showcase screenshots and a release banner for LuckyTwitch v2.0.0
using the real TwitchRivals VOD (https://www.twitch.tv/videos/2908684008).

Usage:
    python tools/make_showcase_banner.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QApplication

from core import paths
from core.settings import load_settings
from luckytwitch_engine import (
    GameSegment,
    Range,
    SourceInfo,
    get_source_info,
    load_storyboard_frames,
)
from luckytwitch_qt import LuckyApplication
from qt_ui.main_window import MainWindow
from qt_ui.queue_model import QueueItem
from qt_ui.theme import apply_theme, set_app_icon


def setup_real_vod(win: MainWindow) -> SourceInfo:
    print("Fetching real Twitch VOD metadata for 2908684008…")
    vod_url = "https://www.twitch.tv/videos/2908684008"
    info = get_source_info(vod_url)
    print(f"Loaded VOD: {info.title} ({info.duration:.0f}s, uploader={info.uploader})")

    # Load into MainWindow
    win.on_info_ok(info, [], True, "")

    # Set realistic cut points for this 5-hour stream
    win.tab_plan.set_cut_text("0:45:00 - 2:30:00 ; 3:00:00 - 4:30:00")
    win.tab_plan.update_preview()

    # Fetch storyboard thumbnails
    if info.storyboard:
        print(f"Downloading storyboard frames ({info.storyboard.count} frames across {len(info.storyboard.urls)} sheets)…")
        frames = load_storyboard_frames(info.storyboard)
        valid = sum(1 for f in frames if f is not None)
        print(f"Extracted {valid}/{len(frames)} thumbnail frames. Applying to timeline…")
        win.tab_plan.on_frames(info, frames)

    return info


def setup_search_tab(win: MainWindow, info: SourceInfo) -> None:
    # Populate TwitchRivals in search results and recents
    tr_channel = {
        "id": "240512680",
        "login": "twitchrivals",
        "name": "TwitchRivals",
        "avatar": "https://static-cdn.jtvnw.net/jtv_user_pictures/8b965d0a-9d29-4560-a54a-a2387114b0df-profile_image-300x300.png",
        "live": True,
        "game": "Rust",
    }
    sample_channels = [
        tr_channel,
        {
            "id": "71092938",
            "login": "xqc",
            "name": "xQc",
            "avatar": "",
            "live": True,
            "game": "Just Chatting",
        },
        {
            "id": "31239503",
            "login": "tarik",
            "name": "tarik",
            "avatar": "",
            "live": False,
            "game": "VALORANT",
        },
    ]

    win.tab_search.search_edit.setText("TwitchRivals")
    win.tab_search.on_search_ok("TwitchRivals", sample_channels)
    win.tab_search.sv_channel = tr_channel
    win.tab_search.set_title("TwitchRivals: past broadcasts")

    # Populate real VODs list
    vods = [
        {
            "id": "2908684008",
            "title": info.title,
            "date": info.date or "2026-10-24",
            "duration": int(info.duration),
            "views": 482910,
            "thumb": "",
            "url": "https://www.twitch.tv/videos/2908684008",
        },
        {
            "id": "2907401912",
            "title": "Rust Base Invaders IV: Day 1 - Qualifier Stage",
            "date": "2026-10-23",
            "duration": 17400,
            "views": 321400,
            "thumb": "",
            "url": "https://www.twitch.tv/videos/2907401912",
        },
        {
            "id": "2901192841",
            "title": "Twitch Rivals: Apex Legends Showdown",
            "date": "2026-10-18",
            "duration": 14200,
            "views": 284100,
            "thumb": "",
            "url": "https://www.twitch.tv/videos/2901192841",
        },
    ]
    win.tab_search.on_videos_ok(win.tab_search.sv_gen, vods, None)
    win.tab_search.refresh_search_empty_states()


def setup_queue_tab(win: MainWindow, info: SourceInfo) -> None:
    model = win.tab_queue.model
    model.items.clear()

    item1 = QueueItem(
        job=None,
        iid="job-1",
        n=1,
        label=f"{info.title} (Part 1)",
        parts=1,
        strategy="Only the parts",
        status="running",
        shown_status="Downloading (68%) · 28.4 MiB/s · ETA 01:42",
        progress=0.68,
        progress_text="68% (2.1 / 3.1 GiB)",
    )

    item2 = QueueItem(
        job=None,
        iid="job-2",
        n=2,
        label=f"{info.title} (Part 2)",
        parts=1,
        strategy="Only the parts",
        status="queued",
        shown_status="Waiting in queue",
        progress=0.0,
        progress_text="",
    )

    item3 = QueueItem(
        job=None,
        iid="job-3",
        n=3,
        label="Rust Base Invaders IV: Day 1 Highlights",
        parts=1,
        strategy="Full VOD + split",
        status="done",
        shown_status="Finished · 1.4 GiB · 1080p60",
        progress=1.0,
        progress_text="100%",
        files=["C:/Videos/Twitch/Day1_Highlights.mp4"],
    )

    model.items.extend([item1, item2, item3])
    model.layoutChanged.emit()
    win.tab_queue.refresh_summary()

    win.tab_queue.clear_log()
    win.tab_queue.log("LuckyTwitch Downloader v2.0.0 started (Qt 6.12.0 · Nuitka Standalone)")
    win.tab_queue.log("Engine initialized. Multi-threaded hardware pipeline active.")
    win.tab_queue.log(f"Loaded VOD: {info.title} ({info.duration // 3600:.0f}h {(info.duration % 3600) // 60:.0f}m)")
    win.tab_queue.log(f"Streamer: {info.uploader} · Date: {info.date}")
    win.tab_queue.log("Queue started: processing job 1 of 2 (Only the parts)")
    win.tab_queue.log("Fetching stream: 1080p60 (source) @ 8200 kbps")
    win.tab_queue.log("Download stream active · 28.4 MiB/s · Segment 640/940")
    win.tab_queue.log("Previous job completed: Rust Base Invaders IV: Day 1 Highlights (1.4 GiB)")


def capture_window(win: MainWindow, out_path: Path) -> Image.Image:
    QApplication.processEvents()
    time.sleep(0.1)
    QApplication.processEvents()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = win.grab()
    pix.save(str(out_path), "PNG")
    print(f"Captured: {out_path.name}")
    return Image.open(str(out_path))


def build_release_banner(plan_img: Image.Image, queue_img: Image.Image, out_path: Path) -> None:
    W, H = 1920, 1080
    banner = Image.new("RGBA", (W, H), (15, 16, 18, 255))

    # Ambient purple glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([W // 2 - 550, -280, W // 2 + 550, 360], fill=(145, 71, 255, 42))
    glow = glow.filter(ImageFilter.GaussianBlur(130))
    banner = Image.alpha_composite(banner, glow)
    draw = ImageDraw.Draw(banner)

    # Fonts
    try:
        title_font = ImageFont.truetype("segoeui.ttf", 46)
        sub_font = ImageFont.truetype("segoeuib.ttf", 20)
        badge_font = ImageFont.truetype("segoeuib.ttf", 16)
    except OSError:
        title_font = sub_font = badge_font = ImageFont.load_default()

    # Header badge: "LUCKYTWITCH v2.0.0"
    badge_text = "LUCKYTWITCH v2.0.0"
    b_w = 210
    b_h = 32
    b_x = (W - b_w) // 2
    b_y = 35
    draw.rounded_rectangle(
        [b_x, b_y, b_x + b_w, b_y + b_h],
        radius=16,
        fill=(145, 71, 255, 60),
        outline=(145, 71, 255, 200),
        width=1,
    )
    draw.text((b_x + 18, b_y + 6), badge_text, font=badge_font, fill=(220, 195, 255, 255))

    # Main Title
    title_text = "The Complete Qt 6 Redesign & Performance Overhaul"
    draw.text((W // 2, 85), title_text, font=title_font, fill=(255, 255, 255, 255), anchor="mt")

    # Subtitle
    sub_text = "Native 60 FPS UI  •  Precision Timeline Cuts  •  Fast Multi-Segment Downloads  •  Integrated IDE Console"
    draw.text((W // 2, 142), sub_text, font=sub_font, fill=(160, 163, 175, 255), anchor="mt")

    target_h = 800
    p_w = int(plan_img.width * (target_h / plan_img.height))
    q_w = int(queue_img.width * (target_h / queue_img.height))

    plan_resized = plan_img.resize((p_w, target_h), Image.Resampling.LANCZOS)
    queue_resized = queue_img.resize((q_w, target_h), Image.Resampling.LANCZOS)

    total_w = p_w + q_w + 40
    start_x = (W - total_w) // 2
    win_y = 190

    def place_with_shadow(img: Image.Image, x: int, y: int):
        nonlocal banner
        shadow = Image.new("RGBA", (img.width + 40, img.height + 40), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rounded_rectangle([20, 20, img.width + 20, img.height + 20], radius=14, fill=(0, 0, 0, 160))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        banner.paste(shadow, (x - 20, y - 20), shadow)

        banner.paste(img, (x, y))
        b_draw = ImageDraw.Draw(banner)
        b_draw.rounded_rectangle([x, y, x + img.width, y + img.height], radius=6, outline=(60, 63, 75, 255), width=2)

    place_with_shadow(plan_resized, start_x, win_y)
    place_with_shadow(queue_resized, start_x + p_w + 40, win_y)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    banner.convert("RGB").save(str(out_path), "JPEG", quality=95)
    print(f"Generated release banner: {out_path}")


def main() -> int:
    out_dir = ROOT / "dist" / "release_assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="lt_real_showcase_"))
    paths.DATA_DIR = tmp
    paths.SETTINGS_PATH = tmp / "settings.json"
    paths.CONFIG_PATH = tmp / "config.json"
    paths.RECENT_PATH = tmp / "recent.json"
    paths.LINKS_DIR = tmp / "links"
    paths.BEAT_PATH = tmp / "running.beat"
    paths.UI_STATE_PATH = tmp / "luckytwitch_ui.json"

    app = QApplication.instance() or LuckyApplication(["--no-weblink"])
    apply_theme(app)
    set_app_icon(app)

    win = MainWindow(settings=load_settings(), client=None)
    win.resize(1060, 920)
    win.show()
    QApplication.processEvents()

    info = setup_real_vod(win)
    setup_queue_tab(win, info)
    setup_search_tab(win, info)

    # 1. Capture Plan Tab with real thumbnails
    win.tabs.setCurrentIndex(1)
    plan_path = out_dir / "LuckyTwitch-v2.0.0-Plan-Tab.png"
    plan_img = capture_window(win, plan_path)

    # 2. Capture Queue Tab
    win.tabs.setCurrentIndex(3)
    queue_path = out_dir / "LuckyTwitch-v2.0.0-Queue-Tab.png"
    queue_img = capture_window(win, queue_path)

    # 3. Capture Search Tab
    win.tabs.setCurrentIndex(0)
    search_path = out_dir / "LuckyTwitch-v2.0.0-Search-Tab.png"
    capture_window(win, search_path)

    win.close()
    QApplication.processEvents()

    # 4. Build Full HD Release Banner
    banner_path = out_dir / "LuckyTwitch-v2.0.0-Banner.jpg"
    build_release_banner(plan_img, queue_img, banner_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
