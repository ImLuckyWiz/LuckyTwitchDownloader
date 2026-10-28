\# Window frame fix: resize, shadow and snap (v2.6.1)



Status: \*\*In progress.\*\* Code for W1 to W4 written; waiting for the Windows 11 checklist (section 9). Update the phase table (section 6) as work moves.



Follow-up to \[`NEW\_WINDOW\_BAR.md`](NEW\_WINDOW\_BAR.md) (Phase W, shipped in v2.6.0).



\---



\## 1. Problem



In v2.6.0 the custom title bar works (buttons, drag, double-click maximize), but the window \*\*cannot be resized\*\*: no cursor change and no reaction on any edge or corner. Maximize / restore still work because they are plain buttons.



\## 2. Cause



`MainWindow` sets `Qt.FramelessWindowHint` when the custom bar is on (`qt\_ui/main\_window.py`). A plain frameless Qt window is a `WS\_POPUP`: Windows gives it \*\*no resize borders, no shadow, no Aero Snap, no Snap Layouts, no system menu\*\*. `NEW\_WINDOW\_BAR.md` planned `qt\_ui/frameless.py` (the native route, "Option A" there) to fix exactly this, but v2.6.0 shipped only the plain-frameless fallback ("Option B" there) with `startSystemMove()` for dragging and nothing for resizing.



(Naming note: in this document \*\*native route\*\* = keep the Win32 frame styles and answer `WM\_NCCALCSIZE` / `WM\_NCHITTEST`; \*\*grips\*\* = small widgets on the edges that call `startSystemResize()`.)



\## 3. Goal



Behave like a professional Windows app, as the owner asked ("everything like a professional app would have done it"):



\* Resize from all 8 edges and corners, with the right cursors; minimum size 900 x 560 holds.

\* Window shadow (and Windows 11 rounded corners, which come from the OS).

\* Aero Snap by dragging to the left / right / top edges; `Win+Arrow`.

\* \*\*Snap Layouts\*\* flyout on the maximize button (Windows 11), with the button still showing hover / pressed.

\* Native drag, double-click to maximize and right-click / `Alt+Space` system menu on the bar.

\* Maximized window fits the monitor exactly (no spill past the screen, auto-hide taskbar still reachable).

\* Mixed DPI and multi-monitor correct.



Non-goals for 2.6.1: the integrated command bar (W3 of the old plan), macOS unified title bar, Linux native look.



\## 4. Approach



On Windows the window keeps `FramelessWindowHint` for Qt, but the app adds the Win32 frame styles (`WS\_CAPTION | WS\_THICKFRAME | WS\_MINIMIZEBOX | WS\_MAXIMIZEBOX | WS\_SYSMENU`) to the real window and answers two messages from `nativeEvent`:



\* \*\*`WM\_NCCALCSIZE`\*\*: the client area is the whole window (no native title bar is drawn). When maximized, the client area becomes the monitor's work area (minus 1 px on an edge that has an auto-hide taskbar).

\* \*\*`WM\_NCHITTEST`\*\*: for every mouse position the app answers what is there: resize edge or corner, caption (empty part of the bar), maximize button, or client. That single answer gives resize, native drag, double-click, system menu and Snap Layouts.

\* \*\*Maximize button (Snap Layouts):\*\* Windows only shows the flyout if the hit-test answers `HTMAXBUTTON` for that rectangle. Qt then gets no hover or click for that button, so the app follows `WM\_NCMOUSEMOVE`, `WM\_NCLBUTTONDOWN`, `WM\_NCLBUTTONUP` and `WM\_NCMOUSELEAVE` itself to draw hover / pressed and to toggle maximize.

\* A thin DWM frame extension (`DwmExtendFrameIntoClientArea`, 1 px) brings the shadow back.



Everywhere else (Linux, macOS, or Windows if the native hook fails) \*\*edge grips\*\* are used: 8 small transparent widgets that call `QWindow.startSystemResize()` and fall back to a manual resize if the platform refuses. So resize can never be missing again.



\## 5. Pieces



| File | Change |

|---|---|

| `qt\_ui/frameless.py` (new) | \*\*Pure layer\*\* (no Qt, no ctypes): `Region`, `edge\_region`, `hit\_test`, `resized\_rect`, `shrink\_for\_autohide`. \*\*Glue\*\*: `NativeFrame` (Win32 styles, DWM, `nativeEvent` handler), `EdgeGrips`, `FrameOutline`, and `FrameController` which owns them and is the only thing the window talks to. |

| `qt\_ui/main\_window.py` | Creates the controller when the custom bar is on; `showEvent` attaches it; `nativeEvent` delegates to it; `resizeEvent` / `changeEvent` refresh it. Adds `LUCKYTWITCH\_NATIVE\_FRAME=1` (promised in `NEW\_WINDOW\_BAR.md`) and the flags below. |

| `qt\_ui/titlebar.py` | `CaptionButton` gets a native-driven hover and pressed look (for the maximize button while Windows owns the mouse). Fallback drag code stays. |

| `tools/frameless\_spike.py` (new) | Tiny standalone window using the same controller. A diagnosis tool: if the app misbehaves, run this to see whether the problem is the frame code or the app. |

| `tests/test\_qt\_frameless.py` (new) | Pure tests, grips tests (run on Linux CI), and Windows-only end-to-end tests that send real `WM\_NCHITTEST` messages (the CI `test` job already runs on `windows-latest`). |

| `docs/`, `RELEASE\_NOTES.md` | This file, the index row, the checklist, release notes. |



Flags (escape hatches, so a broken frame can never lock someone out):



\* `--native-frame` or `LUCKYTWITCH\_NATIVE\_FRAME=1`: OS title bar, no custom bar (already existed; env var is new).

\* `--grips-only`: custom bar, but no Win32 hook (grips for resizing). Use this if the native route misbehaves on some machine.

\* `--frame-outline`: draw the 1 px outline even in native mode (by default it is only drawn when the OS draws no border itself).



\## 6. Phases



| Phase | What | Status |

|---|---|---|

| W0 | Design check against Qt / Win32 behaviour; spike tool kept as `tools/frameless\_spike.py` | Done (tool written, not yet run on real Windows) |

| W1 | Pure layer + tests (`hit\_test`, edges, manual resize, auto-hide shrink) | Done |

| W2 | Edge grips fallback (Linux / macOS / `--grips-only`) + outline | Done |

| W3 | Windows glue: styles, DWM shadow, `WM\_NCCALCSIZE`, `WM\_NCHITTEST`, maximized fit, auto-hide | Done, \*\*needs real Windows 11 check\*\* |

| W4 | Snap Layouts: `HTMAXBUTTON` + `WM\_NC\*` mouse tracking + button look | Done, \*\*needs real Windows 11 check\*\* |

| W5 | Beta round: owner runs section 9, fixes go into `2.6.1-beta.2` | \*\*Next\*\* |

| W6 | Final `2.6.1`: rename the release-notes heading, update `NEW\_WINDOW\_BAR.md` status, tag | Pending |



Delivery: `v2.6.1-beta.1` first (pre-release tags have their own install folder and data folder, see `UPDATE\_DETECTION\_PLAN.md`), then `beta.2` if needed, then `v2.6.1`. The first line of `RELEASE\_NOTES.md` must equal the tag (CI checks this), so it is `## v2.6.1-beta.1` now and becomes `## v2.6.1` at W6.



\## 7. Behaviour spec



\* \*\*Hit regions\*\* (physical pixels, scaled from logical values by the screen's device pixel ratio): resize border 6 px logical on every side, 12 px at the corners; the resize regions are off while maximized. The top 32 px (the bar) is caption, except the minimize and close buttons (client, so Qt gets their clicks) and the maximize button (`HTMAXBUTTON`).

\* \*\*Maximized:\*\* client area = monitor work area; if the taskbar auto-hides on an edge, that edge is shrunk by 1 px so the taskbar can still be revealed.

\* \*\*Min size:\*\* Qt answers `WM\_GETMINMAXINFO` from `setMinimumSize` (900 x 560); checked in the checklist.

\* \*\*Outline:\*\* 1 px `BORDER\_STRONG` line around the window when not maximized, drawn only when the OS draws no border (grips mode); `--frame-outline` forces it.

\* \*\*Welcome overlay / dialogs:\*\* unchanged; dialogs keep the native frame.



\## 8. Tests



\* \*\*Linux CI + local:\*\* `hit\_test` for every region, corners, minimum-size window, maximized; `resized\_rect` (each edge, minimum size, no negative moves); `shrink\_for\_autohide`; grips exist / hide when maximized / reposition on resize in custom mode, and do not exist with `--native-frame`; native hook is a no-op off Windows; `CaptionButton` native look.

\* \*\*Windows CI (`windows-latest`):\*\* after `show()` the window has the thick-frame styles; sending `WM\_NCHITTEST` at the left edge returns `HTLEFT`, in the bar `HTCAPTION`, on the maximize button `HTMAXBUTTON`, on the close button `HTCLIENT`, and at the left edge while maximized `HTCLIENT`.

\* Existing `tests/test\_qt\_titlebar.py` must keep passing.



\## 9. Windows 11 checklist (owner runs this on `v2.6.1-beta.1`)



| # | Check | Pass when |

|---|---|---|

| 1 | Shadow / edge | The window has a visible shadow and does not look flat against the desktop |

| 2 | Resize | All 8 edges and corners resize, with the right cursor on each; 900 x 560 minimum holds |

| 3 | Maximize / restore | Button and double-click on the bar both toggle; resizing works again after restore |

| 4 | Aero Snap | Drag the bar to the left / right / top edge snaps / maximizes; `Win+Arrow` works |

| 5 | Snap Layouts | Hover the maximize button for about a second: the layouts flyout appears; the button shows hover and pressed; clicking toggles maximize |

| 6 | System menu | Right-click on the bar and `Alt+Space` open the menu; Restore / Move / Size / Close work |

| 7 | Bar buttons | Minimize and Close click normally and show hover; Close asks about a running job as before |

| 8 | Maximized fit | No part of the window is cut off by the screen edge; the status bar is fully visible |

| 9 | Auto-hide taskbar | With auto-hide on, a maximized window still lets the taskbar pop up from its edge |

| 10 | Scaling | Repeat 2, 3 and 5 at 125% and 150% |

| 11 | Two monitors | Drag between monitors with different scaling; resize and the maximize button still hit correctly |

| 12 | Welcome overlay | Press F2: the window can still be moved and the bar buttons work |

| 13 | Recovery | `LuckyTwitch.exe --native-frame` shows the OS title bar; `--grips-only` shows the custom bar with grips |



If something fails: note the number, what you saw, and whether `--grips-only` behaves; also run `python tools/frameless\_spike.py` and say whether the same thing happens there.



\## 10. Risks



| Risk | Mitigation |

|---|---|

| Win32 code cannot be run on the developer side | Pure / glue split, Windows CI end-to-end tests, beta builds, the spike tool |

| Mixed-DPI hit-test coordinates | Convert with `ScreenToClient` and the window's own device pixel ratio; checklist 10 and 11 |

| Qt resets the window style on a state change | Styles are applied once per native window handle after `show`; checklist 3 and 4 |

| Snap Layouts hover / click handling | Follows `WM\_NC\*` for that one rectangle; if it cannot be made clean, ship without the flyout rather than without shadow and snap |

| DWM frame extension shows a thin line on some systems | One constant (`DWM\_SHADOW\_MARGIN`) in `frameless.py`; `--grips-only` as escape hatch |



\## 11. How to resume this work



1\. Read section 6 for the phase and section 9 for what the owner reported.

2\. Everything lives in `qt\_ui/frameless.py` plus the small hooks in `main\_window.py` and `titlebar.py`. Nothing in `core/` changes.

3\. Deliver as a zip of only the changed files, plus the commands to run the tests (rule from `HANDOFF.md`).

4\. When the checklist passes: do W6, set the status line at the top to \*\*Done in v2.6.1\*\*, and update `docs/README.md` and `NEW\_WINDOW\_BAR.md`.

