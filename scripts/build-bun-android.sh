#!/usr/bin/env bash
# Build a patched Bun runtime for Android aarch64 that converts seccomp SIGSYS
# traps into ENOSYS, so calls with an ENOSYS fallback (close_range, openat2,
# fchmodat2, pidfd_open, clone3, ...) work under Android's SECCOMP_RET_TRAP
# policy instead of killing the process with "Bad system call" (exit 159).
#
# Upstream: oven-sh/bun#30766 / #39060, fix in PR #39775 and #30769.
# Maintained as patches/bun/android-seccomp-sigsys.patch.
#
# Output: $DIST_DIR/bun-android/bun
#
# Host requirements: Rust (bun's pinned nightly), Ninja, CMake, LLVM 21
# (clang + lld), Android NDK r26+ ($ANDROID_NDK_HOME).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env-v2.sh"

OUT_DIR="${DIST_DIR}/bun-android"
"$SCRIPT_DIR/preflight-v2.sh" bun
"$SCRIPT_DIR/prepare-source-v2.sh" bun

# Use a provisioned LLVM 21 toolchain; never overwrite system symlinks.
TC="${BUN_TOOLCHAIN_LLVM:-/usr/lib/llvm-21}"
test -x "$TC/bin/clang"
test -x "$TC/bin/ld.lld"
export BUN_TOOLCHAIN_LLVM="$TC"

echo ">>> building (NDK=$ANDROID_NDK_HOME, LLVM=${TC:-system})"
ENVV=(ANDROID_NDK_ROOT="$ANDROID_NDK_HOME")
[ -n "$TC" ] && ENVV+=(BUN_TOOLCHAIN_LLVM="$TC")
# The locked Bun CLI cannot accept numeric androidApiLevel via --field.
# Its supported config-file route configures only, then Ninja builds the target.
python3 - <<'CONFIG'
import json, os
from pathlib import Path
p = Path(os.environ['WORK_DIR']) / 'bun-build-config.json'
p.write_text(json.dumps({'profile': 'android-release', 'overrides': {
    'buildDir': 'build/android-release', 'androidApiLevel': int(os.environ['ANDROID_API'])}})+'\n')
CONFIG
(cd "$BUN_SRC" && env "${ENVV[@]}" "$HOST_BUN" scripts/build.ts \
  --config-file="$WORK_DIR/bun-build-config.json")
# The non-CI Android profile must still map C/C++ and Rust source paths.
grep -Fq -- '--remap-path-prefix=' "$BUN_SRC/build/android-release/build.ninja"
grep -Fq -- '-ffile-prefix-map=' "$BUN_SRC/build/android-release/build.ninja"
ninja -j "${V2_JOBS:-2}" -C "$BUN_SRC/build/android-release" bun

mkdir -p "$OUT_DIR"
cp "$BUN_SRC/build/android-release/bun" "$OUT_DIR/bun"
chmod 755 "$OUT_DIR/bun"
echo ">>> patched Android Bun: $OUT_DIR/bun ($(stat -c%s "$OUT_DIR/bun") bytes)"

python3 "$SCRIPT_DIR/v2.py" elf "$OUT_DIR/bun"
python3 "$SCRIPT_DIR/v2.py" cache-stamp "$OUT_DIR/bun"
