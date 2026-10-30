# Translating LuckyTwitch

LuckyTwitch uses standard GNU gettext (`.pot` / `.po` / `.mo`) catalogs with English msgids.
The translations runtime is built directly on Python's standard library `gettext` module, with no external runtime dependencies.

---

## Architecture Overview

* **Catalog templates and files:**
  - `locale/luckytwitch.pot`: Portable Object Template extracted from the codebase.
  - `locale/<lang>/LC_MESSAGES/luckytwitch.po`: Human-editable translation catalogs (UTF-8).
  - `locale/<lang>/LC_MESSAGES/luckytwitch.mo`: Binary compiled catalog read by the application.
  - `locale/qt/qtbase_<lang>.qm`: Qt standard dialog strings (buttons, context menus, file choosers).
* **Code conventions:**
  - `t("English text")`: translates and formats `{placeholders}` using `str.format()`.
  - `tn("singular", "plural", n)`: handles plural forms (returns the correct grammatical form for `n`).
  - `tc("context", "text")`: context-disambiguated translation (e.g. `tc("verb", "Plan")`).
  - `N_("Static text")`: marks strings for extraction without translating immediately (translated later via `t(var)`).

---

## Tooling Workflow (`tools/i18n.py`)

All localization operations are managed through the developer CLI tool:

```bash
python tools/i18n.py <command>
```

### 1. Extracting new strings

Scan `core/` and `qt_ui/` for all `t()`, `tn()`, `tc()`, and `N_()` strings and update `locale/luckytwitch.pot`:

```bash
python tools/i18n.py extract
```

### 2. Updating translation catalogs

Merge newly extracted messages into existing `.po` language files:

```bash
python tools/i18n.py update
```

This preserves existing translations, adds new untranslated messages with `msgstr ""`, and marks obsolete entries.

### 3. Adding a new language

To start translating LuckyTwitch into a new language (e.g. Portuguese `pt` or French `fr`):

1. Initialize the new catalog:
   ```bash
   python tools/i18n.py init pt
   ```
2. Edit `locale/pt/LC_MESSAGES/luckytwitch.po` using Poedit, VS Code, or your preferred text editor.
3. Register the new language code in `SUPPORTED_LANGUAGES` inside `core/i18n.py`:
   ```python
   SUPPORTED_LANGUAGES = {
       LANG_EN: "English",
       LANG_ES: "Español",
       "pt": "Português",
   }
   ```
4. Copy the matching Qt translation file `qtbase_pt.qm` into `locale/qt/`.

### 4. Compiling catalogs

Compile `.po` files to `.mo` binary format:

```bash
python tools/i18n.py compile
```

The compiled `.mo` file must be committed so packaged builds and source checkouts work immediately.

### 5. Running the automated hygiene & guard rail checks

Run the validation suite:

```bash
python tools/i18n.py check
```

The check verifies:
* **POT synchronization:** `luckytwitch.pot` is fully up-to-date with the source code.
* **MO compilation:** every `.mo` binary strictly matches its corresponding `.po`.
* **Completeness:** no untranslated messages (`msgstr ""` or fuzzy entries).
* **Format placeholders:** `{name}`, `{n}`, etc., match identically between msgid and msgstr.
* **Punctuation & accelerators:** identical ending punctuation (`.`, `:`, `!`, `?`), ellipsis (`…`), and `&` keyboard accelerators.
* **Glossary compliance:** required terminology adheres to `docs/i18n-glossary-es.md`.
* **Zero unwrapped literals ratchet:** ensures no new raw UI strings slip into the codebase without `t()`.

---

## Translation Style & Rules

When contributing or editing translations:
1. Consult `docs/i18n-glossary-es.md` for settled vocabulary and tone.
2. For Spanish: neutral Latin American Spanish, informal **tú** (*Reinicia*, *Presiona*).
3. Keep technical names as-is: `VOD`, `clip`, `yt-dlp`, `ffmpeg`, `TwitchDownloaderCLI`, `Premiere Pro`, `MP4`, `MKV`.
4. Ensure length expansion does not clip labels at the minimum application size (900 × 560 px).
