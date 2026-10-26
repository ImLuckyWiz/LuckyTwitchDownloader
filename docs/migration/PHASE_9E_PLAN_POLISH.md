# Phase 9e Plan Page Polish & Responsive Refinements

## 1. Overview & Goals
Based on testing on Windows with real VODs, this plan addresses responsive issues on the Plan page:
1. Resolves label/input text collisions in the clip filter fields (`Clips → chapters`) by converting the 1-row layout into a robust 2×2 grid.
2. Increases the responsive 2-column breakpoint from `1000 px` to `1100 px` so columns have ample room before switching to 2 columns.
3. Implements an auto-looping `MarqueeLabel` for smooth horizontal scrolling of truncated text (such as long game titles on `PartCard`).
4. Enhances the clip table with full `"Duration"` column heading, interactive manual column resizing, horizontal scrolling, and cell tooltips.

---

## 2. Detailed Technical Plan

### Part 1: Fix Filter Squishing & 2-Column Breakpoint
* **Filter Controls Layout (`Clips → chapters` in `qt_ui/tabs/plan.py`):**
  - Replace the single horizontal `QHBoxLayout` with a `QGridLayout` (`2 rows × 2 columns`).
    - **Row 0, Col 0:** `Min views` &nbsp;→ `[SpinBox]`
    - **Row 0, Col 1:** `Min duration (s)` &nbsp;→ `[SpinBox]`
    - **Row 1, Col 0:** `Top N (0 = all)` &nbsp;→ `[SpinBox]`
    - **Row 1, Col 1:** `Lead-in (s)` &nbsp;→ `[SpinBox]`
  - Preserves `self.filter_spins` dictionary and `SettingsBinder` bindings (`min_views`, `min_duration`, `top_n`, `pad_before`).
  - Total minimum width drops from **~610 px** to **~220 px**, completely preventing overlap regardless of window size.
* **Breakpoint Update:**
  - Update `WIDE_BREAKPOINT = 1100` in `qt_ui/tabs/plan.py`.
  - Window widths `< 1100 px` stay in a clean single-column stack.
  - Window widths `≥ 1100 px` adapt into two side-by-side columns.

---

### Part 2: Animated Horizontal Scrolling Text (`MarqueeLabel`)
* **Component (`MarqueeLabel` in `qt_ui/widgets.py` or `qt_ui/tabs/plan.py`):**
  - Subclasses `QWidget` (or `QLabel`) with a custom `paintEvent`.
* **Auto-Looping Animation Behavior:**
  1. Compares `fontMetrics().horizontalAdvance(text)` with `width()`. If text fits, it renders statically (0% CPU, no timer).
  2. If text overflows:
     - **Start Pause:** Holds at offset `0` for **1.5 seconds** for readability.
     - **Smooth Scroll:** Scrolls horizontally at a readable rate (~30 px/sec) until the end of the text is fully visible.
     - **End Pause:** Holds at the end for **1.5 seconds**.
     - **Loop / Reset:** Resets to offset `0` and repeats.
* **Performance & Safety Guardrails:**
  - Respects `Motion.enabled()`: when disabled (in tests or when OS animations are turned off), timers do not run and text is cleanly elided with an ellipsis (`...`).
  - Automatically pauses timer on `hideEvent` and resumes on `showEvent`.
* **Application:**
  - Used for the game category label in `PartCard` (`self.game_lbl`).

---

### Part 3: Clips Table Enhancements
* **"Dur" → "Duration":**
  - Update `CLIP_COLUMNS` heading from `"Dur"` to `"Duration"`.
  - Preserve the key `"dur"` so all existing test assertions (`assert [c[0] for c in CLIP_COLUMNS] == [...]`) remain 100% green.
* **Manual Column Resizing:**
  - Set `head.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)` so users can drag column dividers in the header.
  - Set `head.setStretchLastSection(False)` or keep proportional default widths while allowing manual overrides.
* **Horizontal Scrolling:**
  - Ensure `self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)` so user can scroll horizontally when columns are expanded.
* **Cell Tooltips:**
  - Provide full text tooltips on hover for truncated cells (e.g. Title, Creator).

---

## 3. Verification & Testing
1. Run `python -m pytest tests/test_qt_plan_tab.py tests/test_qt_main_window.py -q` ensuring all 75 tests pass.
2. Update `test_responsive_two_column_vs_stacked_layout` to verify breakpoint at `1100 px` (testing at `1150 px` and `900 px`).
3. Add a unit test verifying `MarqueeLabel` overflow detection and static mode when text fits.
