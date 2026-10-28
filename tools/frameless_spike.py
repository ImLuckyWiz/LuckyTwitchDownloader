"""
Standalone test spike for the custom frameless window frame controller.
Run with: python tools/frameless_spike.py
Flags:
  --native-frame  : Use standard OS window frame
  --grips-only    : Frameless with Qt edge grips instead of Win32 hooks
"""

import sys
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_ui.frameless import FrameController
from qt_ui.titlebar import CustomTitleBar


class SpikeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Frameless Window Spike")
        self.setMinimumSize(900, 560)
        self.resize(1020, 700)

        use_custom = "--native-frame" not in sys.argv
        central = QWidget(self)

        if use_custom:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
            self.frame_controller = FrameController(self)
            outer = QVBoxLayout(central)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            self.title_bar = CustomTitleBar(self, "LuckyTwitch Downloader - Spike")
            outer.addWidget(self.title_bar)

            content = QWidget(central)
            c_lay = QVBoxLayout(content)
            c_lay.setContentsMargins(40, 40, 40, 40)
            lbl = QLabel(
                "<h2>Frameless Spike Window</h2>"
                "<p>Test resizing from all 8 borders and corners.</p>"
                "<p>Test dragging, double-click maximize, and Windows 11 Snap Layouts on the maximize button.</p>",
                content,
            )
            c_lay.addWidget(lbl)
            btn = QPushButton("Toggle Maximize", content)
            btn.clicked.connect(lambda: self.showNormal() if self.isMaximized() else self.showMaximized())
            c_lay.addWidget(btn)
            c_lay.addStretch()
            outer.addWidget(content)
        else:
            self.title_bar = None
            self.frame_controller = None
            outer = QVBoxLayout(central)
            outer.addWidget(QLabel("Running in native OS frame mode."))

        self.setCentralWidget(central)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if getattr(self, "frame_controller", None) is not None:
            self.frame_controller.on_show()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            is_max = self.isMaximized()
            if getattr(self, "title_bar", None) is not None:
                self.title_bar.update_maximized_state(is_max)
            if getattr(self, "frame_controller", None) is not None:
                self.frame_controller.on_state_change(is_max)
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "frame_controller", None) is not None:
            self.frame_controller.on_resize(self.width(), self.height(), self.isMaximized())

    def nativeEvent(self, event_type, message):
        if getattr(self, "frame_controller", None) is not None:
            handled, result = self.frame_controller.handle_native_event(event_type, message)
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SpikeWindow()
    win.show()
    sys.exit(app.exec())
