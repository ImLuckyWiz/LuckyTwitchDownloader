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

## Phase 0: Baseline and decisions  (not started)

The plan and this folder were written before any code. Phase 0 itself (baseline test run, screenshots of every screen, PARITY.md, SETTINGS_KEYS.md, the PySide6 environment) has not been done yet. The only thing done so far is the set-up of the branch, the notes, the hand-off file and the pre-release build workflow (release `v0.0.1-alpha.1`, a pipeline test).
