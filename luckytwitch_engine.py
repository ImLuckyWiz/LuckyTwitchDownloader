"""
LuckyTwitch engine: everything that is not GUI.

  * parse cut points ("0:00 - 30:00 - 1:30:00 - end")
  * choose a download strategy (full download + split, or per-part sections)
  * download with yt-dlp, split / cut with ffmpeg
  * optional: Twitch clips -> chapters (filtered by views, duration, top N...)

Requirements:
    pip install requests

yt-dlp and ffmpeg/ffprobe are NOT bundled: on first run they are downloaded
into a per-user "tools" folder (yt-dlp from its GitHub releases, ffmpeg from
static builds) and yt-dlp is kept up to date. Copies found next to this file,
in a "bin" folder, in the tools folder or on PATH are used as they are.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable
from xml.sax.saxutils import escape

import requests

APP_DIR = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
API_URL = "https://api.twitch.tv/helix"

# Client ID of LuckyTwitch's own *public* Twitch app (Device Code Flow, no secret).
# Client IDs are public by design, so it is fine to ship it inside the app.
TWITCH_CLIENT_ID = "i00ldktkshoyftnytyijdwtjofhcq9"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

END_WORDS = {"end", "fin", "final", "finish", "finishes", "finished", "eof"}
FILLER_WORDS = {"till", "until", "to", "hasta", "the", "of", "vod"}


class EngineError(Exception):
    """Something went wrong; the message is meant to be shown to the user."""


class PlanError(EngineError):
    """The cut points text is invalid."""


class Cancelled(EngineError):
    """The user cancelled the job."""


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def parse_time(text: str) -> float | None:
    """'1:30:00', '90:00', '5400', '1h30m' -> seconds. Empty -> None."""
    text = text.strip().lower()
    if not text:
        return None
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", text)
    if m and any(m.groups()):
        h, mi, s = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)
    parts = text.split(":")
    if len(parts) > 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        raise PlanError(f"Invalid time: «{text}». Use H:MM:SS, MM:SS, seconds or 1h30m.")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def fmt_hms(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    s = int(round(seconds))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_twitch_duration(s: str) -> int:
    """'3h2m10s' -> seconds."""
    total = 0
    for value, unit in re.findall(r"(\d+)([hms])", s):
        total += int(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


# --------------------------------------------------------------------------- #
# Planning: cut points -> parts -> strategy
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Part:
    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Plan:
    parts: list[Part]
    strategy: str  # "full" or "sections"
    coverage: float  # fraction of the VOD that the parts cover
    duration: float | None


def split_groups(text: str) -> list[list[str]]:
    """Text -> list of groups (separated by ; or newline) of time tokens."""
    groups = []
    for chunk in re.split(r"[;\n]+", text):
        tokens = [t for t in re.split(r"[\s,\-–—]+", chunk.strip()) if t]
        tokens = [t for t in tokens if t.lower() not in FILLER_WORDS]
        if tokens:
            groups.append(tokens)
    return groups


def parse_cut_points(text: str, duration: float | None = None) -> list[Part]:
    """
    "0:00 - 30:00 - 1:30:00 - end"  ->  3 consecutive parts.
    Several groups (separated by ';' or a new line) allow gaps:
    "0:00 - 30:00 ; 2:00:00 - end"  ->  2 parts, the middle is skipped.
    """
    groups = split_groups(text)
    if not groups:
        raise PlanError("Write the cut points, e.g.  0:00 - 30:00 - 1:30:00 - end")

    parts: list[tuple[float, float]] = []
    for g in groups:
        points: list[float] = []
        for tok in g:
            if tok.lower() in END_WORDS:
                if duration is None:
                    raise PlanError("«end» needs the VOD length: press «Get info» first.")
                points.append(duration)
            else:
                points.append(parse_time(tok))  # type: ignore[arg-type]
        if len(points) < 2:
            raise PlanError(
                f"«{' '.join(g)}»: a group needs at least two points (use 0 and end)."
            )
        for a, b in zip(points, points[1:]):
            if duration is not None:
                if a >= duration:
                    raise PlanError(f"{fmt_hms(a)} is beyond the end of the VOD ({fmt_hms(duration)}).")
                if b > duration + 2:
                    raise PlanError(f"{fmt_hms(b)} is beyond the end of the VOD ({fmt_hms(duration)}).")
                b = min(b, duration)
            if b <= a:
                raise PlanError(f"Cut points must increase: {fmt_hms(a)} → {fmt_hms(b)}.")
            parts.append((a, b))

    parts.sort()
    for (a1, b1), (a2, b2) in zip(parts, parts[1:]):
        if a2 < b1:
            raise PlanError(
                f"Parts overlap: {fmt_hms(a1)}–{fmt_hms(b1)} and {fmt_hms(a2)}–{fmt_hms(b2)}."
            )
    return [Part(i, a, b) for i, (a, b) in enumerate(parts, 1)]


def choose_strategy(
    parts: list[Part], duration: float | None, mode: str = "auto", threshold: float = 0.6
) -> tuple[str, float]:
    """Return (strategy, coverage). mode: auto | full | sections."""
    coverage = (sum(p.duration for p in parts) / duration) if duration else 1.0
    if mode in ("full", "sections"):
        return mode, coverage
    return ("full" if coverage >= threshold else "sections"), coverage


def make_plan(
    text: str, duration: float | None, mode: str = "auto", threshold: float = 0.6
) -> Plan:
    parts = parse_cut_points(text, duration)
    strategy, coverage = choose_strategy(parts, duration, mode, threshold)
    return Plan(parts, strategy, coverage, duration)


def insert_cut_point(text: str, t: float, duration: float | None) -> str:
    """Insert a split point into the cut text (used by 'split at this clip')."""
    t = round(t)
    groups = split_groups(text)
    if not groups:
        end = "end" if duration else fmt_hms(t + 1)
        return f"0:00:00 - {fmt_hms(t)} - {end}"

    def val(tok: str) -> float | None:
        if tok.lower() in END_WORDS:
            return duration
        try:
            return parse_time(tok)
        except PlanError:
            return None

    for g in groups:
        vals = [val(tok) for tok in g]
        if None in vals or len(vals) < 2:
            continue
        if vals[0] < t < vals[-1]:  # type: ignore[operator]
            if t in vals:
                return text  # already a cut point exactly there: nothing to add (no duplicate boundary)
            pos = next(i for i, v in enumerate(vals) if v > t)  # type: ignore[operator]
            g.insert(pos, fmt_hms(t))
            break
    else:
        raise PlanError("That moment is not inside any of your parts.")
    return "\n".join(" - ".join(g) for g in groups)


# --------------------------------------------------------------------------- #
# Editing the parts from the timeline
#
# The cut text stays the source of truth. The timeline turns it into "ranges" (start, end) with
# ranges_of(), edits them with the functions below and writes them back with ranges_to_text().
# Ranges are in whole seconds, sorted and never overlap; two ranges that touch share a "cut point", a
# gap between two ranges is a skipped section. Every edit keeps parts >= MIN_PART.
# --------------------------------------------------------------------------- #
Range = tuple[float, float]
MIN_PART = 1.0  # seconds: the shortest part an edit can create


@dataclass(frozen=True)
class Edge:
    """Something on the timeline that can be dragged: kind is "cut" (shared by two touching parts, `index`
    is the left one), or "start" / "end" (the border of part `index` next to a skipped section)."""

    kind: str
    index: int
    t: float


def ranges_of(text: str, duration: float | None) -> list[Range]:
    """Cut text -> ranges in whole seconds (the text is written back that way anyway). Raises PlanError like
    parse_cut_points. A part that is shorter than a second once rounded is left out."""
    out = [(round(p.start), round(p.end)) for p in parse_cut_points(text, duration)]
    return [(s, e) for s, e in out if e - s >= MIN_PART]


def ranges_to_text(ranges: list[Range], duration: float | None) -> str:
    """Ranges -> cut text: touching parts in one line ("a - b - c"), skipped sections start a new line."""
    def tok(t: float, last: bool = False) -> str:
        return "end" if last and duration and t >= duration - 0.5 else fmt_hms(t)

    groups: list[list[str]] = []
    prev_end: float | None = None
    for s, e in ranges:
        if groups and prev_end is not None and abs(prev_end - s) < 1e-6:
            groups[-1].append(tok(e, True))
        else:
            groups.append([fmt_hms(s), tok(e, True)])
        prev_end = e
    return "\n".join(" - ".join(g) for g in groups)


def edges_of(ranges: list[Range]) -> list[Edge]:
    out: list[Edge] = []
    for i, (s, e) in enumerate(ranges):
        if not (i > 0 and abs(ranges[i - 1][1] - s) < 1e-6):  # a touching start is the previous part's "cut"
            out.append(Edge("start", i, s))
        touches = i + 1 < len(ranges) and abs(ranges[i + 1][0] - e) < 1e-6
        out.append(Edge("cut" if touches else "end", i, e))
    return out


def nearest_edge(ranges: list[Range], t: float, tolerance: float) -> Edge | None:
    """The edge closest to time `t`, if it is within `tolerance` seconds."""
    best = min(edges_of(ranges), key=lambda ed: abs(ed.t - t), default=None)
    return best if best is not None and abs(best.t - t) <= tolerance else None


def part_index_at(ranges: list[Range], t: float) -> int | None:
    for i, (s, e) in enumerate(ranges):
        if s <= t < e:
            return i
    return None


def add_cut(ranges: list[Range], t: float) -> list[Range] | None:
    """Split the part that contains `t`. None = nothing to do (skipped section, or too close to an edge)."""
    t = round(t)
    for i, (s, e) in enumerate(ranges):
        if s + MIN_PART <= t <= e - MIN_PART:
            return ranges[:i] + [(s, t), (t, e)] + ranges[i + 1:]
    return None


def move_edge(ranges: list[Range], edge: Edge, t: float, duration: float) -> list[Range]:
    """Drag an edge to `t` (clamped so no part gets shorter than MIN_PART and parts never overlap)."""
    t = round(t)
    r = list(ranges)
    i = edge.index
    if edge.kind == "cut":
        t = min(max(t, r[i][0] + MIN_PART), r[i + 1][1] - MIN_PART)
        r[i], r[i + 1] = (r[i][0], t), (t, r[i + 1][1])
    elif edge.kind == "start":
        lo = r[i - 1][1] if i > 0 else 0
        t = min(max(t, lo), r[i][1] - MIN_PART)
        r[i] = (t, r[i][1])
    else:
        hi = r[i + 1][0] if i + 1 < len(r) else duration
        t = min(max(t, r[i][0] + MIN_PART), hi)
        r[i] = (r[i][0], t)
    return r


def remove_cut(ranges: list[Range], index: int) -> list[Range]:
    """Merge part `index` with the next one (they must touch: use it for "cut" edges)."""
    return ranges[:index] + [(ranges[index][0], ranges[index + 1][1])] + ranges[index + 2:]


def toggle_part(ranges: list[Range], t: float, duration: float) -> list[Range] | None:
    """Skip the part at `t`, or bring back the skipped section at `t`. None = not possible
    (the last remaining part cannot be skipped)."""
    i = part_index_at(ranges, t)
    if i is not None:
        return ranges[:i] + ranges[i + 1:] if len(ranges) > 1 else None
    prev_end = max((e for s, e in ranges if e <= t), default=0)
    next_start = min((s for s, e in ranges if s > t), default=duration)
    if next_start - prev_end < MIN_PART:
        return None
    pos = sum(1 for s, e in ranges if e <= t)
    return ranges[:pos] + [(prev_end, next_start)] + ranges[pos:]


def isolate_span(ranges: list[Range], a: float, b: float, duration: float, only: bool = False) -> list[Range]:
    """Make [a, b] its own part(s): cut at a and b, and keep everything in between (skipped sections inside
    it are brought back). only=True: drop everything else and keep just [a, b]."""
    a, b = max(0, round(a)), min(duration, round(b))
    if b - a < MIN_PART:
        return list(ranges)
    if only:
        return [(a, b)]
    pieces: list[Range] = []
    for s, e in ranges:
        pts = [s] + [x for x in (a, b) if s + MIN_PART <= x <= e - MIN_PART] + [e]
        pieces += list(zip(pts, pts[1:]))
    inside = sorted(p for p in pieces if p[0] >= a and p[1] <= b)
    outside = [p for p in pieces if not (p[0] >= a and p[1] <= b)]
    filled: list[Range] = []
    cursor = a
    for s, e in inside:
        if s > cursor:
            filled.append((cursor, s))
        filled.append((s, e))
        cursor = e
    if b > cursor:
        filled.append((cursor, b))
    return sorted(outside + filled)


# --------------------------------------------------------------------------- #
# Twitch API (only needed for clips -> chapters)
# --------------------------------------------------------------------------- #
class TwitchClient:
    """
    Twitch API client with two ways to authenticate:
      * own app:   TwitchClient(client_id, client_secret)         (client credentials)
      * signed in: TwitchClient(client_id, access_token=..., refresh_token=..., on_tokens=...)
        (user token from the Device Code Flow; no secret needed). Twitch refresh tokens are
        single use, so every refresh reports the new pair through `on_tokens(access, refresh)`.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        access_token: str | None = None,
        refresh_token: str | None = None,
        on_tokens: Callable[[str | None, str | None], None] | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token: str | None = access_token
        self.user_refresh: str | None = refresh_token
        self.on_tokens = on_tokens

    @property
    def uses_login(self) -> bool:
        return not self.client_secret

    def refresh_token(self) -> None:
        """Get a fresh access token (named like this for backwards compatibility)."""
        if self.client_secret:
            r = requests.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=20,
            )
            if r.status_code in (400, 401, 403):
                raise ValueError("Invalid Client ID or Client Secret.")
            r.raise_for_status()
            self.token = r.json()["access_token"]
            return
        if not self.user_refresh:
            raise ValueError("Not signed in to Twitch.")
        r = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": self.user_refresh,
            },
            timeout=20,
        )
        if r.status_code in (400, 401, 403):
            self.token = self.user_refresh = None
            if self.on_tokens:
                self.on_tokens(None, None)
            raise ValueError("Your Twitch session expired. Sign in again (Twitch API… button).")
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        self.user_refresh = data.get("refresh_token", self.user_refresh)
        if self.on_tokens:
            self.on_tokens(self.token, self.user_refresh)

    def get(self, endpoint: str, params: dict) -> dict:
        if self.token is None:
            self.refresh_token()
        for _ in range(2):
            r = requests.get(
                f"{API_URL}/{endpoint}",
                params=params,
                headers={"Client-Id": self.client_id, "Authorization": f"Bearer {self.token}"},
                timeout=20,
            )
            if r.status_code == 401:
                self.refresh_token()
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Could not authenticate with Twitch.")


# --- Sign in with Twitch (Device Code Flow, public app: no client secret) ---------------- #
# Fetching clips needs no scope. Twitch documents `scopes` as required, so we first try an
# empty list and, if Twitch refuses, fall back to the least invasive scope.
_FALLBACK_SCOPE = "user:read:subscriptions"


def device_login_start(client_id: str = TWITCH_CLIENT_ID) -> dict:
    """Ask Twitch for a code. Returns device_code, user_code, verification_uri, expires_in, interval, scopes."""
    last = ""
    for scopes in ("", _FALLBACK_SCOPE):
        try:
            r = requests.post(DEVICE_URL, data={"client_id": client_id, "scopes": scopes}, timeout=20)
        except requests.RequestException as e:
            raise EngineError(f"Could not reach Twitch:\n{e}") from e
        if r.ok:
            data = r.json()
            data["scopes"] = scopes
            return data
        last = r.text[:300]
    raise EngineError(f"Twitch refused the sign-in request:\n{last}")


def device_login_poll(start: dict, client_id: str = TWITCH_CLIENT_ID,
                      cancel: threading.Event | None = None) -> tuple[str, str]:
    """Wait until the user approves the code on twitch.tv/activate. Returns (access_token, refresh_token)."""
    interval = max(int(start.get("interval") or 5), 1)
    deadline = time.monotonic() + int(start.get("expires_in") or 1800)
    while time.monotonic() < deadline:
        for _ in range(interval * 4):  # sleep in small steps so cancelling is quick
            if cancel is not None and cancel.is_set():
                raise Cancelled("Sign-in cancelled.")
            time.sleep(0.25)
        try:
            r = requests.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "scopes": start.get("scopes", ""),
                    "device_code": start["device_code"],
                    "grant_type": DEVICE_GRANT,
                },
                timeout=20,
            )
        except requests.RequestException:
            continue  # network blip: keep waiting
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.ok and body.get("access_token"):
            return body["access_token"], body.get("refresh_token", "")
        msg = str(body.get("message") or body.get("error_description") or body.get("error") or "")
        if "pending" in msg.lower():
            continue
        if "slow" in msg.lower():
            interval += 5
            continue
        raise EngineError(f"Twitch sign-in failed: {msg or r.status_code}")
    raise EngineError("The sign-in code expired. Start again.")


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def clip_start(clip: dict) -> float | None:
    """
    Where the clip STARTS in the VOD, in seconds (None if Twitch gave no position).

    Twitch's `vod_offset` is where the clip ENDS in the VOD, not where it starts
    (despite what the API docs say), so the start is `vod_offset - duration`.
    """
    off = clip.get("vod_offset")
    if off is None:
        return None
    return max(0.0, float(off) - float(clip.get("duration") or 0))


def clip_end(clip: dict) -> float | None:
    """Where the clip ENDS in the VOD, in seconds (None if Twitch gave no position)."""
    off = clip.get("vod_offset")
    return None if off is None else float(off)


def fetch_clips_for_vod(client: TwitchClient, vod_id: str) -> list[dict]:
    """All clips that belong to this VOD, sorted by position in the VOD."""
    data = client.get("videos", {"id": vod_id}).get("data", [])
    if not data:
        raise EngineError("Twitch API: VOD not found (deleted or private?).")
    video = data[0]
    start = datetime.strptime(video["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    end = start + timedelta(seconds=parse_twitch_duration(video["duration"]) + 300)

    clips, cursor = [], None
    while True:
        params = {
            "broadcaster_id": video["user_id"],
            "started_at": _iso_z(start),
            "ended_at": _iso_z(end),
            "first": 100,
        }
        if cursor:
            params["after"] = cursor
        page = client.get("clips", params)
        clips.extend(c for c in page.get("data", []) if c.get("video_id") == vod_id)
        cursor = page.get("pagination", {}).get("cursor")
        if not cursor:
            break
    clips.sort(key=lambda c: (clip_start(c) is None, clip_start(c) or 0))
    return clips


# --------------------------------------------------------------------------- #
# Finding streamers and their VODs (Search tab)
# --------------------------------------------------------------------------- #
VIDEO_TYPES = ("archive", "highlight", "upload")  # past broadcasts, highlights, uploads


def search_channels(client: TwitchClient, query: str, limit: int = 8) -> list[dict]:
    """
    Streamers matching `query`: [{id, login, name, live}]. An exact login match comes first,
    so typing a full channel name always finds that channel even if Twitch ranks it lower.
    """
    query = query.strip().lstrip("@")
    if not query:
        return []
    found: list[dict] = []
    for c in client.get("search/channels", {"query": query, "first": max(1, min(limit, 25))}).get("data", []):
        found.append({
            "id": str(c.get("id", "")),
            "login": c.get("broadcaster_login", ""),
            "name": c.get("display_name") or c.get("broadcaster_login", ""),
            "live": bool(c.get("is_live")),
        })
    if re.fullmatch(r"\w{1,25}", query):
        try:
            users = client.get("users", {"login": query.lower()}).get("data", [])
        except requests.RequestException:
            users = []  # the search above already worked; skip the exact lookup
        if users:
            u = users[0]
            uid = str(u.get("id", ""))
            exact = next((c for c in found if c["id"] == uid), None) or {
                "id": uid,
                "login": u.get("login", ""),
                "name": u.get("display_name") or u.get("login", ""),
                "live": False,
            }
            found = [exact] + [c for c in found if c["id"] != uid]
    return [c for c in found if c["id"]]


def fetch_videos(client: TwitchClient, user_id: str, vtype: str = "archive",
                 after: str | None = None, first: int = 20) -> tuple[list[dict], str | None]:
    """
    One page of a streamer's VODs, newest first: ([{id, title, date, duration, views, thumb, url}], next_cursor).
    `thumb` is a ready-to-download image URL ("" when Twitch has none yet, e.g. a stream still in progress).
    """
    if vtype not in VIDEO_TYPES:
        vtype = "archive"
    params: dict = {"user_id": user_id, "type": vtype, "sort": "time", "first": max(1, min(first, 100))}
    if after:
        params["after"] = after
    page = client.get("videos", params)
    videos = []
    for v in page.get("data", []):
        thumb = (v.get("thumbnail_url") or "").replace("%{width}", "320").replace("%{height}", "180")
        videos.append({
            "id": str(v.get("id", "")),
            "title": v.get("title") or "(untitled)",
            "date": (v.get("created_at") or "")[:10],
            "duration": parse_twitch_duration(v.get("duration", "")),
            "views": v.get("view_count", 0),
            "thumb": thumb,
            "url": v.get("url") or f"https://www.twitch.tv/videos/{v.get('id', '')}",
        })
    return videos, (page.get("pagination") or {}).get("cursor") or None


def fetch_thumbnail(url: str) -> Path | None:
    """Download a thumbnail once into the per-user cache folder and return its path (None on failure)."""
    if not url:
        return None
    path = user_data_dir() / "cache" / "thumbs" / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".jpg")
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
        r = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        os.replace(tmp, path)
        return path
    except (requests.RequestException, OSError):
        return None


# --------------------------------------------------------------------------- #
# Clips -> chapters
# --------------------------------------------------------------------------- #
@dataclass
class ClipFilter:
    min_views: int = 0
    min_duration: float = 0  # seconds
    top_n: int = 0  # 0 = no limit; otherwise keep the N most viewed
    pad_before: float = 3  # seconds added before the clip start
    pad_after: float = 0
    title_template: str = "{title} ({creator}, {views} views)"
    gap_title: str = "Stream"  # fills the space between clips; "" = no filler (MKV only)


@dataclass
class Chapter:
    start: float  # seconds, absolute VOD time
    end: float
    title: str
    views: int = 0
    clips: list[dict] = field(default_factory=list)
    kind: str = "clip"  # "clip" (a Twitch clip), "game" (a game / category change) or "muted" (silenced by Twitch)


class _SafeDict(dict):
    def __missing__(self, key):  # unknown {tokens} stay as they are
        return "{" + key + "}"


def filter_clips(clips: list[dict], flt: ClipFilter) -> list[dict]:
    """Keep only the clips that pass the filter (and can be placed in the VOD)."""
    kept = [
        c
        for c in clips
        if clip_start(c) is not None
        and c.get("view_count", 0) >= flt.min_views
        and c.get("duration", 0) >= flt.min_duration
    ]
    if flt.top_n > 0:
        kept.sort(key=lambda c: (-c.get("view_count", 0), clip_start(c)))
        kept = kept[: flt.top_n]
    kept.sort(key=clip_start)
    return kept


def _chapter_title(clip: dict, tpl: str) -> str:
    data = _SafeDict(
        title=clip.get("title", "") or "Clip",
        creator=clip.get("creator_name", ""),
        views=clip.get("view_count", 0),
        duration=round(clip.get("duration", 0)),
    )
    try:
        return tpl.format_map(data)
    except (ValueError, IndexError):
        return data["title"]


def clip_cut_text(
    clip: dict, duration: float | None, pad_before: float = 3, pad_after: float = 3
) -> str:
    """Cut text ('H:MM:SS - H:MM:SS') that covers just one clip (plus a little context)."""
    clip_s = clip_start(clip)
    if clip_s is None:
        raise PlanError("That clip has no position in the VOD.")
    start = max(0.0, clip_s - pad_before)
    end = float(clip["vod_offset"]) + pad_after
    if duration:
        end = min(end, duration)
    a, b = math.floor(start), math.ceil(end)
    if b <= a:
        raise PlanError("That clip is outside the VOD.")
    return f"{fmt_hms(a)} - {fmt_hms(b)}"


def make_chapters(clips: list[dict], flt: ClipFilter) -> list[Chapter]:
    """Filtered clips -> chapters in absolute VOD time. Overlapping clips are merged."""
    chapters: list[Chapter] = []
    for c in filter_clips(clips, flt):
        ch = Chapter(
            start=max(0.0, clip_start(c) - flt.pad_before),
            end=clip_end(c) + flt.pad_after,
            title=_chapter_title(c, flt.title_template),
            views=c.get("view_count", 0),
            clips=[c],
        )
        if chapters and ch.start <= chapters[-1].end:
            prev = chapters[-1]
            best = ch if ch.views > prev.views else prev
            n = len(prev.clips) + 1
            prev.title = best.title.split("  (+")[0] + f"  (+{n - 1} more)"
            prev.views = best.views
            prev.end = max(prev.end, ch.end)
            prev.clips.append(c)
        else:
            chapters.append(ch)
    return chapters


def chapters_for_part(chapters: list[Chapter], start: float, end: float) -> list[Chapter]:
    """Chapters that fall in [start, end], with times relative to the part."""
    out = []
    for ch in chapters:
        if ch.end <= start or ch.start >= end:
            continue
        s, e = max(ch.start, start) - start, min(ch.end, end) - start
        if e - s < 1:
            continue
        out.append(Chapter(s, e, ch.title, ch.views, ch.clips, ch.kind))
    return out


def game_chapters(segments: list[GameSegment]) -> list[Chapter]:
    """The game / category changes of a VOD as chapters of kind "game" (absolute VOD time)."""
    return [Chapter(g.start, g.end, g.title or "(no category)", kind="game") for g in segments]


MUTED_TITLE = "Muted audio"
MUTED_COMMENT = "Silenced by Twitch (usually copyrighted audio)"


def muted_chapters(ranges: list[Range] | None) -> list[Chapter]:
    """The stretches Twitch silenced as chapters of kind "muted" (absolute VOD time)."""
    return [Chapter(s, e, MUTED_TITLE, kind="muted") for s, e in (ranges or [])]


def fill_gaps(chapters: list[Chapter], total: float, title: str) -> list[Chapter]:
    """
    MP4 chapters are contiguous (each one lasts until the next starts, the first
    one starts at 0), so gaps between clips are filled with a neutral chapter.
    """
    if not chapters or not title:
        return chapters
    out: list[Chapter] = []
    pos = 0.0
    for ch in chapters:
        if ch.start - pos >= 1:
            out.append(Chapter(pos, ch.start, title))
        out.append(ch)
        pos = ch.end
    if total - pos >= 1:
        out.append(Chapter(pos, total, title))
    return out


def _ffmeta_escape(text: str) -> str:
    for ch in ("\\", "=", ";", "#", "\n"):
        text = text.replace(ch, "\\" + ch)
    return text


def ffmetadata(chapters: list[Chapter], tags: dict[str, str] | None = None) -> str:
    lines = [";FFMETADATA1"]
    for k, v in (tags or {}).items():
        if v:
            lines.append(f"{k}={_ffmeta_escape(v)}")
    for ch in chapters:
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(ch.start * 1000)}",
            f"END={int(ch.end * 1000)}",
            f"title={_ffmeta_escape(ch.title)}",
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Premiere Pro export (Final Cut Pro 7 XML with sequence markers)
# --------------------------------------------------------------------------- #
def _timebase(fps: float) -> tuple[int, bool]:
    """Frame rate -> (timebase, ntsc) the way FCP7 XML wants it: 59.94 -> (60, True)."""
    tb = max(1, round(fps))
    if abs(fps - tb) < 0.01:
        return tb, False
    if abs(fps - tb * 1000 / 1001) < 0.01:
        return tb, True
    return tb, False


def probe_video(path: Path) -> tuple[float, int, int] | None:
    """(fps, width, height) of the first video stream, or None if ffprobe is missing / fails."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate,width,height", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, env=_tool_env(), creationflags=_NO_WINDOW, timeout=60,
        ).stdout
        st = json.loads(out)["streams"][0]
        num, _, den = str(st["r_frame_rate"]).partition("/")
        fps = float(num) / float(den or 1)
        if fps <= 0:
            return None
        return fps, int(st.get("width") or 1920), int(st.get("height") or 1080)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, TypeError, ZeroDivisionError):
        return None


def premiere_markers_xml(
    name: str, chapters: list[Chapter], duration: float, fps: float, width: int = 1920, height: int = 1080
) -> str:
    """
    FCP7 XML (xmeml) with one empty sequence and one sequence marker (in = chapter start, out = chapter end) per chapter.
    Game / category chapters (kind "game") are named "GAME: <game>" so they stand out from the clip markers.
    Premiere imports it through File > Import. Marker times are relative to the part.
    """
    tb, ntsc = _timebase(fps)
    real_rate = tb * 1000 / 1001 if ntsc else float(tb)
    rate = f"<rate><timebase>{tb}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"
    total = max(1, math.ceil(duration * real_rate))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE xmeml>",
        '<xmeml version="4">',
        '<sequence id="sequence-1">',
        f"<duration>{total}</duration>",
        rate,
        f"<name>{escape(name)}</name>",
        "<media><video><format><samplecharacteristics>",
        rate,
        f"<width>{width}</width><height>{height}</height>",
        "<anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>",
        "</samplecharacteristics></format>",
        "<track><enabled>TRUE</enabled><locked>FALSE</locked></track>",
        "</video></media>",
        f"<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>",
    ]
    for ch in chapters:
        if ch.kind == "game":
            name, comment = f"GAME: {ch.title}", "Game / category"
        else:
            name = ch.title
            comment = " | ".join(
                f"{c.get('creator_name', '')} · {c.get('view_count', 0)} views · {c.get('url', '')}" for c in ch.clips
            )
        frame = min(max(int(round(ch.start * real_rate)), 0), total - 1)
        end = min(int(round(ch.end * real_rate)), total)  # the marker spans the whole clip
        lines += [
            "<marker>",
            f"<comment>{escape(comment)}</comment>",
            f"<name>{escape(name)}</name>",
            f"<in>{frame}</in>",
            f"<out>{end if end > frame else -1}</out>",
            "</marker>",
        ]
    lines += ["</sequence>", "</xmeml>"]
    return "\n".join(lines) + "\n"


def write_premiere_xml(dest: Path, chapters: list[Chapter], duration: float, fps: float,
                       width: int = 1920, height: int = 1080) -> Path:
    """Write <part name>.markers.xml next to the part file."""
    out = dest.with_name(dest.stem + ".markers.xml")
    out.write_text(premiere_markers_xml(dest.stem, chapters, duration, fps, width, height), encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# Premiere Pro plugin export (.markers.json, read by the plugin in premiere-plugin/)
# --------------------------------------------------------------------------- #
MARKERS_JSON_FORMAT = "luckytwitch-markers"
MARKERS_JSON_VERSION = 1  # bump when the layout changes in a way an older plugin cannot read; see docs/markers-format.md


def _clip_marker_comment(clips: list[dict]) -> str:
    return " | ".join(f"{c.get('creator_name', '')} · {c.get('view_count', 0)} views · {c.get('url', '')}" for c in clips)


def premiere_markers_json(
    name: str,
    chapters: list[Chapter],
    duration: float,
    fps: float,
    source: SourceInfo | None = None,
    part_start: float = 0.0,
    part_end: float | None = None,
) -> str:
    """
    The markers of one part as JSON for the Premiere Pro plugin. Unlike the XML it keeps what each marker is
    (a clip or a game) and the numbers behind it (views...), so the plugin can choose colors and names itself.
    Times are seconds from the start of the part; part_start / part_end say where the part sits in the VOD.
    Kinds: "clip", "game" and "muted" (a stretch Twitch silenced). A plugin that does not know "muted" skips those.
    """
    markers = []
    for ch in sorted(chapters, key=lambda c: (c.start, c.kind)):
        m: dict = {
            "kind": ch.kind if ch.kind in ("game", "muted") else "clip",
            "name": ch.title,
            "start": round(ch.start, 3),
            "end": round(ch.end, 3),
        }
        if ch.kind == "game":
            m["game"] = ch.title
            m["comment"] = "Game / category"
        elif ch.kind == "muted":
            m["comment"] = MUTED_COMMENT
        else:
            m["views"] = ch.views
            m["comment"] = _clip_marker_comment(ch.clips)
            m["clips"] = [
                {
                    "id": c.get("id"),
                    "title": c.get("title"),
                    "creator": c.get("creator_name"),
                    "views": c.get("view_count"),
                    "duration": c.get("duration"),
                    "url": c.get("url"),
                }
                for c in ch.clips
            ]
        markers.append(m)
    data: dict = {
        "format": MARKERS_JSON_FORMAT,
        "version": MARKERS_JSON_VERSION,
        "name": name,
        "duration": round(duration, 3),
        "fps": round(fps, 5),
        "part": {"start": round(part_start, 3), "end": round(part_end if part_end is not None else part_start + duration, 3)},
    }
    if source is not None:
        data["source"] = {
            "url": source.url,
            "vod_id": source.twitch_vod_id,
            "title": source.title,
            "streamer": source.uploader,
            "date": source.date,
        }
    data["markers"] = markers
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_markers_json(dest: Path, chapters: list[Chapter], duration: float, fps: float,
                       source: SourceInfo | None = None, part_start: float = 0.0,
                       part_end: float | None = None) -> Path:
    """Write <part name>.markers.json next to the part file."""
    out = dest.with_name(dest.stem + ".markers.json")
    out.write_text(premiere_markers_json(dest.stem, chapters, duration, fps, source, part_start, part_end),
                   encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# Source info (yt-dlp)
# --------------------------------------------------------------------------- #
@dataclass
class GameSegment:
    """One stretch of a VOD streamed under one game / category (Twitch "chapters")."""

    start: float  # seconds from the start of the VOD
    end: float
    title: str  # the game's name; the same game can appear in several segments


@dataclass
class Storyboard:
    """Twitch's preview thumbnails: a few big "sprite sheet" JPEGs, each a grid of small frames.

    Frame i shows the VOD at i * interval seconds. Only the first `count` tiles are real frames:
    the last sheet can be padded with unused tiles.
    """

    urls: list[str]  # the sheets, in order; the sheets are public (no token needed)
    tile_w: int
    tile_h: int
    columns: int
    rows: int  # tile rows per sheet
    interval: float  # seconds between two frames (1 / yt-dlp's "fps")
    count: int  # number of real frames

    @property
    def per_sheet(self) -> int:
        return self.columns * self.rows

    def frame_time(self, index: int) -> float:
        return index * self.interval

    def frame_index_at(self, seconds: float) -> int:
        """Index of the frame closest at or before `seconds` (clamped to the real frames)."""
        return max(0, min(self.count - 1, int(seconds // self.interval)))

    def tile_box(self, index: int) -> tuple[int, tuple[int, int, int, int]]:
        """(sheet number, (left, top, right, bottom) in pixels) of frame `index`."""
        sheet, pos = divmod(index, self.per_sheet)
        row, col = divmod(pos, self.columns)
        x, y = col * self.tile_w, row * self.tile_h
        return sheet, (x, y, x + self.tile_w, y + self.tile_h)


QUALITY_BEST = "best"    # the highest quality there is
QUALITY_AUDIO = "audio"  # the audio-only quality


@dataclass(frozen=True)
class VideoFormat:
    """One quality Twitch offers for a VOD (one entry of yt-dlp's "formats")."""
    format_id: str           # what yt-dlp calls it: "1080p60", "720p60", "480p", "Audio_Only"
    height: int = 0          # 0 for audio only
    fps: float = 0.0
    tbr: float = 0.0         # kbit/s as Twitch declares it (0 = unknown)
    audio_only: bool = False
    source: bool = False     # Twitch's own "Source" quality (format_note == "Source")

    @property
    def label(self) -> str:  # what the person reads
        if self.audio_only:
            return "Audio only"
        return f"{self.format_id} (Source)" if self.source else self.format_id

    @property
    def tag(self) -> str:    # for file names (Phase 7)
        return "audio" if self.audio_only else self.format_id


@dataclass
class SourceInfo:
    url: str
    id: str
    title: str
    uploader: str
    duration: float
    date: str  # YYYY-MM-DD or ""
    twitch_vod_id: str | None
    segments: list[GameSegment] = field(default_factory=list)  # game changes; [] when yt-dlp gives none
    storyboard: Storyboard | None = None  # None when the site has no preview thumbnails
    # Stretches Twitch silenced, in VOD seconds. [] = checked, none; None = not checked or could not be told.
    muted: list[Range] | None = None
    formats: list[VideoFormat] = field(default_factory=list)


def normalize_url(text: str) -> str:
    text = text.strip()
    if text.isdigit():
        return f"https://www.twitch.tv/videos/{text}"
    return text


def twitch_vod_id(url: str) -> str | None:
    m = re.search(r"twitch\.tv/(?:[\w]+/)?videos?/(\d+)", url)
    return m.group(1) if m else None


YTDLP_MISSING = "yt-dlp is not installed yet (it is downloaded automatically on first run). Check your connection and restart."


def get_source_info(text: str) -> SourceInfo:
    url = normalize_url(text)
    if not url:
        raise EngineError("Paste a VOD URL or ID.")
    if "\n" in url or "\r" in url:
        raise EngineError("Paste a single VOD URL or ID (not multi-line text).")
    ytdlp = find_tool("yt-dlp")
    if not ytdlp:
        raise EngineError(YTDLP_MISSING)
    try:
        proc = subprocess.run(
            [ytdlp, "--dump-single-json", "--no-warnings", "--skip-download", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            env=_tool_env(),
            creationflags=_NO_WINDOW,
            timeout=180,
        )
    except subprocess.TimeoutExpired as e:
        raise EngineError("yt-dlp took too long to read that URL.") from e
    except OSError as e:
        raise EngineError(f"Could not run yt-dlp:\n{e}") from e
    if proc.returncode != 0:
        raise EngineError(f"yt-dlp could not read that URL:\n{proc.stderr.strip()[-800:]}")
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise EngineError("yt-dlp returned unreadable data for that URL.") from e
    src = parse_source_info(info, url)
    if src.twitch_vod_id:  # one more small request; a failure only means "no muted ranges to show"
        src.muted = fetch_muted_ranges(info.get("formats"), src.duration)
    return src


def parse_source_info(info: dict, url: str) -> SourceInfo:
    """Turn yt-dlp's --dump-single-json output into a SourceInfo (no I/O, so it is easy to test)."""
    if not info.get("duration"):
        raise EngineError("yt-dlp did not report the video length for that URL.")
    duration = float(info["duration"])
    d = info.get("upload_date") or ""
    date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""
    return SourceInfo(
        url=url,
        id=str(info.get("id", "")),
        title=info.get("title", "") or "",
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=duration,
        date=date,
        twitch_vod_id=twitch_vod_id(url),
        segments=parse_game_segments(info.get("chapters"), duration),
        storyboard=parse_storyboard(info.get("formats"), duration),
        formats=parse_formats(info.get("formats")) if twitch_vod_id(url) else [],
    )


def parse_game_segments(chapters, duration: float) -> list[GameSegment]:
    """yt-dlp "chapters" -> game segments. Tolerates a missing / null / odd list; drops empty or broken entries.

    Segments are NOT merged by title: a streamer can go Just Chatting -> a game -> Just Chatting again.
    """
    if not isinstance(chapters, list):
        return []
    out: list[GameSegment] = []
    for c in chapters:
        if not isinstance(c, dict):
            continue
        try:
            start, end = float(c["start_time"]), float(c["end_time"])
        except (KeyError, TypeError, ValueError):
            continue
        start, end = max(0.0, start), min(end, duration)
        if not (end > start):  # also drops NaN
            continue
        out.append(GameSegment(start, end, str(c.get("title") or "").strip()))
    out.sort(key=lambda g: g.start)
    return out


def parse_storyboard(formats, duration: float, prefer: str = "low") -> Storyboard | None:
    """Pick the preview-thumbnail "format" of yt-dlp's list. prefer="low" = smallest tiles (fewest downloads).

    Frame timing comes from the format's "fps" (frames per second, e.g. 0.2 = one every 5 s), NOT from the
    fragments' "duration": those just split the VOD evenly between sheets, while the last sheet is only
    partly filled. Returns None if nothing usable is there.
    """
    if not isinstance(formats, list) or duration <= 0:
        return None
    best = None
    for f in formats:
        if not isinstance(f, dict) or f.get("format_note") != "storyboard":
            continue
        try:
            w, h = int(f["width"]), int(f["height"])
            cols, rows = int(f["columns"]), int(f["rows"])
            fps = float(f["fps"])
            urls = [str(fr["url"]) for fr in f["fragments"]]
        except (KeyError, TypeError, ValueError):
            continue
        if min(w, h, cols, rows) <= 0 or not (fps > 0) or not urls or not all(urls):
            continue
        count = min(math.ceil(duration * fps - 1e-6), len(urls) * cols * rows)  # never beyond what the sheets hold
        if count < 1:
            continue
        sb = Storyboard(urls=urls, tile_w=w, tile_h=h, columns=cols, rows=rows, interval=1 / fps, count=count)
        key = w * h
        if best is None or (key > best[0] if prefer == "high" else key < best[0]):
            best = (key, sb)
    return best[1] if best else None


def parse_formats(formats) -> list[VideoFormat]:
    """Turn yt-dlp's "formats" list into our sorted list of VideoFormat objects."""
    if not isinstance(formats, list):
        return []
    seen = set()
    result: list[VideoFormat] = []
    for f in formats:
        if not isinstance(f, dict):
            continue
        if f.get("format_note") == "storyboard":
            continue
        fid = f.get("format_id")
        if not fid or not isinstance(fid, str) or fid.strip() == "":
            continue
        fid = fid.strip()
        if fid in seen:
            continue
        url = f.get("url")
        if not isinstance(url, str):
            continue
        base_url = url.split("?")[0]
        if ".m3u8" not in base_url:
            continue
        seen.add(fid)
        audio_only = f.get("vcodec") == "none"
        try:
            h = int(f.get("height") or 0)
        except (ValueError, TypeError):
            h = 0
        try:
            fps = float(f.get("fps") or 0.0)
        except (ValueError, TypeError):
            fps = 0.0
        try:
            tbr = float(f.get("tbr") or 0.0)
        except (ValueError, TypeError):
            tbr = 0.0
        is_source = f.get("format_note") == "Source"
        result.append(
            VideoFormat(
                format_id=fid,
                height=max(0, h),
                fps=max(0.0, fps),
                tbr=max(0.0, tbr),
                audio_only=audio_only,
                source=is_source,
            )
        )
    # Sort: video first, then by height desc, fps desc, tbr desc; audio-only last
    result.sort(key=lambda vf: (not vf.audio_only, vf.height, vf.fps, vf.tbr), reverse=True)
    return result


def resolve_format(formats: list[VideoFormat], wanted: str = QUALITY_BEST) -> VideoFormat | None:
    """Pick the format from ``formats`` that best matches the ``wanted`` string."""
    if not formats:
        return None
    w = (wanted or "").strip().lower()

    # 1. "audio" -> audio-only; fallback to best video
    if w == QUALITY_AUDIO:
        for vf in formats:
            if vf.audio_only:
                return vf
        return resolve_format(formats, QUALITY_BEST)

    # 2. "best" / empty / unknown
    if w in ("", QUALITY_BEST):
        videos = [vf for vf in formats if not vf.audio_only]
        if videos:
            return max(videos, key=lambda vf: (vf.height, vf.fps, vf.tbr))
        return formats[0]

    # 3. Exact format_id match (case-insensitive)
    for vf in formats:
        if vf.format_id.lower() == w:
            return vf

    # 4. Height cap like "720p"
    m = re.search(r"(\d{3,4})p", w)
    if m:
        cap = int(m.group(1))
        videos = [vf for vf in formats if not vf.audio_only and vf.height > 0]
        under = [vf for vf in videos if vf.height <= cap]
        if under:
            return max(under, key=lambda vf: (vf.height, vf.fps, vf.tbr))
        if videos:
            # Lowest video format
            return min(videos, key=lambda vf: (vf.height, vf.fps, vf.tbr))

    # 5. Fallback to best
    return resolve_format(formats, QUALITY_BEST)


def describe_quality(fmt: VideoFormat, asked: str = QUALITY_BEST) -> str:
    """Human-readable description of the resolved format, noting differences if what was asked was not exact."""
    a = (asked or "").strip().lower()
    base = f"Quality: {fmt.label}"
    if a in ("", QUALITY_BEST):
        return base
    if a == fmt.format_id.lower():
        return base
    if a == QUALITY_AUDIO and fmt.audio_only:
        return base
    return f"{base} (asked for {asked})"


def estimate_bytes(fmt: VideoFormat | None, seconds: float) -> int:
    """Estimated download size in bytes based on Twitch's declared bitrate (tbr in kbit/s)."""
    if fmt is None or fmt.tbr <= 0 or seconds <= 0:
        return 0
    return int(round(fmt.tbr * 1000 / 8 * seconds))


# --------------------------------------------------------------------------- #
# Muted stretches (Twitch silences copyrighted audio; the HLS playlist says which segments)
# --------------------------------------------------------------------------- #
# Twitch names a silenced segment "<n>-muted.<ext>" (e.g. "522-muted.mp4") and a normal one "<n>.<ext>".
_MUTED_SEGMENT = re.compile(r"-muted(?:\.[A-Za-z0-9]+)?$", re.IGNORECASE)


def parse_muted_ranges(text: str, duration: float | None = None) -> list[Range]:
    """
    A media playlist -> the stretches (start, end in VOD seconds) made of "-muted" segments; touching
    segments are merged. Deliberately lenient (unlike parse_hls_playlist): tags it does not know are
    ignored, because all it needs is the length of each segment and whether its name says "muted".
    """
    from urllib.parse import urlsplit

    out: list[list[float]] = []
    t, length = 0.0, 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("#EXTINF:"):
                try:
                    length = float(line[8:].split(",", 1)[0])
                except ValueError:
                    length = 0.0
            continue
        name = urlsplit(line).path.rsplit("/", 1)[-1]
        if _MUTED_SEGMENT.search(name) and length > 0:
            if out and abs(out[-1][1] - t) < 0.01:
                out[-1][1] = t + length
            else:
                out.append([t, t + length])
        t += length
        length = 0.0
    top = duration if duration and duration > 0 else None
    ranges: list[Range] = []
    for s, e in out:
        if top is not None:
            s, e = min(s, top), min(e, top)
        if e - s >= 0.5:
            ranges.append((round(s, 3), round(e, 3)))
    return ranges


def pick_playlist_url(formats) -> str | None:
    """The HLS media playlist of the best video quality in yt-dlp's format list (the one the downloads use)."""
    if not isinstance(formats, list):
        return None
    best: tuple[tuple[float, float, float], str] | None = None
    for f in formats:
        if not isinstance(f, dict):
            continue
        url = f.get("url")
        if not isinstance(url, str) or ".m3u8" not in url.split("?", 1)[0]:
            continue
        if f.get("vcodec") == "none" or f.get("format_note") == "storyboard":  # audio-only / thumbnails
            continue
        key = tuple(float(f.get(k) or 0) for k in ("height", "fps", "tbr"))
        if best is None or key > best[0]:
            best = (key, url)  # type: ignore[assignment]
    return best[1] if best else None


def muted_from_playlist_url(url: str, duration: float | None = None) -> list[Range] | None:
    """Download a playlist and read its muted stretches. None = could not be told (any failure)."""
    try:
        resp = requests.get(url, headers={"User-Agent": HLS_USER_AGENT}, timeout=15)
        resp.raise_for_status()
        return parse_muted_ranges(resp.text, duration)
    except (requests.RequestException, ValueError):
        return None


def fetch_muted_ranges(formats, duration: float | None = None) -> list[Range] | None:
    """The muted stretches of a VOD from yt-dlp's format list: [] = none, None = could not be told."""
    url = pick_playlist_url(formats)
    return muted_from_playlist_url(url, duration) if url else None


def muted_overlap(muted: list[Range] | None, start: float, end: float) -> float:
    """Seconds of [start, end] that fall inside muted stretches."""
    return sum(max(0.0, min(e, end) - max(s, start)) for s, e in (muted or []))


def fetch_storyboard_sheet(url: str) -> Path | None:
    """Download one sprite sheet once into the per-user cache and return its path (None on failure)."""
    if not url:
        return None
    path = user_data_dir() / "cache" / "storyboards" / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".jpg")
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
        r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        os.replace(tmp, path)
        return path
    except (requests.RequestException, OSError):
        return None


def load_storyboard_frames(sb: Storyboard, fetch: Callable[[str], Path | None] = fetch_storyboard_sheet) -> list:
    """Download the sheets and cut them into frames: a list of `sb.count` PIL images (None = unavailable).

    Slow (network): call it from a background thread. Needs Pillow; without it (or without any sheet) the
    frames are all None, so callers just show no thumbnails.
    """
    frames: list = [None] * sb.count
    try:
        from PIL import Image
    except ImportError:
        return frames
    sheets: dict[int, object] = {}
    for n, url in enumerate(sb.urls):
        path = fetch(url)
        if path is None:
            continue
        try:
            with Image.open(path) as im:
                sheets[n] = im.convert("RGB")
        except (OSError, ValueError):
            continue
    for i in range(sb.count):
        n, box = sb.tile_box(i)
        im = sheets.get(n)
        if im is None or box[2] > im.width or box[3] > im.height:  # sheet missing or smaller than expected
            continue
        frames[i] = im.crop(box)
    return frames


# --------------------------------------------------------------------------- #
# Job description
# --------------------------------------------------------------------------- #
@dataclass
class JobOptions:
    cut_text: str
    out_dir: str
    container: str = "mp4"  # mp4 | mkv
    strategy: str = "auto"  # auto | full | sections
    full_threshold: float = 0.6
    exact: bool = False  # re-encode for frame-exact cuts (slow)
    keep_full: bool = False
    threads: int = 8
    name_template: str = "{streamer} - {date} - {id} - part{n}"
    chapters: bool = False
    clip_filter: ClipFilter = field(default_factory=ClipFilter)
    sidecar: bool = False  # write a .clips.json next to each part
    subfolders: bool = True  # out_dir/<streamer>/<stream>/parts
    folder_template: str = "{date} - {title} - {id}"  # name of the per-stream folder
    clip_name_template: str = "{clip_title}"  # file name when a single clip is downloaded
    clean_title: bool = True  # strip bot commands (!links, !gsupps) and promo tags from stream titles
    premiere_xml: bool = False  # also write a Premiere Pro XML (clips as markers) next to each part
    game_markers: bool = False  # also put the game / category changes into that XML as markers ("GAME: ...")
    premiere_plugin: bool = False  # also write a .markers.json for the LuckyTwitch Premiere Pro plugin (colors, details)
    muted_markers: bool = False  # ... and put the stretches Twitch silenced into that .markers.json (kind "muted")
    chat: bool = False  # also download the chat of each part with TwitchDownloaderCLI (Twitch VODs only)
    chat_format: str = "json"  # json | txt | html
    chat_embed: bool = False  # embed emotes / badges in the chat file (bigger, but it renders offline)
    chat_render: bool = False  # also render the chat of each part as an overlay video for the editor (Twitch VODs only)
    chat_render_mode: str = "transparent"  # transparent (Animation .mov) | prores (ProRes 4444 .mov) | compact (H.264 .mp4)
    chat_render_look: str = "outline"  # outline (text with an outline, nothing behind) | panel (dark see-through panel)
    chat_render_width: int = 400  # pixels
    chat_render_height: int = 0  # pixels; 0 = the height of the video part
    chat_render_font_size: int = 18
    chat_render_fps: int = 0  # 0 = like the video (60 if it has 60 fps, else 30)
    chat_render_smooth: bool = False  # redraw on every frame (smooth scrolling, slower) instead of 5 times a second
    quality: str = QUALITY_BEST  # quality to download (Twitch VODs): "best", "720p60", "audio", etc.
    audio_format: str = "m4a"  # audio container when quality is audio-only: "m4a" | "mp3"


@dataclass
class Job:
    source: SourceInfo
    opts: JobOptions
    clips: list[dict] | None = None  # pre-fetched clips (otherwise fetched at run time)
    client: TwitchClient | None = None
    single_clip: dict | None = None  # set when the job only downloads this one clip


# --------------------------------------------------------------------------- #
# Runtime context: logging, progress, cancel, subprocess handling
# --------------------------------------------------------------------------- #
def user_data_dir() -> Path:
    """Per-user, always writable folder (also works when the app is frozen / inside a .app)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "LuckyTwitch"


TOOLS_DIR = Path(os.environ.get("LUCKYTWITCH_TOOLS_DIR") or user_data_dir() / "tools")
EXE = ".exe" if sys.platform == "win32" else ""
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
USER_AGENT = "LuckyTwitch/1.0 (+https://github.com/yt-dlp/yt-dlp)"
YTDLP_RELEASES = "https://github.com/yt-dlp/yt-dlp/releases"
FFMPEG_BUILDS = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest"
# Optional chat download: TwitchDownloaderCLI (MIT, https://github.com/lay295/TwitchDownloader). Pinned to the
# version the integration was tested with; downloaded the first time "Download chat" is used.
TDCLI_REPO = "lay295/TwitchDownloader"
TDCLI_VERSION = "1.56.5"


def find_tool(name: str) -> str | None:
    """
    Where is `name` (yt-dlp / ffmpeg / ffprobe)? Order: our tools folder, next to
    the script, ./bin, PyInstaller bundle, PATH and (macOS) the Homebrew folders
    (a GUI app on macOS does not inherit the shell's PATH).
    """
    dirs = [TOOLS_DIR, APP_DIR, APP_DIR / "bin"]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        dirs.append(Path(bundle))
    for d in dirs:
        cand = d / (name + EXE)
        if cand.is_file():
            return str(cand)
    exe = shutil.which(name)
    if exe:
        return exe
    if sys.platform == "darwin":
        for d in ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"):
            cand = Path(d) / name
            if cand.is_file():
                return str(cand)
    return None


def _tool_env() -> dict[str, str]:
    """Environment for yt-dlp / ffmpeg: force UTF-8 so titles with emojis survive the pipe."""
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its children (yt-dlp.exe spawns a child, and yt-dlp spawns ffmpeg)."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                creationflags=_NO_WINDOW,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Tools: download / update yt-dlp and ffmpeg
# --------------------------------------------------------------------------- #
def _is_managed(path: str | Path) -> bool:
    try:
        return Path(path).resolve().parent == TOOLS_DIR.resolve()
    except OSError:
        return False


def _read_versions() -> dict:
    try:
        return json.loads((TOOLS_DIR / "versions.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_version(name: str, value: str) -> None:
    data = _read_versions()
    data[name] = value
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    (TOOLS_DIR / "versions.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def _run_version(path: str, flag: str) -> str:
    try:
        out = subprocess.run(
            [path, flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            env=_tool_env(),
            creationflags=_NO_WINDOW,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "?"
    first = (out.strip().splitlines() or ["?"])[0].strip()
    m = re.match(r"ffmpeg version (\S+)", first)
    return m.group(1) if m else first


def installed_ytdlp_version() -> str | None:
    path = find_tool("yt-dlp")
    if not path:
        return None
    return (_read_versions().get("yt-dlp") if _is_managed(path) else None) or _run_version(path, "--version")


def describe_tools() -> str:
    """Human-readable status of both tools (runs them, so call it from a worker thread)."""
    lines = []
    for name, flag in (("yt-dlp", "--version"), ("ffmpeg", "-version")):
        path = find_tool(name)
        if not path:
            lines.append(f"{name}: not installed")
            continue
        where = "managed by LuckyTwitch" if _is_managed(path) else path
        lines.append(f"{name} {_run_version(path, flag)}  ({where})")
    tdcli = find_tdcli()
    if not tdcli:
        lines.append("TwitchDownloaderCLI: not installed (downloaded the first time chat is used)")
    elif _is_managed_tdcli(tdcli):
        lines.append(f"TwitchDownloaderCLI {_read_versions().get('tdcli', '?')}  (managed by LuckyTwitch)")
    else:
        lines.append(f"TwitchDownloaderCLI {_run_version(tdcli, '--version')}  ({tdcli})")
    return "\n".join(lines)


def _http_get(url: str, **kw) -> requests.Response:
    return requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT}, **kw)


def _download_file(ctx: "Ctx", url: str, dest: Path) -> None:
    ctx.check_cancel()
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        with _http_get(url, stream=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    ctx.check_cancel()
                    f.write(chunk)
                    done += len(chunk)
                    speed = done / max(time.monotonic() - t0, 0.001) / 1048576
                    size = f"{done / 1048576:.0f}" + (f"/{total / 1048576:.0f}" if total else "") + " MiB"
                    ctx.report(done / total if total else None, f"{size} · {speed:.1f} MiB/s")
    except requests.RequestException as e:
        raise EngineError(f"Network error while downloading {url.rsplit('/', 1)[-1]}:\n{e}") from e


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _verify_checksum(path: Path, sums_url: str, filename: str) -> None:
    """Check the download against the checksum list published next to it on GitHub."""
    try:
        r = _http_get(sums_url)
        r.raise_for_status()
    except requests.RequestException as e:
        raise EngineError(f"Could not fetch the checksums to verify {filename}:\n{e}") from e
    expected = None
    for line in r.text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and Path(parts[-1].lstrip("*")).name == filename:
            expected = parts[0].lower()
            break
    if not expected:
        raise EngineError(f"No checksum is published for {filename}.")
    if _sha256(path) != expected:
        raise EngineError(f"Checksum mismatch for {filename}: the download is corrupted, try again.")


def _ytdlp_asset() -> str:
    if sys.platform == "win32":
        return "yt-dlp.exe" if sys.maxsize > 2**32 else "yt-dlp_x86.exe"
    if sys.platform == "darwin":
        return "yt-dlp_macos"  # universal2 (Intel + Apple Silicon)
    return "yt-dlp_linux_aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "yt-dlp_linux"


def latest_ytdlp_tag() -> str:
    """Latest release tag, read from the redirect of /releases/latest/download (no API rate limit)."""
    try:
        r = _http_get(f"{YTDLP_RELEASES}/latest/download/SHA2-256SUMS", allow_redirects=False, stream=True)
        try:
            location = r.headers.get("Location", "")
        finally:
            r.close()
    except requests.RequestException as e:
        raise EngineError(f"Could not reach GitHub to check yt-dlp:\n{e}") from e
    m = re.search(r"/download/([^/]+)/", location)
    if not m:
        raise EngineError("Could not find the latest yt-dlp release on GitHub.")
    return m.group(1)


def install_ytdlp(ctx: "Ctx", tag: str | None = None) -> str:
    """Download the standalone yt-dlp binary from GitHub into the tools folder."""
    tag = tag or latest_ytdlp_tag()
    asset = _ytdlp_asset()
    base = f"{YTDLP_RELEASES}/download/{tag}"
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TOOLS_DIR / "yt-dlp.download"
    ctx.log(f"Downloading yt-dlp {tag}…")
    ctx.stage(0.0, 1.0, f"Downloading yt-dlp {tag}")
    try:
        _download_file(ctx, f"{base}/{asset}", tmp)
        _verify_checksum(tmp, f"{base}/SHA2-256SUMS", asset)
        tmp.chmod(0o755)
        try:
            os.replace(tmp, TOOLS_DIR / ("yt-dlp" + EXE))
        except PermissionError as e:
            raise EngineError("yt-dlp is in use right now. Wait for running jobs to finish and try again.") from e
    finally:
        tmp.unlink(missing_ok=True)
    _write_version("yt-dlp", tag)
    ctx.log(f"yt-dlp {tag} installed.")
    return tag


_FFMPEG_NAMES = {"ffmpeg", "ffprobe"}


def _wanted_member(path: str) -> str | None:
    """File name to extract for a member of an ffmpeg archive (only bin/ffmpeg, bin/ffprobe, bin/*.dll)."""
    p = PurePosixPath(path.replace("\\", "/"))
    if p.parent.name != "bin":
        return None
    stem = p.name[:-4] if p.name.lower().endswith(".exe") else p.name
    if stem in _FFMPEG_NAMES or p.name.lower().endswith(".dll"):
        return p.name
    return None


def _write_member(src, name: str) -> None:
    tmp = TOOLS_DIR / (name + ".tmp")
    with open(tmp, "wb") as out:
        shutil.copyfileobj(src, out)
    tmp.chmod(0o755)
    os.replace(tmp, TOOLS_DIR / name)


def _extract_ffmpeg(archive: Path) -> None:
    found = set()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                name = None if info.is_dir() else _wanted_member(info.filename)
                if name:
                    with z.open(info) as src:
                        _write_member(src, name)
                    found.add(name)
    else:
        with tarfile.open(archive, "r:*") as t:
            for m in t:
                name = _wanted_member(m.name) if m.isfile() else None
                if name:
                    src = t.extractfile(m)
                    if src is not None:
                        with src:
                            _write_member(src, name)
                        found.add(name)
    if "ffmpeg" + EXE not in found:
        raise EngineError("The ffmpeg archive did not contain ffmpeg.")


def _mac_ffmpeg_sources(tool: str) -> list[tuple[str, str]]:
    """(label, url) candidates for a macOS static build, native architecture first."""
    arm = platform.machine().lower() == "arm64"
    riedl = f"https://ffmpeg.martin-riedl.de/redirect/latest/macos/{'arm64' if arm else 'amd64'}/release/{tool}.zip"
    osx = f"https://www.osxexperts.net/{tool}80{'arm' if arm else 'intel'}.zip"
    ever = f"https://evermeet.cx/ffmpeg/getrelease/{tool}/zip"
    return [("martin-riedl.de", riedl), ("osxexperts.net", osx), ("evermeet.cx", ever)]


def _download_with_retry(ctx: "Ctx", url: str, dest: Path, attempts: int = 3) -> None:
    """_download_file, but waits and retries when the server says 429 / 5xx."""
    for n in range(1, attempts + 1):
        try:
            _download_file(ctx, url, dest)
            return
        except EngineError as e:
            if isinstance(e, Cancelled) or n == attempts or not re.search(r"\b(429|50[0-4])\b", str(e)):
                raise
            wait = 5 * n
            ctx.log(f"Server busy ({url.split('/')[2]}), retrying in {wait}s…")
            for _ in range(wait):
                ctx.check_cancel()
                time.sleep(1)


def _install_ffmpeg_macos(ctx: "Ctx") -> None:
    """Static builds, trying several hosts so one rate-limiting us (HTTP 429) is not fatal."""
    errors: list[str] = []
    for label in [s[0] for s in _mac_ffmpeg_sources("ffmpeg")]:
        try:
            for i, tool in enumerate(("ffmpeg", "ffprobe")):
                url = dict(_mac_ffmpeg_sources(tool))[label]
                archive = TOOLS_DIR / f"{tool}.zip.download"
                ctx.stage(i / 2, (i + 1) / 2, f"Downloading {tool}")
                try:
                    _download_with_retry(ctx, url, archive)
                    with zipfile.ZipFile(archive) as z:
                        member = next((n for n in z.namelist()
                                       if PurePosixPath(n).name == tool and not n.startswith("__MACOSX")), None)
                        if member is None:
                            raise EngineError(f"The {tool} download did not contain {tool}.")
                        with z.open(member) as src:
                            _write_member(src, tool)
                finally:
                    archive.unlink(missing_ok=True)
            return
        except (EngineError, zipfile.BadZipFile) as e:
            if isinstance(e, Cancelled):
                raise
            errors.append(f"{label}: {str(e).splitlines()[0]}")
            ctx.log(f"ffmpeg from {label} failed, trying the next source…")
    raise EngineError("Could not download ffmpeg automatically:\n  " + "\n  ".join(errors) +
                      "\n\nWait a few minutes and try again, or install it with Homebrew:  brew install ffmpeg"
                      f"\n(or copy ffmpeg and ffprobe into {TOOLS_DIR})")


def install_ffmpeg(ctx: "Ctx") -> None:
    """Download a static ffmpeg + ffprobe build into the tools folder (one-time)."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    ctx.log("Downloading ffmpeg (one-time download, it can be large)…")
    if sys.platform == "darwin":
        _install_ffmpeg_macos(ctx)
        _write_version("ffmpeg", "macos-static")
        ctx.log("ffmpeg installed.")
        return
    arm = platform.machine().lower() in ("aarch64", "arm64")
    if sys.platform == "win32":
        asset = "ffmpeg-master-latest-win64-gpl-shared.zip"  # "shared" = same tools, much smaller download
    else:
        asset = "ffmpeg-master-latest-linuxarm64-gpl.tar.xz" if arm else "ffmpeg-master-latest-linux64-gpl.tar.xz"
    archive = TOOLS_DIR / (asset + ".download")
    try:
        ctx.stage(0.0, 0.9, "Downloading ffmpeg")
        _download_file(ctx, f"{FFMPEG_BUILDS}/{asset}", archive)
        ctx.stage(0.9, 1.0, "Verifying ffmpeg")
        ctx.report(None)
        _verify_checksum(archive, f"{FFMPEG_BUILDS}/checksums.sha256", asset)
        ctx.stage(0.95, 1.0, "Extracting ffmpeg")
        ctx.report(None)
        _extract_ffmpeg(archive)
    finally:
        archive.unlink(missing_ok=True)
    _write_version("ffmpeg", asset)
    ctx.log("ffmpeg installed.")


def ensure_tools(ctx: "Ctx", update_ytdlp: bool = True, force: bool = False) -> None:
    """
    Make sure ffmpeg and yt-dlp exist (download them if not) and keep our own copy
    of yt-dlp up to date. Missing tools raise EngineError; a failed update check
    is only logged. `force` = reinstall the latest yt-dlp even if it looks current.
    """
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        install_ffmpeg(ctx)
    else:
        where = "managed by LuckyTwitch" if _is_managed(ffmpeg) else ffmpeg
        ctx.log(f"ffmpeg is installed ({_run_version(ffmpeg, '-version')}, {where}).")
    if not find_tool("ffprobe"):
        ctx.log("Warning: ffprobe was not found next to ffmpeg; some features may fail.")

    ytdlp = find_tool("yt-dlp")
    if not ytdlp or (force and not _is_managed(ytdlp)):
        install_ytdlp(ctx)
        return
    if not update_ytdlp and not force:
        return
    if not _is_managed(ytdlp):
        ctx.log(f"Using the yt-dlp found at {ytdlp} (update it yourself if downloads break).")
        return
    try:
        latest = latest_ytdlp_tag()
        current = installed_ytdlp_version()
        if force or current != latest:
            install_ytdlp(ctx, latest)
        else:
            ctx.log(f"yt-dlp is up to date ({current}).")
    except Cancelled:
        raise
    except EngineError as e:
        ctx.log(f"Could not update yt-dlp (using the installed one): {e}")


class Ctx:
    def __init__(
        self,
        log: Callable[[str], None] | None = None,
        progress: Callable[[float, str], None] | None = None,
    ):
        self._log = log or (lambda m: None)
        self._progress = progress or (lambda f, t: None)
        self.cancel_event = threading.Event()
        self.proc: subprocess.Popen | None = None
        self._lo, self._hi, self._label = 0.0, 1.0, ""
        self._log_step, self._log_t = -1, float("-inf")

    # -- logging / progress -- #
    def log(self, msg: str) -> None:
        self._log(msg)

    def stage(self, lo: float, hi: float, label: str) -> None:
        self._lo, self._hi, self._label = lo, hi, label
        self._log_step, self._log_t = -1, float("-inf")
        self._progress(lo, label)

    def span(self) -> tuple[float, float]:
        """The share of the progress bar the current stage owns, to split it into smaller stages."""
        return self._lo, self._hi

    def relabel(self, label: str) -> None:
        """New label for the current stage, keeping its share of the progress bar."""
        self.stage(self._lo, self._hi, label)

    def report(self, frac: float | None, extra: str = "") -> None:
        text = self._label + (f"  ·  {extra}" if extra else "")
        if frac is None:
            self._progress(-1, text)
        else:
            frac = min(max(frac, 0.0), 1.0)
            self._progress(self._lo + frac * (self._hi - self._lo), text)

    def log_progress(self, frac: float | None, extra: str = "") -> None:
        """Write a progress line to the log: every 10% (or every 30 s if there is no percentage)."""
        now = time.monotonic()
        step = int(min(max(frac, 0.0), 1.0) * 10) if frac is not None else None
        if (step is not None and step > self._log_step) or now - self._log_t >= 30:
            if step is not None:
                self._log_step = max(self._log_step, step)
            self._log_t = now
            pct = f"{min(max(frac, 0.0), 1.0) * 100:.0f}%" if frac is not None else ""
            body = " · ".join(x for x in (pct, extra) if x)
            self._log(f"{self._label}: {body}" if body else self._label)

    # -- cancel -- #
    def cancel(self) -> None:
        self.cancel_event.set()
        proc = self.proc
        if proc:
            kill_process_tree(proc)

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled("Cancelled.")


_FF_PROGRESS_KEYS = {"out_time_us", "out_time_ms", "total_size", "speed", "progress"}


class FfmpegProgress:
    """
    Reads the `-progress pipe:1` key=value lines of ffmpeg. feed(line) returns (fraction, text) at the end of
    each update block (text = "12.3 MiB · 2.9x · ETA 1:04:33"), otherwise None.
    """

    def __init__(self, total: float | None):
        self.total = total
        self.t: float | None = None
        self.size: float | None = None  # bytes
        self.speed: float | None = None

    def feed(self, line: str) -> tuple[float | None, str] | None:
        key, _, value = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms"):
            try:
                self.t = int(value) / 1_000_000
            except ValueError:
                pass
        elif key == "total_size":
            try:
                self.size = float(value)
            except ValueError:
                pass
        elif key == "speed":
            try:
                self.speed = float(value.strip().rstrip("x"))
            except ValueError:
                self.speed = None
        elif key == "progress" and self.t is not None:
            frac = min(max(self.t / self.total, 0.0), 1.0) if self.total else None
            bits = []
            if self.size:
                mib = self.size / (1024 * 1024)
                bits.append(f"{mib:.1f} MiB" if mib < 10 else f"{mib:.0f} MiB")
            if self.speed and self.speed > 0:
                bits.append(f"{self.speed:.1f}x")
                if self.total:
                    bits.append(f"ETA {fmt_hms(max(self.total - self.t, 0) / self.speed)}")
            return frac, " · ".join(bits)
        return None


# --------------------------------------------------------------------------- #
# MP4 movie timescale
# --------------------------------------------------------------------------- #
# Newer ffmpeg builds set the MP4 "movie timescale" to the least common multiple of the track timescales
# (720000 for 90 kHz video + 48 kHz audio) instead of 1000. The edit list lengths are then stored in
# 1/720000 s, and on a part longer than ~99 min they no longer fit in 32 bits. Premiere Pro's importer
# crashes on such files (QT::QTTrack::CalcTrim) although every video player opens them. Forcing 1000
# keeps the edit list (so audio and video stay in sync) and its numbers small.
MP4_MOVIE_TIMESCALE = 1000


def mp4_flags(container: str) -> list[str]:
    """ffmpeg output options that keep an MP4 readable by Premiere Pro. Empty for other containers."""
    return ["-movie_timescale", str(MP4_MOVIE_TIMESCALE)] if container.lower().lstrip(".") == "mp4" else []


def audio_out_container(opts: "JobOptions") -> str:
    return opts.audio_format if opts.audio_format in AUDIO_FORMATS else "m4a"


def audio_codec_args(container: str) -> list[str]:
    """m4a: Twitch's AAC copied as it is. mp3: converted."""
    return ["-c:a", "libmp3lame", "-b:a", "192k"] if container == "mp3" else ["-c:a", "copy"]


def audio_only_options(opts: "JobOptions") -> tuple["JobOptions", list[str]]:
    """The options with every video-only extra switched off, and the names of the ones that were on."""
    skipped = [label for key, label in AUDIO_SKIPPED if getattr(opts, key)]
    return replace(opts, **{key: False for key, _ in AUDIO_SKIPPED}), skipped


def mp4_movie_timescale(path: Path) -> int | None:
    """Movie timescale (mvhd) of an MP4 / MOV file, read from its header only. None if it cannot be read."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            total = f.tell()
            pos = 0
            while pos + 8 <= total:
                f.seek(pos)
                head = f.read(16)
                size, typ = int.from_bytes(head[:4], "big"), head[4:8]
                hdr = 8
                if size == 1 and len(head) >= 16:
                    size, hdr = int.from_bytes(head[8:16], "big"), 16
                elif size == 0:
                    size = total - pos
                if size < hdr:
                    return None
                if typ == b"moov":
                    f.seek(pos + hdr)
                    data = f.read(min(size - hdr, 1 << 20))  # mvhd is the first box inside moov
                    i = data.find(b"mvhd")
                    if i < 4:
                        return None
                    body = i + 4  # version(1) flags(3) then times
                    version = data[body]
                    off = body + (20 if version == 1 else 12)
                    return int.from_bytes(data[off:off + 4], "big")
                pos += size
    except OSError:
        return None
    return None


def run_ffmpeg(ctx: Ctx, args: list[str], total: float | None = None) -> str:
    """Run ffmpeg, report progress when `total` (seconds of output) is known."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise EngineError("ffmpeg was not found. Install it and add it to PATH.")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + args
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    ctx.check_cancel()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        start_new_session=sys.platform != "win32",
    )
    ctx.proc = proc
    errors: list[str] = []
    progress = FfmpegProgress(total)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.partition("=")[0] in _FF_PROGRESS_KEYS:
                parsed = progress.feed(line)
                if parsed and total:
                    ctx.report(parsed[0], parsed[1])
                    ctx.log_progress(parsed[0], parsed[1])
            elif line and "=" not in line.split(" ")[0]:
                errors.append(line)
        proc.wait()
    finally:
        ctx.proc = None
    ctx.check_cancel()
    if proc.returncode != 0:
        raise EngineError("ffmpeg failed:\n" + "\n".join(errors[-8:]))
    return "\n".join(errors)


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #
PROGRESS_TEMPLATE = (
    "download:LTPROG|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s"
    "|%(progress.total_bytes_estimate)s|%(progress.fragment_index)s|%(progress.fragment_count)s"
    "|%(progress.speed)s|%(progress.eta)s"
)


def _num(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:  # "NA" = field not available
        return None


def parse_progress(line: str) -> tuple[float | None, str] | None:
    """One line printed by yt-dlp with PROGRESS_TEMPLATE -> (fraction or None, text), else None."""
    if not line.startswith("LTPROG|"):
        return None
    fields = line.split("|")
    if len(fields) < 9:
        return None
    dl, total, est, f_idx, f_cnt, speed, eta = (_num(x) for x in fields[2:9])
    frac = None
    if f_cnt:
        frac = (f_idx or 0) / f_cnt
    elif total or est:
        frac = (dl or 0) / (total or est)  # type: ignore[operator]
    bits = []  # the percentage is shown by the GUI itself
    if dl:
        bits.append(f"{dl / 1048576:.0f} MiB")
    if speed:
        bits.append(f"{speed / 1048576:.1f} MiB/s")
    if eta is not None:
        bits.append(f"ETA {fmt_hms(eta)}")
    return frac, " · ".join(bits)


# Sections are downloaded by ffmpeg (yt-dlp hands the job over) and yt-dlp reports nothing
# while it does, so we read ffmpeg's own stats lines:  "size=  1234KiB time=00:01:23.45 ... speed=12.3x"
_FF_TIME = re.compile(r"\btime=(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_FF_SIZE = re.compile(r"\bL?size=\s*(\d+(?:\.\d+)?)\s*([kKMG]i?B)\b")
_FF_SPEED = re.compile(r"\bspeed=\s*(\d+(?:\.\d+)?)x")


def parse_ffmpeg_stats(line: str, total: float | None) -> tuple[float | None, str] | None:
    """One ffmpeg stats line -> (fraction of `total` seconds, text), or None if it is not one."""
    m = _FF_TIME.search(line)
    if not m:
        return None
    t = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    frac = min(t / total, 1.0) if total else None
    bits = []
    if frac is None:
        bits.append(fmt_hms(t))
    ms = _FF_SIZE.search(line)
    if ms:
        value, unit = float(ms[1]), ms[2].lower()
        mib = value / 1024 if unit.startswith("k") else value * 1024 if unit.startswith("g") else value
        bits.append(f"{mib:.1f} MiB" if mib < 10 else f"{mib:.0f} MiB")
    mp = _FF_SPEED.search(line)
    if mp:
        speed = float(mp[1])
        bits.append(f"{speed:.1f}x")
        if total and speed > 0:
            bits.append(f"ETA {fmt_hms(max(total - t, 0) / speed)}")
    return frac, " · ".join(bits)


def _out_template(folder: Path, stem: str) -> str:
    """yt-dlp output template; '%' in the folder name must be escaped."""
    return str(folder).replace("%", "%%") + os.sep + stem + ".%(ext)s"


def _folder_size(folder: Path) -> int:
    total = 0
    try:
        for p in folder.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def _watch_folder(ctx: Ctx, folder: Path, stop: threading.Event, last_real: list[float]) -> None:
    """Fallback progress: if the downloader reports nothing for a while, show how much has landed on disk."""
    samples: list[tuple[float, int]] = []
    while not stop.wait(1.0):
        now = time.monotonic()
        size = _folder_size(folder)
        samples = (samples + [(now, size)])[-8:]
        if now - last_real[0] < 5 or size <= 0:
            continue
        t0, s0 = samples[0]
        speed = (size - s0) / (now - t0) if now > t0 else 0
        text = f"{size / 1048576:.0f} MiB" + (f" · {speed / 1048576:.1f} MiB/s" if speed > 0 else "")
        ctx.report(None, text)
        ctx.log_progress(None, text)


def run_ytdlp(
    ctx: Ctx,
    args: list[str],
    threads: int,
    total_secs: float | None = None,
    watch_dir: Path | None = None,
    format_id: str | None = None,
) -> None:
    """
    Run the yt-dlp binary, forwarding progress to ctx. Cancel kills the whole process tree.
    total_secs: length of what is being downloaded (sections) so ffmpeg's stats become a percentage.
    watch_dir: folder where the download lands, used as a fallback progress source.
    """
    ytdlp = find_tool("yt-dlp")
    if not ytdlp:
        raise EngineError(YTDLP_MISSING)
    quality_args = ["-f", format_id] if format_id else ["-S", "res,fps,tbr"]
    cmd = [
        ytdlp,
        *quality_args,
        "--concurrent-fragments", str(max(1, threads)),
        "--retries", "10",
        "--fragment-retries", "10",
        "--continue",
        "--quiet", "--progress", "--newline",
        "--progress-template", PROGRESS_TEMPLATE,
    ]
    if total_secs:
        # --quiet makes yt-dlp run ffmpeg with -loglevel quiet; -stats brings its progress line back.
        cmd += ["--downloader-args", "ffmpeg:-stats"]
    ffmpeg = find_tool("ffmpeg")
    if ffmpeg:
        cmd += ["--ffmpeg-location", str(Path(ffmpeg).parent)]
    cmd += args
    ctx.check_cancel()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_tool_env(),
            creationflags=_NO_WINDOW,
            start_new_session=sys.platform != "win32",
        )
    except OSError as e:
        raise EngineError(f"Could not run yt-dlp:\n{e}") from e
    ctx.proc = proc
    last_real = [time.monotonic()]
    stop = threading.Event()
    watcher = None
    if watch_dir is not None:
        watcher = threading.Thread(target=_watch_folder, args=(ctx, watch_dir, stop, last_real), daemon=True)
        watcher.start()
    tail: list[str] = []
    try:
        assert proc.stdout is not None
        # text mode turns the "\r" that ffmpeg uses between stats updates into line breaks
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            parsed = parse_progress(line) or parse_ffmpeg_stats(line, total_secs)
            if parsed:
                last_real[0] = time.monotonic()
                ctx.report(*parsed)
                ctx.log_progress(*parsed)
                continue
            tail.append(line)
            if line.startswith(("WARNING", "ERROR")):
                ctx.log(f"yt-dlp: {line}")
        proc.wait()
    finally:
        stop.set()
        if watcher:
            watcher.join(timeout=2)
        ctx.proc = None
    ctx.check_cancel()
    if proc.returncode != 0:
        raise EngineError("Download failed:\n" + "\n".join(tail[-8:]))


AUDIO_FORMATS = ("m4a", "mp3")
MEDIA_EXTS = {".mp4", ".mkv", ".ts", ".webm", ".mov", ".m4v", ".m4a", ".mp3"}
AUDIO_SKIPPED = (  # settings that need a video track -> what the log calls them
    ("exact", "frame-exact cuts"),
    ("premiere_xml", "Premiere XML markers"),
    ("premiere_plugin", "Premiere plugin markers"),
    ("game_markers", "game markers"),
    ("muted_markers", "muted markers"),
    ("chat_render", "chat overlay video"),
)


def _find_media(folder: Path) -> Path | None:
    files = [p for p in folder.glob("*") if p.suffix.lower() in MEDIA_EXTS and p.is_file()]
    return max(files, key=lambda p: p.stat().st_size) if files else None


def download_full(ctx: Ctx, url: str, workdir: Path, threads: int, format_id: str | None = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    done = workdir / "full.done"
    existing = _find_media(workdir)
    if done.exists() and existing:
        ctx.log("Full VOD already downloaded in the work folder, reusing it.")
        return existing
    kw = {"format_id": format_id} if format_id is not None else {}
    run_ytdlp(ctx, ["-o", _out_template(workdir, "full"), url], threads, **kw)
    media = _find_media(workdir)
    if not media:
        raise EngineError("yt-dlp finished but no video file was found.")
    done.write_text("ok")
    return media


def download_section(
    ctx: Ctx, url: str, part: Part, workdir: Path, threads: int, exact: bool, format_id: str | None = None
) -> Path:
    pdir = workdir / f"part{part.index}"
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True)
    args = ["-o", _out_template(pdir, "part"), "--download-sections", f"*{part.start:.3f}-{part.end:.3f}"]
    if exact:
        args.append("--force-keyframes-at-cuts")
    kw = {"format_id": format_id} if format_id is not None else {}
    run_ytdlp(ctx, args + [url], threads, total_secs=part.duration, watch_dir=pdir, **kw)
    media = _find_media(pdir)
    if not media or media.stat().st_size < 4096:
        raise EngineError(
            f"Part {part.index} ({fmt_hms(part.start)}–{fmt_hms(part.end)}) came out empty. "
            "Try again, or use strategy «full» to download the whole VOD and split it."
        )
    return media


# --------------------------------------------------------------------------- #
# Sections by whole HLS segments (no ffmpeg -ss, so the real start is known)
# --------------------------------------------------------------------------- #
HLS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class Segment:
    start: float  # seconds from the start of the VOD
    end: float
    url: str
    # fMP4 playlists: (absolute init-section URL, "length@offset" or None) from #EXT-X-MAP
    init: tuple[str, str | None] | None = None
    # "length@offset" from #EXT-X-BYTERANGE, with the offset always explicit
    byterange: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


def _hls_attrs(text: str) -> dict[str, str]:
    """Attributes of a tag like  URI="x",BYTERANGE="10@0"  ->  {"URI": "x", "BYTERANGE": "10@0"}."""
    return {k.upper(): v.strip('"') for k, v in re.findall(r'([A-Za-z0-9-]+)=("[^"]*"|[^,]*)', text)}


def parse_hls_playlist(text: str, base_url: str) -> list[Segment]:
    """
    Parse a finished (VOD) media playlist into segments with cumulative times.
    Supports fMP4 playlists (#EXT-X-MAP init section) and byte ranges.
    Raises ValueError for anything where segment time = cumulative duration is not safe
    (live stream, encryption, discontinuities, master playlist).
    """
    from urllib.parse import urljoin

    segments: list[Segment] = []
    pending: float | None = None
    pending_range: tuple[int, int | None] | None = None  # (length, offset or None)
    init: tuple[str, str | None] | None = None
    next_offset: dict[str, int] = {}  # resource URL -> where the next implicit byte range starts
    t = 0.0
    ended = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            tag = line.split(":", 1)[0]
            rest = line.split(":", 1)[1] if ":" in line else ""
            if tag in ("#EXT-X-KEY", "#EXT-X-SESSION-KEY", "#EXT-X-DISCONTINUITY", "#EXT-X-STREAM-INF"):
                raise ValueError(f"unsupported playlist tag {tag}")
            if tag == "#EXT-X-MAP":
                attrs = _hls_attrs(rest)
                if "URI" not in attrs:
                    raise ValueError(f"bad line: {line}")
                init = (urljoin(base_url, attrs["URI"]), attrs.get("BYTERANGE"))
            elif tag == "#EXT-X-BYTERANGE":
                try:
                    length_s, _, offset_s = rest.partition("@")
                    pending_range = (int(length_s), int(offset_s) if offset_s else None)
                except ValueError as e:
                    raise ValueError(f"bad line: {line}") from e
            elif tag == "#EXT-X-ENDLIST":
                ended = True
            elif tag == "#EXTINF":
                try:
                    pending = float(rest.split(",", 1)[0])
                except (ValueError, IndexError) as e:
                    raise ValueError(f"bad line: {line}") from e
            continue
        if pending is None:
            raise ValueError("segment without #EXTINF")
        seg_url = urljoin(base_url, line)
        byterange = None
        if pending_range is not None:
            length, offset = pending_range
            if offset is None:
                offset = next_offset.get(seg_url, 0)
            next_offset[seg_url] = offset + length
            byterange = f"{length}@{offset}"
            pending_range = None
        segments.append(Segment(t, t + pending, seg_url, init, byterange))
        t += pending
        pending = None
    if not ended:
        raise ValueError("playlist is not finished (no #EXT-X-ENDLIST)")
    if not segments:
        raise ValueError("playlist has no segments")
    return segments


def select_segments(segments: list[Segment], start: float, end: float) -> tuple[int, int]:
    """
    Index range (first, last) of the segments that cover [start, end].
    The first segment is the one containing `start`, the last one the one containing `end`
    (an end exactly on a boundary belongs to the segment that ends there). Times outside the VOD are clamped.
    """
    eps = 1e-6
    total = segments[-1].end
    if end <= start:
        raise ValueError("empty time range")
    if start >= total - eps:
        raise ValueError("the part starts after the end of the VOD")
    first = 0
    for i, seg in enumerate(segments):
        if seg.start <= start + eps:
            first = i
        else:
            break
    last = len(segments) - 1
    for i, seg in enumerate(segments):
        if seg.end >= end - eps:
            last = i
            break
    return first, max(first, last)


def write_local_playlist(segments: list[Segment], dest: Path) -> None:
    target = max(1, math.ceil(max(s.duration for s in segments)))
    needs_map = any(s.init for s in segments)
    lines = [
        "#EXTM3U",
        f"#EXT-X-VERSION:{7 if needs_map else 4 if any(s.byterange for s in segments) else 3}",
        f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    current_init = None
    for s in segments:
        if s.init and s.init != current_init:
            uri, brange = s.init
            lines.append(f'#EXT-X-MAP:URI="{uri}"' + (f',BYTERANGE="{brange}"' if brange else ""))
            current_init = s.init
        lines.append(f"#EXTINF:{s.duration:.3f},")
        if s.byterange:
            lines.append(f"#EXT-X-BYTERANGE:{s.byterange}")
        lines.append(s.url)
    lines.append("#EXT-X-ENDLIST")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_playlist_url(ctx: Ctx, url: str, format_id: str | None = None) -> str:
    """The media playlist (.m3u8) yt-dlp would download, chosen with the same quality flags."""
    ytdlp = find_tool("yt-dlp")
    if not ytdlp:
        raise EngineError(YTDLP_MISSING)
    ctx.check_cancel()
    quality_args = ["-f", format_id] if format_id else ["-S", "res,fps,tbr"]
    try:
        proc = subprocess.run(
            [ytdlp, "-g", *quality_args, "--no-warnings", url],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_tool_env(), creationflags=_NO_WINDOW, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise EngineError(f"Could not get the playlist address: {e}") from e
    ctx.check_cancel()
    urls = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0 or len(urls) != 1:
        raise EngineError(f"yt-dlp gave {len(urls)} address(es) instead of one playlist")
    if not urls[0].startswith("http") or ".m3u8" not in urls[0].split("?", 1)[0]:
        raise EngineError("the video address is not an HLS playlist")
    return urls[0]


def download_section_aligned(
    ctx: Ctx, url: str, part: Part, workdir: Path, format_id: str | None = None, audio_only: bool = False
) -> tuple[Path, float, float] | None:
    """
    Download [part.start, part.end] as whole HLS segments with a single ffmpeg stream copy and NO -ss.
    Returns (file, real_start, real_end) in VOD time: the file starts at a segment boundary at or
    before part.start (never after) and the caller knows exactly where.
    Returns None when this method cannot be used (the caller then uses the old method).
    """
    try:
        kw = {"format_id": format_id} if format_id is not None else {}
        playlist_url = get_playlist_url(ctx, url, **kw)
        resp = requests.get(playlist_url, headers={"User-Agent": HLS_USER_AGENT}, timeout=30)
        resp.raise_for_status()
        segments = parse_hls_playlist(resp.text, playlist_url)
        first, last = select_segments(segments, part.start, part.end)
        chosen = segments[first : last + 1]
        real_start, real_end = chosen[0].start, min(chosen[-1].end, segments[-1].end)

        pdir = workdir / f"part{part.index}"
        if pdir.exists():
            shutil.rmtree(pdir)
        pdir.mkdir(parents=True)
        local = pdir / "part.m3u8"
        write_local_playlist(chosen, local)
        out = pdir / ("part.m4a" if audio_only else "part.mp4")
        map_args = ["-map", "0:a:0"] if audio_only else ["-map", "0:v:0", "-map", "0:a?"]
        run_ffmpeg(
            ctx,
            [
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                "-i", str(local),
                *map_args,
                "-c", "copy", *mp4_flags("mp4"), "-f", "mp4", str(out),
            ],
            total=real_end - real_start,
        )
        if not out.exists() or out.stat().st_size < 4096:
            raise EngineError("the downloaded file is empty")
    except Cancelled:
        raise
    except (EngineError, requests.RequestException, ValueError, OSError) as e:
        # Keep every line of the message (ffmpeg's real error comes after the "ffmpeg failed:" header).
        reason = " | ".join(ln.strip() for ln in str(e).splitlines() if ln.strip())[:500] or type(e).__name__
        ctx.log(f"Could not use the segment download ({reason}); using the old method. Markers may be up to 10 s off.")
        return None
    return out, real_start, real_end


# --------------------------------------------------------------------------- #
# Splitting / finalizing
# --------------------------------------------------------------------------- #
def clean_title(title: str) -> str:
    """Clean chat bot commands (!gsupps, !links, !clash), promo tags (#ad),
    emojis without word smushing, and dangling trailing delimiters from a stream title.
    """
    if not title:
        return ""
    # 1. Replace 4-byte Unicode characters (emojis / pictographs) with a space so adjacent words don't smush
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", " ", title)
    # 2. Strip chat bot commands that start with ! (e.g. !gsupps, !links, !clash, !discord, !merch, !drops)
    cleaned = re.sub(r"(?<!\w)!\w+", "", cleaned)
    # 3. Strip promotional hashtags / bracketed tags (e.g. #ad, #sponsored, #partner, [DROPS])
    cleaned = re.sub(r"(?<!\w)#(?:ad|sponsored|partner|drops|promo)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[(?:drops|drops enabled|!drops)\]", "", cleaned, flags=re.IGNORECASE)
    # 4. Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 5. Clean up dangling trailing separators left behind (e.g. trailing " - ", " | ", " · ", " : ")
    cleaned = re.sub(r"[\s\-_|/·•:,]+$", "", cleaned).strip()
    return cleaned or title.strip()


def safe_name(text: str) -> str:
    """Strip emojis / illegal characters so the name is safe everywhere."""
    text = re.sub(r"[\U00010000-\U0010ffff]", " ", text)
    text = re.sub(r"[^\w\s\-\.\(\)\[\]]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip(" .")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def dominant_game(segments: list[GameSegment] | None, start: float, end: float) -> str:
    """Returns the game/category with the longest time overlap inside [start, end]."""
    if not segments or end <= start:
        return ""
    overlaps: dict[str, float] = {}
    for seg in segments:
        seg_start = getattr(seg, "start", 0.0)
        seg_end = getattr(seg, "end", 0.0)
        title = (getattr(seg, "title", "") or "").strip()
        if not title:
            continue
        overlap = max(0.0, min(end, seg_end) - max(start, seg_start))
        if overlap > 0:
            overlaps[title] = overlaps.get(title, 0.0) + overlap
    if not overlaps:
        return ""
    return max(overlaps.items(), key=lambda item: item[1])[0]


def date_components(date_str: str | None) -> tuple[str, str, str]:
    """Extract (year, month, day) from YYYY-MM-DD or empty strings if invalid."""
    if not date_str:
        return "", "", ""
    parts = date_str.strip().split("-")
    year = parts[0] if len(parts) >= 1 and len(parts[0]) == 4 and parts[0].isdigit() else ""
    month = parts[1] if len(parts) >= 2 and len(parts[1]) == 2 and parts[1].isdigit() else ""
    day = parts[2] if len(parts) >= 3 and len(parts[2]) == 2 and parts[2].isdigit() else ""
    return year, month, day


def format_duration_tag(seconds: float) -> str:
    """Format seconds into HHhMMmSSs tag string."""
    s = max(0, int(seconds))
    return f"{s // 3600:02d}h{s % 3600 // 60:02d}m{s % 60:02d}s"


def part_stem(src: SourceInfo, opts: JobOptions, part: Part, total: int, clip: dict | None = None) -> str:
    tag = format_duration_tag

    resolved_q = resolve_format(src.formats, getattr(opts, "quality", QUALITY_BEST)) if getattr(src, "formats", None) else None
    q_tag = resolved_q.tag if resolved_q else ""

    stream_date = src.date or ""
    year, month, day = date_components(src.date)
    download_date = datetime.now().strftime("%Y-%m-%d")
    game = dominant_game(getattr(src, "segments", None), part.start, part.end)
    duration_str = tag(max(0.0, part.end - part.start))

    data = _SafeDict(
        streamer=src.uploader or "vod",
        stream_date=stream_date,
        download_date=download_date,
        date=stream_date,
        year=year,
        month=month,
        day=day,
        game=game,
        category=game,
        id=src.twitch_vod_id or src.id,
        title=src.title,
        duration=duration_str,
        n=part.index,
        total=total,
        start=tag(part.start),
        end=tag(part.end),
        quality=q_tag,
        resolution=q_tag,
    )
    template = opts.name_template
    if clip:  # single clip download: the clip's own name instead of the stream's
        data.update(
            clip_title=clip.get("title") or "Clip",
            creator=clip.get("creator_name", ""),
            views=clip.get("view_count", 0),
            clip_id=clip.get("id", ""),
            clip_duration=round(clip.get("duration", 0) or 0),
        )
        template = opts.clip_name_template
    try:
        name = template.format_map(data)
    except (ValueError, IndexError):
        name = data["clip_title"] if clip else (f"{data['id']}" if total == 1 else f"{data['id']} - part{part.index}")
    name = safe_name(name)
    if clip:
        name = name[:150].strip(" .")
        return name or f"clip {data['clip_id']}".strip()

    if total == 1:
        cleaned = re.sub(r"(?i)[\s\-_]+part\s*1\b", "", name)
        cleaned = re.sub(r"(?i)\bpart\s*1[\s\-_]*", "", cleaned)
        cleaned = re.sub(r"(?i)[\s\-_]+1\s*of\s*1\b", "", cleaned)
        cleaned = re.sub(r"(?i)\b1\s*of\s*1[\s\-_]*", "", cleaned)
        cleaned = safe_name(cleaned)
        if cleaned:
            name = cleaned

    return name or f"part{part.index}"


def stream_dir(src: SourceInfo, opts: JobOptions) -> Path:
    """Where the files of this VOD go: out_dir/<streamer>/<stream>/ (or out_dir if disabled)."""
    base = Path(opts.out_dir)
    if not opts.subfolders:
        return base

    resolved_q = resolve_format(src.formats, getattr(opts, "quality", QUALITY_BEST)) if getattr(src, "formats", None) else None
    q_tag = resolved_q.tag if resolved_q else ""

    stream_date = src.date or ""
    year, month, day = date_components(src.date)
    download_date = datetime.now().strftime("%Y-%m-%d")
    duration_val = getattr(src, "duration", 0.0) or 0.0
    game = dominant_game(getattr(src, "segments", None), 0.0, duration_val)
    duration_str = format_duration_tag(duration_val)

    data = _SafeDict(
        streamer=src.uploader or "vod",
        stream_date=stream_date,
        download_date=download_date,
        date=stream_date,
        year=year,
        month=month,
        day=day,
        game=game,
        category=game,
        id=src.twitch_vod_id or src.id,
        title=src.title,
        duration=duration_str,
        quality=q_tag,
        resolution=q_tag,
    )
    try:
        stream = opts.folder_template.format_map(data)
    except (ValueError, IndexError):
        stream = f"{data['date']} - {data['id']}"
    stream = safe_name(stream)[:100].strip(" .") or str(data["id"])
    streamer = safe_name(src.uploader)[:60].strip(" .") or "vod"
    return base / streamer / stream


def finalize_part(
    ctx: Ctx,
    src_file: Path,
    dest_stem: Path,
    container: str,
    chapters: list[Chapter],
    tags: dict[str, str],
    total: float,
    copy_instead_of_move: bool = False,
) -> Path:
    """Put the part in its final place: add chapters / remux / rename."""
    dest = unique_path(dest_stem.parent / f"{dest_stem.name}.{container}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if chapters:
        meta = src_file.with_suffix(".ffmeta")
        meta.write_text(ffmetadata(chapters, tags), encoding="utf-8")
        run_ffmpeg(
            ctx,
            ["-i", str(src_file), "-i", str(meta), "-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy",
             *mp4_flags(container), str(dest)],
            total=total,
        )
    elif src_file.suffix.lower() == "." + container:
        ts = mp4_movie_timescale(src_file) if container.lower() == "mp4" else None
        if ts is not None and ts != MP4_MOVIE_TIMESCALE:
            # e.g. a file made by yt-dlp's own ffmpeg: rewrite the header only (stream copy), then drop the source
            run_ffmpeg(ctx, ["-i", str(src_file), "-map", "0", "-c", "copy", *mp4_flags(container), str(dest)], total=total)
            if not copy_instead_of_move:
                src_file.unlink(missing_ok=True)
        else:
            (shutil.copy2 if copy_instead_of_move else shutil.move)(str(src_file), str(dest))
    else:
        run_ffmpeg(ctx, ["-i", str(src_file), "-map", "0", "-c", "copy", *mp4_flags(container), str(dest)], total=total)
    return dest


def finalize_audio_part(
    ctx: Ctx,
    src_file: Path,
    dest_stem: Path,
    container: str,
    chapters: list[Chapter],
    tags: dict[str, str],
    total: float,
    copy_instead_of_move: bool = False,
) -> Path:
    """Put an audio-only part in its final place as .m4a (copy) or .mp3 (convert)."""
    dest = unique_path(dest_stem.parent / f"{dest_stem.name}.{container}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not chapters and container == "m4a" and src_file.suffix.lower() == ".m4a":
        (shutil.copy2 if copy_instead_of_move else shutil.move)(str(src_file), str(dest))
        return dest
    args = ["-i", str(src_file)]
    if chapters:
        meta = src_file.with_suffix(".ffmeta")
        meta.write_text(ffmetadata(chapters, tags), encoding="utf-8")
        args += ["-i", str(meta), "-map_metadata", "1", "-map_chapters", "1"]
    args += ["-map", "0:a:0", *audio_codec_args(container)]
    if container == "mp3":
        args += ["-id3v2_version", "3"]
    run_ffmpeg(ctx, args + [str(dest)], total=total)
    return dest


def _write_sidecar(dest: Path, chapters: list[Chapter]) -> None:
    data = [
        {
            "start": round(ch.start, 2),
            "end": round(ch.end, 2),
            "title": ch.title,
            "clips": [
                {
                    "id": c.get("id"),
                    "title": c.get("title"),
                    "creator": c.get("creator_name"),
                    "views": c.get("view_count"),
                    "duration": c.get("duration"),
                    "url": c.get("url"),
                }
                for c in ch.clips
            ],
        }
        for ch in chapters
    ]
    dest.with_suffix(".clips.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Chat download (TwitchDownloaderCLI, only used when "Download chat" is on)
# --------------------------------------------------------------------------- #
CHAT_FORMATS = ("json", "txt", "html")
_TDCLI_EXE = "TwitchDownloaderCLI" + EXE


def tdcli_dir() -> Path:
    return TOOLS_DIR / "TwitchDownloaderCLI"


def find_tdcli() -> str | None:
    """Our own copy first, then a TwitchDownloaderCLI next to the script / in bin / on PATH."""
    cand = tdcli_dir() / _TDCLI_EXE
    if cand.is_file():
        return str(cand)
    return find_tool("TwitchDownloaderCLI")


def _is_managed_tdcli(path: str | Path) -> bool:
    try:
        return Path(path).resolve().parent == tdcli_dir().resolve()
    except OSError:
        return False


def pick_tdcli_asset(names: list[str], plat: str | None = None, machine: str | None = None) -> str | None:
    """Which file of a TwitchDownloader release is the CLI for this system (matched by keywords)."""
    plat = plat or sys.platform
    arm = (machine or platform.machine()).lower().startswith(("arm", "aarch"))
    for name in names:
        n = name.lower()
        if not (n.startswith("twitchdownloadercli") and n.endswith(".zip")):
            continue
        if plat == "win32":
            ok = "windows" in n and "x64" in n  # the x64 build also runs on Windows on ARM
        elif plat == "darwin":
            ok = "mac" in n and (("arm" in n) if arm else ("x64" in n and "arm" not in n))
        else:
            ok = "linux" in n and "alpine" not in n and (("arm" in n) if arm else ("x64" in n and "arm" not in n))
        if ok:
            return name
    return None


def _tdcli_release(tag: str) -> dict:
    for t in (tag, "v" + tag):
        try:
            r = _http_get(f"https://api.github.com/repos/{TDCLI_REPO}/releases/tags/{t}")
        except requests.RequestException as e:
            raise EngineError(f"Could not reach GitHub to download TwitchDownloaderCLI:\n{e}") from e
        if r.status_code == 404:
            continue
        if not r.ok:
            raise EngineError(f"GitHub refused the TwitchDownloaderCLI lookup (HTTP {r.status_code}). Try again in a few minutes.")
        return r.json()
    raise EngineError(f"TwitchDownloaderCLI {tag} was not found on GitHub.")


def _extract_tdcli(archive: Path, dest: Path) -> None:
    """Unzip the CLI and the files next to it into `dest`, whatever folder layout the zip has."""
    with zipfile.ZipFile(archive) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        main = next((i for i in files if PurePosixPath(i.filename.replace("\\", "/")).name == _TDCLI_EXE), None)
        if main is None:
            raise EngineError("The TwitchDownloaderCLI download did not contain the program.")
        root = PurePosixPath(main.filename.replace("\\", "/")).parent
        dest.mkdir(parents=True)
        base = dest.resolve()
        for info in files:
            try:
                rel = PurePosixPath(info.filename.replace("\\", "/")).relative_to(root)
            except ValueError:
                continue  # outside the folder that holds the program
            target = (dest / rel).resolve()
            if base not in target.parents:
                continue  # never write outside the destination
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    (dest / _TDCLI_EXE).chmod(0o755)


def install_tdcli(ctx: "Ctx", tag: str = TDCLI_VERSION) -> None:
    """Download the pinned TwitchDownloaderCLI release from GitHub into the tools folder."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    ctx.log(f"Downloading TwitchDownloaderCLI {tag} (needed for chat, one-time download)…")
    ctx.stage(0.0, 1.0, f"Downloading TwitchDownloaderCLI {tag}")
    release = _tdcli_release(tag)
    assets = [a for a in release.get("assets", []) if isinstance(a, dict) and a.get("name")]
    name = pick_tdcli_asset([a["name"] for a in assets])
    manual = (f"You can download it yourself from https://github.com/{TDCLI_REPO}/releases "
              f"and put the program in:\n{tdcli_dir()}")
    asset = next((a for a in assets if a["name"] == name), None)
    if not asset or not asset.get("browser_download_url"):
        raise EngineError(f"There is no TwitchDownloaderCLI build for this system in release {tag}.\n{manual}")
    archive = TOOLS_DIR / "TwitchDownloaderCLI.zip.download"
    staging = TOOLS_DIR / "TwitchDownloaderCLI.new"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        _download_with_retry(ctx, asset["browser_download_url"], archive)
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:"):
            if _sha256(archive) != digest[len("sha256:"):].lower():
                raise EngineError("Checksum mismatch for TwitchDownloaderCLI: the download is corrupted, try again.")
        else:
            ctx.log("GitHub published no checksum for TwitchDownloaderCLI, so it was not verified.")
        try:
            _extract_tdcli(archive, staging)
        except zipfile.BadZipFile as e:
            raise EngineError("The TwitchDownloaderCLI download is not a valid zip file, try again.") from e
        try:
            if tdcli_dir().exists():
                shutil.rmtree(tdcli_dir())
            os.replace(staging, tdcli_dir())
        except OSError as e:
            raise EngineError("TwitchDownloaderCLI is in use right now. Wait for running jobs to finish and try again.") from e
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
    _write_version("tdcli", tag)
    ctx.log(f"TwitchDownloaderCLI {tag} installed.")


def ensure_tdcli(ctx: "Ctx") -> str:
    """Path of TwitchDownloaderCLI: a copy the user provided as it is, ours only if it is the pinned version."""
    path = find_tdcli()
    if path and (not _is_managed_tdcli(path) or _read_versions().get("tdcli") == TDCLI_VERSION):
        return path
    install_tdcli(ctx)
    path = find_tdcli()
    if not path:
        raise EngineError("TwitchDownloaderCLI was installed but could not be found.")
    return path


_TDCLI_STATUS = re.compile(r"^\[STATUS\]\s*-\s*(?P<phase>.*?)\s*(?:(?P<pct>\d+)%)?\s*(?:\[\d+/\d+\])?\s*$")
_CHAT_PHASES = (("downloading", 0.0, 0.85), ("backfilling", 0.85, 0.98), ("writing", 0.98, 1.0))


def parse_tdcli_status(line: str) -> tuple[str, float | None] | None:
    """'[STATUS] - Downloading 16%' -> ('Downloading', 0.136). None if the line is not a status line."""
    m = _TDCLI_STATUS.match(line.strip())
    if not m:
        return None
    phase, pct = m.group("phase"), m.group("pct")
    for key, lo, hi in _CHAT_PHASES:
        if phase.lower().startswith(key):
            return phase, lo + (hi - lo) * (min(int(pct), 100) / 100 if pct else 0.0)
    return phase, None


def tdcli_error(lines: list[str]) -> str:
    """The useful part of what TwitchDownloaderCLI printed when it failed (it can dump a whole stack trace)."""
    for ln in lines:
        if "--->" in ln and "Exception:" in ln:
            return ln.split("Exception:", 1)[1].strip()
    for ln in lines:
        if ln.startswith("[ERROR]"):
            return ln[len("[ERROR]"):].lstrip(" -").strip()
    for ln in lines:
        if ln.startswith("Unhandled exception"):
            return ln.split(":", 1)[-1].strip()
    return " | ".join(lines[-3:]) or "no details"


def chat_command(tdcli: str, vod_id: str, start: float, end: float, out: Path, embed: bool, cache_dir: Path) -> list[str]:
    """Chat of [start, end] (VOD time, widened to whole seconds: the chat API only has whole seconds)."""
    cmd = [
        tdcli, "chatdownload", "--id", vod_id,
        "-b", f"{math.floor(start)}s", "-e", f"{math.ceil(end)}s",
        "-o", str(out),
        "--collision", "Overwrite",  # never wait for an answer: nobody can type into the pipe
        "--banner=false", "--log-level", "Status,Warning,Error",
        "--temp-path", str(cache_dir),
    ]
    if embed:
        cmd.append("--embed-images")
    return cmd


def _run_tdcli(ctx: "Ctx", cmd: list[str], dest: Path, what: str,
               parse: Callable[[str], tuple[str, float | None] | None], log_steps: bool = False) -> list[str]:
    """
    Run one TwitchDownloaderCLI command that writes `dest` and send its progress to the bar. Never leaves a
    half-written file behind. Returns the [WARNING] lines the program printed (a render says there what it missed).
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=_tool_env(),
            creationflags=_NO_WINDOW, start_new_session=sys.platform != "win32",
        )
    except OSError as e:
        raise EngineError(f"Could not run TwitchDownloaderCLI:\n{e}") from e
    ctx.proc = proc
    tail: list[str] = []
    warnings: list[str] = []
    ok = False
    try:
        assert proc.stdout is not None
        for line in proc.stdout:  # text mode: the program's «\r» progress updates arrive as separate lines
            line = line.strip()
            if not line:
                continue
            status = parse(line)
            if status:
                ctx.report(status[1], status[0])
                if log_steps and status[1] is not None:
                    ctx.log_progress(status[1], status[0].partition(" · ")[2])
                continue
            if len(tail) < 60:
                tail.append(line)
            if line.startswith("[WARNING]") and len(warnings) < 20:
                warnings.append(line)
        proc.wait()
        ctx.check_cancel()
        if proc.returncode != 0:
            raise EngineError(f"{what} failed: " + tdcli_error(tail))
        if not dest.is_file() or dest.stat().st_size == 0:
            raise EngineError(f"{what} finished but the file is empty.")
        ok = True
        return warnings
    finally:
        ctx.proc = None
        if not ok:
            try:  # a cancelled / failed run leaves an empty or half-written file behind
                dest.unlink(missing_ok=True)
            except OSError:
                pass


def download_chat(ctx: "Ctx", tdcli: str, vod_id: str, start: float, end: float, dest: Path,
                  embed: bool, cache_dir: Path) -> Path:
    """Run TwitchDownloaderCLI for one stretch of a VOD. Never leaves a half-written file behind."""
    ctx.check_cancel()
    dest = unique_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run_tdcli(ctx, chat_command(tdcli, vod_id, start, end, dest, embed, cache_dir), dest, "Chat download",
               parse_tdcli_status)
    return dest


# --------------------------------------------------------------------------- #
# Chat overlay: the chat as a video for the editor (TwitchDownloaderCLI chatrender)
# --------------------------------------------------------------------------- #
CHAT_RENDER_MODES = ("transparent", "prores", "compact")
CHAT_RENDER_LOOKS = ("outline", "panel")
CHAT_RENDER_EXT = {"transparent": ".mov", "prores": ".mov", "compact": ".mp4"}
CHAT_RENDER_LABELS = {
    "transparent": "transparent, Animation",
    "prores": "transparent, ProRes 4444",
    "compact": "black background, H.264",
}
_TDCLI_RENDER_STATUS = re.compile(
    r"^\[STATUS\]\s*-\s*(?P<phase>[A-Za-z][A-Za-z ]*?)\s*(?:(?P<pct>\d+)%)?\s*"
    r"(?:\([^|()]*Elapsed\s*\|\s*(?P<left>[^()]*?)\s*Remaining\))?\s*(?:\[\d+/\d+\])?\s*$"
)
_TDCLI_DURATION = re.compile(r"(\d+)h(\d+)m(\d+)s")


def parse_render_status(line: str) -> tuple[str, float | None] | None:
    """
    '[STATUS] - Rendering Video 12% (0h0m1s Elapsed | 0h1m8s Remaining)' -> ('Rendering Video · 0:01:08 left', 0.12).
    Phases without a percentage («Fetching Images [1/2]») give None as the fraction. None if it is not a status line.
    """
    m = _TDCLI_RENDER_STATUS.match(line.strip())
    if not m:
        return None
    phase, pct = m.group("phase"), m.group("pct")
    frac = min(int(pct), 100) / 100 if pct else None
    label = phase
    left = _TDCLI_DURATION.fullmatch((m.group("left") or "").strip())
    if left and pct and int(pct) >= 1:  # at 0% the program's estimate is nonsense
        label += f" · {int(left[1])}:{int(left[2]):02d}:{int(left[3]):02d} left"
    return label, frac


def chat_render_size(width: int, height: int, video_height: int | None) -> tuple[int, int]:
    """(width, height) of the overlay in pixels: even numbers (H.264 needs them), height 0 = the video's height."""
    w = min(max(int(width or 0) or 400, 100), 3840)
    h = min(max(int(height or 0) or int(video_height or 0) or 1080, 100), 4320)
    return w - w % 2, h - h % 2


def chat_render_fps(option: int, video_fps: float | None) -> int:
    """Frame rate of the overlay: the one asked for, or (0) 60 for a 60 fps video and 30 for anything else."""
    if option and option > 0:
        return min(int(option), 120)
    return 60 if video_fps and video_fps >= 45 else 30


def chat_render_output_args(mode: str, lead: float = 0.0) -> str:
    """
    The ffmpeg output arguments of the render. `lead` seconds are cut off the start: the chat file begins at a whole
    second and the part may begin a bit later, so this keeps the overlay lined up with the video. (Never use ffmpeg's
    -t here: it closes the pipe early and TwitchDownloaderCLI crashes. The end is set by the chat file instead.)
    """
    skip = f"-ss {lead:.3f} " if lead >= 0.005 else ""
    if mode == "prores":
        enc = "-c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le -vendor apl0"
    elif mode == "compact":
        enc = "-c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p -movflags +faststart"
    else:  # QuickTime Animation: lossless, keeps the alpha, and a chat that only changes a few times a second is tiny
        enc = "-c:v qtrle -pix_fmt argb"
    return f'{skip}{enc} "{{save_path}}"'


def chat_render_command(tdcli: str, chat_json: Path, out: Path, *, mode: str, look: str, width: int, height: int,
                        font_size: int, fps: int, smooth: bool, ffmpeg: str | None, cache_dir: Path,
                        lead: float = 0.0) -> list[str]:
    """Render the chat file `chat_json` (the stretch it covers, from its own start) to the video `out`."""
    solid = mode == "compact"  # no alpha channel: black, and the editor's Screen blend mode makes it see-through
    panel = look == "panel" and not solid
    cmd = [
        tdcli, "chatrender", "-i", str(chat_json), "-o", str(out),
        "--chat-width", str(width), "--chat-height", str(height),
        "--font-size", str(min(max(int(font_size or 0) or 18, 6), 96)),
        "--framerate", str(fps), "--update-rate", "0" if smooth else "0.2",
        "--background-color", "#000000" if solid else ("#B3000000" if panel else "#00000000"),
        "--collision", "Overwrite",  # never wait for an answer: nobody can type into the pipe
        "--banner=false", "--log-level", "Status,Warning,Error",
        "--temp-path", str(cache_dir),
    ]
    if not solid and not panel:
        cmd.append("--outline")  # nothing behind the text: the outline keeps it readable over any picture
    if ffmpeg:
        cmd += ["--ffmpeg-path", ffmpeg]
    cmd.append("--output-args=" + chat_render_output_args(mode, lead))  # «=»: the value starts with «-»
    return cmd


def render_chat(ctx: "Ctx", tdcli: str, chat_json: Path, dest: Path, *, mode: str, look: str, width: int,
                height: int, font_size: int, fps: int, smooth: bool, cache_dir: Path, lead: float = 0.0) -> Path:
    """Render one chat file as an overlay video. Never leaves a half-written file behind."""
    ctx.check_cancel()
    dest = unique_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cmd = chat_render_command(tdcli, chat_json, dest, mode=mode, look=look, width=width, height=height,
                              font_size=font_size, fps=fps, smooth=smooth, ffmpeg=find_tool("ffmpeg"),
                              cache_dir=cache_dir, lead=lead)
    for w in _run_tdcli(ctx, cmd, dest, "Chat render", parse_render_status, log_steps=True)[:3]:
        ctx.log("Warning: chat overlay: " + w[len("[WARNING]"):].lstrip(" -").strip())
    return dest


def chat_overlay_settings(opts: "JobOptions", probe: tuple[float, int, int] | None) -> tuple[str, str, int, int, int]:
    """(mode, look, width, height, fps) of an overlay: what the options say, and the video's size and rate where they say «like the video»."""
    mode = opts.chat_render_mode if opts.chat_render_mode in CHAT_RENDER_MODES else "transparent"
    look = opts.chat_render_look if opts.chat_render_look in CHAT_RENDER_LOOKS else "outline"
    width, height = chat_render_size(opts.chat_render_width, opts.chat_render_height, probe[2] if probe else None)
    fps = chat_render_fps(opts.chat_render_fps, probe[0] if probe else None)
    return mode, look, width, height, fps


# --------------------------------------------------------------------------- #
# Overlay from a chat file that is already on disk («name.chat.json»)
# --------------------------------------------------------------------------- #
PART_VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".ts", ".m4v", ".webm")


@dataclass
class ChatFileInfo:
    """What a TwitchDownloader .json chat says about itself (all of it is read from the file)."""
    vod_id: str
    streamer: str
    title: str
    start: float  # the stretch of the VOD the file covers, in seconds from the start of the VOD
    end: float
    messages: int
    embedded: bool  # emotes and badges are inside the file (it can be drawn offline)


def read_chat_info(path: Path) -> ChatFileInfo:
    """Read a «.chat.json» saved by TwitchDownloader. Raises EngineError, saying why, if it is not one."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise EngineError(f"Could not read the chat file: {e}") from e
    comments = data.get("comments") if isinstance(data, dict) else None
    video = data.get("video") if isinstance(data, dict) else None
    if not isinstance(comments, list) or not isinstance(video, dict):
        raise EngineError("This is not a chat file saved by TwitchDownloader (a «.chat.json»).")
    if not comments:
        raise EngineError("This chat file has no messages, so there is nothing to draw.")

    def seconds(value, fallback: float) -> float:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else fallback

    def offset(c) -> float:
        return seconds(c.get("content_offset_seconds") if isinstance(c, dict) else None, 0.0)

    streamer = data.get("streamer") if isinstance(data.get("streamer"), dict) else {}
    embedded = data.get("embeddedData")
    return ChatFileInfo(
        vod_id=str(video.get("id") or ""),
        streamer=str(streamer.get("name") or ""),
        title=str(video.get("title") or ""),
        start=seconds(video.get("start"), offset(comments[0])),
        end=seconds(video.get("end"), offset(comments[-1])),
        messages=len(comments),
        embedded=isinstance(embedded, dict) and any(isinstance(v, list) and v for v in embedded.values()),
    )


def chat_base_name(chat_json: Path) -> str:
    """«Streamer - part1.chat.json» → «Streamer - part1»: the name the part's other files share."""
    name = chat_json.name
    for ending in (".chat.json", ".json"):
        if name.lower().endswith(ending):
            return name[: -len(ending)]
    return chat_json.stem


def find_part_video(chat_json: Path) -> Path | None:
    """The video the chat belongs to («name.mp4» next to «name.chat.json»), if it is there."""
    base = chat_base_name(chat_json)
    for ext in PART_VIDEO_EXTS:
        candidate = chat_json.with_name(base + ext)
        if candidate.is_file():
            return candidate
    return None


def chat_lead_from_markers(chat_json: Path, info: ChatFileInfo) -> float:
    """
    Seconds the overlay must be trimmed at its start to line up with the part: the fraction of the part's start,
    read from «name.markers.json» next to the chat when it is there. The chat file itself only has whole seconds.
    Only used when that file is really about this chat (same whole second); 0 otherwise.
    """
    path = chat_json.with_name(chat_base_name(chat_json) + ".markers.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("format") != "luckytwitch-markers":
            return 0.0
        part_start = float(data["part"]["start"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 0.0
    if not math.isfinite(part_start) or math.floor(part_start) != math.floor(info.start):
        return 0.0
    return part_start - math.floor(part_start)


def existing_chat_overlay_path(chat_json: Path, mode: str) -> Path:
    """Where the overlay of «name.chat.json» goes: «name.chat-overlay.mov» (or .mp4), next to it."""
    return chat_json.with_name(chat_base_name(chat_json) + ".chat-overlay" + CHAT_RENDER_EXT.get(mode, ".mov"))


def render_existing_chat(ctx: "Ctx", tdcli: str, chat_json: Path, opts: "JobOptions", cache_dir: Path) -> Path:
    """
    Draw the overlay of a chat file that is already on disk, with the overlay settings of `opts`. Nothing is
    downloaded and neither the chat nor the video is touched. Size and frame rate follow «name.mp4» (or .mkv…)
    next to the chat when it exists; the fraction of the part's start comes from «name.markers.json» when it exists.
    """
    info = read_chat_info(chat_json)
    video = find_part_video(chat_json)
    mode, look, width, height, fps = chat_overlay_settings(opts, probe_video(video) if video else None)
    lead = chat_lead_from_markers(chat_json, info)
    out = render_chat(
        ctx, tdcli, chat_json, existing_chat_overlay_path(chat_json, mode), mode=mode, look=look, width=width,
        height=height, font_size=opts.chat_render_font_size, fps=fps, smooth=opts.chat_render_smooth,
        cache_dir=cache_dir, lead=lead)
    ctx.log(f"✔ {out.name}  ({width}x{height}, {fps} fps, {CHAT_RENDER_LABELS[mode]}; "
            + ("starts together with the part" if lead or video else "starts at the first second of the chat")
            + ")")
    return out


def describe_chat_overlay(chat_json: Path, opts: "JobOptions") -> str:
    """What drawing the overlay of this chat file will do, in plain words (to confirm before the long render)."""
    info = read_chat_info(chat_json)
    video = find_part_video(chat_json)
    mode, _look, width, height, fps = chat_overlay_settings(opts, probe_video(video) if video else None)
    base = chat_base_name(chat_json)
    lines = [
        " · ".join(x for x in (info.streamer, f"VOD {info.vod_id}" if info.vod_id else "") if x) or chat_json.name,
        f"Covers {fmt_hms(info.start)} to {fmt_hms(info.end)} of the VOD · {info.messages:,} messages",
        "",
        f"Video next to it: {video.name}" if video else "No video next to it, so the size and frame rate come from Options.",
        f"Overlay: {width}x{height}, {fps} fps, {CHAT_RENDER_LABELS[mode]}",
        f"File: {existing_chat_overlay_path(chat_json, mode).name}",
    ]
    if chat_lead_from_markers(chat_json, info) > 0:
        lines.append(f"Lined up to the fraction of a second with {base}.markers.json.")
    elif not chat_json.with_name(base + ".markers.json").is_file():
        lines.append(f"No {base}.markers.json: lined up to the whole second (up to 1 s ahead of the video).")
    lines.append("Emotes and badges are inside the file." if info.embedded
                 else "Emotes and badges are fetched from the internet while it draws.")
    return "\n".join(lines)


def chat_files_for_part(ctx: "Ctx", tool: str, src: "SourceInfo", opts: "JobOptions", part: "Part", total_parts: int,
                        dest: Path, real_start: float, real_end: float, workdir: Path) -> None:
    """
    The chat files of one finished part, next to it: the saved chat («.chat.json / .txt / .html») and / or the overlay
    video («.chat-overlay.mov / .mp4»). A failure here is only logged: the video itself is fine.
    """
    chat_fmt = opts.chat_format if opts.chat_format in CHAT_FORMATS else "json"
    vod_id = src.twitch_vod_id or ""
    cache = workdir / "chat_cache"
    lo, hi = ctx.span()

    def stage(a: float, b: float, label: str) -> None:  # a slice of this part's share of the progress bar
        ctx.stage(lo + (hi - lo) * a, lo + (hi - lo) * b, label)

    chat_json: Path | None = None  # the file the overlay is drawn from
    temp_json = False
    chat_failed = False
    try:
        if opts.chat:
            try:
                label = f"Chat for part {part.index}/{total_parts}"
                if opts.chat_render:
                    stage(0.0, 0.1, label)
                else:
                    ctx.relabel(label)
                chat_file = download_chat(
                    ctx, tool, vod_id, real_start, real_end,
                    dest.with_suffix(f".chat.{chat_fmt}"), opts.chat_embed, cache)
                ctx.log(f"✔ {chat_file.name}  (chat from {fmt_hms(real_start)} to {fmt_hms(real_end)} of the VOD)")
                if chat_fmt == "json":
                    chat_json = chat_file
            except Cancelled:
                raise
            except EngineError as e:
                chat_failed = True
                ctx.log(f"Chat for part {part.index} failed (the video is fine): {e}")
        if not opts.chat_render:
            return
        if chat_failed:
            ctx.log(f"Chat overlay for part {part.index} skipped: the chat could not be downloaded.")
            return
        try:
            if chat_json is None:  # the saved chat is not a .json (or not wanted): the overlay needs its own copy
                stage(0.0, 0.1, f"Chat for the overlay of part {part.index}/{total_parts}")
                chat_json = download_chat(ctx, tool, vod_id, real_start, real_end,
                                          cache / f"part{part.index}.chat.json", False, cache)
                temp_json = True
            mode, look, width, height, fps = chat_overlay_settings(opts, probe_video(dest))
            lead = max(0.0, real_start - math.floor(real_start))  # the chat file starts at a whole second
            stage(0.1, 1.0, f"Chat overlay for part {part.index}/{total_parts}")
            out = render_chat(
                ctx, tool, chat_json, dest.with_suffix(".chat-overlay" + CHAT_RENDER_EXT[mode]), mode=mode, look=look,
                width=width, height=height, font_size=opts.chat_render_font_size, fps=fps,
                smooth=opts.chat_render_smooth, cache_dir=cache, lead=lead)
            ctx.log(f"✔ {out.name}  ({width}x{height}, {fps} fps, {CHAT_RENDER_LABELS[mode]}; "
                    f"starts together with the part)")
        except Cancelled:
            raise
        except EngineError as e:
            ctx.log(f"Chat overlay for part {part.index} failed (the video is fine): {e}")
    finally:
        if temp_json and chat_json is not None:
            chat_json.unlink(missing_ok=True)


def split_copy(
    ctx: Ctx, full: Path, parts: list[Part], duration: float, container: str, workdir: Path, audio_only: bool = False
) -> dict[int, tuple[Path, float, float]]:
    """
    Single ffmpeg pass (stream copy) that cuts the full file at every boundary.
    Returns {part.index: (segment_file, real_start, real_end)} in VOD time.
    (ffmpeg normalises the input timeline to start at 0, so the times are VOD time
    even if the downloaded file's own timestamps start somewhere else.)
    Segments that are not part of any wanted part (gaps) are deleted.
    """
    boundaries = sorted({0.0} | {p.start for p in parts} | {p.end for p in parts if p.end < duration - 0.5})
    inner = boundaries[1:]

    if not inner:  # whole video is a single part
        return {parts[0].index: (full, 0.0, duration)}

    seg_dir = workdir / "segments"
    if seg_dir.exists():
        shutil.rmtree(seg_dir)
    seg_dir.mkdir(parents=True)
    listing = seg_dir / "list.csv"
    times = ",".join(f"{t:.3f}" for t in inner)
    map_args = ["-map", "0:a:0"] if audio_only else ["-map", "0:v:0", "-map", "0:a?"]
    run_ffmpeg(
        ctx,
        [
            "-i", str(full),
            *map_args,
            "-c", "copy",
            "-f", "segment",
            *(["-segment_format_options", f"movie_timescale={MP4_MOVIE_TIMESCALE}"] if mp4_flags(container) else []),
            *(["-segment_format", "mp4"] if audio_only else []),
            "-segment_times", times,
            "-segment_list", str(listing),
            "-segment_list_type", "csv",
            "-reset_timestamps", "1",
            str(seg_dir / f"seg_%03d.{container}"),
        ],
        total=duration,
    )
    rows = [r for r in csv.reader(listing.read_text(encoding="utf-8").splitlines()) if len(r) >= 3]
    result: dict[int, tuple[Path, float, float]] = {}
    for p in parts:
        i = boundaries.index(p.start)
        if i >= len(rows):
            raise EngineError(f"Cut point {fmt_hms(p.start)} is past the end of the downloaded video.")
        name, s, e = rows[i][0], float(rows[i][1]), float(rows[i][2])
        result[p.index] = (seg_dir / Path(name).name, s, e)
    return result


def cut_exact(ctx: Ctx, full: Path, part: Part, container: str, workdir: Path, offset: float | None = None) -> Path:
    """
    Frame-exact cut (re-encodes video).
    `offset`: where the part starts inside `full` (default: part.start, i.e. `full` is the whole VOD).
    """
    out = workdir / f"exact_{part.index}.{container}"
    run_ffmpeg(
        ctx,
        [
            "-ss", f"{part.start if offset is None else offset:.3f}", "-i", str(full), "-t", f"{part.duration:.3f}",
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            *mp4_flags(container),
            str(out),
        ],
        total=part.duration,
    )
    return out


# --------------------------------------------------------------------------- #
# Running a job
# --------------------------------------------------------------------------- #
def _load_chapters(ctx: Ctx, job: Job) -> list[Chapter]:
    if not (job.opts.chapters or job.opts.premiere_xml or job.opts.premiere_plugin):
        return []
    clips = job.clips
    if clips is None:
        if not job.source.twitch_vod_id:
            ctx.log("Chapters: not a Twitch VOD URL, skipping.")
            return []
        if job.client is None:
            ctx.log("Chapters: no Twitch API credentials, skipping.")
            return []
        ctx.log("Fetching clips for chapters…")
        clips = fetch_clips_for_vod(job.client, job.source.twitch_vod_id)
    chapters = make_chapters(clips, job.opts.clip_filter)
    ctx.log(f"Chapters: {len(chapters)} (from {len(clips)} clips found)")
    return chapters


def _load_muted(ctx: Ctx, job: Job) -> list[Chapter]:
    """The stretches Twitch silenced, as chapters, when the .markers.json should carry them (else [])."""
    src, opts = job.source, job.opts
    if not (opts.muted_markers and opts.premiere_plugin) or job.single_clip:
        return []
    ranges = src.muted  # normally read at «Get info»
    if ranges is None and src.twitch_vod_id:  # it could not be read then (or the VOD came from elsewhere): try once more
        try:
            ranges = muted_from_playlist_url(get_playlist_url(ctx, src.url), src.duration)
        except Cancelled:
            raise
        except EngineError:
            ranges = None
    if ranges is None:
        ctx.log("Muted audio: could not read which parts Twitch silenced, so no muted markers this time.")
        return []
    if ranges:
        ctx.log(f"Muted audio: {len(ranges)} stretch(es), {fmt_hms(sum(e - s for s, e in ranges))} in total")
    return muted_chapters(ranges)


def run_job(job: Job, ctx: Ctx) -> list[Path]:
    src, opts = job.source, job.opts
    if not find_tool("ffmpeg"):
        raise EngineError("ffmpeg was not found. Install it and add it to PATH.")

    plan = make_plan(opts.cut_text, src.duration, opts.strategy, opts.full_threshold)
    ctx.log(
        f"{len(plan.parts)} part(s), coverage {plan.coverage * 100:.0f}% → "
        + ("download full VOD, then split" if plan.strategy == "full" else "download only the parts")
    )
    fmt = resolve_format(src.formats, opts.quality)
    fmt_kw = {"format_id": fmt.format_id} if fmt else {}
    if fmt:
        ctx.log(describe_quality(fmt, opts.quality))
    elif (opts.quality or "").strip().lower() not in ("", QUALITY_BEST):
        ctx.log("Quality: this video offers no choice, using the best one.")

    audio_only = bool(fmt and fmt.audio_only)
    dl_kw = {**fmt_kw, **({"audio_only": True} if audio_only else {})}
    out_container = audio_out_container(opts) if audio_only else opts.container
    if audio_only:
        opts, skipped = audio_only_options(opts)
        job = replace(job, opts=opts)  # _load_chapters reads job.opts
        if skipped:
            ctx.log("Audio only: skipped " + ", ".join(skipped) + " (they need a video track).")
    chapters_all = _load_chapters(ctx, job)
    games_all = game_chapters(src.segments) if opts.game_markers and not job.single_clip else []
    muted_all = _load_muted(ctx, job)
    chat_tool: str | None = None
    if (opts.chat or opts.chat_render) and not job.single_clip:
        what = "Chat download" if opts.chat else "Chat overlay"
        if not src.twitch_vod_id:
            ctx.log(f"{what} skipped: it only works for Twitch VODs.")
        else:
            try:
                chat_tool = ensure_tdcli(ctx)
            except Cancelled:
                raise
            except EngineError as e:
                ctx.log(f"{what} skipped (the video is still downloaded): {e}")

    out_dir = Path(opts.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final_dir = stream_dir(src, opts)
    workdir = out_dir / (
        f".luckytwitch_{src.twitch_vod_id or src.id}"
        + (f"_{fmt.format_id}" if fmt else "")
    )
    tags = {
        "title": src.title,
        "artist": src.uploader,
        "comment": src.url,
        "date": src.date,
    }
    total_parts = len(plan.parts)
    results: list[Path] = []

    def finish(part: Part, file: Path, real_start: float, real_end: float, copy: bool = False) -> None:
        clip_chs = chapters_for_part(chapters_all, real_start, real_end)
        n_clip_chapters = len(clip_chs) if opts.chapters else 0
        chs = fill_gaps(clip_chs, real_end - real_start, opts.clip_filter.gap_title) if opts.chapters else []
        stem = final_dir / part_stem(src, opts, part, total_parts, job.single_clip)
        t = dict(tags)
        if job.single_clip:
            t["title"] = job.single_clip.get("title") or src.title
            t["comment"] = job.single_clip.get("url") or src.url
        elif total_parts > 1:
            t["title"] = f"{src.title} (part {part.index}/{total_parts})".strip()
        else:
            t["title"] = src.title.strip()
        finalize_fn = finalize_audio_part if audio_only else finalize_part
        dest = finalize_fn(ctx, file, stem, out_container, chs, t, real_end - real_start, copy)
        if opts.sidecar and n_clip_chapters:
            _write_sidecar(dest, [c for c in chs if c.clips])
        ctx.log(f"✔ {dest.name}" + (f"  ({n_clip_chapters} clip chapters)" if n_clip_chapters else ""))
        game_chs = chapters_for_part(games_all, real_start, real_end)
        muted_chs = chapters_for_part(muted_all, real_start, real_end)
        # Two separate outputs. The XML is the plain import (no colors). The JSON is for the plugin. Game markers
        # alone still give the XML, as before, unless the plugin file is on (then they go there).
        xml_clips = clip_chs if opts.premiere_xml else []
        json_clips = clip_chs if opts.premiere_plugin else []
        want_xml = opts.premiere_xml or (opts.game_markers and not opts.premiere_plugin)
        if (want_xml and (xml_clips or game_chs)) or (opts.premiere_plugin and (json_clips or game_chs or muted_chs)):
            probe = probe_video(dest)
            if probe is None:
                ctx.log("Could not read the frame rate with ffprobe; assuming 30 fps for the Premiere markers.")
            fps, w, h = probe or (30.0, 1920, 1080)

            def marker_bits(clips: list[Chapter], muted: list[Chapter] | None = None) -> str:
                return " + ".join(([f"{len(clips)} clip markers"] if clips else [])
                                  + ([f"{len(game_chs)} game markers"] if game_chs else [])
                                  + ([f"{len(muted)} muted markers"] if muted else []))

            if want_xml and (xml_clips or game_chs):
                markers = sorted(xml_clips + game_chs, key=lambda c: (c.start, c.kind))
                xml = write_premiere_xml(dest, markers, real_end - real_start, fps, w, h)
                ctx.log(f"✔ {xml.name}  ({marker_bits(xml_clips)} for Premiere Pro, {fps:g} fps)")
            if opts.premiere_plugin and (json_clips or game_chs or muted_chs):
                markers = sorted(json_clips + game_chs + muted_chs, key=lambda c: (c.start, c.kind))
                mj = write_markers_json(dest, markers, real_end - real_start, fps, src, real_start, real_end)
                ctx.log(f"✔ {mj.name}  ({marker_bits(json_clips, muted_chs)} for the Premiere plugin, {fps:g} fps)")
        if chat_tool:
            chat_files_for_part(ctx, chat_tool, src, opts, part, total_parts, dest, real_start, real_end, workdir)
        results.append(dest)

    if plan.strategy == "full":
        ctx.stage(0.0, 0.85, "Downloading VOD")
        full = download_full(ctx, src.url, workdir, opts.threads, **fmt_kw)
        ctx.stage(0.85, 1.0, "Cutting")
        if opts.exact:
            for i, p in enumerate(plan.parts):
                ctx.stage(0.85 + 0.15 * i / total_parts, 0.85 + 0.15 * (i + 1) / total_parts, f"Re-encoding part {p.index}/{total_parts}")
                cut = cut_exact(ctx, full, p, opts.container, workdir)
                finish(p, cut, p.start, p.end)
        else:
            split_container = "m4a" if audio_only else opts.container
            split_kw = {"audio_only": True} if audio_only else {}
            segs = split_copy(ctx, full, plan.parts, src.duration, split_container, workdir, **split_kw)
            only_full = len(plan.parts) == 1 and segs[plan.parts[0].index][0] == full
            for i, p in enumerate(plan.parts):
                f, s, e = segs[p.index]
                ctx.stage(0.85 + 0.15 * i / total_parts, 0.85 + 0.15 * (i + 1) / total_parts, f"Finishing part {p.index}/{total_parts}")
                finish(p, f, s, e, copy=only_full and opts.keep_full)
        if opts.keep_full and full.exists():
            final_dir.mkdir(parents=True, exist_ok=True)
            stem = final_dir / safe_name(f"{src.uploader} - {src.date} - {src.twitch_vod_id or src.id} - FULL")
            full_suffix = ".m4a" if (audio_only and full.suffix.lower() == ".mp4") else full.suffix
            kept = unique_path(stem.parent / f"{stem.name}{full_suffix}")
            shutil.move(str(full), str(kept))
            ctx.log(f"Kept full VOD: {kept.name}")
    else:
        for i, p in enumerate(plan.parts):
            ctx.check_cancel()
            lo, hi = i / total_parts, (i + 1) / total_parts
            ctx.stage(lo, lo + (hi - lo) * 0.9, f"Downloading part {p.index}/{total_parts}")
            aligned = download_section_aligned(ctx, src.url, p, workdir, **dl_kw)
            if aligned:
                f, real_start, real_end = aligned
                early = p.start - real_start
                ctx.log(
                    f"Part {p.index} starts at {fmt_hms(real_start)} (asked {fmt_hms(p.start)}"
                    + (f", {early:.0f} s early" if early >= 0.5 else "")
                    + f") and ends at {fmt_hms(real_end)}"
                )
                if opts.exact:
                    ctx.stage(lo + (hi - lo) * 0.9, hi, f"Re-encoding part {p.index}/{total_parts}")
                    f = cut_exact(ctx, f, p, opts.container, workdir, offset=max(0.0, p.start - real_start))
                    real_start, real_end = p.start, p.end
            else:
                f = download_section(ctx, src.url, p, workdir, opts.threads, opts.exact, **fmt_kw)
                real_start, real_end = p.start, p.end
            ctx.stage(lo + (hi - lo) * 0.9, hi, f"Finishing part {p.index}/{total_parts}")
            finish(p, f, real_start, real_end)

    shutil.rmtree(workdir, ignore_errors=True)
    ctx.stage(1.0, 1.0, "Done")
    return results
