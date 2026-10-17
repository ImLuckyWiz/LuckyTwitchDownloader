"""Game segments ("chapters") and preview-thumbnail storyboards read from yt-dlp's --dump-single-json.

The three files in tests/fixtures are real dumps (trimmed: signed manifest URLs and headers removed):
  vod_multi_game_long    7h18m, Just Chatting -> a game -> Just Chatting; frames every 131.32 s
  vod_single_game_long   4h21m, one game the whole time;                  frames every 78.25 s
  vod_single_game_short  15 min, one game; frames every 5 s, so the last sheet of the "high" storyboard is padded
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

import luckytwitch_engine as eng
from luckytwitch_engine import (
    EngineError,
    GameSegment,
    Storyboard,
    fetch_storyboard_sheet,
    load_storyboard_frames,
    parse_game_segments,
    parse_source_info,
    parse_storyboard,
)

FIXTURES = Path(__file__).parent / "fixtures"


def dump(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def storyboard_format(**over) -> dict:
    f = {
        "format_id": "sb1", "format_note": "storyboard", "width": 160, "height": 90, "columns": 5, "rows": 4,
        "fps": 0.5, "fragments": [{"url": "https://x/sb-0.jpg", "duration": 40.0}],
    }
    f.update(over)
    return f


# --------------------------------------------------------------------------- real dumps: segments
def test_multi_game_vod_gives_three_segments_and_keeps_the_repeated_game():
    info = parse_source_info(dump("vod_multi_game_long"), "https://www.twitch.tv/videos/2888990596")
    assert [(g.start, g.end, g.title) for g in info.segments] == [
        (0, 17805, "Just Chatting"),
        (17805, 25845, "the cabin game"),
        (25845, 26264, "Just Chatting"),
    ]


def test_segments_cover_the_whole_vod_without_gaps():
    for name in ("vod_multi_game_long", "vod_single_game_long", "vod_single_game_short"):
        info = parse_source_info(dump(name), "https://www.twitch.tv/videos/1")
        segs = info.segments
        assert segs[0].start == 0 and segs[-1].end == info.duration
        assert all(a.end == b.start for a, b in zip(segs, segs[1:]))


@pytest.mark.parametrize("name, duration", [("vod_single_game_long", 15650), ("vod_single_game_short", 900)])
def test_single_game_vod_is_one_segment_covering_everything(name, duration):
    info = parse_source_info(dump(name), "https://www.twitch.tv/videos/1")
    assert info.segments == [GameSegment(0, duration, "Just Chatting")]


def test_the_existing_fields_are_unchanged():
    info = parse_source_info(dump("vod_multi_game_long"), "https://www.twitch.tv/videos/2888990596")
    assert (info.id, info.duration, info.date, info.uploader, info.twitch_vod_id) == (
        "v2888990596", 26264.0, "2026-10-01", "Zentreya", "2888990596")


# --------------------------------------------------------------------------- real dumps: storyboards
def test_long_vod_low_storyboard():
    sb = parse_source_info(dump("vod_multi_game_long"), "u").storyboard
    assert (sb.tile_w, sb.tile_h, sb.columns, sb.rows) == (160, 90, 5, 40)
    assert len(sb.urls) == 1 and sb.urls[0].endswith("2888990596-low-0.jpg")
    assert sb.count == 200 and sb.interval == pytest.approx(26264 / 200)


def test_single_game_long_vod_storyboard():
    sb = parse_source_info(dump("vod_single_game_long"), "u").storyboard
    assert sb.count == 200 and sb.interval == pytest.approx(78.25)


def test_short_vod_has_a_frame_every_5_seconds_and_a_full_low_sheet():
    sb = parse_source_info(dump("vod_single_game_short"), "u").storyboard
    assert sb.interval == pytest.approx(5.0)
    assert sb.count == 180 and sb.rows == 36 and sb.per_sheet == 180  # the low sheet has no padding


def test_high_storyboard_of_the_short_vod_has_four_sheets_and_a_padded_last_one():
    sb = parse_storyboard(dump("vod_single_game_short")["formats"], 900, prefer="high")
    assert (sb.tile_w, sb.tile_h, sb.columns, sb.rows) == (220, 124, 5, 10)
    assert len(sb.urls) == 4 and sb.per_sheet == 50
    # the fragments say "225 s" each (900 / 4), but a sheet really covers 50 frames * 5 s = 250 s
    assert sb.interval == pytest.approx(5.0)
    assert sb.count == 180  # NOT 200: the last 20 tiles are padding
    assert sb.tile_box(179)[0] == 3  # the last real frame is on the last sheet...
    assert sb.tile_box(180)[0] == 3  # ...and the first padding tile would be too (never read)


def test_high_storyboard_of_a_long_vod_is_completely_filled():
    sb = parse_storyboard(dump("vod_multi_game_long")["formats"], 26264, prefer="high")
    assert len(sb.urls) == 4 and sb.count == 200 == len(sb.urls) * sb.per_sheet
    assert sb.interval == pytest.approx(26264 / 200)


def test_default_picks_the_low_storyboard_and_prefer_high_the_other():
    formats = dump("vod_single_game_short")["formats"]
    assert parse_storyboard(formats, 900).tile_w == 160
    assert parse_storyboard(formats, 900, prefer="low").tile_w == 160
    assert parse_storyboard(formats, 900, prefer="high").tile_w == 220


def test_fixtures_hold_no_signed_tokens():
    for name in ("vod_multi_game_long", "vod_single_game_long", "vod_single_game_short"):
        text = (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
        assert "usher.ttvnw.net" not in text and "sig=" not in text and "manifest_url" not in text


# --------------------------------------------------------------------------- parse_game_segments edge cases
@pytest.mark.parametrize("chapters", [None, [], {}, "x", 5, [None, 3, "a"]])
def test_no_usable_chapters_gives_no_segments(chapters):
    assert parse_game_segments(chapters, 100) == []


def test_missing_chapters_key_in_the_dump():
    info = dump("vod_single_game_short")
    del info["chapters"]
    assert parse_source_info(info, "u").segments == []
    info["chapters"] = None
    assert parse_source_info(info, "u").segments == []


def test_broken_entries_are_dropped_and_good_ones_kept():
    chapters = [
        {"title": "ok", "start_time": 0, "end_time": 10},
        {"title": "no end", "start_time": 10},
        {"title": "text times", "start_time": "a", "end_time": "b"},
        {"title": "empty", "start_time": 20, "end_time": 20},
        {"title": "backwards", "start_time": 40, "end_time": 30},
        {"title": "also ok", "start_time": 50, "end_time": 60},
    ]
    assert [g.title for g in parse_game_segments(chapters, 100)] == ["ok", "also ok"]


def test_segments_are_clamped_to_the_duration_and_sorted():
    chapters = [
        {"title": "b", "start_time": 50, "end_time": 500},
        {"title": "a", "start_time": -5, "end_time": 50},
        {"title": "after the end", "start_time": 200, "end_time": 300},
    ]
    assert parse_game_segments(chapters, 100) == [GameSegment(0, 50, "a"), GameSegment(50, 100, "b")]


def test_missing_title_becomes_an_empty_string_and_same_titles_are_not_merged():
    chapters = [
        {"start_time": 0, "end_time": 10},
        {"title": " Game ", "start_time": 10, "end_time": 20},
        {"title": "Game", "start_time": 20, "end_time": 30},
    ]
    segs = parse_game_segments(chapters, 100)
    assert [g.title for g in segs] == ["", "Game", "Game"]


# --------------------------------------------------------------------------- parse_storyboard edge cases
@pytest.mark.parametrize("formats", [None, [], "x", [None], [{"format_note": "Source"}], [{"format_id": "720p"}]])
def test_no_storyboard_in_the_formats(formats):
    assert parse_storyboard(formats, 100) is None


@pytest.mark.parametrize(
    "over",
    [
        {"fps": 0}, {"fps": None}, {"fps": "x"}, {"fps": -1}, {"fps": float("nan")},
        {"fragments": []}, {"fragments": None}, {"fragments": [{"duration": 1}]}, {"fragments": [{"url": ""}]},
        {"rows": 0}, {"columns": 0}, {"width": 0}, {"height": None}, {"rows": "x"},
    ],
)
def test_unusable_storyboard_is_skipped_not_guessed(over):
    assert parse_storyboard([storyboard_format(**over)], 100) is None


def test_a_broken_storyboard_does_not_hide_a_good_one():
    broken = storyboard_format(format_id="sb1", fps=0)
    good = storyboard_format(format_id="sb0", width=220, height=124)
    assert parse_storyboard([broken, good], 100).tile_w == 220


def test_only_storyboard_formats_are_considered_even_if_they_look_like_one():
    lookalike = storyboard_format(format_note="Source", format_id="1080p60")
    assert parse_storyboard([lookalike], 100) is None


def test_frame_count_comes_from_fps_and_duration():
    sb = parse_storyboard([storyboard_format(fps=0.5)], 30)  # one frame every 2 s -> 15 frames (the sheet holds 20)
    assert sb.interval == 2 and sb.count == 15


def test_frame_count_rounds_up():
    assert parse_storyboard([storyboard_format(fps=0.5)], 11).count == 6  # 5.5 -> 6


def test_frame_count_ignores_float_noise():
    fps, duration = 1 / 75, 525  # exactly 7 frames, but 525 * (1/75) is 7.000000000000001
    assert math.ceil(duration * fps) == 8  # the naive way would invent an 8th frame
    assert parse_storyboard([storyboard_format(fps=fps)], duration).count == 7


def test_frame_count_never_exceeds_what_the_sheets_hold():
    sb = parse_storyboard([storyboard_format(fps=10)], 100)  # would want 1000 frames, the sheet has 20 tiles
    assert sb.count == 20


def test_zero_duration_gives_no_storyboard():
    assert parse_storyboard([storyboard_format()], 0) is None


# --------------------------------------------------------------------------- parse_source_info
def test_missing_duration_is_still_an_error():
    info = dump("vod_single_game_short")
    del info["duration"]
    with pytest.raises(EngineError, match="length"):
        parse_source_info(info, "u")


def test_a_vod_without_chapters_or_storyboard_still_parses():
    info = parse_source_info({"id": "1", "title": "t", "duration": 60}, "https://www.twitch.tv/videos/1")
    assert info.segments == [] and info.storyboard is None and info.duration == 60.0


def test_get_source_info_passes_the_new_data_through(monkeypatch):
    raw = json.dumps(dump("vod_multi_game_long"))
    monkeypatch.setattr(eng, "find_tool", lambda name: "yt-dlp")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=raw, stderr="")
    )
    monkeypatch.setattr(eng, "muted_from_playlist_url", lambda url, duration=None: [(10.0, 20.0)])  # no network
    info = eng.get_source_info("2888990596")
    assert info.url == "https://www.twitch.tv/videos/2888990596"
    assert len(info.segments) == 3 and info.storyboard.count == 200
    assert info.muted == [(10.0, 20.0)]


# --------------------------------------------------------------------------- Storyboard geometry
def small_sb(**over) -> Storyboard:
    base = dict(urls=["a", "b"], tile_w=8, tile_h=6, columns=3, rows=2, interval=4.0, count=10)
    base.update(over)
    return Storyboard(**base)


def test_frame_time_and_index_are_inverse_and_clamped():
    sb = small_sb()
    assert [sb.frame_time(i) for i in (0, 1, 9)] == [0.0, 4.0, 36.0]
    assert sb.frame_index_at(0) == 0 and sb.frame_index_at(3.9) == 0 and sb.frame_index_at(4) == 1
    assert sb.frame_index_at(10_000) == 9 and sb.frame_index_at(-5) == 0


def test_tile_box_walks_each_row_then_moves_to_the_next_sheet():
    sb = small_sb()  # 3 columns x 2 rows = 6 per sheet, 8x6 pixel tiles
    assert sb.tile_box(0) == (0, (0, 0, 8, 6))
    assert sb.tile_box(2) == (0, (16, 0, 24, 6))
    assert sb.tile_box(3) == (0, (0, 6, 8, 12))
    assert sb.tile_box(5) == (0, (16, 6, 24, 12))
    assert sb.tile_box(6) == (1, (0, 0, 8, 6))
    assert sb.tile_box(9) == (1, (0, 6, 8, 12))


# --------------------------------------------------------------------------- cutting sheets into frames
PIL = pytest.importorskip("PIL.Image", reason="Pillow is optional")


def colour(i: int) -> tuple[int, int, int]:
    return (10 + i * 20, 200 - i * 10, 7 * i)


def make_sheet(path: Path, sb: Storyboard, first: int, tiles: int, size: tuple[int, int] | None = None) -> Path:
    """A sheet whose tile k is filled with colour(first + k)."""
    from PIL import Image

    im = Image.new("RGB", size or (sb.columns * sb.tile_w, sb.rows * sb.tile_h), (0, 0, 0))
    for k in range(tiles):
        row, col = divmod(k, sb.columns)
        im.paste(colour(first + k), (col * sb.tile_w, row * sb.tile_h, (col + 1) * sb.tile_w, (row + 1) * sb.tile_h))
    im.save(path, "PNG")  # lossless, so the colours can be compared exactly
    return path


def test_frames_are_cut_from_the_right_tiles_and_padding_is_ignored(tmp_path):
    sb = small_sb()  # 10 frames over two sheets: 6 + 4 (the last sheet has 2 padding tiles)
    files = {"a": make_sheet(tmp_path / "a.png", sb, 0, 6), "b": make_sheet(tmp_path / "b.png", sb, 6, 4)}
    frames = load_storyboard_frames(sb, fetch=files.get)
    assert len(frames) == 10 and all(f is not None for f in frames)
    for i, f in enumerate(frames):
        assert f.size == (8, 6)
        assert f.getpixel((3, 3)) == colour(i)


def test_a_sheet_that_failed_to_download_only_loses_its_own_frames(tmp_path):
    sb = small_sb()
    files = {"a": make_sheet(tmp_path / "a.png", sb, 0, 6)}  # "b" is missing -> fetch returns None
    frames = load_storyboard_frames(sb, fetch=files.get)
    assert [f is None for f in frames] == [False] * 6 + [True] * 4


def test_a_sheet_smaller_than_expected_gives_none_not_black_tiles(tmp_path):
    sb = small_sb()
    files = {
        "a": make_sheet(tmp_path / "a.png", sb, 0, 6),
        "b": make_sheet(tmp_path / "b.png", sb, 6, 4, size=(24, 6)),  # only the first row of tiles
    }
    frames = load_storyboard_frames(sb, fetch=files.get)
    assert [f is None for f in frames[6:]] == [False, False, False, True]


def test_an_unreadable_sheet_is_skipped(tmp_path):
    sb = small_sb()
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    frames = load_storyboard_frames(sb, fetch={"a": bad, "b": bad}.get)
    assert frames == [None] * 10


def test_without_pillow_every_frame_is_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)  # makes "from PIL import Image" fail
    sb = small_sb()
    assert load_storyboard_frames(sb, fetch=lambda url: pytest.fail("must not download without Pillow")) == [None] * 10


# --------------------------------------------------------------------------- the sheet cache
class FakeResponse:
    def __init__(self, content=b"jpgdata", error=None):
        self.content, self.error = content, error

    def raise_for_status(self):
        if self.error:
            raise self.error


def test_sheet_is_downloaded_once_then_served_from_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "user_data_dir", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(eng.requests, "get", lambda url, **kw: calls.append(url) or FakeResponse())
    first = fetch_storyboard_sheet("https://x/sb-0.jpg")
    assert first is not None and first.read_bytes() == b"jpgdata" and first.parent == tmp_path / "cache" / "storyboards"
    assert fetch_storyboard_sheet("https://x/sb-0.jpg") == first
    assert calls == ["https://x/sb-0.jpg"]  # the second call did not touch the network
    assert not list(first.parent.glob("*.tmp"))


def test_sheet_download_failures_return_none(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "user_data_dir", lambda: tmp_path)

    def boom(url, **kw):
        raise eng.requests.ConnectionError("offline")

    monkeypatch.setattr(eng.requests, "get", boom)
    assert fetch_storyboard_sheet("https://x/sb-0.jpg") is None
    monkeypatch.setattr(eng.requests, "get", lambda url, **kw: FakeResponse(error=eng.requests.HTTPError("404")))
    assert fetch_storyboard_sheet("https://x/sb-0.jpg") is None
    assert fetch_storyboard_sheet("") is None
    assert not (tmp_path / "cache" / "storyboards").exists() or not any((tmp_path / "cache" / "storyboards").iterdir())
