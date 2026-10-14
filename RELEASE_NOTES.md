## v1.10.0

### Added
- **A new look.** The app has a new icon (a purple rounded square with a white download arrow), used in the window, the taskbar, the installer and the Mac app. The theme keeps the dark and purple colors but is flatter and roomier:
  - The main button of each screen is filled purple (**Get info**, **Search**, **Use this VOD**, **Start queue**).
  - Checkboxes are rounded, fields get a purple outline when you click in them, scrollbars are slimmer, and tabs and tables have more room.
  - The base font is a bit bigger (10 instead of 9).
- **The Options tab has a sidebar.** Instead of one long page, the sections are on the left and only one shows at a time: **Output**, **Cuts**, **Chapters**, **Premiere Pro**, **Chat**, **Clips** and **Tools**. The Up and Down keys move through them.
  - Every setting is a row with its name, a one-line hint and the control on the right. The longer explanations are in the small **i** next to the name: hover it.
  - All on/off settings are now **switches**.
  - The Premiere options (plugin `.markers.json`, game changes, `.markers.xml`, `.clips.json`) are together in **Premiere Pro**.
  - Settings you set once and rarely touch are under a collapsed **Advanced** line in Output, Cuts, Premiere Pro and Chat: download threads, file and folder names, auto threshold, the plain `.markers.xml`, `.clips.json`, and the chat format and emotes.
- **File names are easier to set up.** The file name, stream folder, single-clip name and chapter title fields have clickable `{token}` buttons that insert the token where your cursor is, and an **Example:** line that shows the real result as you type. Once you load a VOD, the example uses that VOD's name. The stream folder field greys out while *Organize in subfolders* is off.

### Good to know
- Nothing was removed and nothing changed in how files are written. Your saved settings carry over as they are, and the Premiere plugin is unchanged.
- *Add clips as chapters* is still in the Plan tab. The Chapters section in Options holds how the chapters look (title, tail, gap name).
- The Search, Plan and Queue tabs get their new look in the next release.