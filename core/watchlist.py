"""Streamer watch list (pins streamers and checks for new VODs on start / periodic throttle)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths


@dataclass
class WatchedStreamer:
    login: str
    name: str = ""
    last_vod_id: str = ""
    last_seen_date: str = ""
    last_checked_at: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WatchedStreamer:
        return cls(
            login=str(data.get("login", "")).lower().strip(),
            name=str(data.get("name", "")).strip(),
            last_vod_id=str(data.get("last_vod_id", "")).strip(),
            last_seen_date=str(data.get("last_seen_date", "")).strip(),
            last_checked_at=float(data.get("last_checked_at", 0.0) or 0.0),
        )


def _watchlist_file(path: Path | None = None) -> Path:
    if path is not None:
        return path
    return getattr(paths, "WATCHLIST_PATH", paths.DATA_DIR / "luckytwitch_watchlist.json")


def load_watchlist(path: Path | None = None) -> list[WatchedStreamer]:
    """Read watch list from JSON. Silent on missing/corrupt file."""
    f = _watchlist_file(path)
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [WatchedStreamer.from_dict(d) for d in data if isinstance(d, dict) and d.get("login")]
    except Exception:
        pass
    return []


def save_watchlist(watchers: list[WatchedStreamer], path: Path | None = None) -> None:
    """Save watch list to JSON safely."""
    f = _watchlist_file(path)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        raw = [asdict(w) for w in watchers]
        f.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass


def add_to_watchlist(login: str, name: str = "", path: Path | None = None) -> list[WatchedStreamer]:
    """Pin a streamer to the watch list."""
    clean_login = login.lower().strip()
    if not clean_login:
        return load_watchlist(path)
    watchers = load_watchlist(path)
    for w in watchers:
        if w.login == clean_login:
            if name and not w.name:
                w.name = name
                save_watchlist(watchers, path)
            return watchers
    watchers.append(WatchedStreamer(login=clean_login, name=name or clean_login))
    save_watchlist(watchers, path)
    return watchers


def remove_from_watchlist(login: str, path: Path | None = None) -> list[WatchedStreamer]:
    """Unpin a streamer from the watch list."""
    clean_login = login.lower().strip()
    watchers = [w for w in load_watchlist(path) if w.login != clean_login]
    save_watchlist(watchers, path)
    return watchers


def is_watched(login: str, path: Path | None = None) -> bool:
    """Check if a streamer login is pinned."""
    clean_login = str(login or "").lower().strip()
    return any(w.login == clean_login for w in load_watchlist(path))


def check_streamer_new_vods(
    client: Any,
    watcher: WatchedStreamer,
    throttle_seconds: int = 300,
    now: float | None = None,
) -> tuple[WatchedStreamer, list[dict]]:
    """Look for VODs newer than the last seen one for this streamer.

    Silent on failure; respects throttle_seconds between network calls.
    """
    current_time = time.time() if now is None else now
    if current_time - watcher.last_checked_at < throttle_seconds:
        return watcher, []

    watcher.last_checked_at = current_time
    if not client:
        return watcher, []

    try:
        vods = client.get_channel_videos(watcher.login, first=6)
    except Exception:
        return watcher, []

    if not vods or not isinstance(vods, list):
        return watcher, []

    new_vods = []
    first_vod_id = str(vods[0].get("id", "")) if vods else ""
    first_vod_date = str(vods[0].get("created_at", "") or vods[0].get("date", "")) if vods else ""

    if not watcher.last_vod_id:
        # First time tracking: record current top VOD as baseline without notification
        watcher.last_vod_id = first_vod_id
        watcher.last_seen_date = first_vod_date
        return watcher, []

    for v in vods:
        vid = str(v.get("id", ""))
        vdate = str(v.get("created_at", "") or v.get("date", ""))
        if vid == watcher.last_vod_id:
            break
        if watcher.last_seen_date and vdate and vdate <= watcher.last_seen_date:
            break
        new_vods.append(v)

    if new_vods:
        watcher.last_vod_id = first_vod_id
        watcher.last_seen_date = first_vod_date

    return watcher, new_vods


def check_all_watchers(
    client: Any,
    path: Path | None = None,
    throttle_seconds: int = 300,
) -> dict[str, list[dict]]:
    """Check all watched streamers for new VODs and update the watch list."""
    watchers = load_watchlist(path)
    results: dict[str, list[dict]] = {}
    changed = False

    for w in watchers:
        updated, new_vods = check_streamer_new_vods(client, w, throttle_seconds=throttle_seconds)
        if new_vods:
            results[w.login] = new_vods
        if updated.last_checked_at != w.last_checked_at or updated.last_vod_id != w.last_vod_id:
            changed = True

    if changed:
        save_watchlist(watchers, path)

    return results
