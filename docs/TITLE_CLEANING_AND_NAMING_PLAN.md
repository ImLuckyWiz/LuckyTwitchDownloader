# Title Cleaning, Manual Naming & Single-Part Naming Plan

Status: Done in v2.1.1

This document outlines the architecture, implementation steps, and verification plan for:
1. **Fixing file truncation on titles with dots** (`Path.with_suffix` bug).
2. **Fixing double container extension in Destination preview** (`.mp4.mp4`).
3. **Skipping part indicators when there is only one part** (`total == 1`).
4. **Auto-clean titles setting** (stripping Twitch bot commands like `!gsupps !links !clash`, emojis without smushing, and promo hashtags).
5. **Manual title editing in the UI** (allowing users to edit/override the title before queuing downloads).

---

## 1. Problem Analysis & Root Causes

### 1.1 Dot Truncation in File Finalization
* **Issue:** When a VOD title contains a period (e.g., `Pretty face tragic reactions. BIG ANNOUNCEMENT!`), Python's `Path.with_suffix("." + container)` in `finalize_part()` treats everything after the period as the suffix and strips it.
* **Result:** `Vexoria_The_SunEater - Pretty face tragic reactions. BIG ANNOUNCEMENTgsupps links clash - part1` became `Vexoria_The_SunEater - Pretty face tragic reactions.mp4`.
* **Fix:** Use `dest_stem.parent / f"{dest_stem.name}.{container}"` (or `with_name`) instead of `with_suffix()`.

### 1.2 Destination Preview Double Extension (`.mp4.mp4`)
* **Issue:** In `qt_ui/tabs/options.py`, `self._refresh_save_preview()` computes:
  ```python
  full_path = Path(out_dir) / folder_tpl / f"{name_tpl}.{container}"
  ```
  However, `name_tpl` (returned by `example_file_name`) already ends with `.{container}`.
* **Result:** Destination preview displays `...part1.mp4.mp4`.
* **Fix:** Check if `name_tpl` already ends with `.{container}` or normalize the stem before joining.

### 1.3 Meaningless Part Numbers on Single-Part VODs
* **Issue:** Default `name_template` is `{streamer} - {date} - {id} - part{n}`. When a VOD has only one part (`total == 1`), the file is named `... - part1.mp4` and tagged with metadata `(part 1/1)`.
* **Fix:** When `total == 1`, cleanly omit part indicators (` - part{n}`, ` - part1`, `_part{n}`, `{n}of{total}`) from the file stem and skip `(part 1/1)` in metadata tags.

### 1.4 Dirty Titles (Bot Commands & Smushed Emojis)
* **Issue:** Streamers frequently add bot commands and sponsor promos to their titles (e.g. `!gsupps !links !clash`, `!merch`, `!discord`, `#ad`). When `safe_name()` strips punctuation and emojis (`🐍`), it deletes them without whitespace boundaries, smushing words together (`ANNOUNCEMENT! 🐍!gsupps` $\rightarrow$ `ANNOUNCEMENTgsupps`).
* **Fix:** 
  1. Add a `clean_title()` function that removes bot command tags (`!\w+`), promo tags, and cleans trailing delimiters.
  2. Improve `safe_name()` to replace emojis/symbols with spaces before collapsing whitespace.
  3. Add a setting `"clean_title": True` so users can toggle auto-cleaning on or off.

### 1.5 Manual Title Customization in the UI
* **Issue:** Currently, `SourceInfo.title` is read-only from the Twitch API. Users cannot customize, shorten, or fix typos in the title before downloading.
* **Fix:** Provide an editable title field in the Plan tab with a "Reset" button to revert to the original Twitch title.

---

## 2. Architecture & Design Specification

### 2.1 Engine & Helper Layer (`luckytwitch_engine.py` & `core/`)

#### A. Title Cleaner Function (`luckytwitch_engine.clean_title`)
```python
def clean_title(title: str) -> str:
    """Clean chat bot commands (!gsupps, !links, !clash), promo tags (#ad),
    and normalize spacing and trailing separators while preserving the core stream title.
    """
```
* **Patterns removed:**
  - Bot command invocations: `(?:^|\s)!\w+` (e.g., `!gsupps`, `!links`, `!clash`, `!discord`, `!merch`, `!prime`, `!drops`, `!socials`, `!specs`).
  - Hashtags: `(?:^|\s)#(?:ad|sponsored|drops|partner)\b` (case-insensitive).
  - Trailing separators left behind: dangling `-`, `|`, `/`, `·`, `•`, `:`, `,`, or `.`.
* **Emoji spacing in `safe_name()`:**
  - Replace non-alphanumeric, non-whitelisted characters with spaces before regex substitution so adjacent text does not merge.

#### B. Single-Part Stem Formatting (`part_stem`)
In `luckytwitch_engine.part_stem()`:
* When `total == 1`:
  - If using the default template or custom template containing part numbering, strip part suffixes matching:
    - `(?i)[\s\-_]+part\s*\{n\}`
    - `(?i)[\s\-_]+part\s*\d+`
    - `(?i)[\s\-_]+\{n\}\s*of\s*\{total\}`
    - `(?i)[\s\-_]+\d+\s*of\s*\d+`
  - Fallback name when empty: if `total == 1`, falls back to `data["title"]` or `data["id"]` instead of `part1`.
* In `run_job()` metadata tagging (line 3292):
  ```python
  if total_parts > 1:
      t["title"] = f"{src.title} (part {part.index}/{total_parts})".strip()
  else:
      t["title"] = src.title.strip()
  ```

#### C. Path Extension Safety (`finalize_part`)
In `luckytwitch_engine.finalize_part()`:
* Replace:
  ```python
  dest = unique_path(dest_stem.with_suffix("." + container))
  ```
  With:
  ```python
  dest = unique_path(dest_stem.parent / f"{dest_stem.name}.{container}")
  ```
  This guarantees any periods in `dest_stem.name` are preserved as part of the filename.

---

### 2.2 Settings Layer (`core/settings.py` & `core/options.py`)

* **New Setting Key:** `"clean_title": True`
  - Added to `DEFAULTS` in `core/settings.py`.
  - Stored as boolean in `luckytwitch_settings.json`.
* **Options Tab UI (`qt_ui/tabs/options.py`):**
  - Add an "Auto-clean titles" toggle switch under the Output section (near File name / Stream folder name).
  - Label: `"Auto-clean titles"`
  - Description: `"Remove bot commands (!links, !gsupps) and promo tags from stream titles."`
* **Fix Destination Preview (`qt_ui/tabs/options.py`):**
  - Update `_refresh_save_preview()`:
    ```python
    file_name = name_tpl if name_tpl.endswith(f".{container}") else f"{name_tpl}.{container}"
    if subfolders and folder_tpl and not folder_tpl.startswith("("):
        full_path = Path(out_dir) / folder_tpl / file_name
    else:
        full_path = Path(out_dir) / file_name
    ```

---

### 2.3 UI Layer: Title Editing & Workflow (`qt_ui/tabs/plan.py` & `qt_ui/main_window.py`)

#### A. Plan Tab Editable Title
In `qt_ui/tabs/plan.py`:
* Add a dedicated Title card or header row at the top of the Plan tab:
  - `QLabel` ("Title:") + `QLineEdit` (`self.title_entry`) + `QPushButton` ("Reset", ghost/small).
  - When a VOD is loaded:
    - If `settings["clean_title"]` is True, prefill `title_entry` with `clean_title(source.title)`.
    - If False, prefill with original `source.title`.
  - When the user edits `title_entry`:
    - Emits a signal `title_changed(str)`.
    - Updates `self.source.title` on the active `SourceInfo`.
    - Updates the Destination preview in Options and example filename labels.
  - "Reset" button restores the original Twitch title (or re-applies auto-clean).

#### B. Main Window & Queue Synchronization
In `qt_ui/main_window.py`:
* When `add_to_queue()` or `download_now()` is invoked:
  - The job uses the currently edited title from `self.source.title`.
  - Queue item displays the customized title in the table and log.

---

## 3. Step-by-Step Implementation Plan

### Phase 1: Core Engine Naming & Truncation Fixes
1. Edit `luckytwitch_engine.py`:
   - Implement `clean_title(title: str) -> str`.
   - Update `safe_name(text: str)` to insert spaces for stripped emojis/symbols instead of collapsing without boundaries.
   - Update `part_stem()` to omit part indicators when `total == 1`.
   - Fix `dest_stem.parent / f"{dest_stem.name}.{container}"` in `finalize_part()`.
   - Update MP4 metadata title tagging in `run_job()`.
2. Add unit tests in `tests/test_naming.py`:
   - Test `clean_title()` with bot commands (`!gsupps !links !clash`), hashtags (`#ad`), emojis, and edge cases.
   - Test `part_stem()` with `total == 1` vs `total > 1`.
   - Test `finalize_part()` destination path with titles containing periods.

### Phase 2: Settings & Options Tab Updates
1. Edit `core/settings.py` & `core/options.py`:
   - Add `"clean_title": True` to `DEFAULTS`.
2. Edit `qt_ui/tabs/options.py`:
   - Add "Auto-clean titles" toggle switch in the Output section.
   - Fix double `.mp4.mp4` in `_refresh_save_preview()`.
3. Add unit tests in `tests/test_core_options.py` and `tests/test_qt_options_tab.py`.

### Phase 3: Manual Title Editing in Plan Tab
1. Edit `qt_ui/tabs/plan.py`:
   - Add title entry widget and "Reset" action in the Plan tab header/summary.
   - Connect text change events to update `self.source.title`.
2. Edit `qt_ui/main_window.py`:
   - Apply `clean_title()` when `clean_title` setting is enabled upon loading VOD info.
   - Connect Plan tab's title changes to update status label and trigger example refreshes.
3. Add UI tests in `tests/test_qt_plan_tab.py`.

### Phase 4: Full Verification & Integration Testing
1. Run `pytest` on all modified test suites (`test_naming.py`, `test_qt_options_tab.py`, `test_qt_plan_tab.py`, etc.).
2. Run complete test suite (`pytest`) to ensure zero regressions across all 1300+ tests.
3. Verify live destination preview and title formatting in sample runs.

---

## 4. User Acceptance Criteria
- [x] Stream titles with dots do not truncate filename stems.
- [x] Destination preview in Options tab never displays double `.mp4.mp4`.
- [x] Single-part downloads omit ` - part1` from both the filename and video metadata title tag.
- [x] Auto-clean option strips bot commands like `!gsupps !links !clash` cleanly without smushing words.
- [x] Auto-clean can be disabled in Settings if the user wants the exact raw Twitch title.
- [x] Users can manually edit the title directly in the Plan tab before downloading.
