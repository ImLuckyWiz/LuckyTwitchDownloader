"""Download history tracking finished jobs (VOD id, title, streamer, date, parts, folder, quality)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths


@dataclass
class HistoryEntry:
    vod_id: str
    title: str = ""
    streamer: str = ""
    date: str = ""
    downloaded_at: str = ""
    parts: int = 1
    folder: str = ""
    quality: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            vod_id=str(data.get("vod_id", "")),
            title=str(data.get("title", "")),
            streamer=str(data.get("streamer", "")),
            date=str(data.get("date", "")),
            downloaded_at=str(data.get("downloaded_at", "") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
            parts=int(data.get("parts", 1) or 1),
            folder=str(data.get("folder", "")),
            quality=str(data.get("quality", "")),
        )


def _history_file(path: Path | None = None) -> Path:
    if path is not None:
        return path
    return getattr(paths, "HISTORY_PATH", paths.DATA_DIR / "luckytwitch_history.json")


def load_history(path: Path | None = None) -> list[HistoryEntry]:
    """Read history from JSON; returns empty list on any error or missing file."""
    f = _history_file(path)
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [HistoryEntry.from_dict(item) for item in data if isinstance(item, dict) and item.get("vod_id")]
    except Exception:
        pass
    return []


def save_history(entries: list[HistoryEntry], path: Path | None = None) -> None:
    """Save history entries to JSON safely."""
    f = _history_file(path)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        raw = [asdict(e) for e in entries]
        f.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass


def record_download(
    entry: HistoryEntry | dict[str, Any],
    path: Path | None = None,
    enabled: bool = True,
    max_entries: int = 500,
) -> list[HistoryEntry]:
    """Record a finished download. If enabled is False, does not write anything."""
    if not enabled:
        return load_history(path)
    item = entry if isinstance(entry, HistoryEntry) else HistoryEntry.from_dict(entry)
    if not item.vod_id:
        return load_history(path)
    if not item.downloaded_at:
        item.downloaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    entries = load_history(path)
    # Deduplicate: if vod_id and folder match, remove existing
    entries = [e for e in entries if not (e.vod_id == item.vod_id and e.folder == item.folder)]
    entries.insert(0, item)
    if len(entries) > max_entries:
        entries = entries[:max_entries]
    save_history(entries, path)
    return entries


def clear_history(path: Path | None = None) -> None:
    """Clear all recorded download history."""
    f = _history_file(path)
    try:
        if f.is_file():
            f.unlink()
    except OSError:
        pass


def is_downloaded(vod_id: str | None, path: Path | None = None) -> HistoryEntry | None:
    """Check if a VOD id is recorded in history; returns the latest entry or None."""
    if not vod_id:
        return None
    s_id = str(vod_id).strip()
    for e in load_history(path):
        if e.vod_id == s_id:
            return e
    return None
