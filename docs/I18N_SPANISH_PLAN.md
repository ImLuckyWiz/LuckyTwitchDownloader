# Spanish Localization Plan (Phase F4b: finish and harden the translation)

Status: **Pending (plan only, no code written).** Date of analysis: 2026-10-29, repo at v2.9.0.

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
| **I1 Infrastructure** | `bind_text` + `language_changed`; locale helper (numbers/dates); `QTranslator` for Qt strings; fix detection with `QLocale` and drop `getdefaultlocale`; **Auto** option; remove hard-coded Spanish comparisons; keep a short "restart" notice only for what really needs it. **Packaging:** the build scripts (`build_windows.bat`, `build_mac.sh`, `build_linux.sh`) bundle `locale/` into the Nuitka build; CI runs `tools/i18n.py check` and a frozen-build smoke test that loads the Spanish catalog. Tests: switching language updates every bound widget without restart (offscreen); detection with mocked locales (`es_UY`, `es-ES`, `en_US`, `C`); `tn` plural forms 0/1/2. Ship as **v2.9.1**. | M |
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

Release proposal: **v2.9.1** after I0+I1 (little visible change, safer detection), a **v2.10.0-beta.1** after I5 for Spanish testers, final **v2.10.0** after I9 and I11 (I10 is deferred).

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
* **D7** Commit the compiled `.mo` files (proposed: yes, with a CI check that they match the `.po`, so running from source and building both just work) or compile them only in the build scripts and CI (cleaner repo, but running from source needs one extra command, otherwise the app silently shows English).

---

## 7. Acceptance criteria

1. With the language set to Español, the "no English left" walk finds nothing outside the allow-list, and the coverage baseline is empty.
2. Switching language updates every open window immediately; no restart notice.
3. Qt standard buttons and context menus are Spanish.
4. The installer, README.es.md and the Linux launcher entry are Spanish; the README wording is accurate.
5. Both test suites are green on the CI matrix.
