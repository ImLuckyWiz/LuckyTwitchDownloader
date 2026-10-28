"""
Unit tests for core.twitch_api.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.twitch_api import (
    API_URL,
    DEVICE_GRANT,
    DEVICE_URL,
    TOKEN_URL,
    TWITCH_CLIENT_ID,
    TwitchClient,
    _iso_z,
    clip_end,
    clip_start,
)


def test_twitch_api_constants():
    assert TOKEN_URL == "https://id.twitch.tv/oauth2/token"
    assert DEVICE_URL == "https://id.twitch.tv/oauth2/device"
    assert API_URL == "https://api.twitch.tv/helix"
    assert TWITCH_CLIENT_ID == "i00ldktkshoyftnytyijdwtjofhcq9"
    assert DEVICE_GRANT == "urn:ietf:params:oauth:grant-type:device_code"


def test_iso_z_formatting():
    dt = datetime(2026, 10, 28, 5, 30, 0, tzinfo=timezone.utc)
    assert _iso_z(dt) == "2026-10-28T05:30:00Z"


def test_clip_start_and_end():
    # Twitch vod_offset is where the clip ends, so start = vod_offset - duration
    clip = {"vod_offset": 3600, "duration": 30.0}
    assert clip_start(clip) == 3570.0
    assert clip_end(clip) == 3600.0

    # Missing vod_offset returns None
    clip_no_offset = {"vod_offset": None, "duration": 30.0}
    assert clip_start(clip_no_offset) is None
    assert clip_end(clip_no_offset) is None

    # vod_offset smaller than duration clamps start to 0.0
    clip_small_offset = {"vod_offset": 10, "duration": 30.0}
    assert clip_start(clip_small_offset) == 0.0
    assert clip_end(clip_small_offset) == 10.0


def test_twitch_client_init():
    client_app = TwitchClient("my_client_id", "my_secret")
    assert client_app.client_id == "my_client_id"
    assert client_app.client_secret == "my_secret"
    assert not client_app.uses_login

    client_user = TwitchClient("my_client_id", access_token="AT", refresh_token="RT")
    assert client_user.client_id == "my_client_id"
    assert client_user.client_secret == ""
    assert client_user.uses_login
    assert client_user.token == "AT"
    assert client_user.user_refresh == "RT"
