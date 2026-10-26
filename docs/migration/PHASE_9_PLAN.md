# Phase 9 plan: UI redesign beyond parity

**Status: PLAN ONLY. No code has been written and none should be until the user has answered section 9 (decisions) and approved a first version.**

Written 2026-10-26, after Phases 0 to 8 were approved. This file is the detailed plan; PLAN.md section 6 (Phase 9) and HANDOFF.md point here. It replaces decision D7 ("the user provides references") with: *the user asked the agent to propose the redesign and plan it before touching anything.* The user can still bring references; section 9 says where they would change the plan.

How to read it: section 1 is what the running app looks like today (measured, not guessed). Section 2 and 3 are the rules and the technical limits. Section 4 is the list of ideas, each with what, why, how, risk and a priority (**M** must, **S** should, **C** could). Section 5 is what I would NOT do and why. Section 6 splits the work into versions. Sections 7 to 10 are tests, decisions, risks and files.

---

## 1. What the app looks like today (evidence)

Rendered offscreen from the uploaded zip (Qt 6.12.0, DejaVu fonts, so fonts differ from Windows) at 1020x910 and at the minimum size 900x560, every tab, two Options sections, and the Plan tab with a sample VOD. Numbers below are read from those renders and from the code.

**Layout and space**
- At 900x560 the page content is only about **405 px tall (72% of the window)**. The rest is chrome: the VOD bar plus info line (about 100 px with the tab bar) and the progress bar plus status line (about 55 px).
- The progress bar is a full-width 18 px empty bar on every tab, all the time, even when nothing runs. It is the heaviest piece of chrome for the least information.
- The info line under the VOD bar ("Streamer · Big Stream · 2:00:00 · 2 clips") is 10 pt muted text. The most important fact in the app (which VOD is loaded) is its quietest element.
- **Plan tab at 900x560:** the timeline card fills the view; "Cut points" is barely visible; the "Clips → chapters" card needs scrolling. The three things that belong together (timeline, cut text, parts) are stacked in one scroll column.
- **Options tab:** a good sidebar, but "Output" holds two rows and leaves the bottom 60% of the window empty, while rows stretch to the full width on wide windows (long distance between a setting's name and its control).
- **Search tab:** the left column (Results and Recent streamers, about 240 px wide) is mostly empty text most of the time; the VOD table is the real content and gets the rest.
- **Queue tab:** a table with five text columns. Running progress is not in the row, it is in the global bar at the bottom. The log is always open and takes half of the page even when empty.

**Visual language**
- Text-only buttons and labels: **no icons anywhere** (arrows, dots and quotes are Unicode characters).
- Rectangles with zero radius, borders of 1.16 to 1.38 contrast against the surfaces (see below). It reads as "dark and flat" but not as a designed system: there is no spacing scale (values like 2, 4, 6, 7, 8, 10, 12, 14, 16, 20 are all in use), and sizes 9, 10, 11 and 15 pt are mixed ad hoc.
- Buttons draw **no keyboard focus ring** (an inherited tkinter choice, HANDOFF.md warnings). A keyboard user cannot see where the focus is on a button.
- Contrast, computed from `core/palette.py` (WCAG ratios):

| Pair | Ratio | Verdict |
| --- | --- | --- |
| MUTED on BG / BG2 / BG3 | 6.07 / 5.08 / **4.06** | hints on BG3 buttons and headers fall under 4.5 |
| White on ACCENT (button text) | 4.64 | passes, just |
| ACCENT as text on BG2 (group titles, sign-in code) | **2.97** | fails; needs a lighter accent-text token |
| DISABLED on BG / BG2 / BG3 | 3.33 / 2.78 / **2.23** | exempt from WCAG, but hard to read on BG3 |
| BORDER on BG2 / BG (hairlines) | **1.16** / 1.38 | card edges are almost invisible; input borders fail the 3:1 rule for UI boundaries |
| FG on BG2 | 11.05 | fine |

**Behaviour that is already good and must not regress:** Get info loads from anywhere (Enter, link, "Use this VOD"); the Timeline and the cut text always match; queue never starts by itself from a link; closing while a job runs asks first; the Options "Advanced" areas still apply when collapsed; all 38 settings keys.

---

## 2. Principles and guardrails (the rules for the whole phase)

1. **Parity tests stay green.** The 450 or so `tests/test_qt_*.py` tests are the contract. When a redesign makes a test wrong (a moved widget, a renamed text), the test is updated in the same version and listed in PHASE_NOTES.md under "tests changed on purpose". A test is never deleted to make a version pass.
2. **Every deliberate difference goes in MIGRATION_LOG.md**, numbered from **20**, with the usual three lines (tkinter / Qt / Why). Behaviour changes are separated from looks: a purely visual change gets one grouped entry per version; a behaviour change (right-click menu, new shortcut, toasts instead of message boxes) gets its own.
3. **Settings JSON keys stay identical and none is added** (section 4, B9 explains where new UI state goes: a separate file).
4. **Do not touch** `luckytwitch_engine.py`, `weblink.py`, the Premiere plugins. If an idea needs engine data that is not there (marked "needs engine" below) it becomes a report to the user, not a change.
5. **Versions, not a batch** (HANDOFF.md section 4): `phase-9-<letter>-v1`, each one runnable and looked at by the user on Windows before the next. No tag until the whole phase is approved. Each version updates HANDOFF.md, PHASE_NOTES.md, VERSIONS.md.
6. **Looks first, layout second, features last.** The order of the versions in section 6 follows this: a new design system underneath, then the shell around the tabs, then one tab at a time. New features (the ones that are not just a better way to do an existing thing) are tagged **[new feature]** and each needs the user's yes.
7. **Offscreen-testable.** Anything that animates must also have a state the tests can read without waiting (a property with the end value), and a way to switch animations off (tests, and users who want it, see B6/A6).

---

## 3. Technical facts that shape the plan

- **QtSvg is excluded from the build** (Phase 8 excluded `PySide6.QtSvg*` to save size). Any icon set made of SVG files is therefore not available as it is. Three ways out, decided in version 9a: (a) draw the 25 to 30 icons in code with `QPainterPath` (no files, no plugin, crisp at every DPI, themeable, about 400 lines); (b) bundle pre-rasterised PNGs at 1x/2x/3x (more files, blurry at fractional DPI); (c) stop excluding QtSvg and ship its plugins (a few hundred KB, then any SVG set with a permissive licence works). My recommendation is (a); see A5.
- **QSS cannot animate, blur, glow or round everything.** There are no `transition`s. `border-radius` works on frames, buttons and inputs, but not on `QTabBar::tab` corners reliably, and not with anti-aliasing on every platform. There is no backdrop blur at all (Qt has no portable API), and `QGraphicsDropShadowEffect` is slow and clashes with custom painting. So: animation means `QVariantAnimation` driving a property of a custom-painted widget (the `Toggle` already does this), and "glow" means a 1 px accent ring, not a shadow.
- **The window can be 900x560.** Anything that costs width (a sidebar) or height (a bigger header) has to prove itself at that size, not at 1020x910.
- **Tests are coupled to structure.** `win.tabs` is used 28 times in the tests (`currentWidget` 9, `setCurrentWidget` 7, `widget`, `currentIndex`, `tabText`, `tabBar`, `setCurrentIndex`). If the tab bar is replaced by a rail, a small `PageStack` class exposes the same methods so those 28 uses keep working. `qt_ui/dialogs.py` has about 30 call sites that tests replace; the toast service (B5) goes next to it with the same seam.
- **Fonts differ by OS** (Segoe UI, Helvetica Neue, DejaVu). All sizes in points from a scale, nothing in pixels, so DPI 100% to 200% behave. 
- **Packaging budget:** icons drawn in code and animation code add no dependency; a bundled font (C, see A3) adds about 300 to 700 KB.

---

## 4. The ideas

Tier: **M** = I would do it, **S** = worth doing, **C** = optional. "Risk" is risk to parity and schedule, not to taste.

### A. Design system (the base everything else sits on)

**A1. Tokens for space, radius, type and elevation. (M)**
*What:* one place (`core/palette.py` for colours, a new `qt_ui/tokens.py` for the rest) with named steps: space 4/8/12/16/24/32; radius 4 (inputs, chips), 6 (buttons), 8 (cards), 999 (pills, toggles); type scale 9 (caption), 10 (body), 11 (row title), 13 (section), 16 (page title) pt; three surface levels (BG base, BG2 raised, BG3 control) plus one overlay level for menus, toasts and tooltips.
*Why:* today's inconsistency is the main reason the app feels "assembled" rather than designed. Qt makes this cheap because the QSS is already generated from tokens (`build_qss()`); we extend the template, not rewrite it.
*How:* QSS gets `${R_CARD}`, `${S_2}` and so on; widgets that lay out in code import the same constants. A test fails if the QSS contains a spacing or font size that is not on the scale.
*Risk:* low. Sizes change a few pixels everywhere, so baseline screenshots change; no behaviour changes.

**A2. Surfaces, borders and focus: a visible, consistent edge. (M)**
*What:* cards get radius 8, a 1 px border that is actually visible (new `BORDER_STRONG` about 1.6:1 on BG2) and no fill change on hover; inputs get a border that reaches 3:1 against their surface (new `FIELD_BORDER`) and an accent ring on focus; a **focus ring for buttons, toggles, nav items and table rows** (2 px, `ACCENT_HOVER`, drawn so it does not move the layout). Selected rows use `ACCENT_DIM` with a 3 px accent bar on the left instead of a solid purple fill (solid purple rows with white text are loud and tire the eye in long lists).
*Why:* section 1 measured the borders at 1.16:1 and the focus is invisible on buttons. This is the single most useful accessibility fix and costs little.
*Risk:* low. Must re-check Tab order tests (`test_gui_final_pass` ports) because focus rings can change size hints.

**A3. Type hierarchy. (S, with an optional C)**
*What:* page title 16 pt bold, section 13 pt semibold, row title 11 pt semibold, body 10 pt, hint 9 pt muted (never below 4.5:1), monospace only for times, paths and the log. Numbers in tables and the timeline use tabular figures where the font has them, so columns of durations line up.
*(C)* Bundle one UI font (Inter, SIL OFL) so Windows, macOS and Linux look alike. About 300 to 700 KB for two weights. Not needed: Segoe UI and Helvetica Neue are fine. Ask the user (D11).

**A4. Contrast repair, enforced by a test. (M)**
*What:* raise MUTED a few points so it passes 4.5:1 on BG3 (it is 4.06 today); add `ACCENT_TEXT` (a lighter tint, about 4.5:1 on BG2) for accent-coloured text; keep DISABLED visibly dimmer but not below about 3:1 on BG and BG2. A pure-Python test (`tests/test_qt_contrast.py`, no Qt) computes the ratios of every text/surface pair the QSS uses and fails under 4.5 (text) or 3 (UI boundaries); disabled is exempt but must stay above a floor.
*Why:* it turns a taste argument into a number, and it stops later phases from regressing it.

**A5. Icons. (M)**
*What:* a small icon layer, `qt_ui/icons.py`, `icon(name, size, colour)`, drawn with `QPainterPath` at any DPI and colour (so hover/disabled/accent colours are free). The set I would draw: search, film/vod, scissors, list/queue, gear, play, pause/stop, plus, minus, fit, undo, redo, folder, folder-open, copy, trash, check, x, alert, info, chevron-right/down, external-link, refresh, user, link, download, clock, eye (views), flag (clip), grid, list-view, filter, sliders.
*Where they go:* nav rail (B1), buttons that act on something (Add to queue gets a plus; Open folder a folder; Copy log a copy), status chips in the queue, empty states (a 48 px outline icon instead of just text), toasts, the timeline toolbar.
*Rule:* an icon never replaces the text on a primary action; icon-only buttons (zoom, undo) always have a tooltip and an accessible name.
*Why QPainterPath and not a set of SVGs:* QtSvg is excluded (section 3); drawing in code needs no plugin, and the shapes can animate (a chevron that rotates when a section opens).
*Risk:* medium effort (a day of drawing and a gallery to check them), low risk. Needs a gallery section in `tools/widget_gallery.py`.

**A6. Motion, small and optional. (S)**
*What, in this order of value:* (1) hover and press fades on buttons and nav items (120 ms ease-out); (2) the Advanced/Collapsible areas slide open (180 ms) instead of popping; (3) the nav selection indicator slides between items (150 ms); (4) the progress value eases to its new value instead of jumping; (5) toasts slide and fade (B5); (6) skeleton shimmer while thumbnails load (C3, E9).
*How:* a `Motion` helper holding the durations and one `enabled()` switch. Animated widgets paint themselves from an animated property (like `Toggle`). Reduced motion: honour Windows' "show animations" system setting (a `ctypes` call, same style as the DWM call) and a user switch in Options > Tools [new feature, stored in the UI-state file, B9]; tests turn it off in `conftest.py`.
*Risk:* medium on schedule (hover fades on a QSS-styled `QPushButton` means moving its painting into a subclass; spike in 9a before committing). Zero on parity if disabled.

### B. The shell (window frame, navigation, status)

**B1. Navigation: a left rail instead of the top tab bar. (M, but see the trade-off)**
*What:* a 56 px icon rail on the left (Search, Plan, Queue with a count badge; Settings at the bottom), expandable to about 176 px with labels, state remembered. The selected item has a left accent bar and `ACCENT_DIM` fill. The rail shows live state: the Queue icon has a badge with the number of waiting jobs and a spinner ring while one runs; Plan shows a dot when there is a VOD loaded and unsaved cut changes... only if that state exists (checked in 9b), otherwise just "VOD loaded".
*Why it is better here, not only fashionable:* the workflow is linear (find a VOD → cut it → queue it → watch it), and the rail can express it: items are ordered by it, Plan is visibly "empty" until a VOD is loaded, Queue shows progress from any page. It also frees height: the tab bar (about 40 px) goes away.
*The trade-off I want you to decide (D8):* a rail costs 56 px of width at 900 px (6%), and Options already has its own sidebar, so Settings would show a rail next to a sidebar. Three ways: **(a) rail + Options keeps its inner sidebar** (simplest, two narrow columns; acceptable at 56 px collapsed); **(b) the rail expands to show the Options sections under Settings** (one navigation tree, no double sidebar, more code); **(c) keep top tabs** and spend the effort elsewhere. My recommendation is (a), with (b) as a later refinement.
*Test impact:* `PageStack` shim (section 3) keeps all 28 `win.tabs` uses working; `TAB_NAMES` and `tab_names()` stay.
*Risk:* medium (focus order, keyboard `Ctrl+1..4`, the "starts on Plan when not signed in" rule must survive).

**B2. A command bar instead of "label + entry + two buttons". (M)**
*What:* one rounded field with a link icon, placeholder "Paste a Twitch VOD link or ID", an inline paste-and-clear button, and **Get info** as the accent button attached to its right. While loading, the field shows a thin animated bar under it and the button shows a spinner (replaces the "Loading..." dots animation; same states, `set_info_busy` keeps its meaning). Enter still loads.
*Why:* the bar is the front door and it is the same tiny label-and-box it was in 2018.
*Also:* **drag a link or text into the window** loads it (`dragEnterEvent`), and when the app gains focus with a Twitch VOD link on the clipboard and the field is empty, a non-modal toast offers "Load this VOD?" **[new feature]**. Both are off the critical path and easy to turn off.
*Risk:* low. Tests that look for `vod_entry`, `info_btn` keep those attribute names.

**B3. The current VOD gets a face: the VOD strip. (M)**
*What:* under the command bar, only when a VOD is loaded, a 44 px strip: 16:9 thumbnail (the first storyboard frame, else a placeholder; checked in 9b), title, `streamer · date · duration · N clips · muted 1:54`, and two small buttons (Open on Twitch, Clear). Replaces the muted info line, which still exists as accessible text for tests (`info_label`). Click it to jump to Plan.
*Why:* "what am I working on" is always on screen, on every page, with a picture; it also tells you instantly that you loaded the wrong VOD.
*Risk:* low. Height cost 44 px only when loaded; hidden when not.

**B4. Twitch account chip instead of the "Twitch API…" button. (S)**
*What:* a chip at the right end of the command bar: "Sign in" (accent outline) when not signed in, "● Signed in" when signed in (and the login name if the client exposes it; checked in 9b, otherwise no name), opening the same dialog. The own-app Client ID/Secret stays in the dialog's advanced part.
*Why:* it shows state, the button does not. Today you cannot tell if you are signed in without going to the Search tab.
*Risk:* low. Needs a cheap `signed_in` signal from `MainWindow` (the data is there).

**B5. Toasts instead of message boxes for good news. (M)**
*What:* a `Toast` overlay (bottom right, stacked, auto-dismiss in 4 s, pause on hover, optional action link such as "Open folder" or "Undo") reached through a new `notify(level, text, action=None)` in `qt_ui/dialogs.py`'s neighbour `qt_ui/notify.py`. Moved to toasts: "Added to queue", "Log copied", "Tools updated", "Chat overlay done", "Link loaded", "Clip downloads queued". **Stay modal dialogs:** errors that need a decision or a reading (job failed with details, invalid cut points, sign-in errors), "close while a job runs?", and anything that asks yes/no.
*Why:* `dialogs.info` has about 14 call sites, most of which interrupt the user to say "done". A toast says it and gets out of the way. The seam stays: tests replace `notify` like they replace `dialogs`.
*Migration log:* its own entry (behaviour change: no click needed).
*Risk:* medium (overlay positioning on resize, stacking, focus not stolen).

**B6. Tell me when it is done: system notification and tray hint. (S) [new feature]**
*What:* when the queue finishes or a job fails while the window is not the active one, a system notification ("3 of 3 jobs finished · Open folder") via `QSystemTrayIcon.showMessage`, and the taskbar icon flashes once (`QApplication.alert`). No tray icon residing permanently; the `QSystemTrayIcon` is created only for the message. A Windows taskbar *progress* overlay needs `ITaskbarList3` through `ctypes` and is a stretch (C).
*Why:* these downloads take a long time; people tab away. It is the most "native app" thing missing, and it needs no new dependency.

**B7. Status bar that earns its place. (M)**
*What:* replace the 18 px bar + line with one 28 px status bar: left, the status text; right, a compact activity pill when something runs (`Job 2/5 · 43% · 12 MB/s · 4 min left`, click goes to Queue); the progress itself is a 3 px line along the top edge of the status bar (accent when running, indeterminate shimmer when busy, hidden when idle). The big bar returns inside the Queue page (F2) where it belongs.
*Why:* −26 px of chrome on every page and the information moves next to where the person looks.
*Needs engine?* Speed/ETA text comes from the progress text the engine already sends (`Bridge.progress(frac, text)`); 9b checks what the text contains and shows only what is there, nothing invented.
*Risk:* low-medium: tests read `win.progress` and the status label; both keep their names (the progress object can still be a `QProgressBar` styled as the line).

**B8. Keyboard layer. (S)**
*What:* `Ctrl+L` focuses the command bar; `Ctrl+1/2/3/4` go to Search/Plan/Queue/Settings (`Cmd` on macOS); `Ctrl+Enter` on Plan = Add & start, `Ctrl+Shift+Enter` = Add to queue; `Ctrl+,` opens Settings; `F1` or `?` shows a shortcut sheet (a small dialog). Every shortcut is also visible in the tooltip of its button. The timeline's own keys are in E2.
*Why:* the app is a tool people use repeatedly; shortcuts are what separates "uses" from "likes".

**B9. The window remembers itself. (S) [new feature]**
*What:* last window size and position (clamped to the available screens), last page, rail expanded or not, Plan splitter sizes, log drawer open or not.
*Where it is stored:* **not in `luckytwitch_settings.json`** (its 38 keys stay identical, so a downgrade or the old app is never confused) but in a new `luckytwitch_ui.json` next to it, a path in `core.paths` like the others, read tolerantly, deletable without loss.

**B10. First run and empty states that teach. (S)**
*What:* with no VOD loaded, the Plan page shows a three-step card ("1 Paste a link or search a streamer · 2 Mark where to cut · 3 Add to queue") with the two real buttons (Search, Paste from clipboard) instead of an empty timeline card; each empty state gets an outline icon, a one-line explanation and at most one action. Not a wizard, not a tour, nothing modal.

### C. Search page

**C1. Recent streamers become a chip row. (S)** The left column goes away when there are no results; "Recent" is a horizontal row of chips under the search box (name, live dot, ✕ on hover), scrolling sideways when long. At 900 px this gives the VOD list **about 240 px more width**. When results exist, they appear as a popover list under the box (like a search suggestion), not as a permanent column. Keeps: generation counter, cap of 12, "Clear recent", live marker, keyboard Up/Down/Enter (all in `test_qt_search_tab.py`).

**C2. List and grid views of VODs. (S)** A segmented toggle (list/grid). Grid: 16:9 thumbnail cards (about 220 px) with the title on two lines and `date · length · views` below, a duration badge over the thumbnail, and a hover lift. List stays the default and the tested one (the model is the same, `QListView` in `IconMode` with a different delegate, so D5 holds). Thumbnail cache cap stays 300, sized per mode.

**C3. Skeleton loading. (C)** Rows/cards appear as grey placeholders with a slow shimmer while the page loads and while thumbnails arrive, instead of an empty table with a message.

**C4. Find within the loaded list. (S) [new feature]** A "Filter titles" box over the VOD list (client-side substring, no request), so a streamer with 300 VODs can be searched. Plus **infinite scroll** option for "Load more" (loads when the list end is reached; the button stays for keyboard users).

**C5. LIVE as a badge. (S)** The `●` becomes a small red LIVE pill; live channels sort first in results as now.

### D. Plan page (the heart of the app)

**D1. A layout built for the job: pinned timeline + split workspace. (M)**
*What:* the timeline is no longer a card in a scrolling column. The page becomes a `QSplitter`: **top** the timeline (its height is the user's, remembered, default about 220 px), **below** two columns that adapt: *Cut points + parts* on the left, *Clips → chapters* on the right (at widths ≥ 1000 px); under 1000 px they become two sub-tabs ("Cuts" / "Clips"), because side by side at 900 px both would be too narrow. The footer (parts summary, Add to queue, Add & start) stays fixed as today.
*Why:* this answers the measured problem (section 1): at 900x560 you currently see the timeline and nothing else. The relationship between the three is the point of the page; they should be seen together.
*Risk:* **the highest of the layout changes** (the Plan tests are 55 and use `ScrollPage` and the footer). It is why Plan comes after Queue and Search and gets its own version, with a "classic layout" fallback kept until approved.

**D2. Parts as cards, text kept as the source of truth. (M)**
*What:* below the cut text, the live preview becomes a row of **part cards**: `Part 2 · 0:30:00 → 1:30:00 · 1:00:00`, with a game-colour stripe (same colour the timeline uses for that stretch, when known), a skip toggle (same as clicking the part on the timeline), and muted time if any. Errors stay as the red line they are now. The text box stays the single source of truth: cards are generated from the same `make_plan` result, and `preview_text()` / `preview_kind` (used by tests) keep returning what they return today.
*Why:* a list of text lines is the least scannable way to read a plan.

**D3. Strategy and coverage made visible. (S)** The line "→ download the full VOD once, then split it (parts cover 100% of the VOD)" becomes a two-segment bar (covered / not covered) with the strategy as a chip ("Full download, then split" / "Sections only") and one sentence on why. The data is already computed (`choose_strategy` returns strategy and coverage, `make_plan` keeps it); no engine change. Strategy and threshold remain Options > Cuts; the chip links there.

**D4. The footer says what will happen. (S)** `3 parts · 2:00:00 in total · full download first` instead of just the count and duration, and a disabled-state explanation (why "Add to queue" is grey: "No VOD loaded" / "Fix the cut points"), as a tooltip and as the line.

**D5. Clips → chapters card. (S)** The switch and its filter fields stay; the filter fields become one compact row with labels above; the table gets the same row style as everywhere else with a view-count bar behind the number (a thin proportional bar, so the most-viewed clips stand out); "Split at clip" and "Open clip" become row buttons on hover plus the current buttons. Empty state: when there are no clips, one line, not a card full of controls.

**D6. Command palette for cuts? (C)** A small input to type `1:30:00` and press Enter to cut at that time, next to the timeline toolbar (today you must type into the text box). Optional because the text box already does it.

### E. Timeline (polish, not a rewrite; `qt_ui/timeline.py` 836 lines, 62 tests)

**E1. Parts as rounded pills, skipped parts hatched. (M)** Part bars get rounded ends, a label that fits (`P1 · 2:00:00`, shortened when narrow), a clear lift on hover, and skipped parts are drawn with diagonal hatching rather than only dimmed (hatching reads as "excluded" even for colour-blind users).

**E2. Keyboard editing. (M) [new feature, small]** Hover or click the strip, then: `S` cut at the hover time, `Delete` removes the nearest cut, `←/→` nudges the selected cut by 1 s (`Shift` 10 s, `Alt` 0.1 s), `Home/End` jump to the start/end, `+/-` zoom, `0` fit, `Ctrl+Shift+Z` or `Ctrl+Y` **redo** (the 100-step undo exists; redo is new). The existing mouse behaviours do not change.

**E3. Overview strip when zoomed in. (S)** A 10 px minimap of the whole VOD (game colours, cut marks) with the current window as a draggable handle, replacing the plain horizontal scrollbar when zoomed. Plain scrollbar remains for tests/keyboard.

**E4. Games as a legend. (S)** A row of colour chips under the strip, one per game, ordered by time spent, with the hours (`Just Chatting 3:10`). Click = isolate that game as its own part (the same as the double-click, now discoverable); hover highlights it on the strip. Currently the colours mean nothing until you hover.

**E5. Clips as flags, clustered when crowded. (S)** The green ▼ marks become small flags with a tooltip (title, creator, views); when zoomed out and they overlap, they merge into a counter badge (`12`), which expands on zoom. Requires touching only paint code.

**E6. Toolbar with icons and a zoom readout. (S)** `−  +  Fit  Undo Redo` become icon buttons with tooltips and shortcuts, plus a zoom percentage or visible span (`Showing 0:42:10`), and "Show muted" keeps its switch.

**E7. Right-click menu and a calmer hint line. (S) [behaviour change, logged]** Right-click on empty timeline opens a menu: *Cut here · Skip this part · Isolate this game · Split at nearest clip · Zoom to this part · Undo*. Right-click **on a cut line keeps removing it** (parity). The long hint line ("Click the thumbnails to cut · click a part to skip it · …") is replaced by a "?" that opens the same text in a popover and by showing the hint once, then remembering (B9).

**E8. Snap feedback. (S)** When a cut snaps (6 px to a game change, clip or muted edge), a thin guide line and a small label (`snaps to: Game change`) show while dragging, so the magnet is understood, not mysterious.

**E9. States: loading and no thumbnails. (S)** Thumbnails loading: shimmer. No storyboard ("This VOD has no preview thumbnails", as in the render): a neutral striped placeholder with the game colours still visible, so the strip never looks broken.

### F. Queue page

**F1. Rich rows. (M)** Keep `QueueModel` (D5) and the table API; replace the plain cells with a **delegate**: thumbnail (when known), title + `n parts · strategy`, a status chip with icon and colour (queued grey, running purple with spinner, done green check, failed red, cancelled amber), and for the running row a **progress bar inside the row** with percent and the text the engine sends (ETA/speed if present, checked in 9c). Finished rows show an "Open folder" icon button (the files are in `QueueItem.files`).
*Why:* now the progress for a job lives at the bottom of the window, away from the job.

**F2. A header that summarises. (S)** `2 done · 1 running · 3 waiting · 1 failed`, and the main buttons as one group (Start / Pause?—see below / Cancel) with icons; "Remove selected" and "Clear finished" move to a secondary group. The global progress bar returns here in a bigger form (the status bar B7 shows the compact form).

**F3. Log as a drawer with filters. (S)** The log is collapsed by default to one line (the last message, colour-coded) and opens as a drawer; when open: filter chips (All / Warnings / Errors), search box, "Pause autoscroll" toggle, Copy, Clear, **Save…** [new feature, writes the visible log to a file]. When a job fails, the drawer opens by itself on the first error. Colour coding and autoscroll behaviour of today stay.

**F4. Reorder and retry. (S) [new feature]** Drag a waiting row to reorder; "Retry" on a failed or cancelled row re-queues the same job at the end (today you rebuild it in Plan). Reordering needs `QueueRunner` to read order at start of each job (it iterates items; check in 9c); if that needs a runner change it is small and in `qt_ui`, not the engine.

**F5. Pause (C, probably no).** A true pause means pausing ffmpeg/yt-dlp; the engine's contract is cancel-and-resume-later ("cancelling keeps the partial download"). I would not add Pause; "Cancel current" already resumes later. Listed so the question is answered.

### G. Options page

**G1. Settings search. (M) [new feature]** A search box at the top of Options ("Search settings…"): typing filters rows across all seven sections by name, hint and the info tooltip text, shows results grouped by section, Enter jumps to the row and flashes it. With 33 settings in 7 sections this is the fastest improvement for finding things.

**G2. "Changed from default" markers and per-row reset. (S)** A small accent dot on a row whose value differs from `DEFAULTS` (and a count in the sidebar: `Chat 3`), and a "Reset" ghost button on hover that writes the default. No setting is added; this reads `DEFAULTS` and the current value.

**G3. The result is always visible. (M)** In Output, a "Files will be saved as" card above the fold: the full resulting path built with the engine's own naming (the `core.examples` code that already exists), e.g. `D:\Twitch\2026-10-01 - Big Stream - v123\Streamer - 2026-10-01 - v123 - part1.mp4`, with an Open-folder button and a free-space/writable check (`shutil.disk_usage`, `os.access`; red text if the folder is not writable). Today the example lines are inside the collapsed Advanced area, so the user must open it to see the effect of the setting.

**G4. Layout: a readable width. (S)** Content column capped at about 760 px and centred in the page so a name and its control are never 900 px apart; the left side nav stays; section header shows icon + title + one-line description (as now) and the sections that have more than six rows get a "jump to" mini-list. The empty lower half of short sections is fine (it is a settings page), but a short "Tips" line can use it where useful.

**G5. Tools section with real status. (S)** yt-dlp and ffmpeg shown as two rows each with a status dot, version/date if the existing `describe_tools()` provides it, and the two actions ("Update now", "Open tools folder") as row buttons.

**G6. Setting profiles. (C) [new feature, own decision]** "Save these settings as a preset / load a preset" (e.g. "Premiere editing", "Quick archive"). Needs a presets file and rules for which keys. I list it because it is the obvious next step once G1/G2 exist, but it is a feature, not a redesign; D12.

### H. Dialogs and messages

**H1. One look for every dialog. (S)** The Twitch sign-in dialog gets the stepper look (1 Get code → 2 Authorise in browser → 3 Done) with the code in a large copyable chip and a "Copy code" button; error and confirm boxes use one themed `ConfirmDialog`/`ErrorDialog` (accent button for the safe action, red for the destructive), still reached through `qt_ui/dialogs.py` so tests keep replacing the functions.
**H2. Error messages that say what to do. (S)** An error dialog has a one-line summary, a "Details" fold with the raw text and a "Copy details" button; the content of the messages does not change in this phase, only the container.

### I. Accessibility, DPI, platform

**I1. Keyboard and focus audit** (A2 and B8 deliver it; this item is the check): every control reachable and visible, tab order tests extended to the rail and the splitter.
**I2. Screen-reader names.** `setAccessibleName`/`Description` on icon-only buttons, the rail items, toast text (live region), the timeline canvas (a text summary of parts and cuts). Windows Narrator and macOS VoiceOver spot check by the user.
**I3. DPI.** Check at 100/125/150/200% on Windows and Retina on macOS: icons crisp, no clipped text, the timeline `devicePixelRatio` (already handled in 7b) still right.
**I4. Text size.** A check that the layout survives a user raising the Windows text size by 125% (the QSS uses pt; layouts must not use fixed heights on text rows).

---

## 5. What I would not do, and why

- **A frameless window with a custom title bar.** It looks modern in screenshots and costs a lot: resize borders, snap layouts, DPI edge cases, macOS traffic lights, double-click-to-maximise, accessibility. The native dark title bar is already done (DWM + Qt colour scheme). Not worth it.
- **A video player in the timeline area (NLE style).** The app has nothing to play: a VOD is a remote HLS stream and the app never downloads before the cut is decided; the preview today is storyboard thumbnails. A player means a media backend (`QtMultimedia` is excluded and large) and either streaming a full VOD or downloading it first, which is the opposite of what the "sections only" strategy saves. I would instead improve the hover preview (a larger frame on hover and arrow-key scrubbing through thumbnails). If you ever want playback it is its own project.
- **Glass, blur, glowing accents.** No portable backdrop blur in Qt; fake glass over a flat dark UI looks muddy and costs paint time; `QGraphicsDropShadowEffect` glows are slow. Layered flat surfaces and a 1 px accent ring get 90% of the look at no cost.
- **Rewriting in QML/Qt Quick.** Qt Quick is excluded from the build, it would mean throwing away 5,500 lines of tested widgets and 450 tests, and gives nothing the plan above needs.
- **A web view or a different toolkit.** Same reason, plus size.
- **A light theme now.** The token structure (A1) makes it possible later; designing and testing a second theme doubles every screenshot and contrast check. Out of scope unless you ask.
- **Toasts for errors.** An error that needs reading or a decision stays modal.
- **Pause in the queue** (F5).
- **Changing what any option means**, renaming settings, or touching the engine.

---

## 6. Work breakdown (versions)

Each line is a semi-phase delivered as `phase-9-<letter>-v1.zip` (then `-v2`, … for fixes). Sizes S/M/L/XL as in PLAN.md. Order matters: foundation under everything, the shell next (everything sits in it), then pages from least to most risky, polish last.

| Ver. | Name | Contents | Size | Done when |
| --- | --- | --- | --- | --- |
| **9a** | Design foundation | A1 tokens + QSS refactor, A2 surfaces/focus ring, A4 contrast tokens + `test_qt_contrast.py`, A5 icons drawn in code + gallery, spike for A6 (button hover fade) and decision on the button painting approach, B9 UI-state file (reader/writer only), `tools/qt_screenshots.py` (the baseline screenshots of the current Qt app, all pages, both sizes; the tkinter baseline in `baseline/linux-xvfb/` is old) | M | No layout change; every old test green; contrast test green; gallery shows icons; before/after screenshots |
| **9b** | Shell | B1 rail + `PageStack` shim, B2 command bar (+ drag-drop, clipboard offer), B3 VOD strip, B4 account chip, B5 toasts + `notify`, B7 status bar, B8 shortcuts, B9 geometry restore, B10 empty-state card on Plan | L | The four pages live inside the new shell; 28 `win.tabs` uses pass through the shim; keyboard tab order test covers the rail |
| **9c** | Queue | F1 rich rows (delegate), F2 header, F3 log drawer, F4 reorder + retry, B6 system notification on finish | M | Queue tests green (48) + new ones; a real short job checked by the user |
| **9d** | Search | C1 chips + popover results, C2 list/grid, C4 filter + infinite scroll, C5 LIVE badge, C3 skeleton | M | Search tests green (70) + new ones |
| **9e** | Plan layout | D1 splitter and responsive columns, D2 part cards, D3 strategy bar, D4 footer text, D5 clips card, D6 | L | Plan tests green (55) at 900x560 and 1020x910; "classic layout" fallback removed only after the user's OK |
| **9f** | Timeline | E1 to E9 | L | Timeline tests green (62) + keyboard/redo/snap/legend tests; manual session on a long real VOD |
| **9g** | Options | G1 search, G2 changed markers, G3 result card + disk check, G4 width, G5 tools rows | M | Options tests green (57); golden test (`test_core_matches_tkinter.py`) untouched and green |
| **9h** | Dialogs, motion, accessibility, release | H1, H2, A6 motion rollout, I1 to I4, screenshots of every page at both sizes and 125%/150% DPI, `RELEASE_NOTES_QT.md` entry, **beta pre-release tag** | M | User's Windows checks pass; screenshots in `docs/migration/phase9/` |

Rough effort, in the usual unit of one agent session per version: 9a 1 to 2, 9b 2 to 3, 9c 1, 9d 1, 9e 2, 9f 2 to 3, 9g 1, 9h 1 to 2. About **11 to 16 sessions** end to end, and the app is releasable (as a beta) after any of them.

**What can be dropped without breaking the rest:** 9d (Search) can wait; B6, C3, C4, E3, E5, F4, G2, G5 are independent; 9a and 9b cannot.

**Release question (D14):** do Phase 9 before or after the `v2.0.0` cutover. My recommendation: **ship `v2.0.0` with parity first** (it is what 1.x users were promised, and a bug in the redesign should not delay it), then ship the redesign as `v2.1.0` after betas `v0.9.x-beta.N`. The alternative (one big jump to 2.0.0) is a single disruption for users but harder to debug.

---

## 7. Test strategy

- **No new test depends on pixels of a font.** Looks are tested where it is cheap and stable: contrast ratios from tokens (`test_qt_contrast.py`), "the QSS only uses scale values", geometry relationships (the rail is narrower than N px, the timeline never smaller than M px at 900x560), property end-states of animations, and `grab()` pixel probes for a few key colours (as `test_qt_widgets.py` already does).
- **Layout at both sizes.** A parametrised test opens each page at 1020x910 and 900x560 and asserts: nothing clipped (children inside the page rect), the footer visible, the primary action reachable.
- **Every changed old test** is listed per version in PHASE_NOTES.md ("tests changed on purpose") with the reason; the count of tests never goes down.
- **Animations** run with `Motion.enabled = False` in `conftest.py`; one dedicated test per animated widget turns it on and waits for the end value.
- **Parity tests that must not change at all:** `test_core_matches_tkinter.py`, `test_core_options.py`, `test_core_helpers.py`, the settings round-trip. They test the data, and the data does not change.
- **What the agent runs and what the user runs** follows HANDOFF.md: the agent writes tests and runs only cheap, targeted ones; the user runs the new files first, the touched ones next, the full suite last on Windows, and looks at the screens by eye (checklist per version).
- **Screenshots:** `tools/qt_screenshots.py` (9a) produces the same set before and after each version so the user compares like with like. Offscreen Linux renders are for structure only; Windows screenshots are the user's check.

---

## 8. Risks

| Risk | Why | Mitigation |
| --- | --- | --- |
| Plan page layout (D1) breaks the 55 Plan tests and the fixed-footer behaviour | most coupled page | own version; keep the old layout switchable until approved; port tests with the layout |
| Nav change breaks focus order and `win.tabs` users | 28 uses, tab-order tests | `PageStack` shim; extend the order tests first |
| Custom-painted buttons diverge from QSS-styled ones | two ways to draw a button | spike in 9a and choose one; all variants in the gallery |
| Animations flaky in tests | timers and offscreen | `Motion.enabled`, end-state properties, no sleeps |
| Fonts differ (Windows vs Linux sandbox) so the agent cannot judge spacing | offscreen DejaVu | user checks on Windows each version; sizes from the scale in pt |
| Scope creep: "while we are here" features | many ideas | every **[new feature]** needs a yes (D9); parity tests stay the contract |
| Size/startup | icons, animation, fonts | icons drawn in code, no new dependency; re-run `tools/measure_build.py` in 9h (startup must stay near the 975 ms median) |
| macOS differences (rail, shortcuts `Cmd`, tray messages, title bar) | no Mac in the sandbox | user's Mac check in 9b and 9h; no mac-only code paths without a fallback |

---

## 9. Decisions needed from the user

Recommended answer first. Nothing in 9a needs more than D8 to D10.

- **D8 Navigation.** (a) left rail, Options keeps its inner sidebar; (b) rail with the Options sections folded into it; (c) keep the top tabs. *Recommend (a).*
- **D9 New features.** Which of the **[new feature]** items are in: clipboard/drag-drop (B2), system notification (B6), window memory (B9), filter + infinite scroll (C4), keyboard cutting + redo (E2), right-click menu (E7), settings search (G1), log save (F3), retry + reorder (F4). *Recommend all except G6 (presets) and the taskbar progress overlay, which stay "could".*
- **D10 Icons.** (a) drawn in code, (b) PNG set, (c) re-enable QtSvg. *Recommend (a).*
- **D11 Font.** keep Segoe UI / Helvetica Neue, or bundle Inter. *Recommend keep.*
- **D12 Presets (G6).** later feature or never. *Recommend later.*
- **D13 Motion.** on by default with a switch in Options > Tools and respecting the system setting, or off by default. *Recommend on, with the switch.*
- **D14 Release order.** v2.0.0 with parity first and the redesign as v2.1.0, or one jump. *Recommend parity first.*
- **D15 References.** If you have screenshots or an app whose look you like (not necessarily the ones above), send them before 9a: they change section A (tokens, radius, density) and B1/D1, not the rest.

---

## 10. Files this phase will probably touch

New: `qt_ui/tokens.py`, `qt_ui/icons.py`, `qt_ui/motion.py`, `qt_ui/notify.py`, `qt_ui/shell.py` (rail, `PageStack`, status bar, command bar), `qt_ui/toast.py`, `core/ui_state.py` (the UI-state file), `tools/qt_screenshots.py`, `tests/test_qt_contrast.py`, `tests/test_qt_shell.py`, `tests/test_qt_notify.py`, `tests/test_qt_ui_state.py`, `docs/migration/phase9/` (screenshots).
Changed: `qt_ui/theme.py` (token-driven QSS), `qt_ui/widgets.py` (buttons, cards, collapsible animation, chips), `qt_ui/main_window.py`, the four tab files, `qt_ui/timeline.py`, `qt_ui/twitch_dialog.py`, `qt_ui/dialogs.py`, `core/palette.py`, `core/paths.py` (one path), `tools/widget_gallery.py`, the `test_qt_*.py` files named in the versions, and the docs (HANDOFF, PHASE_NOTES, VERSIONS, MIGRATION_LOG, PARITY for any behaviour box that moves, RELEASE_NOTES_QT).
Not touched: `luckytwitch_engine.py`, `weblink.py`, both `premiere-plugin*` folders, the tkinter app and its tests (until their own removal task).

---

## Appendix: wireframes (structure, not final visuals)

Shell at 1020x910 (rail expanded) and 900x560 (rail collapsed):

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ▣ Search │ ⌕ Paste a Twitch VOD link or ID…        [Paste][Get info] (● Signed in)│
│ ▤ Plan   ├──────────────────────────────────────────────────────────────┤
│ ☰ Queue ②│ [thumb] Big Stream · Streamer · 2026-10-01 · 2:00:00 · 2 clips  ✕ │
│          ├──────────────────────────────────────────────────────────────┤
│          │                                                              │
│          │                    PAGE CONTENT                              │
│          │                                                              │
│ ⚙ Settings│                                                              │
│          ├──────────────────────────────────────────────────────────────┤
│ ‹        │ Ready.                       Job 2/5 · 43% · 12 MB/s · 4 min │
└──────────┴──────────────────────────────────────────────────────────────┘
 chrome above the page: about 52 (command bar) + 44 (VOD strip, only when loaded) + 28 (status) = 80 to 124 px
 today: about 150 px. At 900x560 the page gets about 475 px instead of 405 (+70 px) when no VOD is loaded.
```

Plan page, wide (≥ 1000 px) and narrow:

```
wide                                                    narrow (< 1000 px)
┌────────────────────────────────────────────┐          ┌──────────────────────────────┐
│ Timeline (own height, draggable splitter)  │          │ Timeline                     │
├──────────────────────┬─────────────────────┤          ├──────────────────────────────┤
│ Cut points           │ Clips → chapters    │          │ [Cuts] [Clips]               │
│ [text box]           │ [switch] [filters]  │          │ Cut points + part cards      │
│ ▮P1 ▮P2 ▮P3 (cards)│ [clips table]       │          │                              │
│ ▬▬▬▬▬▬▬ 100% full    │                     │          │                              │
├──────────────────────┴─────────────────────┤          ├──────────────────────────────┤
│ 3 parts · 2:00:00 · full download first  [Add to queue][Add & start] │ (fixed footer) │
└────────────────────────────────────────────┘          └──────────────────────────────┘
```

Queue page:

```
┌ 2 done · 1 running · 3 waiting ──────────  [▶ Start] [■ Cancel]  [⋯ more] ┐
│ ✓ #1  Big Stream · 3 parts · Full download                    [done]  📁 │
│ ◔ #2  Other VOD · 1 part · Sections          ████████░░░░ 43% · 4 min    │
│ ◷ #3  Third VOD · 2 parts · Auto                         [waiting]       │
├ ▸ Log: [Warnings] [Errors] [search…] ▮ last message here…   (drawer)  ───┤
└──────────────────────────────────────────────────────────────────────────┘
```
