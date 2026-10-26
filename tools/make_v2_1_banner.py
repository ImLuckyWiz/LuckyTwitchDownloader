"""Generates a showcase release banner for LuckyTwitch v2.1.0 highlighting the
First-Run Welcome & Quick Setup experience and the Fluid Motion System.

Usage:
    python tools/make_v2_1_banner.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from qt_ui.motion import Motion
from qt_ui.theme import apply_theme
from qt_ui.welcome.overlay import WelcomeOverlay


def capture_welcome_screen() -> Image.Image:
    Motion.set_enabled(False)
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)

    win = QWidget()
    win.resize(1020, 910)

    overlay = WelcomeOverlay(
        initial_out_dir="E:/Videos/Twitch",
        initial_container="mp4",
        is_signed_in=True,
        parent=win,
    )
    overlay.setGeometry(0, 0, 1020, 910)
    win.show()
    overlay.show()
    app.processEvents()

    pix = overlay.grab()
    tmp_path = ROOT / "dist" / "release_assets" / "raw_welcome.png"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(tmp_path))
    win.close()

    img = Image.open(str(tmp_path)).convert("RGBA")
    try:
        tmp_path.unlink()
    except OSError:
        pass
    return img


def draw_glass_card(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    tag: str,
    title: str,
    desc: str,
    accent_color: tuple[int, int, int],
    tag_font: ImageFont.ImageFont,
    title_font: ImageFont.ImageFont,
    desc_font: ImageFont.ImageFont,
) -> None:
    # Card surface
    r = 12
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=(24, 26, 32, 235), outline=(55, 58, 68, 255), width=1)

    # Accent highlight bar on left
    draw.rounded_rectangle([x + 16, y + 18, x + 20, y + h - 18], radius=2, fill=(*accent_color, 255))

    # Content
    cx = x + 34
    draw.text((cx, y + 16), tag.upper(), font=tag_font, fill=(*accent_color, 255))
    draw.text((cx, y + 36), title, font=title_font, fill=(255, 255, 255, 255))

    # Multi-line description wrap
    words = desc.split(" ")
    lines = []
    cur = []
    for word in words:
        test_line = " ".join(cur + [word])
        bbox = draw.textbbox((0, 0), test_line, font=desc_font)
        if bbox[2] - bbox[0] > (w - 56):
            lines.append(" ".join(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        lines.append(" ".join(cur))

    dy = y + 66
    for line in lines:
        draw.text((cx, dy), line, font=desc_font, fill=(160, 163, 175, 255))
        dy += 20


def build_v2_1_banner(welcome_img: Image.Image, out_path: Path) -> None:
    W, H = 1920, 1080
    banner = Image.new("RGBA", (W, H), (10, 11, 14, 255))

    # Dual Ambient Glows (Purple top center, Emerald bottom left, Cyan bottom right)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    # Twitch Purple glow top-center
    g_draw.ellipse([W // 2 - 600, -250, W // 2 + 600, 450], fill=(145, 71, 255, 55))
    # Emerald accent glow bottom-left
    g_draw.ellipse([-100, H - 400, 500, H + 200], fill=(16, 185, 129, 35))
    # Vibrant Violet glow bottom-right
    g_draw.ellipse([W - 500, H - 420, W + 150, H + 200], fill=(124, 58, 237, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    banner = Image.alpha_composite(banner, glow)

    draw = ImageDraw.Draw(banner)

    # Load Windows fonts
    try:
        badge_font = ImageFont.truetype("segoeuib.ttf", 15)
        title_font = ImageFont.truetype("segoeuib.ttf", 46)
        sub_font = ImageFont.truetype("segoeui.ttf", 20)
        card_tag_font = ImageFont.truetype("segoeuib.ttf", 12)
        card_title_font = ImageFont.truetype("segoeuib.ttf", 18)
        card_desc_font = ImageFont.truetype("segoeui.ttf", 14)
    except OSError:
        badge_font = title_font = sub_font = card_tag_font = card_title_font = card_desc_font = ImageFont.load_default()

    # 1. Header Badge: "LUCKYTWITCH v2.1.0"
    badge_text = "LUCKYTWITCH v2.1.0 RELEASE"
    b_w = 260
    b_h = 32
    b_x = (W - b_w) // 2
    b_y = 36
    draw.rounded_rectangle(
        [b_x, b_y, b_x + b_w, b_y + b_h],
        radius=16,
        fill=(145, 71, 255, 50),
        outline=(164, 107, 255, 220),
        width=1,
    )
    draw.text((W // 2, b_y + 7), badge_text, font=badge_font, fill=(230, 210, 255, 255), anchor="mt")

    # 2. Main Title
    title_text = "First-Run Experience & 60 FPS Motion Upgrade"
    draw.text((W // 2, 82), title_text, font=title_font, fill=(255, 255, 255, 255), anchor="mt")

    # 3. Subtitle
    sub_text = "Immersive Quick Setup  •  Full-Bleed Animated Canvas  •  Zero-Delay Motion Architecture"
    draw.text((W // 2, 142), sub_text, font=sub_font, fill=(163, 166, 173, 255), anchor="mt")

    # 4. Centerpiece: Window Frame with Welcome Screen Mockup
    target_h = 790
    target_w = int(welcome_img.width * (target_h / welcome_img.height))
    welcome_scaled = welcome_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    win_x = (W - target_w) // 2
    win_y = 195

    # Window dropshadow
    shadow = Image.new("RGBA", (target_w + 80, target_h + 80), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([40, 40, target_w + 40, target_h + 40], radius=18, fill=(0, 0, 0, 210))
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    banner.paste(shadow, (win_x - 40, win_y - 40), shadow)

    # Window frame with top titlebar
    titlebar_h = 30
    frame = Image.new("RGBA", (target_w, target_h + titlebar_h), (22, 23, 27, 255))
    f_draw = ImageDraw.Draw(frame)

    # Window titlebar controls (close, minimize, maximize dots)
    dot_y = 15
    f_draw.ellipse([14, dot_y - 5, 24, dot_y + 5], fill=(255, 95, 87, 255))
    f_draw.ellipse([32, dot_y - 5, 42, dot_y + 5], fill=(254, 188, 46, 255))
    f_draw.ellipse([50, dot_y - 5, 60, dot_y + 5], fill=(40, 200, 64, 255))

    # Window title
    try:
        wt_font = ImageFont.truetype("segoeui.ttf", 12)
    except OSError:
        wt_font = ImageFont.load_default()
    f_draw.text((target_w // 2, 9), "LuckyTwitch Downloader — Welcome & Quick Setup", font=wt_font, fill=(140, 143, 155, 255), anchor="mt")

    # Paste the captured welcome screen inside the frame
    frame.paste(welcome_scaled, (0, titlebar_h))

    # Outer border on frame
    f_draw.rounded_rectangle([0, 0, target_w - 1, target_h + titlebar_h - 1], radius=10, outline=(58, 60, 68, 255), width=2)

    # Paste frame onto banner
    banner.paste(frame, (win_x, win_y - titlebar_h), frame)

    # 5. Side Feature Highlight Cards
    card_w = 400
    card_h = 130

    # Left Side Cards
    left_x = win_x - card_w - 36
    draw_glass_card(
        draw,
        x=left_x,
        y=win_y + 80,
        w=card_w,
        h=card_h,
        tag="Onboarding",
        title="Zero-Friction Quick Setup",
        desc="Preconfigured downloads folder, instant container picker (MP4 / MKV), and optional Twitch sign-in.",
        accent_color=(145, 71, 255),
        tag_font=card_tag_font,
        title_font=card_title_font,
        desc_font=card_desc_font,
    )

    draw_glass_card(
        draw,
        x=left_x,
        y=win_y + 250,
        w=card_w,
        h=card_h,
        tag="Design System",
        title="Living Canvas Background",
        desc="Full-bleed radial gradient canvas blending Twitch purple into emerald with an ambient breathing loop.",
        accent_color=(16, 185, 129),
        tag_font=card_tag_font,
        title_font=card_title_font,
        desc_font=card_desc_font,
    )

    draw_glass_card(
        draw,
        x=left_x,
        y=win_y + 420,
        w=card_w,
        h=card_h,
        tag="Accessibility",
        title="Zero-Delay Fallback",
        desc="Honors Windows reduce-motion settings and provides immediate zero-timer execution in headless modes.",
        accent_color=(164, 107, 255),
        tag_font=card_tag_font,
        title_font=card_title_font,
        desc_font=card_desc_font,
    )

    # Right Side Cards
    right_x = win_x + target_w + 36
    draw_glass_card(
        draw,
        x=right_x,
        y=win_y + 80,
        w=card_w,
        h=card_h,
        tag="Motion Core",
        title="Fluid 60 FPS Animations",
        desc="Standardized motion tokens, OutCubic easing curves, tactile button depression, and spring switch squish.",
        accent_color=(145, 71, 255),
        tag_font=card_tag_font,
        title_font=card_title_font,
        desc_font=card_desc_font,
    )

    draw_glass_card(
        draw,
        x=right_x,
        y=win_y + 250,
        w=card_w,
        h=card_h,
        tag="Page Transitions",
        title="Seamless Stack Crossfades",
        desc="Animated stacked widget crossfades on rail tabs with dynamic VOD strip reveals and accordion dialogs.",
        accent_color=(56, 189, 248),
        tag_font=card_tag_font,
        title_font=card_title_font,
        desc_font=card_desc_font,
    )

    draw_glass_card(
        draw,
        x=right_x,
        y=win_y + 420,
        w=card_w,
        h=card_h,
        tag="Keyboard First",
        title="Quick Launch & Shortcuts",
        desc="Press Enter or Esc to start instantly; press F2 anytime from the main window to reopen settings.",
        accent_color=(245, 158, 11),
        tag_font=card_tag_font,
        title_font=card_title_font,
        desc_font=card_desc_font,
    )

    # Save PNG and high-quality JPG
    out_path.parent.mkdir(parents=True, exist_ok=True)
    banner.save(str(out_path), "PNG")
    jpg_path = out_path.with_suffix(".jpg")
    banner.convert("RGB").save(str(jpg_path), "JPEG", quality=96)
    print(f"Generated v2.1.0 release banner:\n  {out_path}\n  {jpg_path}")


def main() -> int:
    out_dir = ROOT / "dist" / "release_assets"
    print("Capturing Welcome Screen...")
    welcome_img = capture_welcome_screen()

    print("Building v2.1.0 Showcase Release Banner...")
    banner_png = out_dir / "LuckyTwitch-v2.1.0-Banner.png"
    build_v2_1_banner(welcome_img, banner_png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
