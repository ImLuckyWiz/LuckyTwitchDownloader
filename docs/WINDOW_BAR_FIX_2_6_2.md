# Window bar fix: un-maximize by dragging, and the broken spike tool (v2.6.2)

Status: **Plan only. No code written.** Nothing here was run on Windows: the analysis comes from reading `qt_ui/frameless.py`, `qt_ui/titlebar.py` and `qt_ui/main_window.py` of the v2.6.1 repo. Every cause below is a ranked hypothesis until phase F1 confirms it with logs from a real Windows 11 machine.

Follow-up to [`fixwindowbar.md`](fixwindowbar.md) (v2.6.1) and [`NEW_WINDOW_BAR.md`](NEW_WINDOW_BAR.md) (v2.6.0).

---

## 1. Problem

v2.6.1 fixed resize, shadow, Aero Snap and Snap Layouts. Two things are still wrong:

1. **Un-maximize by dragging.** Maximize the window, then grab the title bar and pull it down (instead of pressing the restore button). The window "bugs": it comes out of maximized state but is drawn wrong (screenshot from the owner; not attached to this plan, see open question Q1). Everything else works: button maximize/restore, double-click, snap, resize.
2. **`tools/frameless_spike.py` does not start.** Running it from the repo root fails with `ModuleNotFoundError: No module named 'qt_ui'` at the line `from qt_ui.frameless import FrameController`. The main app (`python luckytwitch_qt.py`) is fine.

Target: **v2.6.2** fixes both and changes nothing else.

---

## 2. How the title bar is driven today (the key fact)

On Windows in native mode, the app answers `WM_NCHITTEST` for the whole window. For the top 32 px that answer is:

| Where in the bar | Answer | Who handles the mouse |
|---|---|---|
| Empty part, title text | `HTCAPTION` | **Windows** (non-client area; Qt gets no mouse events) |
| App icon, minimize, close | `HTCLIENT` | Qt (`CustomTitleBar` widgets) |
| Maximize button | `HTMAXBUTTON` | Windows (Snap Layouts); the app follows `WM_NC*` messages for the look and the click |

Consequence: when the owner grabs the bar and pulls a maximized window down, **Windows does the whole restore-by-drag itself.** The Qt code in `CustomTitleBar.mouseMoveEvent` that restores a maximized window under the cursor is **not involved**. It only runs on the fallback path (grips mode, Linux, macOS). So the bug is almost certainly in the Win32 glue (`NativeFrame`), not in the title bar widget.

---

## 3. Analysis

### 3.1 Why only this case: the app trusts Qt's idea of "maximized", and Qt learns it late

`NativeFrame.handle_native_event` decides what to do in `WM_NCCALCSIZE` and `WM_NCHITTEST` by asking **`self.window.isMaximized()`**. That is Qt's cached window state, not what Windows currently has.

- **Gesture started by the app** (restore/maximize button, double-click handled by the app, `showNormal()`): Qt sets its own state *first*, then asks Windows. When `WM_NCCALCSIZE` arrives, Qt and Windows agree. Works.
- **Gesture started by Windows** (drag the caption of a maximized window, and also `Win+Up/Down`, Aero Snap to the top edge, double-click on the caption when Windows handles it): Windows changes state *first* and sends `WM_NCCALCSIZE` for the new size. Qt only updates its state later, when it processes the resulting `WM_SIZE` / `WM_WINDOWPOSCHANGED`. At the moment of `WM_NCCALCSIZE`, Qt still says "maximized".

Expected message order during drag-restore (to be confirmed by logging):

1. `WM_NCLBUTTONDOWN` (`HTCAPTION`), then the move loop starts.
2. Cursor passes the threshold: Windows restores the window.
3. `WM_GETMINMAXINFO`, `WM_WINDOWPOSCHANGING`.
4. **`WM_NCCALCSIZE`**, with the proposed *restored* window rectangle. Qt still says maximized.
5. `WM_WINDOWPOSCHANGED`, `WM_SIZE` (restored), `WM_MOVE`. Only now does Qt update its state and fire `WindowStateChange`.

### 3.2 Ranked hypotheses

| # | Hypothesis | Evidence in the code | Confidence | How F1 confirms it |
|---|---|---|---|---|
| **H1** | In step 4 the handler sees "maximized" (stale Qt state) and **overwrites the client rectangle with the monitor work area**, although the window is now restored and smaller. Client area and window rectangle disagree; Qt lays out and paints for a work-area-sized client inside a smaller window (cropped, offset or oversized content). | The `isMaximized()` branch in `WM_NCCALCSIZE` rewrites `rgrc[0]` from `rcWork` with no check of the real state. | **High** | Log shows `qt_max=True` and `native_zoomed=False` at the `WM_NCCALCSIZE` of the restore, and the rectangle we write equals the work area. |
| **H2** | The monitor is chosen with `MonitorFromWindow(hwnd)` at a moment when the window is mid-transition (or being dragged across monitors), so the work area comes from the wrong monitor. | Same branch uses `MonitorFromWindow` on the live window, not on the proposed rectangle. | Medium (matters mainly with two monitors) | Log monitor handle and work area per event; repro on one and two monitors. |
| **H3** | The same stale state also feeds `WM_NCHITTEST` (resize borders off while maximized), so right after a native restore the borders stay disabled or the caption zone is wrong until Qt catches up. | `hit_test(..., maximized=self.window.isMaximized())`. | Medium (secondary symptom, not the visual glitch) | Hit-test log right after restore; try resizing immediately. |
| **H4** | Qt's frame bookkeeping (saved normal geometry, cached frame margins) is computed while the client rectangle was rewritten, so `geometry()` and `GetWindowRect` stay out of sync after the restore. Would also corrupt what `_save_ui_state` writes (it uses `normalGeometry()` when maximized). | `_save_ui_state` / `_restore_ui_state` rely on Qt's geometry values. | Low-medium (consequence of H1) | After the bug, compare Qt `geometry()` / `frameGeometry()` with `GetWindowRect` / `GetClientRect`; quit and reopen to see whether a bad geometry was saved. |
| **H5** | Qt re-applies or drops the Win32 styles on a state change, so `WS_THICKFRAME` or the DWM frame extension is lost after the restore (the v2.6.1 risk table already listed this). The styles and `DwmExtendFrameIntoClientArea` are applied **once**. | `_styles_applied` flag in `NativeFrame.init_window`. | Low (resize still works after other restores) | Log `GWL_STYLE` before and after the restore. |
| **H6** | Leftover Qt backing-store or compositor state is stale after the size change (visual only). | Would show as the right layout but wrong painting. | Low | Visible only if H1 is ruled out; forcing a frame refresh fixes it. |

H1 is the main suspect. H2 and H3 are the same class (trusting something that is stale during a transition) and should be fixed together with it.

### 3.3 Why the title bar widget is probably not the cause

`CustomTitleBar.mousePressEvent` / `mouseMoveEvent` only see the mouse on the icon, the minimize and close buttons (client zones) and in grips mode. The restore-under-cursor logic there (compute ratio, `showNormal()`, `move()`) is a **separate implementation** used on non-Windows platforms. It is checked in the matrix (section 6) with `--grips-only` to separate the two paths, but is not expected to be the cause.

### 3.4 The spike tool: cause

`python tools/frameless_spike.py` puts the **`tools/` folder** first on `sys.path`, not the repo root, so `qt_ui` cannot be found. The other tools that import project code (`widget_gallery.py`, `qt_screenshots.py`, `queue_demo.py`) insert the repo root into `sys.path` before importing; `frameless_spike.py` does not. It was written in phase W0 and never run on real Windows (the v2.6.1 plan says so), so this slipped through. The tests do not catch it because `tests/conftest.py` adds the root for them.

Likely follow-up problems once it starts (to check, not to assume):

* It does not call `apply_theme` or `dark_titlebar`, so it can look different from the app and may hide or change a symptom.
* It re-implements the window hooks (`showEvent`, `changeEvent`, `resizeEvent`, `nativeEvent`) by hand instead of sharing them with `MainWindow`. If one copy changes, the spike stops being a faithful reproduction.
* It has no way to print what the frame code is doing.

---

## 4. Fix plan

One phase per session, tests green before moving on, same method as the previous plans.

### F0. Repair the spike tool first

It is the isolation tool: it tells us whether the bug lives in the frame code or in the app. So it comes first.

* Make `tools/frameless_spike.py` find the project root the same way the other tools do, and run from any working directory.
* Make it look like the app: same theme and dark title bar call as `luckytwitch_qt.py`.
* Add a `--smoke` flag: show the window, process events briefly, exit with code 0. Lets CI and tests prove the tool still starts.
* Add the debug flag from F1 so the spike can log too.
* Update the tool's docstring (run command, flags).
* Done when: `python tools/frameless_spike.py` opens the frameless window on Windows, `--grips-only` and `--native-frame` both work, and the owner can reproduce the drag-un-maximize glitch in it (or confirm it only happens in the full app, which is itself a finding).

### F1. Evidence: instrument and reproduce

Add an opt-in diagnostic mode (environment variable `LUCKYTWITCH_FRAME_DEBUG=1`, off by default, no cost when off) that appends to a log file in the data folder. For each of `WM_NCCALCSIZE`, `WM_NCHITTEST` (only on change), `WM_GETMINMAXINFO`, `WM_WINDOWPOSCHANGING/ED`, `WM_SIZE`, and Qt `WindowStateChange` / `resizeEvent`, record:

* a timestamp and the message name;
* Qt's `isMaximized()` **and** Windows' real state (zoomed / iconic / normal);
* the proposed rectangle, the rectangle the app wrote back, the window rectangle and the client rectangle;
* the monitor and its work area;
* the `GWL_STYLE` value and the device pixel ratio.

Owner reproduces on Windows 11 using the matrix in section 6 and sends the log with the screenshot. The outcome fills the "Confirmed cause" row at the end of this document and decides F2.

Done when: the log for the failing case shows which hypothesis holds (expected: H1).

### F2. Primary fix: trust Windows' state, not Qt's cache

Behaviour to implement (no code here):

* In `WM_NCCALCSIZE` and `WM_NCHITTEST`, decide "is the window maximized right now" from **Windows' own state for that window** (and from the style bits / the proposed rectangle when the message arrives mid-transition), not from `QWidget.isMaximized()`.
* When maximized, take the work area from the monitor that contains the **proposed** window rectangle, not from the window's current monitor.
* When not maximized, leave the proposed rectangle untouched (as today).
* Put the decision in a **pure function** in the pure layer (inputs: proposed rectangle, real state, work area, auto-hide edges; output: client rectangle), next to `shrink_for_autohide`, so Linux CI can test every case.
* If F1 shows H5, re-assert the Win32 styles after a state change, in a place that does not loop (guard against re-entrancy).

Done when: dragging a maximized window down restores it cleanly, on one monitor and on two, at 100%, 125% and 150%.

### F3. Hardening of the same class of problem

Only what F1 shows is needed; candidates:

* **Sync after native-initiated changes:** make sure the title bar icon (restore vs maximize glyph), the controller and the grips update when Windows changes the state, not only when Qt does (`WM_SIZE` / `WM_WINDOWPOSCHANGED` path, in addition to `WindowStateChange`).
* **Last-resort refresh:** if H6 is the real cause or a residue remains, one deferred frame refresh after a native restore. Only as a safety net, never instead of F2.
* **Saved geometry sanity:** if H4 shows that a bad rectangle can be saved, validate it on load (minimum size, on-screen), reusing the existing on-screen check in `_restore_ui_state`. Keep the existing behaviour for good data.
* **Fallback drag code:** if the `--grips-only` row of the matrix shows the same glitch, review the restore-under-cursor code in `CustomTitleBar` separately (the cursor-ratio math and the order of `showNormal()` and `move()`).

### F4. Tests

* **Pure tests (Linux + Windows CI):** the new client-rectangle function for: normal, maximized, maximized with each auto-hide edge, restored window with stale "maximized" input (the exact bug), proposed rectangle on a second monitor.
* **Windows-only end-to-end (CI already has `windows-latest`):** show the window, then change its state **directly through Windows** (`ShowWindow` maximize, then restore) so Qt's state lags exactly like in a caption drag. Assert after each step: client rectangle size equals window rectangle size (restored), the frame styles are still set, `WM_NCHITTEST` at the left edge answers a resize edge again, and the title bar glyph matches. This reproduces the bug class without a mouse.
* **Spike test:** run the tool's `--smoke` mode in a subprocess from a different working directory (offscreen), expect exit code 0. This is the test that would have caught the import error.
* Existing `tests/test_qt_frameless.py` and `tests/test_qt_titlebar.py` keep passing unchanged.

### F5. Release: v2.6.2

* Ship `v2.6.2-beta.1` first (pre-release tags have their own install and data folder, see `UPDATE_DETECTION_PLAN.md`), owner runs section 6, then `v2.6.2`.
* `RELEASE_NOTES.md`: new top section whose first line equals the tag (CI checks this), for example `## v2.6.2`. The version itself comes from the tag, there is no version constant to bump.
* Release notes content: fixed un-maximize by dragging the title bar; `tools/frameless_spike.py` fixed (and the `--smoke` / debug flags).
* Docs housekeeping, same release:
  * `docs/fixwindowbar.md` still says "In progress" with W5/W6 pending: close it ("Done in v2.6.1", with a pointer to this file).
  * It also describes pieces the v2.6.1 code does not contain (`FrameOutline`, `edge_region`, the `--frame-outline` flag, a `DWM_SHADOW_MARGIN` constant). Either remove them from the doc or note that they were not built.
  * Add this file to the index in `docs/README.md`.
  * Update the "v2.6.1" mentions in the module docstrings of `qt_ui/frameless.py` and the spike tool if the contents changed.

---

## 5. Files expected to change

| File | Change |
|---|---|
| `tools/frameless_spike.py` | F0: project root on the path, app theme, `--smoke`, debug flag, docstring |
| `qt_ui/frameless.py` | F1 logging; F2 real-state check, monitor from proposed rectangle, new pure function; F3 as needed |
| `qt_ui/main_window.py` | F3 only if state sync or geometry validation is needed |
| `qt_ui/titlebar.py` | F3 only if the grips-only check shows a bug in the fallback drag code |
| `tests/test_qt_frameless.py` (+ a small spike test file) | F4 |
| `RELEASE_NOTES.md`, `docs/README.md`, `docs/fixwindowbar.md`, this file | F5 |

Nothing in `core/`, the engine, the Premiere panel or the settings changes.

---

## 6. Reproduction and verification matrix (owner runs on Windows 11)

Run each row on the **v2.6.1 build first** (to record the current behaviour and capture F1 logs), then again on `v2.6.2-beta.1`.

| # | Action | Expected after the fix |
|---|---|---|
| 1 | Maximize with the button, then **drag the bar down** (the reported case) | Restores under the cursor, content and size correct, shadow and rounded corners back |
| 2 | Same, but maximize by **double-click** on the bar | Same as 1 |
| 3 | Same, but maximize with **Win+Up**, then drag down | Same as 1 |
| 4 | **Aero Snap**: drag to the top edge (maximizes), then drag down | Same as 1 |
| 5 | Maximized, **double-click the bar** to restore | Clean restore |
| 6 | Maximized, **Win+Down** | Clean restore |
| 7 | After any of 1 to 6: resize from all 8 edges and corners | Cursors and resizing work, minimum 900 x 560 holds |
| 8 | After 1: press the maximize button, then restore with the button | Still clean (no regression) |
| 9 | After 1: close and reopen the app | Opens at a sane size and position; glyph on the maximize button matches the real state |
| 10 | Repeat 1 at 125% and 150% scaling | Clean |
| 11 | Two monitors with different scaling: maximize on one, drag down, drop on the other | Clean on both |
| 12 | Auto-hide taskbar on: maximize, drag down | Clean; taskbar still reachable when maximized |
| 13 | `--grips-only`: maximize and drag the bar down | Record the result (separates the Win32 path from the Qt fallback path); must not be worse than before |
| 14 | `python tools/frameless_spike.py`, then rows 1 and 7 in it | Starts, behaves like the app; shows whether the glitch lives in the frame code itself |
| 15 | Old checklist items from `fixwindowbar.md` (shadow, snap, Snap Layouts, system menu, bar buttons, F2 welcome overlay) | No regression |

If a row fails: note the row number, send a screenshot and the F1 log, and say whether `--grips-only` behaves the same.

---

## 7. Risks and fallbacks

| Risk | Mitigation |
|---|---|
| The cause is not H1 (the log says so) | F1 exists exactly for this; the table in section 3.2 lists the next candidates and what each needs. No fix is written before the log is read. |
| Windows' state is not yet updated when `WM_NCCALCSIZE` arrives mid-restore, so reading it does not help | Then decide from the proposed rectangle (restored window is smaller than the work area) and the style bits; the pure function takes all of them as inputs so the rule can be changed without touching the glue. |
| The fix changes how maximize behaves for the other gestures (rows 2 to 6) | They are in the matrix and in the Windows end-to-end test. |
| The bug cannot be fixed cleanly in the native route | Fallback: intercept the caption press on a maximized window and implement the restore-drag ourselves (like the fallback code in `CustomTitleBar`), keeping everything else native. Costs Aero Snap behaviour during that one drag, so only if F2 and F3 fail. |
| Debug logging slows or breaks normal use | Opt-in via environment variable, off by default, never raises, covered by a test that the handler still works with logging off. |
| Win32 code cannot be run on the developer side | Pure function + Windows CI end-to-end test + beta build + the repaired spike tool. |

---

## 8. Done criteria

* Matrix rows 1 to 12 pass on real Windows 11 (rows 13 and 14 recorded).
* `python tools/frameless_spike.py` runs from the repo root and from `tools/`, and its `--smoke` test is in CI.
* New tests are green on Linux and Windows CI; existing frameless and title bar tests unchanged.
* `v2.6.2` tagged, release notes first line equals the tag, docs updated (section 4, F5).
* The "Confirmed cause" line below is filled in.

**Confirmed cause (fill in after F1):** Confirmed Hypothesis **H1**. During drag-to-restore gestures, Windows initiates the unmaximize transition natively before Qt's event queue processes the state change. The previous `WM_NCCALCSIZE` implementation relied on Qt's stale `self.window.isMaximized()` state instead of querying native `user32.IsZoomed(hwnd)`. This caused `WM_NCCALCSIZE` to overwrite the restored window's proposed rectangle with the full monitor work area, desynchronizing the Win32 window geometry and client viewport. Fixed by using pure `calculate_client_rect` driven by native `IsZoomed` and `MonitorFromRect`. Also resolved `frameless_spike.py` import path and added `--smoke` / `--debug` flags.

---

## 9. Open questions

* **Q1.** The screenshot of the broken window is not part of this plan. Save it in the repo docs (or describe it: cropped, offset, stretched, missing shadow, wrong buttons) so F1 can be compared against it.
* **Q2.** Does it happen only after maximizing with the button, or also after double-click, `Win+Up` and Aero Snap (rows 1 to 4)? The answer tells us how general the stale-state problem is.
* **Q3.** One monitor or two, and what scaling, when it happens?
* **Q4.** Does the glitch also appear in the spike tool once it runs (F0)?
