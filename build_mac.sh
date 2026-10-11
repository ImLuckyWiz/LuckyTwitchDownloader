#!/usr/bin/env bash
# Build LuckyTwitch for macOS -> dist/LuckyTwitch.app (+ dist/LuckyTwitch-macos-<arch>.zip)
# Use Python from python.org (the Python bundled with macOS has an outdated Tk).
# The result matches the Mac you build on: Apple Silicon -> arm64, Intel -> x86_64.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name LuckyTwitch \
  --osx-bundle-identifier com.luckytwitch.app \
  --collect-submodules requests \
  --hidden-import luckytwitch_engine \
  luckytwitch_downloader.py

# Ad-hoc signature: required for arm64 binaries to launch at all.
codesign --force --deep --sign - dist/LuckyTwitch.app

ARCH="$(uname -m)"
ditto -c -k --keepParent dist/LuckyTwitch.app "dist/LuckyTwitch-macos-${ARCH}.zip"
# Install into Applications (shows up in Finder, Launchpad and Spotlight).
if [ -d "$HOME/Applications" ] || mkdir -p "$HOME/Applications" 2>/dev/null; then :; fi
DEST="/Applications"
[ -w "$DEST" ] || DEST="$HOME/Applications"
rm -rf "$DEST/LuckyTwitch.app"
ditto dist/LuckyTwitch.app "$DEST/LuckyTwitch.app"
echo "Installed in $DEST/LuckyTwitch.app"

echo
echo "Done: dist/LuckyTwitch.app  and  dist/LuckyTwitch-macos-${ARCH}.zip"
