#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env-v2.sh"
mkdir -p "$WORK_DIR/logs"
exec > >(tee "$WORK_DIR/logs/build.log") 2>&1
finish() {
  printf "Build exit status: %s\nAndroid runtime: NOT TESTED\n" "$1" > "$WORK_DIR/logs/status.txt"
}
trap 'finish "$?"' EXIT
"$REPO_ROOT/scripts/preflight-v2.sh"
"$REPO_ROOT/scripts/prepare-source-v2.sh"
# Only complete, key-specific artifacts are cached. Each stage still checks its output.
if [[ ! -f "$DIST_DIR/bun-android/bun" ]]; then "$REPO_ROOT/scripts/build-bun-android.sh"; fi
python3 "$REPO_ROOT/scripts/v2.py" cache-check "$DIST_DIR/bun-android/bun"
python3 "$REPO_ROOT/scripts/v2.py" elf "$DIST_DIR/bun-android/bun"
if [[ ! -f "$OPENTUI_LIB" ]]; then "$REPO_ROOT/scripts/build-opentui-v2.sh"; fi
python3 "$REPO_ROOT/scripts/v2.py" cache-check "$OPENTUI_LIB"
python3 "$REPO_ROOT/scripts/v2.py" elf "$OPENTUI_LIB"
"$REPO_ROOT/scripts/build-opencode2-android.sh"
"$REPO_ROOT/scripts/make-packages-v2.sh"
"$REPO_ROOT/scripts/verify-packages-v2.sh"
