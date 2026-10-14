## v1.7.1

### Fixed
- **The exact segment download now works on newer Twitch VODs.** Some VODs are served as fMP4 (with an init section, `#EXT-X-MAP`), and the app refused them with *"Could not use the segment download (unsupported playlist tag #EXT-X-MAP)"* and fell back to the old method. The segment download now handles fMP4 playlists (and byte ranges), so the part starts at a known segment boundary and the markers line up exactly, instead of being up to 10 s off.

### Good to know
- Encrypted playlists and playlists with discontinuities still use the old method, as before. When that happens, the log line says why.

