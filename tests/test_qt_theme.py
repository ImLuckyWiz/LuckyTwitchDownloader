"""Theme, fonts and icon of the Qt app (pytest-qt; QT_QPA_PLATFORM=offscreen is fine, no display needed)."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import core.palette as palette  # noqa: E402
from qt_ui import theme  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_qss_is_generated_from_the_tokens_and_has_no_leftovers():
    qss = theme.build_qss()
    assert "${" not in qss and "$" not in qss
    for colour in (palette.ACCENT, palette.ACCENT_HOVER, palette.ACCENT_PRESS, palette.BG2, palette.BG3,
                   palette.BORDER, palette.HOVER, palette.PRESSED, palette.DISABLED, palette.MUTED):
        assert colour in qss, colour
    for selector in ('QPushButton[variant="accent"]', 'QPushButton[variant="ghost"]', 'QLabel[role="muted"]',
                     "QTabBar::tab:selected", "QScrollBar", "QProgressBar::chunk", "QHeaderView::section", "QLineEdit"):
        assert selector in qss, selector


def _qt_messages_while_applying(qtbot, qss: str) -> list[str]:
    """Apply ``qss`` to the app with a widget on screen (Qt only parses a sheet when it styles a widget) and return
    the messages Qt printed meanwhile. A private message handler, because pytest-qt's qtlog does not see this one."""
    app = QApplication.instance()
    old, messages = app.styleSheet(), []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
    try:
        app.setStyleSheet(qss)
        button = QPushButton("probe")
        qtbot.addWidget(button)
        button.show()
        qtbot.wait(20)
        button.close()
    finally:
        qInstallMessageHandler(previous)
        app.setStyleSheet(old)
    return messages


def test_the_stylesheet_parses_without_qt_warnings(qtbot):
    assert _qt_messages_while_applying(qtbot, "QPushButton { background-color: ; color red;;; } QLabel {{{")  # the probe sees a bad sheet
    assert _qt_messages_while_applying(qtbot, theme.build_qss()) == []


def test_palette_tokens_equal_the_tkinter_ones():
    ui_common = pytest.importorskip("ui.common")  # plain module, no tkinter needed
    for name, value in palette.TOKENS.items():
        assert getattr(ui_common, name) == value, name
    assert (palette.UI_FONT, palette.MONO_FONT) == (ui_common.UI_FONT, ui_common.MONO_FONT)


def test_the_qt_palette_uses_the_dark_tokens():
    p = theme.build_palette()
    assert p.color(QPalette.ColorRole.Window) == QColor(palette.BG)
    assert p.color(QPalette.ColorRole.WindowText) == QColor(palette.FG)
    assert p.color(QPalette.ColorRole.Base) == QColor(palette.BG2)
    assert p.color(QPalette.ColorRole.Highlight) == QColor(palette.ACCENT)
    assert p.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText) == QColor(palette.DISABLED)


def test_apply_theme_sets_fusion_font_palette_and_stylesheet(qtbot):
    app = QApplication.instance()
    saved = (app.style().objectName(), app.palette(), app.font(), app.styleSheet())
    try:
        theme.apply_theme(app)
        assert app.palette().color(QPalette.ColorRole.Window) == QColor(palette.BG)
        assert app.font().pointSize() == theme.FONT_SIZE_PT
        assert app.font().family()  # a family that is not installed falls back to another one, never to nothing
        assert app.styleSheet() == theme.build_qss()
        app.setStyleSheet("")  # with a stylesheet active, style() is Qt's wrapper; without it we see the base style
        assert app.style().name().lower() == "fusion"
    finally:
        app.setStyle(saved[0])
        app.setPalette(saved[1])
        app.setFont(saved[2])
        app.setStyleSheet(saved[3])


def test_a_button_variant_gets_its_colour_from_the_stylesheet(qtbot):
    app = QApplication.instance()
    old = app.styleSheet()
    try:
        theme.apply_theme(app)
        plain, accent = QPushButton("Plain"), QPushButton("Accent")
        accent.setProperty("variant", "accent")
        for b in (plain, accent):
            qtbot.addWidget(b)
            b.show()
        qtbot.wait(20)
        img_plain, img_accent = plain.grab().toImage(), accent.grab().toImage()
        assert img_plain.pixelColor(3, 3) == QColor(palette.BG3)
        assert img_accent.pixelColor(3, 3) == QColor(palette.ACCENT)
    finally:
        app.setStyleSheet(old)


# ------------------------------------------------------------------ icon
def test_icon_files_are_where_the_qt_app_looks_for_them():
    from core.resources import resource_path

    for name in ("icon.png", "icon.ico", "icon.icns"):
        assert resource_path("assets", name).is_file(), name


def test_set_app_icon_installs_an_icon(qtbot):
    app = QApplication.instance()
    old = app.windowIcon()
    try:
        app.setWindowIcon(QIcon())
        assert theme.set_app_icon(app) is True
        assert not app.windowIcon().isNull()
        assert app.windowIcon().pixmap(32, 32).width() > 0
    finally:
        app.setWindowIcon(old)


def test_set_app_icon_is_silent_when_the_files_are_missing(qtbot, monkeypatch):
    monkeypatch.setattr(theme, "resource_path", lambda *parts: Path("/nonexistent").joinpath(*parts))
    assert theme.set_app_icon(QApplication.instance()) is False  # must not raise


def test_dark_titlebar_never_raises_and_does_nothing_off_windows(qtbot, monkeypatch):
    from PySide6.QtWidgets import QWidget

    w = QWidget()
    qtbot.addWidget(w)
    theme.dark_titlebar(w)  # whatever the platform: must not raise
    monkeypatch.setattr(theme.sys, "platform", "linux")
    theme.dark_titlebar(None)  # not even looking at the window off Windows


def test_build_scripts_use_the_icon():
    assert "assets\\icon.ico" in (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert "assets/icon.icns" in (ROOT / "build_mac.sh").read_text(encoding="utf-8")
    assert "SetupIconFile=assets\\icon.ico" in (ROOT / "installer.iss").read_text(encoding="utf-8")
