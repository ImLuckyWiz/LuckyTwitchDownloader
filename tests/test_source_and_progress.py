"""URL helpers and the parsers for yt-dlp / ffmpeg progress output."""

import pytest

from luckytwitch_engine import normalize_url, parse_ffmpeg_stats, parse_progress, twitch_vod_id


# --------------------------------------------------------------------------- URLs
def test_normalize_url_turns_a_bare_id_into_a_vod_url():
    assert normalize_url("123456") == "https://www.twitch.tv/videos/123456"
    assert normalize_url("  123456  ") == "https://www.twitch.tv/videos/123456"


def test_normalize_url_leaves_urls_alone_apart_from_whitespace():
    assert normalize_url(" https://www.twitch.tv/videos/1 ") == "https://www.twitch.tv/videos/1"
    assert normalize_url("https://youtu.be/xyz") == "https://youtu.be/xyz"
    assert normalize_url("") == ""


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.twitch.tv/videos/123456", "123456"),
        ("https://www.twitch.tv/videos/123456?t=1h2m", "123456"),
        ("https://twitch.tv/streamer/video/987?t=1h", "987"),
        ("https://m.twitch.tv/videos/55", "55"),
        ("https://www.twitch.tv/streamer", None),
        ("https://www.twitch.tv/streamer/clip/SomeClip", None),
        ("https://youtu.be/xyz", None),
        ("", None),
    ],
)
def test_twitch_vod_id(url, expected):
    assert twitch_vod_id(url) == expected


# --------------------------------------------------------------------------- yt-dlp progress
def line(status="downloading", dl="NA", total="NA", est="NA", f_idx="NA", f_cnt="NA", speed="NA", eta="NA"):
    return "|".join(["LTPROG", status, dl, total, est, f_idx, f_cnt, speed, eta])


def test_parse_progress_ignores_other_lines():
    assert parse_progress("[download] 12.0% of 1GiB") is None
    assert parse_progress("") is None
    assert parse_progress("LTPROG|too|short") is None


def test_parse_progress_fraction_from_fragments():
    frac, text = parse_progress(line(dl="1048576", f_idx="5", f_cnt="20", speed="2097152", eta="90"))
    assert frac == 0.25
    assert text == "1 MiB · 2.0 MiB/s · ETA 0:01:30"


def test_parse_progress_fraction_from_bytes():
    frac, _ = parse_progress(line(dl="500", total="2000"))
    assert frac == 0.25


def test_parse_progress_falls_back_to_the_estimated_total():
    frac, _ = parse_progress(line(dl="500", est="1000"))
    assert frac == 0.5


def test_parse_progress_unknown_total_gives_no_fraction():
    frac, text = parse_progress(line(dl="1048576"))
    assert frac is None
    assert text == "1 MiB"


def test_parse_progress_all_unknown():
    assert parse_progress(line()) == (None, "")


def test_parse_progress_zero_fragments_done_is_zero_not_none():
    frac, _ = parse_progress(line(f_idx="NA", f_cnt="10"))
    assert frac == 0.0


# --------------------------------------------------------------------------- ffmpeg stats
STATS = "size=   12345KiB time=00:01:23.45 bitrate=1234.5kbits/s speed=12.3x"


def test_ffmpeg_stats_with_a_known_total():
    frac, text = parse_ffmpeg_stats(STATS, 600)
    assert frac == pytest.approx(83.45 / 600)
    assert text == "12 MiB · 12.3x · ETA 0:00:42"


def test_ffmpeg_stats_without_a_total_shows_the_elapsed_time():
    frac, text = parse_ffmpeg_stats("size=   512KiB time=00:00:10.00 speed=2x", None)
    assert frac is None
    assert text == "0:00:10 · 0.5 MiB · 2.0x"


def test_ffmpeg_stats_fraction_is_capped_at_one():
    frac, text = parse_ffmpeg_stats("time=00:20:00.00 speed=1x", 600)
    assert frac == 1.0
    assert text == "1.0x · ETA 0:00:00"


@pytest.mark.parametrize("unit, value, shown", [("KiB", 2048, "2.0 MiB"), ("MiB", 5, "5.0 MiB"), ("GiB", 2, "2048 MiB")])
def test_ffmpeg_stats_size_units(unit, value, shown):
    _, text = parse_ffmpeg_stats(f"size= {value}{unit} time=00:00:01.00", 10)
    assert text.startswith(shown)


def test_ffmpeg_stats_ignores_lines_without_a_time():
    assert parse_ffmpeg_stats("Press [q] to stop", 600) is None
    assert parse_ffmpeg_stats("", 600) is None
