#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env-v2.sh"

"$SCRIPT_DIR/preflight-v2.sh"
"$SCRIPT_DIR/prepare-source-v2.sh" opentui
src="$OPENTUI_SRC"

rm -rf "$BIONIC_SYSROOT_INC"
mkdir -p "$BIONIC_SYSROOT_INC"
cp -a "$NDK_SYSROOT/usr/include/." "$BIONIC_SYSROOT_INC/"
cp -a "$NDK_SYSROOT/usr/include/aarch64-linux-android/." "$BIONIC_SYSROOT_INC/"

# Vendored deps the shim headers reference as "../miniaudio.h" / "../yoga/yoga/Yoga.h"
mkdir -p "$BIONIC_SYSROOT_INC/yoga"
cp -a "$src/packages/native/src/vendor/miniaudio/miniaudio.h" "$BIONIC_SYSROOT_INC/miniaudio.h"
cp -a "$src/packages/native/zig-deps/yoga/yoga" "$BIONIC_SYSROOT_INC/yoga/yoga"
mkdir -p "$BIONIC_SYSROOT_INC/__opentui"
cat > "$BIONIC_SYSROOT_INC/__opentui/miniaudio_shimmed.h" <<'EOF'
#define _Nullable
#define _Nonnull
#include "../miniaudio.h"
EOF
cat > "$BIONIC_SYSROOT_INC/__opentui/Yoga_shimmed.h" <<'EOF'
#define _Nullable
#define _Nonnull
#include "../yoga/yoga/Yoga.h"
EOF

cat > "$ZIG_LIBC" <<EOF
include_dir=$BIONIC_SYSROOT_INC
sys_include_dir=$BIONIC_SYSROOT_INC
crt_dir=$NDK_SYSROOT/usr/lib/aarch64-linux-android/$ANDROID_API
msvc_lib_dir=
kernel32_lib_dir=
gcc_dir=
EOF

export ANDROID_NDK_HOME BIONIC_SYSROOT_INC ZIG_LIBC
cd "$src/packages/native"
"$ZIG_BIN" build -Dlibrary-target=aarch64-linux-android -Doptimize=ReleaseSafe
cp "lib/aarch64-linux-android/libopentui.so" "$OPENTUI_LIB"

python3 "$SCRIPT_DIR/v2.py" elf "$OPENTUI_LIB"
python3 "$SCRIPT_DIR/v2.py" cache-stamp "$OPENTUI_LIB"
