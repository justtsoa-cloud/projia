#!/usr/bin/env bash
# Construit l'AppImage à partir du bundle Flutter Linux.
# Usage : scripts/build_appimage.sh 0.1.0
set -euo pipefail
VERSION="${1:?version}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="${ARCH:-x86_64}"
BUNDLE="$ROOT/app/build/linux/x64/release/bundle"
APPDIR="$ROOT/app/build/AppDir"
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/bin"
cp -r "$BUNDLE"/. "$APPDIR/usr/bin/"
cp "$ROOT/app/assets/icon.png" "$APPDIR/projia.png"
cat > "$APPDIR/projia.desktop" <<DESK
[Desktop Entry]
Name=Projia
Comment=Hub d'IA libre et gratuit
Exec=projia
Icon=projia
Type=Application
Categories=Utility;Development;
Terminal=false
DESK
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/projia" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL="$ROOT/app/build/appimagetool"
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
  chmod +x "$TOOL"
fi
mkdir -p "$ROOT/dist"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$ROOT/dist/Projia-$VERSION-$ARCH.AppImage"
ls -lh "$ROOT/dist/"*.AppImage
