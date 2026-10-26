# Linux Native Build & Distribution Plan

This document outlines the architecture, requirements, and step-by-step implementation plan for shipping native Linux binaries (x86_64 and arm64) for LuckyTwitch Downloader in a future release.

---

## 1. Executive Summary & Objective

- **Goal:** Provide official, standalone native Linux packages for LuckyTwitch Downloader alongside the Windows installer (`.exe`) and macOS DMG (`.dmg`).
- **Target Distribution Format:** **AppImage** (`LuckyTwitch-x86_64.AppImage`), supplemented by a portable directory tarball (`LuckyTwitch-linux-x86_64.tar.gz`).
- **Why AppImage:**
  - Single executable file requiring zero installation or root privileges (`chmod +x LuckyTwitch-x86_64.AppImage && ./LuckyTwitch-x86_64.AppImage`).
  - Compatible with major distributions: Ubuntu/Debian, Fedora, Arch/Manjaro, openSUSE, and SteamOS (Steam Deck).
  - Isolates shared library versions (bundled Qt 6 / Python runtime) while letting the OS manage Wayland/X11 rendering.

---

## 2. Codebase Readiness Assessment

The LuckyTwitch codebase is already ~95% Linux-ready out of the box:

| Component | Status | Linux Behavior / Implementation |
|---|---|---|
| **GUI Runtime (PySide6 / Qt 6)** | Ready | Native Wayland and X11 support via Qt 6 QPA (`libqwayland` / `libqxcb`). Dark theme and SVG rendering work natively. |
| **Data Directory (`core/paths.py`)** | Ready | Adheres to the XDG Base Directory specification: `~/.local/share/LuckyTwitch`. |
| **Tool Management (`luckytwitch_engine.py`)** | Ready | Engine already contains Linux handlers: auto-downloads `yt-dlp_linux`, static GPL Linux builds of `ffmpeg` (`.tar.xz`), and Linux x64/arm builds of `TwitchDownloaderCLI`. |
| **IPC & Web Links (`weblink.py`)** | Ready | Uses POSIX file-based heartbeats and link files in `~/.local/share/LuckyTwitch/links/`. |
| **Process Tree Management** | Ready | Engine already uses `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` on non-Windows platforms to terminate child downloader and ffmpeg jobs cleanly. |

---

## 3. Implementation Steps

### Phase 1: Desktop Entry & Icon Assets

1. Create a freedesktop-compliant desktop entry file at `assets/luckytwitch.desktop`:
   ```ini
   [Desktop Entry]
   Name=LuckyTwitch
   Comment=Twitch VOD Downloader & Video Cutter
   Exec=LuckyTwitch %u
   Icon=luckytwitch
   Terminal=false
   Type=Application
   Categories=AudioVideo;Video;Network;
   MimeType=x-scheme-handler/luckytwitch;
   ```
2. Place a high-resolution PNG icon (e.g. 512x512) at `assets/luckytwitch.png` for AppImage and desktop environment integration.

### Phase 2: Build Script (`build_linux.sh`)

Create `build_linux.sh` modeled after `build_mac.sh` and `build_windows.bat`:
- **Compiler:** Nuitka (`python -m nuitka`).
- **Parameters:**
  - `--standalone`
  - `--enable-plugin=pyside6`
  - `--include-data-files=assets/icons/app_icon.ico=assets/icons/app_icon.ico`
  - `--include-data-files=assets/icons/app_icon.png=assets/icons/app_icon.png`
  - `--include-data-files=assets/icons/badge_*.png=assets/icons/`
  - `--output-dir=dist`
- **Packaging:**
  - Assemble the AppDir structure:
    ```text
    AppDir/
    ├── AppRun (symlink or launcher script)
    ├── luckytwitch.desktop
    ├── luckytwitch.png
    └── usr/
        ├── bin/ (Nuitka standalone executable + libraries)
        └── share/
            ├── applications/luckytwitch.desktop
            └── icons/hicolor/512x512/apps/luckytwitch.png
    ```
  - Use `appimagetool` to generate `dist/LuckyTwitch-x86_64.AppImage`.
  - Also produce `dist/LuckyTwitch-linux-x86_64.tar.gz` as a fallback portable archive.

### Phase 3: GitHub Actions CI Matrix (`.github/workflows/build.yml`)

Add an Ubuntu runner to the build matrix:

```yaml
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            label: windows
          - os: macos-14
            label: macos-arm64
          - os: macos-15-intel
            label: macos-x86_64
          - os: ubuntu-22.04
            label: linux-x86_64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Linux build dependencies
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
            libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xfixes0 \
            patchelf file
          # Fetch appimagetool
          wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O appimagetool
          chmod +x appimagetool
          ./appimagetool --appimage-extract
          sudo mv squashfs-root/usr/bin/appimagetool /usr/local/bin/

      - name: Install Python dependencies
        run: python -m pip install -r requirements-dev.txt

      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest tests -q

      - name: Build (Linux)
        if: runner.os == 'Linux'
        run: bash build_linux.sh "${{ github.ref_type == 'tag' && github.ref_name || '1.0' }}"

      - uses: actions/upload-artifact@v4
        with:
          name: LuckyTwitch-${{ matrix.label }}
          path: |
            dist/LuckyTwitch-Setup.exe
            dist/LuckyTwitch-*.dmg
            dist/LuckyTwitch-*.AppImage
            dist/LuckyTwitch-*.tar.gz
```

---

## 4. Platform-Specific Edge Cases & Solutions

1. **Wayland vs X11:**
   - Qt 6 automatically detects whether the session is Wayland or X11.
   - If a user has a misconfigured Wayland compositor, they can launch with `QT_QPA_PLATFORM=xcb` or `QT_QPA_PLATFORM=wayland`.
2. **AppImage FUSE Dependency on Ubuntu 24.04+:**
   - Modern Ubuntu installations omit `libfuse2` by default in favor of `fuse3`.
   - The AppImage runtime or instructions should note `sudo apt install libfuse2t64` (or extract via `--appimage-extract`).
3. **MIME & Scheme Association:**
   - Running `luckytwitch://` URLs in browser on Linux requires registering the `.desktop` file via:
     ```bash
     xdg-mime default luckytwitch.desktop x-scheme-handler/luckytwitch
     ```
   - Tools like `AppImageLauncher` handle this automatically when users click an AppImage.

---

## 5. Verification Checklist for Release

- [ ] Automated tests pass with `QT_QPA_PLATFORM=offscreen` on `ubuntu-22.04`.
- [ ] Built AppImage executes on clean Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, and Fedora 40+.
- [ ] VOD search, thumbnail caching, and download engine work seamlessly with auto-downloaded Linux `yt-dlp` and `ffmpeg`.
- [ ] Dark theme, icons, and custom navigation rail render crisply without font metric anomalies.
- [ ] `build.yml` publishes `LuckyTwitch-x86_64.AppImage` and `.tar.gz` to GitHub Releases.
