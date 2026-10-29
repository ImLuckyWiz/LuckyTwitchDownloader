#!/usr/bin/env bash
# Build LuckyTwitch (PySide6) for Linux with Nuitka -> dist/LuckyTwitch-x86_64.AppImage (+ dist/LuckyTwitch-linux-x86_64.tar.gz)
# Usage: bash build_linux.sh [version]
set -euo pipefail
cd "$(dirname "$0")"

VER="${1:-${GITHUB_REF_NAME:-1.0}}"

echo "Building LuckyTwitch Linux standalone ($VER)..."

PIP_FLAGS=""
if python3 -m pip install --help 2>&1 | grep -q -- '--break-system-packages'; then
    PIP_FLAGS="--break-system-packages"
fi

python3 -m pip install --upgrade pip $PIP_FLAGS || true
python3 -m pip install -r requirements.txt $PIP_FLAGS

mkdir -p build
printf '%s\n' "$VER" > build/version.txt

rm -rf dist/LuckyTwitch dist/LuckyTwitch.dist

python3 -m nuitka --mode=standalone \
  --enable-plugin=pyside6 \
  --output-dir=dist \
  --output-folder-name=LuckyTwitch \
  --output-filename=LuckyTwitch \
  --include-data-dir=assets=assets \
  --include-data-dir=locale=locale \
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

# Nuitka in standalone mode creates dist/LuckyTwitch.dist; normalize to dist/LuckyTwitch
if [ -d "dist/LuckyTwitch.dist" ]; then
    rm -rf dist/LuckyTwitch
    mv dist/LuckyTwitch.dist dist/LuckyTwitch
fi

# Create fallback portable tarball
echo "Creating portable tarball..."
tar -czf "dist/LuckyTwitch-linux-x86_64.tar.gz" -C dist LuckyTwitch

# Build AppImage AppDir structure
echo "Assembling AppDir..."
APPDIR="build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/512x512/apps"

cp -r dist/LuckyTwitch/* "$APPDIR/usr/bin/"
cp assets/luckytwitch.desktop "$APPDIR/luckytwitch.desktop"
cp assets/luckytwitch.desktop "$APPDIR/usr/share/applications/luckytwitch.desktop"
cp assets/luckytwitch.png "$APPDIR/luckytwitch.png"
cp assets/luckytwitch.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/luckytwitch.png"

cat << 'EOF' > "$APPDIR/AppRun"
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/LuckyTwitch" "$@"
EOF
chmod +x "$APPDIR/AppRun"

if command -v appimagetool >/dev/null 2>&1; then
    echo "Creating AppImage with appimagetool..."
    ARCH=x86_64 appimagetool --no-appstream "$APPDIR" "dist/LuckyTwitch-x86_64.AppImage"
else
    echo "Notice: appimagetool not found on PATH. Tarball created at dist/LuckyTwitch-linux-x86_64.tar.gz."
fi

echo "Linux build completed successfully."
