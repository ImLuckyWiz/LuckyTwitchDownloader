# LuckyTwitch – building the app

yt-dlp and ffmpeg/ffprobe are **not** bundled. On first launch the app downloads them
into a per-user tools folder and keeps yt-dlp up to date:

- Windows: `%LOCALAPPDATA%\LuckyTwitch\tools`
- macOS: `~/Library/Application Support/LuckyTwitch/tools`

The packaged app also stores `config.json` and its settings in the parent folder
(`...\LuckyTwitch`), and downloads go to `~/Downloads/LuckyTwitch` by default.
(Running from source keeps everything next to the scripts, as before.)

## Build locally
PyInstaller cannot cross-compile: build each OS on that OS.

- **Windows:** run `build_windows.bat` → `dist\LuckyTwitch\LuckyTwitch.exe`
- **macOS:** run `./build_mac.sh` → `dist/LuckyTwitch.app` and a zip.
  Install Python from python.org first (the system Python has an old Tk).

## Build both automatically
Push this folder to GitHub and run the **Build LuckyTwitch** workflow (Actions tab).
It produces a Windows installer (LuckyTwitch-Setup.exe) plus macOS Apple Silicon and Intel .dmg files as downloadable artifacts.

## macOS first launch
The app is ad-hoc signed, not notarized. First time: right-click the app → **Open** → **Open**
(or System Settings → Privacy & Security → *Open Anyway*).
Windows may show a SmartScreen "unknown publisher" warning: *More info → Run anyway*.

## Notes
- ffmpeg builds used are GPL: fine for personal use; follow GPL terms if you redistribute.
- Because tools are downloaded, the app needs internet on first run.

## Twitch login (clips)
Clips need a Twitch session. In the app, press **Twitch API…** → **Sign in with Twitch**: it shows a code and opens
twitch.tv/activate (Device Code Flow, a *public* Twitch app, no client secret). Users do not need a developer account.
The tokens are stored in `config.json` in the user data folder and refreshed automatically.
Advanced users can still enter their own Client ID / Secret there.
