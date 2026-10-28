# New Window Bar Plan (custom title bar)

Status: Done in v2.6.0 (implemented via Option B cross-platform FramelessWindowHint)

This document plans a **custom window bar** for **LuckyTwitch Downloader**: the OS title bar is replaced by a bar drawn by the app, in the same dark/purple theme as the rest of the UI, with its own minimize / maximize / close buttons. It is a plan only. No code is written until the owner approves the open decisions in section 12.

It slots into `docs/NEXT_UPGRADES_PLAN.md` as **Phase W** (section 6A), after the engine split (Phase E) and before the Premiere panel work (Phase P). Same working method as the other plans: one phase per session, tests green before the next, release notes per phase, nothing "verified by reading".

---

## 1. Goals and Non-Goals

**Goals**

* One visual identity: the top of the window uses the app's tokens (`core/palette.py`, `qt_ui/tokens.py`) on every OS, instead of the OS title bar colour.
* **Keep every native behaviour people rely on** (Windows): resize from all edges, shadow, Aero Snap by dragging, Snap Layouts on the maximize button (Windows 11), double-click to maximize, right-click / `Alt+Space` system menu, `Win+Arrow` keys.
* Optionally (phase W3) fold the command bar (VOD entry, **Get info**, **Twitch API**) into the bar, so the window shows one top strip instead of two.
* Zero regression risk for anyone who does not like it: a setting and a command-line flag go back to the native frame.

**Non-goals**

* No new third-party dependency (the project ships with `requests`, `pillow`, `nuitka`, `zstandard`, `PySide6`). Win32 calls go through `ctypes` from the standard library.
* No translucent window / `WA_TranslucentBackground` tricks to fake shadows or rounded corners (fragile, and costs rendering performance).
* No change to the engine, to `.markers.json`, to the Premiere panel, or to job settings.
* Dialogs keep the native frame in the first release (see section 8).
* macOS and Linux do **not** get the custom bar in the first release (see section 4). They keep working exactly as today.

---

## 2. Review of the idea we started from

The idea came with an explanation of how apps like Discord, Steam or VS Code do it. It is mostly right. What the plan keeps, and what it adjusts after reading this repository:

| Point in the original idea | Verdict | What the plan does |
|---|---|---|
| A plain `Qt.FramelessWindowHint` window loses the shadow, Aero Snap and edge resizing | Correct | Plain frameless is only the fallback (Option B, section 4). The main route keeps the native window styles. |
| On Windows, handle `WM_NCCALCSIZE` and `WM_NCHITTEST` in `nativeEvent` | Correct, and the standard route | Option A. It is the part with real risk, so it gets a spike (W0) before any product code. |
| The Snap Layouts flyout on the maximize button | Correct, but with a known catch | Windows only shows the flyout if the hit-test answers "maximize button" for that rectangle. Then Qt stops receiving hover and click for that button, so the app must follow the `WM_NC*` mouse messages itself to draw hover/pressed. Planned in W1, verified in W0. |
| macOS: unified title bar, traffic lights stay | Right idea, not for the first release | Qt 6.9 added `Qt::ExpandedClientAreaHint` and `Qt::NoTitleBarBackgroundHint` for this. The project pins PySide6 6.12.0, so the flags exist, but there is no Mac to verify on (V4/V5 are still open). macOS stays native until a Mac is available (phase W5). |
| Linux: "render native controls" | Too vague | There is no native control to borrow in a frameless Qt window. Linux uses the same custom bar with `startSystemMove()` / `startSystemResize()`, and is experimental and opt-in (phase W4). |
| Moving the command bar into the title bar saves vertical space | True, but small | Today the command bar plus the VOD strip use roughly 100 px at the top. Folding the command bar in saves about one row (the exact number is measured in W3). The main win is coherence, not space. It is also the riskiest part for the tests and the keyboard order, so it is its own phase (W3) and can be skipped. |
| Close button with a soft red hover | Fine | A new colour token, checked by the contrast tests (section 5.4). |
| "Difficulty medium (3/5)" | Agreed for Windows; higher for "all platforms" | Windows is scoped as the real work. The other platforms are optional follow-ups. |

---

## 3. Findings: how the window is built today

All of this comes from reading the repository, not from running it.

| Area | Finding | Consequence for the bar |
|---|---|---|
| Main window | `MainWindow(QMainWindow)` in `qt_ui/main_window.py`, native frame. Title `LuckyTwitch Downloader`, start size 1020x910, minimum 900x560. | The minimum width (900) is the budget for everything in the bar (section 5.2). |
| Layout | `central` is a `QHBoxLayout`: `NavRail` (46 px collapsed, 134 expanded, full height) on the left, `main_pane` on the right. `main_pane` is a `QVBoxLayout`: `top_wrap` (`CommandBar` + `VodStrip`), the `PageStack`, and the status bar. | A bar across the full width means a new root: a vertical layout with the bar on top and the current horizontal layout below it. The rail would no longer be the full window height; it starts under the bar. |
| Command bar | `CommandBar` (`qt_ui/shell.py`): prompt label, `vod_entry`, Paste/Clear button, **Get info**, account dot, **Twitch API** button, and a wrapped `info_label` line below. `MainWindow` aliases `vod_entry`, `vod_action_btn`, `info_btn`, `api_btn`, `info_label` from it, and the "Getting info..." animation writes to `info_label`. | Moving it keeps those attribute names, so most code and tests keep working. The `info_label` line needs a new home (open decision 2). |
| Dark title bar today | `theme.apply_theme` sets Qt's colour scheme to Dark (Qt 6.8+) and `theme.dark_titlebar(window)` calls DWM (`DwmSetWindowAttribute`, attributes 20 and 19). Called by `MainWindow`, `TwitchDialog` and `UpdateDialog`. | Stays as is for the dialogs. For the main window in custom mode the call becomes unnecessary but harmless. |
| Geometry persistence | `_save_ui_state` stores `x, y, w, h`, active tab and rail state in `luckytwitch_ui.json` (`core/ui_state.py`). `_restore_ui_state` resizes and moves from it. | There is **no maximized flag** and **no check that the saved position is still on a screen**. With a native frame this is a minor annoyance; with a custom bar it matters more (W2 fixes both). |
| Welcome overlay | `WelcomeOverlay` is a child of the main window, resized to the full window in `resizeEvent`. | It would cover the bar too, hiding the window buttons during first run. The bar must stay above it (section 8). |
| Toasts | `ToastHost` anchors cards to the bottom-right of the window (`MARGIN_BOTTOM = 38`, above the status bar). | Unaffected, as long as it stays parented to the window. Checked in W1. |
| Close | `closeEvent` asks "A job is running. Cancel it and quit?", cancels tools/chat contexts, saves settings and UI state, removes the heartbeat file. | The custom close button must call `window.close()`, never `QApplication.quit()`, so all of that still runs. |
| Keyboard order | A test follows the focus chain and expects `vod_entry -> info_btn -> api_btn -> tabs.tabBar()`. | Every new button in the bar is `NoFocus`. |
| Icons | `qt_ui/icons.py` draws icons in code (24-unit grid, strokes). `minus` and `x` exist; there is no maximize or restore glyph. `tests/test_qt_icons.py` holds a fixed `CATALOG` of names. | Add `window-minimize`, `window-maximize`, `window-restore` (and reuse `x` for close). The catalog test is updated deliberately. |
| Motion | `qt_ui/motion.py` has `Motion.enabled()` (off under pytest) and `ButtonHoverAnimator` for custom-painted buttons. | The close and caption buttons use it, so reduced-motion rules and tests keep working. |
| Packaging | Nuitka standalone/app builds with `--enable-plugin=pyside6`. | `ctypes` is stdlib, nothing to add to the build scripts. The CI smoke test starts the frozen app with `QT_QPA_PLATFORM=offscreen`, which cannot exercise Win32 messages (see section 9). |
| Tests | All Qt tests run offscreen on Linux CI (`tests/conftest.py`). | Win32 code must be split into pure functions that run everywhere and a thin glue layer that only runs on Windows. |

---

## 4. Options and recommendation

| | A. Native styles kept + `nativeEvent` (`WM_NCCALCSIZE`, `WM_NCHITTEST`) | B. Plain `FramelessWindowHint` + `startSystemMove` / `startSystemResize` | C. `Qt::ExpandedClientAreaHint` (Qt 6.9+) |
|---|---|---|
| What it is | Window keeps the Win32 caption/thickframe styles; the app answers the two messages so the client area covers the title bar | Qt removes the frame; the app starts OS-driven moves and resizes from its own widgets | Qt expands the client area into the title bar zone and keeps the system's own controls |
| Shadow, snap, double-click, system menu | All native | Partly: depends on the platform, no shadow on Windows | Native |
| Snap Layouts on maximize | Yes (with the hover catch from section 2) | No | Native buttons, so yes |
| Our own button look (red close hover, theme colours) | Yes | Yes | No, the buttons are the system's |
| Windows 10 | Works (no Snap Layouts, no rounded corners: that is the OS) | Works | To be checked |
| Risk | Highest: Win32 details (maximized overhang, DPI, auto-hide taskbar) | Lowest, but a flatter result | Unknown on Windows for a `QMainWindow`; Qt's own blog lists Windows as supported but the behaviour was not tested here |
| Where it fits | **Windows, main route** | **Linux, and the Windows fallback** | **macOS (phase W5)**, and a Windows candidate to evaluate in the spike |

**Recommendation (to be confirmed by the W0 spike):** Option A on Windows, Option B on Linux (experimental), Option C on macOS later. Option C on Windows is evaluated in the spike because if it behaves, it is far less code than A, at the cost of not owning the button look. The owner decides after seeing the spike (open decision 1).

---

## 5. Design

### 5.1 Layout

Phase W1 ("classic bar") keeps the command bar where it is; the bar only replaces the OS title bar.

```
+--------------------------------------------------------------------------------+
| [icon] LuckyTwitch Downloader                              [ - ] [ [] ] [ X ]  |  bar, 32 px
+------+-------------------------------------------------------------------------+
| rail | VOD URL or ID: [ paste a link ............ ][Paste][Get info] o [Twitch ]|  command bar (unchanged)
|      | No VOD loaded.                                                          |
|      | ...tabs / pages...                                                      |
|      | status bar                                                              |
+------+-------------------------------------------------------------------------+
```

Phase W3 ("integrated", optional, a setting) moves the command bar into the bar:

```
+--------------------------------------------------------------------------------+
| [icon] [ Paste a Twitch VOD link or ID ........ ][Paste][Get info] o [Twitch API]  ~drag~  [ - ][ [] ][ X ] |
+------+-------------------------------------------------------------------------+
| rail | VodStrip / info line / tabs / status bar                                |
```

### 5.2 Width budget at the 900 px minimum (integrated mode)

Icon and margins about 44, window buttons 3 x 46 = 138, **a drag gap of at least 48** so the window can always be grabbed. That leaves roughly 670 px for the command row. The existing widgets need about 330 px without the entry, so the entry keeps at least 200 px. The entry gets a maximum width (about 560) so on wide windows the drag gap grows instead of the entry. If a later change makes the row not fit, the Paste button collapses to an icon first.

### 5.3 The pieces (new files, no behaviour in `core/`)

| File | Role |
|---|---|
| `qt_ui/window_bar.py` | `WindowBar` (the bar widget: icon, title, optional slot for the command row, drag area) and `CaptionButton` (minimize / maximize-restore / close; custom-painted with `ButtonHoverAnimator`; `NoFocus`; accessible names and tooltips). Emits `minimize_requested`, `maximize_toggle_requested`, `close_requested`. Knows the window state (maximized/active) only through `set_maximized(bool)` and `set_active(bool)`. |
| `qt_ui/frameless.py` | Platform glue in two layers. **Pure layer** (no Qt, no ctypes): `hit_test(x, y, w, h, border, bar_height, maximized, client_rects) -> Region` and the maximized-overhang arithmetic. **Glue layer**: the Windows `nativeEvent` handler (parses `MSG`, calls the pure layer) and, for Linux, edge grips that call `startSystemResize`. |
| `qt_ui/main_window.py` | Builds the new root layout when custom mode is on, keeps `WINDOW_TITLE` for the taskbar and Alt+Tab, routes the bar signals to `showMinimized()`, `showMaximized()/showNormal()` and `close()`. |
| `core/ui_state.py` | New optional field `window_maximized` (default `False`). Old files without it load as before. |
| `core/settings.py` | New key for the frame mode (default decided in section 12, decision 3). Old settings files keep working. |
| `qt_ui/icons.py`, `qt_ui/theme.py`, `core/palette.py`, `qt_ui/tokens.py` | Window-button icons, the QSS for `QFrame#windowBar` and the caption buttons, one new colour token for the close hover. |
| `tools/frameless_spike.py` | **Throwaway** script for W0 only (same spirit as `tools/hello_qt.py`). Deleted when W1 starts, or kept as a manual test tool if useful. |

### 5.4 Behaviour spec

* **Drag area** is every part of the bar that is not an interactive child. The hit-test asks the window which widget is under the cursor and treats entries, buttons and the caption buttons as client area; everything else in the bar is caption (this is what gives drag, double-click maximize and the system menu for free on Windows).
* **Resize border** about 6 px on every side (a bit larger at the corners), disabled while maximized.
* **Maximized**: the window must not spill past the monitor by the invisible border width; the glue layer compensates in `WM_NCCALCSIZE`. The bar draws no outline and no rounded corners while maximized; the maximize button shows the restore glyph.
* **Inactive window**: title text and glyphs dim (`QEvent.ActivationChange`), like a native bar.
* **Close** calls `window.close()` so the "A job is running" question, the contexts cancel and the state saving run unchanged.
* **Double-click** on the bar toggles maximize; **right-click** opens the system menu on Windows.
* **Title text**: the app name. Optionally (decision 8) the loaded VOD title after it, elided. The window title (`setWindowTitle`) stays `WINDOW_TITLE` for the taskbar and Alt+Tab; tests that check it keep passing.
* **Look**: bar background `BG` (or `BG2`, decided in W1 against the rail and command bar), caption buttons 46 x 32 with `HOVER` on hover and `PRESSED` on press; close hover uses a new token `CLOSE_HOVER` (soft red, starting from `#c42b1c`, final value chosen so white glyph on it passes the same contrast helper used by `tests/test_qt_contrast.py`). A 1 px `BORDER_STRONG` outline around the window in custom mode (frameless windows look flat without one), hidden when maximized.
* **Accessibility**: tooltips and accessible names "Minimize", "Maximize" / "Restore", "Close". Buttons are not in the tab chain; keyboard users keep `Alt+Space`, `Alt+F4` and `Win+Arrow`. A native title bar exposes its buttons to screen readers on its own; the custom one only exposes what we name, which is why the names are part of the tests.
* **Motion**: hover fades use the motion tokens and `Motion.enabled()`; nothing animates during drag or resize.
* **Recovery**: `luckytwitch_ui.json` and the settings file are never the only way back. `--native-frame` on the command line and the environment variable `LUCKYTWITCH_NATIVE_FRAME=1` force the native frame for that run, so a broken custom frame can never lock someone out. Changing the frame mode in Options takes effect after a restart (window flags are chosen when the window is created).

### 5.5 Windows glue: sketch (not code to paste)

```
nativeEvent(eventType, message):
    if not custom_frame_active or eventType is not windows_generic_MSG: return (False, 0)
    msg = parse MSG from message
    WM_NCCALCSIZE (wParam true): client area = whole window, minus the overhang when maximized  -> result 0
    WM_NCHITTEST: convert lParam to window coordinates (watch DPI)
                  edge/corner (not maximized) -> HTLEFT / HTTOPLEFT / ...
                  maximize-button rect        -> HTMAXBUTTON   (Snap Layouts)
                  minimize / close rects      -> HTCLIENT      (Qt handles them)
                  interactive child           -> HTCLIENT
                  empty bar area              -> HTCAPTION
                  else                        -> HTCLIENT
    WM_NCMOUSEMOVE / WM_NCLBUTTONDOWN / WM_NCLBUTTONUP / WM_NCMOUSELEAVE on the maximize rect:
                  drive the button's hover/pressed look and, on button up, toggle maximize
```

Window styles (keep `WS_THICKFRAME`, `WS_MINIMIZEBOX`, `WS_MAXIMIZEBOX`) and the DWM calls that keep the shadow are the part W0 must confirm on real Windows 10 and 11 before W1 writes them.

---

## 6. Phases

Each phase ends with both suites green (`python -m pytest tests -q`; `npm test` is untouched, the panel does not change) and a tag, like the other plans.

### W0. Spike and decisions (no product code)

* Write `tools/frameless_spike.py`: a minimal `QMainWindow` using Option A, one using Option B, and one using Option C, each with a fake bar and a dark body.
* The owner runs it on Windows 11 (and Windows 10 if one is available) and ticks each line of the spike checklist in section 10. Results are written into a new "Spike results" section of this file.
* Outcome: the owner picks the Windows option (decision 1) and the plan is updated with the exact styles and DWM calls that worked.
* Done when: the checklist is filled and decision 1 is recorded. Nothing under `qt_ui/` or `core/` changes.

### W1. Foundation: classic bar on Windows (v2.6.0-beta.1)

* `core/palette.py`: `CLOSE_HOVER`. `qt_ui/icons.py`: the three window glyphs. `qt_ui/theme.py`: QSS for the bar and caption buttons.
* `qt_ui/window_bar.py` and the pure layer of `qt_ui/frameless.py`, tested everywhere; the Windows glue layer behind `sys.platform == "win32"`.
* `MainWindow` builds the new root layout only when custom mode is on (Windows, setting on). With the flag off, the construction path is the current one, untouched.
* Welcome overlay fits under the bar; toasts and status bar checked.
* Options gets a small "Window frame" row (native / custom) with a restart note.
* Released as a **pre-release build** (the app already keeps pre-release builds with a hyphen in the version in their own `LuckyTwitch-beta` data folder), so daily use can happen without touching the real settings.
* Done when: tests green, the Windows checklist (section 10) passes on the owner's machine, native mode behaves exactly as before.

### W2. Persistence and robustness (v2.6.0-beta.2)

* `UIState.window_maximized`; save the normal (restored) geometry while maximized; restore maximized.
* Clamp the restored position to the screens that exist now (this also fixes the existing "window opens off-screen after a monitor was unplugged" gap, in both modes).
* Mixed-DPI and multi-monitor pass; taskbar auto-hide pass; `--native-frame` and `LUCKYTWITCH_NATIVE_FRAME`.
* Done when: the multi-monitor and DPI lines of section 10 pass and old `luckytwitch_ui.json` files load unchanged.

### W3. Integrated command bar (optional; v2.6.0)

* The `CommandBar` row moves into `WindowBar` in "integrated" mode; `vod_entry`, `info_btn`, `api_btn`, `vod_action_btn`, `info_label` keep their names on `MainWindow`.
* Decide where `info_label` lives (decision 2): a thin line under the bar, or merged into `VodStrip`.
* Measure the real vertical gain at 1020 x 910 and at 900 x 560 and write it down here. If it is under about one row and the keyboard/test cost is high, the owner may drop W3 and ship W1 + W2 as v2.6.0.
* Done when: the keyboard-order test is unchanged, the width budget holds at 900 px, and classic mode still works.

### W4. Linux custom bar (optional, experimental)

* Option B glue: bar press starts `startSystemMove()`, edge grips start `startSystemResize()`.
* Off by default; verified on at least one X11 and one Wayland session (the owner or a tester). Until then Linux ships native.

### W5. macOS unified title bar (optional)

* Option C flags with the traffic lights kept; the bar content respects the safe-area margins Qt reports for the window. Only after a Mac is available to verify (same condition as V4/V5).

### W6. Themed dialogs (optional)

* A slim themed header for the `ThemedDialog` family so dialogs match the main window. Only if the native dark dialogs next to the custom main window look wrong in daily use (decision 5).

---

## 7. Versions and release

| Phase | Build |
|---|---|
| W0 | none (docs and a spike script only) |
| W1, W2 | pre-release builds (`v2.6.0-beta.N`), own data folder |
| W3 | joins the same line |
| Final | `v2.6.0` with a `## v2.6.0` section at the top of `RELEASE_NOTES.md` (the workflow checks the first line against the tag) |

Because Phase W sits between E (v2.5.0) and F, every version in section 8 of the master plan moves up one minor (F1 becomes v2.7.0, and so on). This is recorded in `docs/NEXT_UPGRADES_PLAN.md`. If the owner prefers a different order, only the numbers change.

Rollback is cheap by design: the native construction path is never edited, so flipping the default back (or the flag) restores today's behaviour.

---

## 8. Other windows and overlays

| Surface | Decision |
|---|---|
| `ThemedDialog`, `UpdateDialog`, `TwitchDialog`, `ShortcutsDialog`, file pickers | Keep the native frame and `dark_titlebar()`. Reassessed in W6. Modal dialogs over a custom-frame parent are a normal Qt case, checked in W1. |
| `WelcomeOverlay` | Covers the body only; the bar stays above it, so a first-time user can always move, minimize or close. Geometry logic moves from "whole window" to "the body area"; the welcome tests are updated. |
| `ToastHost` | Unchanged; verify the 38 px bottom margin against the 1 px outline. |
| `Tooltip` (own `Qt.ToolTip` labels) | Unchanged. |
| `Timeline` | An in-window widget, not a separate window. Unchanged. |

---

## 9. Testing strategy

CI runs the Qt tests offscreen on Linux, which has no Win32 messages. So:

* **Pure layer, tested everywhere:** a table of `hit_test` cases (every edge, every corner, the bar, each caption button, interactive children, maximized, tiny window), and the maximized-overhang arithmetic.
* **Glue layer, tested on Windows:** a small set of tests that run only when `sys.platform == "win32"`, feeding fabricated `MSG` values. They run in a `windows-latest` CI step limited to the two new test files (the build job already uses a Windows runner, so no new runner type).
* **Widget tests (offscreen):** `tests/test_qt_window_bar.py` covers signals, glyph swap on maximize/restore, active/inactive dimming, tooltips and accessible names, `NoFocus`, hover colour with motion disabled, and that the close button reaches `closeEvent` (including the "job running" question, with `dialogs.ask_yes_no` replaced as the other tests do).
* **Existing tests to adjust on purpose:**
  * `tests/test_qt_main_window.py`: root layout shape, tab order unchanged, the bottom-bar-visible-at-minimum-size test unchanged.
  * `tests/test_qt_icons.py`: `CATALOG` gains the new names (a deliberate act, as that file says).
  * `tests/test_qt_contrast.py`: a case for white on `CLOSE_HOVER`.
  * `tests/test_qt_theme.py`: `dark_titlebar` still never raises.
  * `tests/test_qt_welcome.py`: overlay geometry under the bar.
  * `tests/test_qt_shell.py`: only if W3 moves `CommandBar` construction.
  * a `core` test that `UIState` loads old files and round-trips `window_maximized`.
* **Rule kept from the engine split plan:** tests patch where a name is used, not where it is defined.
* **Frozen build:** the CI smoke test must still start the Nuitka build on Windows with the custom frame on.

---

## 10. Verification checklists (owner runs, sends back a screenshot or a note)

**Spike (W0) and every later Windows build**

| # | Check | Passes when |
|---|---|---|
| 1 | Shadow and 1 px outline | The window has a visible shadow (Windows) and does not look flat against the desktop |
| 2 | Resize | All 8 edges/corners resize with the right cursor; minimum size 900 x 560 holds |
| 3 | Drag | Dragging the bar moves the window; dragging from maximized restores it under the cursor |
| 4 | Aero Snap | Drag to left/right/top edges snaps and maximizes; `Win+Arrow` works |
| 5 | Snap Layouts (Windows 11) | Hovering the maximize button shows the layouts flyout, and the button still shows hover/pressed and toggles correctly |
| 6 | Double-click | Double-click on empty bar toggles maximize; double-click on the entry does not |
| 7 | System menu | Right-click on empty bar and `Alt+Space` open the system menu |
| 8 | Maximized | No gap, no overhang past the monitor edge; with the taskbar auto-hidden the taskbar can still be reached |
| 9 | Minimize / restore | Minimize and restore from the taskbar work, with the usual animation |
| 10 | Close | Close with no job closes; with a job running, the "Cancel it and quit?" question appears |
| 11 | Mixed DPI | Moving between two monitors of different scale keeps the bar crisp and the hit areas right |
| 12 | Windows 10 | Same list, minus Snap Layouts and rounded corners |
| 13 | Recovery | `--native-frame` shows the OS title bar and everything works |
| 14 | Welcome | First-run overlay: the window buttons and dragging still work |

**Later, when hardware exists:** Linux X11 and Wayland (W4) and macOS (W5), each with its own short list added to `docs/VERIFICATION_CHECKLIST.md` when that phase starts. Until then they stay "not verified" in the README, like V4/V5.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Snap Layouts: the maximize button needs `HTMAXBUTTON` yet Qt then gets no hover/click | Follow `WM_NC*` mouse messages for that one rectangle; check #5 above; if it cannot be made clean, ship without the flyout rather than without the shadow/snap (owner decision, recorded in W0). |
| Maximized window overhangs the monitor or breaks with an auto-hide taskbar | Overhang arithmetic is a pure function with tests; checks #8 and #11. |
| Mixed-DPI hit-test errors | Hit-test works in device pixels from the message, converted once, tested with scale factors; check #11. |
| Win32 code cannot be tested on Linux CI | Pure/glue split (section 9) and a Windows CI step for the glue. |
| PySide6 update changes `nativeEvent` or the flags' behaviour | PySide6 is pinned (`6.12.0`); the spike result and the tests are the safety net on any bump. |
| People dislike it or hit a bug | Setting, `--native-frame`, the env var, and beta builds in their own data folder first. |
| Integrated bar fights the tests or the keyboard order | W3 is optional and separate; names stay on `MainWindow`; all new buttons are `NoFocus`. |
| Rounded corners absent on Windows 10 | Accepted: it is the OS. The outline keeps it tidy. |

---

## 12. Open decisions (the owner)

1. **Windows route after the spike:** Option A (planned), or Option C if it behaves well and we accept the system's own buttons.
2. **Integrated command bar (W3):** do it or skip it; and where `info_label` goes (thin line under the bar, or inside `VodStrip`).
3. **Default frame mode:** custom on Windows for everyone once W2 passes, or opt-in for one release first. Proposal: opt-in in the beta builds, default on in v2.6.0.
4. **Linux:** native until W4 is verified (proposed), or custom from the start.
5. **Dialogs:** keep native (proposed) or theme them (W6).
6. **Close hover colour:** start from `#c42b1c`, or a softer red closer to the existing `ERR` (`#ff6b6b`); final value must pass the contrast test.
7. **Version slot:** Phase W as v2.6.0 between E and F (proposed), or somewhere else in the order.
8. **Title text:** only "LuckyTwitch Downloader", or also the loaded VOD's title after it.

---

## 13. Definition of done (per phase)

- [ ] `python -m pytest tests -q` is green (CI also green on the Python versions of the matrix, and the Windows glue tests green on the Windows step).
- [ ] The Windows checklist in section 10 passes on the owner's machine for the phase's features.
- [ ] Native mode (flag or setting off) behaves exactly like the previous release.
- [ ] Old `luckytwitch_settings.json` and `luckytwitch_ui.json` files still load.
- [ ] `RELEASE_NOTES.md` section added; its first line matches the tag.
- [ ] README and `docs/README.md` match what shipped; this file's status line and `docs/NEXT_UPGRADES_PLAN.md` are updated.
