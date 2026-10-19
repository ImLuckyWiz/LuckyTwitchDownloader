# Phase notes

Internal notes, one entry per phase, newest first. Written by the agent at the end of a phase, reviewed by the user. Public release notes for the phases that get a pre-release are in RELEASE_NOTES_QT.md.

Entry template (copy it for each phase):

```
## Phase N: <name>  (<date>, tag migration-phase-N, PR #<n>)
**Done:** what was built, in a few lines.
**Definition of Done:** each item from the plan, marked done or not done, with the evidence (test names, command output, screenshots).
**Divergences from the tkinter app:** each also in MIGRATION_LOG.md, or "none".
**Known issues / left for later:**
**Tests:** how many pass, how many skipped or expected to fail, and why.
**Next:** the exact next step.
```

## Phase 0: Baseline and decisions  (2026-10-19, tag migration-phase-0 pending, PR pending)
**Done:** `docs/migration/PLAN.md` added to the repository. Baseline test run recorded (`baseline/TEST_BASELINE.md`): 798 passed. `PARITY.md` (one section per screen, 235 tkinter GUI tests as a checklist plus the structure and texts of each screen), `SETTINGS_KEYS.md` (all 38 keys with type, default and where edited), `MIGRATION_LOG.md` (empty with header). `requirements-qt.txt` (PySide6 6.12.0, pytest-qt) and `tools/hello_qt.py`. `tools/baseline_screenshots.py` and 28 Linux/xvfb screenshots in `baseline/linux-xvfb/`. `progress-eta.patch` checked (stale). File sizes re-measured. D1 to D6 confirmed by the user.
**Definition of Done:**
- Baseline test report: done. `baseline/TEST_BASELINE.md`; `xvfb-run -a python3 -m pytest tests` gave 798 passed.
- Screenshots (or the exact list the user must take): partly done. 28 screenshots made under xvfb (every tab, all 7 Options sections, the Twitch sign-in dialog, at 1020x910 and 900x560). They are not Windows renderings. The user takes the Windows set with one command (HANDOFF.md section 7). Screens that need real data (search results, a running job, a real VOD in the timeline, message boxes) are not covered; listed in TEST_BASELINE.md.
- The three docs: done (`PARITY.md`, `SETTINGS_KEYS.md`, `MIGRATION_LOG.md`). PARITY.md is a first version built from the sources I read (`build_search_tab`, `build_queue_tab`, `ask_credentials`, `ui/plan_tab.py`, section lists) and the test names; each porting phase re-reads its screen and adds what is missing.
- `requirements-qt.txt` and the hello-window running: done. `QT_QPA_PLATFORM=offscreen python3 tools/hello_qt.py --check` printed `platform=offscreen label='Signal and slot work.'`, exit 0. A throw-away pytest-qt test of the window also passed (not delivered).
- User confirmation of D1 to D6: done (2026-10-19, "agree with all").
- Not run by me: the app on Windows or macOS, the hello-window with a real display, the screenshots with real fonts.
**Divergences from the tkinter app:** none (no app code changed).
**Known issues / left for later:** the two timeline tests from the old warning already pass (nothing to fix). `progress-eta.patch` is stale (delete is the user's decision). The sandbox needed `apt-get install python3-tk` to run the GUI tests. PySide6 meta-package is large; consider PySide6-Essentials in Phase 8. During the session the agent read the `.git` folder of the uploaded zip (`git log`, `git apply --check`, `git status`) against the rules; nothing was modified, and it was reported to the user.
**Tests:** 798 passed, 0 skipped, 0 xfail with Tk and xvfb; 513 passed and 1 skipped without tkinter.
**Next:** user checks and approval, then Phase 1 (HANDOFF.md section 7).
