# Upgrade Progress Review and Feature Ideas

Status: **Pending (plan only, no code written).** Date: 2026-10-29. Reviewed against `NEXT_UPGRADES_PLAN.md`, `RELEASE_NOTES.md` and the v2.9.0 sources.

## 1. Plan versus reality

| Plan item | Result in the repo | Verdict |
|---|---|---|
| H Housekeeping (v2.3.1) | Patch file removed, CI branch cleaned, Python 3.14 test leg, docs index and status lines. | Done. 3.14 is allowed to fail. |
| V Real-hardware verification | `VERIFICATION_CHECKLIST.md`: Windows checks verified, macOS pending. | **Partly done** (macOS V4/V5 deferred until a friend's Mac is available; no Mac access now). |
| L Linux AppImage (v2.4.0) | AppImage and tarball, `.desktop`, update asset choice. x86_64 only. | Done. arm64 never decided. |
| E Engine split (v2.5.0) | 14 `core/` modules, ~200-line facade, 1,449 tests at that time. | Done. |
| W Window bar (v2.6.0 to 2.6.2, not in the original plan) | Custom title bar, resize, snap, drag-to-restore, spike tool. | Done. Win32 behaviour only verifiable on Windows. |
| P1 Limit to chapter, P2 Named recipes, P3 Preferences from downloader (panel v0.15.0) | Present in release notes and panel version. | Done. |
| P4 Panel polish | The list of polish items was never written. | **Open** (undefined). |
| F1 Download history (v2.7.0) | Present, with badge and dialog. | Done, but see audit A2/A3 (storage safety). |
| F2 Watch list (v2.7.0) | Present, with badge on the Search rail icon. | Done. Never downloads by itself, as planned. |
| F3 Parallel jobs and speed limit (v2.8.0) | Present (1 to 4 jobs, limit presets). | Done with caveats: audit A3, A5, A6. |
| F4 Spanish (v2.9.0) | Catalog and picker exist; about 330 UI strings and the engine messages untranslated. | **Incomplete.** Reopened as `I18N_SPANISH_PLAN.md`. |

**Things that went wrong or were missed**

1. `NEXT_UPGRADES_PLAN.md` and `docs/README.md` mark everything "Done in v2.9.0", but F4 is incomplete, V is partial and P4 is undefined. Proposed status: "Done with exceptions" plus links to the follow-up plans.
2. F3 shipped without a safe-storage review: history writes from worker threads are unprotected and the shared progress bar is wrong with several jobs (`PROJECT_AUDIT_2026_10.md` A3, A5).
3. The macOS Intel build was dropped on purpose (confirmed), but the README does not say so.
4. The README claims full Spanish localization.
5. Stale docs (`SESSION_RESUME_PHASE_L.md`, `WINDOW_BAR_FIX_2_6_2.md` status).

## 2. Feature ideas (checked against the code so nothing already built is proposed)

Already present, so **not** proposed: resume of partial downloads (`--continue`), OS notifications (`qt_ui/notify.py`), Premiere sequence backup before cutting (`backup: true`), Windows silent update, download history, watch list, queue concurrency.

| # | Idea | Why | Notes | Size |
|---|---|---|---|---|
| 1 | **Disk-space pre-flight** | Today free space is only displayed in Options. A multi-hour VOD can fill the drive halfway. | Estimate from format size x duration x jobs; warn or block before the queue starts. | S |
| 2 | **Persistent log file + "Copy diagnostics"** | Faster support and crash analysis. | Rotating log (audit A13); diagnostics = versions, tool versions, OS, last log lines, settings without secrets. | S |
| 3 | **Settings export/import and automatic backup** | Protects against corruption and eases moving to a new PC. | Ties to audit A2; never include tokens in the export. | S |
| 4 | **Per-streamer presets and optional auto-queue from the watch list** | Natural next step of F2: new VOD found, add it to the queue with that streamer's cut strategy, quality and naming, **only if the user enabled it for that streamer**. | Keep "never downloads by itself" as the default. | M |
| 5 | **Queue finish actions** | Long overnight queues: open folder, play sound, or (opt-in) shut down/sleep the PC after the last job. | Needs a clear confirmation and a cancel countdown. | S |
| 6 | **Trust and distribution** | Windows SmartScreen and macOS Gatekeeper warnings put users off. | Windows code signing (for example a free open-source signing program) and macOS notarization need accounts, so this is a decision rather than a coding task. | M (mostly process) |
| 7 | **Update flow beyond Windows** | Linux/macOS only open the release page. | AppImage update information (zsync) for Linux; macOS stays manual until notarized. | M |
| 8 | **Panel: define P4 and add a language option** | P4 never got a list; panel is English only. | Collect the list from real use; panel language is deferred (future work). | S to M |
| 9 | **Chat as subtitles** | Chat already downloads; exporting it as `.srt`/`.vtt` next to the video would let editors and players use it without the heavy overlay render. | Check TwitchDownloaderCLI output formats first. | M |
| 10 | **Platform decisions** | Intel Mac is dropped on purpose; Linux arm64 is still unresolved. | Add one README line for Intel; decide arm64. | S |

## 3. Suggested order

1. **Audit R1 + R2** (safe storage, double History dialog) together with Spanish **I0 + I1** as **v2.9.1**.
2. **Spanish I2 to I9** as **v2.10.0** (beta after I5).
3. **Audit R3 to R5** as **v2.9.2** (can run in parallel with the Spanish work, they touch different files except `queue.py`).
4. Ideas 1, 2, 3 and 5 (small, high value), then 4, then 6/7 as process decisions.
5. The Phase V macOS checks wait for your friend's Mac; until then `NEXT_UPGRADES_PLAN.md` stays "Done with exceptions".

## 4. Decisions needed

* ~~Mac / Intel~~ **Decided:** Intel support is dropped on purpose; macOS checks are deferred until a friend's Mac is available.
* Linux arm64: yes or no?
* Which of ideas 1 to 10 do you want in the roadmap (I would start with 1, 2, 3, 5)?
* Is code signing (idea 6) something you want to invest in?
