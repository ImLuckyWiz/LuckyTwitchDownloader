## v0.0.1-alpha.1

**Pipeline test. This is not the PySide6 app yet.** It is the current tkinter app (same code as v1.16.0) built from the `qt-migration` branch, published as a pre-release to check that the branch, the tag, the notes and the build all work. No PySide6 code exists yet.

### What to know
- **Do not install it over your normal LuckyTwitch.** The Windows installer uses the same install folder and the same app id as the stable one, and the app keeps its settings and Twitch login in the same data folder. If you want to try it, use a separate machine or a virtual machine.
- Nothing was removed or changed in the app itself.
- What is new is only in the repository: `docs/migration/` (the migration plan, the hand-off file and the phase notes) and the build workflow, which now publishes tags like `v0.0.1-alpha.1` as pre-releases that never become the Latest release.

### Version plan for the migration
- `v0.0.1-alpha.1`: this one (pipeline test, Phase 0).
- `v0.6.0-alpha.1`: after Phase 6, the first Qt build that can load a VOD, set cut points and queue a job.
- `v0.7.0-alpha.1`: after Phase 7 (the timeline).
- `v0.8.0-beta.1`: after Phase 8 (installers and packaging for PySide6).
- `v2.0.0`: the cutover; the Qt app replaces the tkinter app.

Phases 1 to 5 are not published; they only get a git tag (`migration-phase-N`).
