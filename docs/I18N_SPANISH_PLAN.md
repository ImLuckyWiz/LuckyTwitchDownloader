# Spanish Localization Plan (Phase F4b: finish and harden the translation)

Status: **In progress: phases I0, I1, and I2 delivered (see section 8), I3 is next.** Date of analysis: 2026-10-29, repo at v2.9.2.

Decisions taken on 2026-10-29: Spanish uses informal **tú**; the mechanism is **gettext** (`.po`/`.mo`, standard Python `gettext` at runtime, Babel for tooling); translating the Premiere panel is **future work** (phase I10 is deferred and out of scope for now).

v2.9.0 shipped a Spanish catalog and a language picker, but the interface is **partly translated and partly English**. This plan finishes the job and adds the guard rails so it cannot drift again.

---

## 1. Diagnosis (measured on the v2.9.0 sources)

All numbers come from an AST scan of `qt_ui/` and `core/` (analysis only; no project file was changed).

| Finding | Evidence | Consequence |
|---|---|---|
| Catalog is small compared with the UI | `core/i18n.py` has **140** Spanish entries; the scan finds about **470** user-facing English literals in `qt_ui/`, of which about **376 (332 unique) are not in the catalog**. | Most of the Options tab (124 literals), main window (46), timeline (40), Plan tab (34), Search tab (32), shell (30), Twitch dialog (23), update dialog (16), Queue tab (15), welcome setup (15) stay English. |
| Wrapping is manual and incomplete | Only **52** `t("...")` calls use a literal; **88** catalog keys are reached only through variables (tab names, option titles). | Easy to add text without `t()`; no check notices. |
| Composed texts cannot be translated | About 60 f-strings go straight to widgets, e.g. `f"{n} stretch{'es' if n != 1 else ''}"`, `f"Download {n} clip{'s'...}"`, `f"Added {added} clip(s) to the queue."`, `"Job {n}/{total}"`. | Word order and plurals are English-only. |
| Engine messages are English | `core/` has **63** `PlanError`/`EngineError` calls and about **43** `ctx.log(...)` lines that reach dialogs and the log panel. | A Spanish user sees English errors. |
| Fragile live refresh | `shell.py:408` compares the label with the hard-coded Spanish `"Ningún VOD cargado."`; every tab has its own `refresh_language()`; a "restart to apply" notice remains. | Breaks when the Spanish text changes; some widgets never refresh. |
| Qt's own strings | No `QTranslator` is loaded. | Standard buttons (Yes/No/Cancel/Open), line-edit context menus (Cut/Copy/Paste) and file dialogs stay English. |
| Detection is weak | `get_system_language()` reads `LANG`/`LC_ALL`, then the deprecated `locale.getdefaultlocale()` (removed in Python 3.15). The 2.9.0 release notes say it also uses `QLocale`; it does not. | Works by accident on Windows today; breaks on a newer Python. |
| Numbers and dates | e.g. `f"Drive free space: {free_gb:.1f} GB"` always prints a decimal point. | Spanish expects a decimal comma. |
| Other surfaces | Installer (`installer.iss` has no `[Languages]`), README, Linux `.desktop`, Premiere panel (`cep-panel/index.html`, 231 lines, plus JS/JSX), GitHub release notes shown in the update dialog. | "Fully localized" in the README is not true today. |
| No test proves coverage | `tests/test_i18n.py` checks the catalog (placeholders, non-empty) but not the code. | Nothing fails when a string is missed. |

---

## 2. Design decisions

1. **Mechanism: gettext** (decided 2026-10-29, replaces the earlier "keep the dictionary" idea). Reasons: the project may get more languages; `.po` files are the industry standard with ready tools (Poedit, Weblate, Crowdin); plurals are built in (`ngettext` with a `Plural-Forms` rule per language); it works in `core/` and `qt_ui/` alike (Python's stdlib `gettext`, no Qt dependency, no new runtime package). Qt's `.ts`/`.qm` system was rejected for strings because it would not cover `core/` (about 106 engine messages), leaving two systems; Qt's own `qtbase_es.qm` is still loaded for Qt's standard buttons and menus (decision 8).
   The **call sites stay as they are**: `t("English text")` with English as the message ID, so the wrapping work in section 3 is the same. Only `core/i18n.py` changes inside. New helpers: `tn(singular, plural, n)` (ngettext) and `tc(context, text)` (pgettext, for ambiguous words such as the verb and the tab "Plan" or "Open").
2. **Live switching, no restart.** Add a small helper so a widget registers its text once (`bind_text(widget, "setText", "Key", **params)`) and a single `language_changed` signal re-applies every binding. This replaces the per-tab `refresh_language()` code and the hard-coded Spanish comparisons.
3. **Plurals:** one helper `tn("{n} clip", "{n} clips", n)`; catalog entries become `{"one": ..., "other": ...}` for these keys. Spanish uses the same two forms (1 = singular).
4. **Composed texts become parameterised keys** (`t("Added {n} clips to the queue.", n=...)`), never f-strings. Placeholders must be identical in both languages (already tested).
5. **Logic never depends on translated text.** Queue statuses (`"queued"`, `"running…"`, `"done (N files)"`) are compared in code (`it.status == "queued"`); labels must be derived in the view (`status_label`) and never stored translated.
6. **Core stays Qt-free.** `core/i18n.py` is pure Python, so `core/` may call `t()` at the raise/log site. Messages are translated when created; changing the language does not rewrite old log lines.
7. **Numbers/dates** go through one helper based on `QLocale` (decimal comma, date order); time strings like `1:23:45` stay as they are.
8. **Qt standard strings:** load `qtbase_es.qm` with `QTranslator` from PySide6's translations folder, and make sure the Nuitka build bundles it.
9. **Language choice:** picker gets **Auto (system)**, English, Español. Auto uses `QLocale.system()`; the first-run rule becomes "Auto" instead of writing a guessed language.
10. **What stays English on purpose:** yt-dlp/ffmpeg/TwitchDownloaderCLI raw output, tool names, naming-template tokens (`{streamer}` etc.), setting keys, the `luckytwitch://` scheme, `.markers.json` field names, debug logs, GitHub release notes.

### Gettext layout

| Path | Role |
|---|---|
| `locale/luckytwitch.pot` | Template with every message found in the code (generated, committed) |
| `locale/es/LC_MESSAGES/luckytwitch.po` | Spanish translations (edited by hand or with Poedit) |
| `locale/es/LC_MESSAGES/luckytwitch.mo` | Compiled catalog loaded at runtime (see decision D7) |
| `babel.cfg` | Extraction mapping: `qt_ui/`, `core/`, `luckytwitch_qt.py`; keywords `t`, `tn:1,2`, `tc:1c,2` |
| `tools/i18n.py` | Small wrapper with `extract`, `update` (merge new strings into the `.po`), `compile` and `check` |

* **Runtime:** `core/i18n.py` keeps its public API (`t`, `tn`, `tc`, `set_language`, `get_language`, `get_system_language`) and loads the catalog with the standard library `gettext` (`fallback=True`, so English needs no catalog). Switching language swaps the active translation object.
* **Dev only:** Babel goes into `requirements-dev.txt`. The app itself gains no dependency.
* **Migration:** a one-time script turns the 140 entries of `TRANSLATIONS_ES` into `es/LC_MESSAGES/luckytwitch.po`; the dictionary is then deleted and `tests/test_i18n.py` reads the `.po` instead.
* **Adding a language later** = one new `.po` file plus an entry in `SUPPORTED_LANGUAGES`; no code change.

### Spanish style guide (to be saved as `docs/i18n-glossary-es.md` in phase I0)

* Neutral Latin American Spanish, informal **tú** (matches the current catalog: "Reinicia", "Presiona"). **Decided (2026-10-29): tú**, not vos.
* Keep as-is: VOD, clip, yt-dlp, ffmpeg, Premiere Pro, Twitch, MP4/MKV, AppImage.
* Proposed glossary: queue = cola; part = parte; chapter = capítulo; marker = marcador; muted = silenciado; chat overlay = superposición de chat; watch list = lista de seguimiento; history = historial; strategy = estrategia; quality = calidad; split = dividir; cut point = punto de corte; settings = ajustes/opciones (keep "Opciones", already used).
* Sentence case, same punctuation and ellipsis as the English source, same `&` accelerators, keep «guillemets» as in the English text.
* Spanish is 20 to 30% longer: every phase checks truncation (section 5).

---

## 3. Phases

Each phase ends with both test suites green and a tag `i18n-phase-N`. Phases I2 to I8 are ordered by what the user sees first.

| Phase | Scope | Size |
|---|---|---|
| **I0 Gettext migration and guard rails (no visible change)** | Add `babel.cfg`, `tools/i18n.py`, `locale/` layout; convert the 140 existing entries to a `.po`; rewrite `core/i18n.py` on stdlib `gettext` with the same `t()` API plus `tn`/`tc`; adapt `tests/test_i18n.py`. Two checks with a **ratchet baseline** (the current gaps, which may only shrink): (a) **wrapped** messages: after `extract`, no entry in the `.po` may be empty or fuzzy; (b) **unwrapped literals**: an AST scan (same method as this analysis) lists user-facing literals passed to widgets/dialogs without `t()` (about 330 today); a new one fails the test. Catalog tests: no obsolete entries, placeholders equal, `&`/ellipsis/ending punctuation equal, Spanish differs from English unless allow-listed, glossary terms respected. Save the glossary. | M |
| **I1 Infrastructure** | `bind_text` + `language_changed`; locale helper (numbers/dates); `QTranslator` for Qt strings; fix detection with `QLocale` and drop `getdefaultlocale`; **Auto** option; remove hard-coded Spanish comparisons; keep a short "restart" notice only for what really needs it. **Packaging:** the build scripts (`build_windows.bat`, `build_mac.sh`, `build_linux.sh`) bundle `locale/` into the Nuitka build; CI runs `tools/i18n.py check` and a frozen-build smoke test that loads the Spanish catalog. Tests: switching language updates every bound widget without restart (offscreen); detection with mocked locales (`es_UY`, `es-ES`, `en_US`, `C`); `tn` plural forms 0/1/2. Ship as **v2.9.2** (v2.9.1 was hotfix locking English). | M |
| **I2 Shell** | `main_window.py` (46), `shell.py` (30), title bar, toasts, status bar, shortcuts dialog, tray notifications. | S |
| **I3 Plan tab + timeline** | `plan.py` (34), `timeline.py` (40) including context menus and accessible names; all plural/f-string texts. | M |
| **I4 Search + History + Watch list** | `search.py` (32), history dialog, "✓ Downloaded" badge and tooltips (dates via locale helper). | S |
| **I5 Queue tab** | `queue.py` (15), status labels (view only), speed-limit and parallel-jobs texts, log panel messages emitted by the UI. | S |
| **I6 Options** | `options.py` (124): card titles, setting labels, hints, buttons, link/update/tools cards. **Settings search must match both the translated text and the English keywords** so users can find a setting either way. | L |
| **I7 Dialogs and first run** | Twitch sign-in dialog (23), update dialog (16), welcome overlay and setup card, every `info/warning/error` message box (title and body), file-dialog filters. | M |
| **I8 Engine messages** | `core/` `PlanError`/`EngineError` (63), user-visible `ctx.log` (43), job summaries, update/tool errors in `background_jobs.py`. Raw tool output stays English. | M |
| **I9 Installer and docs** | `installer.iss` `[Languages]` (English + Spanish, check the Spanish file ships with the Inno Setup version used by CI); Linux `.desktop` `Name[es]`/`Comment[es]`; `README.es.md`; correct the README wording until I8 is done; a short `docs/TRANSLATING.md` (how to add or update a language with `tools/i18n.py`). | S |
| **I10 Premiere panel (DEFERRED: future work, decided 2026-10-29)** | Panel strings into a small `strings.js` (en/es). Language source: Premiere's UI locale (`CSInterface.getHostEnvironment().appUILocale`), optionally overridden by a new optional `"language"` field in `.markers.json` (additive, documented in `docs/markers-format.md`). Node tests for key parity. Panel version bump. | M |
| **I11 QA** | Pseudo-localization mode (env var or `--lang pseudo`: accented, 30% longer text) to expose missed strings and truncation; screenshot walk of every tab/dialog in Spanish at the minimum window size (900x560); native-speaker review by the owner; `docs/I18N_QA_CHECKLIST.md`. | S |

Release proposal: **v2.9.2** after I0+I1 (little visible change, safer detection), a **v2.10.0-beta.1** after I5 for Spanish testers, final **v2.10.0** after I9 and I11 (I10 is deferred).

---

## 4. Tests

* **Coverage ratchet** (I0): two baselines (empty/fuzzy `.po` entries, and unwrapped literals in UI calls); a new gap fails the test. Both reach zero at I8.
* **Catalog hygiene:** `tools/i18n.py check` in CI: the `.pot` is up to date with the code, the `.po` has no obsolete entries, the committed `.mo` matches the `.po` (if D7 keeps it committed); placeholders, accelerators, ellipsis and trailing punctuation equal; plural entries have all forms the language needs; no leading/trailing space mismatch.
* **"No English left" walk** (offscreen): create every tab and dialog with `language=es`, collect `text()`, `toolTip()`, `placeholderText()`, `accessibleName()` of all widgets and assert none is a key of the English catalog without a Spanish value (allow-list for words that are the same in both languages).
* **Live switch:** en → es → en without restart restores identical text.
* **Plurals and numbers:** 0, 1, 2 items; decimal comma; dates.
* **Layout:** with Spanish, no button/label wider than its parent at 900x560 (`sizeHint` checks) and no clipped text in the collapsed navigation rail.
* **Engine messages:** each `PlanError` path returns Spanish text when the language is `es` and English otherwise.
* **Panel (I10):** key parity between `en` and `es` in Node tests.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Text expands and gets cut off (buttons, rail, table headers) | Layout test at minimum size; shorter Spanish wording in the glossary where needed; tooltips for abbreviations. |
| English text edited later silently loses its translation | The coverage and "dead key" tests fail in CI. |
| Worker threads read the language while the user switches | Language is read-only state per message; switching mid-job only affects new messages (documented). |
| Nuitka build misses `qtbase_es.qm` or the `.mo` files | Both are added to the build scripts as data files; the frozen-build smoke test checks that a Qt standard button and an app string appear in Spanish. If a message is missing from the `.mo`, gettext falls back to English instead of failing. |
| Mixed states during the migration | Each phase translates a whole surface; the ratchet baseline shows what is left. |
| Search in Options breaks with translated labels | Search indexes translated text **and** English keys; test for both. |

---

## 6. Open decisions

* ~~D1~~ **Decided:** gettext (`.po`/`.mo`) with English as the message ID.
* ~~D2~~ **Decided:** informal **tú**.
* **D3** Saved log files and the "Copy details" text: keep English for easier bug reports (proposed) or follow the interface language.
* ~~D4~~ **Decided:** the Premiere panel is future work; I10 stays deferred and the panel remains English for now.
* **D5** Release notes in the update dialog: English only (proposed) or add a Spanish summary line per release.
* **D6** Next language after Spanish (for example Portuguese)? With gettext it is just another `.po`; only the plural rule and the glossary need care.
* ~~D7~~ **Decided (I0):** the compiled `.mo` is committed; `tools/i18n.py check` (and the test suite) fail when it does not match the `.po`, so running from source and building both just work.

---

## 7. Acceptance criteria

1. With the language set to Español, the "no English left" walk finds nothing outside the allow-list, and the coverage baseline is empty.
2. Switching language updates every open window immediately; no restart notice.
3. Qt standard buttons and context menus are Spanish.
4. The installer, README.es.md and the Linux launcher entry are Spanish; the README wording is accurate.
5. Both test suites are green on the CI matrix.

---

## 8. Progress log

### Phase I0 delivered (2026-10-29): gettext migration and guard rails, no visible change

What changed:

* `core/i18n.py` now runs on stdlib `gettext` with the same `t()` API plus `tn()` (plurals), `tc()` (context) and `N_()` (mark for extraction). `TRANSLATIONS_ES` is gone (the engine shim no longer re-exports it). A missing or corrupt catalog falls back to English instead of failing.
* `locale/luckytwitch.pot`, `locale/es/LC_MESSAGES/luckytwitch.po` and the committed `luckytwitch.mo`. The 140 old entries became **139** (the unreachable duplicate `Add & start` was dropped; the code only uses `Add && start`). `.gitattributes` keeps `.po`/`.pot` in LF and `.mo` binary.
* `babel.cfg` and `tools/i18n.py` (`extract`, `update`, `compile`, `check`, `scan`, `baseline`, `status`). Babel is a dev-only dependency (`requirements-dev.txt`).
* `docs/i18n-glossary-es.md`: style guide plus a machine-readable glossary that the checker enforces.
* `tests/test_i18n.py` rewritten: runtime API, catalog hygiene, guard rails tested with synthetic messages, and the ratchets.
* **Pulled forward from I1:** the three build scripts now bundle `locale/` (`--include-data-dir=locale=locale`). Without it a packaged I0 build would silently show English, which would be a regression from v2.9.0. The frozen-build smoke test and the CI step stay in I1 (the test suite already runs the same checks).

How the guard rails work (what a developer sees):

| You do | `check` / the tests say |
|---|---|
| Add a user-facing literal to a widget, dialog, `PlanError` or `ctx.log` without `t()` | fails: wrap it in `t()` (or `N_()` when it is translated later through a variable) |
| Add `t("New text")` | fails until `python tools/i18n.py update` adds it to the `.pot`/`.po` and it is translated, then `compile` |
| Change the English text of a wrapped message | the old entry becomes dead and the new one untranslated: run `update`, move the translation |
| Wrap a literal that was in the baseline | fails with "run `python tools/i18n.py baseline`" (the baseline only shrinks; growth needs `--allow-growth`) |
| Break a placeholder, `&` accelerator, `…`, final punctuation, line break or edge spaces in the `.po` | fails, with the message named |

Ratchet baselines (`tools/i18n_baseline.json`), the starting point for I2 to I8:

* **570 unwrapped user-facing literals** (437 distinct texts in `qt_ui/`, 90 distinct engine messages in `core/`). The numbers are higher than the estimate in section 1 because f-strings and engine messages are counted too. Each phase removes its surface from the baseline with `python tools/i18n.py baseline`; it must reach zero at I8.
* **28 "dead" catalog entries**: translations that exist in the `.po` but whose English text is not in the code yet (for example "Save", "Copy", "Pinned", "Signed in as {user}"). They were written in F4 for screens that never used them. Phases I2 to I8 wire them up or delete them; the baseline may only shrink.
* **0 untranslated** extracted messages.
* 88 catalog keys reach `t()` only through variables or helpers (tab names, option titles, `card.add_row("...")`). `extract` keeps them in the `.pot` when their exact text is a literal in the code, marked `indirect`. New code should use `t()` or `N_()` explicitly.

Not done in I0 on purpose: detection (`getdefaultlocale`, still present and emitting a DeprecationWarning), live switching, `QTranslator`, the Auto option and the CI step belong to I1. No app version was bumped (no visible change); the plan proposes v2.9.1 after I1, tag `i18n-phase-0` for this step.

### Phase I1 delivered (2026-10-30): live switching, Auto, Qt strings, formatting, packaging check (release v2.9.2)

* `qt_ui/i18n_qt.py` is the Qt side: `apply_language(setting)` (the one entry point: sets the language, swaps the Qt translator, re-applies bindings, emits `language_bus().changed`), `bind_text(widget, "setText", "Text", **params)` / `bind(widget, setter, factory)` (weakly held; a widget bound once never needs a `refresh_language` method), and `format_number` / `format_date` / `format_datetime` (use the language being shown, not the OS).
* Detection: `core.i18n.get_system_language()` no longer uses the deprecated `locale.getdefaultlocale` (environment in gettext order, then `locale.getlocale()`); the app uses `QLocale.system().uiLanguages()` (`system_language()`), which also copes with `Spanish_Uruguay` style names. `resolve_language()` turns the saved setting into the language to show.
* **Auto (system)** is a real setting: `UIState.language` defaults to `"auto"`, the picker in Options → Interface has Auto / English / Español, and the saved value is the setting, never the guessed language. Existing files with `en` / `es` keep working.
* Qt's own strings: `locale/qt/qtbase_es.qm` (copied from PySide6, so frozen builds do not depend on where Nuitka puts Qt translations) with PySide6's own folder as fallback; installed and removed with the language (never stacked).
* No restart notice any more: the three "Language changed ... Restart" messages were deleted from the catalog (dead entries: 30 to 27).
* The empty-state line under the command bar no longer compares against a hard-coded Spanish string (`CommandBar.show_no_vod()` remembers what it showed). This also fixed `clear_vod()` and link handling, which put the raw English constant on screen.
* `human_size` and the disk-space label use `format_number` (`1,4 GB` in Spanish).
* Packaging: `--i18n-selftest` (loads the Spanish catalog and Qt's Spanish catalog without opening a window; exit code 0/1). `.github/workflows/build.yml` runs `python tools/i18n.py check` and the self-test against the packaged binary on Windows, macOS and Linux. **These CI steps could not be run where this was written**; the first tag build is their first real run. The macOS step also verifies `resource_path` inside `.app`.
* Not changed on purpose: the per-tab `refresh_language()` methods stay until their tab is migrated (I2 to I7). `QLocale.setDefault` is not called (spin boxes and parsing keep the same behaviour); formatting is explicit through the helpers.

Developer rule from now on: new widget text is either `t(...)` at build time plus a `bind_text` when the widget lives across language changes, or built inside a `refresh_language`/`retranslate` that runs on `language_bus().changed`.


### Phase I2 delivered (2026-10-30): Shell localization (tag i18n-phase-2)

* qt_ui/titlebar.py: Caption buttons (*Minimize*, *Maximize*, *Restore*, *Close*) fully localized with dynamic updates via language_bus().changed.
* qt_ui/shell.py:
  - NavRail: toggle button tooltips, accessible names, and accessible descriptions (Navigate to {tab} tab).
  - CommandBar: placeholder text, inline action button tooltips/accessible descriptions, API account status tooltips (Signed in to Twitch API, etc.), history button tooltip.
  - VodStrip: VOD, ✓ Downloaded badge, Open on Twitch, Clear loaded VOD, and download date tooltip (Downloaded on {date}).
  - ShortcutsDialog: window title, heading, descriptions, and close button localized into natural Latin American Spanish.
* qt_ui/main_window.py: All 55 shell messages wrapped with 	(...):
  - Status line feedback: reading VOD info, loading VOD, link opening, queue finished, tools setup.
  - Toasts and dialogs: clipboard detection (Twitch VOD in clipboard), update notifications (● Update available · {version}), saved chat overlay, job completion, and confirm quit dialog.
* Catalog and baseline:
  - 88 new strings translated into locale/es/LC_MESSAGES/luckytwitch.po following docs/i18n-glossary-es.md.
  - Ratchet baseline unwrapped literals dropped from 570 down to 477 (qt_ui/shell.py, qt_ui/titlebar.py, and qt_ui/main_window.py now have 0 unwrapped literals).
  - All 1,589 tests passing, python tools/i18n.py check passing cleanly with 0 problems.

### Phase I3 delivered (2026-10-30): Plan tab + timeline localization (tag i18n-phase-3)

* `qt_ui/tabs/plan.py`:
  - Visual cards, headers and hints: Onboarding instructions, *Timeline*, *Cut points*, *Clips → chapters*, subtitle hints, and cut formatting hint (`CUT_HINT`).
  - Title row: *Title:*, placeholder *Stream title…*, *Reset*, tooltip *Reset to original Twitch title*.
  - Strategy selector: *Strategy:*, choices *Auto*, *Full VOD + split*, *Only the parts*, coverage badge (*100% of VOD* / *{pct}% of VOD*).
  - Quality row: *Quality:*, *Best available ({quality})*.
  - Clips card & filters: *Add clips as chapters*, filter spinners (*Min views*, *Min duration (s)*, *Top N (0 = all)*, *Lead-in (s)*), selection bar (*Selection:*, *Select all*, *Invert*, *Clear*).
  - Clips table & actions: table headers (*At*, *Views*, *Duration*, *Title*, *Creator*, *Chapter*), *Split at selected clip*, plural-aware button (*Download {n} clip* / *Download {n} clips*).
  - Plan preview & footer: parts summary, strategy descriptions, audio-only and size estimates, *Add to queue*, *Add & start*, dialogs (*Select a clip*, *No VOD*, *No offset*, *Can't split here*).
  - Dynamic retranslation: `refresh_language()` retranslates all card titles, labels, inputs, table headers, preview and clips on language switch.
* `qt_ui/timeline.py`:
  - Zoom & history controls: *Zoom out (−)*, *Zoom in (+)*, *Fit*, *Show the whole VOD (0)*, *Undo*, *Redo* (with tooltips and accessible names).
  - Muted audio: *Show muted*, plural-aware label (*{stretches} · {duration} silenced by Twitch*).
  - Canvas & minimap: accessible names, descriptions, minimap tooltip, idle placeholder (*Press «Get info» to see the VOD here.*), error messages.
  - Context menu & status messages: *Cut here ({time})*, *Skip this part*, *Keep this section*, *Isolate this game*, *Undo*, *Redo*, and all canvas feedback toasts.
  - Ruler badges & legend: clip cluster tooltip (*{n} clips between {start} and {end}*), game totals tooltip (*{game}: {duration} in total\nClick: make it its own part · Shift+click: keep only this game*), *+{n} more*.
  - Hooked to `language_bus().changed` to update on live language switch.
* Catalog and baseline:
  - 107 new strings translated into `locale/es/LC_MESSAGES/luckytwitch.po` strictly respecting `docs/i18n-glossary-es.md`.
  - Unwrapped literals dropped from 477 to 402 (`qt_ui/tabs/plan.py` and `qt_ui/timeline.py` now have 0 unwrapped literals).
  - `python tools/i18n.py check` passing cleanly with 0 problems.

### Phase I4 delivered (2026-10-30): Search, History dialog, and Watch List localization (tag i18n-phase-4)

* `qt_ui/tabs/search.py`:
  - Search row & banner: *Streamer:*, *Search*, *Sign in with Twitch to search streamers and list their VODs.*, *Sign in…*.
  - Left pane: *Results*, *● = live now*, *Recent streamers*, *The ones you opened lately*, *Clear recent*.
  - Right pane & controls: *Search for a streamer, or pick one from your recent list.*, *Filter titles…*, pin tooltips & accessible names (*Pin streamer to Watch List* / *Unpin streamer from Watch List* / *Toggle watch list pin for streamer*), view mode buttons (*List view* / *Grid view*), *Load more*, *Double-click a VOD to use it*, *Use this VOD*.
  - Empty states & feedback: *Loading VODs…*, *One moment.*, *Sign in to browse VODs*, *Pick a streamer*, *No {kind} found*, *No streamers found for «{query}»*, *Search results show up here.*, *Streamers you open show up here.*, *Search failed.*, *Searching for «{query}»…*, plural-aware *{n} streamer found* / *{n} streamers found*, *{name}: loading…*, *{name}: no {kind} found*, *{name} · {n} VOD(s) · more available*, *Could not load the VODs.*, *Select a VOD*.
  - Live retranslation: `refresh_language()` dynamic retranslation hooked to `language_bus().changed`.
* `qt_ui/search_models.py`:
  - `VOD_COLUMNS` wrapped with `N_`: *Title*, *Date*, *Length*, *Views*. `VodModel.headerData` translates column headings.
  - `VodModel.refresh_language()` emits horizontal header data change.
  - `VodGridDelegate.paint`: *✓ Downloaded*, localized date using `i18n_qt.format_date()`, and plural-aware views count `tn("{n} view", "{n} views", n)`.
* `qt_ui/dialogs.py`:
  - `HistoryDialog`: window title and heading (*Download History*), *Clear history*, table headings (*Downloaded*, *Streamer*, *Title*, *Parts*, *Quality*, *Actions*), buttons (*Folder*, *Load*, *Close*), count label (*{n} completed download* / *{n} completed downloads*), empty state (*No downloads yet*), confirmation dialog on clear (*Clear download history? This cannot be undone.*).
  - `ThemedDialog`: details bar buttons (*Show details*, *Hide details*, *Copy details*, *Copied!*).
* `qt_ui/i18n_qt.py`:
  - Extended `format_date()` and `format_datetime()` to safely parse ISO strings directly.
* Catalog and baseline:
  - 53 new strings translated into `locale/es/LC_MESSAGES/luckytwitch.po`.
  - Unwrapped literals dropped from 402 to 350 (`qt_ui/tabs/search.py`, `qt_ui/search_models.py`, and `qt_ui/dialogs.py` now have 0 unwrapped literals).
  - Dead entries in baseline shrank from 28 to 24.
  - `python tools/i18n.py check` passing cleanly with 0 problems.

### Phase I5 delivered (2026-10-30): Queue tab localization (tag i18n-phase-5)

* `qt_ui/tabs/queue.py`:
  - Cards and headers: *Queue*, *Log*.
  - Toolbar & action buttons: *Start queue*, *Cancel current*, *Retry*, *Remove selected*, *Clear finished*, *Open folder*, *Move selected waiting job up*, *Move selected waiting job down*, *Retry failed or cancelled jobs*.
  - Concurrency & speed limit: *1 job*, *2/3/4 parallel jobs*, tooltip *How many queue jobs can run at the same time*, *Unlimited speed*, tooltip *Bandwidth limit passed to yt-dlp (--limit-rate)*.
  - Log console: filter chips (*All*, *Warnings*, *Errors*), search placeholder *Filter log lines…*, *Pause autoscroll*, *Save log…*, *Copy log*, *Clear log*, empty/feedback toasts (*No log messages yet.*, *Log copied to the clipboard.*, *Log saved*, *Log saved to {name}.*, *Save log* file dialog filters).
  - Empty states & feedback: *Nothing in the queue yet*, *Set your cut points in the Plan tab and press «Add to queue».*, *Go to the Plan tab*, *Running*, *Cancel the running job first.*, *Nothing queued.*, *Cancelling {name}…*, *Cancelling…*, *Could not open:\n{target}\n\n{error}*.
  - Row delegate: inline *Open* button, plural-aware parts subtitle `tn("{n} part", "{n} parts", n)` and strategy.
  - Live retranslation: `refresh_language()` retranslates cards, buttons, tooltips, combo choices, empty state, and table viewport.
* `qt_ui/queue_model.py`:
  - `COLUMNS` wrapped with `N_`: *#*, *Video*, *Parts*, *Strategy*, *Status*. `headerData` translates headings.
  - `refresh_language()` emits horizontal header data change.
  - Real-time counter banner: `header_summary()` localized (*{done} done · {running} running · {waiting} waiting · {failed} failed*).
* `core/status.py`:
  - `queue_summary()` translates status words in the summary string.
  - `status_label()` translates status words in the status column chip (e.g. *✓ listo (N archivos)* in Spanish, preserving legacy format in English).
* Catalog and baseline:
  - 19 new strings translated into `locale/es/LC_MESSAGES/luckytwitch.po`.
  - Unwrapped literals dropped from 350 to 330 (`qt_ui/tabs/queue.py`, `qt_ui/queue_model.py`, and `core/status.py` now have 0 unwrapped literals).
  - `python tools/i18n.py check` passing cleanly with 0 problems.
