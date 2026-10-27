# Update Detection Plan

This document describes how **LuckyTwitch Downloader** will find out that a newer version exists on GitHub, tell the person (an advice, not an interruption), and give them a button to update.

Source of truth for versions: <https://github.com/ImLuckyWiz/LuckyTwitchDownloader/releases>

---

## 1. Executive Summary & Design Principles

* **Purpose:** Today nobody learns about a new release unless they visit GitHub. The app should notice a newer stable release by itself, say so once, keep a small reminder visible, and offer a one-click path to the update.
* **Never in the way:** An automatic check is silent when it fails (offline, rate limit, bad JSON) and never opens a modal. Only a manual **Check now** reports "up to date" or an error.
* **Never during work:** Nothing installs while a queue job, the tools setup or a saved-chat overlay is running.
* **Honest per platform:** Windows can update in place (the installer is per-user, no admin rights). macOS is ad-hoc signed and not notarized, so it opens the right DMG instead of replacing itself. From source it only links to the release page.
* **Opt-out:** One switch in Options. Default on. The only request is an anonymous `GET` to `api.github.com`.
* **Reuse what exists:** Bridge signals, background runner threads, toasts, the status-bar pill, the Options cards, the engine's download helper. No new dependency.

---

## 2. What the Project Already Has (Findings)

| Area | Finding | Consequence |
|---|---|---|
| App version | `core/paths.py` reads `version.txt` (`BUNDLED_VERSION`) only when frozen. From source it is `""`. `build_windows.bat` / `build_mac.sh` write the tag into it. | A release build knows its own tag (`v2.1.1`). Source runs have no version, so they skip the check. |
| CI default version | `build.yml` passes `1.0` to the build scripts when the ref is not a tag (push builds, manual runs). | `1.0` must count as a **dev build**: no check. A release build always looks like `vMAJOR.MINOR.PATCH`. |
| Pre-releases | Tags with `-` (for example `v0.0.1-alpha.1`) are published with `prerelease: true` and `make_latest: false`, and use their own data folder and installer id. | `/releases/latest` never returns a pre-release, which is what stable users want. |
| Release body | The release workflow publishes the matching `## vX.Y.Z` section of `RELEASE_NOTES.md` as the body, and fails the build if the first line is not the tag. | The update dialog can show real release notes. |
| Asset names | Windows `LuckyTwitch-Setup.exe`; macOS `LuckyTwitch-macos-arm64.dmg` and `LuckyTwitch-macos-x86_64.dmg`; plus the plugin files. | The updater depends on these names. They become a **contract** (section 8). |
| Existing "update" setting | `auto_update` (Options > Tools, "Check for yt-dlp updates on startup") only updates **yt-dlp**. | Name clash. The new setting is called `check_app_updates` and its text says "LuckyTwitch". |
| Installer | `installer.iss`: per-user (`PrivilegesRequired=lowest`), same `AppId` on every version, so a new Setup upgrades in place. `[Run]` relaunch is `skipifsilent`. | A silent install works without UAC, but needs a relaunch entry (section 6). |
| macOS | `codesign --force --deep --sign -` (ad-hoc), no notarization. | No safe self-replace. Browser download only. |
| Existing HTTP | `luckytwitch_engine._http_get` fixes `timeout=30` itself, so a caller cannot pass `timeout=`. yt-dlp's latest tag is read from a redirect to avoid the API rate limit. | The updater makes its own short-timeout `requests.get` with the engine's `USER_AGENT`, and falls back to the redirect trick on 403/429. |
| UI parts | `qt_ui/notify.py` toasts accept an `action=(label, callable)`. `main_window` has an `activity_pill` (status bar). `shell.ShortcutsDialog` and `twitch_dialog.py` are custom dialogs. Options cards use `_card`, `add_row`, `_register_setting`, `_switch`. | All four UI pieces below are small additions, not new systems. |
| Published vs. repo | GitHub's **Latest** is `v2.1.1`; `RELEASE_NOTES.md` already starts at `v2.2.0` (unreleased). | An installed build can only learn about updates **if it already contains this feature**. The feature ships in a normal release (see section 9). |

---

## 3. Version Rules

1. **Own version:** `paths.BUNDLED_VERSION`. Valid only if it matches `^v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$`. Anything else (`""`, `1.0`, a branch build) = dev build, no automatic check.
2. **Remote version:** the `tag_name` of the newest **stable** release (`GET /repos/ImLuckyWiz/LuckyTwitchDownloader/releases/latest`).
3. **Compare** as tuples of integers (`v2.10.0 > v2.9.0`). A pre-release is lower than the same number without a suffix (`v2.0.0-beta.1 < v2.0.0`).
4. **Stable builds** ignore pre-releases. **Beta builds** (own version has `-`) also look at `GET /releases?per_page=10` and take the highest version including pre-releases (Phase U5, optional).
5. Same or lower than ours = up to date. Drafts are never returned by the unauthenticated API.

---

## 4. Architecture

```
luckytwitch_qt.main ──(3 s after window.show, only if frozen + setting on + 24 h passed)──► window.start_update_check()
                                                                                              │
                              qt_ui/background_jobs.UpdateCheckRunner (daemon thread, like ToolsRunner)
                                                                                              │
                                           core/updates.check_latest()  ──►  Bridge.update_checked(object)
                                                                                              │  (GUI thread)
                                   MainWindow.on_update_checked ─► state file ─► toast (once) + status-bar pill + Options card
```

### New and changed files

| File | Change |
|---|---|
| `core/updates.py` (new, no Qt) | `parse_version`, `is_newer`, `fetch_latest()` (API, redirect fallback, 8 s timeout), `pick_asset(release, platform, machine)`, `UpdateInfo` dataclass (`tag`, `notes`, `page_url`, `asset_name`, `asset_url`, `asset_size`, `sha256`), `should_check(state, now)`, state load/save, `download_installer(ctx, info, dest)`, `verify_download(...)`. |
| `core/paths.py` | `UPDATE_STATE_PATH = DATA_DIR / "luckytwitch_update.json"`. |
| `core/settings.py` | `"check_app_updates": True` in `DEFAULTS`. Older files without it load the default. If a test or doc pins the number of keys, update it. |
| `qt_ui/bridge.py` | New signal `update_checked = Signal(object, str)` (an `UpdateInfo` or `None`, plus an error text, `""` when fine). The installer download reuses the existing `progress` signal. Add the new kind to `KINDS`. |
| `qt_ui/background_jobs.py` | `UpdateCheckRunner` and `UpdateDownloadRunner` (same shape as `ToolsRunner`: one daemon thread, report only through the Bridge, `Cancelled` supported). |
| `qt_ui/update_dialog.py` (new) | The "Update available" dialog (section 5). |
| `qt_ui/main_window.py` | `start_update_check(force=False)`, `on_update_checked`, `update_pill` next to `activity_pill`, `open_update_dialog`, `install_update_now`, guards (queue/tools/chat busy). |
| `qt_ui/tabs/options.py` | New "LuckyTwitch updates" card in the Tools section (switch, version/last-checked row, **Check now**). |
| `luckytwitch_qt.py` | One call after `window.start_tools_setup()`, delayed with `QTimer.singleShot(3000, ...)` so it never competes with the tools download. |
| `installer.iss` | Relaunch entry for silent upgrades (section 6). |
| `.github/workflows/build.yml` | `SHA256SUMS.txt` in the release, asset-name check (section 8). |
| `tests/conftest.py` | Add `("UPDATE_STATE_PATH", "luckytwitch_update.json")` to the paths that Qt tests redirect to `tmp_path`. |

### State file (`luckytwitch_update.json`)

```json
{
  "last_check": "2026-10-27T14:02:11Z",
  "latest_tag": "v2.3.0",
  "notified_tag": "v2.3.0",
  "skipped_tag": "",
  "cached": { "...UpdateInfo fields..." },
  "installer_path": ""
}
```

It is separate from `luckytwitch_settings.json` (preferences) and `luckytwitch_ui.json` (layout), for the same reason `ui_state` is separate. `cached` lets the pill appear at the next launch without a network call. A cache is dropped when its tag is not newer than the running version (the person updated by hand).

### Throttle and failure rules

* Automatic check at most once per 24 h; **Check now** ignores the throttle.
* Timeout 8 s. Any exception becomes `error` text and a log line (`Updates: could not check (offline)`), never a dialog.
* HTTP 403 or 429 from the API: read the tag from the `/releases/latest` redirect instead (notes and assets are then unknown, so the dialog only offers **Release page**).
* Malformed JSON, missing `tag_name`, unparsable tag: treated as "no information".

---

## 5. UI: the Advice and the Button

### 5.1 Toast (the advice, shown once per new version)

`notify.info(window, "Update available", "LuckyTwitch v2.3.0 is out (you have v2.1.1).", action=("View update", window.open_update_dialog))` with `duration_ms=12000`, longer than the default 4 s because it is an advice.

It is shown only when the tag differs from `notified_tag`, then `notified_tag` is saved. Skipped versions never toast.

### 5.2 Status-bar pill (the persistent reminder)

A pill beside `activity_pill`, same `variant="pill"` style, hidden when up to date:

```
[ ● Update available · v2.3.0 ]            Ready.
```

Click opens the dialog. Tooltip: "A new version of LuckyTwitch is available." Fades in with `animate_opacity` like the activity pill. Hidden for a skipped version.

### 5.3 Update dialog (the button)

```
+--------------------------------------------------------------+
|  Update available                                            |
|  LuckyTwitch v2.3.0   (you have v2.1.1)                      |
|  ----------------------------------------------------------  |
|  What's new                                                  |
|  • Stream quality selector …                                 |
|  • …                                              [scrolls]  |
|                                                              |
|  Your settings, Twitch login and tools are kept.             |
|                                                              |
|  [ Update now ]  [ Release page ]  [ Later ]  [ Skip v2.3.0 ]|
+--------------------------------------------------------------+
```

* **Update now** (primary): by platform, see section 6. While downloading, the button row becomes a progress bar with **Cancel**.
* **Release page:** `QDesktopServices.openUrl(page_url)`.
* **Later:** closes. The pill stays.
* **Skip this version:** saves `skipped_tag`, hides the pill. A newer tag shows again. **Check now** still shows a skipped version, marked "(skipped)".
* **Notes:** the release body, capped at about 2,500 characters with "Read the full notes on GitHub". Markdown images and raw HTML are stripped first (the v2.0.0 body embeds images that would not load). Links open in the browser only when they are `https://github.com/...`.
* Built like `ShortcutsDialog`/`TwitchDialog`, on `qt_ui.motion` tokens: no animation when reduced motion is on or under pytest.

### 5.4 Options > Tools > "LuckyTwitch updates" card

| Row | Control |
|---|---|
| Check for new versions of LuckyTwitch | switch bound to `check_app_updates` (registered with `_register_setting`, so search and the changed-from-default marker work) |
| Version | muted label: `v2.1.1 · last checked today 14:02` (dev build: `Development build, updates are not checked`) |
| Check now | button. Result as toast: "You're up to date (v2.1.1)." / opens the dialog / "Could not check: offline." |

---

## 6. What "Update now" Does

| Platform | Behaviour |
|---|---|
| **Windows, installed with Setup** (a `unins000.exe` sits next to `LuckyTwitch.exe`) | Phase U3: download `LuckyTwitch-Setup.exe`, verify, confirm, run it silently, close, reopen the new version. |
| **Windows, anything else** (no uninstaller next to the exe) | Opens the asset URL / release page. |
| **macOS** | Opens the DMG for this machine (`platform.machine()` → `arm64` or `x86_64`) in the browser. The person drags it to Applications, as today. No self-replace. |
| **From source / dev build** | Link to the release page only. (The check itself is off.) |

### Windows silent upgrade, step by step

1. Block with a clear message if `tab_queue.runner.is_running()`, `tools_busy` or `saved_chat_busy`, the same guard `update_tools_now` already uses.
2. Download to `%TEMP%\LuckyTwitch-update\LuckyTwitch-Setup-v2.3.0.exe` with the engine's download helper (progress goes to the dialog bar; **Cancel** raises `Cancelled` and deletes the partial file).
3. **Verify** (section 7). Mismatch: delete the file, show "The download did not pass the integrity check", offer **Release page**.
4. Confirm: "LuckyTwitch will close, update and reopen. Settings, Twitch login and tools are kept. [Install and restart] [Cancel]".
5. Start the installer detached, then close the window (so `closeEvent` saves settings and removes the heartbeat file):
   `LuckyTwitch-Setup-v2.3.0.exe /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELAUNCH=1`
   (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, so the installer outlives the app.)
6. `installer.iss`: add `CloseApplications=yes` to `[Setup]` and a second `[Run]` entry that starts `{app}\LuckyTwitch.exe` with `Flags: nowait` and `Check: IsRelaunch` (reads `{param:RELAUNCH|0}`). The existing `postinstall skipifsilent` entry stays for normal installs. Inno keeps the previously chosen tasks (desktop icon, `luckytwitch://` links) on an in-place upgrade; verify on Windows.
7. Next start: delete the old `LuckyTwitch-update` temp folder (`installer_path` in the state file).
8. If starting the installer raises `OSError`: toast "Could not start the installer" and open the release page.

---

## 7. Security Considerations

The app would download and **run** an executable, so this part is not optional polish.

* **Source allow-list:** the asset URL must start with `https://github.com/ImLuckyWiz/LuckyTwitchDownloader/releases/download/`. Redirects to GitHub's own asset hosts are followed by `requests`; nothing else is accepted. HTTPS only.
* **Integrity:** compare size with the API's `size`, and SHA-256 with the asset `digest` when the API provides one, otherwise with `SHA256SUMS.txt` from the same release (section 8). **No hash available = no silent install**: fall back to the release page.
* **No SmartScreen prompt:** a file downloaded by the app carries no "Mark of the Web", so Windows will not warn the way it does for a browser download. That makes the hash check the only gate; it must never be skipped silently.
* **No code signing today.** Authenticode signing is out of scope; if it is added later, verify the signature before running.
* **Privacy:** one anonymous `GET` per day with the existing `User-Agent`. No settings, paths or identifiers are sent. State this in `README.md` under a short "Update check" note, and keep the opt-out switch.
* **Untrusted text:** release notes are data. They are only displayed (stripped Markdown), never executed or used to build a command.

---

## 8. Release Workflow Changes (`.github/workflows/build.yml`)

1. **Hashes:** in the `release` job, before `softprops/action-gh-release`, generate `SHA256SUMS.txt` for `release/*.exe` and `release/*.dmg` and add it to `files:`.
2. **Asset-name contract:** a step that fails the release if `LuckyTwitch-Setup.exe`, `LuckyTwitch-macos-arm64.dmg` or `LuckyTwitch-macos-x86_64.dmg` is missing. Add a comment in `installer.iss` and `build_mac.sh` that `core/updates.py` depends on these names.
3. Nothing else changes: tag format `vX.Y.Z`, notes-match-tag check and `make_latest` logic already give the updater what it needs.

---

## 9. Phases

Following the project's habit of one phase per session, each with release notes.

| Phase | Scope | Result |
|---|---|---|
| **U1: Core** | `core/updates.py`, `paths.UPDATE_STATE_PATH`, setting `check_app_updates`, conftest path, unit tests with a fake HTTP layer. | Pure logic, fully tested, no UI. |
| **U2: Advice + button (browser)** | Bridge signal, `UpdateCheckRunner`, toast, status-bar pill, dialog, Options card, startup hook. **Update now** opens the release page / DMG. | Usable on every platform. Safe to ship first. |
| **U3: Windows one-click** | `UpdateDownloadRunner`, verify, silent installer launch, `installer.iss` relaunch entry, `SHA256SUMS.txt` in the release workflow. | In-place update on Windows. Needs the Windows hands-on check. |
| **U4: Docs and notes** | README "Update check" note, `RELEASE_NOTES.md` entry, this plan's checklist ticked. | Shipped and documented. |
| **U5 (optional)** | Beta channel (pre-releases for hyphen builds), macOS auto-replace only if notarization is ever added. | Not needed for the first release. |

**First-release caveat:** only builds that contain U2 can detect anything. Ship U2 (and ideally U3) in the next published version, so every release after it is discoverable. A build with the feature can be tested against the real API by temporarily installing an older tag number into `version.txt` (or with a test environment variable that overrides the own version), before it is published.

---

## 10. Test Plan

Same conventions as the existing suite (`tests/test_*.py`, Qt tests named `test_qt_*.py` on the offscreen platform, the HTTP layer replaced by fakes, nothing touches the network).

**`tests/test_updates.py` (pure)**
* Version parsing and ordering: `v2.1.1 < v2.2.0`, `v2.10.0 > v2.9.0`, `v2.0.0-beta.1 < v2.0.0`, `1.0`, `""`, `garbage`, a tag without `v`.
* A stable build ignores a newer pre-release; a dev build does not check.
* Asset choice per platform and machine (`arm64`, `x86_64`, Windows); a missing asset gives release-page-only.
* Throttle: not before 24 h, forced check ignores it, a clock set back does not break it.
* Failures are silent: timeout, 403 then redirect fallback, 429, malformed JSON, no `tag_name`.
* A cached release that is no longer newer is dropped.
* Download verification: wrong size, wrong hash, no hash (refuses silent install), URL outside the allow-list.

**`tests/test_qt_update_dialog.py`**
* Shows tag, current version and stripped notes (images and HTML removed, length capped).
* **Skip** saves `skipped_tag` and hides the pill; **Later** keeps it; **Release page** opens the URL (patched `QDesktopServices`).
* Progress state and **Cancel** delete the partial file.

**Additions to existing files**
* `test_qt_main_window.py`: update found → toast with action and pill; same tag again → no second toast; setting off → no thread started; dev build → no check; update refused while the queue runs.
* `test_qt_options_tab.py`: the card, the switch (changed marker), **Check now** messages.
* `test_qt_bridge.py`: the new signal is delivered on the GUI thread.
* `test_qt_packaging.py` / settings tests: the key list or key count if they pin it.

**Manual Windows checks (U3)**: upgrade over an installed older build; settings, login and tools survive; the app relaunches; desktop icon and `luckytwitch://` links keep their state; a running queue blocks the update; a corrupted download is rejected.

---

## 11. Open Decisions

1. **Default on or off?** Plan assumes on (same as the yt-dlp check, one anonymous request a day, documented, with an off switch).
2. **Ship U2 alone first, or U2 + U3 together?** U2 alone is lowest risk; U3 needs your Windows verification.
3. **Release notes in the dialog:** plain stripped text (planned) or rendered Markdown with the image/HTML stripping kept.
4. **Toast frequency:** once per new version (planned) or once per launch until updated.

---

## 12. Verification Checklist

- [ ] `core/updates.py` fully unit-tested, no network in the test suite.
- [ ] Dev builds (`""`, `1.0`) and source runs never check automatically.
- [ ] Offline start shows nothing and logs one line.
- [ ] A newer stable release produces one toast, a pill, and a working dialog.
- [ ] Skip, Later, Release page and Check now behave as specified.
- [ ] Windows: silent upgrade keeps settings, Twitch login and tools, and relaunches.
- [ ] No update starts while a queue job, tools setup or chat overlay runs.
- [ ] A bad hash or a URL outside the allow-list never reaches the installer.
- [ ] `SHA256SUMS.txt` and the three asset names are enforced in the release workflow.
- [ ] README note, release notes, and this plan updated.
