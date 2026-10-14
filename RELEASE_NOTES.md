## v1.9.0

### Added
- **A proper app icon.** LuckyTwitch now has its own icon: a purple download arrow with a cut through its shaft. It shows in the window title bar, the taskbar / Dock, the Start menu and desktop shortcut, and in the installer and uninstaller (no more default Python feather).

### Changed
- **A fresher look, same colors.** The dark theme with the purple accent stays, but everything is cleaner:
  - The main action of each screen is now a solid purple button: **Get info**, **Search**, **Use this VOD** and **Start queue**. The other buttons are flat and light up when you hover them.
  - Check boxes are rounded and turn purple when ticked.
  - Fields get a purple outline while you type in them, and the text boxes no longer show a white frame.
  - Scrollbars are thinner and have no arrows, tabs are flatter and roomier, tables have more breathing room, and the progress bar is thinner.
  - The text is slightly bigger (10 pt instead of 9 pt) to make it easier to read.

### Good to know
- This is the first part of a bigger visual update. The **Options** tab will get a new layout in the next version; nothing moved yet.
- Nothing about how the app works changed: your settings, queue, cut points and downloads behave exactly as before, and the Premiere plugin and its `.markers.json` files are untouched.
- Tests: the app's tests were extended with checks for the icon files, the new look and the new switch widget.
