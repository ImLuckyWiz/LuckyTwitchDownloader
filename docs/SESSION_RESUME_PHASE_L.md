# Session Resume: Phase L (Linux AppImage - v2.4.0)

**Date & Time:** 2026-10-28 04:36 UTC-3  
**Status:** In progress — ready to resume immediately after PC restart.

---

## 1. Context & Completed Work

### Prior Phases Completed
- **Phase H (v2.3.1):** Cleaned legacy branch triggers, added Python 3.14 to CI, added docs status lines and index.
- **Phase V (Hardware Verification):**
  - **V1 (Chat Overlay Transparency in Premiere Pro):** Verified with screenshot.
  - **V2 (Multi-hour VOD stability/memory):** Verified from prior production runs.
  - **V3 (MP3 ID3v2 `CHAP` chapters):** Verified in `mpv`.
  - **V6 (Windows silent in-place update):** Verified upgrading from v2.3.1 to v2.3.2 with all settings, credentials, and tool paths preserved.
  - **V4 & V5 (macOS):** Marked as pending real Mac hardware.
- **macOS Intel Sunset:** Dropped `macos-15-intel` / `macos-x86_64` from CI matrix and README to cut build times and CI costs in half.
- **Python 3.14 Test Fix:** Replaced fixed `qtbot.wait(60)` with reactive `qtbot.waitUntil(..., timeout=1000)` in `tests/test_qt_motion.py`.

---

## 2. Phase L (Linux AppImage v2.4.0) Status

### Already Implemented & Saved
1. **Desktop Entry & Icon Assets:**
   - [`assets/luckytwitch.desktop`](../assets/luckytwitch.desktop): Freedesktop standard with `x-scheme-handler/luckytwitch;` MIME support.
   - [`assets/luckytwitch.png`](../assets/luckytwitch.png): 512x512 high-res application icon.
2. **Linux Build Script:**
   - [`build_linux.sh`](../build_linux.sh): Standalone Nuitka compilation, portable tarball generation (`LuckyTwitch-linux-x86_64.tar.gz`), AppDir structure assembly, and AppImage generation via `appimagetool` (`LuckyTwitch-x86_64.AppImage`).
3. **Linux Update Discovery:**
   - [`core/updates.py`](../core/updates.py): `pick_asset()` recognizes Linux platform and selects `.AppImage` (or fallback `.tar.gz`).
   - [`qt_ui/update_dialog.py`](../qt_ui/update_dialog.py): Already opens the release/asset URL in browser for non-Windows platforms.
4. **CI Workflow:**
   - [`.github/workflows/build.yml`](../.github/workflows/build.yml): Added `ubuntu-22.04` runner, apt dependencies (`libegl1`, `libgl1`, `libxcb-*`, `patchelf`, `appimagetool`), Linux build step, headless offscreen smoke test, and release asset upload for `.AppImage` and `.tar.gz`.
5. **README Documentation:**
   - [`README.md`](../README.md): Added Linux row to Download table and installation notes (FUSE `libfuse2t64` note for Ubuntu 24.04+).
6. **Tests:**
   - [`tests/test_qt_packaging.py`](../tests/test_qt_packaging.py) and [`tests/test_updates.py`](../tests/test_updates.py): Added test cases for desktop entry parsing, Linux asset picking, and CI workflow contract. Passed 66/66.

---

## 3. What to do next right after restart

1. **Update `RELEASE_NOTES.md`:** Add `## v2.4.0` section at the top detailing native Linux AppImage and tarball support.
2. **Update Plan Status Lines:**
   - `docs/LINUX_BUILD_PLAN.md` -> `Status: Done in v2.4.0`
   - `docs/NEXT_UPGRADES_PLAN.md` -> update Phase L status to Done.
   - `docs/README.md` -> update Linux plan entry.
3. **Run Test Suite:** Run `python -m pytest tests -q` to confirm all 1,426+ tests are green.
4. **Commit & Tag v2.4.0:**
   ```bash
   git add -A
   git commit -m "feat: add native Linux AppImage and portable tarball support (v2.4.0)"
   git push origin main
   git tag v2.4.0
   git push origin v2.4.0
   ```
5. **Next Phase:** Transition to **Phase E (Engine split into core/ modules)**.
