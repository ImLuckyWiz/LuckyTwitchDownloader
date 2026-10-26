"""Non-modal notification seam for the Qt UI (Phase 9b, B5 & B6).

Replaces ``dialogs.info`` for routine confirmations («Added to queue», «Clips added», «Copied»,
«Nothing to test») with non-modal bottom-right toast cards via ``qt_ui/toast.py``, while keeping
a simple function seam (``notify.info``, ``notify.success``, ``notify.warning``, ``notify.calls``)
that tests can inspect or monkeypatch just like ``qt_ui/dialogs.py``.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from qt_ui.toast import ToastCard, ToastHost

calls: list[tuple[str, str, str]] = []  # (kind, title, message) log for tests


def _host_for(parent: QWidget | None) -> ToastHost | None:
    if parent is None:
        return None
    win = parent.window()
    if win is None:
        return None
    host = getattr(win, "_toast_host", None)
    if not isinstance(host, ToastHost):
        host = ToastHost(win)
        win._toast_host = host
    return host


def show(
    parent: QWidget | None,
    title: str,
    message: str = "",
    kind: str = "info",
    action: tuple[str, Callable[[], None]] | None = None,
    duration_ms: int = ToastCard.DURATION_MS,
) -> ToastCard | None:
    """Show a non-modal toast on ``parent``'s top-level window and record the call."""
    calls.append((kind, title, message))
    host = _host_for(parent)
    if host is None:
        return None
    return host.show_toast(title, message, kind=kind, action=action, duration_ms=duration_ms)


def info(
    parent: QWidget | None,
    title: str,
    message: str = "",
    action: tuple[str, Callable[[], None]] | None = None,
) -> ToastCard | None:
    return show(parent, title, message, kind="info", action=action)


def success(
    parent: QWidget | None,
    title: str,
    message: str = "",
    action: tuple[str, Callable[[], None]] | None = None,
) -> ToastCard | None:
    return show(parent, title, message, kind="success", action=action)


def warning(
    parent: QWidget | None,
    title: str,
    message: str = "",
    action: tuple[str, Callable[[], None]] | None = None,
) -> ToastCard | None:
    return show(parent, title, message, kind="warning", action=action)


def system_notify(
    parent: QWidget | None,
    title: str,
    message: str = "",
    action: tuple[str, Callable[[], None]] | None = None,
) -> ToastCard | None:
    """Show an in-app toast and, when the window is in the background on a desktop session,
    an OS notification via ``QSystemTrayIcon`` if available (Phase 9b, B6)."""
    card = success(parent, title, message, action=action)
    app = QApplication.instance()
    if app is None or app.platformName() == "offscreen":
        return card
    win = parent.window() if parent is not None else None
    if win is not None and win.isActiveWindow():
        return card
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = getattr(win, "_tray_icon", None) if win is not None else None
            if tray is None and win is not None:
                tray = QSystemTrayIcon(app.windowIcon(), win)
                win._tray_icon = tray
            if tray is not None:
                tray.show()
                tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
    except Exception:  # noqa: BLE001
        pass
    return card
