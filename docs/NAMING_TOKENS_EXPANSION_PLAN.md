# Naming Tokens Expansion Plan

This plan outlines the architecture, specification, and implementation steps for expanding file and folder naming template tokens in **LuckyTwitch Downloader**.

---

## 1. Scope & Proposed Token Inventory

All practical tokens for dates, stream content, quality, and segment timing will be supported across both file names (`name_template`) and folder names (`folder_template`):

| Token | Description | Sample Output | Applicable To |
| :--- | :--- | :--- | :--- |
| `{stream_date}` | Date the stream aired (`YYYY-MM-DD`) | `2026-10-26` | File & Folder |
| `{download_date}`| Date downloaded (`YYYY-MM-DD`) | `2026-10-27` | File & Folder |
| `{date}` | Backward-compatible alias for `{stream_date}` | `2026-10-26` | File & Folder |
| `{year}` | 4-digit broadcast year (extracted from stream date) | `2026` | File & Folder |
| `{month}` | 2-digit broadcast month (`01`-`12`) | `10` | File & Folder |
| `{day}` | 2-digit broadcast day (`01`-`31`) | `26` | File & Folder |
| `{game}` / `{category}` | Game or category played (dominant game for the part or stream) | `Just Chatting` | File & Folder |
| `{duration}` | Duration of the part or full stream formatted as tag | `01h30m00s` | File & Folder |
| `{quality}` / `{resolution}` | Video quality tag (e.g. `1080p60`, `720p60`, `Audio`) | `1080p60` | File & Folder |
| `{streamer}` | Channel / broadcaster username | `Vexoria_The_SunEater` | File & Folder |
| `{id}` | Twitch VOD ID (or fallback source ID) | `2911427150` | File & Folder |
| `{title}` | Stream / VOD title (cleaned or user-edited) | `Pretty face tragic reactions` | File & Folder |
| `{n}` | Part index (1-based; omitted if `total == 1`) | `1` | File only |
| `{total}` | Total parts in the cut plan | `3` | File only |
| `{start}` | Part start timestamp in stream | `00h00m00s` | File only |
| `{end}` | Part end timestamp in stream | `01h30m00s` | File only |

> [!NOTE]
> The Quality selection engine is already implemented in v2.2.0. `{quality}` is currently supported in `part_stem()`. This update adds `{quality}` to `stream_dir()`, adds `{resolution}` as a synonym in both, and introduces all date deconstruction, dominant game, and duration tokens.

---

## 2. Technical Specification & Architecture

### 2.1 Dominant Game Resolution (`{game}` & `{category}`)
Define a pure helper function in `luckytwitch_engine.py`:
```python
def dominant_game(segments: list[GameSegment] | None, start: float, end: float) -> str:
    """Returns the game/category with the longest time overlap inside [start, end]."""
    if not segments or end <= start:
        return ""
    overlaps: dict[str, float] = {}
    for seg in segments:
        seg_start = getattr(seg, "start", 0.0)
        seg_end = getattr(seg, "end", 0.0)
        title = (getattr(seg, "title", "") or "").strip()
        if not title:
            continue
        overlap = max(0.0, min(end, seg_end) - max(start, seg_start))
        if overlap > 0:
            overlaps[title] = overlaps.get(title, 0.0) + overlap
    if not overlaps:
        return ""
    return max(overlaps.items(), key=lambda item: item[1])[0]
```
- **In `part_stem`:** span is `(part.start, part.end)`.
- **In `stream_dir`:** span is `(0.0, src.duration or 0.0)`.
- **Fallback:** Returns `""` cleanly if no segments exist or there is no overlap.
- **Alias:** Both `{game}` and `{category}` are populated with this value.

### 2.2 Date Deconstruction (`{stream_date}`, `{download_date}`, `{year}`, `{month}`, `{day}`)
Define a helper function to deconstruct date strings:
```python
def date_components(date_str: str | None) -> tuple[str, str, str]:
    """Extract (year, month, day) from YYYY-MM-DD or empty strings if invalid."""
    if not date_str:
        return "", "", ""
    parts = date_str.strip().split("-")
    year = parts[0] if len(parts) >= 1 and len(parts[0]) == 4 and parts[0].isdigit() else ""
    month = parts[1] if len(parts) >= 2 and len(parts[1]) == 2 and parts[1].isdigit() else ""
    day = parts[2] if len(parts) >= 3 and len(parts[2]) == 2 and parts[2].isdigit() else ""
    return year, month, day
```
- `stream_date = src.date or ""`
- `date = stream_date` (backward compatible)
- `year, month, day = date_components(src.date)`
- `download_date = datetime.now().strftime("%Y-%m-%d")`

### 2.3 Duration Formatting (`{duration}`)
Format duration using standard timestamp tags:
```python
def format_duration_tag(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 3600:02d}h{s % 3600 // 60:02d}m{s % 60:02d}s"
```
- **In `part_stem`:** `format_duration_tag(part.end - part.start)`
- **In `stream_dir`:** `format_duration_tag(src.duration or 0.0)`

### 2.4 Quality & Resolution in `stream_dir`
In `stream_dir(src: SourceInfo, opts: JobOptions)`:
- Resolve format tag using `resolve_format()` like `part_stem()`:
  ```python
  resolved_q = resolve_format(src.formats, getattr(opts, "quality", QUALITY_BEST)) if getattr(src, "formats", None) else None
  q_tag = resolved_q.tag if resolved_q else ""
  ```
- Bind both `quality=q_tag` and `resolution=q_tag`.

---

## 3. UI Changes (Options Tab & Live Previews)

### 3.1 Token Chips Row
In [`qt_ui/tabs/options.py`](file:///d:/Lucky/Coding/LuckyTwitchDownloader/qt_ui/tabs/options.py):
- **File name chips (`name_template`):**
  ```python
  [
      "streamer", "stream_date", "download_date", "year", "month", "day",
      "game", "quality", "id", "title", "duration", "n", "total", "start", "end",
  ]
  ```
- **Folder name chips (`folder_template`):**
  ```python
  [
      "streamer", "stream_date", "download_date", "year", "month", "day",
      "game", "quality", "id", "title", "duration",
  ]
  ```
- **Info descriptions:** Update the hint / info text to describe the new tokens.

### 3.2 Live Examples (`core/examples.py`)
- Update `SAMPLE_SOURCE` with sample game segments:
  ```python
  from luckytwitch_engine import GameSegment

  SAMPLE_SOURCE = dict(
      url="https://www.twitch.tv/videos/123",
      id="v123",
      title="Big Stream",
      uploader="Streamer",
      duration=7200.0,
      date="2026-10-01",
      twitch_vod_id="123",
      segments=[GameSegment(0.0, 7200.0, "Just Chatting")],
  )
  ```
- Ensure live previews in Options tab display resolved values for `{game}`, `{year}`, `{month}`, `{day}`, `{duration}`, `{download_date}`, and `{stream_date}`.

---

## 4. Implementation Phases

- **Phase 1: Pure Engine Helpers & Data Dictionary**
  - Implement `dominant_game()`, `date_components()`, and `format_duration_tag()` in `luckytwitch_engine.py`.
  - Populate all tokens in `_SafeDict` for both `part_stem()` and `stream_dir()`.
  - Add `{resolution}` as synonym for `{quality}`, and `{category}` as synonym for `{game}`.
  - Tests in `tests/test_naming.py`.

- **Phase 2: Example Source & Live Previews**
  - Update `core/examples.py` `SAMPLE_SOURCE` with sample game segments.
  - Verify live preview example functions.

- **Phase 3: Options Tab Chips & Layout**
  - Update token lists for `name_template` and `folder_template` in `qt_ui/tabs/options.py`.
  - Update `tests/test_qt_options_tab.py` expectations.

- **Phase 4: Full Test Suite & Verification**
  - Run `python -m pytest` across all test files.
  - Verify all 1,360+ tests pass with 0 regressions.
