"""The two background jobs of the Options tab: the tools setup and the overlay of a saved chat.

Ports of ``App.start_tools_setup`` and ``App.start_saved_chat_render``. Each starts ONE daemon thread that reports
only through the Bridge (``log``, ``progress``, ``tools_info``, ``tools_done``, ``saved_chat_done``); nothing here
touches a widget. The engine functions are looked up in this module when the thread runs, so tests replace
``qt_ui.background_jobs.ensure_tools`` / ``describe_tools`` / ``ensure_tdcli`` / ``render_existing_chat`` with fakes
(nothing is downloaded).

``tools_done`` and ``saved_chat_done`` carry ``""`` where the tkinter message carried ``None``.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from luckytwitch_engine import (
    Cancelled, Ctx, JobOptions, describe_tools, ensure_tdcli, ensure_tools, render_existing_chat,
)
from qt_ui.bridge import Bridge


def _emit(signal_name: str, bridge: Bridge, *args) -> None:
    """``bridge.<signal_name>.emit(*args)``, but a Bridge that was deleted meanwhile (the window closed while the
    thread was still working) is not an error: nobody is left to listen, so the thread just ends."""
    try:
        getattr(bridge, signal_name).emit(*args)
    except RuntimeError:  # «Signal source has been deleted»
        pass


def _make_ctx(bridge: Bridge) -> Ctx:
    return Ctx(log=lambda m: _emit("log", bridge, m), progress=lambda f, t: _emit("progress", bridge, f, t))


class ToolsRunner:
    """Download missing tools / update yt-dlp in the background."""

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.thread: threading.Thread | None = None

    def start(self, update: bool, force: bool) -> Ctx:
        """Start the setup and return its context at once (the window keeps it to cancel the setup when it closes)."""
        bridge = self.bridge
        ctx = _make_ctx(bridge)

        def work():
            error = ""
            try:
                ensure_tools(ctx, update_ytdlp=update, force=force)
            except Cancelled:
                error = "Cancelled."
            except Exception as e:  # noqa: BLE001
                error = str(e)
            try:
                text = describe_tools()
            except Exception as e:  # noqa: BLE001 (the status text is not worth losing the «done» message for)
                text = f"Could not read the tools: {e}"
            _emit("tools_info", bridge, text)
            _emit("tools_done", bridge, error)

        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()
        return ctx


class SavedChatRunner:
    """Draw the overlay of a chat file the person already has (no download)."""

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.thread: threading.Thread | None = None

    def start(self, chat: Path, opts: JobOptions) -> Ctx:
        bridge = self.bridge
        ctx = _make_ctx(bridge)

        def work():
            out, error = None, ""
            try:
                ctx.stage(0.0, 1.0, "Chat overlay")
                tool = ensure_tdcli(ctx)
                with tempfile.TemporaryDirectory(prefix="luckytwitch_chat_") as cache:
                    out = render_existing_chat(ctx, tool, chat, opts, Path(cache))
            except Cancelled:
                error = "Cancelled."
            except Exception as e:  # noqa: BLE001
                error = str(e)
            _emit("saved_chat_done", bridge, str(out) if out else "", error)

        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()
        return ctx
