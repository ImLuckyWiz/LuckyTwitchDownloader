"""Tests for Phase 3: Audio-only engine support."""

import json
from pathlib import Path

import pytest

import luckytwitch_engine as eng

FIXTURE_SHORT = Path("tests/fixtures/vod_single_game_short.json")
BASE = "https://cdn.example.com/abc/chunked/index-muted-XYZ.m3u8"


def load_fixture(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _ctx():
    logs = []
    return eng.Ctx(log=logs.append), logs


class FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def make_playlist(n: int = 5, last: float = 10.0) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:10", "#EXT-X-PLAYLIST-TYPE:EVENT"]
    for i in range(n):
        lines += [f"#EXTINF:{last if i == n - 1 else 10.0:.3f},", f"{i}.ts"]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


# --- 1. audio_out_container & audio_codec_args --- #

def test_audio_out_container():
    opts_mp3 = eng.JobOptions(cut_text="0-10", out_dir=".", audio_format="mp3")
    assert eng.audio_out_container(opts_mp3) == "mp3"

    opts_m4a = eng.JobOptions(cut_text="0-10", out_dir=".", audio_format="m4a")
    assert eng.audio_out_container(opts_m4a) == "m4a"

    opts_ogg = eng.JobOptions(cut_text="0-10", out_dir=".", audio_format="ogg")
    assert eng.audio_out_container(opts_ogg) == "m4a"

    opts_empty = eng.JobOptions(cut_text="0-10", out_dir=".", audio_format="")
    assert eng.audio_out_container(opts_empty) == "m4a"


def test_audio_codec_args():
    assert eng.audio_codec_args("mp3") == ["-c:a", "libmp3lame", "-b:a", "192k"]
    assert eng.audio_codec_args("m4a") == ["-c:a", "copy"]
    assert eng.audio_codec_args("other") == ["-c:a", "copy"]


# --- 2. audio_only_options --- #

def test_audio_only_options():
    original = eng.JobOptions(
        cut_text="0-10",
        out_dir=".",
        exact=True,
        premiere_plugin=True,
        chat_render=True,
        game_markers=True,
        chat=True,
        chapters=True,
    )
    stripped, skipped = eng.audio_only_options(original)

    # 4 active video-only options
    assert set(skipped) == {"frame-exact cuts", "Premiere plugin markers", "chat overlay video", "game markers"}
    assert stripped.exact is False
    assert stripped.premiere_plugin is False
    assert stripped.chat_render is False
    assert stripped.game_markers is False
    assert stripped.premiere_xml is False
    assert stripped.muted_markers is False

    # Video-agnostic options preserved
    assert stripped.chat is True
    assert stripped.chapters is True

    # Original object not modified
    assert original.exact is True
    assert original.premiere_plugin is True
    assert original.chat_render is True
    assert original.game_markers is True


def test_audio_only_options_none_active():
    original = eng.JobOptions(cut_text="0-10", out_dir=".")
    stripped, skipped = eng.audio_only_options(original)
    assert skipped == []
    assert stripped == original


# --- 3. finalize_audio_part --- #

def test_finalize_audio_part_m4a_from_mp4(monkeypatch, tmp_path):
    seen = {}

    def fake_ffmpeg(ctx, args, total=None):
        seen["args"] = args
        Path(args[-1]).write_bytes(b"audio")

    monkeypatch.setattr(eng, "run_ffmpeg", fake_ffmpeg)

    src = tmp_path / "part.mp4"
    src.write_bytes(b"data")
    dest_stem = tmp_path / "out" / "Streamer - Stream"
    ctx, _ = _ctx()

    dest = eng.finalize_audio_part(ctx, src, dest_stem, "m4a", chapters=[], tags={}, total=60.0)
    assert dest.suffix == ".m4a"
    assert seen["args"] == ["-i", str(src), "-map", "0:a:0", "-c:a", "copy", str(dest)]


def test_finalize_audio_part_mp3(monkeypatch, tmp_path):
    seen = {}

    def fake_ffmpeg(ctx, args, total=None):
        seen["args"] = args
        Path(args[-1]).write_bytes(b"audio")

    monkeypatch.setattr(eng, "run_ffmpeg", fake_ffmpeg)

    src = tmp_path / "part.m4a"
    src.write_bytes(b"data")
    dest_stem = tmp_path / "out" / "Streamer - Stream"
    ctx, _ = _ctx()

    dest = eng.finalize_audio_part(ctx, src, dest_stem, "mp3", chapters=[], tags={}, total=60.0)
    assert dest.suffix == ".mp3"
    assert seen["args"] == [
        "-i", str(src),
        "-map", "0:a:0",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-id3v2_version", "3",
        str(dest),
    ]


def test_finalize_audio_part_with_chapters(monkeypatch, tmp_path):
    seen = {}

    def fake_ffmpeg(ctx, args, total=None):
        seen["args"] = args
        Path(args[-1]).write_bytes(b"audio")

    monkeypatch.setattr(eng, "run_ffmpeg", fake_ffmpeg)

    src = tmp_path / "part.m4a"
    src.write_bytes(b"data")
    dest_stem = tmp_path / "out" / "Streamer - Stream"
    ctx, _ = _ctx()

    chs = [eng.Chapter(0.0, 30.0, "Intro", []), eng.Chapter(30.0, 60.0, "Game", [])]
    dest = eng.finalize_audio_part(ctx, src, dest_stem, "m4a", chapters=chs, tags={"title": "Test"}, total=60.0)

    meta = src.with_suffix(".ffmeta")
    assert meta.exists()
    assert "-map_chapters" in seen["args"]
    assert "-map_metadata" in seen["args"]
    assert dest.suffix == ".m4a"


def test_finalize_audio_part_m4a_from_m4a_fast_move(monkeypatch, tmp_path):
    ffmpeg_called = []
    monkeypatch.setattr(eng, "run_ffmpeg", lambda *a, **k: ffmpeg_called.append(True))

    src = tmp_path / "part.m4a"
    src.write_bytes(b"aac data")
    dest_stem = tmp_path / "out" / "Streamer - Stream"
    ctx, _ = _ctx()

    dest = eng.finalize_audio_part(ctx, src, dest_stem, "m4a", chapters=[], tags={}, total=60.0)
    assert dest.suffix == ".m4a"
    assert dest.exists()
    assert not src.exists()  # moved!
    assert not ffmpeg_called


def test_finalize_audio_part_unique_path(monkeypatch, tmp_path):
    monkeypatch.setattr(eng, "run_ffmpeg", lambda c, a, total=None: Path(a[-1]).write_bytes(b"data"))

    dest_stem = tmp_path / "out" / "Streamer - Stream"
    dest_stem.parent.mkdir(parents=True)
    existing = dest_stem.parent / f"{dest_stem.name}.m4a"
    existing.write_bytes(b"existing")

    src = tmp_path / "part.mp4"
    src.write_bytes(b"src")
    ctx, _ = _ctx()

    dest = eng.finalize_audio_part(ctx, src, dest_stem, "m4a", chapters=[], tags={}, total=60.0)
    assert dest.name == "Streamer - Stream (2).m4a"
    assert dest.exists()
    assert existing.exists()


# --- 4. download_section_aligned with audio_only=True --- #

def test_download_section_aligned_audio_only(monkeypatch, tmp_path):
    ctx, _ = _ctx()
    monkeypatch.setattr(eng, "get_playlist_url", lambda c, u, **k: BASE)
    monkeypatch.setattr(eng.requests, "get", lambda *a, **k: FakeResp(make_playlist()))
    seen = {}

    def fake_ffmpeg(c, args, total=None):
        seen["args"] = args
        Path(args[-1]).write_bytes(b"x" * 5000)

    monkeypatch.setattr(eng, "run_ffmpeg", fake_ffmpeg)

    part = eng.Part(1, 0, 30)
    f, rs, re_ = eng.download_section_aligned(ctx, "https://twitch.tv/videos/1", part, tmp_path, audio_only=True)
    assert f.name == "part.m4a"
    assert "-map" in seen["args"]
    assert "0:a:0" in seen["args"]
    assert "0:v:0" not in seen["args"]


# --- 5. split_copy with audio_only=True --- #

def test_split_copy_audio_only(monkeypatch, tmp_path):
    ctx, _ = _ctx()
    full = tmp_path / "full.m4a"
    full.write_bytes(b"x" * 5000)
    seen = {}

    def fake_ffmpeg(c, args, total=None):
        seen["args"] = args
        list_idx = args.index("-segment_list") + 1
        list_path = Path(args[list_idx])
        list_path.write_text("seg_000.m4a,0.000,10.000\nseg_001.m4a,10.000,20.000\n", encoding="utf-8")
        seg_dir = list_path.parent
        (seg_dir / "seg_000.m4a").write_bytes(b"x" * 1000)
        (seg_dir / "seg_001.m4a").write_bytes(b"x" * 1000)

    monkeypatch.setattr(eng, "run_ffmpeg", fake_ffmpeg)

    parts = [eng.Part(1, 0, 10), eng.Part(2, 10, 20)]
    res = eng.split_copy(ctx, full, parts, 20.0, "m4a", tmp_path, audio_only=True)

    assert len(res) == 2
    cmd = seen["args"]
    assert "0:a:0" in cmd
    assert "0:v:0" not in cmd
    assert "-segment_format" in cmd
    sf_idx = cmd.index("-segment_format")
    assert cmd[sf_idx + 1] == "mp4"


# --- 6. run_job end to end with audio_only --- #

def test_run_job_audio_only_end_to_end(monkeypatch, tmp_path):
    formats = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    src = eng.SourceInfo(
        url="https://www.twitch.tv/videos/1",
        id="1",
        title="Audio Stream",
        uploader="Streamer",
        duration=3600.0,
        date="2026-01-01",
        twitch_vod_id="1",
        formats=formats,
    )
    opts = eng.JobOptions(
        cut_text="0:00:00 - 0:01:00",
        out_dir=str(tmp_path / "out"),
        strategy="sections",
        quality=eng.QUALITY_AUDIO,
        audio_format="mp3",
        exact=True,
        premiere_plugin=True,
        chat_render=True,
        chapters=False,
    )
    job = eng.Job(source=src, opts=opts)

    monkeypatch.setattr(eng, "find_tool", lambda n: "/bin/true")
    raw = tmp_path / "raw.m4a"
    raw.write_bytes(b"x" * 5000)

    calls = {"finalize_audio": 0, "finalize_video": 0, "markers_json": 0, "premiere_xml": 0}

    def fake_aligned(ctx, url, part, workdir, **kw):
        return raw, 0.0, 60.0

    monkeypatch.setattr(eng, "download_section_aligned", fake_aligned)

    def fake_finalize_audio(ctx, src_file, dest_stem, container, chapters, tags, total, copy=False):
        calls["finalize_audio"] += 1
        calls["audio_container"] = container
        return dest_stem.parent / f"{dest_stem.name}.{container}"

    def fake_finalize_video(*a, **k):
        calls["finalize_video"] += 1
        return tmp_path / "video.mp4"

    monkeypatch.setattr(eng, "finalize_audio_part", fake_finalize_audio)
    monkeypatch.setattr(eng, "finalize_part", fake_finalize_video)
    monkeypatch.setattr(eng, "write_markers_json", lambda *a, **k: calls.update({"markers_json": calls["markers_json"] + 1}))
    monkeypatch.setattr(eng, "write_premiere_xml", lambda *a, **k: calls.update({"premiere_xml": calls["premiere_xml"] + 1}))

    ctx, logs = _ctx()
    results = eng.run_job(job, ctx)

    assert len(results) == 1
    assert results[0].suffix == ".mp3"
    assert calls["finalize_audio"] == 1
    assert calls["audio_container"] == "mp3"
    assert calls["finalize_video"] == 0
    assert calls["markers_json"] == 0
    assert calls["premiere_xml"] == 0

    assert any("Audio only: skipped" in line for line in logs)
    assert any("frame-exact cuts" in line for line in logs)
    assert any("Quality: Audio only" in line for line in logs)


def test_run_job_audio_only_full_strategy_and_keep_full(monkeypatch, tmp_path):
    formats = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    src = eng.SourceInfo(
        url="https://www.twitch.tv/videos/1",
        id="1",
        title="Full Audio Stream",
        uploader="Streamer",
        duration=3600.0,
        date="2026-01-01",
        twitch_vod_id="1",
        formats=formats,
    )
    opts = eng.JobOptions(
        cut_text="0:00:00 - 0:01:00 ; 0:05:00 - 0:06:00",
        out_dir=str(tmp_path / "out"),
        strategy="full",
        quality=eng.QUALITY_AUDIO,
        audio_format="m4a",
        keep_full=True,
    )
    job = eng.Job(source=src, opts=opts)

    monkeypatch.setattr(eng, "find_tool", lambda n: "/bin/true")
    full_mp4 = tmp_path / "full.mp4"
    full_mp4.write_bytes(b"x" * 5000)

    monkeypatch.setattr(eng, "download_full", lambda *a, **k: full_mp4)

    split_calls = {}

    def fake_split(ctx, full, parts, duration, container, workdir, **kw):
        split_calls["container"] = container
        split_calls.update(kw)
        p1 = tmp_path / "seg_000.m4a"
        p2 = tmp_path / "seg_001.m4a"
        p1.write_bytes(b"1")
        p2.write_bytes(b"2")
        return {1: (p1, 0.0, 60.0), 2: (p2, 300.0, 360.0)}

    monkeypatch.setattr(eng, "split_copy", fake_split)

    def fake_finalize_audio(ctx, src_file, dest_stem, container, chapters, tags, total, copy=False):
        return dest_stem.parent / f"{dest_stem.name}.{container}"

    monkeypatch.setattr(eng, "finalize_audio_part", fake_finalize_audio)

    ctx, logs = _ctx()
    results = eng.run_job(job, ctx)

    assert len(results) == 2
    assert split_calls["container"] == "m4a"
    assert split_calls.get("audio_only") is True

    # "Keep the full VOD" -> saved as .m4a because full was .mp4 and audio_only is True
    kept_files = [p for p in (tmp_path / "out").rglob("*- FULL.*") if p.is_file()]
    assert len(kept_files) == 1
    assert kept_files[0].suffix == ".m4a"


def test_video_job_uses_finalize_part(monkeypatch, tmp_path):
    formats = eng.parse_formats(load_fixture(FIXTURE_SHORT).get("formats"))
    src = eng.SourceInfo(
        url="https://www.twitch.tv/videos/1",
        id="1",
        title="Video Stream",
        uploader="Streamer",
        duration=3600.0,
        date="2026-01-01",
        twitch_vod_id="1",
        formats=formats,
    )
    opts = eng.JobOptions(
        cut_text="0:00:00 - 0:01:00",
        out_dir=str(tmp_path / "out"),
        strategy="sections",
        quality="720p",
    )
    job = eng.Job(source=src, opts=opts)

    monkeypatch.setattr(eng, "find_tool", lambda n: "/bin/true")
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"x" * 5000)

    calls = {"audio": 0, "video": 0}

    monkeypatch.setattr(eng, "download_section_aligned", lambda ctx, u, p, wd, **kw: (raw, 0.0, 60.0))
    monkeypatch.setattr(eng, "finalize_part", lambda *a, **k: (calls.update({"video": calls["video"] + 1}), raw)[1])
    monkeypatch.setattr(eng, "finalize_audio_part", lambda *a, **k: (calls.update({"audio": calls["audio"] + 1}), raw)[1])

    ctx, _ = _ctx()
    eng.run_job(job, ctx)

    assert calls["video"] == 1
    assert calls["audio"] == 0
