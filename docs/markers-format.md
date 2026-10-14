# `.markers.json` format (version 1)

Written by LuckyTwitch Downloader next to each part when **Options → Chapter details → Also export a .markers.json for the LuckyTwitch Premiere plugin** is on. Read by the plugin in [`premiere-plugin/`](../premiere-plugin). This file is the contract between the two, so a change here means a change on both sides.

The sample `tests/fixtures/markers_sample.json` is checked by the Python tests (it must be exactly what the app writes) and by the plugin's tests (it must be readable), so the two cannot drift apart without a test failing. Regenerate it with `python tests/test_premiere_plugin_json.py`.

```json
{
  "format": "luckytwitch-markers",
  "version": 1,
  "name": "Streamer - 2026-01-01 - 1 - part1",
  "duration": 70.0,
  "fps": 29.97,
  "part": { "start": 1200.0, "end": 1270.0 },
  "source": { "url": "...", "vod_id": "1", "title": "...", "streamer": "...", "date": "2026-01-01" },
  "markers": [
    { "kind": "game", "name": "Just Chatting", "start": 0.0, "end": 50.0, "game": "Just Chatting", "comment": "Game / category" },
    { "kind": "clip", "name": "Funny moment (bob, 120 views)", "start": 7.0, "end": 30.0, "views": 120,
      "comment": "bob · 120 views · https://clips.twitch.tv/c1",
      "clips": [ { "id": "c1", "title": "Funny moment", "creator": "bob", "views": 120, "duration": 20.0, "url": "https://clips.twitch.tv/c1" } ] }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `format` | Always `"luckytwitch-markers"`. The plugin refuses anything else. |
| `version` | Layout version. The plugin refuses a file newer than it understands and says to update. Adding optional fields does not bump it; removing or changing the meaning of a field does. |
| `name` | The part's file name without extension. |
| `duration` | Real length of the part in seconds. |
| `fps` | Frame rate read from the part with ffprobe (30 if it could not be read). |
| `part.start` / `part.end` | Where the part sits in the original VOD, in seconds. Useful to line up the chat file, whose times count from the start of the VOD. |
| `source` | The VOD the part came from (omitted if unknown). |
| `markers[].kind` | `"game"` (a game / category stretch) or `"clip"` (a Twitch clip). |
| `markers[].start` / `end` | Seconds **from the start of the part** (not the VOD). `end > start` for a range; a marker can also be a single point. |
| `markers[].name` | Clip: the title built from the chapter title template. Game: the game's name, with no `GAME:` prefix (the plugin adds it if asked). |
| `markers[].comment` | Text for the marker's comment field. |
| `markers[].views` | Clips only. Total views of the clip (the largest, if several clips were merged into one chapter). |
| `markers[].game` | Games only. The game's name. |
| `markers[].clips` | Clips only. Every Twitch clip behind the marker (several when overlapping clips were merged). |

Markers are sorted by start time (game markers first when they start together). Colors are **not** in the file on purpose: the plugin chooses them from `kind` and `views`, so you can change the scheme without re-downloading.
