# UI redesign: progress

Goal: a newer-looking, easier-to-read app (especially the Options tab), a proper icon, **no feature removed or broken**.
Phased: each phase is delivered on its own, this file says what is done and what is left.

## Phase 1: icon + theme foundation  ✅ delivered

### What changed
| Area | Change |
| --- | --- |
| **App icon** | New original icon: purple rounded square, white download arrow whose shaft is "cut" by a slanted gap, and a tray. No clover. Files in `assets/` (`icon.png`, `icon.ico` with 16-256 px, `icon.icns`). Redraw any time with `python tools/make_icon.py`. |
| **Icon wiring** | Window + taskbar icon at runtime (`ui/common.py: set_app_icon`, also gives the app its own Windows taskbar identity). `build_windows.bat` / `build_mac.sh` pass `--icon` and bundle `assets/`; `installer.iss` uses it for the installer and uninstaller. |
| **Theme** (`ui/theme.py`, new) | Same palette (dark + purple `#9146ff`), refined: flat buttons with hover/pressed states, filled purple **Accent** buttons for the main action of a screen (Get info, Search, Use this VOD, Start queue), purple focus outline on fields, rounded purple **checkboxes**, slim scrollbars without arrows, flatter tabs, roomier tables, thinner progress bar, hairline-bordered text boxes (no more white ring), font 9 → 10. |
| **New widgets** (`ui/widgets.py`, new) | `Toggle` (on/off switch with a small slide animation, keyboard + mouse), `Tooltip` and `info_icon` (the little *i*), `Card` and `SettingRow` (title + one-line hint on the left, control on the right). Ready for Phase 2; not used by the screens yet. |
| **Code layout** | Theme code moved out of `luckytwitch_downloader.py` into `ui/theme.py`. `apply_dark_theme` and `dark_titlebar` still exist under the same names in the main file. |
| **Tests** | `tests/test_gui_theme_and_icon.py`: 13 new tests (icon files, icon never crashes the app, build scripts reference it, styles exist, checkbox still toggles, switch behaviour, tooltip, card/rows). |

### Test status
477 passed, 2 failed. The 2 failures (`test_gui_timeline.py`: `test_split_at_a_clip...`, `test_refreshing_the_clips...`) fail identically **before any of my changes**.
*Correction (found in Phase 2):* this is **not** a Tk 9 issue, they fail on Tk 8.6 as well, and on a pristine copy of your zip. The tests expect the clip mark at `600`
but `clip_start()` returns `600.4` (clip offset 630.4 minus its 30 s duration, not rounded). Either the test expectation or the rounding is outdated; not touched yet.

### Files touched
New: `assets/*`, `tools/make_icon.py`, `ui/theme.py`, `ui/widgets.py`, `tests/test_gui_theme_and_icon.py`, this file.
Edited: `ui/common.py`, `luckytwitch_downloader.py`, `build_windows.bat`, `build_mac.sh`, `installer.iss`.
(`ui/timeline.py` also differs from your zip by one line, a Tk 9 compatibility fix that was already in the working copy; harmless on Tk 8.6.)

### Please check on your machine
- Run `python luckytwitch_downloader.py`: icon in the title bar and taskbar, new buttons/checkboxes/tabs.
- Fonts: my preview machine has no Segoe UI, so bold weights and spacing are only truly visible on yours. Tell me if text feels too big or small.

## Phase 2: Options tab redesign  ✅ delivered

Your answers: the up-front / Advanced split is right, and the sidebar layout (one section at a time) is right.

### What changed
| Area | Change |
| --- | --- |
| **Layout** | The Options tab is now a sidebar (**Output · Cuts · Chapters · Premiere Pro · Chat · Clips · Tools**) with one section visible at a time. Switching sections scrolls back to the top; Up/Down keys move through the sidebar. |
| **Rows** | Every setting is a row: bold name, one-line hint, control on the right. Long explanations moved into the little *i* tooltips. All on/off settings are now **switches** (no checkboxes left in Options). |
| **Advanced** | Collapsed by default, inside Output, Cuts, Premiere Pro and Chat. Values in a collapsed area still apply. |
| **Templates** | File name, stream folder, clip name and chapter title have clickable `{token}` chips (insert at the cursor, replace a selection) and a **live example** line. The example uses the VOD you loaded, or a sample until then, and is computed by the engine's own naming code, so it matches what is really written. «Stream folder name» greys out while *Organize in subfolders* is off. A half-typed template never breaks it. |

### Where each setting went
- **Output:** folder, format. *Advanced:* download threads, file name, organize in subfolders, stream folder name.
- **Cuts:** strategy, frame-exact cuts, keep the full VOD. *Advanced:* auto threshold %.
- **Chapters:** chapter title, tail, gap chapter name (all of them are set-once settings, so no Advanced area; the on/off switch stays in the Plan tab).
- **Premiere Pro:** LuckyTwitch plugin `.markers.json`, game / category changes. *Advanced:* plain `.markers.xml`, `.clips.json`.
- **Chat:** download the chat. *Advanced:* format, embed emotes and badges.
- **Clips:** file name, extra time before / after (all set-once, no Advanced area).
- **Tools:** tool status, yt-dlp update check on startup, update now, open tools folder.

Every setting keeps its old variable name, so saved settings, `build_options()` and the queue are unchanged. No feature removed.

### Code layout
New: `ui/options_tab.py` (`OptionsTabMixin`, same pattern as the Plan tab), `tests/test_gui_options_tab.py` (28 tests).
Edited: `ui/widgets.py` (new `SideNav`, `Collapsible`, `TokenChips`; `ScrollFrame` moved here, still importable from `luckytwitch_downloader`), `ui/theme.py` (styles `Nav`, `NavSel`, `CardGhost`, `Chip`), `luckytwitch_downloader.py` (the old `build_options_tab` removed, Options tab is a plain frame, examples refresh when a VOD loads).

### Release notes
`RELEASE_NOTES.md` has a new **v1.10.0** entry covering Phase 1 and Phase 2 (the file in your zip stopped at v1.8.0; change the number if 1.10.0 does not fit).

### Test status
505 passed, 2 failed (the same 2 timeline tests described above), on Tk 8.6.

### Please check on your machine
- Font sizes in the sidebar and rows (my preview machine uses DejaVu Sans, not Segoe UI).
- The `▸ / ▾` arrow on the Advanced header: if it shows as a box on your Windows, tell me and I will swap it.

## Phase 3: the other tabs + polish  ⏳ after that
- Search: result lists and VOD table styling, empty states.
- Plan: card grouping around the timeline / cut points / clips table, replace the remaining checkbox with a switch, nicer part preview.
- Queue: status colours per job, cleaner log.
- Final pass: keyboard focus order, resize behaviour, full test run, release notes entry.
