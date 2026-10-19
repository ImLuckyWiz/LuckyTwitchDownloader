"""How a queue job's status and a log line are shown (copied from luckytwitch_downloader.py)."""

from __future__ import annotations

from core.palette import ACCENT_HOVER, ERR, MUTED, OK, WARN

STATUS_ICONS = {"queued": "○", "running": "▶", "done": "✓", "failed": "✕", "cancelled": "■"}
STATUS_COLOURS = {"queued": MUTED, "running": ACCENT_HOVER, "done": OK, "failed": ERR, "cancelled": WARN}
FINISHED = ("done", "failed", "cancelled")


def status_word(status: str) -> str:
    """«done (3 files)» -> «done», «running…» -> «running»."""
    words = status.split()
    return words[0].rstrip("…:") if words else ""


def status_label(status: str) -> str:
    """What the Status column shows: the text with a small icon in front («✓ done (3 files)»)."""
    icon = STATUS_ICONS.get(status_word(status))
    return f"{icon} {status}" if icon else status


def log_kind(msg: str) -> str:
    """How a log line is coloured: err | warn | ok | muted | plain."""
    m = msg.lstrip()
    low = m.lower()
    if m.startswith("ERROR"):
        return "err"
    if (m.startswith(("Warning", "Could not", "Cancelled", "Server busy")) or " failed" in low
            or "skipped" in low or "not found" in low):
        return "warn"
    if m.startswith("✔") or low.endswith(("installed.", "is up to date.")) or "up to date" in low:
        return "ok"
    if m.startswith("Queued:"):
        return "muted"
    return "plain"


def queue_summary(statuses: list[str]) -> str:
    """«1 running · 2 queued · 1 done · 1 failed» (nothing while the queue is empty: the list says so itself)."""
    if not statuses:
        return ""
    words = [status_word(s) for s in statuses]
    parts = [f"{words.count(w)} {w}" for w in ("running", "queued", "done", "failed", "cancelled") if w in words]
    return "  ·  ".join(parts)
