## v1.7.2

### Fixed
- **The Premiere Pro plugin now works.** The panel in v1.7.1 and earlier could start dead: *Choose .markers.json…* did nothing and nothing was shown. It now starts reliably, opens the file picker, and imports the markers (and their colors) into the active sequence. Checked on Premiere Pro 2026.
- **The panel looks right and can be scrolled.** Text was black on gray boxes; the controls now have proper colors for Premiere's dark theme (and light theme). A scroll bar was added so everything is reachable.

### Added
- **A real plugin file: `LuckyTwitch-Premiere-Plugin.ccx`.** Double-click it and Creative Cloud installs the plugin, no more copying folders. The `.zip` (with `install-dev.bat`) is still there for a manual install.
- **A log you can copy** in the plugin panel, with *Copy log* and *Clear log* buttons, plus a *Diagnostics* section to check the plugin against your Premiere.
- **A paste box** under *Choose .markers.json…*: if the file picker will not open on some Premiere, paste the file's text there instead.

### Good to know
- To install or update the plugin: double-click `LuckyTwitch-Premiere-Plugin.ccx` and restart Premiere. If you installed it before with `install-dev.bat`, run `install-dev.bat -Uninstall` first so there are not two copies.
- The Python app is unchanged since v1.7.1.