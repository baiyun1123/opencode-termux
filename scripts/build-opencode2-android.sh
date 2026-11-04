#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env-v2.sh"

"$SCRIPT_DIR/preflight-v2.sh"
"$SCRIPT_DIR/prepare-source-v2.sh" opencode
mkdir -p "$DIST_DIR"
cd "$OPENCODE_WORKTREE"
host_bun_path="$(command -v "$HOST_BUN")"
PATH="$(dirname "$host_bun_path"):$PATH"
export PATH
export BUN_COMPILE_RELEASE="bun-v${BUN_VERSION}"
export OPENCODE_BUN_RUNTIME="$DIST_DIR/bun-android/bun"
test -x "$OPENCODE_BUN_RUNTIME"
python3 "$SCRIPT_DIR/v2.py" cache-check "$OPENCODE_BUN_RUNTIME"
python3 "$SCRIPT_DIR/v2.py" cache-check "$OPENTUI_LIB"
python3 "$SCRIPT_DIR/v2.py" elf "$OPENCODE_BUN_RUNTIME"
# Never silently fall back to the unpatched release runtime.
"$HOST_BUN" install --frozen-lockfile --ignore-scripts --os='*' --cpu='*'
cd packages/cli
"$HOST_BUN" run script/build.ts \
  --target=opencode2-linux-arm64-android --skip-install \
  --skip-web-ui --outdir="$DIST_DIR/cli"
cp "$DIST_DIR/cli/cli-linux-arm64-android/bin/opencode2" "$DIST_DIR/opencode2.bin"
chmod 755 "$DIST_DIR/opencode2.bin"
python3 "$SCRIPT_DIR/v2.py" elf "$DIST_DIR/opencode2.bin"
python3 "$SCRIPT_DIR/v2.py" verify-source opencode
