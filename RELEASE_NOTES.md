## v1.8.0

### Added
- **Put the markers on the video itself, not just on the sequence (Premiere plugin 0.3.0).** The panel now has two buttons side by side: **To sequence** and **To clip**.
  - **To sequence** works as before: the markers sit on the timeline at fixed times.
  - **To clip** puts the markers on the video you have selected in the timeline (or the first video clip if none is selected). They belong to the video, so they **follow it through your cuts**: razor it, ripple-delete a piece or move it, and every marker stays on the same moment of the stream.
- **A new look for the plugin panel.** It is organized in three steps: *Marker file*, *What to import* and *Add the markers*.
  - After you pick a `.markers.json`, a card shows the stream, the part and how many game changes and clips it holds.
  - Each color menu has a dot showing the color, so you see what you are choosing.
  - Only the options that matter are shown: the game colors when game changes are ticked, the three view tiers when *Color by views* is on (otherwise one color for all clips), and nothing for clips when clips are off.
  - Each button says how many markers it will add, and a status line under them shows progress, success or the error.
- **Troubleshooting section.** The paste box, the diagnostics buttons and the copyable log moved into a collapsed section at the bottom of the panel. It opens by itself when something goes wrong.

### Fixed
- **Marker colors now get applied on every import.** On some Premiere Pro 2026 setups the markers were added but stayed in Premiere's default color, and the panel showed *could not read the markers back from the sequence*. The plugin now reads the markers back fresh after adding them (and retries briefly), so all of them are colored. Checked on Premiere Pro 2026 with a full 53-marker import, both on the sequence and on a clip.
- **macOS builds no longer fail at random** with *hdiutil: create failed - Resource busy*. Creating the DMG now retries a few times.

### Good to know
- **To sequence or To clip?** Use *To clip* if you are going to cut the video (that is the usual case): the markers move with the footage. Use *To sequence* if you only want reference marks on the timeline. Pressing both adds the markers twice, once on the video and once on the sequence.
- **Importing again adds the markers again.** One Undo (Ctrl/Cmd+Z) removes the last import; do that before importing a second time.
- **The playhead option** (*The part starts... at the playhead*) only applies to *To sequence*. *To clip* always uses the video's own time, so the markers line up when the clip plays the part from its start.
- Nothing changes in how the files are written: your existing `.markers.json` files work as they are, and the Python app is unchanged apart from the macOS build fix.
- To update the plugin, install the new version over the old one. With `LuckyTwitch-Premiere-Plugin.ccx`, open it with Creative Cloud. If your PC does not open `.ccx` files, unzip `LuckyTwitch-Premiere-Plugin.zip` and run `install-dev.bat`. Restart Premiere afterwards. If you used `install-dev.bat` before and now install the `.ccx`, run `install-dev.bat -Uninstall` first so there are not two copies.
- The plugin keeps using the same settings storage, so your colors and view tiers should carry over. If they reset, just set them again.