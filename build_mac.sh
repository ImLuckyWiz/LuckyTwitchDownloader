#!/usr/bin/env bash
# Build LuckyTwitch for macOS -> dist/LuckyTwitch.app (+ dist/LuckyTwitch-macos-<arch>.dmg)
# Use Python from python.org (the Python bundled with macOS has an outdated Tk).
# The result matches the Mac you build on: Apple Silicon -> arm64, Intel -> x86_64.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name LuckyTwitch \
  --icon assets/icon.icns \
  --add-data "assets:assets" \
  --osx-bundle-identifier com.luckytwitch.app \
  --collect-submodules requests \
  --collect-submodules ui \
  --hidden-import luckytwitch_engine \
  --hidden-import PIL._tkinter_finder \
  luckytwitch_downloader.py

# Ad-hoc signature: required for arm64 binaries to launch at all.
codesign --force --deep --sign - dist/LuckyTwitch.app

ARCH="$(uname -m)"
# DMG: a disk image showing the app next to an "Applications" shortcut (drag to install).
STAGE="$(mktemp -d)"
ditto dist/LuckyTwitch.app "$STAGE/LuckyTwitch.app"
ln -s /Applications "$STAGE/Applications"
rm -f "dist/LuckyTwitch-macos-${ARCH}.dmg"
# hdiutil sometimes fails with "Resource busy" on CI runners (the disk-image service is still occupied),
# so try a few times, detaching anything left mounted in between.
DMG_OK=0
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname "LuckyTwitch" -srcfolder "$STAGE" -ov -format UDZO "dist/LuckyTwitch-macos-${ARCH}.dmg"; then
    DMG_OK=1
    break
  fi
  echo "hdiutil create failed (attempt $attempt of 5), retrying..."
  hdiutil detach "/Volumes/LuckyTwitch" -force >/dev/null 2>&1 || true
  rm -f "dist/LuckyTwitch-macos-${ARCH}.dmg"
  sleep $((attempt * 5))
done
[ "$DMG_OK" = 1 ] || { echo "Could not create the DMG after 5 attempts."; exit 1; }
rm -rf "$STAGE"

# Also install straight into Applications on this Mac (Finder, Launchpad, Spotlight).
# Skipped on GitHub Actions, where there is nobody to use it.
if [ -z "${CI:-}" ]; then
  DEST="/Applications"
  [ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }
  rm -rf "$DEST/LuckyTwitch.app"
  ditto dist/LuckyTwitch.app "$DEST/LuckyTwitch.app"
  echo "Installed in $DEST/LuckyTwitch.app"
fi

echo
echo "Done: dist/LuckyTwitch.app  and  dist/LuckyTwitch-macos-${ARCH}.dmg"
