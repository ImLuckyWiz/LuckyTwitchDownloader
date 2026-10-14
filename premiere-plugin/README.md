# LuckyTwitch Markers (Premiere Pro panel)

Imports the `.markers.json` that LuckyTwitch Downloader writes next to each part, as **colored markers on your active sequence**: one color for game changes, clip markers colored by how many views the clip has, the clip's creator, views and link in the marker comment. It adds to the sequence you are editing instead of importing a separate sequence like the XML does.

> **Status: beta (0.1.5).** Checked on a running Premiere Pro 2026: the file picker, importing markers into the active sequence, and coloring work. If a marker color does not match its name, see Diagnostics below.

Needs Premiere Pro 2026 (UXP panels; `minVersion` in `manifest.json` is 25.6.0).

## Install

**Double-click `LuckyTwitch-Premiere-Plugin.ccx`** (from the release page). Creative Cloud Desktop installs it, then restart Premiere Pro and open the panel from the Window menu (Window > UXP Plugins). Needs the Creative Cloud Desktop app, which Premiere comes with.

If an older copy was installed with `install-dev.bat`, remove it first (`install-dev.bat -Uninstall`) so two copies do not sit side by side.

### Manual install (if the .ccx will not open)

Unzip `LuckyTwitch-Premiere-Plugin.zip` and double-click `install-dev.bat`. It copies the plugin to `%APPDATA%\Adobe\UXP\Plugins\External\com.luckytwitch.premiere-markers_<version>` (Premiere only loads it if the folder is named `<manifest id>_<manifest version>`; the script reads both from `manifest.json`), replacing any earlier copy. Then restart Premiere Pro. Run it again after every change to the plugin. `install-dev.bat -Uninstall` removes it.

You may need **Enable developer mode** in Premiere's UXP plugin settings. If the panel does not show up, check the folder name first.

Alternative: **UXP Developer Tool** (Creative Cloud Desktop > All apps), Add Plugin, pick `manifest.json`, Load. The panel then appears under the Window menu.

## Use

1. In LuckyTwitch Downloader, tick **Also export a .markers.json for the LuckyTwitch Premiere plugin** (and **Also mark the game / category changes** if you want games). Download as usual. The `.markers.json` appears next to each part.
2. Put the part on a sequence in Premiere and make that sequence active.
3. In the panel press **Choose .markers.json…**, pick the file (if the picker will not open on your Premiere, paste the file's text into the box under the button and press **Use pasted text**), adjust colors if you like, and press **Import markers into the active sequence**.

The plain `.markers.xml` option is still there for anyone who does not want the plugin.

- **Colors:** Premiere only has eight marker colors (Green, Red, Purple, Orange, Yellow, White, Blue, Cyan). Clips use three tiers by view count; the thresholds and colors are editable and remembered.
- **Where:** markers are placed from the start of the sequence, or from the playhead if you choose that (use it when the part does not start at 0:00 of the sequence).
- **Undo:** one Undo removes everything an import added (markers and colors are two steps if coloring runs).

## Diagnostics

- **Probe the API** lists what this Premiere build offers on the objects the plugin uses. Paste the result into an issue or a message when something does not work.
- **Add test markers** puts eight markers at 0, 5, 10… seconds, each named with the color the plugin *thinks* its color index is. If a marker's color does not match its name, the color order in `src/markers-core.js` (`COLORS`) needs adjusting.

## Development

```
manifest.json            UXP manifest (panel entry point)
index.html               the panel
src/markers-core.js      pure logic: read and check the file, settings, colors, plan (tested)
src/premiere-adapter.js  every call into Premiere (the only file to fix when the API differs)
src/main.js              UI wiring
test/                    node tests; they read ../tests/fixtures/markers_sample.json
```

```
npm run check     # syntax check
npm test          # needs Node 20+, no dependencies
```

The file format is described in [`../docs/markers-format.md`](../docs/markers-format.md).
