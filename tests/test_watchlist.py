from __future__ import annotations

from pathlib import Path

from core import watchlist
from core.watchlist import WatchedStreamer


def test_watchlist_add_remove_is_watched(tmp_path: Path):
    target = tmp_path / "watchlist.json"
    assert watchlist.load_watchlist(target) == []

    watchlist.add_to_watchlist("shroud", "Shroud", path=target)
    assert watchlist.is_watched("shroud", path=target)
    assert watchlist.is_watched("SHROUD", path=target)
    assert not watchlist.is_watched("tarik", path=target)

    # Adding again doesn't duplicate
    watchlist.add_to_watchlist("shroud", path=target)
    assert len(watchlist.load_watchlist(target)) == 1

    # Remove
    watchlist.remove_from_watchlist("shroud", path=target)
    assert not watchlist.is_watched("shroud", path=target)
    assert len(watchlist.load_watchlist(target)) == 0


def test_watchlist_handles_corrupt_file(tmp_path: Path):
    target = tmp_path / "watchlist.json"
    target.write_text("broken json", encoding="utf-8")
    assert watchlist.load_watchlist(target) == []


def test_watchlist_throttling(tmp_path: Path):
    target = tmp_path / "watchlist.json"
    w = WatchedStreamer(login="streamer", last_vod_id="100", last_checked_at=1000.0)

    class FakeClient:
        called = False

        def get_channel_videos(self, login, first=6):
            self.called = True
            return [{"id": "101", "created_at": "2026-10-28T12:00:00Z"}]

    client = FakeClient()
    # Within 300s throttle: no call
    updated, new_vods = watchlist.check_streamer_new_vods(client, w, throttle_seconds=300, now=1100.0)
    assert not client.called
    assert new_vods == []

    # After throttle: calls client
    updated, new_vods = watchlist.check_streamer_new_vods(client, w, throttle_seconds=300, now=1500.0)
    assert client.called
    assert len(new_vods) == 1
    assert new_vods[0]["id"] == "101"
    assert updated.last_vod_id == "101"


def test_watchlist_first_run_records_baseline_without_toast():
    w = WatchedStreamer(login="streamer", last_vod_id="")

    class FakeClient:
        def get_channel_videos(self, login, first=6):
            return [
                {"id": "202", "created_at": "2026-10-28T10:00:00Z"},
                {"id": "201", "created_at": "2026-10-27T10:00:00Z"},
            ]

    updated, new_vods = watchlist.check_streamer_new_vods(FakeClient(), w, throttle_seconds=0)
    # First time: records top vod without triggering false positive alerts
    assert new_vods == []
    assert updated.last_vod_id == "202"


def test_watchlist_silent_on_client_error():
    w = WatchedStreamer(login="streamer", last_vod_id="100", last_checked_at=0.0)

    class FailingClient:
        def get_channel_videos(self, login, first=6):
            raise RuntimeError("Twitch network failure")

    updated, new_vods = watchlist.check_streamer_new_vods(FailingClient(), w, throttle_seconds=0)
    assert new_vods == []
    # last_checked_at updated to prevent error hammering
    assert updated.last_checked_at > 0


def test_nav_rail_search_badge(qtbot):
    from qt_ui.shell import NavRail
    rail = NavRail()
    qtbot.addWidget(rail)

    assert not rail.search_badge
    rail.set_search_badge(True)
    assert rail.search_badge
    # Button 0 should have dot
    assert "●" in rail.buttons[0].text()

    rail.set_search_badge(False)
    assert not rail.search_badge
    assert "●" not in rail.buttons[0].text()


def test_search_tab_pin_button_toggles_streamer(qtbot, tmp_path, monkeypatch):
    import core.paths as paths
    target = tmp_path / "luckytwitch_watchlist.json"
    monkeypatch.setattr(paths, "WATCHLIST_PATH", target)

    from qt_ui.tabs.search import SearchTab
    tab = SearchTab()
    qtbot.addWidget(tab)

    tab.sv_channel = {"login": "pokimane", "name": "Pokimane"}
    tab._sync_pin()
    assert not tab.pin_btn.isChecked()

    # Click pin
    tab.pin_btn.click()
    assert tab.pin_btn.isChecked()
    assert watchlist.is_watched("pokimane", path=target)

    # Click unpin
    tab.pin_btn.click()
    assert not tab.pin_btn.isChecked()
    assert not watchlist.is_watched("pokimane", path=target)
