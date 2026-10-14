"""The refined theme, the small widgets (switch, tooltip, card/setting row) and the app icon.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
"""

import time

import pytest

tk = pytest.importorskip("tkinter")

from pathlib import Path  # noqa: E402
from tkinter import ttk  # noqa: E402

import luckytwitch_downloader as dl  # noqa: E402
from ui import common  # noqa: E402
from ui.widgets import Card, SettingRow, Toggle, Tooltip  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no usable display for Tk: {e}")
    r.withdraw()
    dl.apply_dark_theme(r)
    yield r
    r.destroy()


# ------------------------------------------------------------------ icon files
def test_icon_files_exist_and_have_the_sizes_windows_needs():
    from PIL import Image

    for name in ("icon.png", "icon.ico", "icon.icns"):
        assert (ROOT / "assets" / name).is_file(), name
    ico = Image.open(ROOT / "assets" / "icon.ico")
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])
    png = Image.open(ROOT / "assets" / "icon.png")
    assert png.size == (512, 512) and png.mode == "RGBA"


def test_resource_path_points_into_the_project():
    assert common.resource_path("assets", "icon.png").is_file()


def test_set_app_icon_installs_an_icon_and_never_raises(root):
    common.set_app_icon(root)
    assert getattr(root, "_lt_icon", None) is not None or root.tk.call("tk", "windowingsystem") == "win32"


def test_set_app_icon_is_silent_when_the_files_are_missing(root, monkeypatch):
    monkeypatch.setattr(common, "resource_path", lambda *parts: Path("/nonexistent").joinpath(*parts))
    common.set_app_icon(root)  # must not raise


def test_build_scripts_use_the_icon():
    assert "assets\\icon.ico" in (ROOT / "build_windows.bat").read_text()
    assert "assets/icon.icns" in (ROOT / "build_mac.sh").read_text()
    assert "SetupIconFile=assets\\icon.ico" in (ROOT / "installer.iss").read_text()


# ------------------------------------------------------------------ theme
def test_theme_defines_the_styles_the_ui_uses(root):
    style = ttk.Style(root)
    for name in ("Accent.TButton", "Ghost.TButton", "Muted.TLabel", "Card.TFrame", "Card.TLabel", "CardMuted.TLabel"):
        assert style.lookup(name, "background") != "" or style.lookup(name, "foreground") != "", name
    assert style.lookup("Accent.TButton", "background") == common.ACCENT
    assert int(style.lookup("Vods.Treeview", "rowheight")) == dl.THUMB_SIZE[1] + 8


def test_checkbutton_still_toggles_with_the_custom_indicator(root):
    var = tk.BooleanVar(value=False)
    cb = ttk.Checkbutton(root, text="x", variable=var)
    cb.pack()
    root.update()
    cb.invoke()
    assert var.get() is True
    cb.invoke()
    assert var.get() is False


# ------------------------------------------------------------------ Toggle
def test_toggle_follows_the_variable_and_the_user(root):
    var = tk.BooleanVar(value=False)
    calls = []
    t = Toggle(root, var, command=lambda: calls.append(var.get()))
    t.pack()
    root.update()
    t._click()
    assert var.get() is True and calls == [True]
    t._click()
    assert var.get() is False and calls == [True, False]
    var.set(True)  # changed from code: the switch follows (animated), command is not called
    deadline = time.time() + 2
    while t._pos != 1.0 and time.time() < deadline:
        root.update()
        time.sleep(0.01)
    assert t._pos == 1.0 and calls == [True, False]


def test_toggle_works_with_int_variables_too(root):
    var = tk.IntVar(value=0)
    t = Toggle(root, var)
    t.pack()
    t._click()
    assert var.get() == 1
    t._click()
    assert var.get() == 0


def test_disabled_toggle_ignores_clicks(root):
    var = tk.BooleanVar(value=False)
    calls = []
    t = Toggle(root, var, command=lambda: calls.append(1), state="disabled")
    t.pack()
    t._click()
    assert var.get() is False and calls == []
    t.configure_state("normal")
    t._click()
    assert var.get() is True and calls == [1]


def test_destroying_a_toggle_removes_its_trace(root):
    var = tk.BooleanVar(value=False)
    t = Toggle(root, var)
    t.pack()
    t.destroy()
    var.set(True)  # would raise (animating a dead widget) if the trace were still there
    root.update()


# ------------------------------------------------------------------ Tooltip / Card / SettingRow
def test_tooltip_shows_and_hides(root):
    lbl = ttk.Label(root, text="hover me")
    lbl.pack()
    root.update()
    tip = Tooltip(lbl, "explanation")
    tip._show()
    assert tip._tip is not None
    tip._hide()
    assert tip._tip is None


def test_card_collects_setting_rows(root):
    card = Card(root, "Output", "where files go")
    card.pack()
    r1 = card.add_row("Name", "hint", info="long text")
    r2 = card.add_row("Other", divider=False)
    assert isinstance(r1, SettingRow) and r2._divider is None and r1._divider is not None
    Toggle(r1.control, tk.BooleanVar()).pack()
    root.update()
    assert card.body.winfo_children()
