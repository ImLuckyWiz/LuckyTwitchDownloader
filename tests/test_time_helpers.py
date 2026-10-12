"""parse_time / fmt_hms / parse_twitch_duration."""

import pytest

from luckytwitch_engine import PlanError, fmt_hms, parse_time, parse_twitch_duration


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0", 0.0),
        ("90", 90.0),
        ("1.5", 1.5),
        ("1:30", 90.0),
        ("90:00", 5400.0),
        ("1:30:00", 5400.0),
        ("0:00:01.5", 1.5),
        ("1h30m", 5400.0),
        ("1h", 3600.0),
        ("45m", 2700.0),
        ("90s", 90.0),
        ("1h2m3s", 3723.0),
        ("1m30.5s", 90.5),
        (" 1H30M ", 5400.0),  # case and surrounding spaces do not matter
    ],
)
def test_parse_time_valid(text, expected):
    assert parse_time(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "   "])
def test_parse_time_empty_is_none(text):
    assert parse_time(text) is None


@pytest.mark.parametrize("text", ["abc", "1h30", "1:2:3:4", "-5", "1::2", "1:xx", "1,5"])
def test_parse_time_invalid(text):
    with pytest.raises(PlanError, match="Invalid time"):
        parse_time(text)


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (None, "-"),
        (0, "0:00:00"),
        (59, "0:00:59"),
        (60, "0:01:00"),
        (3661, "1:01:01"),
        (36000, "10:00:00"),
        (360000, "100:00:00"),  # hours do not wrap
        (59.6, "0:01:00"),  # rounds to the nearest second
        (0.4, "0:00:00"),
    ],
)
def test_fmt_hms(seconds, expected):
    assert fmt_hms(seconds) == expected


def test_fmt_hms_roundtrips_through_parse_time():
    for s in (0, 1, 59, 60, 3599, 3600, 86399, 123456):
        assert parse_time(fmt_hms(s)) == s


@pytest.mark.parametrize(
    "text, expected",
    [("3h2m10s", 10930), ("45s", 45), ("1h", 3600), ("2m", 120), ("", 0), ("nonsense", 0)],
)
def test_parse_twitch_duration(text, expected):
    assert parse_twitch_duration(text) == expected
