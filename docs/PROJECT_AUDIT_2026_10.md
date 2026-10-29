# Project Audit (v2.9.0) and Remediation Plan

Status: **Pending (plan only, no code written).** Date: 2026-10-29. Source: `lt-repo_1.zip` (app v2.9.0, Premiere CEP panel v0.15.0).

## 1. Scope and method

* **Run:** full Python suite (**1,541 passed**) and Node suite (**133 passed**) in a Linux sandbox with Qt offscreen.
* **Static analysis:** `ruff` (pyflakes, bugbear, performance, selected security rules) across the Python code.
* **Code reading:** history/watch list/settings storage, the parallel queue, update flow, configuration and tokens, localization, CI/build files, docs.
* **Not verified (cannot be done here):** the Windows frameless-window code (`qt_ui/frameless.py`, Win32 messages), real Premiere Pro, a real Mac, real Twitch network calls, frozen (Nuitka) builds, a real GUI session. Findings marked *by reading* should be confirmed with a test or on the real system before fixing.

**Overall:** the project is in good shape. Tests are green, the engine split is clean, downloads of tools use temp file + `os.replace`, and the update installer requires a SHA-256 match. The findings below are mostly robustness and consistency problems, not crashes in normal use.

## 2. Findings

| ID | Severity | Finding | Evidence | Proposed fix |
|---|---|---|---|---|
| A1 | **High** (user-visible) | The **History** button is connected twice, so one click can open the history dialog twice (the second after the first is closed). | `qt_ui/main_window.py` lines 241 and 242 are identical `history_btn.clicked.connect(self.open_history_dialog)`. *By reading.* | Remove one line; add a test that clicks the button and counts dialog openings. |
| A2 | **High** (data loss) | Settings files are written with plain `write_text` (not atomic), and a damaged `config.json` is read as `{}`, so the next save **erases the Twitch tokens and own-app secret**. History and watch list return an empty list on any error and then overwrite the file. | `core/config.py` (`read_config` returns `{}` on `JSONDecodeError`; `save_login_tokens` writes back). `write_text` in `config.py`, `settings.py`, `ui_state.py`, `history.py`, `watchlist.py`, `recent.py`, `updates.py`. Atomic `os.replace` is used only for tools, `source_info` and `vod_search`. | One shared `atomic_write_json()` (temp file in the same folder, flush, `os.replace`); on a parse error rename the bad file to `*.corrupt` and keep it instead of overwriting; keep one `.bak`. Tests with simulated partial writes. |
| A3 | **High** under parallel jobs | `record_download` does read → modify → write on `luckytwitch_history.json` and is called from worker threads, with no lock. Two jobs finishing together can lose an entry or corrupt the file (then A2 wipes it). | `core/history.py` `record_download`; called from `core/finalize.py:635`; workers in `qt_ui/queue_runner.py`. *By reading.* | A module lock around read-modify-write plus the atomic write from A2; test with 8 threads recording at once. |
| A4 | Medium | Twitch access/refresh tokens and the client secret are stored in plain text in `config.json`, with no restrictive permissions on Linux/macOS. | `core/config.py`; no `chmod`/keyring anywhere. | `chmod 600` on POSIX at minimum; consider the OS keyring as an option. Mention in the README. |
| A5 | Medium | With several jobs, the status bar progress and "Job n/total" are **shared**: every job emits to the same `bridge.progress`, so the bar jumps between jobs; `self.ctx` keeps only the last one. | `qt_ui/queue_runner.py` `on_item_progress` emits `bridge.progress` for all jobs. *By reading.* | Show per-row progress only (already supported by the model), and for the global bar use the average of running jobs; test with two fake jobs. |
| A6 | Medium | The speed limit is **per process**: 4 parallel jobs with "5 MB/s" can use 20 MB/s. It is also unverified that the ffmpeg-based section downloads honour `--limit-rate` (yt-dlp's ffmpeg downloader generally does not). | `core/download.py` lines 301 to 329 and 403 to 447; queue tab speed combo. | Label it "per job" (or divide by the number of running jobs); verify with a real section download and document the result in the Verification Checklist. |
| A7 | Medium | System language detection uses the deprecated `locale.getdefaultlocale()` (removed in Python 3.15) and ignores `QLocale`, although the 2.9.0 notes say it uses it. The test run already shows the deprecation warning. | `core/i18n.py:190`. | Covered by `I18N_SPANISH_PLAN.md`, phase I1. |
| A8 | Medium (accuracy) | The README says LuckyTwitch is "fully localized" in English and Spanish; about 330 UI strings and the engine messages are still English. | See the diagnosis in `I18N_SPANISH_PLAN.md`. | Soften the wording now, restore it after phase I8. |
| A9 | Medium | CI runs the tests **only on Windows** and Python 3.14 is allowed to fail; the Linux and macOS code paths (edge grips, AppImage packaging, update asset choice) have no test run on their own OS. | `.github/workflows/build.yml` `test` job: `runs-on: windows-latest`, `allow-failure` for 3.14. | Add an Ubuntu test job (`QT_QPA_PLATFORM=offscreen`, `xvfb` if needed) and a macOS job when affordable. |
| A10 | Medium | Build is not reproducible: `requests`, `pillow`, `nuitka`, `zstandard` are unpinned (only `PySide6==6.12.0` is), so a new Nuitka release can break a tag build. | `requirements.txt`. | Pin versions (or a constraints file) and let Dependabot propose updates; keep the release build on pinned versions. |
| A11 | Low | Dead and duplicate code: 353 `F401` (almost all expected re-exports in the `luckytwitch_engine.py` facade, about 10 real ones in `core/chat.py`, `core/finalize.py`, `core/job.py`, `core/watchlist.py`, `core/chapters.py`); redefined imports in `qt_ui/main_window.py` (lines 501 and 552, `F811`); unused loop variable in `qt_ui/tabs/plan.py:596`; `zip()` without `strict=` in `core/planning.py` (71, 83) and `core/timeline.py:138`. | `ruff` output. | Declare the facade's `__all__` (or a targeted ignore) so real unused imports show up; remove the real ones; add `strict=True` where lengths must match. |
| A12 | Low | 19 `try/except/pass` and 18 blind `except Exception` hide errors (for example in history and watch list loading). | `ruff` S110/BLE001. | Log a one-line warning in the data folder log instead of silently passing; keep the user-facing behaviour. |
| A13 | Low | No persistent log file: the log panel can be saved by hand ("Save log…") but a crash leaves nothing to inspect. | No file handler in `core/` or `qt_ui/`. | Rotating log file in the data folder (a few MB, 3 files) plus an "Open logs folder" button. |
| A14 | Low | Docs status drift: `docs/SESSION_RESUME_PHASE_L.md` still says "In progress, resume after PC restart"; `docs/WINDOW_BAR_FIX_2_6_2.md` says "Plan only. No code written" while the index and release notes say Done in v2.6.2; `ENGINE_SPLIT_MAP.md` says Active while the index says Done; `NEXT_UPGRADES_PLAN.md` says Done although F4 is incomplete and Phase V (macOS) is pending. | Status lines in `docs/`. | Fix statuses; archive or delete the Phase L session note. |
| A15 | Low | The macOS Intel build was dropped in v2.4.0 **on purpose** (confirmed 2026-10-29; CI matrix has only `macos-14` arm64). The README table lists Apple Silicon only but does not say Intel is unsupported. | `build.yml` build matrix; README download table. | Only add one README line saying Intel Macs are not supported. |
| A16 | Low | The installer is English-only (`installer.iss` has no `[Languages]`). | `installer.iss`. | Covered by the Spanish plan, phase I9. |

## 3. Remediation plan

| Phase | Content | Release |
|---|---|---|
| **R1 Safe storage** | A2, A3, A4: shared atomic JSON helper, corrupt-file handling with `.corrupt`/`.bak`, history lock, `chmod 600` for `config.json`. New tests: partial write, corrupt file keeps credentials, concurrent history writes. | v2.9.1 |
| **R2 Quick fixes** | A1 (+ test), A7 (`QLocale`, with I1 of the Spanish plan), A11 (facade `__all__`, real unused imports, `strict=`), A8 wording. | v2.9.1 |
| **R3 Parallel polish** | A5, A6: per-row progress and honest global bar, "per job" speed limit, real-download verification of the limit on section downloads. | v2.9.2 |
| **R4 CI and build hygiene** | A9, A10: Ubuntu test job, pinned requirements, Dependabot. A15 README line. | v2.9.2 |
| **R5 Observability and docs** | A12, A13, A14: logged warnings, rotating log file, docs statuses cleaned. | v2.9.2 |

Order suggestion: **R1 and R2 first** (they protect user data and remove the double dialog), then the Spanish plan (phases I0 and I1 can ride along in v2.9.1), then R3 to R5.

## 4. Acceptance

* Both suites green on every CI leg; the new Ubuntu job passes.
* A corrupted `config.json`/`luckytwitch_history.json` never loses data silently (the bad file is kept next to the new one).
* One click on History opens one dialog (test).
* `ruff check --select F,E9,B` is clean outside the explicitly allowed facade re-exports.
* Verification Checklist updated with the real-download check for the speed limit and the Spanish-locale Windows check.
