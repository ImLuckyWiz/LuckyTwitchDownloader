"""Tests for Phase 1: VideoFormat, parse_formats, resolve_format, estimate_bytes."""

import json
from pathlib import Path

import pytest

from luckytwitch_engine import (
    QUALITY_AUDIO,
    QUALITY_BEST,
    VideoFormat,
    estimate_bytes,
    parse_formats,
    parse_source_info,
    resolve_format,
)

FIXTURE_SHORT = Path("tests/fixtures/vod_single_game_short.json")
FIXTURE_MULTI = Path("tests/fixtures/vod_multi_game_long.json")
FIXTURE_LONG = Path("tests/fixtures/vod_single_game_long.json")


def load_fixture(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_real_fixtures_give_sorted_qualities():
    for fpath in (FIXTURE_SHORT, FIXTURE_MULTI, FIXTURE_LONG):
        data = load_fixture(fpath)
        fmts = parse_formats(data.get("formats"))
        ids = [f.format_id for f in fmts]
        assert ids == ["1080p60", "720p60", "480p", "360p", "160p", "Audio_Only"]
        assert fmts[0].source is True
        assert all(not f.source for f in fmts[1:])
        audio = fmts[-1]
        assert audio.audio_only is True
        assert audio.height == 0
        assert all(not f.format_id.startswith("sb") for f in fmts)


def test_labels_and_tags():
    f_source = VideoFormat("1080p60", height=1080, fps=60, source=True)
    assert f_source.label == "1080p60 (Source)"
    assert f_source.tag == "1080p60"

    f_720 = VideoFormat("720p60", height=720, fps=60)
    assert f_720.label == "720p60"
    assert f_720.tag == "720p60"

    f_audio = VideoFormat("Audio_Only", audio_only=True)
    assert f_audio.label == "Audio only"
    assert f_audio.tag == "audio"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        "x",
        [None, 3],
        [{"format_id": "a"}],
        [{"format_id": "b", "url": "https://example.com/stream.mp4"}],
    ],
)
def test_garbage_formats_never_raise_and_return_empty(bad):
    assert parse_formats(bad) == []


def test_resolve_format():
    data = load_fixture(FIXTURE_SHORT)
    fmts = parse_formats(data.get("formats"))

    assert resolve_format(fmts, "best").format_id == "1080p60"
    assert resolve_format(fmts, QUALITY_BEST).format_id == "1080p60"
    assert resolve_format(fmts, "audio").format_id == "Audio_Only"
    assert resolve_format(fmts, QUALITY_AUDIO).format_id == "Audio_Only"
    assert resolve_format(fmts, "AUDIO").format_id == "Audio_Only"
    assert resolve_format(fmts, " best ").format_id == "1080p60"

    assert resolve_format(fmts, "720p60").format_id == "720p60"
    assert resolve_format(fmts, "Audio_Only").format_id == "Audio_Only"

    # Caps
    assert resolve_format(fmts, "720p").format_id == "720p60"
    assert resolve_format(fmts, "900p").format_id == "720p60"
    assert resolve_format(fmts, "100p").format_id == "160p"  # lowest video
    assert resolve_format(fmts, "banana").format_id == "1080p60"  # fallback to best

    assert resolve_format([], "best") is None

    # Synthetic list: 720p30 vs 720p60
    synth = [
        VideoFormat("720p30", height=720, fps=30, tbr=2000),
        VideoFormat("720p60", height=720, fps=60, tbr=3000),
    ]
    assert resolve_format(synth, "720p").format_id == "720p60"

    # No audio in list -> wanted "audio" falls back to best video
    no_audio = [VideoFormat("720p60", height=720, fps=60, tbr=3000)]
    assert resolve_format(no_audio, "audio").format_id == "720p60"


def test_parse_source_info_formats():
    data = load_fixture(FIXTURE_SHORT)
    src_twitch = parse_source_info(data, "https://www.twitch.tv/videos/123")
    assert len(src_twitch.formats) == 6
    assert src_twitch.formats[0].format_id == "1080p60"

    src_other = parse_source_info(data, "https://example.com/v/1")
    assert src_other.formats == []


def test_estimate_bytes():
    fmt = VideoFormat("1080p60", tbr=6000.0)
    # 6000 kbit/s * 1000 / 8 * 3600 s = 2_700_000_000 bytes
    assert estimate_bytes(fmt, 3600.0) == 2_700_000_000
    assert estimate_bytes(None, 3600.0) == 0
    assert estimate_bytes(fmt, 0) == 0
    assert estimate_bytes(fmt, -10) == 0
    assert estimate_bytes(VideoFormat("zero", tbr=0), 3600) == 0
