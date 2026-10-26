#!/usr/bin/env bash
# Build LuckyTwitch (PySide6) for macOS with Nuitka -> dist/LuckyTwitch.app (+ dist/LuckyTwitch-macos-<arch>.dmg)
# Usage: bash build_mac.sh [version]
# The result matches the Mac you build on: Apple Silicon -> arm64, Intel -> x86_64.
set -euo pipefail
cd "$(dirname "$0")"

VER="${1:-${GITHUB_REF_NAME:-1.0}}"
BUNDLE_ID="com.luckytwitch.app"
case "$VER" in
  *-*) BUNDLE_ID="com.luckytwitch.app.beta" ;;
esac

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

mkdir -p build
printf '%s\n' "$VER" > build/version.txt

rm -rf dist/LuckyTwitch.app

python3 -m nuitka --mode=app \
  --enable-plugin=pyside6 \
  --macos-app-icon=assets/icon.icns \
  --macos-app-name=LuckyTwitch \
  --macos-signed-app-name="$BUNDLE_ID" \
  --macos-app-version="$VER" \
  --output-dir=dist \
  --output-folder-name=LuckyTwitch \
  --output-filename=LuckyTwitch \
  --include-data-dir=assets=assets \
  --include-data-files=build/version.txt=version.txt \
  --include-package=core \
  --include-package=qt_ui \
  --include-package=requests \
  --include-module=luckytwitch_engine \
  --include-module=weblink \
  --nofollow-import-to=tkinter \
  --nofollow-import-to=_tkinter \
  --nofollow-import-to=pytest \
  --assume-yes-for-downloads \
  --update-check=never \
  luckytwitch_qt.py

# Let macOS send luckytwitch:// links to the app (web pages can offer them). This has to happen before signing.
PLIST="dist/LuckyTwitch.app/Contents/Info.plist"
PB=/usr/libexec/PlistBuddy
"$PB" -c "Delete :CFBundleURLTypes" "$PLIST" 2>/dev/null || true
"$PB" -c "Add :CFBundleURLTypes array" \
      -c "Add :CFBundleURLTypes:0 dict" \
      -c "Add :CFBundleURLTypes:0:CFBundleURLName string com.luckytwitch.app.link" \
      -c "Add :CFBundleURLTypes:0:CFBundleTypeRole string Viewer" \
      -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" \
      -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string luckytwitch" "$PLIST"

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
  # Tell macOS about the copy right away, so luckytwitch:// links work before the first launch.
  LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
  [ -x "$LSREG" ] && "$LSREG" -f "$DEST/LuckyTwitch.app" || true
  echo "Installed in $DEST/LuckyTwitch.app"
fi

echo
echo "Done: dist/LuckyTwitch.app  and  dist/LuckyTwitch-macos-${ARCH}.dmg"
