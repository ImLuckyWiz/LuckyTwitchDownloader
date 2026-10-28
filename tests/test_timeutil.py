"""
Tests for core.timeutil and core.errors.
"""

from __future__ import annotations

import pytest

from core.errors import Cancelled, EngineError, PlanError
from core.timeutil import fmt_hms, parse_time, parse_twitch_duration


def test_error_hierarchy():
    assert issubclass(PlanError, EngineError)
    assert issubclass(Cancelled, EngineError)
    assert issubclass(EngineError, Exception)


def test_parse_time_empty():
    assert parse_time("") is None
    assert parse_time("   ") is None


def test_parse_time_colon_format():
    assert parse_time("0:00") == 0.0
    assert parse_time("1:30") == 90.0
    assert parse_time("90:00") == 5400.0
    assert parse_time("1:30:00") == 5400.0
    assert parse_time("0:10:05") == 605.0
    assert parse_time("1:00:00.5") == 3600.5


def test_parse_time_seconds():
    assert parse_time("5400") == 5400.0
    assert parse_time("12.5") == 12.5


def test_parse_time_hm_format():
    assert parse_time("1h30m") == 5400.0
    assert parse_time("1h") == 3600.0
    assert parse_time("30m") == 1800.0
    assert parse_time("45s") == 45.0
    assert parse_time("1h30m15s") == 5415.0


def test_parse_time_invalid_raises_plan_error():
    with pytest.raises(PlanError, match="Invalid time"):
        parse_time("invalid")
    with pytest.raises(PlanError, match="Invalid time"):
        parse_time("1:2:3:4")
    with pytest.raises(PlanError, match="Invalid time"):
        parse_time("1h30x")


def test_fmt_hms():
    assert fmt_hms(None) == "-"
    assert fmt_hms(0) == "0:00:00"
    assert fmt_hms(59) == "0:00:59"
    assert fmt_hms(61) == "0:01:01"
    assert fmt_hms(3661) == "1:01:01"
    assert fmt_hms(36000) == "10:00:00"


def test_parse_twitch_duration():
    assert parse_twitch_duration("3h2m10s") == 10930
    assert parse_twitch_duration("1h") == 3600
    assert parse_twitch_duration("45m") == 2700
    assert parse_twitch_duration("30s") == 30
    assert parse_twitch_duration("") == 0
