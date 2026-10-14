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
477 passed, 2 failed. The 2 failures (`test_gui_timeline.py`: `test_split_at_a_clip...`, `test_refreshing_the_clips...`) fail identically **before any of my changes**
(a 600.4 vs 600 rounding difference when run on Tk 9 on Linux; Windows Python uses Tk 8.6). Worth running the suite once on your machine.

### Files touched
New: `assets/*`, `tools/make_icon.py`, `ui/theme.py`, `ui/widgets.py`, `tests/test_gui_theme_and_icon.py`, this file.
Edited: `ui/common.py`, `luckytwitch_downloader.py`, `build_windows.bat`, `build_mac.sh`, `installer.iss`.
(`ui/timeline.py` also differs from your zip by one line, a Tk 9 compatibility fix that was already in the working copy; harmless on Tk 8.6.)

### Please check on your machine
- Run `python luckytwitch_downloader.py`: icon in the title bar and taskbar, new buttons/checkboxes/tabs.
- Fonts: my preview machine has no Segoe UI, so bold weights and spacing are only truly visible on yours. Tell me if text feels too big or small.

## Phase 2: Options tab redesign  ⏳ next

Plan:
- Left sidebar with sections, one visible at a time (no more long scroll): **Output · Cuts · Chapters · Premiere · Chat · Clips · Tools**.
- Every setting = bold name + one-line hint + control on the right; switches instead of checkboxes; the long explanations move into *i* tooltips.
- Template fields (`{streamer} {date} ...`) get clickable token chips and a **live filename example**.
- The four Premiere/markers options grouped in one "Premiere Pro" section.
- Rarely-changed settings go under a collapsed **Advanced** area inside each section.

Proposed split (tell me what to move):
- **Up front (changed often):** output folder, format, strategy, frame-exact cuts, keep full VOD, chat download on/off, Premiere plugin `.markers.json`, game markers.
- **Advanced (set once):** file and folder name templates, subfolders, download threads, Auto threshold %, chapter title / tail / gap name, `.clips.json`, Premiere XML, single-clip name and padding, chat format and embed, tools and yt-dlp auto-update.

## Phase 3: the other tabs + polish  ⏳ after that
- Search: result lists and VOD table styling, empty states.
- Plan: card grouping around the timeline / cut points / clips table, replace the remaining checkbox with a switch, nicer part preview.
- Queue: status colours per job, cleaner log.
- Final pass: keyboard focus order, resize behaviour, full test run, release notes entry.
