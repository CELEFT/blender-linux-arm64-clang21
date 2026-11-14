#!/bin/sh
# Register this portable Blender tree in the user's desktop menu.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BLENDER_BIN="$ROOT/bin/blender"
ICON_SRC="$ROOT/share/icons/hicolor/scalable/apps/blender-linux-arm64.svg"

[ -x "$BLENDER_BIN" ] || { echo "Missing launcher: $BLENDER_BIN" >&2; exit 1; }
[ -f "$ICON_SRC" ] || { echo "Missing icon: $ICON_SRC" >&2; exit 1; }

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
ICON_DEST="$ICON_DIR/blender-linux-arm64.svg"
APP_FILE="$APP_DIR/blender-linux-arm64.desktop"

mkdir -p "$APP_DIR" "$ICON_DIR"
cp -f "$ICON_SRC" "$ICON_DEST"
cat > "$APP_FILE" <<DESKTOP
[Desktop Entry]
Name=Blender (Snapdragon ARM64)
Comment=CPU Cycles, Vulkan and OpenGL Blender for Snapdragon 8s Gen 3
Exec="$BLENDER_BIN" %f
TryExec="$BLENDER_BIN"
Icon=$ICON_DEST
Terminal=false
Type=Application
Categories=Graphics;3DGraphics;
MimeType=application/x-blender;
StartupWMClass=Blender
DESKTOP
chmod 0644 "$APP_FILE" "$ICON_DEST"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf 'Installed desktop entry: %s\n' "$APP_FILE"
printf 'Installed icon: %s\n' "$ICON_DEST"
