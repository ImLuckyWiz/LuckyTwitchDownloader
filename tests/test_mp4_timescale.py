"""MP4 movie timescale: keep it at 1000 so Premiere Pro can import long parts (see luckytwitch_engine.mp4_flags)."""

import shutil
import struct
import subprocess

import pytest

from luckytwitch_engine import MP4_MOVIE_TIMESCALE, Ctx, finalize_part, mp4_flags, mp4_movie_timescale


def box(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I", 8 + len(body)) + typ + body


def fake_mp4(path, timescale: int, version: int = 0):
    if version == 1:
        mvhd = bytes([1, 0, 0, 0]) + struct.pack(">QQIQ", 0, 0, timescale, 123456789)
    else:
        mvhd = bytes([0, 0, 0, 0]) + struct.pack(">IIII", 0, 0, timescale, 1000)
    path.write_bytes(box(b"ftyp", b"isom" + bytes(4) + b"isom") + box(b"mdat", bytes(100)) + box(b"moov", box(b"mvhd", mvhd + bytes(80))))
    return path


def test_flags_only_for_mp4():
    assert mp4_flags("mp4") == ["-movie_timescale", "1000"]
    assert mp4_flags(".MP4") == ["-movie_timescale", "1000"]
    assert mp4_flags("mkv") == []


@pytest.mark.parametrize("version", [0, 1])
@pytest.mark.parametrize("ts", [1000, 720000])
def test_reads_movie_timescale(tmp_path, ts, version):
    assert mp4_movie_timescale(fake_mp4(tmp_path / "a.mp4", ts, version)) == ts


def test_unreadable_files_give_none(tmp_path):
    assert mp4_movie_timescale(tmp_path / "missing.mp4") is None
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not an mp4 at all")
    assert mp4_movie_timescale(junk) is None


needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed")


@needs_ffmpeg
def test_finalize_part_forces_timescale(tmp_path, monkeypatch):
    import luckytwitch_engine as eng
    monkeypatch.setattr(eng, "find_tool", lambda name: shutil.which(name))
    src = tmp_path / "part.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=128x72:rate=30", "-f", "lavfi", "-i", "sine",
                    "-t", "3", "-c:v", "libx264", "-c:a", "aac", "-movie_timescale", "720000", str(src)], check=True)
    assert mp4_movie_timescale(src) == 720000
    dest = finalize_part(Ctx(), src, tmp_path / "out", "mp4", [], {}, 3.0)
    assert mp4_movie_timescale(dest) == MP4_MOVIE_TIMESCALE
    assert not src.exists()


@needs_ffmpeg
def test_finalize_part_without_need_just_moves(tmp_path, monkeypatch):
    import luckytwitch_engine as eng
    monkeypatch.setattr(eng, "find_tool", lambda name: None)  # would raise if ffmpeg were called
    src = fake_mp4(tmp_path / "part.mp4", 1000)
    dest = finalize_part(Ctx(), src, tmp_path / "out", "mp4", [], {}, 1.0)
    assert dest.exists() and not src.exists()
