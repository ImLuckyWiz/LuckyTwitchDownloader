# LuckyTwitch v1.0

Download Twitch VODs (or any yt-dlp supported link) and cut them into parts by timestamps, with optional Twitch clip chapters.

## Features
- **Cut by timestamps:** `0:00 - 30:00 - 1:30:00 - end` makes consecutive parts. Use `;` or a new line to skip gaps: `0:00 - 30:00 ; 2:00:00 - end`.
- **Smart download strategy:** downloads the full VOD and splits it, or downloads only the parts you asked for, whichever is cheaper (or force one).
- **Exact cuts** option, custom file/folder name templates, and the choice to keep the full VOD.
- **Clip chapters (optional):** build chapters from a VOD's Twitch clips, filtered by views, duration or top N (needs Twitch API credentials).
- **Progress and cancel:** live progress with speed, and cancelling stops everything and keeps the partial download so it can resume.
- **Zero setup:** yt-dlp and ffmpeg are downloaded automatically on first launch, and yt-dlp stays up to date.

## Downloads
- **Windows:** `LuckyTwitch-Setup.exe` (installs for your user, no admin rights needed).
- **macOS:** `LuckyTwitch-macos-arm64.dmg` for Apple Silicon (M1/M2/M3...), `LuckyTwitch-macos-x86_64.dmg` for Intel Macs.

## First launch
- **macOS:** the app is not notarized. Right-click it, choose **Open**, then **Open** again (once). If macOS says it is damaged, run `xattr -cr /Applications/LuckyTwitch.app`.
- **Windows:** SmartScreen may warn about an unknown publisher. Click **More info**, then **Run anyway**.
- Needs internet on first run to fetch yt-dlp and ffmpeg.

Settings and downloaded tools are stored in `%LOCALAPPDATA%\LuckyTwitch` (Windows) or `~/Library/Application Support/LuckyTwitch` (macOS). Downloads go to `Downloads/LuckyTwitch` by default.
