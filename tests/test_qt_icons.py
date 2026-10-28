"""qt_ui/icons.py: the code-drawn icon layer (Phase 9, A5). Offscreen, no files, no QtSvg."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from core.palette import ACCENT_TEXT, DISABLED, ERR, FG, MUTED, OK, WARN  # noqa: E402
from qt_ui import icons  # noqa: E402
from qt_ui.icons import available_icons, clear_cache, has_icon, icon, pixmap  # noqa: E402

# The catalog the design plan (A5) promises: removing or renaming one is a deliberate act.
CATALOG = {
    "search", "queue", "film", "gear",
    "play", "pause", "stop", "scissors", "fit", "undo", "redo", "plus", "minus",
    "folder", "folder-open", "copy", "trash", "download", "refresh", "external-link", "link",
    "check", "x", "alert", "info", "clock", "eye", "flag",
    "chevron-right", "chevron-down", "grid", "list-view", "filter", "sliders", "user",
    "window-minimize", "window-maximize", "window-restore",
}
SIZES = (12, 16, 20, 24, 32, 48)
DPRS = (1.0, 1.25, 1.5, 2.0, 3.0)


@pytest.fixture(scope="module", autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield


def _image(pm) -> QImage:
    return pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _alphas(pm) -> list[list[int]]:
    im = _image(pm)
    return [[QColor.fromRgba(im.pixel(x, y)).alpha() for x in range(im.width())] for y in range(im.height())]


def _ink_stats(pm) -> tuple[float, tuple[int, int, int, int]]:
    """(fraction of pixels with ink, bounding box of the ink)"""
    a = _alphas(pm)
    pts = [(x, y) for y, row in enumerate(a) for x, v in enumerate(row) if v > 0]
    assert pts, "blank icon"
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return len(pts) / (len(a) * len(a[0])), (min(xs), min(ys), max(xs), max(ys))


# ----------------------------------------------------------------------------- catalog
def test_catalog_is_complete_and_sorted():
    names = available_icons()
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert CATALOG <= set(names), f"missing: {sorted(CATALOG - set(names))}"


def test_available_icons_returns_a_copy():
    names = available_icons()
    names.clear()
    assert available_icons()


def test_has_icon():
    assert all(has_icon(n) for n in available_icons())
    assert has_icon("PLAY") and has_icon("folder_open") and has_icon("list") and has_icon("vod")
    assert not has_icon("nope") and not has_icon("") and not has_icon(None)  # type: ignore[arg-type]
    assert not has_icon("?")  # the placeholder key is not a public name


def test_aliases_resolve_to_the_same_cached_objects():
    assert pixmap("list", 16) is pixmap("queue", 16)
    assert pixmap("vod", 16) is pixmap("film", 16)
    assert pixmap("Folder_Open", 16) is pixmap("folder-open", 16)
    assert icon("close", 16) is icon("x", 16)
    assert "list" not in available_icons() and "vod" not in available_icons()


# ----------------------------------------------------------------------------- rendering
@pytest.mark.parametrize("name", sorted(CATALOG))
def test_every_icon_renders_at_every_size_and_dpr(name):
    for size in SIZES:
        for dpr in DPRS:
            pm = pixmap(name, size, FG, dpr)
            assert not pm.isNull()
            assert pm.width() == pm.height() == round(size * dpr)
            assert pm.devicePixelRatio() == dpr
            ink, _ = _ink_stats(pm)
            assert ink > 0


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_ink_has_sane_coverage_and_a_margin(name):
    ink, (x0, y0, x1, y1) = _ink_stats(pixmap(name, 48))
    assert 0.04 < ink < 0.5, f"{name}: ink {ink:.3f}"
    assert min(x0, y0) >= 2 and max(x1, y1) <= 45, f"{name} touches the edge: {(x0, y0, x1, y1)}"


def test_icons_are_visually_distinct():
    seen: dict[bytes, str] = {}
    for name in available_icons():
        data = bytes(_image(pixmap(name, 32)).constBits())
        assert data not in seen, f"{name} is identical to {seen.get(data)}"
        seen[data] = name


def test_tint_is_exact_for_str_and_qcolor():
    for tint in (FG, MUTED, ACCENT_TEXT, OK, ERR, WARN, DISABLED, "#123456"):
        want = QColor(tint)
        for arg in (tint, QColor(tint)):
            im = _image(pixmap("stop", 32, arg))  # a solid shape: the middle is fully opaque
            got = QColor.fromRgba(im.pixel(16, 16))
            assert got.alpha() == 255
            assert (got.red(), got.green(), got.blue()) == (want.red(), want.green(), want.blue())


def test_tint_respects_alpha_and_never_leaks_other_colors():
    pm = pixmap("stop", 32, QColor(255, 0, 0, 128))
    got = QColor.fromRgba(_image(pm).pixel(16, 16))
    assert abs(got.alpha() - 128) <= 1 and got.red() == 255 and got.green() == 0 and got.blue() == 0
    # every inked pixel of a coloured icon has that colour (anti-aliasing only changes alpha)
    im = _image(pixmap("gear", 48, "#6bd49a"))
    for y in range(48):
        for x in range(48):
            c = QColor.fromRgba(im.pixel(x, y))
            if c.alpha() > 200:  # premultiplied rounding allows +-3 on semi-transparent edge pixels
                assert max(abs(c.red() - 0x6B), abs(c.green() - 0xD4), abs(c.blue() - 0x9A)) <= 3


def test_hidpi_is_rendered_not_upscaled():
    # dpr 2 has 2x the pixels and the same shape (same ink fraction, same relative bounding box)
    lo, hi = pixmap("search", 16, FG, 1.0), pixmap("search", 16, FG, 2.0)
    assert hi.width() == 2 * lo.width()
    (ink_lo, box_lo), (ink_hi, box_hi) = _ink_stats(lo), _ink_stats(hi)
    assert ink_hi == pytest.approx(ink_lo, abs=0.06)
    assert all(abs(h / 2 - lo_v) <= 1.5 for h, lo_v in zip(box_hi, box_lo))
    # an upscaled 1x bitmap would have few alpha levels; a real render has many more
    levels = {v for row in _alphas(hi) for v in row}
    assert len(levels) > 8


def test_redo_is_the_mirror_of_undo():
    a = _alphas(pixmap("undo", 48))
    b = _alphas(pixmap("redo", 48))
    for ra, rb in zip(a, b):
        for x, v in enumerate(ra):
            assert abs(v - rb[47 - x]) <= 12


def test_stroke_gets_lighter_as_size_grows():
    # 16 px icons use a heavier grid-stroke than 48 px ones so small icons keep a visible line
    assert icons._stroke_width(16) > icons._stroke_width(24) > icons._stroke_width(48)


# ----------------------------------------------------------------------------- QIcon
@pytest.mark.parametrize("name", sorted(CATALOG))
def test_qicon_is_valid_and_renders(name):
    ic = icon(name, 16, FG)
    assert isinstance(ic, QIcon) and not ic.isNull()
    pm = ic.pixmap(QSize(16, 16))
    assert not pm.isNull() and _ink_stats(pm)[0] > 0


def test_qicon_honours_device_pixel_ratio():
    ic = icon("plus", 16)
    for dpr in (1.0, 1.5, 2.0, 3.0):
        pm = ic.pixmap(QSize(16, 16), dpr)
        assert pm.width() == round(16 * dpr) and pm.devicePixelRatio() == dpr
    # and any size Qt asks for, not only the nominal one
    assert ic.pixmap(QSize(48, 48)).width() == 48


def test_qicon_disabled_mode_uses_the_palette_grey():
    ic = icon("stop", 32, "#ff0000")
    normal = QColor.fromRgba(_image(ic.pixmap(QSize(32, 32))).pixel(16, 16))
    off = QColor.fromRgba(_image(ic.pixmap(QSize(32, 32), QIcon.Mode.Disabled)).pixel(16, 16))
    want = QColor(DISABLED)
    assert (normal.red(), normal.green(), normal.blue()) == (255, 0, 0)
    assert (off.red(), off.green(), off.blue()) == (want.red(), want.green(), want.blue())
    assert not ic.pixmap(QSize(32, 32), QIcon.Mode.Active).isNull()


def test_qicon_paint_draws_into_a_painter():
    img = QImage(40, 40, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    icon("check", 24, ERR).paint(p, 8, 8, 24, 24)
    p.end()
    assert any(QColor.fromRgba(img.pixel(x, y)).alpha() for x in range(40) for y in range(40))


def test_qicon_survives_copy_and_widget_use():
    ic = QIcon(icon("plus", 16))  # copy
    assert not ic.isNull() and not ic.pixmap(QSize(16, 16)).isNull()
    btn = QPushButton("Add to queue")
    btn.setIcon(icon("plus", 16))
    btn.setIconSize(QSize(16, 16))
    assert not btn.icon().isNull()
    assert btn.icon().actualSize(QSize(16, 16)) == QSize(16, 16)


# ----------------------------------------------------------------------------- cache
def test_pixmap_cache_returns_the_identical_object():
    a = pixmap("plus", 16, "#e6e6e6", 1.0)
    assert pixmap("plus", 16, "#e6e6e6", 1.0) is a
    assert pixmap("plus", 16, QColor("#e6e6e6"), 1.0) is a  # str and QColor normalise to one key
    assert pixmap("plus", 16, "#E6E6E6", 1.0) is a  # hex case does not matter
    assert pixmap("plus") is a  # defaults: 16 px, FG, dpr 1


def test_cache_keys_are_name_size_color_and_dpr():
    base = pixmap("plus", 16, "#e6e6e6", 1.0)
    assert pixmap("minus", 16, "#e6e6e6", 1.0) is not base
    assert pixmap("plus", 20, "#e6e6e6", 1.0) is not base
    assert pixmap("plus", 16, "#ff0000", 1.0) is not base
    assert pixmap("plus", 16, "#e6e6e6", 2.0) is not base
    assert pixmap("plus", 16, QColor(230, 230, 230, 100), 1.0) is not base  # alpha is part of the colour


def test_icon_cache_returns_the_identical_object():
    a = icon("gear", 16, FG)
    assert icon("gear", 16, FG) is a
    assert icon("gear", 16, QColor(FG)) is a
    assert icon("gear", 24, FG) is not a
    assert icon("gear", 16, ERR) is not a


def test_clear_cache_forces_a_new_render():
    a = pixmap("plus")
    clear_cache()
    b = pixmap("plus")
    assert a is not b and _alphas(a) == _alphas(b)


def test_pixmap_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(icons, "_PIXMAP_LIMIT", 8)
    for s in range(10, 40):
        pixmap("plus", s)
    assert len(icons._pixmap_cache) <= 8


def test_cache_does_not_re_render(monkeypatch):
    calls = []
    real = icons._render
    monkeypatch.setattr(icons, "_render", lambda *a: calls.append(a) or real(*a))
    for _ in range(5):
        pixmap("clock", 24, ACCENT_TEXT, 2.0)
    assert len(calls) == 1


# ----------------------------------------------------------------------------- unknown names and bad input
def test_unknown_icon_gives_a_placeholder_and_warns_once(caplog):
    with caplog.at_level(logging.WARNING, logger="qt_ui.icons"):
        a = pixmap("definitely-not-an-icon", 24)
        b = pixmap("definitely-not-an-icon", 24)
        ic = icon("definitely-not-an-icon", 24)
    assert not a.isNull() and _ink_stats(a)[0] > 0
    assert a is b and not ic.isNull()
    warnings = [r for r in caplog.records if "definitely-not-an-icon" in r.getMessage()]
    assert len(warnings) <= 1  # once per name per process (may already have been logged by an earlier test)
    assert not has_icon("definitely-not-an-icon")
    assert "definitely-not-an-icon" not in available_icons()
    # the placeholder is distinguishable from every real icon
    placeholder = bytes(_image(pixmap("nope-x", 32)).constBits())
    assert all(bytes(_image(pixmap(n, 32)).constBits()) != placeholder for n in available_icons())


def test_unknown_icon_is_tinted_too():
    got = QColor.fromRgba(_image(pixmap("nope-x", 48, "#00ff00")).pixel(24, 5))
    assert got.alpha() > 0 and (got.red(), got.blue()) == (0, 0)


@pytest.mark.parametrize("bad", [0, -1, 0.4, True, "16", None])
def test_bad_size_raises(bad):
    with pytest.raises(ValueError):
        pixmap("plus", bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        icon("plus", bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1.0, True, "2", None])
def test_bad_dpr_raises(bad):
    with pytest.raises(ValueError):
        pixmap("plus", 16, FG, bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "not-a-colour", "#12", "#gggggg"])
def test_bad_color_raises(bad):
    with pytest.raises(ValueError):
        pixmap("plus", 16, bad)
    with pytest.raises(ValueError):
        icon("plus", 16, bad)


def test_non_string_name_raises_type_error():
    with pytest.raises(TypeError):
        pixmap(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        icon(3)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- packaging constraint
def test_no_qtsvg_and_no_icon_files():
    src = Path(icons.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+PySide6\.QtSvg", src, re.M)
    assert not re.search(r"\b(QFile|QResource|QSvgRenderer|QPixmap\(\s*[\"'])", src), "icons must not load files"
    assert not [m for m in sys.modules if m.startswith("PySide6.QtSvg")], "QtSvg got imported"
