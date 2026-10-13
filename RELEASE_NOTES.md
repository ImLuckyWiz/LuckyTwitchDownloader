## v1.5.0

### Added
- **Timeline** at the top of the Plan tab: the whole VOD on one strip, so you can see where the streamer changed game and place your cuts with the mouse. It shows:
  - one coloured bar per game (the same game always has the same colour);
  - preview thumbnails of the VOD, loaded in the background;
  - green marks for the clips;
  - the parts you will download, with skipped sections left dark.
- **Editing on the timeline:**
  - click the thumbnails to cut there (cuts snap to game changes and clips);
  - drag a cut line to move it, right-click it to remove it;
  - click a part to skip it, click a skipped section to bring it back;
  - double-click a game bar to make it its own part (Shift + double-click: keep only that game).
- **Zoom and move:** mouse wheel to zoom, Shift + wheel or the scroll bar to move, **Fit** to see the whole VOD again, **Undo** (or Ctrl+Z) to take back the last edit. Hover anywhere to see the time, the game and a bigger thumbnail.
- The **Cut points** text box still works and stays in sync: type there and the timeline follows, edit the timeline and the text changes.

### Fixed
- **Split at selected clip** used twice on the same clip no longer writes an empty range like `0:59:57 - 0:59:57`. The second split now does nothing.

### Good to know
- Thumbnails are a few minutes apart on long VODs (every 5 seconds on a 15-minute one), so use them to find the place and type the exact time when you need precision.
- Without Pillow, or if Twitch has no thumbnails for a VOD, the timeline works without pictures. VODs without game information show no game bars.
- On macOS, right-click means two-finger click or Ctrl + click.
