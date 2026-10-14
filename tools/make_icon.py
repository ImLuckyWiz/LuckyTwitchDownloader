"""Draws the LuckyTwitch app icon and writes assets/icon.png, icon.ico and icon.icns.

Run from the project root:  python tools/make_icon.py   (needs Pillow)
A purple rounded square, a white download arrow whose shaft is cut by a slanted gap (the "cut" in
cut-and-download), and a tray underneath.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 1024  # drawing size; everything is scaled down from here
TOP, BOTTOM = (168, 108, 255), (98, 44, 222)  # gradient, brand purple #9146ff sits in the middle
OUT = Path(__file__).resolve().parent.parent / "assets"


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def draw_icon() -> Image.Image:
    # rounded-square plate with a vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(TOP, BOTTOM, y / (S - 1)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=255)
    plate = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    plate.paste(grad, (0, 0), mask)

    # soft highlight along the top edge
    hl = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    hd = ImageDraw.Draw(hl)
    for y in range(S // 2):
        hd.line([(0, y), (S, y)], fill=(255, 255, 255, round(46 * (1 - y / (S / 2)) ** 1.6)))
    hl.putalpha(ImageChops.multiply(hl.getchannel("A"), mask))
    plate = Image.alpha_composite(plate, hl)

    # the glyph, as a single white layer
    glyph = Image.new("L", (S, S), 0)
    g = ImageDraw.Draw(glyph)
    cx = S // 2
    w = 150  # shaft width
    x0, x1 = cx - w // 2, cx + w // 2
    g.polygon([(x0, 200), (x1, 200), (x1, 352), (x0, 416)], fill=255)  # shaft, upper half
    g.polygon([(x0, 470), (x1, 406), (x1, 548), (x0, 548)], fill=255)  # shaft, lower half (after the cut)
    g.polygon([(284, 528), (S - 284, 528), (cx, 752)], fill=255)  # arrow head
    # tray: a U shape
    g.rounded_rectangle([240, 806, S - 240, 880], radius=37, fill=255)
    g.rounded_rectangle([240, 690, 314, 880], radius=37, fill=255)
    g.rounded_rectangle([S - 314, 690, S - 240, 880], radius=37, fill=255)
    glyph = ImageChops.offset(glyph, 0, -34)  # centre the whole glyph on the plate

    # drop shadow under the glyph
    shadow = Image.new("RGBA", (S, S), (40, 10, 110, 0))
    shadow.putalpha(glyph.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.45)))
    shadow = ImageChops.offset(shadow, 0, 18)
    shadow.putalpha(ImageChops.multiply(shadow.getchannel("A"), mask))
    plate = Image.alpha_composite(plate, shadow)

    white = Image.new("RGBA", (S, S), (255, 255, 255, 255))
    plate.paste(white, (0, 0), glyph)
    return plate


def main() -> None:
    OUT.mkdir(exist_ok=True)
    big = draw_icon()
    big.resize((512, 512), Image.LANCZOS).save(OUT / "icon.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big.save(OUT / "icon.ico", sizes=[(s, s) for s in sizes])
    big.save(OUT / "icon.icns")
    print("wrote", ", ".join(p.name for p in sorted(OUT.iterdir())))


if __name__ == "__main__":
    main()
