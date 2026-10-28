"""
Planning logic for LuckyTwitch Downloader: cut points -> parts -> strategy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.errors import PlanError
from core.timeutil import fmt_hms, parse_time

END_WORDS = {"end", "fin", "final", "finish", "finishes", "finished", "eof"}
FILLER_WORDS = {"till", "until", "to", "hasta", "the", "of", "vod"}


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
