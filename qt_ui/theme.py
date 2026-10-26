"""The look of the Qt app: palette tokens -> QPalette + generated QSS on the Fusion style, fonts, icon, title bar.

``apply_theme(app)`` is the one entry point. ``build_qss()`` is a pure function (a string), so it can be
tested without a display. A widget picks one of the variants with a dynamic property (set it BEFORE the widget
is shown, or call ``unpolish``/``polish`` on it afterwards):

  QPushButton  ``variant="accent"``   filled purple button (the main action of a screen)
               ``variant="ghost"``    no background until hovered (small secondary actions)
  QLabel       ``role="muted"``       grey helper text
               ``role="title"`` / ``role="heading"``   bigger text for page and section titles

Phase 2 added the looks of the widget kit (``qt_ui/widgets.py``): object names ``card``, ``divider``, ``sideNav``,
``emptyState``, ``tooltipBubble``, ``scrollFrame``/``scrollBody``; buttons ``variant="nav"`` (selected: property
``selected="true"``), ``"cardghost"`` (the «Advanced» header) and ``"chip"``; label roles ``"rowtitle"`` and
``"emptytitle"``. Phase 4 added combo boxes, list items, group boxes, the sign-in banner (``#signinBar``) and the
sign-in code (``QLabel#loginCode``). Not styled yet: spin boxes and check boxes (they keep the Fusion look in the
dark palette until Phase 5). Keyboard focus on buttons is not drawn, same as the tkinter app
(``focusthickness=0``).
"""

from __future__ import annotations

import sys
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from core.palette import MONO_FONT, TOKENS, UI_FONT
from core.resources import resource_path

APP_ID = "LuckyTwitch.Downloader"  # Windows taskbar identity (same as the tkinter app, see HANDOFF.md warnings)
FONT_SIZE_PT = 10

_QSS = Template("""
QToolTip { background-color: ${BG3}; color: ${FG}; border: 1px solid ${BORDER}; padding: 4px 6px; }

/* ---- buttons ---- */
QPushButton { background-color: ${BG3}; color: ${FG}; border: none; padding: 7px 14px; }
QPushButton:hover { background-color: ${HOVER}; }
QPushButton:pressed { background-color: ${PRESSED}; }
QPushButton:disabled { background-color: ${BG2}; color: ${DISABLED}; }
QPushButton[variant="accent"] { background-color: ${ACCENT}; color: ${WHITE}; font-weight: bold; padding: 7px 16px; }
QPushButton[variant="accent"]:hover { background-color: ${ACCENT_HOVER}; }
QPushButton[variant="accent"]:pressed { background-color: ${ACCENT_PRESS}; }
QPushButton[variant="accent"]:disabled { background-color: ${BG3}; color: ${DISABLED}; }
QPushButton[variant="ghost"] { background-color: ${BG}; color: ${MUTED}; padding: 5px 10px; }
QPushButton[variant="ghost"]:hover { background-color: ${BG3}; color: ${FG}; }
QPushButton[variant="ghost"]:pressed { background-color: ${PRESSED}; color: ${FG}; }
QPushButton[variant="ghost"]:disabled { background-color: ${BG}; color: ${DISABLED}; }

/* ---- labels (transparent, so they sit on any surface) ---- */
QLabel { background: transparent; color: ${FG}; }
QLabel:disabled { color: ${DISABLED}; }
QLabel[role="muted"] { color: ${MUTED}; }
QLabel[role="title"] { font-size: 15pt; font-weight: bold; }
QLabel[role="heading"] { font-size: 11pt; font-weight: bold; }
QLabel[role="rowtitle"] { font-weight: bold; }
QLabel[role="emptytitle"] { color: ${FG}; font-weight: bold; }

/* ---- text fields: a hairline that turns purple on focus ---- */
QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: ${BG2}; color: ${FG}; border: 1px solid ${BORDER}; padding: 5px 6px;
    selection-background-color: ${ACCENT}; selection-color: ${WHITE};
}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover { border-color: ${HOVER}; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus { border-color: ${ACCENT}; }
QLineEdit:disabled { background-color: ${BG}; color: ${DISABLED}; }

/* ---- tabs (flat, the selected one purple) ---- */
QTabWidget::pane { border: 1px solid ${BORDER}; background-color: ${BG}; }
QTabWidget::tab-bar { alignment: left; }
QTabBar { background: transparent; }
QTabBar::tab {
    background-color: ${BG}; color: ${MUTED}; padding: 8px 20px; border: none; font-weight: bold; margin: 6px 6px 0 0;
}
QTabBar::tab:hover:!selected { background-color: ${BG3}; color: ${FG}; }
QTabBar::tab:selected { background-color: ${ACCENT}; color: ${WHITE}; }

/* ---- lists and tables ---- */
QTableView, QListView, QTreeView {
    background-color: ${BG2}; alternate-background-color: ${BG2}; color: ${FG}; border: none; outline: none;
    selection-background-color: ${ACCENT}; selection-color: ${WHITE};
}
QHeaderView::section {
    background-color: ${BG3}; color: ${FG}; border: none; padding: 7px 8px; font-weight: bold;
}
QHeaderView::section:hover { background-color: ${HOVER}; }

/* ---- list items, combo boxes, group boxes (Search tab, Twitch dialog) ---- */
QListView::item { padding: 0 6px; }
QComboBox {
    background-color: ${BG2}; color: ${FG}; border: 1px solid ${BORDER}; padding: 5px 6px; min-height: 18px;
    selection-background-color: ${BG2}; selection-color: ${FG};
}
QComboBox:hover { border-color: ${HOVER}; }
QComboBox:focus, QComboBox:on { border-color: ${ACCENT}; }
QComboBox:disabled { background-color: ${BG}; color: ${DISABLED}; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView {
    background-color: ${BG2}; color: ${FG}; border: 1px solid ${BORDER}; outline: none;
    selection-background-color: ${ACCENT}; selection-color: ${WHITE};
}
QSpinBox {
    background-color: ${BG2}; color: ${FG}; border: 1px solid ${BORDER}; padding: 5px 6px; min-height: 18px;
    selection-background-color: ${ACCENT}; selection-color: ${WHITE};
}
QSpinBox:hover { border-color: ${HOVER}; }
QSpinBox:focus { border-color: ${ACCENT}; }
QSpinBox:disabled { background-color: ${BG}; color: ${DISABLED}; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 18px; border: none; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; border: none; }
QSpinBox::up-arrow, QSpinBox::down-arrow { image: none; width: 0; height: 0; }
/* fields on a card are darker than the card (BG on BG2), like the tkinter «Card.TEntry»; a disabled one melts into it */
QFrame#card QLineEdit, QFrame#card QSpinBox, QFrame#card QComboBox { background-color: ${BG}; }
QFrame#card QLineEdit:disabled, QFrame#card QSpinBox:disabled, QFrame#card QComboBox:disabled { background-color: ${BG2}; }
QGroupBox { border: 1px solid ${BORDER}; margin-top: 8px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px; color: ${ACCENT}; font-weight: bold; }

/* ---- the sign-in banner of the Search tab and the code of the Twitch dialog ---- */
#signinBar { background-color: ${ACCENT_DIM}; }
#signinBar QLabel { color: ${WHITE}; background: transparent; }
QLabel#loginCode { color: ${ACCENT}; }

/* ---- slim scrollbars without arrows ---- */
QScrollBar:vertical { background: ${BG}; width: 11px; margin: 0; border: none; }
QScrollBar:horizontal { background: ${BG}; height: 11px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: ${BG3}; min-height: 24px; }
QScrollBar::handle:horizontal { background: ${BG3}; min-width: 24px; }
QScrollBar::handle:hover { background: ${HOVER}; }
QScrollBar::handle:pressed { background: ${PRESSED}; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ---- the log (Queue & log tab) ---- */
QPlainTextEdit#logView { background-color: ${BG}; border: none; padding: 6px 8px; }
QPlainTextEdit#logView:hover, QPlainTextEdit#logView:focus { border: none; }

/* ---- widget kit (Phase 2) ---- */
QFrame#card { background-color: ${BG2}; border: 1px solid ${BORDER}; }
QFrame#divider { background-color: ${BORDER}; border: none; }
QFrame#sideNav { background-color: ${BG2}; border: none; }
QWidget#emptyState { background-color: ${BG2}; }
QLabel#tooltipBubble { background-color: ${BG3}; color: ${FG}; border: 1px solid ${BORDER}; }
QScrollArea#scrollFrame { background-color: ${BG}; border: none; }
QWidget#scrollBody { background-color: ${BG}; }
QPushButton[variant="nav"] {
    background-color: ${BG2}; color: ${MUTED}; text-align: left; padding: 9px 14px; font-weight: normal;
}
QPushButton[variant="nav"]:hover { background-color: ${BG3}; color: ${FG}; }
QPushButton[variant="nav"]:pressed { background-color: ${PRESSED}; color: ${FG}; }
QPushButton[variant="nav"][selected="true"] { background-color: ${ACCENT_DIM}; color: ${WHITE}; font-weight: bold; }
QPushButton[variant="nav"][selected="true"]:hover { background-color: ${ACCENT_DIM}; color: ${WHITE}; }
QPushButton[variant="nav"][selected="true"]:pressed { background-color: ${PRESSED}; color: ${WHITE}; }
QPushButton[variant="cardghost"] {
    background-color: ${BG2}; color: ${MUTED}; text-align: left; padding: 5px 8px; font-weight: bold;
}
QPushButton[variant="cardghost"]:hover { background-color: ${BG3}; color: ${FG}; }
QPushButton[variant="cardghost"]:pressed { background-color: ${PRESSED}; color: ${FG}; }
QPushButton[variant="chip"] { background-color: ${BG3}; color: ${FG}; padding: 2px 8px; font-size: 9pt; }
QPushButton[variant="chip"]:hover { background-color: ${HOVER}; color: ${WHITE}; }
QPushButton[variant="chip"]:pressed { background-color: ${ACCENT_PRESS}; color: ${WHITE}; }
QPushButton[variant="chip"]:disabled { background-color: ${BG2}; color: ${DISABLED}; }

/* ---- progress bar ---- */
QProgressBar { background-color: ${BG2}; border: none; min-height: 18px; max-height: 18px; text-align: center; }
QProgressBar::chunk { background-color: ${ACCENT}; }
""")


def build_qss() -> str:
    """The stylesheet, generated from the palette tokens (``Template.substitute`` raises on an unknown token)."""
    return _QSS.substitute(TOKENS)


def build_palette() -> QPalette:
    """The dark palette, so widgets that the stylesheet does not cover (message boxes, file dialogs) match."""
    t = {k: QColor(v) for k, v in TOKENS.items()}
    p = QPalette()
    for role, colour in (
        (QPalette.ColorRole.Window, t["BG"]), (QPalette.ColorRole.WindowText, t["FG"]),
        (QPalette.ColorRole.Base, t["BG2"]), (QPalette.ColorRole.AlternateBase, t["BG2"]),
        (QPalette.ColorRole.Text, t["FG"]), (QPalette.ColorRole.Button, t["BG3"]),
        (QPalette.ColorRole.ButtonText, t["FG"]), (QPalette.ColorRole.BrightText, t["WHITE"]),
        (QPalette.ColorRole.ToolTipBase, t["BG3"]), (QPalette.ColorRole.ToolTipText, t["FG"]),
        (QPalette.ColorRole.PlaceholderText, t["MUTED"]), (QPalette.ColorRole.Highlight, t["ACCENT"]),
        (QPalette.ColorRole.HighlightedText, t["WHITE"]), (QPalette.ColorRole.Link, t["ACCENT_HOVER"]),
        (QPalette.ColorRole.Mid, t["BORDER"]), (QPalette.ColorRole.Dark, t["BG"]), (QPalette.ColorRole.Light, t["HOVER"]),
    ):
        p.setColor(role, colour)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, t["DISABLED"])
    return p


def ui_font() -> QFont:
    return QFont(UI_FONT, FONT_SIZE_PT)


def mono_font() -> QFont:
    f = QFont(MONO_FONT, FONT_SIZE_PT)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def apply_theme(app: QApplication) -> None:
    """Fusion style + dark palette + generated QSS + the UI font. Call once, right after creating the QApplication."""
    app.setStyle("Fusion")
    try:  # Qt 6.8+: tells the platform the app is dark (on Windows that also darkens the title bar)
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    except AttributeError:  # pragma: no cover  (older Qt)
        pass
    app.setPalette(build_palette())
    app.setFont(ui_font())
    app.setStyleSheet(build_qss())


def set_app_icon(app: QApplication) -> bool:
    """Window and taskbar icon from assets/. Silent (returns False) when the files are missing or unreadable."""
    if sys.platform == "win32":
        try:  # own taskbar identity, so Windows shows our icon instead of python.exe's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass
    names = ("icon.ico", "icon.png") if sys.platform == "win32" else ("icon.png",)
    for name in names:
        path = resource_path("assets", name)
        if not path.is_file():
            continue
        icon = QIcon(str(path))
        if not icon.isNull():
            app.setWindowIcon(icon)
            return True
    return False


def dark_titlebar(window: QWidget) -> None:
    """Windows only: ask DWM for a dark title bar. A fallback next to the Qt colour scheme (the call is harmless
    when Qt already did it). Never raises."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:  # noqa: BLE001
        pass
