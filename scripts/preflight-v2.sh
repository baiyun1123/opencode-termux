#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env-v2.sh"
stage="${1:-all}"
case "$stage" in all|bun|opentui) ;; *) echo "Unknown build stage: $stage" >&2; exit 1 ;; esac
errors=0
fail() { echo "ERROR: $*" >&2; errors=$((errors + 1)); }
commands=(git python3 readelf)
if [[ "$stage" != opentui ]]; then commands+=(cmake ninja rustup zip xz dpkg-deb); fi
for cmd in "${commands[@]}"; do
  command -v "$cmd" >/dev/null || fail "Missing tool: $cmd"
done
if [[ "$stage" != opentui ]]; then
if command -v "$HOST_BUN" >/dev/null; then
  [[ "$("$HOST_BUN" --version)" == "$BUN_VERSION" ]] || fail "Host Bun must be $BUN_VERSION"
else fail 'Host Bun missing; run python3 scripts/bootstrap-v2.py'; fi
fi
if [[ "$stage" != bun ]]; then
if command -v "$ZIG_BIN" >/dev/null; then
  [[ "$("$ZIG_BIN" version)" == "$ZIG_VERSION" ]] || fail "Zig must be $ZIG_VERSION"
else fail 'Zig missing; run python3 scripts/bootstrap-v2.py'; fi
fi
if [[ -f "$ANDROID_NDK_HOME/source.properties" ]]; then
  grep -Eq "Pkg.Revision[[:space:]]*=[[:space:]]*$NDK_VERSION" "$ANDROID_NDK_HOME/source.properties" || fail "NDK must be $NDK_VERSION"
else fail "NDK missing: $ANDROID_NDK_HOME"; fi
[[ -d "$NDK_SYSROOT/usr/lib/aarch64-linux-android/$ANDROID_API" ]] || fail 'NDK target API sysroot missing'
if [[ "$stage" != opentui ]]; then
TC="${BUN_TOOLCHAIN_LLVM:-/usr/lib/llvm-21}"
if [[ -x "$TC/bin/clang" && -x "$TC/bin/ld.lld" ]]; then
  "$TC/bin/clang" --version | grep -Fq "version $LLVM_VERSION" || fail "LLVM clang $LLVM_VERSION required"
  "$TC/bin/ld.lld" --version | grep -Fq "LLD $LLVM_VERSION" || fail "LLVM lld $LLVM_VERSION required"
else fail "LLVM 21 missing: $TC"; fi
fi
[[ "${V2_JOBS:-2}" =~ ^[1-9][0-9]*$ ]] || fail 'V2_JOBS must be a positive integer'
if [[ "${V2_RESOURCE_GATE:-0}" == 1 ]]; then
  mkdir -p "$WORK_DIR"
  profile="${V2_RESOURCE_PROFILE:-dedicated}"
  case "$profile" in
    dedicated) min_mem=30000000; min_disk=125829120 ;;
    hosted-experimental)
      min_mem=12000000; min_disk=41943040
      echo 'Experimental hosted build: 2 jobs recommended; full build may still exhaust resources.' ;;
    *) fail "Unknown resource profile: $profile"; min_mem=30000000; min_disk=125829120 ;;
  esac
  memory=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
  disk=$(df -Pk "$WORK_DIR" | awk 'END {print $4}')
  echo "Resource profile: $profile; RAM=${memory}KiB; free disk=${disk}KiB"
  (( memory >= min_mem )) || fail "Insufficient RAM for $profile (need ${min_mem}KiB)"
  (( disk >= min_disk )) || fail "Insufficient free disk for $profile (need ${min_disk}KiB)"
fi
(( errors == 0 )) || { echo "$errors preflight check(s) failed" >&2; exit 1; }
echo 'Toolchain and resource preflight PASS; Android runtime: NOT TESTED'
