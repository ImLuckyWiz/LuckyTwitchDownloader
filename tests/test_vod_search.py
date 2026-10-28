"""
Unit tests for core.vod_search.
"""

from __future__ import annotations

import types

from core.vod_search import (
    VIDEO_TYPES,
    fetch_thumbnail,
    fetch_videos,
    search_channels,
)


def test_video_types_constant():
    assert "archive" in VIDEO_TYPES
    assert "highlight" in VIDEO_TYPES
    assert "upload" in VIDEO_TYPES


def test_search_channels_empty_query():
    client = types.SimpleNamespace()
    assert search_channels(client, "") == []
    assert search_channels(client, "   ") == []
    assert search_channels(client, "@") == []


def test_search_channels_exact_match_sorting():
    fake_data = [
        {"id": "100", "broadcaster_login": "channel_other", "display_name": "Channel Other", "is_live": False},
        {"id": "200", "broadcaster_login": "target_channel", "display_name": "Target Channel", "is_live": True},
    ]

    class FakeClient:
        def get(self, endpoint, params):
            if endpoint == "search/channels":
                return {"data": fake_data}
            if endpoint == "users":
                return {"data": [{"id": "200", "login": "target_channel", "display_name": "Target Channel"}]}
            return {}

    results = search_channels(FakeClient(), "target_channel")
    assert len(results) == 2
    assert results[0]["id"] == "200"
    assert results[0]["login"] == "target_channel"
    assert results[0]["live"] is True


def test_fetch_videos_invalid_type_defaults_to_archive():
    recorded_params = {}

    class FakeClient:
        def get(self, endpoint, params):
            nonlocal recorded_params
            recorded_params = params
            return {"data": []}

    fetch_videos(FakeClient(), "12345", vtype="invalid_type")
    assert recorded_params["type"] == "archive"
    assert recorded_params["user_id"] == "12345"


def test_fetch_thumbnail_empty():
    assert fetch_thumbnail("") is None
