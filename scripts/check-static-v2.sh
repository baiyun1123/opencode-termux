#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for script in scripts/*v2*.sh scripts/build-bun-android.sh scripts/build-opencode2-android.sh; do bash -n "$script"; done
python3 scripts/v2.py validate
python3 scripts/bootstrap-v2.py --validate
python3 -m unittest discover -s tests -p 'test*v2.py' -v
# Parse patch structure without needing multi-gigabyte upstream checkouts.
for patch in patches/bun/android-seccomp-sigsys.patch patches/bun/v1.4.2-android-build-paths.patch patches/opentui/v2-0.5.10-android.patch patches/opentui/v2-0.5.10-reproducible-paths.patch; do git apply --stat "$patch"; done
if command -v actionlint >/dev/null; then actionlint .github/workflows/*v2.yml; fi
if command -v shellcheck >/dev/null; then
  shellcheck -x -e SC1091 scripts/setup-host-v2.sh scripts/env-v2.sh scripts/prepare-source-v2.sh scripts/preflight-v2.sh scripts/test-build-v2.sh scripts/verify-packages-v2.sh scripts/build-bun-android.sh scripts/build-opentui-v2.sh scripts/build-opencode2-android.sh scripts/make-packages-v2.sh
fi
