# Quality selection and audio-only: implementation plan

Written to be executed by a smaller model (Gemini Flash), one phase at a time. Read the whole file once, then work
phase by phase. Every phase ends green (`python -m pytest tests -q`) before the next one starts.

## 1. What we are building

1. **Quality selection.** For a Twitch VOD, the person picks one of the qualities Twitch offers (for example
   `1080p60 (Source)`, `720p60`, `480p`, `360p`, `160p`) instead of always getting the best one.
2. **Audio only.** Twitch also offers an `Audio_Only` quality. It becomes a download option, saved either as
   **`.m4a`** (Twitch's AAC audio copied untouched) or **`.mp3`** (converted with ffmpeg).

Decisions already made by the owner (do not reopen them):

- Quality is chosen **per VOD on the Plan tab**. A **default preference** lives in Options (default: *Best available*).
- Audio-only offers **both** `.m4a` (copy) and `.mp3` (convert). The choice is an Options setting.
- With audio-only, the video-only extras are **skipped automatically, with a line in the log**: frame-exact cuts,
  Premiere XML markers, Premiere plugin markers, game markers, muted markers, chat overlay video.
  Things that do not need video keep working: clip chapters, `.clips.json`, the chat `.json/.txt/.html` download.
- Quality choice only applies to **Twitch VODs**. For any other site the picker is hidden and nothing changes.

## 2. Facts about the project you must know first

Everything non-GUI is in `luckytwitch_engine.py` (about 3,400 lines). The GUI is Qt 6 (PySide6) in `qt_ui/`, pure
logic in `core/`. Tests are in `tests/` (pytest, Qt runs offscreen, see `tests/conftest.py`).

**How quality works today.** There is no quality choice. yt-dlp is always called with `-S res,fps,tbr` (sort: best
first). That string appears in exactly two places: `run_ytdlp` and `get_playlist_url`.

**What Twitch gives us.** `get_source_info` runs `yt-dlp --dump-single-json`. The `formats` list holds one entry per
quality. Real data is in `tests/fixtures/vod_single_game_short.json` (and `vod_multi_game_long.json`,
`vod_single_game_long.json`). Look at it before coding. The ids are `Audio_Only`, `160p`, `360p`, `480p`, `720p60`,
`1080p60`. The Source quality has `format_note: "Source"` (it is not always 1080p). Every video format already
contains audio (`acodec` set). `Audio_Only` has `vcodec: "none"` and AAC audio (`mp4a.40.2`). Two entries have
`format_note: "storyboard"` (thumbnails): ignore them. This list is currently thrown away after "Get info".

**The download paths in `run_job`:**

| Strategy | Path | Functions |
|---|---|---|
| `full` | download the whole VOD, then cut | `download_full` -> `run_ytdlp`, then `split_copy` (or `cut_exact` if frame-exact) |
| `sections` | download only the parts | `download_section_aligned` (HLS segments + ffmpeg copy; uses `get_playlist_url`), and if that returns `None`, `download_section` -> `run_ytdlp` |

Then `finish()` (inside `run_job`) calls `finalize_part`, writes Premiere markers (`probe_video`, `write_premiere_xml`,
`write_markers_json`) and the chat files (`chat_files_for_part`).

**Things in the code that assume video (will break with audio-only):**

- `-map 0:v:0 -map 0:a?` in `download_section_aligned`, `split_copy`, `cut_exact`. With no video stream this fails.
- `download_section_aligned` writes `part.mp4`.
- `MEDIA_EXTS` has no `.m4a` / `.mp3`.
- `probe_video` and the Premiere / chat-overlay code need a video track.

**A bug that quality selection would create (must be fixed in Phase 2):** the work folder is
`.luckytwitch_<vod id>` and the full download is cached with a `full.done` marker. A cancelled job keeps that folder
so it can resume. If the person then retries at another quality, the old file would be reused or mixed in. The work
folder name must include the chosen format.

**Settings.** `core/settings.py` `DEFAULTS` currently has **39 keys** (15 booleans + 24 strings, following the addition of `clean_title`) and tests assert that
number. On/off settings are real booleans, everything else is a string. Adding `default_quality` and `audio_format` will bring this to **41 keys** (15 booleans + 26 strings). A combo box stores its **visible text** as the
value (like `strategy` stores `"Auto"`); `core/options.py` maps that text to the engine value (`STRATEGIES = {...}`).
Follow that pattern exactly.

**Test habits to copy.** Tests replace engine functions with fakes using `monkeypatch.setattr(eng, "name", fake)`.
Several fakes have a **fixed signature**, for example `lambda c, u: BASE` for `get_playlist_url`,
`lambda ctx, url, p, wd: ...` for `download_section_aligned`,
`fake_finalize(ctx, f, stem, container, chapters, tags, total, copy=False)` for `finalize_part`. See
`tests/test_hls_sections.py` (`_patch_run_job`, `_job`, `_ctx`) and `tests/test_muted_audio.py`.

## 3. Rules for the implementer (read twice)

1. **One phase at a time.** After each phase run `python -m pytest tests -q`. Do not start the next phase while
   anything is red. Report the pass/fail summary after each phase.
2. **Only edit the files a phase lists.** Do not refactor, rename or "improve" anything else.
3. **Never change an existing function signature except by adding optional parameters at the END with a default.**
4. **Pass a new keyword argument only when it is needed.** Existing tests fake engine functions with fixed
   signatures. So write `kw = {"format_id": fid} if fid else {}` and call `f(ctx, url, **kw)`. When no format was
   resolved (every old test), the call must look exactly like it does today. This one rule keeps the old tests green.
5. **Keep Windows line endings (CRLF) in existing files.** The repo uses them. Do not convert a file to LF. New
   files may use either.
6. **No new dependencies. No real network or real ffmpeg/yt-dlp in tests.** Fake `run_ffmpeg`, `subprocess.Popen`,
   `subprocess.run`, `requests.get`.
7. **Do not touch:** `premiere-plugin/`, `premiere-plugin-cep/`, `installer.iss`, `build_*`, `.github/`,
   `docs/markers-format.md`, `docs/link-format.md`, `weblink.py`, `RELEASE_NOTES.md` (see Phase 7).
8. **You write the tests** for each phase (the owner runs them on Windows and pastes the result back). Tests come
   in the new files named in each phase, plus the small edits to existing tests that are listed explicitly. If an
   *unlisted* existing test fails, **stop and ask**. Do not edit it to make it pass.
9. **Stop and ask the owner** if the same test fails 3 times in a row, if something in this plan contradicts the
   code you see, or if you think a design decision should change.
10. Write comments and messages in plain English in the same style as the file (short, no jargon). User-facing
    strings use the project's typographic style (`«` `»` and `·` are fine where the file already uses them).

## 4. Phases

### Phase 0: baseline

- Run `python -m pytest tests -q`. Write down how many tests pass (baseline is **1,311 passed, 31 skipped**). It must be fully green before you change anything.
  If it is not, stop and tell the owner.
- Look at the real data once: print `[(f["format_id"], f.get("format_note"), f.get("height"), f.get("vcodec"))
  for f in json.load(open("tests/fixtures/vod_single_game_short.json"))["formats"]]`.

### Phase 1: the list of qualities (engine, no I/O)

**Files:** `luckytwitch_engine.py`; new `tests/test_quality_formats.py`.

Add, **above `class SourceInfo`**:

```python
QUALITY_BEST = "best"    # the highest quality there is
QUALITY_AUDIO = "audio"  # the audio-only quality


@dataclass(frozen=True)
class VideoFormat:
    """One quality Twitch offers for a VOD (one entry of yt-dlp's "formats")."""
    format_id: str           # what yt-dlp calls it: "1080p60", "720p60", "480p", "Audio_Only"
    height: int = 0          # 0 for audio only
    fps: float = 0.0
    tbr: float = 0.0         # kbit/s as Twitch declares it (0 = unknown)
    audio_only: bool = False
    source: bool = False     # Twitch's own "Source" quality (format_note == "Source")

    @property
    def label(self) -> str:  # what the person reads
        if self.audio_only:
            return "Audio only"
        return f"{self.format_id} (Source)" if self.source else self.format_id

    @property
    def tag(self) -> str:    # for file names (Phase 7)
        return "audio" if self.audio_only else self.format_id
```

Add `formats: list[VideoFormat] = field(default_factory=list)` as the **last** field of `SourceInfo` (it has a default,
so every existing `SourceInfo(...)` call keeps working).

Add these functions (next to `parse_storyboard`):

- `parse_formats(formats) -> list[VideoFormat]`: yt-dlp's `formats` -> our list. Rules: not a list -> `[]`; skip
  entries that are not dicts, have `format_note == "storyboard"`, have no non-empty string `format_id`, repeat an
  earlier `format_id`, or whose `url` is not a string containing `.m3u8` (look only at the part before `?`).
  `audio_only = f.get("vcodec") == "none"`. `height`/`fps`/`tbr` are read tolerantly (bad value -> 0).
  `source = f.get("format_note") == "Source"`. Sort: video first, then by height, fps, tbr (all descending);
  audio-only last. Never raises.
- `resolve_format(formats, wanted=QUALITY_BEST) -> VideoFormat | None`. `None` when `formats` is empty. Otherwise,
  in this order (compare case-insensitively, after `strip()`):
  1. `"audio"` -> the audio-only format; if there is none, the best video.
  2. `"best"` (or empty / anything unknown) -> the video format with the highest (height, fps, tbr). If there is
     no video format at all, the audio one.
  3. exact `format_id` match (so `"720p60"` and `"Audio_Only"` work).
  4. a height cap like `"720p"` (regex `(\d{3,4})p`): among video formats with `0 < height <= cap` the one with the
     highest (height, fps, tbr); if none fits, the **lowest** video format.
  5. otherwise, as 2.
- `estimate_bytes(fmt, seconds) -> int`: `fmt.tbr * 1000 / 8 * seconds`, `0` if `fmt` is `None`, `tbr <= 0` or
  seconds `<= 0`.

In `parse_source_info`, add `formats=parse_formats(info.get("formats")) if twitch_vod_id(url) else []` to the
`SourceInfo(...)` call.

**Tests (`tests/test_quality_formats.py`).** Load the three real fixtures with `json.load`. Check:

- real fixtures give ids in this order: `1080p60, 720p60, 480p, 360p, 160p, Audio_Only`; only `1080p60` has
  `source=True`; `Audio_Only` has `audio_only=True` and `height == 0`; storyboard entries never appear;
- labels: `"1080p60 (Source)"`, `"720p60"`, `"Audio only"`; tags: `"1080p60"`, `"audio"`;
- garbage never raises and gives `[]`: `None`, `[]`, `"x"`, `[None, 3]`, `[{"format_id": "a"}]` (no url),
  an entry with a non-m3u8 url;
- `resolve_format`: `best` -> 1080p60; `audio` -> Audio_Only; `"720p60"` exact; `"Audio_Only"` exact;
  `"720p"` -> 720p60 (cap); `"900p"` -> 720p60; `"100p"` -> 160p (lowest); `"banana"` -> 1080p60;
  `[]` -> `None`; `"AUDIO"` and `" best "` work; a synthetic list with `720p30` and `720p60` and wanted `"720p"`
  -> the 60 fps one; a list with no audio entry and wanted `audio` -> best video;
- `parse_source_info(fixture, "https://www.twitch.tv/videos/1").formats` is filled, and with
  `"https://example.com/v/1"` it is `[]`;
- `estimate_bytes` for 6000 kbit/s and 3600 s is `2_700_000_000`; `None` and `0` cases give `0`.

**Done when:** the new tests and the whole suite pass.

### Phase 2: download the chosen quality (engine, video)

**Files:** `luckytwitch_engine.py`; new `tests/test_quality_download.py`.

1. `JobOptions`: add at the end `quality: str = QUALITY_BEST` and `audio_format: str = "m4a"` (the second one is
   used in Phase 3; add both now so the dataclass changes once). Comment each in the same style as its neighbours.
2. `run_ytdlp(..., format_id: str | None = None)`: replace the fixed pair `"-S", "res,fps,tbr"` in the command
   by `["-f", format_id]` when `format_id` is given, else the old pair. Same position in the list.
3. `get_playlist_url(ctx, url, format_id=None)`: same idea for its `-g` command:
   `[ytdlp, "-g", *quality_args, "--no-warnings", url]`.
4. `download_full(ctx, url, workdir, threads, format_id=None)` and
   `download_section(ctx, url, part, workdir, threads, exact, format_id=None)`: forward to `run_ytdlp` (pass the
   keyword only when `format_id` is not `None`, rule 4).
5. `download_section_aligned(ctx, url, part, workdir, format_id=None)`: call `get_playlist_url` with the keyword
   only when `format_id` is not `None`.
6. In `run_job`, right after the first `ctx.log(...)` (the one that prints the part count) and before
   `chapters_all = ...`:

```python
fmt = resolve_format(src.formats, opts.quality)
fmt_kw = {"format_id": fmt.format_id} if fmt else {}
if fmt:
    ctx.log(describe_quality(fmt, opts.quality))
elif (opts.quality or "").strip().lower() not in ("", QUALITY_BEST):
    ctx.log("Quality: this video offers no choice, using the best one.")
```

   Add the small pure helper `describe_quality(fmt, asked) -> str` next to `resolve_format`: returns
   `f"Quality: {fmt.label}"` and appends `f" (asked for {asked})"` only when what was asked is not already what
   was chosen (asked `best` -> nothing appended; asked equal to the `format_id` -> nothing; asked `audio` and the
   result is audio-only -> nothing; anything else, for example asked `480p` and got `480p30`, or asked `audio`
   and got a video -> appended).
7. Change the work folder name: `workdir = out_dir / (f".luckytwitch_{src.twitch_vod_id or src.id}" +
   (f"_{fmt.format_id}" if fmt else ""))`. (No format: the name stays exactly as it is today.)
8. Pass `**fmt_kw` to the three calls in `run_job`: `download_full(...)`, `download_section_aligned(...)`,
   `download_section(...)`.
9. Do **not** change the muted-range code: it still reads the best-quality playlist. (Twitch mutes the same time
   ranges in every quality. This is an assumption, see section 6.)

**Tests (`tests/test_quality_download.py`).**

- `run_ytdlp` with `format_id="720p60"`: patch `eng.find_tool` (return `"yt-dlp"`) and `eng.subprocess.Popen` with a
  fake that records the command and has `stdout=iter([])`, `wait()` and `returncode = 0`. Assert `"-f"` followed by
  `"720p60"` is in the command and `"-S"` is not. Without `format_id`, `"-S"` is there and `"-f"` is not.
- `get_playlist_url` with and without `format_id`: patch `eng.subprocess.run` to return
  `subprocess.CompletedProcess(args, 0, stdout="https://x/a.m3u8\n", stderr="")` and check the recorded command.
- `run_job` wiring: copy the `_patch_run_job` / `_job` / `_ctx` pattern from `tests/test_hls_sections.py`. Build
  the `SourceInfo` with `formats=parse_formats(<fixture formats>)` and `JobOptions(quality="720p", strategy=
  "sections", ...)`. Fake `download_section_aligned` as `lambda ctx, url, p, wd, **kw: (calls.update(kw), ...)[1]`
  and assert `calls["format_id"] == "720p60"` and the log has `"Quality: 720p60"`.
- Same job with `formats=[]` (default): the fake receives **no** `format_id` and the log has no "Quality:" line.
- `strategy="full"`: fake `download_full` records its `workdir`; two jobs with `quality="720p"` and `"480p"` get
  **different** work folders, and a job without formats gets the old name `.luckytwitch_1`.
- `describe_quality` cases (all five bullets of step 6).

**Done when:** new tests pass **and every old test still passes untouched**.

### Phase 3: audio-only (engine)

**Files:** `luckytwitch_engine.py`; new `tests/test_audio_only.py`.

Audio-only is a format like any other (`fmt.audio_only`). What changes is the ffmpeg mapping, the file extension,
the finishing step and the skipped extras.

1. Constants, near `MEDIA_EXTS`:

```python
AUDIO_FORMATS = ("m4a", "mp3")
MEDIA_EXTS = {".mp4", ".mkv", ".ts", ".webm", ".mov", ".m4v", ".m4a", ".mp3"}   # add the last two
AUDIO_SKIPPED = (  # settings that need a video track -> what the log calls them
    ("exact", "frame-exact cuts"),
    ("premiere_xml", "Premiere XML markers"),
    ("premiere_plugin", "Premiere plugin markers"),
    ("game_markers", "game markers"),
    ("muted_markers", "muted markers"),
    ("chat_render", "chat overlay video"),
)
```

2. Helpers (pure, next to `mp4_flags`). Import `replace` (`from dataclasses import dataclass, field, replace`).

```python
def audio_out_container(opts: "JobOptions") -> str:
    return opts.audio_format if opts.audio_format in AUDIO_FORMATS else "m4a"


def audio_codec_args(container: str) -> list[str]:
    """m4a: Twitch's AAC copied as it is. mp3: converted."""
    return ["-c:a", "libmp3lame", "-b:a", "192k"] if container == "mp3" else ["-c:a", "copy"]


def audio_only_options(opts: "JobOptions") -> "tuple[JobOptions, list[str]]":
    """The options with every video-only extra switched off, and the names of the ones that were on."""
    skipped = [label for key, label in AUDIO_SKIPPED if getattr(opts, key)]
    return replace(opts, **{key: False for key, _ in AUDIO_SKIPPED}), skipped
```

3. `download_section_aligned(..., format_id=None, audio_only=False)`: when `audio_only`, the maps are
   `["-map", "0:a:0"]` (instead of `-map 0:v:0 -map 0:a?`) and the output file is `part.m4a` (instead of
   `part.mp4`); the `-f mp4` stays. Everything else unchanged.
4. `split_copy(..., audio_only=False)` (new last parameter): when true, the maps are `["-map", "0:a:0"]` and add
   `"-segment_format", "mp4"` before `-segment_times`. The `container` argument it receives is `"m4a"` (see step 6),
   so the files are `seg_000.m4a`, ... Keep the rest.
5. New `finalize_audio_part`, next to `finalize_part` (do **not** change `finalize_part`). Same parameters and same
   positional order as `finalize_part`:

```python
def finalize_audio_part(ctx, src_file, dest_stem, container, chapters, tags, total, copy_instead_of_move=False) -> Path:
    """Put an audio-only part in its final place as .m4a (copy) or .mp3 (convert)."""
    dest = unique_path(dest_stem.parent / f"{dest_stem.name}.{container}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not chapters and container == "m4a" and src_file.suffix.lower() == ".m4a":
        (shutil.copy2 if copy_instead_of_move else shutil.move)(str(src_file), str(dest))
        return dest
    args = ["-i", str(src_file)]
    if chapters:
        meta = src_file.with_suffix(".ffmeta")
        meta.write_text(ffmetadata(chapters, tags), encoding="utf-8")
        args += ["-i", str(meta), "-map_metadata", "1", "-map_chapters", "1"]
    args += ["-map", "0:a:0", *audio_codec_args(container)]
    if container == "mp3":
        args += ["-id3v2_version", "3"]
    run_ffmpeg(ctx, args + [str(dest)], total=total)
    return dest
```

   (Never delete `src_file`: the work folder is removed at the end of `run_job`, and a "whole VOD is one part" file
   may also be the full file that "keep the full VOD" moves.)
6. `run_job`:
   - After step 6 of Phase 2 (the `fmt` lines) and **before** `chapters_all = ...`:

```python
audio_only = bool(fmt and fmt.audio_only)
out_container = audio_out_container(opts) if audio_only else opts.container
if audio_only:
    opts, skipped = audio_only_options(opts)
    job = replace(job, opts=opts)   # _load_chapters reads job.opts
    if skipped:
        ctx.log("Audio only: skipped " + ", ".join(skipped) + " (they need a video track).")
```

   - In `finish()`: use `out_container` instead of `opts.container` in the `finalize` call, and call
     `finalize_audio_part` instead of `finalize_part` when `audio_only` (same positional arguments, `copy` last).
     Because all the video-only switches are now off, the existing marker and overlay code does nothing; do not
     add extra `if` blocks there.
   - Calls: `download_section_aligned(..., **fmt_kw, **({"audio_only": True} if audio_only else {}))` (build one
     dict `kw = {**fmt_kw, **({"audio_only": True} if audio_only else {})}` and pass `**kw`). Same for
     `split_copy`, whose container argument is `"m4a" if audio_only else opts.container`, with
     `audio_only=True` only when needed. (mp3 is made from the m4a segment in `finalize_audio_part`; never put AAC
     into an `.mp3` container with `-c copy`.)
   - "Keep the full VOD": when `audio_only` and `full.suffix.lower() == ".mp4"`, keep it as `.m4a`
     (`unique_path(stem.with_suffix(".m4a"))`).
   - The exact-cut branches (`if opts.exact:`) need no change: `exact` is now `False`.

**Tests (`tests/test_audio_only.py`).**

- `audio_out_container` (`"mp3"` -> mp3, `"m4a"` -> m4a, `"ogg"` / `""` -> m4a); `audio_codec_args` for both.
- `audio_only_options`: with `exact`, `premiere_plugin`, `chat_render`, `game_markers` on, the returned options have
  all six switches off, `chat` and `chapters` are unchanged, the skipped list has exactly the four names that were on
  (and is empty when none was on), and the original `opts` object is not modified.
- `finalize_audio_part` with `run_ffmpeg` faked to record its arguments: m4a with a `.mp4` source -> `-c:a copy`,
  `-map 0:a:0`, output ends `.m4a`; mp3 -> `libmp3lame`, `192k`, `-id3v2_version`, output `.mp3`; with chapters ->
  `-map_chapters` present and the `.ffmeta` file written; no chapters + `.m4a` source + m4a -> file moved and
  `run_ffmpeg` **not** called; `unique_path` numbering when the destination exists.
- `download_section_aligned(..., audio_only=True)` with `get_playlist_url`, `requests.get` and `run_ffmpeg`
  faked (copy the pattern from `tests/test_hls_sections.py`): arguments contain `0:a:0`, do not contain `0:v:0`,
  and the returned file is named `part.m4a`.
- `split_copy(..., audio_only=True)`: fake `run_ffmpeg` that records the arguments and writes the `list.csv` file
  (path = the argument after `-segment_list`) with rows like `seg_000.m4a,0.000,10.000`; assert `0:a:0`,
  `-segment_format`, `mp4`, no `0:v:0`.
- `run_job` end to end with everything faked: `SourceInfo` with real parsed formats, `quality="audio"`,
  `audio_format="mp3"`, `exact=True`, `premiere_plugin=True`, `chat_render=True`, `chapters=False`. Assert:
  `finalize_audio_part` was called with container `"mp3"` and `finalize_part` was not; `write_markers_json` /
  `write_premiere_xml` were not called; the log contains `"Audio only: skipped"` and `"frame-exact cuts"` and
  `"Quality: Audio only"`. A second case with `audio_format="m4a"` and `strategy="full"` (fake `download_full`
  and `split_copy`) checks `split_copy` received container `"m4a"` and `audio_only=True`, and that with
  `keep_full=True` the kept file ends `.m4a`.
- A video job (`quality="720p"`) still calls `finalize_part` and never `finalize_audio_part`.

**Done when:** new tests and the whole suite pass.

### Phase 4: settings and options mapping (core)

**Files:** `core/settings.py`, `core/options.py`, `tests/fixtures/settings_written_by_tk.json`,
`tests/test_core_helpers.py`, `tests/test_core_options.py`.

1. `core/settings.py` `DEFAULTS`: add `"default_quality": "Best available"` and
   `"audio_format": "m4a · keep Twitch's audio"` (both strings).
2. `core/options.py`: add, next to `STRATEGIES`:

```python
QUALITY_CHOICES = {          # what the person reads -> what the engine uses
    "Best available": "best", "1080p": "1080p", "720p": "720p", "480p": "480p",
    "360p": "360p", "160p": "160p", "Audio only": "audio",
}
AUDIO_FORMAT_CHOICES = {"m4a · keep Twitch's audio": "m4a", "mp3 · converted": "mp3"}
QUALITY_NAMES = list(QUALITY_CHOICES)
AUDIO_FORMAT_NAMES = list(AUDIO_FORMAT_CHOICES)
```

   `build_options(settings, cut_text="", quality=None)`: add the optional `quality` parameter (engine value, for
   example `"720p60"`, `"best"`, `"audio"`). Set
   `quality=quality or QUALITY_CHOICES.get(text(s, "default_quality"), "best")` and
   `audio_format=AUDIO_FORMAT_CHOICES.get(text(s, "audio_format"), "m4a")` in the `JobOptions(...)` call.
3. Existing tests that must be edited (these are the only existing tests you may change in this phase):
   - `tests/test_core_helpers.py::test_defaults_are_the_38_documented_keys_with_the_documented_types`: now **41**
     keys, **26** strings, 15 booleans (including `clean_title`). Rename the test to say 41.
   - `tests/fixtures/settings_written_by_tk.json`: add `"default_quality": "720p"` and
     `"audio_format": "mp3 · converted"` (both differ from the defaults, as the test requires). Update the
     docstring of `test_settings_file_written_by_the_tkinter_app_loads_with_every_value` to say the two newest keys
     were added by hand.
4. New tests in `tests/test_core_options.py` (or a new `tests/test_core_quality_options.py`): the defaults give
   `quality == "best"` and `audio_format == "m4a"`; `default_quality = "720p"` -> `"720p"`;
   `"Audio only"` -> `"audio"`; an unknown text -> `"best"`; an explicit `quality="480p"` argument wins over the
   setting; `audio_format = "mp3 · converted"` -> `"mp3"`; unknown -> `"m4a"`.

**Done when:** whole suite green (this phase makes `tests/test_qt_options_tab.py` red: see Phase 5, do it right
after; if you prefer, do Phase 4 and 5 together and run the suite at the end of Phase 5).

### Phase 5: Options tab (Qt)

**Files:** `qt_ui/tabs/options.py`, `tests/test_qt_options_tab.py`.

In `_section_output`, **after** the main card (after the `Download threads`... advanced block) add a second card in
the same section:

```python
qcard = self._card(f, "Quality", "What to download when a VOD offers several qualities (Twitch VODs).")
row = qcard.add_row(
    "Default quality", "Used when you load a VOD. You can change it for each VOD on the Plan tab.",
    info="Best available is the highest quality Twitch offers. If a VOD does not have the chosen quality, the "
         "closest lower one is used. Audio only downloads just the sound.")
self._register_setting(row, "default_quality", "output", qcard)
row.add_control(self._combo("default_quality", QUALITY_NAMES, 16))
row = qcard.add_row(
    "Audio-only file", "How the sound is saved when the quality is Audio only.", divider=False,
    info="m4a keeps Twitch's own audio exactly as it is (no re-encoding). mp3 converts it with ffmpeg "
         "(192 kbit/s) and plays everywhere.")
self._register_setting(row, "audio_format", "output", qcard)
row.add_control(self._combo("audio_format", AUDIO_FORMAT_NAMES, 26))
```

Import `QUALITY_NAMES, AUDIO_FORMAT_NAMES` from `core.options` (the import already exists, extend it). Do not call
`self._advanced(...)` again for this card (`self.advanced["output"]` already exists).

**Edits to the existing test file:** add `"default_quality"` and `"audio_format"` to `OPTIONS_KEYS`; add both to the
`combos` set (the line with `"container", "strategy", "chat_format", ...`); add them to the `"output"` entry of the
per-section dictionary (the one that currently lists `{"out_dir", "container"}`: read what that test checks and
extend it the same way). Read the tests around `OPTIONS_KEYS` before editing so you extend, not replace.

**New tests** (append to `tests/test_qt_options_tab.py`, copy the fixtures used there): both combos exist, show the
default texts, hold the right items (`QUALITY_NAMES` / `AUDIO_FORMAT_NAMES`); choosing "720p" writes
`settings["default_quality"] == "720p"`; the settings search for "quality" and for "audio" finds the rows
(see how the existing search tests call `search_entry`); the changed-from-default marker appears after a change
(look at the existing test for `container`).

**Done when:** whole suite green.

### Phase 6: the quality picker on the Plan tab (Qt)

**Files:** `qt_ui/tabs/plan.py`, `qt_ui/main_window.py`, new `tests/test_qt_quality.py`.

**Behaviour.** In the "Cut points" card, directly under the strategy row, a row: label `Quality:`, a `ComboBox`, a
muted note label on the right. It is hidden until a Twitch VOD with formats is loaded. The choice belongs to the
loaded VOD, it is **not** a setting and is never written to `settings`.

`plan.py`:

- Import `ComboBox` from `qt_ui.widgets`; `QUALITY_CHOICES` from `core.options`;
  `QUALITY_BEST`, `resolve_format`, `estimate_bytes` from `luckytwitch_engine`.
- Signal `quality_changed = Signal(str)`.
- In `_build_cuts_card`, after `self.cuts_card.add_widget(self.strategy_row)`, build `self.quality_row` the same
  way `strategy_row` is built (HBox, muted `QLabel("Quality:")`, then `self.quality_combo = ComboBox()`, stretch,
  `self.quality_note = QLabel("")` with `role="muted"`); `self.quality_row.setVisible(False)`;
  `self.quality_combo.activated.connect(self._on_quality_activated)`.
- `set_formats(self, formats, default_setting: str) -> None`:
  - clear the combo with signals blocked; if `formats` is empty: hide the row and return;
  - item 0: text `f"Best available ({best.label})"`, data `QUALITY_BEST`, where
    `best = resolve_format(formats, QUALITY_BEST)`;
  - then one item per format in the list order: text `fmt.label`, data `fmt.format_id`;
  - pick the default: `wanted = QUALITY_CHOICES.get(default_setting, "best")`; if `wanted == "best"` select item 0,
    otherwise `chosen = resolve_format(formats, wanted)` and select the item whose data is `chosen.format_id`;
  - show the row; call `self.update_preview()`.
- `current_quality(self) -> str`: the data of the current item when the row is visible, else `QUALITY_BEST`.
- `_on_quality_activated(self, _index)`: `self.update_preview()` and `self.quality_changed.emit(self.current_quality())`.
- `build_options(self)`: `build_options(self.settings, self.cut_text(), quality=self.current_quality())`.
- In `_render_preview`, when the plan is valid and `self.source` has formats, add one line at the end of the
  preview lines: `f"Quality: {fmt.label}"` plus, when `estimate_bytes` is above 0,
  `f" · about {human_size(n)}"`, where `n` is the estimate for the seconds that will be downloaded
  (`sum(p.duration for p in plan.parts)` for the "sections" strategy, `self.source.duration` for "full"). For an
  audio-only choice add `"Audio only: saved as .m4a or .mp3 (Options). Video-only extras are skipped."` instead of
  the size line. Add a small module-level `human_size(n: int) -> str` (`"1.4 GB"`, `"820 MB"`; one decimal for GB).
  `fmt` is `resolve_format(self.source.formats, self.current_quality())`.

`main_window.py`:

- `MainWindow.build_options`: `build_options(self.settings, self.cut_text(), quality=self.tab_plan.current_quality())`.
- `on_info_ok`: right after `self.source, self.clips, self.clips_loaded = ...` add
  `self.tab_plan.set_formats(info.formats, str(self.settings.get("default_quality", DEFAULTS["default_quality"])))`
  (import `DEFAULTS` if not already there).
- `clear_vod`: call `self.tab_plan.set_formats([], "")`.
- `download_clips` needs no change (`replace(base, ...)` keeps `quality`, so a clip follows the chosen quality; a
  clip downloaded while "Audio only" is selected becomes an audio file, which is fine).

Do **not** change the queue table or `enqueue` (the quality shows in the log line `Quality: ...` that `run_job`
already writes).

**Tests (`tests/test_qt_quality.py`)**: copy the `themed` / `boxes` / `win` fixtures and `load_vod` style from
`tests/test_qt_plan_tab.py`. Build formats with `parse_formats(<fixture formats>)`. Check:

- row hidden for a VOD without formats and after `clear_vod()`;
- after `set_formats(fmts, "Best available")`: row visible, 7 items (Best + 6), item 0 text is
  `"Best available (1080p60 (Source))"`, `current_quality() == "best"`;
- default `"720p"` selects the `720p60` item; default `"Audio only"` selects the `Audio_Only` item;
- picking the `480p` item (`setCurrentIndex` then `activated.emit(index)`) -> `current_quality() == "480p"`,
  `quality_changed` fired with `"480p"`, and `win.build_options().quality == "480p"`;
- `win.settings["default_quality"]` is unchanged by that pick;
- `add_to_queue()` creates an item whose `job.opts.quality == "480p"` (see `test_qt_plan_tab.py` line ~385 for how
  to read `win.tab_queue.items[i].job.opts`);
- loading another VOD (`on_info_ok(...)` or `set_formats` again) resets the pick to the default;
- the preview text mentions `Quality: 480p` and, for the audio choice, `Audio only`;
- `human_size(1_400_000_000) == "1.4 GB"`, `human_size(820_000_000) == "820 MB"`, `human_size(0)` does not raise.

**Done when:** whole suite green.

### Phase 7 (small, last): `{quality}` in file names and docs

**Files:** `luckytwitch_engine.py` (`part_stem`), `qt_ui/tabs/options.py` (token list), `README.md`, new tests in
`tests/test_naming.py`.

- `part_stem`: add `quality=` to the `_SafeDict(...)`: `resolve_format(src.formats, opts.quality).tag` when
  `src.formats` has entries, else `""`. Default templates do not use it, so existing names do not change.
  Different qualities of the same VOD can then be told apart: `{streamer} - {date} - {id} - {quality} - part{n}`.
- Options tab: add `"quality"` to the token list of the `name_template` row only.
- Tests: `{quality}` gives `720p60` / `audio` / empty; an old template without it is unchanged.
- `README.md`: a short **Quality** and **Audio only** section under "Using it" (what the picker is, where the default
  lives, `.m4a` vs `.mp3`, what is skipped in audio-only mode and why). English, same style as the file.
- **Do not edit `RELEASE_NOTES.md`.** Its first line must equal the next git tag; the owner decides the version.
  Instead, hand the owner a 6-line summary of the user-visible changes to paste there.

## 5. Manual check on a real VOD (owner, Windows)

The automatic tests use fakes. These cannot be tested without a real Twitch download, so please run them once with a
short VOD (a few minutes of each case is enough):

1. Get info on a Twitch VOD: the Quality row shows "Best available (...)" and the VOD's real qualities.
2. Add a short part at **360p**, strategy "only the parts": the file's height is 360; the log says `Quality: 360p`.
3. Same VOD, **160p**, strategy "full VOD + split": works, and the work folder (`.luckytwitch_<id>_160p`) is separate.
4. Cancel a download, then retry the same VOD at a different quality: nothing from the first attempt is reused.
5. **Audio only + m4a**: file is `.m4a`, plays, is small; the log says `Audio only: skipped ...` for the extras that
   were on.
6. **Audio only + mp3**: file is `.mp3`, plays; with clip chapters on, a player that shows chapters shows them.
7. Audio only + strategy "full VOD + split" + "keep the full VOD": the kept file is `FULL.m4a`.
8. Audio only with Premiere markers on: no `.markers.json` / `.markers.xml`, one log line says so.
9. A non-Twitch link: no Quality row, download exactly as before.
10. The default quality in Options (try 720p, then Audio only) changes what the row preselects on the next VOD.

## 6. Unverified assumptions and risks

- **AAC copy into `.m4a`.** Twitch's audio-only playlist is AAC; `-c copy` into an MP4 audio file should work with the
  ffmpeg builds the app downloads (ffmpeg adds the needed AAC filter by itself). Not run against a real VOD yet:
  check 5. If ffmpeg complains about an ADTS/ASC bitstream, the fix is adding `-bsf:a aac_adtstoasc` to the
  `-c:a copy` branch. **Do not add it up front.**
- **MP3 chapters.** ffmpeg writes chapters into MP3 as ID3 `CHAP` frames; not verified: check 6. If it fails, the
  existing error path reports it; do not build a workaround without asking.
- **Muted ranges are read from the best-quality playlist** for every choice (assumed identical in all qualities).
- **Format ids.** The code never hard-codes `1080p60`; it reads whatever Twitch offers, so older VODs with other ids
  work. A VOD with a single quality shows a picker with "Best available" and that one entry.
- The queue table does not show the quality (only the log does). Adding a column is a separate, optional change.
- `luckytwitch://` links cannot carry a quality yet (out of scope; `docs/link-format.md` stays as it is).
- mp3 files carry no title/artist tags in this version (only chapters if any), same as video parts today.

## 7. Definition of done

- Phases 1 to 7 finished, `python -m pytest tests -q` green, no existing test edited except the ones named in
  Phases 4 and 5.
- A short report: files changed per phase, test count before and after, anything you were unsure about.
