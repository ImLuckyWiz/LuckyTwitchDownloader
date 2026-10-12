# LuckyTwitch Downloader

Download Twitch VODs (or any link yt-dlp supports) and cut them into parts by timestamps, with optional chapters built from the VOD's Twitch clips. Runs on Windows and macOS.

## Download

Get the latest version from the [Releases](../../releases) page:

| System | File |
| --- | --- |
| Windows | `LuckyTwitch-Setup.exe` |
| macOS, Apple Silicon (M1, M2, M3...) | `LuckyTwitch-macos-arm64.dmg` |
| macOS, Intel | `LuckyTwitch-macos-x86_64.dmg` |

### Install

- **Windows:** run the installer. It installs for your user only (no admin rights needed) and adds a Start menu entry. Running a newer installer updates the existing install.
- **macOS:** open the `.dmg` and drag **LuckyTwitch** onto the **Applications** shortcut. To update, drag the new version over the old one and choose **Replace** (close the app first).

### First launch

- **macOS:** the app is not notarized by Apple. Right-click it → **Open** → **Open** (only once). If macOS says the app is damaged, run `xattr -cr /Applications/LuckyTwitch.app` in Terminal.
- **Windows:** SmartScreen may warn about an unknown publisher. Click **More info** → **Run anyway**.
- The app needs internet on first run: it downloads **yt-dlp** and **ffmpeg** by itself. yt-dlp is kept up to date automatically.

## Using it

1. Paste a VOD URL or ID and press **Get info**.
2. Write the cut points, for example `0:00 - 30:00 - 1:30:00 - end` (consecutive parts). Use `;` or a new line to skip gaps: `0:00 - 30:00 ; 2:00:00 - end`. Times can be `H:MM:SS`, `MM:SS`, seconds or `1h30m`.
3. Choose the download strategy (**Auto** picks whichever is cheaper: full VOD then split, or only the parts), then start the job.

Other options include exact cuts, file and folder name templates, keeping the full VOD, and a queue of jobs. Cancelling stops everything and keeps the partial download so it can resume.

### Clip chapters (optional)

The app can build chapters from a VOD's Twitch clips, filtered by views, duration or top N. This needs a Twitch session:

1. Press **Twitch API…** → **Sign in with Twitch**.
2. A code appears and `twitch.tv/activate` opens in your browser. Enter the code and authorize.

This uses Twitch's Device Code Flow with a public app, so there is no client secret and you do **not** need a Twitch developer account. Advanced users can still enter their own Client ID / Secret in the same window.

## Where things are stored

| What | Windows | macOS |
| --- | --- | --- |
| Settings, Twitch login (`config.json`) | `%LOCALAPPDATA%\LuckyTwitch` | `~/Library/Application Support/LuckyTwitch` |
| yt-dlp and ffmpeg | `...\LuckyTwitch\tools` | `.../LuckyTwitch/tools` |
| Downloads (default) | `Downloads\LuckyTwitch` | `~/Downloads/LuckyTwitch` |

Uninstalling the app leaves this data folder in place; delete it for a clean removal. To reinstall ffmpeg, delete `ffmpeg` and `ffprobe` from the `tools` folder and restart the app.

## Run from source

```
pip install requests
python luckytwitch_downloader.py
```

Python 3.10+ with Tk is required (on macOS use Python from python.org, since the system Python ships an old Tk). When run from source, settings and downloads stay next to the scripts.

## Build it yourself

PyInstaller cannot cross-compile, so build each system on that system.

- **Windows:** run `build_windows.bat [version]` → `dist\LuckyTwitch\LuckyTwitch.exe`, plus `dist\LuckyTwitch-Setup.exe` if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed.
- **macOS:** run `./build_mac.sh` → `dist/LuckyTwitch.app` and `dist/LuckyTwitch-macos-<arch>.dmg`. It also installs the app into Applications on that Mac. The result matches the Mac's chip (Apple Silicon or Intel).

## Notes

- The ffmpeg builds the app downloads are GPL. That is fine for personal use; follow the GPL terms if you redistribute them.
- yt-dlp breaks now and then when Twitch changes things. The app updates it on launch, so restarting it is usually enough.
