# Real-Hardware Verification Checklist (Phase V)

Status: In progress (Windows checks verified; macOS checks pending hardware)

This document tracks real-hardware verification runs across Windows, macOS, and Premiere Pro environments.

---

## Verification Matrix

| # | Check | Platform | Status | What Proved It / Current State |
|---|---|---|---|---|
| **V1** | Chat overlay `.mov` (Animation) transparency & playback in Premiere | Windows + Premiere Pro | **VERIFIED** | Verified with 20 min 1080p60 cut. Premiere Pro program monitor confirmed transparent alpha channel over video. LuckyTwitch Markers CEP panel (v0.14.0) loaded and matched cut markers. |
| **V2** | Overlay on a multi-hour VOD (time, memory, stability) | Windows | **VERIFIED** | Verified with 5+ hour full VODs rendered without memory leaks or crashes. |
| **V3** | MP3 audio-only chapters (ID3v2 `CHAP`) | Windows | **VERIFIED** | Verified with 20 min MP3 cut. Chapters (clip titles, timestamps) cleanly detected and seekable in `mpv`. *(Note: VLC media player does not support ID3v2 `CHAP` tags natively; players using ffmpeg/libav like mpv and Foobar2000 support them fully).* |
| **V4** | `install-mac.command` installs CEP panel and Premiere displays it | macOS + Premiere Pro | **PENDING** | Awaiting real Mac hardware. Documented as *not verified on macOS* in the meantime. |
| **V5** | macOS update flow (pill, dialog, download correct DMG for architecture) | macOS | **PENDING** | Awaiting real Mac hardware. Documented as *not verified on macOS* in the meantime. |
| **V6** | Windows silent update preserves settings, credentials, and tools | Windows | **VERIFIED** | Verified upgrading in-place from v2.3.1 to v2.3.2. Update dialog downloaded setup, verified SHA-256, exited cleanly, installed silently, and relaunched into v2.3.2 with all settings, tool paths, and window state intact. |

---

## Detailed Procedures

### V4: CEP Panel macOS Installation
1. On a Mac running Premiere Pro, extract `LuckyTwitch-Premiere-Plugin-CEP.zip` (or repo).
2. Run `install-mac.command` in Terminal.
3. Launch Adobe Premiere Pro → **Window → Extensions → LuckyTwitch Markers**.
4. Confirm extension opens without signing or unsigned extension errors.

### V5: macOS Update Flow
1. Run a release build of LuckyTwitch on macOS (Apple Silicon or Intel).
2. Trigger update check when a newer GitHub release is live.
3. Confirm status bar pill and update dialog appear.
4. Click **Update now** and verify it opens the appropriate DMG (`-arm64.dmg` or `-x86_64.dmg`).

### V6: Windows In-Place Silent Update
1. Install an earlier version (e.g. v2.3.0) via `LuckyTwitch-Setup.exe`.
2. Configure settings (e.g. custom output folder, Twitch login, downloaded tools in `%LOCALAPPDATA%\LuckyTwitch`).
3. Launch app, trigger update to v2.3.1.
4. Click **Update now**.
5. Confirm installer completes silently without UAC prompts and relaunches into v2.3.1.
6. Verify all settings, Twitch login, and tools are preserved.
