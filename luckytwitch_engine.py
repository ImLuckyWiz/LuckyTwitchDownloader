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
from dataclasses import dataclass, field
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
            pos = next(i for i, v in enumerate(vals) if v > t)  # type: ignore[operator]
            g.insert(pos, fmt_hms(t))
            break
    else:
        raise PlanError("That moment is not inside any of your parts.")
    return "\n".join(" - ".join(g) for g in groups)


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
    clips.sort(key=lambda c: (c.get("vod_offset") is None, c.get("vod_offset") or 0))
    return clips


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


class _SafeDict(dict):
    def __missing__(self, key):  # unknown {tokens} stay as they are
        return "{" + key + "}"


def filter_clips(clips: list[dict], flt: ClipFilter) -> list[dict]:
    """Keep only the clips that pass the filter (and can be placed in the VOD)."""
    kept = [
        c
        for c in clips
        if c.get("vod_offset") is not None
        and c.get("view_count", 0) >= flt.min_views
        and c.get("duration", 0) >= flt.min_duration
    ]
    if flt.top_n > 0:
        kept.sort(key=lambda c: (-c.get("view_count", 0), c["vod_offset"]))
        kept = kept[: flt.top_n]
    kept.sort(key=lambda c: c["vod_offset"])
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
    off = clip.get("vod_offset")
    if off is None:
        raise PlanError("That clip has no position in the VOD.")
    start = max(0.0, float(off) - pad_before)
    end = float(off) + float(clip.get("duration") or 0) + pad_after
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
        off = float(c["vod_offset"])
        ch = Chapter(
            start=max(0.0, off - flt.pad_before),
            end=off + float(c.get("duration", 0)) + flt.pad_after,
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
        out.append(Chapter(s, e, ch.title, ch.views, ch.clips))
    return out


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
        comment = " | ".join(
            f"{c.get('creator_name', '')} · {c.get('view_count', 0)} views · {c.get('url', '')}" for c in ch.clips
        )
        frame = min(max(int(round(ch.start * real_rate)), 0), total - 1)
        end = min(int(round(ch.end * real_rate)), total)  # the marker spans the whole clip
        lines += [
            "<marker>",
            f"<comment>{escape(comment)}</comment>",
            f"<name>{escape(ch.title)}</name>",
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
# Source info (yt-dlp)
# --------------------------------------------------------------------------- #
@dataclass
class SourceInfo:
    url: str
    id: str
    title: str
    uploader: str
    duration: float
    date: str  # YYYY-MM-DD or ""
    twitch_vod_id: str | None


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
    if not info.get("duration"):
        raise EngineError("yt-dlp did not report the video length for that URL.")
    d = info.get("upload_date") or ""
    date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""
    return SourceInfo(
        url=url,
        id=str(info.get("id", "")),
        title=info.get("title", "") or "",
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=float(info["duration"]),
        date=date,
        twitch_vod_id=twitch_vod_id(url),
    )


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
    premiere_xml: bool = False  # also write a Premiere Pro XML (clips as markers) next to each part


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
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    t = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                if total:
                    ctx.report(t / total)
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
) -> None:
    """
    Run the yt-dlp binary, forwarding progress to ctx. Cancel kills the whole process tree.
    total_secs: length of what is being downloaded (sections) so ffmpeg's stats become a percentage.
    watch_dir: folder where the download lands, used as a fallback progress source.
    """
    ytdlp = find_tool("yt-dlp")
    if not ytdlp:
        raise EngineError(YTDLP_MISSING)
    cmd = [
        ytdlp,
        "-S", "res,fps,tbr",
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


MEDIA_EXTS = {".mp4", ".mkv", ".ts", ".webm", ".mov", ".m4v"}


def _find_media(folder: Path) -> Path | None:
    files = [p for p in folder.glob("*") if p.suffix.lower() in MEDIA_EXTS and p.is_file()]
    return max(files, key=lambda p: p.stat().st_size) if files else None


def download_full(ctx: Ctx, url: str, workdir: Path, threads: int) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    done = workdir / "full.done"
    existing = _find_media(workdir)
    if done.exists() and existing:
        ctx.log("Full VOD already downloaded in the work folder, reusing it.")
        return existing
    run_ytdlp(ctx, ["-o", _out_template(workdir, "full"), url], threads)
    media = _find_media(workdir)
    if not media:
        raise EngineError("yt-dlp finished but no video file was found.")
    done.write_text("ok")
    return media


def download_section(ctx: Ctx, url: str, part: Part, workdir: Path, threads: int, exact: bool) -> Path:
    pdir = workdir / f"part{part.index}"
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True)
    args = ["-o", _out_template(pdir, "part"), "--download-sections", f"*{part.start:.3f}-{part.end:.3f}"]
    if exact:
        args.append("--force-keyframes-at-cuts")
    run_ytdlp(ctx, args + [url], threads, total_secs=part.duration, watch_dir=pdir)
    media = _find_media(pdir)
    if not media or media.stat().st_size < 4096:
        raise EngineError(
            f"Part {part.index} ({fmt_hms(part.start)}–{fmt_hms(part.end)}) came out empty. "
            "Try again, or use strategy «full» to download the whole VOD and split it."
        )
    return media


# --------------------------------------------------------------------------- #
# Splitting / finalizing
# --------------------------------------------------------------------------- #
def safe_name(text: str) -> str:
    """Strip emojis / illegal characters so the name is safe everywhere."""
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


def part_stem(src: SourceInfo, opts: JobOptions, part: Part, total: int, clip: dict | None = None) -> str:
    def tag(t: float) -> str:
        s = int(t)
        return f"{s // 3600:02d}h{s % 3600 // 60:02d}m{s % 60:02d}s"

    data = _SafeDict(
        streamer=src.uploader or "vod",
        date=src.date or "",
        id=src.twitch_vod_id or src.id,
        title=src.title,
        n=part.index,
        total=total,
        start=tag(part.start),
        end=tag(part.end),
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
        name = data["clip_title"] if clip else f"{data['id']} - part{part.index}"
    name = safe_name(name)
    if clip:
        name = name[:150].strip(" .")
        return name or f"clip {data['clip_id']}".strip()
    return name or f"part{part.index}"


def stream_dir(src: SourceInfo, opts: JobOptions) -> Path:
    """Where the files of this VOD go: out_dir/<streamer>/<stream>/ (or out_dir if disabled)."""
    base = Path(opts.out_dir)
    if not opts.subfolders:
        return base
    data = _SafeDict(
        streamer=src.uploader or "vod",
        date=src.date or "",
        id=src.twitch_vod_id or src.id,
        title=src.title,
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
    dest = unique_path(dest_stem.with_suffix("." + container))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if chapters:
        meta = src_file.with_suffix(".ffmeta")
        meta.write_text(ffmetadata(chapters, tags), encoding="utf-8")
        run_ffmpeg(
            ctx,
            ["-i", str(src_file), "-i", str(meta), "-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", str(dest)],
            total=total,
        )
    elif src_file.suffix.lower() == "." + container:
        (shutil.copy2 if copy_instead_of_move else shutil.move)(str(src_file), str(dest))
    else:
        run_ffmpeg(ctx, ["-i", str(src_file), "-map", "0", "-c", "copy", str(dest)], total=total)
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


def split_copy(ctx: Ctx, full: Path, parts: list[Part], duration: float, container: str, workdir: Path) -> dict[int, tuple[Path, float, float]]:
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
    run_ffmpeg(
        ctx,
        [
            "-i", str(full),
            "-map", "0:v:0", "-map", "0:a?",
            "-c", "copy",
            "-f", "segment",
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


def cut_exact(ctx: Ctx, full: Path, part: Part, container: str, workdir: Path) -> Path:
    """Frame-exact cut (re-encodes video)."""
    out = workdir / f"exact_{part.index}.{container}"
    run_ffmpeg(
        ctx,
        [
            "-ss", f"{part.start:.3f}", "-i", str(full), "-t", f"{part.duration:.3f}",
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            str(out),
        ],
        total=part.duration,
    )
    return out


# --------------------------------------------------------------------------- #
# Running a job
# --------------------------------------------------------------------------- #
def _load_chapters(ctx: Ctx, job: Job) -> list[Chapter]:
    if not (job.opts.chapters or job.opts.premiere_xml):
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


def run_job(job: Job, ctx: Ctx) -> list[Path]:
    src, opts = job.source, job.opts
    if not find_tool("ffmpeg"):
        raise EngineError("ffmpeg was not found. Install it and add it to PATH.")

    plan = make_plan(opts.cut_text, src.duration, opts.strategy, opts.full_threshold)
    ctx.log(
        f"{len(plan.parts)} part(s), coverage {plan.coverage * 100:.0f}% → "
        + ("download full VOD, then split" if plan.strategy == "full" else "download only the parts")
    )
    chapters_all = _load_chapters(ctx, job)

    out_dir = Path(opts.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final_dir = stream_dir(src, opts)
    workdir = out_dir / f".luckytwitch_{src.twitch_vod_id or src.id}"
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
        else:
            t["title"] = f"{src.title} (part {part.index}/{total_parts})".strip()
        dest = finalize_part(ctx, file, stem, opts.container, chs, t, real_end - real_start, copy)
        if opts.sidecar and n_clip_chapters:
            _write_sidecar(dest, [c for c in chs if c.clips])
        ctx.log(f"✔ {dest.name}" + (f"  ({n_clip_chapters} clip chapters)" if n_clip_chapters else ""))
        if opts.premiere_xml and clip_chs:
            probe = probe_video(dest)
            if probe is None:
                ctx.log("Could not read the frame rate with ffprobe; assuming 30 fps for the Premiere XML.")
            fps, w, h = probe or (30.0, 1920, 1080)
            xml = write_premiere_xml(dest, clip_chs, real_end - real_start, fps, w, h)
            ctx.log(f"✔ {xml.name}  ({len(clip_chs)} markers for Premiere Pro, {fps:g} fps)")
        results.append(dest)

    if plan.strategy == "full":
        ctx.stage(0.0, 0.85, "Downloading VOD")
        full = download_full(ctx, src.url, workdir, opts.threads)
        ctx.stage(0.85, 1.0, "Cutting")
        if opts.exact:
            for i, p in enumerate(plan.parts):
                ctx.stage(0.85 + 0.15 * i / total_parts, 0.85 + 0.15 * (i + 1) / total_parts, f"Re-encoding part {p.index}/{total_parts}")
                cut = cut_exact(ctx, full, p, opts.container, workdir)
                finish(p, cut, p.start, p.end)
        else:
            segs = split_copy(ctx, full, plan.parts, src.duration, opts.container, workdir)
            only_full = len(plan.parts) == 1 and segs[plan.parts[0].index][0] == full
            for i, p in enumerate(plan.parts):
                f, s, e = segs[p.index]
                ctx.stage(0.85 + 0.15 * i / total_parts, 0.85 + 0.15 * (i + 1) / total_parts, f"Finishing part {p.index}/{total_parts}")
                finish(p, f, s, e, copy=only_full and opts.keep_full)
        if opts.keep_full and full.exists():
            final_dir.mkdir(parents=True, exist_ok=True)
            stem = final_dir / safe_name(f"{src.uploader} - {src.date} - {src.twitch_vod_id or src.id} - FULL")
            kept = unique_path(stem.with_suffix(full.suffix))
            shutil.move(str(full), str(kept))
            ctx.log(f"Kept full VOD: {kept.name}")
    else:
        for i, p in enumerate(plan.parts):
            ctx.check_cancel()
            lo, hi = i / total_parts, (i + 1) / total_parts
            ctx.stage(lo, lo + (hi - lo) * 0.9, f"Downloading part {p.index}/{total_parts}")
            f = download_section(ctx, src.url, p, workdir, opts.threads, opts.exact)
            ctx.stage(lo + (hi - lo) * 0.9, hi, f"Finishing part {p.index}/{total_parts}")
            finish(p, f, p.start, p.end)

    shutil.rmtree(workdir, ignore_errors=True)
    ctx.stage(1.0, 1.0, "Done")
    return results
