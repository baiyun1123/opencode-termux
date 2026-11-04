#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env-v2.sh"
python3 "$REPO_ROOT/scripts/v2.py" prepare "$@"
