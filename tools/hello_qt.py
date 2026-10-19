"""Proves that PySide6 runs here. Not part of the app.

    python tools/hello_qt.py            # opens a small window (needs a display)
    QT_QPA_PLATFORM=offscreen python tools/hello_qt.py --check   # no display: builds the window, prints, exits
"""

import sys

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
import PySide6


def build_window() -> QWidget:
    win = QWidget()
    win.setWindowTitle("LuckyTwitch Qt: hello")
    label = QLabel(f"PySide6 {PySide6.__version__} · Qt {qVersion()} · Python {sys.version.split()[0]}")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    button = QPushButton("Click me")
    button.clicked.connect(lambda: label.setText("Signal and slot work."))
    layout = QVBoxLayout(win)
    layout.addWidget(label)
    layout.addWidget(button)
    win.button, win.label = button, label  # kept so --check can click it
    return win


def main(argv: list[str]) -> int:
    app = QApplication(argv)
    win = build_window()
    if "--check" in argv:
        win.show()
        win.button.click()
        print(f"platform={app.platformName()} label={win.label.text()!r}")
        return 0 if win.label.text() == "Signal and slot work." else 1
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
