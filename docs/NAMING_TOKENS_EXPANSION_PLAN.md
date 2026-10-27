# Naming Tokens Expansion Plan

This plan outlines the architecture, specification, and implementation steps for expanding file and folder naming template tokens in **LuckyTwitch Downloader**.

---

## 1. Scope & Proposed Token Inventory

We will implement the complete set of practical tokens in this pass, giving users full flexibility over dates, content metadata, and segment timing:

| Token | Description | Sample Output | Applicable To |
| :--- | :--- | :--- | :--- |
| `{stream_date}` | Date the stream aired (`YYYY-MM-DD`) | `2026-10-26` | File & Folder |
| `{download_date}`| Current date when downloaded (`YYYY-MM-DD`) | `2026-10-27` | File & Folder |
| `{date}` | Backward-compatible alias for `{stream_date}` | `2026-10-26` | File & Folder |
| `{year}` | 4-digit broadcast year (extracted from stream date) | `2026` | File & Folder |
| `{month}` | 2-digit broadcast month (`01`-`12`) | `10` | File & Folder |
| `{day}` | 2-digit broadcast day (`01`-`31`) | `26` | File & Folder |
| `{game}` / `{category}` | Game or category played (dominant game for the part span) | `Just Chatting` | File & Folder |
| `{duration}` | Duration of the part or full stream formatted as tag | `01h30m00s` | File & Folder |
| `{quality}` / `{resolution}` | Video quality / resolution (e.g., `1080p60`, `720p60`, `source`) | `1080p60` | File & Folder |
| `{streamer}` | Channel / broadcaster username | `Vexoria_The_SunEater` | File & Folder |
| `{id}` | Twitch VOD ID (or fallback source ID) | `2911427150` | File & Folder |
| `{title}` | Stream / VOD title (cleaned or user-edited) | `Pretty face tragic reactions` | File & Folder |
| `{n}` | Part index (1-based; omitted if `total == 1`) | `1` | File only |
| `{total}` | Total parts in the cut plan | `3` | File only |
| `{start}` | Part start timestamp in stream | `00h00m00s` | File only |
| `{end}` | Part end timestamp in stream | `01h30m00s` | File only |

> [!NOTE]
> `{quality}` and `{resolution}` tokens are implemented to bind to the selected video quality profile. While the quality selection feature is being rolled out, they default to the source resolution (e.g. `1080p60` or `source`) and will automatically bind to the user's chosen stream format once the quality selector is active.

---

## 2. Technical Specification & Architecture

### 2.1 Dominant Game Resolution
For `{game}` and `{category}`:
* If `src.segments` exists, calculate which game segment has the maximum time overlap with the target span:
  * In `part_stem`: span is `(part.start, part.end)`.
  * In `stream_dir`: span is `(0, src.duration)`.
* If no segments exist or stream has no category, resolve cleanly to `""` (no error).

### 2.2 Date Deconstruction
* Parse `src.date` (expected format `YYYY-MM-DD`):
  * `year`: `parts[0]` or `""`
  * `month`: `parts[1]` or `""`
  * `day`: `parts[2]` or `""`
* `download_date`: `datetime.date.today().strftime("%Y-%m-%d")`.
* `stream_date`: `src.date or ""`.
* `date`: alias pointing to `stream_date`.

### 2.3 Duration Formatting
* In `part_stem`: formatted duration of `part.end - part.start` using tag format `01h30m00s` (or minutes/seconds for short parts).
* In `stream_dir`: formatted duration of `src.duration`.

---

## 3. UI Changes (Options Tab)

### 3.1 Token Chips Row
In [`qt_ui/tabs/options.py`](file:///d:/Lucky/Coding/LuckyTwitchDownloader/qt_ui/tabs/options.py):
* **File name chips:**
  ```
  [streamer] [stream_date] [download_date] [game] [quality] [id] [title] [n] [total] [start] [end] [duration]
  ```
* **Stream folder name chips:**
  ```
  [streamer] [stream_date] [download_date] [year] [month] [day] [game] [quality] [id] [title] [duration]
  ```
* **Info tooltip update:** Update helper description explaining `{stream_date}`, `{download_date}`, `{game}`, and `{duration}`.

### 3.2 Live Examples (`core/examples.py`)
* Add a sample `GameSegment(0, 7200, "Just Chatting")` into `SAMPLE_SOURCE`.
* Verify that changing templates dynamically shows resolved example names in the Destination preview.

---

## 4. Verification & Testing

1. **Unit Tests in `tests/test_naming.py`:**
   * Test `{stream_date}` and `{download_date}` tokens.
   * Test `{date}` backward compatibility.
   * Test `{year}`, `{month}`, `{day}` token extraction.
   * Test `{game}` resolution for single-game and multi-game VOD segments.
   * Test `{duration}` token on whole stream and split parts.
2. **Options Tab Tests in `tests/test_qt_options_tab.py`:**
   * Verify all token chips are present, clickable, and insert cleanly into the text entries.
   * Verify Destination preview resolves with the new tokens without error.
3. **Full Suite Regression:**
   * Run full test suite (`pytest`) to ensure 100% pass rate.
