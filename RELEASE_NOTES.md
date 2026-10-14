## v1.6.0

### Added
- **Chat download (Twitch VODs).** In Options → Chat, tick *Also download the chat of each part*. Each part gets a chat file next to it (`name.chat.json`, or `.txt` / `.html`) that covers exactly the stretch of the VOD the part covers, using the real start and end of the file. *Embed emotes and badges* makes the file bigger but lets it render offline.
- The first time you use it, the app downloads **TwitchDownloaderCLI** (version 1.56.5) into the tools folder, the same way it does with yt-dlp and ffmpeg. Tools shows its status. If you already have a copy next to the app or on your PATH, that one is used.
- **Game markers for Premiere Pro.** In Options → Chapter details, tick *Also mark the game / category changes*. The `.markers.xml` next to each part (or the full VOD) then gets one marker per game, named `GAME: <game>`, spanning the whole stretch, for example `GAME: Just Chatting` from 0:00:00 to 1:00:00 and then `GAME: Resident Evil 2`. For a part, only the games inside it are marked, with times relative to the part. It works with or without the clip markers; when both are on they share the same file. The games are the same ones the Timeline shows as colored bars.

### Good to know
- **Chat times count from the start of the VOD**, not from the start of the part (this is how the `.json` is written). The `start` and `end` inside the file say which stretch it covers. Chat times are whole seconds, so expect up to a second of difference against the video.
- If the chat cannot be downloaded (deleted VOD, no internet, GitHub unreachable), the video is still downloaded and the log says why. A cancelled or failed chat download leaves no empty file behind.
- Chat is skipped for single clips and for links that are not Twitch VODs.
- Premiere's XML import has no marker color, so the `GAME:` prefix is what tells the game markers apart from the clip markers.
- Game markers are off by default, and so is chat, so nothing changes for existing setups.
- TwitchDownloader is MIT licensed and is downloaded on demand, not bundled. See Credits in the README.
