# Settings keys

Every key in `DEFAULTS` of `luckytwitch_downloader.py` (v1.16.0). **These names stay identical in the Qt app** so existing `luckytwitch_settings.json` files still load.

How the tkinter app handles them (behaviour to keep):

- `load_settings()` returns `DEFAULTS` overlaid with the saved keys that exist in `DEFAULTS`. Unknown saved keys are dropped; a missing or broken file gives the defaults.
- `App.var(name)` makes a `BooleanVar` if the default is a `bool`, otherwise a `StringVar`. So **every numeric setting is stored as a string** (`"60"`, `"8"`), and every on/off setting as a JSON boolean.
- `save_settings()` writes `{key: var.get()}` for every var created, as indented JSON (`json.dumps(data, indent=2)`), and silently ignores `OSError`.
- Numbers are parsed when used (`App.num`): invalid text gives the fallback value, it does not raise.
- File: `SETTINGS_PATH = DATA_DIR / "luckytwitch_settings.json"`. `DATA_DIR` is the app folder when running from source and `user_data_dir()` when frozen.

| Key | Type in JSON | Default | Where it is edited |
| --- | --- | --- | --- |
| `out_dir` | string | `Downloads/LuckyTwitch` under the home folder when frozen, otherwise `<app folder>/downloads` | Options > Output |
| `container` | string | `"mp4"` | Options > Output |
| `strategy` | string | `"Auto"` | Options > Cuts |
| `threshold` | string | `"60"` | Options > Cuts |
| `exact` | bool | `False` | Options > Cuts |
| `keep_full` | bool | `False` | Options > Cuts |
| `threads` | string | `"8"` | Options > Output |
| `name_template` | string | `"{streamer} - {date} - {id} - part{n}"` | Options > Output |
| `chapters` | bool | `False` | Options > Chapters (also read by Plan tab) |
| `min_views` | string | `"0"` | Plan tab (clip filter) |
| `min_duration` | string | `"0"` | Plan tab (clip filter) |
| `top_n` | string | `"0"` | Plan tab (clip filter) |
| `pad_before` | string | `"3"` | Plan tab (clip filter) |
| `pad_after` | string | `"0"` | Options > Chapters (read by build_filter) |
| `title_tpl` | string | `"{title} ({creator}, {views} views)"` | Options > Chapters |
| `gap_title` | string | `"Stream"` | Options > Chapters |
| `sidecar` | bool | `False` | Options > Premiere |
| `premiere_xml` | bool | `False` | Options > Premiere (also read by Plan tab) |
| `premiere_plugin` | bool | `False` | Options > Premiere (also read by Plan tab) |
| `game_markers` | bool | `False` | Options > Premiere |
| `muted_markers` | bool | `False` | Options > Premiere |
| `chat` | bool | `False` | Options > Chat |
| `chat_format` | string | `"json"` | Options > Chat |
| `chat_embed` | bool | `False` | Options > Chat |
| `chat_render` | bool | `False` | Options > Chat |
| `chat_render_mode` | string | `"Transparent · Animation (.mov, small)"` | Options > Chat |
| `chat_render_look` | string | `"Outlined text, nothing behind"` | Options > Chat |
| `chat_render_width` | string | `"400"` | Options > Chat |
| `chat_render_height` | string | `"0"` | Options > Chat |
| `chat_render_font_size` | string | `"18"` | Options > Chat |
| `chat_render_fps` | string | `"Like the video"` | Options > Chat |
| `chat_render_smooth` | bool | `False` | Options > Chat |
| `subfolders` | bool | `True` | Options > Output |
| `folder_template` | string | `"{date} - {title} - {id}"` | Options > Output |
| `clip_name_template` | string | `"{clip_title}"` | Options > Clips |
| `clip_pad_before` | string | `"3"` | Options > Clips |
| `clip_pad_after` | string | `"3"` | Options > Clips |
| `auto_update` | bool | `True` | Options > Tools |

38 keys: 14 boolean, 24 string.

Other files in the data folder that the Qt app must keep reading and writing the same way (not part of `DEFAULTS`):

- `config.json` (`CONFIG_PATH`): Twitch credentials and sign-in tokens (`client_id`, `client_secret`, `access_token`, `refresh_token`).
- `luckytwitch_recent.json` (`RECENT_PATH`): list of `{id, login, name}`, most recent first, capped at `MAX_RECENT`.
- `links/` and `running.beat`: the hand-off to a second launch (see `weblink.py`).
