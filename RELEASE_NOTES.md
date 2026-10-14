## v1.7.0

### Added
- **Premiere Pro plugin (beta): colored markers.** In Options → Chapter details, tick *Also export a .markers.json for the LuckyTwitch Premiere plugin*. Each part (or the full VOD) gets a `.markers.json` next to it with every marker's kind (clip or game), time, views and clip details. The new panel in `premiere-plugin/` (download `LuckyTwitch-Premiere-Plugin.zip` from this release) imports it as **colored markers straight onto your active sequence**, instead of bringing in a separate sequence like the XML does.
- In the panel you choose what to import (games, clips, minimum views) and the colors: one color for game changes, and clip markers colored by view tiers (for example red from 50 views, orange from 10, yellow below). The clip's creator, views and link go in the marker comment. Choices are remembered. Markers can start at the beginning of the sequence or at the playhead, and one Undo removes an import.
- The plugin needs Premiere Pro 2026. Install steps are in `premiere-plugin/README.md`. A **Diagnostics** section in the panel helps check that the plugin and your Premiere agree.
- The format of the file is documented in `docs/markers-format.md`. It carries a version number, so a newer file opened by an older plugin gives a clear message instead of failing silently.

### Good to know
- **The `.markers.xml` option is unchanged.** It is a separate checkbox, so you can use the XML, the plugin file, or both. Premiere's XML import still has no marker color, so the XML keeps its `GAME:` prefix.
- *Also mark the game / category changes* now applies to both files. If it is the only marker option ticked, you still get the `.markers.xml` with the games, as before. If the plugin file is ticked as well, the games go into the `.markers.json` (tick the XML option too if you also want them there).
- Marker times in the `.markers.json` count from the start of the part, like the XML. The file also says where the part sits in the VOD (`part.start` / `part.end`), which helps to line it up with the chat file.
- Colors are not stored in the file: the plugin picks them, so you can change the scheme without downloading again. Premiere has eight marker colors to choose from.
- Both marker options are off by default, so nothing changes for existing setups.
