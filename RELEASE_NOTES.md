## v1.5.2

### Fixed
- **"Download only these parts": the file could start up to 10 s before the time you typed, which shifted the chapters and the Premiere Pro markers.** The app now downloads whole 10-second segments of the VOD itself, so it knows exactly where each file starts. Chapters and Premiere markers (`.markers.xml`) now match the Twitch player.
- The file can still begin a few seconds before your time (at the previous 10-second mark), never after. Times that are multiples of 10 s (for example 20:00:00 or 1:00:00) start exactly.
- The log now shows one line per part with the real start and end, for example `Part 1 starts at 0:20:00 (asked 0:20:03, 3 s early) and ends at 0:21:10`, so you can compare it with the Twitch player.

### Changed
- **Exact cuts** (the re-encode option) with "download only these parts" now cut from the downloaded segments, so the file starts at the exact second you typed. Before, this option still started up to 10 s early.

### Good to know
- If the segment method cannot be used for a VOD, the app falls back to the previous method and says so in the log. In that case the markers can still be up to 10 s off.
- If you already downloaded parts with clip chapters or Premiere markers using "only these parts", download them again to get the corrected positions.
- The "download the full VOD, then split" strategy was already accurate and is not changed.
