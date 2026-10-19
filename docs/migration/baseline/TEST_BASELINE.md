# Test baseline (Phase 0)

Run on 2026-10-19 on the code of the uploaded zip (v1.16.0 plus the migration docs), before any change.

| | |
| --- | --- |
| Environment | Linux (Ubuntu 24.04), Python 3.12.3, Tk 8.6.14 (`python3-tk`), xvfb, requests, pillow, pytest 9.1.1 |
| Command (everything) | `xvfb-run -a python3 -m pytest -p no:cacheprovider tests -q` |
| Result | **798 passed**, 0 failed, 0 skipped, 0 xfail (55.6 s) |
| Command (no GUI, no display) | `python3 -m pytest -p no:cacheprovider tests/test_*.py` without the GUI files, with `tkinter` not installed |
| Result | 513 passed, 1 skipped (`test_muted_audio.py`: the tkinter part is skipped without tkinter) |

## Tests that need tkinter and a display

235 of the 798: the nine `tests/test_gui_*.py` files (232) plus 3 timeline tests in `tests/test_muted_audio.py`.
HANDOFF.md said "197 tests"; that figure was out of date.

| File | Tests |
| --- | --- |
| test_gui_final_pass.py | 6 |
| test_gui_options_tab.py | 40 |
| test_gui_plan_redesign.py | 10 |
| test_gui_plan_tab.py | 31 |
| test_gui_queue_tab.py | 41 |
| test_gui_search_tab.py | 18 |
| test_gui_theme_and_icon.py | 13 |
| test_gui_timeline.py | 57 |
| test_gui_weblink.py | 16 |
| test_muted_audio.py (3 of its 53) | 3 |

## The two "known failing" timeline tests

`test_split_at_a_clip_updates_the_timeline_and_a_second_split_changes_nothing` and
`test_refreshing_the_clips_updates_the_marks_without_a_vod_change` **pass** in this zip. Both now compare with
`pytest.approx(600.4)` (`tests/test_gui_timeline.py` lines 507 and 570), so the outdated expectation (600) was already fixed
before this phase. Nothing to fix and nothing to mark as expected-fail; no test was changed in Phase 0.

## `progress-eta.patch`

Stale, not needed. Its subject (size, speed and ETA while downloading by segments) is already in the engine:
`FfmpegProgress` and `_FF_PROGRESS_KEYS` exist in `luckytwitch_engine.py`, the tests that use `FfmpegProgress` exist in
`tests/test_hls_sections.py`, and the patch no longer applies to the engine (checked on LF copies, so that line endings
were not the reason). Nothing in the repository refers to the file except the migration docs. Suggested: `git rm progress-eta.patch`
(left to the user; not part of the delivery commit unless the user chooses to).

## Re-measured sizes (HANDOFF.md section 6)

`luckytwitch_downloader.py` 1,645 lines; `ui/`: widgets 560, timeline 726, options_tab 441, plan_tab 302, theme 251,
common 72; `luckytwitch_engine.py` 145,000 bytes. Same as written there.

## Screenshots

`docs/migration/baseline/linux-xvfb/` has 28 PNGs made by `tools/baseline_screenshots.py`
(14 per size: 1020x910 and 900x560 as the file-name prefix):
`search_empty`, `plan_empty`, `options_empty`, `queue_empty`, `options_output`, `options_cuts`, `options_chapters`,
`options_premiere`, `options_chat`, `options_clips`, `options_tools`, `plan_with_vod`, `queue_with_log`,
`dialog_twitch_signin`.
They were taken on Linux under xvfb with no window manager: the fonts are not Segoe UI, there is no title bar, the
`dark_titlebar` and icon code have no effect, and the Plan tab, queue and log hold sample data, not a real VOD. They are a
layout reference only. For the real look, run the same script on Windows (the command is in section 7 of HANDOFF.md) into
`docs/migration/baseline/windows/`.

Not covered by screenshots: states that need a signed-in Twitch client (search results, VOD list with thumbnails), a running
job (progress bar, queue rows with statuses), a loaded VOD with games and thumbnails in the timeline, and the message boxes.
Those need real data; they are better captured by hand when the corresponding phase starts.
