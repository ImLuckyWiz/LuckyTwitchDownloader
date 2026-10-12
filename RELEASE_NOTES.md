## v1.2.1

### Changed
- **Premiere Pro markers now span the whole clip.** In the exported `.markers.xml`, each marker starts where the clip starts (including the lead-in) and ends where the clip ends (including the tail), instead of being a single point. If clips overlap and were merged into one chapter, the marker covers all of them.

### Notes
- Re-run the download of a part to get the new XML (the file is written when the part finishes).
