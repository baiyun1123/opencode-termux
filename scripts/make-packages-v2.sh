#!/usr/bin/env bash
# Create distribution packages for OpenCode 2 (opencode2) for Android
#
# Usage: ./scripts/make-packages-v2.sh
#
# Creates three package formats:
# 1. ZIP: opencode2-${RELEASE_VERSION}-android-aarch64.zip (standalone binary)
# 2. Pacman: opencode2-${RELEASE_VERSION}-1-aarch64.pkg.tar.xz (Termux pacman format)
# 3. Deb: opencode2_${RELEASE_VERSION}_aarch64.deb (Termux deb format)
#
# Layouts (the wrapper supports both):
#   zip:      opencode2, opencode2.bin, libopentui.so in one directory
#   packages: $PREFIX/bin/opencode2, $PREFIX/libexec/opencode2/opencode2.bin,
#             $PREFIX/libexec/opencode2/libopentui.so
#
# All v2 files live under bin/ and libexec/opencode2/ so the package never
# shares a path with the v1 "opencode" package (which owns lib/libopentui.so).
# The two can therefore be installed side by side.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env-v2.sh"

BIN="$DIST_DIR/opencode2.bin"
LIB="$OPENTUI_LIB"
OUT="$PACKAGE_DIR"
mkdir -p "$OUT" "$DIST_DIR/flat"
test -x "$BIN"
test -f "$LIB"
python3 "$SCRIPT_DIR/v2.py" elf "$BIN"
python3 "$SCRIPT_DIR/v2.py" elf "$LIB"
python3 "$SCRIPT_DIR/v2.py" record
export TZ=UTC
umask 022

echo "=== Creating packages for opencode2 v${RELEASE_VERSION} ==="

# ==========================================
# Wrapper (identical file ships in zip, pacman, deb)
# ==========================================
cat > "$DIST_DIR/flat/opencode2" <<'WEOF'
#!/data/data/com.termux/files/usr/bin/sh
# opencode2 - wrapper for the OpenCode 2 CLI on Android/Termux
#
# Path resolution order (supports both layouts):
#   flat zip:    opencode2, opencode2.bin, libopentui.so in the same directory
#   installed:   bin/opencode2 and libexec/opencode2/{opencode2.bin,libopentui.so}
set -eu

SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
DIR="$(CDPATH= cd -- "$(dirname "$SELF")" && pwd)"

# Termux markers, in case we are launched outside a Termux shell
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"

# Select binary and renderer as one pair; never mix two installations.
export OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER="${OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER:-true}"
for candidate in "$DIR/../libexec/opencode2" "$DIR" "$PREFIX/libexec/opencode2"; do
    if [ -x "$candidate/opencode2.bin" ] && [ -f "$candidate/libopentui.so" ]; then
        export OPENTUI_LIB_PATH="$candidate/libopentui.so"
        export LD_LIBRARY_PATH="$candidate${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        exec "$candidate/opencode2.bin" "$@"
    fi
done

echo "opencode2: error: could not find opencode2.bin" >&2
exit 127
WEOF

cp "$BIN" "$DIST_DIR/flat/opencode2.bin"
cp "$LIB" "$DIST_DIR/flat/libopentui.so"
chmod 755 "$DIST_DIR/flat/opencode2" "$DIST_DIR/flat/opencode2.bin"
chmod 644 "$DIST_DIR/flat/libopentui.so"
find "$DIST_DIR/flat" -type f -exec touch -d "@$SOURCE_DATE_EPOCH" {} +

# ==========================================
# 1. ZIP package
# ==========================================
echo ">>> Creating ZIP package..."
ZIP="$OUT/opencode2-${RELEASE_VERSION}-android-aarch64.zip"
rm -f "$ZIP"
(cd "$DIST_DIR/flat" && zip -X -9 "$ZIP" opencode2 opencode2.bin libopentui.so >/dev/null)
echo "    Created $ZIP"

# ==========================================
# 2. Pacman package (Termux)
# ==========================================
echo ">>> Creating pacman package..."
STAGE="$(mktemp -d "$WORK_DIR/pacman.XXXXXXXX")"
DEB_STAGE="$(mktemp -d "$WORK_DIR/deb.XXXXXXXX")"
trap 'rm -rf "$STAGE" "$DEB_STAGE"' EXIT
mkdir -p "$STAGE/data/data/com.termux/files/usr/bin"
mkdir -p "$STAGE/data/data/com.termux/files/usr/libexec/opencode2"
cp "$DIST_DIR/flat/opencode2" "$STAGE/data/data/com.termux/files/usr/bin/opencode2"
cp "$BIN" "$STAGE/data/data/com.termux/files/usr/libexec/opencode2/opencode2.bin"
cp "$LIB" "$STAGE/data/data/com.termux/files/usr/libexec/opencode2/libopentui.so"
chmod 644 "$STAGE/data/data/com.termux/files/usr/libexec/opencode2/libopentui.so"
chmod 755 "$STAGE/data/data/com.termux/files/usr/bin/opencode2"
chmod 755 "$STAGE/data/data/com.termux/files/usr/libexec/opencode2/opencode2.bin"
cat > "$STAGE/.PKGINFO" <<PEOF
pkgname = opencode2
pkgver = ${PACMAN_VERSION}-${PACKAGE_REVISION}
pkgdesc = OpenCode 2 AI coding assistant for Android/Termux
url = https://github.com/guysoft/opencode-termux
builddate = ${SOURCE_DATE_EPOCH}
packager = opencode-termux
size = $(( $(stat -c%s "$BIN") + $(stat -c%s "$LIB") + $(stat -c%s "$DIST_DIR/flat/opencode2") ))
arch = aarch64
license = MIT
depend = ripgrep
PEOF

PACMAN_NAME="opencode2-${PACMAN_VERSION}-${PACKAGE_REVISION}-aarch64.pkg.tar.xz"
(cd "$STAGE" && tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner -cf - .PKGINFO data | xz -T1 -9 > "$OUT/$PACMAN_NAME")
echo "    Created $PACMAN_NAME"

# ==========================================
# 3. Deb package (Termux)
# ==========================================
echo ">>> Creating deb package..."
mkdir -p "$DEB_STAGE/DEBIAN"
cp -a "$STAGE/data" "$DEB_STAGE/data"
cat > "$DEB_STAGE/DEBIAN/control" <<DEOF
Package: opencode2
Version: ${RELEASE_VERSION}
Architecture: aarch64
Maintainer: Guy Sheffer <guysoft@gmail.com>
Installed-Size: $(du -sk "$DEB_STAGE/data" | cut -f1)
Depends: ripgrep
Section: utils
Priority: optional
Homepage: https://github.com/guysoft/opencode-termux
Description: OpenCode 2 AI coding assistant for Android/Termux
 This package provides the OpenCode v2 CLI (opencode2) and the Android
 OpenTUI renderer. It installs alongside the v1 opencode package.
DEOF
find "$DEB_STAGE" -exec touch -d "@$SOURCE_DATE_EPOCH" {} +
dpkg-deb --root-owner-group -Zxz --build "$DEB_STAGE" "$OUT/opencode2_${RELEASE_VERSION}_aarch64.deb"
DEB_NAME="opencode2_${RELEASE_VERSION}_aarch64.deb"
echo "    Created $DEB_NAME"

# ==========================================
# Summary
# ==========================================
rm -rf "$STAGE" "$DEB_STAGE"
(cd "$OUT" && sha256sum "$DEB_NAME" "$PACMAN_NAME" "opencode2-${RELEASE_VERSION}-android-aarch64.zip" > SHA256SUMS)
echo ""
cp "$DIST_DIR/build-record.json" "$OUT/build-record.json"
echo "=== Packages created ==="
echo ""
ls -lh "$OUT"/*.{zip,xz,deb} "$OUT/SHA256SUMS"
echo ""
echo "Install on Termux:"
echo "  pacman -U $PACMAN_NAME"
echo "  dpkg -i $DEB_NAME"
echo "  unzip opencode2-${RELEASE_VERSION}-android-aarch64.zip"
