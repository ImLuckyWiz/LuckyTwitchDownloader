"""Chat overlay: the chat of a part drawn as a video (TwitchDownloaderCLI chatrender) for the editor."""

import json
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

import luckytwitch_engine as eng
from luckytwitch_engine import (
    CHAT_RENDER_MODES,
    Cancelled,
    Ctx,
    EngineError,
    JobOptions,
    Part,
    SourceInfo,
    chat_files_for_part,
    chat_render_command,
    chat_render_fps,
    chat_render_output_args,
    chat_render_size,
    parse_render_status,
    render_chat,
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLI is a shebang script")

SRC = SourceInfo(url="https://www.twitch.tv/videos/99", id="99", title="Stream", uploader="Streamer",
                 duration=20000.0, date="2026-10-01", twitch_vod_id="99")


# --------------------------------------------------------------------------- progress lines (real output of the CLI)
def test_render_status_with_percentage_and_time_left():
    got = parse_render_status("[STATUS] - Rendering Video 12% (0h0m1s Elapsed | 0h1m8s Remaining)")
    assert got == ("Rendering Video · 0:01:08 left", pytest.approx(0.12))


def test_render_status_time_left_is_not_shown_at_zero_percent():
    # at 0% the program says «3h14m7s Remaining», which is nonsense
    assert parse_render_status("[STATUS] - Rendering Video 0% (0h0m0s Elapsed | 3h14m7s Remaining)") == (
        "Rendering Video", 0.0)


def test_render_status_phase_without_percentage_is_indeterminate():
    assert parse_render_status("[STATUS] - Fetching Images [1/2]") == ("Fetching Images", None)


def test_render_status_ignores_other_lines():
    assert parse_render_status("[WARNING] - Something odd") is None
    assert parse_render_status("") is None
    assert parse_render_status("Unhandled exception. System.IO.IOException: x") is None


# --------------------------------------------------------------------------- size and frame rate
@pytest.mark.parametrize("w, h, video_h, expected", [
    (400, 0, 1080, (400, 1080)),  # height 0 = the video's
    (400, 0, 720, (400, 720)),
    (400, 0, None, (400, 1080)),  # video not readable
    (401, 601, 1080, (400, 600)),  # H.264 needs even numbers
    (0, 500, 1080, (400, 500)),  # nonsense width -> default
    (5, 5, 1080, (100, 100)),
    (99999, 99999, 1080, (3840, 4320)),
])
def test_chat_render_size(w, h, video_h, expected):
    assert chat_render_size(w, h, video_h) == expected


@pytest.mark.parametrize("option, video_fps, expected", [
    (0, 30.0, 30), (0, 29.97, 30), (0, 60.0, 60), (0, 59.94, 60), (0, None, 30), (30, 60.0, 30), (60, 30.0, 60),
    (999, 30.0, 120),
])
def test_chat_render_fps(option, video_fps, expected):
    assert chat_render_fps(option, video_fps) == expected


# --------------------------------------------------------------------------- the command line
def test_output_args_per_type():
    assert chat_render_output_args("transparent") == '-c:v qtrle -pix_fmt argb "{save_path}"'
    assert "prores_ks -profile:v 4444 -pix_fmt yuva444p10le" in chat_render_output_args("prores")
    assert "libx264" in chat_render_output_args("compact") and "yuv420p" in chat_render_output_args("compact")
    assert set(CHAT_RENDER_MODES) == {"transparent", "prores", "compact"}


@pytest.mark.parametrize("mode", CHAT_RENDER_MODES)
def test_output_args_never_use_t_because_it_crashes_the_program(mode):
    # ffmpeg -t closes the pipe early and TwitchDownloaderCLI dies with a broken pipe (found by trying it)
    assert " -t " not in " " + chat_render_output_args(mode, 0.4) + " "


def test_output_args_skip_the_lead_at_the_start():
    assert chat_render_output_args("transparent", 0.4).startswith("-ss 0.400 -c:v qtrle")
    assert chat_render_output_args("transparent", 0.0).startswith("-c:v qtrle")
    assert chat_render_output_args("transparent", 0.001).startswith("-c:v qtrle")  # not worth a re-trim


def command(tmp_path, **kw):
    args = dict(mode="transparent", look="outline", width=400, height=1080, font_size=18, fps=30, smooth=False,
                ffmpeg="/opt/ffmpeg", cache_dir=tmp_path / "cache")
    args.update(kw)
    return chat_render_command("tdcli", tmp_path / "in.chat.json", tmp_path / "out.mov", **args)


def value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_command_basics(tmp_path):
    cmd = command(tmp_path)
    assert cmd[:2] == ["tdcli", "chatrender"]
    assert value(cmd, "-i").endswith("in.chat.json") and value(cmd, "-o").endswith("out.mov")
    assert (value(cmd, "--chat-width"), value(cmd, "--chat-height")) == ("400", "1080")
    assert value(cmd, "--framerate") == "30" and value(cmd, "--font-size") == "18"
    assert value(cmd, "--collision") == "Overwrite"  # a prompt would hang the queue
    assert value(cmd, "--ffmpeg-path") == "/opt/ffmpeg"
    assert "--banner=false" in cmd and value(cmd, "--temp-path").endswith("cache")


def test_the_output_args_travel_in_one_argument_with_an_equals_sign(tmp_path):
    # a value that starts with «-» would be read as an option of its own («Option 'c' is unknown»)
    cmd = command(tmp_path, mode="prores", ffmpeg=None)
    args = [a for a in cmd if a.startswith("--output-args=")]
    assert len(args) == 1 and args[0].endswith('"{save_path}"')
    assert "--output-args" not in cmd and "--ffmpeg-path" not in cmd


def test_transparent_look_outline_has_no_background_and_an_outline(tmp_path):
    cmd = command(tmp_path, look="outline")
    assert value(cmd, "--background-color") == "#00000000" and "--outline" in cmd


def test_transparent_look_panel_is_a_see_through_dark_panel(tmp_path):
    cmd = command(tmp_path, look="panel")
    assert value(cmd, "--background-color") == "#B3000000" and "--outline" not in cmd


def test_the_black_background_type_is_solid_black_whatever_the_look(tmp_path):
    for look in ("outline", "panel"):
        cmd = command(tmp_path, mode="compact", look=look)
        assert value(cmd, "--background-color") == "#000000" and "--outline" not in cmd


def test_smooth_scrolling_redraws_every_frame(tmp_path):
    assert value(command(tmp_path, smooth=False), "--update-rate") == "0.2"
    assert value(command(tmp_path, smooth=True), "--update-rate") == "0"


def test_font_size_is_kept_sane(tmp_path):
    assert value(command(tmp_path, font_size=0), "--font-size") == "18"
    assert value(command(tmp_path, font_size=1), "--font-size") == "6"
    assert value(command(tmp_path, font_size=500), "--font-size") == "96"


# --------------------------------------------------------------------------- running it (fake CLI)
FAKE = r"""#!{py}
import json, sys, time
args = sys.argv[1:]
mode = args[0]
out = args[args.index('-o') + 1]
log = {log!r}
with open(log, 'a') as f:
    f.write(json.dumps(args) + "\n")
{body}
"""


def fake_cli(tmp_path: Path, chatdownload: str = "open(out, 'w').write('{}')", chatrender: str = "open(out, 'wb').write(b'video')"):
    """A script that behaves like TwitchDownloaderCLI. Every call is logged (as JSON) in tmp_path/calls.log."""
    body = f"if mode == 'chatdownload':\n    {chatdownload}\nelif mode == 'chatrender':\n    {chatrender}\n"
    script = tmp_path / "fake_tdcli"
    script.write_text(FAKE.format(py=sys.executable, log=str(tmp_path / "calls.log"), body=body), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def calls(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "calls.log"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def make_ctx():
    logs = []
    ctx = Ctx(log=logs.append, progress=lambda f, t: None)
    ctx.stage(0.0, 1.0, "Finishing")
    return ctx, logs


RENDER_KW = dict(mode="transparent", look="outline", width=400, height=1080, font_size=18, fps=30, smooth=False)


@posix_only
def test_render_chat_success(tmp_path):
    cli = fake_cli(tmp_path, chatrender=(
        "print('[STATUS] - Fetching Images [1/2]', flush=True)\n"
        "    print('[STATUS] - Rendering Video 50% (0h0m1s Elapsed | 0h0m1s Remaining)', flush=True)\n"
        "    print('[WARNING] - Failed to fetch 7TV emotes', flush=True)\n"
        "    open(out, 'wb').write(b'video')"))
    ctx, logs = make_ctx()
    (tmp_path / "in.json").write_text("{}")
    got = render_chat(ctx, cli, tmp_path / "in.json", tmp_path / "videos" / "p.chat-overlay.mov",
                      cache_dir=tmp_path / "cache", **RENDER_KW)
    assert got == tmp_path / "videos" / "p.chat-overlay.mov" and got.read_bytes() == b"video"
    assert any("Failed to fetch 7TV emotes" in m and m.startswith("Warning") for m in logs)  # the person hears of it


@posix_only
def test_render_chat_does_not_overwrite_an_existing_file(tmp_path):
    cli = fake_cli(tmp_path)
    ctx, _ = make_ctx()
    dest = tmp_path / "p.chat-overlay.mov"
    dest.write_bytes(b"old")
    got = render_chat(ctx, cli, tmp_path / "in.json", dest, cache_dir=tmp_path / "cache", **RENDER_KW)
    assert dest.read_bytes() == b"old" and got.name == "p.chat-overlay (2).mov" and got.read_bytes() == b"video"


@posix_only
def test_render_chat_failure_reports_the_reason_and_removes_the_file(tmp_path):
    cli = fake_cli(tmp_path, chatrender=(
        "open(out, 'wb').write(b'half')\n"
        "    print('[ERROR] - ffmpeg could not be found')\n"
        "    sys.exit(1)"))
    ctx, _ = make_ctx()
    dest = tmp_path / "p.chat-overlay.mov"
    with pytest.raises(EngineError) as e:
        render_chat(ctx, cli, tmp_path / "in.json", dest, cache_dir=tmp_path / "cache", **RENDER_KW)
    assert "Chat render failed" in str(e.value) and "ffmpeg could not be found" in str(e.value)
    assert not dest.exists()


@posix_only
def test_render_chat_empty_output_is_an_error(tmp_path):
    cli = fake_cli(tmp_path, chatrender="open(out, 'wb').close()")
    ctx, _ = make_ctx()
    with pytest.raises(EngineError):
        render_chat(ctx, cli, tmp_path / "in.json", tmp_path / "p.mov", cache_dir=tmp_path / "cache", **RENDER_KW)
    assert not (tmp_path / "p.mov").exists()


@posix_only
def test_render_chat_cancel_stops_the_process_and_removes_the_file(tmp_path):
    cli = fake_cli(tmp_path, chatrender=(
        "open(out, 'wb').write(b'half')\n"
        "    print('[STATUS] - Rendering Video 10% (0h0m1s Elapsed | 0h9m0s Remaining)', flush=True)\n"
        "    time.sleep(60)"))
    ctx, _ = make_ctx()
    dest = tmp_path / "p.mov"
    threading.Timer(1.0, ctx.cancel).start()
    t0 = time.monotonic()
    with pytest.raises(Cancelled):
        render_chat(ctx, cli, tmp_path / "in.json", dest, cache_dir=tmp_path / "cache", **RENDER_KW)
    assert time.monotonic() - t0 < 20 and not dest.exists()


# --------------------------------------------------------------------------- the whole thing for one part
def part_file(tmp_path: Path) -> Path:
    dest = tmp_path / "out" / "Streamer - part1.mp4"
    dest.parent.mkdir()
    dest.write_bytes(b"not a real video")  # ffprobe cannot read it: size and frame rate fall back to the defaults
    return dest


def run_part(tmp_path, cli, real_start=3600.0, real_end=3720.0, **opts):
    ctx, logs = make_ctx()
    options = JobOptions(cut_text="", out_dir=str(tmp_path), **opts)
    dest = part_file(tmp_path)
    chat_files_for_part(ctx, cli, SRC, options, Part(1, real_start, real_end), 1, dest, real_start, real_end,
                        tmp_path / "work")
    return dest, logs


def names(dest: Path) -> list[str]:
    return sorted(p.name for p in dest.parent.iterdir())


@posix_only
def test_with_the_json_chat_the_chat_is_downloaded_once_and_used_for_the_overlay(tmp_path):
    cli = fake_cli(tmp_path)
    dest, logs = run_part(tmp_path, cli, chat=True, chat_render=True)
    assert [c[0] for c in calls(tmp_path)] == ["chatdownload", "chatrender"]
    assert names(dest) == ["Streamer - part1.chat-overlay.mov", "Streamer - part1.chat.json", "Streamer - part1.mp4"]
    render = calls(tmp_path)[1]
    assert value(render, "-i").endswith("Streamer - part1.chat.json")  # drawn from the saved file
    assert any(m.startswith("✔ Streamer - part1.chat-overlay.mov") and "400x1080, 30 fps" in m for m in logs)


@posix_only
def test_overlay_only_downloads_a_temporary_chat_and_removes_it(tmp_path):
    cli = fake_cli(tmp_path)
    dest, _ = run_part(tmp_path, cli, chat=False, chat_render=True)
    assert [c[0] for c in calls(tmp_path)] == ["chatdownload", "chatrender"]
    assert names(dest) == ["Streamer - part1.chat-overlay.mov", "Streamer - part1.mp4"]  # no .chat.json left over
    assert not list((tmp_path / "work").rglob("*.json"))


@posix_only
def test_with_an_html_chat_the_overlay_gets_its_own_json(tmp_path):
    cli = fake_cli(tmp_path)
    dest, _ = run_part(tmp_path, cli, chat=True, chat_format="html", chat_render=True)
    got = calls(tmp_path)
    assert [c[0] for c in got] == ["chatdownload", "chatdownload", "chatrender"]
    assert value(got[0], "-o").endswith(".chat.html") and value(got[1], "-o").endswith(".chat.json")
    assert names(dest) == ["Streamer - part1.chat-overlay.mov", "Streamer - part1.chat.html", "Streamer - part1.mp4"]


@posix_only
def test_chat_only_does_not_render_anything(tmp_path):
    cli = fake_cli(tmp_path)
    dest, _ = run_part(tmp_path, cli, chat=True)
    assert [c[0] for c in calls(tmp_path)] == ["chatdownload"]
    assert names(dest) == ["Streamer - part1.chat.json", "Streamer - part1.mp4"]


@posix_only
def test_the_black_background_overlay_is_an_mp4(tmp_path):
    cli = fake_cli(tmp_path)
    dest, _ = run_part(tmp_path, cli, chat_render=True, chat_render_mode="compact")
    assert "Streamer - part1.chat-overlay.mp4" in names(dest)


@posix_only
def test_unknown_values_fall_back_to_the_defaults(tmp_path):
    cli = fake_cli(tmp_path)
    dest, _ = run_part(tmp_path, cli, chat_render=True, chat_render_mode="nonsense", chat_render_look="nonsense")
    render = calls(tmp_path)[-1]
    assert "--outline" in render and value(render, "--background-color") == "#00000000"
    assert "Streamer - part1.chat-overlay.mov" in names(dest)


@posix_only
def test_the_overlay_is_lined_up_with_a_part_that_starts_between_two_seconds(tmp_path):
    cli = fake_cli(tmp_path)
    run_part(tmp_path, cli, real_start=3600.4, real_end=3720.0, chat_render=True)
    render = calls(tmp_path)[-1]
    assert chat_render_output_args("transparent", 0.4) in value_of_equals(render, "--output-args")
    chat_dl = calls(tmp_path)[0]
    assert value(chat_dl, "-b") == "3600s"  # the chat file begins at the whole second before the part


def value_of_equals(cmd, flag):
    return next(a for a in cmd if a.startswith(flag + "="))[len(flag) + 1:]


@posix_only
def test_a_part_that_starts_on_a_whole_second_needs_no_trim(tmp_path):
    cli = fake_cli(tmp_path)
    run_part(tmp_path, cli, real_start=3600.0, real_end=3720.0, chat_render=True)
    assert "-ss" not in value_of_equals(calls(tmp_path)[-1], "--output-args")


@posix_only
def test_size_and_frame_rate_follow_the_video(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "probe_video", lambda p: (60.0, 2560, 1440))
    cli = fake_cli(tmp_path)
    run_part(tmp_path, cli, chat_render=True)
    render = calls(tmp_path)[-1]
    assert (value(render, "--chat-width"), value(render, "--chat-height"), value(render, "--framerate")) == ("400", "1440", "60")


@posix_only
def test_settings_that_were_chosen_win_over_the_video(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "probe_video", lambda p: (60.0, 2560, 1440))
    cli = fake_cli(tmp_path)
    run_part(tmp_path, cli, chat_render=True, chat_render_width=500, chat_render_height=900, chat_render_fps=30,
             chat_render_font_size=24, chat_render_smooth=True, chat_render_look="panel")
    render = calls(tmp_path)[-1]
    assert (value(render, "--chat-width"), value(render, "--chat-height"), value(render, "--framerate")) == ("500", "900", "30")
    assert value(render, "--font-size") == "24" and value(render, "--update-rate") == "0"
    assert value(render, "--background-color") == "#B3000000"


@posix_only
def test_if_the_chat_cannot_be_downloaded_the_overlay_is_skipped_and_the_video_is_fine(tmp_path):
    cli = fake_cli(tmp_path, chatdownload="print('[ERROR] - Invalid VOD'); sys.exit(1)")
    dest, logs = run_part(tmp_path, cli, chat=True, chat_render=True)
    assert [c[0] for c in calls(tmp_path)] == ["chatdownload"]  # no second try, no render
    assert names(dest) == ["Streamer - part1.mp4"]
    assert any("Chat for part 1 failed" in m for m in logs) and any("overlay for part 1 skipped" in m for m in logs)


@posix_only
def test_overlay_only_with_a_chat_that_cannot_be_downloaded_is_a_logged_failure(tmp_path):
    cli = fake_cli(tmp_path, chatdownload="print('[ERROR] - Invalid VOD'); sys.exit(1)")
    dest, logs = run_part(tmp_path, cli, chat_render=True)
    assert names(dest) == ["Streamer - part1.mp4"]
    assert any("Chat overlay for part 1 failed (the video is fine)" in m for m in logs)


@posix_only
def test_a_failed_render_keeps_the_saved_chat_and_the_temporary_file_goes_away(tmp_path):
    cli = fake_cli(tmp_path, chatrender="print('[ERROR] - no space left'); sys.exit(1)")
    dest, logs = run_part(tmp_path, cli, chat=True, chat_format="txt", chat_render=True)
    assert names(dest) == ["Streamer - part1.chat.txt", "Streamer - part1.mp4"]
    assert not list((tmp_path / "work").rglob("*.json"))
    assert any("Chat overlay for part 1 failed (the video is fine)" in m and "no space left" in m for m in logs)


@posix_only
def test_cancelling_during_the_render_propagates_and_cleans_up(tmp_path):
    cli = fake_cli(tmp_path, chatrender="open(out, 'wb').write(b'half'); time.sleep(60)")
    ctx, _ = make_ctx()
    options = JobOptions(cut_text="", out_dir=str(tmp_path), chat_render=True)
    dest = part_file(tmp_path)
    threading.Timer(1.5, ctx.cancel).start()
    with pytest.raises(Cancelled):
        chat_files_for_part(ctx, cli, SRC, options, Part(1, 0.0, 60.0), 1, dest, 0.0, 60.0, tmp_path / "work")
    assert names(dest) == ["Streamer - part1.mp4"]
    assert not list((tmp_path / "work").rglob("*.json"))


@posix_only
def test_progress_stays_inside_the_share_of_the_part(tmp_path):
    cli = fake_cli(tmp_path, chatrender=(
        "print('[STATUS] - Rendering Video 50% (0h0m1s Elapsed | 0h0m1s Remaining)', flush=True)\n"
        "    open(out, 'wb').write(b'video')"))
    seen = []
    ctx = Ctx(log=lambda m: None, progress=lambda f, t: seen.append(f))
    ctx.stage(0.4, 0.6, "Finishing part 1/1")
    options = JobOptions(cut_text="", out_dir=str(tmp_path), chat=True, chat_render=True)
    chat_files_for_part(ctx, cli, SRC, options, Part(1, 0.0, 60.0), 1, part_file(tmp_path), 0.0, 60.0, tmp_path / "work")
    real = [f for f in seen if f >= 0]
    assert real and min(real) >= 0.4 - 1e-9 and max(real) <= 0.6 + 1e-9
    assert max(real) > 0.5  # the render moved the bar through the rest of the share


def test_the_new_options_are_off_by_default():
    o = JobOptions(cut_text="", out_dir="")
    assert o.chat_render is False and o.chat_render_mode == "transparent" and o.chat_render_look == "outline"
    assert (o.chat_render_width, o.chat_render_height, o.chat_render_fps) == (400, 0, 0)
