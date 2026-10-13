"""Sections downloaded by whole HLS segments: playlist parsing, selection, fallback."""

from pathlib import Path

import pytest

import luckytwitch_engine as eng

BASE = "https://cdn.example.com/abc/chunked/index-muted-XYZ.m3u8"


def make_playlist(n: int = 2627, last: float = 4.851, extra: str = "", ended: bool = True) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:10", "#EXT-X-PLAYLIST-TYPE:EVENT"]
    if extra:
        lines.append(extra)
    for i in range(n):
        lines += [f"#EXTINF:{last if i == n - 1 else 10.0:.3f},", f"{i}.ts"]
    if ended:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


@pytest.fixture
def segs():
    return eng.parse_hls_playlist(make_playlist(), BASE)


def test_parse_durations_and_urls(segs):
    assert len(segs) == 2627
    assert segs[120].start == 1200.0 and segs[120].end == 1210.0
    assert segs[120].url == "https://cdn.example.com/abc/chunked/120.ts"
    assert segs[-1].duration == pytest.approx(4.851)
    assert segs[-1].end == pytest.approx(26264.851)


@pytest.mark.parametrize(
    "bad",
    ['#EXT-X-KEY:METHOD=AES-128,URI="k"', '#EXT-X-MAP:URI="init.mp4"', "#EXT-X-DISCONTINUITY", "#EXT-X-BYTERANGE:100@0"],
)
def test_parse_rejects_unsafe_tags(bad):
    with pytest.raises(ValueError):
        eng.parse_hls_playlist(make_playlist(n=5, extra=bad), BASE)


def test_parse_rejects_live_and_empty():
    with pytest.raises(ValueError):
        eng.parse_hls_playlist(make_playlist(n=5, ended=False), BASE)
    with pytest.raises(ValueError):
        eng.parse_hls_playlist("#EXTM3U\n#EXT-X-ENDLIST\n", BASE)


@pytest.mark.parametrize(
    "start,end,real_start,real_end",
    [
        (1200, 1260, 1200, 1260),
        (1200, 12600, 1200, 12600),   # end on a boundary -> segment 1259, not 1260
        (1203, 1263, 1200, 1270),
        (1199.9, 1260, 1190, 1260),
        (1200, 12601, 1200, 12610),
        (0, 30, 0, 30),
        (-5, 30, 0, 30),
        (26000, 99999, 26000, 26264.851),  # past the end -> clamped
    ],
)
def test_selection(segs, start, end, real_start, real_end):
    a, b = eng.select_segments(segs, start, end)
    assert segs[a].start == pytest.approx(real_start)
    assert segs[b].end == pytest.approx(real_end)


def test_selection_errors(segs):
    with pytest.raises(ValueError):
        eng.select_segments(segs, 30000, 31000)
    with pytest.raises(ValueError):
        eng.select_segments(segs, 100, 100)


def test_local_playlist(segs, tmp_path):
    out = tmp_path / "part.m3u8"
    eng.write_local_playlist(segs[120:123], out)
    text = out.read_text()
    assert text.startswith("#EXTM3U") and text.strip().endswith("#EXT-X-ENDLIST")
    assert "#EXT-X-TARGETDURATION:10" in text
    assert text.count("#EXTINF:10.000,") == 3
    assert "https://cdn.example.com/abc/chunked/120.ts" in text and "\n120.ts" not in text


class FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def _ctx():
    logs = []
    return eng.Ctx(log=logs.append), logs


def test_aligned_success(monkeypatch, tmp_path):
    ctx, _ = _ctx()
    monkeypatch.setattr(eng, "get_playlist_url", lambda c, u: BASE)
    monkeypatch.setattr(eng.requests, "get", lambda *a, **k: FakeResp(make_playlist()))
    seen = {}

    def fake_ffmpeg(c, args, total=None):
        seen["args"], seen["total"] = args, total
        Path(args[-1]).write_bytes(b"x" * 5000)
        return ""

    monkeypatch.setattr(eng, "run_ffmpeg", fake_ffmpeg)
    f, rs, re_ = eng.download_section_aligned(ctx, "u", eng.Part(1, 1203, 1263), tmp_path)
    assert (rs, re_) == (1200.0, 1270.0)
    assert f.name == "part.mp4"
    assert "-ss" not in seen["args"] and "-t" not in seen["args"]
    assert "-protocol_whitelist" in seen["args"]
    assert seen["total"] == 70.0


def test_fallback_when_not_hls(monkeypatch, tmp_path):
    ctx, logs = _ctx()

    def boom(c, u):
        raise eng.EngineError("yt-dlp gave 2 address(es) instead of one playlist")

    monkeypatch.setattr(eng, "get_playlist_url", boom)
    assert eng.download_section_aligned(ctx, "u", eng.Part(1, 0, 60), tmp_path) is None
    assert any("old method" in m for m in logs)


def test_fallback_when_encrypted(monkeypatch, tmp_path):
    ctx, logs = _ctx()
    monkeypatch.setattr(eng, "get_playlist_url", lambda c, u: BASE)
    monkeypatch.setattr(eng.requests, "get", lambda *a, **k: FakeResp(make_playlist(n=5, extra="#EXT-X-KEY:METHOD=AES-128")))
    assert eng.download_section_aligned(ctx, "u", eng.Part(1, 0, 20), tmp_path) is None
    assert logs


def test_cancel_is_not_swallowed(monkeypatch, tmp_path):
    ctx, _ = _ctx()

    def cancelled(c, u):
        raise eng.Cancelled("Cancelled.")

    monkeypatch.setattr(eng, "get_playlist_url", cancelled)
    with pytest.raises(eng.Cancelled):
        eng.download_section_aligned(ctx, "u", eng.Part(1, 0, 60), tmp_path)


# --- wiring in run_job --- #
def _job(tmp_path, exact=False):
    src = eng.SourceInfo(
        url="https://www.twitch.tv/videos/1", id="1", title="T", uploader="Streamer",
        duration=26264.851, date="2026-01-01", twitch_vod_id="1",
    )
    opts = eng.JobOptions(cut_text="0:20:03 - 0:21:03", out_dir=str(tmp_path / "out"), strategy="sections", exact=exact)
    return eng.Job(source=src, opts=opts)


def _patch_run_job(monkeypatch, tmp_path, aligned):
    monkeypatch.setattr(eng, "find_tool", lambda n: "/bin/true")
    calls = {}
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"x" * 5000)
    monkeypatch.setattr(eng, "download_section_aligned", lambda ctx, url, p, wd: aligned(raw))
    monkeypatch.setattr(eng, "download_section", lambda *a, **k: calls.setdefault("old", raw))

    def fake_cut(ctx, f, part, container, workdir, offset=None):
        calls["offset"] = offset
        return raw

    def fake_finalize(ctx, f, stem, container, chapters, tags, total, copy=False):
        calls["total"] = total
        return stem.with_suffix(".mp4")

    monkeypatch.setattr(eng, "cut_exact", fake_cut)
    monkeypatch.setattr(eng, "finalize_part", fake_finalize)
    return calls


def test_run_job_uses_real_start(monkeypatch, tmp_path):
    calls = _patch_run_job(monkeypatch, tmp_path, lambda raw: (raw, 1200.0, 1270.0))
    ctx, logs = _ctx()
    eng.run_job(_job(tmp_path), ctx)
    assert "old" not in calls
    assert calls["total"] == 70.0  # real length of the file, not the asked 60 s
    assert any("starts at 0:20:00" in m and "3 s early" in m for m in logs)


def test_run_job_falls_back_to_old_method(monkeypatch, tmp_path):
    calls = _patch_run_job(monkeypatch, tmp_path, lambda raw: None)
    ctx, _ = _ctx()
    eng.run_job(_job(tmp_path), ctx)
    assert "old" in calls
    assert calls["total"] == 60.0


def test_run_job_exact_cuts_from_the_real_start(monkeypatch, tmp_path):
    calls = _patch_run_job(monkeypatch, tmp_path, lambda raw: (raw, 1200.0, 1270.0))
    ctx, _ = _ctx()
    eng.run_job(_job(tmp_path, exact=True), ctx)
    assert calls["offset"] == 3.0
    assert calls["total"] == 60.0
