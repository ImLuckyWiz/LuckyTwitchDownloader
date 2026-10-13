## v1.5.1

### Fixed
- **Clips were out of sync: they appeared one clip-length too late.** Twitch reports the position of a clip as the moment it *ends*, and the app used it as the moment it *starts*. Every clip start was shifted by the length of the clip (a 60 s clip showed up 60 s late). The start is now calculated as end − length. This fixes all of these at once:
  - the **At** column in the Clips table;
  - the green clip marks on the timeline;
  - **Split at selected clip**;
  - **Download selected clips** (the cut now covers the clip itself and not the part after it);
  - the clip **chapters** inside the downloaded file;
  - the **Premiere Pro markers** (`.markers.xml`): In is now at the start of the clip and Out at its end.
- Example: a 60 s clip that ends at 0:22:15 now starts at 0:21:15 (before, it was shown at 0:22:15).

### Good to know
- If you already downloaded parts with clip chapters or Premiere markers, download them again to get the corrected positions. Old `.markers.xml` files are wrong by the length of each clip.
- Markers can still be 1–2 seconds off in Premiere. When a part is cut without re-encoding, it starts at the nearest keyframe and not at the exact second you typed. This is a separate, small difference and is not changed in this version.
