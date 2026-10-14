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
2. Write the cut points, for example `0:00 - 30:00 - 1:30:00 - end` (consecutive parts). Use `;` or a new line to skip gaps: `0:00 - 30:00 ; 2:00:00 - end`. Times can be `H:MM:SS`, `MM:SS`, seconds or `1h30m`. Or use the **Timeline** above the text box: click the thumbnails to cut, drag a cut line to move it, right-click it to remove it, click a part to skip it, double-click a game bar to make that game its own part. The mouse wheel zooms, **Undo** takes back the last edit. The text and the timeline always match.
3. Choose the download strategy (**Auto** picks whichever is cheaper: full VOD then split, or only the parts), then start the job.

### Finding a VOD (Search tab)

Instead of pasting a link you can search for a streamer: open the **Search** tab, type a name and press Enter. Pick a channel to see its VODs with thumbnails (past broadcasts, highlights or uploads), then double-click one (or press **Use this VOD**) and it is loaded in the Plan tab. The streamers you open are remembered under **Recent streamers**. Searching needs the Twitch sign-in described below; if you are not signed in, the tab shows a **Sign in…** button.

Other options include exact cuts, file and folder name templates, keeping the full VOD, and a queue of jobs. Cancelling stops everything and keeps the partial download so it can resume.

### Clip chapters (optional)

The Search tab and clip chapters need a Twitch session. The app can build chapters from a VOD's Twitch clips, filtered by views, duration or top N. To sign in:

1. Press **Twitch API…** → **Sign in with Twitch**.
2. A code appears and `twitch.tv/activate` opens in your browser. Enter the code and authorize.

This uses Twitch's Device Code Flow with a public app, so there is no client secret and you do **not** need a Twitch developer account. Advanced users can still enter their own Client ID / Secret in the same window.

### Game markers for Premiere Pro (optional)

In **Options → Chapter details**, tick *Also mark the game / category changes*. Each part (or the full VOD) then gets a `.markers.xml` next to it with one marker per game, named `GAME: <game>` and spanning the whole stretch (for example `GAME: Just Chatting` from 0:00:00 to 1:00:00, then `GAME: Resident Evil 2`). Import it in Premiere with **File → Import**. The game list comes from Twitch through yt-dlp, the same data the Timeline shows as colored bars. It works with or without the clip markers (they share the same file when both are ticked). Premiere's XML import has no marker color, so the `GAME:` prefix is what tells them apart from the clip markers.

### Premiere Pro plugin: colored markers (optional)

The `.markers.xml` above is limited by what Premiere's XML import understands: no marker colors, and it brings in a separate sequence. For more, tick **Options → Chapter details → Also export a .markers.json for the LuckyTwitch Premiere plugin**. Each part (or the full VOD) then gets a `.markers.json` next to it, and the panel in [`premiere-plugin/`](premiere-plugin) imports it as colored markers straight onto your active sequence: game changes in one color, clips colored by their views, with the creator and link in the comment. It is independent of the XML option, so you can use either or both. The game markers option applies to both files. See [`premiere-plugin/README.md`](premiere-plugin/README.md) to install it and [`docs/markers-format.md`](docs/markers-format.md) for the file format.

### Chat download (optional, Twitch VODs only)

In **Options → Chat**, tick *Also download the chat of each part*. The first time, the app downloads [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader) (MIT license, pinned to one tested version) into the tools folder. Each part then gets a chat file next to it, `name.chat.json` (or `.txt` / `.html`), covering exactly the stretch of the VOD that the part covers. Notes:

- Inside the `.json`, message times count from the **start of the VOD**, not from the start of the part. The file's `start` and `end` say which stretch it covers.
- Chat times are whole seconds, so expect up to a second of difference against the video.
- If the chat cannot be downloaded (deleted VOD, no internet...), the video is still downloaded and the log says why.
- *Embed emotes and badges* makes the file bigger but lets it render offline.

## Where things are stored

| What | Windows | macOS |
| --- | --- | --- |
| Settings, Twitch login (`config.json`) | `%LOCALAPPDATA%\LuckyTwitch` | `~/Library/Application Support/LuckyTwitch` |
| yt-dlp and ffmpeg | `...\LuckyTwitch\tools` | `.../LuckyTwitch/tools` |
| Downloads (default) | `Downloads\LuckyTwitch` | `~/Downloads/LuckyTwitch` |

Uninstalling the app leaves this data folder in place; delete it for a clean removal. To reinstall ffmpeg, delete `ffmpeg` and `ffprobe` from the `tools` folder and restart the app.

## Run from source

```
pip install requests pillow
python luckytwitch_downloader.py
```

Python 3.10+ with Tk is required (on macOS use Python from python.org, since the system Python ships an old Tk). When run from source, settings and downloads stay next to the scripts.

## Build it yourself

PyInstaller cannot cross-compile, so build each system on that system.

- **Windows:** run `build_windows.bat [version]` → `dist\LuckyTwitch\LuckyTwitch.exe`, plus `dist\LuckyTwitch-Setup.exe` if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed.
- **macOS:** run `./build_mac.sh` → `dist/LuckyTwitch.app` and `dist/LuckyTwitch-macos-<arch>.dmg`. It also installs the app into Applications on that Mac. The result matches the Mac's chip (Apple Silicon or Intel).

## Development

```
luckytwitch_engine.py       everything that is not GUI (planning, yt-dlp / ffmpeg, chapters)
luckytwitch_downloader.py   the Tk app: window, tabs, queue
ui/                         UI pieces split out of the app (plan_tab.py, timeline.py, common.py: colours and fonts)
tests/                      pytest suite
premiere-plugin/            the Premiere Pro panel that reads the .markers.json (JavaScript, own tests)
docs/                       file format notes (markers-format.md)
```

Run the tests:

```
pip install -r requirements-dev.txt
python -m pytest
```

The plugin has its own tests (`cd premiere-plugin && npm test`, Node 20+, no dependencies). The engine tests need nothing else. The GUI tests open a real (hidden) Tk window and are skipped when there is no display; on a headless Linux machine run `xvfb-run -a python -m pytest`.

## Credits

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) downloads the videos (Unlicense).
- [FFmpeg](https://ffmpeg.org) cuts them (builds from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds) on Windows, static builds on macOS).
- [TwitchDownloader](https://github.com/lay295/TwitchDownloader) by lay295 and contributors downloads the chat (MIT). It is downloaded on demand, not bundled.

LuckyTwitch Downloader is not affiliated with Twitch Interactive, Inc., TwitchDownloader or yt-dlp.

## Notes

- The ffmpeg builds the app downloads are GPL. That is fine for personal use; follow the GPL terms if you redistribute them.
- yt-dlp breaks now and then when Twitch changes things. The app updates it on launch, so restarting it is usually enough.
