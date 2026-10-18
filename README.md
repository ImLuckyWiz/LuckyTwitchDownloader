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

### Premiere Pro panels: colored markers and the whole edit (optional)

The `.markers.xml` above is limited by what Premiere's XML import understands: no marker colors, and it brings in a separate sequence. For more, tick **Options → Chapter details → Also export a .markers.json for the LuckyTwitch Premiere plugin**. Each part (or the full VOD) then gets a `.markers.json` next to it, and a Premiere Pro panel imports it as colored markers: game changes in one color, clips colored by their views, with the creator and link in the comment. It is independent of the XML option, so you can use either or both. The game markers option applies to both files. There are **two panels**, both read the same file, and both are on the release page (see [`docs/markers-format.md`](docs/markers-format.md) for the file format):

- **UXP panel** ([`premiere-plugin/`](premiere-plugin), `LuckyTwitch-Premiere-Plugin.ccx`): the easy one. Double-click the `.ccx` to install it with Creative Cloud. Imports the markers (on the clip or on the sequence) and cuts and deletes on any timeline, also one you already trimmed. See [`premiere-plugin/README.md`](premiere-plugin/README.md).
- **CEP panel** ([`premiere-plugin-cep/`](premiere-plugin-cep), `LuckyTwitch-Premiere-Plugin-CEP.zip`): the whole edit in one button, with the real razor. It adds the markers, cuts around every clip (with padding), deletes the gaps, links video and audio again, and checks the whole result against the plan. It wants a fresh sequence with the video alone on V1/A1, and its installer script switches on Adobe's "allow unsigned panels" flag. See [`premiere-plugin-cep/README.md`](premiere-plugin-cep/README.md).

You can install both; they do not get in each other's way.

### Muted audio (Twitch VODs)

Twitch silences copyrighted audio in a VOD. When you press **Get info** the app reads which stretches were silenced (from the VOD's playlist; it is one extra small request, and if it fails you just see nothing) and shows them:

- **Plan tab → Timeline:** a thin red line along the bottom of the game bars, a line under the buttons saying how many stretches and how much time (`25 stretches · 1:54:00 silenced by Twitch`), and a hover note on the red parts. The **Show muted** switch hides the red line; cuts also snap to the edges of muted stretches while it is on. Zoom in to see the shorter ones clearly.
- **Plan tab → part list:** each part says how much of it is muted (`Part 2: 1:30:00 → 2:30:00 (1:00:00) · 0:24:00 muted`), and the line at the bottom adds up the total.
- **Premiere Pro:** tick **Options → Premiere Pro → Muted audio** (with the plugin `.markers.json` option on) and each `.markers.json` also lists the muted stretches of that part as `muted` markers. The plugin chooses their color. See [`docs/markers-format.md`](docs/markers-format.md).

Twitch silences whole segments, so a red stretch can be a little longer than the song itself; it is exactly what is silent in the downloaded file.

### Chat download (optional, Twitch VODs only)

In **Options → Chat**, tick *Also download the chat of each part*. The first time, the app downloads [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader) (MIT license, pinned to one tested version) into the tools folder. Each part then gets a chat file next to it, `name.chat.json` (or `.txt` / `.html`), covering exactly the stretch of the VOD that the part covers. Notes:

- Inside the `.json`, message times count from the **start of the VOD**, not from the start of the part. The file's `start` and `end` say which stretch it covers.
- Chat times are whole seconds, so expect up to a second of difference against the video.
- If the chat cannot be downloaded (deleted VOD, no internet...), the video is still downloaded and the log says why.
- *Embed emotes and badges* makes the file bigger but lets it render offline.

### Open a VOD from a link (web pages and other programs)

A web page, a document or another program can offer a `luckytwitch://` link. Clicking it opens the app (or brings the open window to the front) with the VOD and the cut points already filled in on the **Plan** tab, and reads the VOD for you. A link only fills in the form: it never adds to the queue and never starts a download, so you still check the cut points and press the button yourself.

- **Windows:** the installer has an option for it, ticked by default. If you use the portable folder, or run from source, press **Options → Tools → Links from web pages → Set up links**.
- **macOS:** it works once the app is in Applications. If a link does nothing, open LuckyTwitch from Applications once and try again.
- Your browser may ask whether to open LuckyTwitch the first time.

Making a page that offers such a link? The format is in [`docs/link-format.md`](docs/link-format.md).

## Where things are stored

| What | Windows | macOS |
| --- | --- | --- |
| Settings, Twitch login (`config.json`) | `%LOCALAPPDATA%\LuckyTwitch` | `~/Library/Application Support/LuckyTwitch` |
| yt-dlp and ffmpeg | `...\LuckyTwitch\tools` | `.../LuckyTwitch/tools` |
| Downloads (default) | `Downloads\LuckyTwitch` | `~/Downloads/LuckyTwitch` |

The data folder also holds a small `links` folder and a `running.beat` file: they are how a second launch (a clicked link) hands its link to the window that is already open.

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
weblink.py                  luckytwitch:// links: reading them, handing them to the open window, registering the scheme
ui/                         UI pieces split out of the app (plan_tab.py, timeline.py, common.py: colours and fonts)
tests/                      pytest suite
premiere-plugin/            the Premiere Pro panel (UXP) that reads the .markers.json (JavaScript, own tests)
premiere-plugin-cep/        the second Premiere Pro panel (CEP): same file, edits the whole timeline (JavaScript, own tests)
docs/                       file format notes (markers-format.md, link-format.md)
```

Run the tests:

```
pip install -r requirements-dev.txt
python -m pytest
```

The two Premiere panels have their own tests (`cd premiere-plugin && npm test`, `cd premiere-plugin-cep && npm test`, Node 20+, no dependencies; the CEP tests also check that its `markers-core.js` is exactly the UXP one). The engine tests need nothing else. The GUI tests open a real (hidden) Tk window and are skipped when there is no display; on a headless Linux machine run `xvfb-run -a python -m pytest`.

## Credits

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) downloads the videos (Unlicense).
- [FFmpeg](https://ffmpeg.org) cuts them (builds from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds) on Windows, static builds on macOS).
- [TwitchDownloader](https://github.com/lay295/TwitchDownloader) by lay295 and contributors downloads the chat (MIT). It is downloaded on demand, not bundled.

LuckyTwitch Downloader is not affiliated with Twitch Interactive, Inc., TwitchDownloader or yt-dlp.

## Notes

- The ffmpeg builds the app downloads are GPL. That is fine for personal use; follow the GPL terms if you redistribute them.
- yt-dlp breaks now and then when Twitch changes things. The app updates it on launch, so restarting it is usually enough.
