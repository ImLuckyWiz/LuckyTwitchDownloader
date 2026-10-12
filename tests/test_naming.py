"""File and folder naming: safe_name, unique_path, part_stem, stream_dir."""

from pathlib import Path

import pytest

from luckytwitch_engine import JobOptions, Part, SourceInfo, part_stem, safe_name, stream_dir, unique_path


def make_src(**kw):
    base = dict(url="https://www.twitch.tv/videos/123", id="v123", title="Big Stream", uploader="Streamer",
                duration=7200.0, date="2026-10-01", twitch_vod_id="123")
    base.update(kw)
    return SourceInfo(**base)


def make_opts(**kw):
    return JobOptions(cut_text="0:00 - end", out_dir="OUT", **kw)


# --------------------------------------------------------------------------- safe_name
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hello World", "Hello World"),
        ("a:b*c?d", "abcd"),
        ('He said "hi" <ok> | x/y\\z', "He said hi ok xyz"),
        ("  lots   of   space  ", "lots of space"),
        ("trailing dots...", "trailing dots"),
        (". leading dot", "leading dot"),
        ("Fun \U0001F602 stream", "Fun stream"),
        ("Ñandú – año", "Ñandú año"),
        ("keep (these) [brackets] - and-dashes", "keep (these) [brackets] - and-dashes"),
        ("???", ""),
    ],
)
def test_safe_name(raw, expected):
    assert safe_name(raw) == expected


# --------------------------------------------------------------------------- unique_path
def test_unique_path_returns_the_same_path_when_free(tmp_path):
    p = tmp_path / "video.mp4"
    assert unique_path(p) == p


def test_unique_path_numbers_the_copies(tmp_path):
    p = tmp_path / "video.mp4"
    p.write_text("x")
    assert unique_path(p) == tmp_path / "video (2).mp4"
    (tmp_path / "video (2).mp4").write_text("x")
    assert unique_path(p) == tmp_path / "video (3).mp4"


# --------------------------------------------------------------------------- part_stem
def test_part_stem_default_template():
    stem = part_stem(make_src(), make_opts(), Part(1, 0, 600), 3)
    assert stem == "Streamer - 2026-10-01 - 123 - part1"


def test_part_stem_all_stream_tokens():
    opts = make_opts(name_template="{streamer}_{date}_{id}_{title}_{n}of{total}_{start}_{end}")
    stem = part_stem(make_src(), opts, Part(2, 3661, 7322), 5)
    assert stem == "Streamer_2026-10-01_123_Big Stream_2of5_01h01m01s_02h02m02s"


def test_part_stem_start_end_tags():
    opts = make_opts(name_template="{start}_{end}")
    assert part_stem(make_src(), opts, Part(1, 3661, 7322), 1) == "01h01m01s_02h02m02s"


def test_part_stem_uses_the_source_id_when_there_is_no_twitch_id():
    stem = part_stem(make_src(twitch_vod_id=None, id="abc"), make_opts(name_template="{id}"), Part(1, 0, 1), 1)
    assert stem == "abc"


def test_part_stem_unknown_token_survives_as_plain_text():
    # unknown {tokens} are kept by the template, then the braces are stripped by safe_name
    assert part_stem(make_src(), make_opts(name_template="{foo} x"), Part(1, 0, 1), 1) == "foo x"


@pytest.mark.parametrize("template", ["{n", "{0}"])
def test_part_stem_broken_template_falls_back(template):
    assert part_stem(make_src(), make_opts(name_template=template), Part(1, 0, 1), 1) == "123 - part1"


def test_part_stem_empty_name_becomes_partN():
    stem = part_stem(make_src(title="", uploader="", date="", twitch_vod_id="9"),
                     make_opts(name_template="???"), Part(2, 0, 1), 2)
    assert stem == "part2"


CLIP = {"title": "Epic fail", "creator_name": "viewer1", "view_count": 12, "id": "ClipId", "duration": 29.6}


def test_part_stem_single_clip_uses_the_clip_template():
    opts = make_opts(clip_name_template="{clip_title} by {creator} ({views}) {clip_duration}s")
    assert part_stem(make_src(), opts, Part(1, 0, 1), 1, CLIP) == "Epic fail by viewer1 (12) 30s"


def test_part_stem_single_clip_can_use_vod_tokens_too():
    opts = make_opts(clip_name_template="{streamer} - {clip_title}")
    assert part_stem(make_src(), opts, Part(1, 0, 1), 1, CLIP) == "Streamer - Epic fail"


def test_part_stem_single_clip_name_is_truncated_to_150_chars():
    clip = {**CLIP, "title": "x" * 400}
    assert len(part_stem(make_src(), make_opts(), Part(1, 0, 1), 1, clip)) == 150


def test_part_stem_single_clip_empty_name_falls_back_to_the_clip_id():
    opts = make_opts(clip_name_template="???")
    assert part_stem(make_src(), opts, Part(1, 0, 1), 1, CLIP) == "clip ClipId"


def test_part_stem_single_clip_untitled():
    clip = {**CLIP, "title": ""}
    assert part_stem(make_src(), make_opts(), Part(1, 0, 1), 1, clip) == "Clip"


# --------------------------------------------------------------------------- stream_dir
def test_stream_dir_default_layout():
    assert stream_dir(make_src(), make_opts()) == Path("OUT") / "Streamer" / "2026-10-01 - Big Stream - 123"


def test_stream_dir_without_subfolders_is_the_output_folder():
    assert stream_dir(make_src(), make_opts(subfolders=False)) == Path("OUT")


def test_stream_dir_cleans_names():
    src = make_src(uploader="Str:eamer?", title="Big *Stream*")
    assert stream_dir(src, make_opts()) == Path("OUT") / "Streamer" / "2026-10-01 - Big Stream - 123"


def test_stream_dir_missing_streamer_becomes_vod():
    assert stream_dir(make_src(uploader=""), make_opts()).parts[-2] == "vod"


def test_stream_dir_broken_template_falls_back_to_date_and_id():
    assert stream_dir(make_src(), make_opts(folder_template="{")).name == "2026-10-01 - 123"


def test_stream_dir_long_names_are_truncated():
    src = make_src(uploader="u" * 200, title="t" * 300)
    p = stream_dir(src, make_opts())
    assert len(p.parts[-2]) == 60
    assert len(p.name) <= 100
