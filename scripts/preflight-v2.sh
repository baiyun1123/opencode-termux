#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env-v2.sh"
for cmd in git python3 readelf cmake ninja rustup zip xz dpkg-deb; do
  command -v "$cmd" >/dev/null || { echo "Missing tool: $cmd" >&2; exit 1; }
done
[[ "$("$HOST_BUN" --version)" == "$BUN_VERSION" ]] || { echo 'Host Bun version mismatch' >&2; exit 1; }
[[ "$("$ZIG_BIN" version)" == "$ZIG_VERSION" ]] || { echo 'Zig version mismatch' >&2; exit 1; }
grep -Eq "Pkg.Revision[[:space:]]*=[[:space:]]*$NDK_VERSION" "$ANDROID_NDK_HOME/source.properties"
test -d "$NDK_SYSROOT/usr/lib/aarch64-linux-android/$ANDROID_API"
TC="${BUN_TOOLCHAIN_LLVM:-/usr/lib/llvm-21}"
"$TC/bin/clang" --version | grep -Eq 'version 21\.'
"$TC/bin/ld.lld" --version | grep -Eq 'LLD 21\.'
# Resource gate is advisory locally; CI explicitly enables it for full builds.
if [[ "${V2_RESOURCE_GATE:-0}" == 1 ]]; then
  mkdir -p "$WORK_DIR"
  awk '/MemTotal/ {if ($2 < 30000000) exit 1}' /proc/meminfo || { echo 'Full build requires >=32GB RAM; use a dedicated runner' >&2; exit 1; }
  available=$(df -Pk "$WORK_DIR" | awk 'END {print $4}')
  (( available >= 125829120 )) || { echo 'Full build requires >=120GiB free disk' >&2; exit 1; }
fi
