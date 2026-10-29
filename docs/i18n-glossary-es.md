# Spanish style guide and glossary (LuckyTwitch)

Used by everyone who edits `locale/es/LC_MESSAGES/luckytwitch.po` (by hand, with Poedit, or with an AI assistant) and
checked by `python tools/i18n.py check` (the tables below are read by the tool, keep the format).

## Style

* Neutral Latin American Spanish, informal **tú** (decided 2026-10-29; not *vos*, not *usted*): "Reinicia", "Presiona".
* Sentence case. Same punctuation as the English source: same final `.` / `:` / `!` / `?`, same ellipsis `…` (the single
  character, never three dots), same `&` accelerators and the same «guillemets» as the English text.
* Spanish inverted marks are added where Spanish needs them (`¿…?`, `¡…!`); the checker only compares the final mark.
* Keep placeholders exactly: `{user}`, `{n}`, `{version}`. They may move inside the sentence but never change.
* Spanish is 20 to 30% longer than English: prefer the shorter word when two are equally correct, and check the layout
  at the minimum window size (900x560).
* Never translate: tool names, naming-template tokens (`{streamer}`, `{stream_date}`), setting keys, the
  `luckytwitch://` scheme, file extensions, raw output of yt-dlp / ffmpeg / TwitchDownloaderCLI.

Keep as-is: `VOD`, `clip`, `yt-dlp`, `ffmpeg`, `TwitchDownloaderCLI`, `Premiere Pro`, `Twitch`, `MP4`, `MKV`, `AppImage`

## Glossary

When the English message contains the term on the left, the Spanish message must contain one of the words on the
right (accents and capitals do not matter). The list is read by the checker; add a row when you settle a new term.

| English | Spanish | Note |
|---|---|---|
| queue | cola | "Start queue" = "Iniciar cola" |
| part | parte | one piece of a split VOD |
| chapter | capítulo | |
| marker | marcador | Premiere Pro markers |
| muted | silenciado | |
| chat overlay | superposición de chat | |
| watch list | lista de seguimiento | |
| history | historial | |
| strategy | estrategia | |
| quality | calidad | |
| split | dividir | verb |
| cut point | punto de corte | |
| settings | ajustes / opciones | the tab itself stays "Opciones" |

## Words that are the same in both languages

Some short UI words are identical in Spanish ("Plan", "Chat", "Clips", "Streamer", "Premiere Pro"). They are listed
under `identical_ok` in `tools/i18n_baseline.json`; anything else that equals its English text fails the check.
